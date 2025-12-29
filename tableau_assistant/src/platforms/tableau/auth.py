"""
Tableau 认证模块

支持两种认证方式：
- JWT (Connected App)
- PAT (Personal Access Token)

Token 自动缓存 10 分钟（仅缓存成功的认证）

认证上下文通过 RunnableConfig 传递给工作流节点：
- 工作流启动时获取一次 token
- 通过 RunnableConfig["configurable"]["workflow_context"].auth 传递
- Token 过期时自动刷新
"""
import os
import time
import logging
import requests
import jwt
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from langgraph.types import RunnableConfig

logger = logging.getLogger(__name__)


# SSL 配置
from tableau_assistant.src.infra.certs import get_certificate_config

def _get_requests_verify(target_domain: Optional[str] = None):
    """
    获取 requests 的 SSL 验证参数
    
    支持多环境：根据目标域名返回对应的证书
    
    Args:
        target_domain: 目标 Tableau 域名（可选）
                      如果提供，会查找该域名对应的证书文件
    
    Returns:
        - 证书文件路径（如果找到域名对应的证书）
        - True（使用系统证书，如 Tableau Cloud）
        - False（禁用 SSL 验证，不推荐）
    """
    from pathlib import Path
    from urllib.parse import urlparse
    
    # 获取全局配置
    cert_config = get_certificate_config()
    
    # 如果没有指定域名，使用全局配置
    if not target_domain:
        return cert_config.get_verify_param()
    
    # 解析域名
    parsed = urlparse(target_domain)
    hostname = (parsed.netloc or target_domain).lower()
    
    # 检查是否是 Tableau Cloud
    # 使用 certifi 的证书而不是系统证书，避免 Windows 上的 SSL 问题
    if "online.tableau.com" in hostname:
        try:
            import certifi
            cert_path = certifi.where()
            logger.debug(f"Tableau Cloud ({hostname}) 使用 certifi 证书: {cert_path}")
            return cert_path
        except ImportError:
            logger.debug(f"Tableau Cloud ({hostname}) certifi 未安装，使用系统证书")
            return True
    
    # 查找域名对应的证书文件
    # 证书文件命名格式: {safe_hostname}_cert.pem
    # 注意：hostname 可能包含端口号，需要同时尝试带端口和不带端口的文件名
    safe_hostname_with_port = hostname.replace('.', '_').replace(':', '_')
    # 去掉端口号的版本
    hostname_no_port = hostname.split(':')[0]
    safe_hostname_no_port = hostname_no_port.replace('.', '_')
    
    cert_dir = Path(cert_config.cert_dir)
    
    # 尝试多种可能的证书文件名（优先使用完整证书链）
    possible_cert_files = [
        cert_dir / f"{safe_hostname_with_port}_full_chain.pem",  # 完整证书链（带端口）
        cert_dir / f"{safe_hostname_no_port}_full_chain.pem",    # 完整证书链（不带端口）
        cert_dir / f"{safe_hostname_with_port}_cert.pem",  # 带端口
        cert_dir / f"{safe_hostname_no_port}_cert.pem",    # 不带端口
        cert_dir / f"{safe_hostname_with_port}.pem",
        cert_dir / f"{safe_hostname_no_port}.pem",
        cert_dir / "tableau_cert.pem",  # 全局 Tableau 证书
    ]
    
    for cert_file in possible_cert_files:
        if cert_file.exists():
            logger.info(f"SSL: 使用证书文件 {cert_file} (域名: {hostname})")
            return str(cert_file)
    
    logger.debug(f"SSL: 未找到证书文件，尝试过: {[str(f) for f in possible_cert_files]}")
    
    # 没有找到域名对应的证书，尝试自动获取
    logger.info(f"未找到域名 {hostname} 的证书，尝试自动获取...")
    try:
        from tableau_assistant.src.infra.certs import CertificateManager
        manager = CertificateManager()
        
        # 解析端口（使用不带端口的主机名）
        port = parsed.port or 443
        
        # 获取并保存证书（使用不带端口的主机名）
        result = manager.fetch_and_save_certificates(hostname_no_port, port)
        cert_file = result.get("server_cert")
        if cert_file and Path(cert_file).exists():
            logger.info(f"已获取并保存证书: {cert_file}")
            return cert_file
    except Exception as e:
        logger.warning(f"自动获取证书失败: {e}")
    
    # 回退到全局配置
    logger.warning(f"未找到域名 {hostname} 的证书，使用全局配置")
    return cert_config.get_verify_param()

