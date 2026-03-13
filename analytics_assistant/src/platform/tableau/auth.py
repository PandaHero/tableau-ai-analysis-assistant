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
import hashlib
import time
import logging
from typing import Any, Optional
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
    except Exception as e:
        logger.warning(f"获取认证超时配置失败，使用默认值: {e}")
        return _DEFAULT_AUTH_TIMEOUT

# ══════════════════════════════════════════════════════════════════════════════
# Token 缓存
# ══════════════════════════════════════════════════════════════════════════════

_cache_lock = Lock()
_token_cache: dict[str, dict[str, Any]] = {}  # domain -> cache_data
_token_cached_at: dict[str, float] = {}  # domain -> cached_at

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

from .ssl_utils import get_ssl_verify as _get_ssl_verify

# ══════════════════════════════════════════════════════════════════════════════
# JWT 认证
# ══════════════════════════════════════════════════════════════════════════════

def _build_jwt_token(
    client_id: str,
    secret_id: str,
    secret: str,
    user: str,
    scopes: list[str],
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

def _build_jwt_auth_request(
    domain: str,
    site: str,
    api_version: str,
    user: str,
    client_id: str,
    secret_id: str,
    secret: str,
    scopes: list[str],
) -> tuple[str, dict[str, Any], dict[str, str]]:
    """构建 JWT 认证请求参数（公共逻辑）。

    将 JWT token 生成、URL 构建、payload 构建等与 HTTP 无关的逻辑
    提取为公共函数，供同步/异步版本共用。

    Returns:
        (endpoint, payload, headers) 三元组。
    """
    token = _build_jwt_token(client_id, secret_id, secret, user, scopes)
    endpoint = f"{domain}/api/{api_version}/auth/signin"
    payload = {
        "credentials": {
            "jwt": token,
            "site": {"contentUrl": site},
        }
    }
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    return endpoint, payload, headers

def _parse_auth_response(
    response: httpx.Response,
    auth_method: str,
) -> dict[str, Any]:
    """解析认证 HTTP 响应（公共逻辑）。

    校验状态码并返回 JSON，失败时抛出 TableauAuthError。

    Args:
        response: httpx 响应对象。
        auth_method: 认证方式标识（"jwt" 或 "pat"），用于错误信息。

    Returns:
        认证响应 JSON 字典。

    Raises:
        TableauAuthError: 状态码非 200 时抛出。
    """
    if response.status_code == 200:
        return response.json()
    raise TableauAuthError(
        f"{auth_method.upper()} 认证失败: {response.status_code} - {response.text}",
        auth_method=auth_method,
    )

def _jwt_authenticate(
    domain: str,
    site: str,
    api_version: str,
    user: str,
    client_id: str,
    secret_id: str,
    secret: str,
    scopes: list[str],
) -> dict[str, Any]:
    """使用 JWT Connected App 认证（同步版本）"""
    endpoint, payload, headers = _build_jwt_auth_request(
        domain, site, api_version, user, client_id, secret_id, secret, scopes,
    )
    try:
        response = httpx.post(
            endpoint, headers=headers, json=payload,
            verify=_get_ssl_verify(), timeout=_get_auth_timeout(),
        )
        return _parse_auth_response(response, "jwt")
    except httpx.RequestError as e:
        raise TableauAuthError(f"JWT 认证请求失败: {e}", auth_method="jwt") from e

async def _jwt_authenticate_async(
    domain: str,
    site: str,
    api_version: str,
    user: str,
    client_id: str,
    secret_id: str,
    secret: str,
    scopes: list[str],
) -> dict[str, Any]:
    """使用 JWT Connected App 认证（异步版本）"""
    endpoint, payload, headers = _build_jwt_auth_request(
        domain, site, api_version, user, client_id, secret_id, secret, scopes,
    )
    try:
        async with httpx.AsyncClient(verify=_get_ssl_verify(), timeout=_get_auth_timeout()) as client:
            response = await client.post(endpoint, headers=headers, json=payload)
        return _parse_auth_response(response, "jwt")
    except httpx.RequestError as e:
        raise TableauAuthError(f"JWT 认证请求失败: {e}", auth_method="jwt") from e

# ══════════════════════════════════════════════════════════════════════════════
# PAT 认证
# ══════════════════════════════════════════════════════════════════════════════

def _build_pat_auth_request(
    domain: str,
    site: str,
    api_version: str,
    pat_name: str,
    pat_secret: str,
) -> tuple[str, dict[str, Any], dict[str, str]]:
    """构建 PAT 认证请求参数（公共逻辑）。

    Returns:
        (endpoint, payload, headers) 三元组。
    """
    endpoint = f"{domain}/api/{api_version}/auth/signin"
    payload = {
        "credentials": {
            "personalAccessTokenName": pat_name,
            "personalAccessTokenSecret": pat_secret,
            "site": {"contentUrl": site},
        }
    }
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    return endpoint, payload, headers

def _pat_authenticate(
    domain: str,
    site: str,
    api_version: str,
    pat_name: str,
    pat_secret: str,
) -> dict[str, Any]:
    """使用 Personal Access Token 认证（同步版本）"""
    endpoint, payload, headers = _build_pat_auth_request(
        domain, site, api_version, pat_name, pat_secret,
    )
    try:
        response = httpx.post(
            endpoint, headers=headers, json=payload,
            verify=_get_ssl_verify(), timeout=_get_auth_timeout(),
        )
        return _parse_auth_response(response, "pat")
    except httpx.RequestError as e:
        raise TableauAuthError(f"PAT 认证请求失败: {e}", auth_method="pat") from e

async def _pat_authenticate_async(
    domain: str,
    site: str,
    api_version: str,
    pat_name: str,
    pat_secret: str,
) -> dict[str, Any]:
    """使用 Personal Access Token 认证（异步版本）"""
    endpoint, payload, headers = _build_pat_auth_request(
        domain, site, api_version, pat_name, pat_secret,
    )
    try:
        async with httpx.AsyncClient(verify=_get_ssl_verify(), timeout=_get_auth_timeout()) as client:
            response = await client.post(endpoint, headers=headers, json=payload)
        return _parse_auth_response(response, "pat")
    except httpx.RequestError as e:
        raise TableauAuthError(f"PAT 认证请求失败: {e}", auth_method="pat") from e

# ══════════════════════════════════════════════════════════════════════════════
# 认证获取函数
# ══════════════════════════════════════════════════════════════════════════════

def _get_auth_params() -> dict[str, Any]:
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
            "scopes": jwt_config.get("scopes") or ["tableau:content:read"],
        },
        "pat_config": {
            "name": pat_config.get("name", "").strip(),
            "secret": pat_config.get("secret", "").strip(),
        },
    }

