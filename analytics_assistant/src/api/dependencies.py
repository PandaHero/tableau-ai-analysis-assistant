# -*- coding: utf-8 -*-
"""
FastAPI 依赖注入

提供 BaseRepository 工厂和用户认证依赖。
支持 JWT token 验证（可通过 app.yaml 配置启用/禁用）。
"""

import logging
from typing import Optional

import jwt
from fastapi import Header, HTTPException

from analytics_assistant.src.infra.config import get_config
from analytics_assistant.src.infra.storage import BaseRepository

logger = logging.getLogger(__name__)

# Repository 单例缓存（按 namespace 缓存，避免重复创建）
_repositories: dict = {}

def get_repository(namespace: str) -> BaseRepository:
    """获取指定命名空间的 Repository 实例（单例）。

    Args:
        namespace: 命名空间（如 "sessions"、"user_settings"、"user_feedback"）

    Returns:
        BaseRepository 实例
    """
    if namespace not in _repositories:
        _repositories[namespace] = BaseRepository(namespace)
    return _repositories[namespace]

def get_session_repository() -> BaseRepository:
    """获取会话 Repository（FastAPI 依赖注入用）。"""
    return get_repository("sessions")

def get_settings_repository() -> BaseRepository:
    """获取用户设置 Repository（FastAPI 依赖注入用）。"""
    return get_repository("user_settings")

def get_feedback_repository() -> BaseRepository:
    """获取用户反馈 Repository（FastAPI 依赖注入用）。"""
    return get_repository("user_feedback")

def _get_auth_config() -> dict:
    """从 app.yaml 读取认证配置。

    Returns:
        认证配置字典，包含 enabled、secret_key、algorithm 等字段
    """
    try:
        config = get_config()
        return config.get("api", {}).get("auth", {})
    except Exception as e:
        logger.warning(f"加载认证配置失败，使用默认值: {e}")
        return {}

def _verify_jwt_token(token: str, auth_config: dict) -> dict:
    """验证 JWT token 并返回 payload。

    Args:
        token: JWT token 字符串
        auth_config: 认证配置字典

    Returns:
        JWT payload 字典

    Raises:
        HTTPException: token 无效或过期时返回 401
    """
    secret_key = auth_config.get("secret_key", "")
    algorithm = auth_config.get("algorithm", "HS256")

    if not secret_key:
        logger.error("JWT secret_key 未配置，无法验证 token")
        raise HTTPException(
            status_code=401,
            detail="服务端认证配置错误",
        )

    try:
        payload = jwt.decode(token, secret_key, algorithms=[algorithm])
        return payload
    except jwt.ExpiredSignatureError as e:
        logger.warning("JWT token 已过期")
        raise HTTPException(
            status_code=401,
            detail="认证凭证已过期，请刷新 token",
        ) from e
    except jwt.InvalidTokenError as e:
        logger.warning(f"JWT token 验证失败: {e}")
        raise HTTPException(
            status_code=401,
            detail="无效的认证凭证",
        ) from e

async def get_tableau_username(
    x_tableau_username: Optional[str] = Header(None, alias="X-Tableau-Username"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> str:
    """验证用户身份，支持 JWT token 验证和请求头认证。

    认证模式由 app.yaml 的 api.auth.enabled 控制：
    - enabled=True: 验证 Authorization: Bearer <token> 请求头中的 JWT token
    - enabled=False（开发模式）: 仅依赖 X-Tableau-Username 请求头

    Args:
        x_tableau_username: X-Tableau-Username 请求头值
        authorization: Authorization 请求头值

    Returns:
        经过验证的用户名

    Raises:
        HTTPException: 认证失败时返回 401
    """
    auth_config = _get_auth_config()

    if auth_config.get("enabled", False):
        # 认证模式：验证 JWT token
        if not authorization:
            raise HTTPException(
                status_code=401,
                detail="缺少 Authorization 请求头",
            )

        # 提取 Bearer token
        if not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=401,
                detail="Authorization 请求头格式错误，应为 'Bearer <token>'",
            )

        token = authorization[len("Bearer "):]
        payload = _verify_jwt_token(token, auth_config)

        # 从 token payload 中获取用户名，回退到请求头
        username = payload.get("sub") or x_tableau_username
        if not username:
            raise HTTPException(
                status_code=401,
                detail="JWT token 中缺少 sub 字段且未提供 X-Tableau-Username",
            )
        return username
    else:
        # 开发模式：仅依赖 X-Tableau-Username 请求头
        if not x_tableau_username:
            raise HTTPException(
                status_code=401,
                detail="缺少 X-Tableau-Username 请求头",
            )
        return x_tableau_username
