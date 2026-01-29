# -*- coding: utf-8 -*-
"""
Tableau 认证模块

支持两种认证方式：
- JWT (Connected App)
- PAT (Personal Access Token)

Token 自动缓存（TTL 从配置读取，默认 10 分钟）

使用方式：
    from analytics_assistant.src.platform.tableau.auth import get_tableau_auth
    
    # 获取认证上下文
    auth = await get_tableau_auth_async()
    
    # 使用 token
    headers = {"X-Tableau-Auth": auth.api_key}
"""
import time
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from threading import Lock

import jwt
import httpx
from pydantic import BaseModel, Field

from analytics_assistant.src.infra.config import get_config
from analytics_assistant.src.core.exceptions import TableauAuthError


logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# 默认配置
# ══════════════════════════════════════════════════════════════════════════════

_DEFAULT_AUTH_TIMEOUT = 30  # 默认认证请求超时（秒）


def _get_auth_timeout() -> int:
    """从配置获取认证请求超时时间"""
    try:
        config = get_config()
        return config.get("tableau", {}).get("auth_timeout", _DEFAULT_AUTH_TIMEOUT)
    except Exception:
        return _DEFAULT_AUTH_TIMEOUT


# ══════════════════════════════════════════════════════════════════════════════
# Token 缓存
# ══════════════════════════════════════════════════════════════════════════════

_cache_lock = Lock()
_token_cache: Dict[str, Dict[str, Any]] = {}  # domain -> cache_data
_token_cached_at: Dict[str, float] = {}  # domain -> cached_at


# ══════════════════════════════════════════════════════════════════════════════
# Tableau 认证上下文
# ══════════════════════════════════════════════════════════════════════════════

