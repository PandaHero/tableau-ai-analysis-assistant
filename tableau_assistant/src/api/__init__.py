"""
FastAPI 路由模块

包含:
- chat: 聊天 API 路由
- preload: 预热服务 API 路由
"""

from tableau_assistant.src.api.chat import router as chat_router
from tableau_assistant.src.api.preload import router as preload_router

__all__ = [
    "chat_router",
    "preload_router",
]