# Token 缓存（仅缓存成功的认证）
# 支持多环境：使用 domain 作为缓存 key
_CTX_TTL_SEC: int = 600  # 10 分钟
_ctx_cache: Dict[str, Dict[str, Any]] = {}  # domain -> cache_data
_ctx_cached_at: Dict[str, float] = {}  # domain -> cached_at


# ═══════════════════════════════════════════════════════════════════════════
# Tableau 认证上下文（Pydantic 模型）
# ═══════════════════════════════════════════════════════════════════════════

class TableauAuthContext(BaseModel):
    """
    Tableau 认证上下文
    
    通过 RunnableConfig["configurable"]["workflow_context"].auth 传递给所有节点。
    
    Attributes:
        api_key: Tableau API token
        site: Tableau site content URL
        domain: Tableau server domain
        expires_at: Token 过期时间戳
        auth_method: 认证方式 ("jwt" 或 "pat")
    """
    api_key: str
    site: str = ""
    domain: str = ""
    expires_at: float = Field(default_factory=lambda: time.time() + 600)
    auth_method: str = "unknown"
    
    def is_expired(self, buffer_seconds: int = 60) -> bool:
        """检查 token 是否即将过期"""
        return time.time() >= (self.expires_at - buffer_seconds)
    
    @property
    def remaining_seconds(self) -> float:
        """剩余有效时间（秒）"""
        return max(0, self.expires_at - time.time())


class TableauAuthError(Exception):
    """Tableau 认证错误"""
    pass


def _get_tableau_context_from_env(target_domain: Optional[str] = None) -> Dict[str, Any]:
    """
    获取 Tableau token，支持 JWT 和 PAT 两种认证方式。
    支持多环境：根据 target_domain 选择对应的配置。
    优先使用 JWT，如果 JWT 配置不完整则尝试 PAT。
    
    Args:
        target_domain: 目标 Tableau 域名（可选），如果不提供则使用默认配置
    
    JWT 必需：TABLEAU_DOMAIN, TABLEAU_JWT_CLIENT_ID, TABLEAU_JWT_SECRET_ID, TABLEAU_JWT_SECRET, TABLEAU_USER
    PAT 必需：TABLEAU_DOMAIN, TABLEAU_PAT_NAME, TABLEAU_PAT_SECRET
    可选：TABLEAU_SITE, TABLEAU_API_VERSION(默认 3.18)
    
    Token 10 分钟缓存（按域名分别缓存）
    返回: {"domain": str, "site": str, "api_key": Optional[str]}
    """
    from tableau_assistant.src.infra.config.tableau_env import get_tableau_config
    
    # 获取对应环境的配置
    tableau_config = get_tableau_config(target_domain)
    
    domain = tableau_config.domain.strip().rstrip("/")
    site = tableau_config.site.strip()
    tableau_api_version = tableau_config.api_version.strip()
    
    # JWT 配置
    jwt_client_id = tableau_config.jwt_client_id.strip()
    jwt_secret_id = tableau_config.jwt_secret_id.strip()
    jwt_secret = tableau_config.jwt_secret.strip()
    tableau_user = tableau_config.user.strip()
    
    # PAT 配置
    pat_name = tableau_config.pat_name.strip()
    pat_secret = tableau_config.pat_secret.strip()

    # 检查缓存（按域名分别缓存）
    global _ctx_cache, _ctx_cached_at
    now = time.time()
    cache_key = domain.lower()
    
    if cache_key in _ctx_cache:
        cached = _ctx_cache[cache_key]
        cached_at = _ctx_cached_at.get(cache_key, 0)
        if cached.get("api_key") and (now - cached_at) < _CTX_TTL_SEC:
            logger.debug(f"使用缓存的认证: {domain}")
            return {"domain": cached["domain"], "site": cached["site"], "api_key": cached["api_key"]}

    # 尝试 JWT 认证
    jwt_error = None
    if all([domain, jwt_client_id, jwt_secret_id, jwt_secret, tableau_user]):
        try:
            logger.debug(f"尝试 JWT 认证: domain={domain}, user={tableau_user}")
            session = jwt_connected_app(
                tableau_domain=domain,
                tableau_site=site,
                tableau_api=tableau_api_version,
                tableau_user=tableau_user,
                jwt_client_id=jwt_client_id,
                jwt_secret_id=jwt_secret_id,
                jwt_secret=jwt_secret,
                scopes=["tableau:content:read"],
            )
            api_key = (session.get("credentials") or {}).get("token")
            if api_key:
                logger.info(f"JWT 认证成功: {domain}")
                _ctx_cache[cache_key] = {"domain": domain, "site": site, "api_key": api_key, "auth_method": "jwt"}
                _ctx_cached_at[cache_key] = now
                return {"domain": domain, "site": site, "api_key": api_key, "auth_method": "jwt"}
        except Exception as e:
            jwt_error = str(e)
            logger.warning(f"JWT 认证失败 ({domain}): {e}")
    else:
        logger.debug(f"JWT 配置不完整，跳过 JWT 认证: {domain}")

    # 尝试 PAT 认证
    pat_error = None
    if all([domain, pat_name, pat_secret]):
        try:
            logger.debug(f"尝试 PAT 认证: domain={domain}, pat_name={pat_name}")
            session = pat_authentication(
                tableau_domain=domain,
                tableau_site=site,
                tableau_api=tableau_api_version,
                pat_name=pat_name,
                pat_secret=pat_secret,
            )
            api_key = (session.get("credentials") or {}).get("token")
            if api_key:
                logger.info(f"PAT 认证成功: {domain}")
                _ctx_cache[cache_key] = {"domain": domain, "site": site, "api_key": api_key, "auth_method": "pat"}
                _ctx_cached_at[cache_key] = now
                return {"domain": domain, "site": site, "api_key": api_key, "auth_method": "pat"}
        except Exception as e:
            pat_error = str(e)
            logger.warning(f"PAT 认证失败 ({domain}): {e}")
    else:
        logger.debug(f"PAT 配置不完整，跳过 PAT 认证: {domain}")

    # 认证失败 - 不缓存失败结果，下次请求会重试
    error_msg = f"所有认证方式均失败 ({domain})。JWT: {jwt_error or '未配置'}, PAT: {pat_error or '未配置'}"
    logger.error(error_msg)
    return {"domain": domain, "site": site, "api_key": None, "error": error_msg}


