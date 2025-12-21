"""
FastAPI 路由模块

包含:
- chat: 聊天 API 路由
- cache: 缓存管理 API 路由
- custom_models: 自定义模型 API 路由
"""

from tableau_assistant.src.api.chat import router as chat_router
from tableau_assistant.src.api.cache import router as cache_router
from tableau_assistant.src.api.custom_models import router as custom_models_router

__all__ = [
    "chat_router",
    "cache_router",
    "custom_models_router",
]