def _extract_api_key(response_data: dict[str, Any]) -> Optional[str]:
    """从认证响应中提取 API Key。"""
    return (response_data.get("credentials") or {}).get("token")

def _build_auth_result(
    domain: str,
    site: str,
    api_key: str,
    auth_method: str,
) -> dict[str, Any]:
    """构建认证结果字典（公共逻辑）。"""
    return {
        "domain": domain,
        "site": site,
        "api_key": api_key,
        "auth_method": auth_method,
    }


def _normalize_scopes(scopes: Optional[list[str]]) -> list[str]:
    normalized = sorted({
        str(scope).strip()
        for scope in (scopes or [])
        if str(scope).strip()
    })
    return normalized


def _build_scope_hash(scopes: Optional[list[str]]) -> str:
    normalized = _normalize_scopes(scopes)
    if not normalized:
        return "noscope"
    digest = hashlib.sha1(",".join(normalized).encode("utf-8")).hexdigest()
    return digest[:12]


def _build_auth_cache_key(
    *,
    domain: str,
    site: str,
    principal: str,
    auth_method: str,
    scopes: Optional[list[str]],
) -> str:
    normalized_domain = str(domain or "").strip().lower().rstrip("/")
    normalized_site = str(site or "").strip().lower()
    normalized_principal = str(principal or "").strip().lower()
    scope_hash = _build_scope_hash(scopes)
    return (
        f"tableau:token:{normalized_domain}:{normalized_site}:"
        f"{normalized_principal}:{auth_method}:{scope_hash}"
    )


def _build_cache_candidates(params: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    jwt_cfg = params["jwt_config"]
    pat_cfg = params["pat_config"]

    if all([jwt_cfg["client_id"], jwt_cfg["secret_id"], jwt_cfg["secret"], jwt_cfg["user"]]):
        candidates.append(_build_auth_cache_key(
            domain=params["domain"],
            site=params["site"],
            principal=jwt_cfg["user"],
            auth_method="jwt",
            scopes=jwt_cfg.get("scopes"),
        ))

    if all([pat_cfg["name"], pat_cfg["secret"]]):
        candidates.append(_build_auth_cache_key(
            domain=params["domain"],
            site=params["site"],
            principal=pat_cfg["name"],
            auth_method="pat",
            scopes=[],
        ))

    return candidates


def _resolve_cache_key_for_auth(params: dict[str, Any], auth_method: str) -> str:
    if auth_method == "jwt":
        jwt_cfg = params["jwt_config"]
        return _build_auth_cache_key(
            domain=params["domain"],
            site=params["site"],
            principal=jwt_cfg["user"],
            auth_method="jwt",
            scopes=jwt_cfg.get("scopes"),
        )

    pat_cfg = params["pat_config"]
    return _build_auth_cache_key(
        domain=params["domain"],
        site=params["site"],
        principal=pat_cfg["name"],
        auth_method="pat",
        scopes=[],
    )

def _authenticate_from_config() -> dict[str, Any]:
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
                domain=domain, site=site, api_version=api_version,
                user=jwt_cfg["user"], client_id=jwt_cfg["client_id"],
                secret_id=jwt_cfg["secret_id"], secret=jwt_cfg["secret"],
                scopes=_normalize_scopes(jwt_cfg.get("scopes")),
            )
            api_key = _extract_api_key(response)
            if api_key:
                logger.info(f"JWT 认证成功: {domain}")
                return _build_auth_result(domain, site, api_key, "jwt")
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
                domain=domain, site=site, api_version=api_version,
                pat_name=pat_cfg["name"], pat_secret=pat_cfg["secret"],
            )
            api_key = _extract_api_key(response)
            if api_key:
                logger.info(f"PAT 认证成功: {domain}")
                return _build_auth_result(domain, site, api_key, "pat")
        except TableauAuthError as e:
            pat_error = str(e)
            logger.warning(f"PAT 认证失败: {e}")
    else:
        logger.debug("PAT 配置不完整，跳过")
    
    error_msg = f"所有认证方式均失败。JWT: {jwt_error or '未配置'}, PAT: {pat_error or '未配置'}"
    raise TableauAuthError(error_msg)