def jwt_connected_app(
    tableau_domain: str,
    tableau_site: str,
    tableau_api: str,
    tableau_user: str,
    jwt_client_id: str,
    jwt_secret_id: str,
    jwt_secret: str,
    scopes: List[str],
) -> Dict[str, Any]:
    """使用 JWT Connected App 认证"""
    token = jwt.encode(
        {
            "iss": jwt_client_id,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
            "jti": str(uuid4()),
            "aud": "tableau",
            "sub": tableau_user,
            "scp": scopes
        },
        jwt_secret,
        algorithm="HS256",
        headers={"kid": jwt_secret_id, "iss": jwt_client_id}
    )

    endpoint = f"{tableau_domain}/api/{tableau_api}/auth/signin"
    payload = {
        "credentials": {
            "jwt": token,
            "site": {"contentUrl": tableau_site}
        }
    }

    response = requests.post(
        endpoint,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        json=payload,
        verify=_get_requests_verify(tableau_domain)
    )

    if response.status_code == 200:
        return response.json()
    raise RuntimeError(f"JWT auth failed: {response.status_code} - {response.text}")


def pat_authentication(
    tableau_domain: str,
    tableau_site: str,
    tableau_api: str,
    pat_name: str,
    pat_secret: str,
) -> Dict[str, Any]:
    """使用 Personal Access Token 认证"""
    endpoint = f"{tableau_domain}/api/{tableau_api}/auth/signin"
    payload = {
        "credentials": {
            "personalAccessTokenName": pat_name,
            "personalAccessTokenSecret": pat_secret,
            "site": {"contentUrl": tableau_site}
        }
    }

    response = requests.post(
        endpoint,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        json=payload,
        verify=_get_requests_verify(tableau_domain)
    )

    if response.status_code == 200:
        return response.json()
    raise RuntimeError(f"PAT auth failed: {response.status_code} - {response.text}")


# ═══════════════════════════════════════════════════════════════════════════
# 认证获取函数（统一入口）
# ═══════════════════════════════════════════════════════════════════════════

