# -*- coding: utf-8 -*-
"""
FastAPI 应用入口

提供 Analytics Assistant 的 RESTful API 和 SSE 流式端点。
底层存储基于 LangGraph BaseStore（通过 infra/storage 模块），无需 SQLAlchemy。
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from analytics_assistant.src.infra.config import get_config

from .middleware import register_exception_handlers, RequestLoggingMiddleware

logger = logging.getLogger(__name__)


def _get_api_config() -> dict:
    """从 app.yaml 读取 API 配置。

    Returns:
        API 配置字典
    """
    try:
        config = get_config()
        return config.get("api", {})
    except Exception as e:
        logger.warning(f"加载 API 配置失败，使用默认值: {e}")
        return {}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """应用生命周期管理。

    BaseStore 由 StoreFactory 懒加载，无需显式初始化。
    """
    logger.info("Analytics Assistant API 启动中...")
    yield
    logger.info("Analytics Assistant API 已关闭")


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用实例。

    Returns:
        配置完成的 FastAPI 应用
    """
    api_config = _get_api_config()

    app = FastAPI(
        title="Analytics Assistant API",
        description="Analytics Assistant 后端 API，提供 SSE 流式聊天、会话管理、用户设置和反馈功能。",
        version="1.0.0",
        lifespan=lifespan,
    )

    # 配置 CORS
    cors_config = api_config.get("cors", {})
    allowed_origins = cors_config.get("allowed_origins", ["*"])
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注册请求日志中间件
    app.add_middleware(RequestLoggingMiddleware)

    # 注册异常处理器
    register_exception_handlers(app)

    # 注册路由
    from .routers import chat, feedback, health, sessions, settings

    app.include_router(health.router)
    app.include_router(chat.router)
    app.include_router(sessions.router)
    app.include_router(settings.router)
    app.include_router(feedback.router)

    return app


# 应用实例（供 uvicorn 使用）
app = create_app()


if __name__ == "__main__":
    import uvicorn

    api_config = _get_api_config()
    port = api_config.get("port", 8000)
    uvicorn.run(
        "analytics_assistant.src.api.main:app",
        host="0.0.0.0",
        port=port,
        reload=True,
    )