class TableauAuthContext(BaseModel):
    """
    Tableau 认证上下文
    
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


# ══════════════════════════════════════════════════════════════════════════════
# SSL 配置辅助函数
# ══════════════════════════════════════════════════════════════════════════════

def _get_ssl_verify() -> Any:
    """
    获取 SSL 验证参数
    
    Returns:
        - ssl.SSLContext（如果配置了 ca_bundle）
        - True（使用系统证书）
        - False（禁用 SSL 验证）
    """
    import ssl
    
    config = get_config()
    
    if not config.get_ssl_verify():
        return False
    
    ca_bundle = config.get_ssl_ca_bundle()
    if ca_bundle:
        # 使用新的 ssl.create_default_context API
        ssl_context = ssl.create_default_context(cafile=ca_bundle)
        return ssl_context
    
    # 尝试使用 certifi
    try:
        import certifi
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        return ssl_context
    except ImportError:
        return True


# ══════════════════════════════════════════════════════════════════════════════
# JWT 认证
# ══════════════════════════════════════════════════════════════════════════════

def _build_jwt_token(
    client_id: str,
    secret_id: str,
    secret: str,
    user: str,
    scopes: List[str],
) -> str:
    """构建 JWT token"""
    return jwt.encode(
        {
            "iss": client_id,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
            "jti": str(uuid4()),
            "aud": "tableau",
            "sub": user,
            "scp": scopes,
        },
        secret,
        algorithm="HS256",
        headers={"kid": secret_id, "iss": client_id},
    )


def _jwt_authenticate(
    domain: str,
    site: str,
    api_version: str,
    user: str,
    client_id: str,
    secret_id: str,
    secret: str,
    scopes: List[str],
) -> Dict[str, Any]:
    """
    使用 JWT Connected App 认证（同步版本）
    
    Args:
        domain: Tableau 域名
        site: Tableau site
        api_version: API 版本
        user: Tableau 用户名
        client_id: JWT Client ID
        secret_id: JWT Secret ID
        secret: JWT Secret
        scopes: 权限范围
    
    Returns:
        认证响应 JSON
    
    Raises:
        TableauAuthError: 认证失败
    """
    token = _build_jwt_token(client_id, secret_id, secret, user, scopes)
    
    endpoint = f"{domain}/api/{api_version}/auth/signin"
    payload = {
        "credentials": {
            "jwt": token,
            "site": {"contentUrl": site},
        }
    }
    
    try:
        response = httpx.post(
            endpoint,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            json=payload,
            verify=_get_ssl_verify(),
            timeout=_get_auth_timeout(),
        )
        
        if response.status_code == 200:
            return response.json()
        
        raise TableauAuthError(
            f"JWT 认证失败: {response.status_code} - {response.text}",
            auth_method="jwt",
        )
    except httpx.RequestError as e:
        raise TableauAuthError(f"JWT 认证请求失败: {e}", auth_method="jwt")


async def _jwt_authenticate_async(
    domain: str,
    site: str,
    api_version: str,
    user: str,
    client_id: str,
    secret_id: str,
    secret: str,
    scopes: List[str],
) -> Dict[str, Any]:
    """
    使用 JWT Connected App 认证（异步版本）
    
    Args:
        domain: Tableau 域名
        site: Tableau site
        api_version: API 版本
        user: Tableau 用户名
        client_id: JWT Client ID
        secret_id: JWT Secret ID
        secret: JWT Secret
        scopes: 权限范围
    
    Returns:
        认证响应 JSON
    
    Raises:
        TableauAuthError: 认证失败
    """
    token = _build_jwt_token(client_id, secret_id, secret, user, scopes)
    
    endpoint = f"{domain}/api/{api_version}/auth/signin"
    payload = {
        "credentials": {
            "jwt": token,
            "site": {"contentUrl": site},
        }
    }
    
    try:
        async with httpx.AsyncClient(verify=_get_ssl_verify(), timeout=_get_auth_timeout()) as client:
            response = await client.post(
                endpoint,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                json=payload,
            )
        
        if response.status_code == 200:
            return response.json()
        
        raise TableauAuthError(
            f"JWT 认证失败: {response.status_code} - {response.text}",
            auth_method="jwt",
        )
    except httpx.RequestError as e:
        raise TableauAuthError(f"JWT 认证请求失败: {e}", auth_method="jwt")


# ══════════════════════════════════════════════════════════════════════════════
# PAT 认证
# ══════════════════════════════════════════════════════════════════════════════

def _pat_authenticate(
    domain: str,
    site: str,
    api_version: str,
    pat_name: str,
    pat_secret: str,
) -> Dict[str, Any]:
    """
    使用 Personal Access Token 认证（同步版本）
    
    Args:
        domain: Tableau 域名
        site: Tableau site
        api_version: API 版本
        pat_name: PAT 名称
        pat_secret: PAT 密钥
    
    Returns:
        认证响应 JSON
    
    Raises:
        TableauAuthError: 认证失败
    """
    endpoint = f"{domain}/api/{api_version}/auth/signin"
    payload = {
        "credentials": {
            "personalAccessTokenName": pat_name,
            "personalAccessTokenSecret": pat_secret,
            "site": {"contentUrl": site},
        }
    }
    
    try:
        response = httpx.post(
            endpoint,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            json=payload,
            verify=_get_ssl_verify(),
            timeout=_get_auth_timeout(),
        )
        
        if response.status_code == 200:
            return response.json()
        
        raise TableauAuthError(
            f"PAT 认证失败: {response.status_code} - {response.text}",
            auth_method="pat",
        )
    except httpx.RequestError as e:
        raise TableauAuthError(f"PAT 认证请求失败: {e}", auth_method="pat")


async def _pat_authenticate_async(
    domain: str,
    site: str,
    api_version: str,
    pat_name: str,
    pat_secret: str,
) -> Dict[str, Any]:
    """
    使用 Personal Access Token 认证（异步版本）
    
    Args:
        domain: Tableau 域名
        site: Tableau site
        api_version: API 版本
        pat_name: PAT 名称
        pat_secret: PAT 密钥
    
    Returns:
        认证响应 JSON
    
    Raises:
        TableauAuthError: 认证失败
    """
    endpoint = f"{domain}/api/{api_version}/auth/signin"
    payload = {
        "credentials": {
            "personalAccessTokenName": pat_name,
            "personalAccessTokenSecret": pat_secret,
            "site": {"contentUrl": site},
        }
    }
    
    try:
        async with httpx.AsyncClient(verify=_get_ssl_verify(), timeout=_get_auth_timeout()) as client:
            response = await client.post(
                endpoint,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                json=payload,
            )
        
        if response.status_code == 200:
            return response.json()
        
        raise TableauAuthError(
            f"PAT 认证失败: {response.status_code} - {response.text}",
            auth_method="pat",
        )
    except httpx.RequestError as e:
        raise TableauAuthError(f"PAT 认证请求失败: {e}", auth_method="pat")


# ══════════════════════════════════════════════════════════════════════════════
# 认证获取函数
# ══════════════════════════════════════════════════════════════════════════════

def _get_auth_params() -> Dict[str, Any]:
    """
    从配置获取认证参数
    
    Returns:
        包含 domain, site, api_version, jwt_config, pat_config 的字典
    
    Raises:
        TableauAuthError: 域名未配置
    """
    config = get_config()
    
    domain = config.get_tableau_domain().strip().rstrip("/")
    site = config.get_tableau_site().strip()
    api_version = config.get_tableau_api_version().strip()
    
    if not domain:
        raise TableauAuthError("Tableau 域名未配置")
    
    jwt_config = config.get_tableau_jwt_config()
    pat_config = config.get_tableau_pat_config()
    
    return {
        "domain": domain,
        "site": site,
        "api_version": api_version,
        "jwt_config": {
            "client_id": jwt_config.get("client_id", "").strip(),
            "secret_id": jwt_config.get("secret_id", "").strip(),
            "secret": jwt_config.get("secret", "").strip(),
            "user": jwt_config.get("user", "").strip(),
        },
        "pat_config": {
            "name": pat_config.get("name", "").strip(),
            "secret": pat_config.get("secret", "").strip(),
        },
    }


def _authenticate_from_config() -> Dict[str, Any]:
    """
    从配置获取认证信息（同步版本）
    
    优先使用 JWT，如果 JWT 配置不完整则尝试 PAT。
    
    Returns:
        {"domain": str, "site": str, "api_key": str, "auth_method": str}
    
    Raises:
        TableauAuthError: 所有认证方式均失败
    """
    params = _get_auth_params()
    domain = params["domain"]
    site = params["site"]
    api_version = params["api_version"]
    jwt_cfg = params["jwt_config"]
    pat_cfg = params["pat_config"]
    
    jwt_error = None
    pat_error = None
    
    # 尝试 JWT 认证
    if all([jwt_cfg["client_id"], jwt_cfg["secret_id"], jwt_cfg["secret"], jwt_cfg["user"]]):
        try:
            logger.debug(f"尝试 JWT 认证: domain={domain}, user={jwt_cfg['user']}")
            response = _jwt_authenticate(
                domain=domain,
                site=site,
                api_version=api_version,
                user=jwt_cfg["user"],
                client_id=jwt_cfg["client_id"],
                secret_id=jwt_cfg["secret_id"],
                secret=jwt_cfg["secret"],
                scopes=["tableau:content:read"],
            )
            api_key = (response.get("credentials") or {}).get("token")
            if api_key:
                logger.info(f"JWT 认证成功: {domain}")
                return {
                    "domain": domain,
                    "site": site,
                    "api_key": api_key,
                    "auth_method": "jwt",
                }
        except TableauAuthError as e:
            jwt_error = str(e)
            logger.warning(f"JWT 认证失败: {e}")
    else:
        logger.debug("JWT 配置不完整，跳过")
    
    # 尝试 PAT 认证
    if all([pat_cfg["name"], pat_cfg["secret"]]):
        try:
            logger.debug(f"尝试 PAT 认证: domain={domain}, pat_name={pat_cfg['name']}")
            response = _pat_authenticate(
                domain=domain,
                site=site,
                api_version=api_version,
                pat_name=pat_cfg["name"],
                pat_secret=pat_cfg["secret"],
            )
            api_key = (response.get("credentials") or {}).get("token")
            if api_key:
                logger.info(f"PAT 认证成功: {domain}")
                return {
                    "domain": domain,
                    "site": site,
                    "api_key": api_key,
                    "auth_method": "pat",
                }
        except TableauAuthError as e:
            pat_error = str(e)
            logger.warning(f"PAT 认证失败: {e}")
    else:
        logger.debug("PAT 配置不完整，跳过")
    
    # 所有认证方式均失败
    error_msg = f"所有认证方式均失败。JWT: {jwt_error or '未配置'}, PAT: {pat_error or '未配置'}"
    raise TableauAuthError(error_msg)


async def _authenticate_from_config_async() -> Dict[str, Any]:
    """
    从配置获取认证信息（异步版本）
    
    优先使用 JWT，如果 JWT 配置不完整则尝试 PAT。
    
    Returns:
        {"domain": str, "site": str, "api_key": str, "auth_method": str}
    
    Raises:
        TableauAuthError: 所有认证方式均失败
    """
    params = _get_auth_params()
    domain = params["domain"]
    site = params["site"]
    api_version = params["api_version"]
    jwt_cfg = params["jwt_config"]
    pat_cfg = params["pat_config"]
    
    jwt_error = None
    pat_error = None
    
    # 尝试 JWT 认证
    if all([jwt_cfg["client_id"], jwt_cfg["secret_id"], jwt_cfg["secret"], jwt_cfg["user"]]):
        try:
            logger.debug(f"尝试 JWT 认证: domain={domain}, user={jwt_cfg['user']}")
            response = await _jwt_authenticate_async(
                domain=domain,
                site=site,
                api_version=api_version,
                user=jwt_cfg["user"],
                client_id=jwt_cfg["client_id"],
                secret_id=jwt_cfg["secret_id"],
                secret=jwt_cfg["secret"],
                scopes=["tableau:content:read"],
            )
            api_key = (response.get("credentials") or {}).get("token")
            if api_key:
                logger.info(f"JWT 认证成功: {domain}")
                return {
                    "domain": domain,
                    "site": site,
                    "api_key": api_key,
                    "auth_method": "jwt",
                }
        except TableauAuthError as e:
            jwt_error = str(e)
            logger.warning(f"JWT 认证失败: {e}")
    else:
        logger.debug("JWT 配置不完整，跳过")
    
    # 尝试 PAT 认证
    if all([pat_cfg["name"], pat_cfg["secret"]]):
        try:
            logger.debug(f"尝试 PAT 认证: domain={domain}, pat_name={pat_cfg['name']}")
            response = await _pat_authenticate_async(
                domain=domain,
                site=site,
                api_version=api_version,
                pat_name=pat_cfg["name"],
                pat_secret=pat_cfg["secret"],
            )
            api_key = (response.get("credentials") or {}).get("token")
            if api_key:
                logger.info(f"PAT 认证成功: {domain}")
                return {
                    "domain": domain,
                    "site": site,
                    "api_key": api_key,
                    "auth_method": "pat",
                }
        except TableauAuthError as e:
            pat_error = str(e)
            logger.warning(f"PAT 认证失败: {e}")
    else:
        logger.debug("PAT 配置不完整，跳过")
    
    # 所有认证方式均失败
    error_msg = f"所有认证方式均失败。JWT: {jwt_error or '未配置'}, PAT: {pat_error or '未配置'}"
    raise TableauAuthError(error_msg)


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
    global _token_cache, _token_cached_at
    
    config = get_config()
    cache_ttl = config.get_tableau_token_cache_ttl()
    cache_key = config.get_tableau_domain().lower().rstrip("/")
    
    now = time.time()
    
    # 检查缓存
    if not force_refresh:
        with _cache_lock:
            if cache_key in _token_cache:
                cached = _token_cache[cache_key]
                cached_at = _token_cached_at.get(cache_key, 0)
                if cached.get("api_key") and (now - cached_at) < cache_ttl:
                    logger.debug(f"使用缓存的认证: {cache_key}")
                    return TableauAuthContext(
                        api_key=cached["api_key"],
                        site=cached.get("site", ""),
                        domain=cached.get("domain", ""),
                        expires_at=cached_at + cache_ttl,
                        auth_method=cached.get("auth_method", "unknown"),
                    )
    
    # 获取新 token
    auth_data = _authenticate_from_config()
    
    # 更新缓存
    with _cache_lock:
        _token_cache[cache_key] = auth_data
        _token_cached_at[cache_key] = now
    
    return TableauAuthContext(
        api_key=auth_data["api_key"],
        site=auth_data.get("site", ""),
        domain=auth_data.get("domain", ""),
        expires_at=now + cache_ttl,
        auth_method=auth_data.get("auth_method", "unknown"),
    )


async def get_tableau_auth_async(force_refresh: bool = False) -> TableauAuthContext:
    """
    获取 Tableau 认证上下文（异步版本）
    
    使用 httpx.AsyncClient 进行真正的异步 HTTP 请求。
    
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
    global _token_cache, _token_cached_at
    
    config = get_config()
    cache_ttl = config.get_tableau_token_cache_ttl()
    cache_key = config.get_tableau_domain().lower().rstrip("/")
    
    now = time.time()
    
    # 检查缓存
    if not force_refresh:
        with _cache_lock:
            if cache_key in _token_cache:
                cached = _token_cache[cache_key]
                cached_at = _token_cached_at.get(cache_key, 0)
                if cached.get("api_key") and (now - cached_at) < cache_ttl:
                    logger.debug(f"使用缓存的认证: {cache_key}")
                    return TableauAuthContext(
                        api_key=cached["api_key"],
                        site=cached.get("site", ""),
                        domain=cached.get("domain", ""),
                        expires_at=cached_at + cache_ttl,
                        auth_method=cached.get("auth_method", "unknown"),
                    )
    
    # 获取新 token（异步）
    auth_data = await _authenticate_from_config_async()
    
    # 更新缓存
    with _cache_lock:
        _token_cache[cache_key] = auth_data
        _token_cached_at[cache_key] = now
    
    return TableauAuthContext(
        api_key=auth_data["api_key"],
        site=auth_data.get("site", ""),
        domain=auth_data.get("domain", ""),
        expires_at=now + cache_ttl,
        auth_method=auth_data.get("auth_method", "unknown"),
    )


def clear_auth_cache() -> None:
    """清除认证缓存"""
    global _token_cache, _token_cached_at
    with _cache_lock:
        _token_cache.clear()
        _token_cached_at.clear()
    logger.info("认证缓存已清除")


# ══════════════════════════════════════════════════════════════════════════════
# 导出
# ══════════════════════════════════════════════════════════════════════════════

__all__ = [
    # 认证上下文
    "TableauAuthContext",
    # 认证获取
    "get_tableau_auth",
    "get_tableau_auth_async",
    # 缓存管理
    "clear_auth_cache",
]
