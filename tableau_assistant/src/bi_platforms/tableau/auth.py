"""
Tableau 认证模块

支持两种认证方式：
- JWT (Connected App)
- PAT (Personal Access Token)

Token 自动缓存 10 分钟
"""
import os
import time
import requests
import jwt
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from dotenv import load_dotenv

# Token 缓存
_CTX_TTL_SEC: int = 600  # 10 分钟
_ctx_cache: Dict[str, Any] = {}
_ctx_cached_at: float = 0.0


def _get_tableau_context_from_env() -> Dict[str, Any]:
    """
    从环境变量获取 Tableau token，支持 JWT 和 PAT 两种认证方式。
    优先使用 JWT，如果 JWT 配置不完整则尝试 PAT。
    
    JWT 必需：TABLEAU_DOMAIN, TABLEAU_JWT_CLIENT_ID, TABLEAU_JWT_SECRET_ID, TABLEAU_JWT_SECRET, TABLEAU_USER
    PAT 必需：TABLEAU_DOMAIN, TABLEAU_PAT_NAME, TABLEAU_PAT_SECRET
    可选：TABLEAU_SITE, TABLEAU_API_VERSION(默认 3.18)
    
    Token 10 分钟缓存
    返回: {"domain": str, "site": str, "api_key": Optional[str]}
    """
    try:
        load_dotenv()
    except Exception:
        pass
    
    domain = (os.environ.get("TABLEAU_DOMAIN") or "").strip().rstrip("/")
    site = (os.environ.get("TABLEAU_SITE") or "").strip()
    tableau_api_version = (os.environ.get("TABLEAU_API_VERSION") or "3.18").strip()
    
    # JWT 配置
    jwt_client_id = (os.environ.get("TABLEAU_JWT_CLIENT_ID") or "").strip()
    jwt_secret_id = (os.environ.get("TABLEAU_JWT_SECRET_ID") or "").strip()
    jwt_secret = (os.environ.get("TABLEAU_JWT_SECRET") or "").strip()
    tableau_user = (os.environ.get("TABLEAU_USER") or "").strip()
    
    # PAT 配置
    pat_name = (os.environ.get("TABLEAU_PAT_NAME") or "").strip()
    pat_secret = (os.environ.get("TABLEAU_PAT_SECRET") or "").strip()

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
    if all([domain, jwt_client_id, jwt_secret_id, jwt_secret, tableau_user]):
        try:
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
                _ctx_cache = {"domain": domain, "site": site, "api_key": api_key}
                _ctx_cached_at = now
                return {"domain": domain, "site": site, "api_key": api_key}
        except Exception:
            pass

    # 尝试 PAT 认证
    if all([domain, pat_name, pat_secret]):
        try:
            session = pat_authentication(
                tableau_domain=domain,
                tableau_site=site,
                tableau_api=tableau_api_version,
                pat_name=pat_name,
                pat_secret=pat_secret,
            )
            api_key = (session.get("credentials") or {}).get("token")
            if api_key:
                _ctx_cache = {"domain": domain, "site": site, "api_key": api_key}
                _ctx_cached_at = now
                return {"domain": domain, "site": site, "api_key": api_key}
        except Exception:
            pass

    # 认证失败
    _ctx_cache = {"domain": domain, "site": site, "api_key": None}
    _ctx_cached_at = now
    return {"domain": domain, "site": site, "api_key": None}


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
