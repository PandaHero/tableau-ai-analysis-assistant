# -*- coding: utf-8 -*-
"""用户设置路由。"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from analytics_assistant.src.api.dependencies import (
    get_settings_repository,
    get_tableau_username,
)
from analytics_assistant.src.api.models.settings import (
    UpdateSettingsRequest,
    UserSettingsResponse,
)
from analytics_assistant.src.infra.business_storage import SettingsRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])

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
    repo: SettingsRepository = Depends(get_settings_repository),
) -> UserSettingsResponse:
    """获取用户设置，首次访问会自动初始化默认值。"""
    data = repo.find_by_id(tableau_username)
    if data is None:
        data = repo.save(
            tableau_username,
            {
                **_DEFAULT_SETTINGS,
                "tableau_username": tableau_username,
            },
        )
        logger.info("创建默认用户设置: user=%s", tableau_username)

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
    repo: SettingsRepository = Depends(get_settings_repository),
) -> UserSettingsResponse:
    """更新用户设置。"""
    data = repo.find_by_id(tableau_username) or {
        **_DEFAULT_SETTINGS,
        "tableau_username": tableau_username,
    }

    payload = dict(data)
    payload["tableau_username"] = tableau_username
    if request.language is not None:
        payload["language"] = request.language
    if request.analysis_depth is not None:
        payload["analysis_depth"] = request.analysis_depth
    if request.theme is not None:
        payload["theme"] = request.theme
    if request.default_datasource_id is not None:
        payload["default_datasource_id"] = request.default_datasource_id
    if request.show_thinking_process is not None:
        payload["show_thinking_process"] = request.show_thinking_process

    saved = repo.save(tableau_username, payload)
    logger.info("更新用户设置: user=%s", tableau_username)

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
