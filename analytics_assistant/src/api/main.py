# -*- coding: utf-8 -*-
"""
FastAPI 应用入口

提供 Analytics Assistant 的 RESTful API 和 SSE 流式端点。
底层存储基于 LangGraph BaseStore（通过 infra/storage 模块），无需 SQLAlchemy。
"""

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from analytics_assistant.src.agents.semantic_parser.graph import (
    compile_semantic_parser_graph,
)
from analytics_assistant.src.infra.config import get_config

from .middleware import register_exception_handlers, RequestLoggingMiddleware

# 配置日志输出到控制台
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

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
    compile_semantic_parser_graph()
    logger.info("semantic_parser graph 预编译完成")
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
    allowed_origins = cors_config.get("allowed_origins", [])  # 默认空列表，需显式配置
    allow_credentials = cors_config.get("allow_credentials", False)

    # 安全检查：credentials=True 时禁止 origins=["*"]
    if allow_credentials and "*" in allowed_origins:
        logger.warning(
            "CORS 安全冲突: allow_credentials=True 时不应使用 "
            "allowed_origins=['*']，已自动禁用 credentials"
        )
        allow_credentials = False

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=allow_credentials,
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

    # ── 静态文件 serve（前端 build 产物）──────────────────────────────────────
    # 前端 build 后的 dist 目录，FastAPI 直接 serve，不依赖 Vite dev server。
    # 这样重启后端时，Tableau iframe 页面不会刷新，initializeAsync 握手状态永久保持。
    _frontend_dist = Path(__file__).parent.parent.parent / "frontend" / "dist"
    if _frontend_dist.exists():
        # 挂载 assets 静态资源目录（JS/CSS/图片等 hash 文件名资源）
        _assets_dir = _frontend_dist / "assets"
        if _assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="assets")

        # 根路径返回 index.html（Tableau 扩展入口）
        @app.get("/", include_in_schema=False)
        async def serve_index():
            return FileResponse(str(_frontend_dist / "index.html"))

        # SPA fallback：非 /api/ 开头的路径都返回 index.html（或对应静态文件）
        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa(full_path: str, request: Request):
            # /api/ 开头的请求不应走到这里（FastAPI 路由优先），但加个兜底防御
            if full_path.startswith("api/"):
                raise HTTPException(status_code=404)
            file_path = _frontend_dist / full_path
            if file_path.exists() and file_path.is_file():
                return FileResponse(str(file_path))
            accept = request.headers.get("accept", "").lower()
            if "text/html" not in accept:
                raise HTTPException(status_code=404)
            return FileResponse(str(_frontend_dist / "index.html"))

        logger.info(f"前端静态文件已挂载: {_frontend_dist}")
    else:
        logger.warning(
            f"前端 dist 目录不存在: {_frontend_dist}\n"
            "请先执行: cd analytics_assistant/frontend && npm run build"
        )

    return app

# 应用实例（供 uvicorn 使用）
app = create_app()

if __name__ == "__main__":
    import uvicorn

    api_config = _get_api_config()
    host = api_config.get("host", "127.0.0.1")
    port = api_config.get("port", 8000)
    uvicorn.run(
        "analytics_assistant.src.api.main:app",
        host=host,
        port=port,
        reload=True,
    )