async def _authenticate_from_config_async() -> dict[str, Any]:
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
                domain=domain, site=site, api_version=api_version,
                user=jwt_cfg["user"], client_id=jwt_cfg["client_id"],
                secret_id=jwt_cfg["secret_id"], secret=jwt_cfg["secret"],
                scopes=_normalize_scopes(jwt_cfg.get("scopes")),
            )
            api_key = _extract_api_key(response)
            if api_key:
                logger.info(f"JWT 认证成功: {domain}")
                return _build_auth_result(domain, site, api_key, "jwt")
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
                domain=domain, site=site, api_version=api_version,
                pat_name=pat_cfg["name"], pat_secret=pat_cfg["secret"],
            )
            api_key = _extract_api_key(response)
            if api_key:
                logger.info(f"PAT 认证成功: {domain}")
                return _build_auth_result(domain, site, api_key, "pat")
        except TableauAuthError as e:
            pat_error = str(e)
            logger.warning(f"PAT 认证失败: {e}")
    else:
        logger.debug("PAT 配置不完整，跳过")
    
    error_msg = f"所有认证方式均失败。JWT: {jwt_error or '未配置'}, PAT: {pat_error or '未配置'}"
    raise TableauAuthError(error_msg)

def _check_cache(cache_key: str, cache_ttl: float) -> Optional[TableauAuthContext]:
    """检查认证缓存是否有效（公共逻辑）。

    Args:
        cache_key: 缓存键（通常是 domain 小写）。
        cache_ttl: 缓存 TTL（秒）。

    Returns:
        缓存命中时返回 TableauAuthContext，否则返回 None。
    """
    now = time.time()
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
    return None

def _update_cache(cache_key: str, auth_data: dict[str, Any]) -> None:
    """更新认证缓存（公共逻辑）。"""
    with _cache_lock:
        _token_cache[cache_key] = auth_data
        _token_cached_at[cache_key] = time.time()

def _build_auth_context(auth_data: dict[str, Any], cache_ttl: float) -> TableauAuthContext:
    """从认证数据构建 TableauAuthContext（公共逻辑）。"""
    return TableauAuthContext(
        api_key=auth_data["api_key"],
        site=auth_data.get("site", ""),
        domain=auth_data.get("domain", ""),
        expires_at=time.time() + cache_ttl,
        auth_method=auth_data.get("auth_method", "unknown"),
    )

def _get_cache_params() -> tuple[list[str], float, dict[str, Any]]:
    """获取候选缓存键、TTL 和认证参数。"""
    config = get_config()
    cache_ttl = config.get_tableau_token_cache_ttl()
    params = _get_auth_params()
    cache_candidates = _build_cache_candidates(params)
    return cache_candidates, cache_ttl, params

def get_tableau_auth(force_refresh: bool = False) -> TableauAuthContext:
    """
    获取 Tableau 认证上下文（同步版本）
    
    优先级：
    1. 内存缓存（如果未过期）
    2. 调用认证 API 获取新 token
    """
    cache_candidates, cache_ttl, params = _get_cache_params()
    
    if not force_refresh:
        for cache_key in cache_candidates:
            cached = _check_cache(cache_key, cache_ttl)
            if cached:
                return cached
    
    auth_data = _authenticate_from_config()
    cache_key = _resolve_cache_key_for_auth(params, auth_data["auth_method"])
    _update_cache(cache_key, auth_data)
    return _build_auth_context(auth_data, cache_ttl)

async def get_tableau_auth_async(force_refresh: bool = False) -> TableauAuthContext:
    """
    获取 Tableau 认证上下文（异步版本）
    
    优先级：
    1. 内存缓存（如果未过期）
    2. 调用认证 API 获取新 token
    """
    cache_candidates, cache_ttl, params = _get_cache_params()
    
    if not force_refresh:
        for cache_key in cache_candidates:
            cached = _check_cache(cache_key, cache_ttl)
            if cached:
                return cached
    
    auth_data = await _authenticate_from_config_async()
    cache_key = _resolve_cache_key_for_auth(params, auth_data["auth_method"])
    _update_cache(cache_key, auth_data)
    return _build_auth_context(auth_data, cache_ttl)

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