def get_tableau_auth(
    target_domain: Optional[str] = None,
    force_refresh: bool = False
) -> TableauAuthContext:
    """
    获取 Tableau 认证上下文（同步版本）
    
    支持多环境：根据 target_domain 选择对应的配置。
    
    优先级：
    1. 内存缓存（如果未过期）
    2. 调用认证 API 获取新 token
    
    Args:
        target_domain: 目标 Tableau 域名（可选），如果不提供则使用默认配置
        force_refresh: 是否强制刷新 token
    
    Returns:
        TableauAuthContext 认证上下文
    
    Raises:
        TableauAuthError: 认证失败
    """
    global _ctx_cache, _ctx_cached_at
    
    # 获取缓存 key
    from tableau_assistant.src.infra.config.tableau_env import get_tableau_config
    tableau_config = get_tableau_config(target_domain)
    cache_key = tableau_config.domain.lower().rstrip("/")
    
    # 1. 检查内存缓存
    if not force_refresh and cache_key in _ctx_cache:
        cached = _ctx_cache[cache_key]
        cached_at = _ctx_cached_at.get(cache_key, 0)
        now = time.time()
        if cached.get("api_key") and (now - cached_at) < _CTX_TTL_SEC:
            return TableauAuthContext(
                api_key=cached["api_key"],
                site=cached.get("site", ""),
                domain=cached.get("domain", ""),
                expires_at=cached_at + _CTX_TTL_SEC,
                auth_method=cached.get("auth_method", "unknown"),
            )
    
    # 2. 获取新 token
    ctx = _get_tableau_context_from_env(target_domain)
    
    api_key = ctx.get("api_key")
    if not api_key:
        error_msg = ctx.get("error", f"认证失败，请检查 .env 中的 Tableau 配置 ({target_domain or 'default'})")
        raise TableauAuthError(error_msg)
    
    return TableauAuthContext(
        api_key=api_key,
        site=ctx.get("site", ""),
        domain=ctx.get("domain", ""),
        expires_at=time.time() + _CTX_TTL_SEC,
        auth_method=ctx.get("auth_method", "unknown"),
    )


async def get_tableau_auth_async(
    target_domain: Optional[str] = None,
    force_refresh: bool = False
) -> TableauAuthContext:
    """
    获取 Tableau 认证上下文（异步版本）
    
    支持多环境：根据 target_domain 选择对应的配置。
    
    注意：当前实现是同步的，因为 Tableau API 调用是同步的。
    提供异步接口是为了与异步工作流兼容。
    
    Args:
        target_domain: 目标 Tableau 域名（可选），如果不提供则使用默认配置
        force_refresh: 是否强制刷新 token
    """
    return get_tableau_auth(target_domain=target_domain, force_refresh=force_refresh)


# ═══════════════════════════════════════════════════════════════════════════
# RunnableConfig 集成
# ═══════════════════════════════════════════════════════════════════════════

def create_config_with_auth(
    thread_id: str,
    auth_ctx: TableauAuthContext,
    **extra_configurable: object,
) -> dict:
    """
    创建带 Tableau 认证的 RunnableConfig
    
    Args:
        thread_id: 线程/会话 ID
        auth_ctx: Tableau 认证上下文
        **extra_configurable: 额外的配置项
    
    Returns:
        RunnableConfig 字典
    """
    return {
        "configurable": {
            "thread_id": thread_id,
            "tableau_auth": auth_ctx.model_dump(),
            **extra_configurable,
        }
    }


def get_auth_from_config(config: Optional[RunnableConfig]) -> Optional[TableauAuthContext]:
    """
    从 RunnableConfig 获取 Tableau 认证上下文
    
    Args:
        config: RunnableConfig 配置
    
    Returns:
        TableauAuthContext 或 None
    """
    if config is None:
        return None
    
    configurable = config.get("configurable", {})
    
    # 从 workflow_context 获取认证
    workflow_context = configurable.get("workflow_context")
    if workflow_context is not None:
        return workflow_context.auth
    
    return None


def ensure_valid_auth(config: Optional[RunnableConfig] = None) -> TableauAuthContext:
    """
    确保有有效的 Tableau 认证（同步版本）
    
    优先级：
    1. 从 config 获取（如果未过期）
    2. 获取新 token
    
    Args:
        config: RunnableConfig 配置（可选）
    
    Returns:
        有效的 TableauAuthContext
    
    Raises:
        TableauAuthError: 认证失败
    """
    # 1. 尝试从 config 获取
    if config is not None:
        auth_ctx = get_auth_from_config(config)
        if auth_ctx and not auth_ctx.is_expired():
            return auth_ctx
    
    # 2. 获取新 token
    return get_tableau_auth(force_refresh=True)


async def ensure_valid_auth_async(config: Optional[RunnableConfig] = None) -> TableauAuthContext:
    """
    确保有有效的 Tableau 认证（异步版本）
    """
    return ensure_valid_auth(config)


# ═══════════════════════════════════════════════════════════════════════════
# 导出
# ═══════════════════════════════════════════════════════════════════════════

__all__ = [
    # 认证上下文
    "TableauAuthContext",
    "TableauAuthError",
    # 认证获取
    "get_tableau_auth",
    "get_tableau_auth_async",
    # RunnableConfig 集成
    "create_config_with_auth",
    "get_auth_from_config",
    "ensure_valid_auth",
    "ensure_valid_auth_async",
    # 底层函数（供内部使用）
    "_get_tableau_context_from_env",
    "jwt_connected_app",
    "pat_authentication",
]
