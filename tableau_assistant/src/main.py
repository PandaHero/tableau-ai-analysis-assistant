"""
FastAPI应用入口
"""
import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv

# 加载环境变量 - 从项目根目录加载
root_dir = Path(__file__).parent.parent.parent
env_path = root_dir / ".env"
load_dotenv(dotenv_path=env_path)

# 前端静态文件目录
FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"

# 创建FastAPI应用
app = FastAPI(
    title="VizQL Multi-Agent API",
    description="""
    基于LangChain + LangGraph的多智能体查询与分析系统
    
    ## 特性
    
    - **Token级流式输出**: 使用astream_events实现实时进度反馈
    - **类型安全**: 使用Pydantic模型提供输入输出验证
    - **自动文档**: 自动生成OpenAPI文档
    - **多智能体架构**: 7个专业化Agent协同工作
    
    ## 主要端点
    
    - `POST /api/chat`: 同步查询（返回完整结果）
    - `POST /api/chat/stream`: 流式查询（SSE实时推送）
    - `POST /api/boost-question`: 问题优化
    - `POST /api/metadata/init-hierarchy`: 元数据初始化
    
    ## 使用LangGraph 1.0新特性
    
    - **context_schema**: 运行时上下文（datasource_luid, user_id等）
    - **input_schema**: 输入验证（自动验证请求格式）
    - **output_schema**: 输出验证（自动验证响应格式）
    - **Store**: 跨会话持久化存储
    - **astream_events**: Token级流式输出
    """,
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# 配置CORS
from tableau_assistant.src.infra.config.settings import settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
from tableau_assistant.src.api.chat import router as chat_router
from tableau_assistant.src.api.cache import router as cache_router

app.include_router(chat_router)
app.include_router(cache_router)


@app.get("/api/status")
async def api_status():
    """API 状态检查"""
    return {
        "status": "ok",
        "message": "VizQL Multi-Agent API is running",
        "version": "0.1.0",
    }


@app.get("/health")
async def health_check():
    """健康检查端点"""
    return {"status": "healthy"}


# ============================================
# 静态文件服务（生产模式）
# ============================================

# 检查是否存在前端构建
if FRONTEND_DIST.exists() and (FRONTEND_DIST / "index.html").exists():
    # 挂载静态资源目录（JS、CSS、图片等）
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")
    
    # 挂载其他静态文件（favicon 等）
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIST)), name="static")
    
    @app.get("/")
    async def serve_frontend():
        """服务前端首页"""
        return FileResponse(str(FRONTEND_DIST / "index.html"))
    
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """
        SPA 路由回退
        
        对于非 API 路径，返回 index.html 让前端路由处理
        """
        # API 路径不处理
        if full_path.startswith("api/") or full_path in ["docs", "redoc", "openapi.json", "health"]:
            return {"error": "Not found"}
        
        # 检查是否是静态文件
        file_path = FRONTEND_DIST / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        
        # 其他路径返回 index.html（SPA 路由）
        return FileResponse(str(FRONTEND_DIST / "index.html"))
else:
    # 没有前端构建，显示 API 状态
    @app.get("/")
    async def root():
        """API 根路径"""
        return {
            "status": "ok",
            "message": "VizQL Multi-Agent API is running",
            "version": "0.1.0",
            "note": "Frontend not built. Run 'npm run build' in tableau_assistant/frontend to enable UI.",
        }


if __name__ == "__main__":
    import uvicorn

    # 构建uvicorn配置
    uvicorn_config = {
        "app": "main:app",
        "host": settings.api_host,
        "port": settings.api_port,
        "reload": settings.api_reload,
        "log_level": settings.api_log_level,
    }
    
    # HTTPS配置
    ssl_cert_file = settings.ssl_cert_file
    ssl_key_file = settings.ssl_key_file
    
    # 如果配置了SSL证书，启用HTTPS
    if ssl_cert_file and ssl_key_file:
        from pathlib import Path
        if Path(ssl_cert_file).exists() and Path(ssl_key_file).exists():
            uvicorn_config["ssl_certfile"] = ssl_cert_file
            uvicorn_config["ssl_keyfile"] = ssl_key_file
            print(f"🔒 HTTPS enabled: https://{settings.api_host}:{settings.api_port}")
        else:
            print(f"⚠️  SSL证书文件不存在，使用HTTP模式")
            print(f"   证书: {ssl_cert_file}")
            print(f"   密钥: {ssl_key_file}")
    else:
        print(f"ℹ️  未配置SSL证书，使用HTTP模式: http://{host}:{port}")
    
    uvicorn.run(**uvicorn_config)
