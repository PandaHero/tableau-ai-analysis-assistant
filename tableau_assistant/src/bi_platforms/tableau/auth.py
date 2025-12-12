"""
Tableau 认证模块

支持两种认证方式：
- JWT (Connected App)
- PAT (Personal Access Token)

Token 自动缓存 10 分钟（仅缓存成功的认证）

认证上下文通过 RunnableConfig 传递给工作流节点：
- 工作流启动时获取一次 token
- 通过 RunnableConfig["configurable"]["tableau_auth"] 传递
- Token 过期时自动刷新
"""
import os
import time
import logging
import requests
import jwt
from typing import Dict, Any, List, Optional, TYPE_CHECKING
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from dotenv import load_dotenv
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from langgraph.types import RunnableConfig

logger = logging.getLogger(__name__)

# Token 缓存（仅缓存成功的认证）
_CTX_TTL_SEC: int = 600  # 10 分钟
_ctx_cache: Dict[str, Any] = {}
_ctx_cached_at: float = 0.0


# ═══════════════════════════════════════════════════════════════════════════
# Tableau 认证上下文（Pydantic 模型）
# ═══════════════════════════════════════════════════════════════════════════

class TableauAuthContext(BaseModel):
    """
    Tableau 认证上下文
    
    通过 RunnableConfig["configurable"]["tableau_auth"] 传递给所有节点。
    
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


def _get_tableau_context_from_env() -> Dict[str, Any]:
    """
    从 settings 获取 Tableau token，支持 JWT 和 PAT 两种认证方式。
    优先使用 JWT，如果 JWT 配置不完整则尝试 PAT。
    
    JWT 必需：TABLEAU_DOMAIN, TABLEAU_JWT_CLIENT_ID, TABLEAU_JWT_SECRET_ID, TABLEAU_JWT_SECRET, TABLEAU_USER
    PAT 必需：TABLEAU_DOMAIN, TABLEAU_PAT_NAME, TABLEAU_PAT_SECRET
    可选：TABLEAU_SITE, TABLEAU_API_VERSION(默认 3.18)
    
    Token 10 分钟缓存
    返回: {"domain": str, "site": str, "api_key": Optional[str]}
    """
    from tableau_assistant.src.config.settings import settings
    
    domain = settings.tableau_domain.strip().rstrip("/")
    site = settings.tableau_site.strip()
    tableau_api_version = settings.tableau_api_version.strip()
    
    # JWT 配置
    jwt_client_id = settings.tableau_jwt_client_id.strip()
    jwt_secret_id = settings.tableau_jwt_secret_id.strip()
    jwt_secret = settings.tableau_jwt_secret.strip()
    tableau_user = settings.tableau_user.strip()
    
    # PAT 配置
    pat_name = settings.tableau_pat_name.strip()
    pat_secret = settings.tableau_pat_secret.strip()

    # 检查缓存
    global _ctx_cache, _ctx_cached_at
    now = time.time()
    if (
        _ctx_cache.get("api_key")
        and _ctx_cache.get("domain") == domain
        and _ctx_cache.get("site") == site
        and (now - _ctx_cached_at) < _CTX_TTL_SEC
    ):
        return {"domain": _ctx_cache["domain"], "site": _ctx_cache["site"], "api_key": _ctx_cache["api_key"]}

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
                logger.info("JWT 认证成功")
                _ctx_cache = {"domain": domain, "site": site, "api_key": api_key}
                _ctx_cached_at = now
                return {"domain": domain, "site": site, "api_key": api_key}
        except Exception as e:
            jwt_error = str(e)
            logger.warning(f"JWT 认证失败: {e}")
    else:
        logger.debug("JWT 配置不完整，跳过 JWT 认证")

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
                logger.info("PAT 认证成功")
                _ctx_cache = {"domain": domain, "site": site, "api_key": api_key}
                _ctx_cached_at = now
                return {"domain": domain, "site": site, "api_key": api_key}
        except Exception as e:
            pat_error = str(e)
            logger.warning(f"PAT 认证失败: {e}")
    else:
        logger.debug("PAT 配置不完整，跳过 PAT 认证")

    # 认证失败 - 不缓存失败结果，下次请求会重试
    error_msg = f"所有认证方式均失败。JWT: {jwt_error or '未配置'}, PAT: {pat_error or '未配置'}"
    logger.error(error_msg)
    # 注意：不缓存失败结果，这样下次请求会重新尝试认证
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
        json=payload
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
        json=payload
    )

    if response.status_code == 200:
        return response.json()
    raise RuntimeError(f"PAT auth failed: {response.status_code} - {response.text}")


# ═══════════════════════════════════════════════════════════════════════════
# 认证获取函数（统一入口）
# ═══════════════════════════════════════════════════════════════════════════

def get_tableau_auth(force_refresh: bool = False) -> TableauAuthContext:
    """
    获取 Tableau 认证上下文（同步版本）
    
    优先级：
    1. 内存缓存（如果未过期）
    2. 调用认证 API 获取新 token
    
    Args:
        force_refresh: 是否强制刷新 token
    
    Returns:
        TableauAuthContext 认证上下文
    
    Raises:
        TableauAuthError: 认证失败
    """
    global _ctx_cache, _ctx_cached_at
    
    # 1. 检查内存缓存
    if not force_refresh and _ctx_cache.get("api_key"):
        now = time.time()
        if (now - _ctx_cached_at) < _CTX_TTL_SEC:
            return TableauAuthContext(
                api_key=_ctx_cache["api_key"],
                site=_ctx_cache.get("site", ""),
                domain=_ctx_cache.get("domain", ""),
                expires_at=_ctx_cached_at + _CTX_TTL_SEC,
                auth_method=_ctx_cache.get("auth_method", "unknown"),
            )
    
    # 2. 获取新 token
    ctx = _get_tableau_context_from_env()
    
    api_key = ctx.get("api_key")
    if not api_key:
        error_msg = ctx.get("error", "认证失败，请检查 .env 中的 Tableau 配置")
        raise TableauAuthError(error_msg)
    
    return TableauAuthContext(
        api_key=api_key,
        site=ctx.get("site", ""),
        domain=ctx.get("domain", ""),
        expires_at=time.time() + _CTX_TTL_SEC,
        auth_method=_ctx_cache.get("auth_method", "unknown"),
    )


async def get_tableau_auth_async(force_refresh: bool = False) -> TableauAuthContext:
    """
    获取 Tableau 认证上下文（异步版本）
    
    注意：当前实现是同步的，因为 Tableau API 调用是同步的。
    提供异步接口是为了与异步工作流兼容。
    """
    return get_tableau_auth(force_refresh=force_refresh)


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


def get_auth_from_config(config: Optional["RunnableConfig"]) -> Optional[TableauAuthContext]:
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
    auth_data = configurable.get("tableau_auth")
    
    if auth_data is None:
        return None
    
    try:
        return TableauAuthContext(**auth_data)
    except Exception as e:
        logger.warning(f"解析认证上下文失败: {e}")
        return None


def ensure_valid_auth(config: Optional["RunnableConfig"] = None) -> TableauAuthContext:
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


async def ensure_valid_auth_async(config: Optional["RunnableConfig"] = None) -> TableauAuthContext:
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
