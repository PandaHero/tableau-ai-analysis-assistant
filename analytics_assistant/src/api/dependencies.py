# -*- coding: utf-8 -*-
"""
FastAPI 依赖注入

提供 BaseRepository 工厂和用户认证依赖。
"""

import logging

from fastapi import Header, HTTPException

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
    """获取会话 Repository（FastAPI 依赖注入用）。

    Returns:
        会话 BaseRepository 实例
    """
    return get_repository("sessions")


def get_settings_repository() -> BaseRepository:
    """获取用户设置 Repository（FastAPI 依赖注入用）。

    Returns:
        用户设置 BaseRepository 实例
    """
    return get_repository("user_settings")


def get_feedback_repository() -> BaseRepository:
    """获取用户反馈 Repository（FastAPI 依赖注入用）。

    Returns:
        用户反馈 BaseRepository 实例
    """
    return get_repository("user_feedback")


async def get_tableau_username(
    x_tableau_username: str = Header(None, alias="X-Tableau-Username"),
) -> str:
    """从请求头获取 Tableau 用户名。

    Args:
        x_tableau_username: X-Tableau-Username 请求头值

    Returns:
        Tableau 用户名

    Raises:
        HTTPException: 请求头缺失时返回 401
    """
    if not x_tableau_username:
        raise HTTPException(
            status_code=401,
            detail="缺少 X-Tableau-Username 请求头",
        )
    return x_tableau_username
