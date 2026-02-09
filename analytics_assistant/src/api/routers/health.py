# -*- coding: utf-8 -*-
"""
健康检查路由

提供 /health 端点，用于监控服务状态和存储连通性。
"""

import logging

from fastapi import APIRouter

from analytics_assistant.src.api.models.common import HealthResponse
from analytics_assistant.src.infra.storage import get_kv_store

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """健康检查端点。

    验证服务运行状态和存储连通性。

    Returns:
        HealthResponse: 包含服务状态、版本和存储状态
    """
    storage_status = "ok"
    try:
        store = get_kv_store()
        # 执行一次轻量读操作验证存储可用
        store.get(("_health_check",), "_ping")
    except Exception as e:
        logger.warning(f"存储健康检查失败: {e}")
        storage_status = "unavailable"

    return HealthResponse(
        status="ok",
        version="1.0.0",
        storage=storage_status,
    )
