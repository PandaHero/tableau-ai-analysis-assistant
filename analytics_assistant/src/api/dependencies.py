# -*- coding: utf-8 -*-
"""FastAPI 依赖注入入口。"""

from __future__ import annotations

import logging
from typing import Any, Optional

import jwt
from fastapi import Header, HTTPException

from analytics_assistant.src.infra.business_storage import (
    AnalysisRunRepository,
    FeedbackRepository,
    InterruptRepository,
    SessionRepository,
    SettingsRepository,
)
from analytics_assistant.src.infra.config import get_config

logger = logging.getLogger(__name__)

# 仓库单例缓存，测试可以直接替换其中实例。
_repositories: dict[str, Any] = {}


def _summarize_authorization_header(authorization: Optional[str]) -> str:
    """返回脱敏后的 Authorization 摘要。"""
    if not authorization:
        return "<missing>"
    if authorization.startswith("Bearer "):
        token = authorization[len("Bearer "):]
        return f"Bearer ***{token[-4:]}" if token else "Bearer <empty>"
    return "<non-bearer>"


def get_repository(namespace: str) -> Any:
    """按命名空间返回结构化业务仓储。"""
    if namespace not in _repositories:
        if namespace == "sessions":
            _repositories[namespace] = SessionRepository()
        elif namespace == "user_settings":
            _repositories[namespace] = SettingsRepository()
        elif namespace == "user_feedback":
            _repositories[namespace] = FeedbackRepository()
        elif namespace == "analysis_runs":
            _repositories[namespace] = AnalysisRunRepository()
        elif namespace == "analysis_interrupts":
            _repositories[namespace] = InterruptRepository()
        else:
            raise KeyError(f"unsupported repository namespace: {namespace}")
    return _repositories[namespace]


def get_session_repository() -> SessionRepository:
    """获取会话仓储。"""
    return get_repository("sessions")


def get_settings_repository() -> SettingsRepository:
    """获取用户设置仓储。"""
    return get_repository("user_settings")


def get_feedback_repository() -> FeedbackRepository:
    """获取用户反馈仓储。"""
    return get_repository("user_feedback")


def get_analysis_run_repository() -> AnalysisRunRepository:
    """获取分析运行仓储。"""
    return get_repository("analysis_runs")


def get_interrupt_repository() -> InterruptRepository:
    """获取中断仓储。"""
    return get_repository("analysis_interrupts")


def _get_auth_config() -> dict[str, Any]:
    """从配置读取 API 认证参数。"""
    try:
        config = get_config()
        return config.get("api", {}).get("auth", {})
    except Exception as exc:
        logger.warning("加载认证配置失败，使用默认配置: %s", exc)
        return {}


def _verify_jwt_token(token: str, auth_config: dict[str, Any]) -> dict[str, Any]:
    """校验 JWT 并返回 payload。"""
    secret_key = str(auth_config.get("secret_key") or "").strip()
    algorithm = str(auth_config.get("algorithm") or "HS256").strip() or "HS256"

    if not secret_key:
        logger.error("JWT secret_key 未配置，无法校验 token")
        raise HTTPException(status_code=401, detail="服务端认证配置错误")

    try:
        return jwt.decode(token, secret_key, algorithms=[algorithm])
    except jwt.ExpiredSignatureError as exc:
        logger.warning("JWT token 已过期")
        raise HTTPException(status_code=401, detail="认证凭证已过期，请刷新 token") from exc
    except jwt.InvalidTokenError as exc:
        logger.warning("JWT token 校验失败: %s", exc)
        raise HTTPException(status_code=401, detail="无效的认证凭证") from exc


async def get_tableau_username(
    x_tableau_username: Optional[str] = Header(None, alias="X-Tableau-Username"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> str:
    """获取并校验当前请求的 Tableau 用户名。"""
    logger.info("=" * 60)
    logger.info("[认证] 收到请求")
    logger.info("[认证] X-Tableau-Username: %s", x_tableau_username or "<missing>")
    logger.info(
        "[认证] Authorization 摘要: %s",
        _summarize_authorization_header(authorization),
    )
    logger.info("=" * 60)

    auth_config = _get_auth_config()
    enabled = bool(auth_config.get("enabled", False))
    logger.info("[认证] 配置 enabled=%s", enabled)

    if enabled:
        if not authorization:
            logger.warning("[认证] 缺少 Authorization 请求头")
            raise HTTPException(status_code=401, detail="缺少 Authorization 请求头")
        if not authorization.startswith("Bearer "):
            logger.warning("[认证] Authorization 请求头格式错误")
            raise HTTPException(
                status_code=401,
                detail="Authorization 请求头格式错误，应为 'Bearer <token>'",
            )

        token = authorization[len("Bearer "):]
        payload = _verify_jwt_token(token, auth_config)
        if "sub" not in payload or payload.get("sub") is None:
            logger.warning("[认证] JWT token 缺少 sub 字段")
            raise HTTPException(status_code=401, detail="JWT token 缺少 sub 字段")

        # 不主动 strip `sub`，避免篡改 JWT 中的真实身份值。
        username = str(payload["sub"])
        if username == "":
            logger.warning("[认证] JWT token sub 字段为空字符串")
            raise HTTPException(status_code=401, detail="JWT token sub 字段不能为空")

        if x_tableau_username is not None and x_tableau_username != username:
            logger.warning(
                "[认证] Header 用户名与 JWT 不匹配: header=%s, sub=%s",
                x_tableau_username,
                username,
            )
            raise HTTPException(status_code=401, detail="请求头用户身份与 JWT 不匹配")

        logger.info("[认证] JWT 认证成功，用户=%s", username)
        return username

    if not x_tableau_username:
        logger.error("[认证] X-Tableau-Username 请求头缺失")
        raise HTTPException(status_code=401, detail="缺少 X-Tableau-Username 请求头")

    logger.info("[认证] 开发模式认证成功，用户=%s", x_tableau_username)
    return x_tableau_username


__all__ = [
    "get_analysis_run_repository",
    "get_feedback_repository",
    "get_interrupt_repository",
    "get_repository",
    "get_session_repository",
    "get_settings_repository",
    "get_tableau_username",
]
