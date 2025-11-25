
from typing import Dict, Any, List
import os
import time
import requests
import jwt
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from tableau_assistant.src.utils.tableau.utils import http_post
from dotenv import load_dotenv

# Simple in-module cache for Tableau API token context
_CTX_TTL_SEC: int = 600  # 10 minutes
_ctx_cache: Dict[str, Any] = {}
_ctx_cached_at: float = 0.0


def _get_tableau_context_from_env() -> Dict[str, Any]:
    """
    仅使用 JWT Connected App 从环境变量获取 Tableau token（无 PAT、无预置 API_KEY 分支）。
    - 必需：TABLEAU_DOMAIN, TABLEAU_JWT_CLIENT_ID, TABLEAU_JWT_SECRET_ID, TABLEAU_JWT_SECRET, TABLEAU_USER
    - 可选：TABLEAU_SITE, TABLEAU_API_VERSION(默认 3.18)
    - Token 10 分钟缓存
    返回: {"domain": str, "site": str, "api_key": Optional[str]}
    """
    # 读取并规范化环境变量
    try:
        load_dotenv()
    except Exception:
        pass
    domain = (os.environ.get("TABLEAU_DOMAIN") or "").strip()
    if domain.endswith("/"):
        domain = domain.rstrip("/")
    site = (os.environ.get("TABLEAU_SITE") or "").strip()
    jwt_client_id = (os.environ.get("TABLEAU_JWT_CLIENT_ID") or "").strip()
    jwt_secret_id = (os.environ.get("TABLEAU_JWT_SECRET_ID") or "").strip()
    jwt_secret = (os.environ.get("TABLEAU_JWT_SECRET") or "").strip()
    tableau_api_version = (os.environ.get("TABLEAU_API_VERSION") or "3.18").strip()
    tableau_user = (os.environ.get("TABLEAU_USER") or "").strip()

    # 校验 JWT 所需变量齐全，否则不返回 token（交由上层提示）
    required = [domain, jwt_client_id, jwt_secret_id, jwt_secret, tableau_user]
    if not all(required):
        return {"domain": domain, "site": site, "api_key": None}

    # JWT 模式缓存
    global _ctx_cache, _ctx_cached_at
    now = time.time()
    if (
        _ctx_cache.get("api_key")
        and _ctx_cache.get("domain") == domain
        and _ctx_cache.get("site") == site
        and (now - _ctx_cached_at) < _CTX_TTL_SEC
    ):
        return {"domain": _ctx_cache["domain"], "site": _ctx_cache["site"], "api_key": _ctx_cache["api_key"]}

    # 获取 JWT token
    try:
        access_scopes = ["tableau:content:read"]
        session = jwt_connected_app(
            tableau_domain=domain,
            tableau_site=site,
            tableau_api=tableau_api_version or "3.18",
            tableau_user=tableau_user,
            jwt_client_id=jwt_client_id,
            jwt_secret_id=jwt_secret_id,
            jwt_secret=jwt_secret,
            scopes=access_scopes,
        )
        api_key = (session.get("credentials") or {}).get("token")
        _ctx_cache = {"domain": domain, "site": site, "api_key": api_key or None}
        _ctx_cached_at = now
    except Exception:
        _ctx_cache = {"domain": domain, "site": site, "api_key": None}
        _ctx_cached_at = now

    return {"domain": _ctx_cache["domain"], "site": _ctx_cache["site"], "api_key": _ctx_cache["api_key"]}


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
    """
    Authenticates a user to Tableau using JSON Web Token (JWT) authentication.

    This function generates a JWT based on the provided credentials and uses it to authenticate
    a user with the Tableau Server or Tableau Online. The JWT is created with a specified expiration
    time and scopes, allowing for secure access to Tableau resources.

    Args:
        tableau_domain (str): The domain of the Tableau Server or Tableau Online instance.
        tableau_site (str): The content URL of the specific Tableau site to authenticate against.
        tableau_api (str): The version of the Tableau API to use for authentication.
        tableau_user (str): The username of the Tableau user to authenticate.
        jwt_client_id (str): The client ID used for generating the JWT.
        jwt_secret_id (str): The key ID associated with the JWT secret.
        jwt_secret (str): The secret key used to sign the JWT.
        scopes (List[str]): A list of scopes that define the permissions granted by the JWT.

    Returns:
        Dict[str, Any]: A dictionary containing the response from the Tableau authentication endpoint,
        typically including an API key or session that is valid for 2 hours and user information.
    """
    # Encode the payload and secret key to generate the JWT
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
        algorithm = "HS256",
        headers = {
        'kid': jwt_secret_id,
        'iss': jwt_client_id
        }
    )

    # authentication endpoint + request headers & payload
    endpoint = f"{tableau_domain}/api/{tableau_api}/auth/signin"

    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }

    payload = {
        "credentials": {
        "jwt": token,
        "site": {
            "contentUrl": tableau_site,
        }
        }
    }

    response = requests.post(endpoint, headers=headers, json=payload)

    # Check if the request was successful (status code 200)
    if response.status_code == 200:
        return response.json()
    else:
        error_message = (
            f"Failed to authenticate to the Tableau site. "
            f"Status code: {response.status_code}. Response: {response.text}"
        )
        raise RuntimeError(error_message)


async def jwt_connected_app_async(
        tableau_domain: str,
        tableau_site: str,
        tableau_api: str,
        tableau_user: str,
        jwt_client_id: str,
        jwt_secret_id: str,
        jwt_secret: str,
        scopes: List[str],
) -> Dict[str, Any]:
    """
    Authenticates a user to Tableau using JSON Web Token (JWT) authentication.

    This function generates a JWT based on the provided credentials and uses it to authenticate
    a user with the Tableau Server or Tableau Online. The JWT is created with a specified expiration
    time and scopes, allowing for secure access to Tableau resources.

    Args:
        tableau_domain (str): The domain of the Tableau Server or Tableau Online instance.
        tableau_site (str): The content URL of the specific Tableau site to authenticate against.
        tableau_api (str): The version of the Tableau API to use for authentication.
        tableau_user (str): The username of the Tableau user to authenticate.
        jwt_client_id (str): The client ID used for generating the JWT.
        jwt_secret_id (str): The key ID associated with the JWT secret.
        jwt_secret (str): The secret key used to sign the JWT.
        scopes (List[str]): A list of scopes that define the permissions granted by the JWT.

    Returns:
        Dict[str, Any]: A dictionary containing the response from the Tableau authentication endpoint,
        typically including an API key or session that is valid for 2 hours and user information.
    """
    # Encode the payload and secret key to generate the JWT
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
        algorithm = "HS256",
        headers = {
        'kid': jwt_secret_id,
        'iss': jwt_client_id
        }
    )

    # authentication endpoint + request headers & payload
    endpoint = f"{tableau_domain}/api/{tableau_api}/auth/signin"

    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }

    payload = {
        "credentials": {
        "jwt": token,
        "site": {
            "contentUrl": tableau_site,
        }
        }
    }

    response = await http_post(endpoint=endpoint, headers=headers, payload=payload)
     # Check if the request was successful (status code 200)
    if response['status'] == 200:
        return response['data']
    else:
        error_message = (
            f"Failed to authenticate to the Tableau site. "
            f"Status code: {response['status']}. Response: {response['data']}"
        )
        raise RuntimeError(error_message)
