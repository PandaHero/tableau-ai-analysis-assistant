# -*- coding: utf-8 -*-
"""
用户设置路由

提供用户设置端点：
- GET  /api/settings    获取用户设置（首次访问自动创建默认值）
- PUT  /api/settings    更新用户设置（部分更新）

数据隔离：通过 X-Tableau-Username 请求头过滤。

注意：使用同步 CRUD 方法，因为默认 SqliteStore 后端不支持异步操作。
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from analytics_assistant.src.api.dependencies import (
    get_settings_repository,
    get_tableau_username,
)
from analytics_assistant.src.api.models.settings import (
    UpdateSettingsRequest,
    UserSettingsResponse,
)
from analytics_assistant.src.infra.storage import BaseRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])

# 默认设置值
_DEFAULT_SETTINGS = {
    "language": "zh",
    "analysis_depth": "detailed",
    "theme": "light",
    "default_datasource_id": None,
    "show_thinking_process": True,
}


@router.get("", response_model=UserSettingsResponse)
def get_settings(
    tableau_username: str = Depends(get_tableau_username),
    repo: BaseRepository = Depends(get_settings_repository),
) -> UserSettingsResponse:
    """获取用户设置（首次访问自动创建默认值）。

    Args:
        tableau_username: Tableau 用户名
        repo: 用户设置 Repository

    Returns:
        用户设置
    """
    data = repo.find_by_id(tableau_username)

    if data is None:
        # 首次访问，创建默认设置
        default_data = {
            **_DEFAULT_SETTINGS,
            "tableau_username": tableau_username,
        }
        data = repo.save(tableau_username, default_data)
        logger.info(f"创建默认用户设置: user={tableau_username}")

    return UserSettingsResponse(
        tableau_username=data.get("tableau_username", tableau_username),
        language=data.get("language", "zh"),
        analysis_depth=data.get("analysis_depth", "detailed"),
        theme=data.get("theme", "light"),
        default_datasource_id=data.get("default_datasource_id"),
        show_thinking_process=data.get("show_thinking_process", True),
        created_at=data["created_at"],
        updated_at=data["updated_at"],
    )


@router.put("", response_model=UserSettingsResponse)
def update_settings(
    request: UpdateSettingsRequest,
    tableau_username: str = Depends(get_tableau_username),
    repo: BaseRepository = Depends(get_settings_repository),
) -> UserSettingsResponse:
    """更新用户设置（部分更新，只更新非 None 字段）。

    Args:
        request: 更新请求
        tableau_username: Tableau 用户名
        repo: 用户设置 Repository

    Returns:
        更新后的用户设置
    """
    data = repo.find_by_id(tableau_username)

    if data is None:
        # 首次更新，先创建默认设置
        data = {
            **_DEFAULT_SETTINGS,
            "tableau_username": tableau_username,
        }

    # 部分更新：只更新非 None 字段
    update_data = dict(data)
    update_data["tableau_username"] = tableau_username

    if request.language is not None:
        update_data["language"] = request.language
    if request.analysis_depth is not None:
        update_data["analysis_depth"] = request.analysis_depth
    if request.theme is not None:
        update_data["theme"] = request.theme
    if request.default_datasource_id is not None:
        update_data["default_datasource_id"] = request.default_datasource_id
    if request.show_thinking_process is not None:
        update_data["show_thinking_process"] = request.show_thinking_process

    saved = repo.save(tableau_username, update_data)

    logger.info(f"更新用户设置: user={tableau_username}")

    return UserSettingsResponse(
        tableau_username=saved.get("tableau_username", tableau_username),
        language=saved.get("language", "zh"),
        analysis_depth=saved.get("analysis_depth", "detailed"),
        theme=saved.get("theme", "light"),
        default_datasource_id=saved.get("default_datasource_id"),
        show_thinking_process=saved.get("show_thinking_process", True),
        created_at=saved["created_at"],
        updated_at=saved["updated_at"],
    )
