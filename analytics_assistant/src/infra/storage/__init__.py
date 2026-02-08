"""
存储模块

统一使用 LangGraph/LangChain 提供的存储能力：
- KV 存储：LangGraph SqliteStore（单例模式）
- 缓存管理：基于 KV 存储的高级缓存功能
- 向量存储：LangChain FAISS / ChromaDB

模块拆分说明：
- kv_store.py: KV 存储 + CacheManager（不依赖 infra.ai）
- vector_store.py: 向量存储（依赖 infra.ai 的 get_model_manager）

拆分原因：消除 infra.ai ↔ infra.storage 的循环导入。
infra.ai.model_persistence 需要 CacheManager，而 vector_store 需要 infra.ai。

向量存储使用方式：
    from analytics_assistant.src.infra.storage.vector_store import get_vector_store
"""

from .kv_store import (
    # KV 存储
    get_kv_store,
    reset_kv_store,
    # 缓存管理
    CacheManager,
    # 常量
    DEFAULT_DB_PATH,
    DEFAULT_TTL_MINUTES,
)

__all__ = [
    # KV 存储
    "get_kv_store",
    "reset_kv_store",
    # 缓存管理
    "CacheManager",
    # 常量
    "DEFAULT_DB_PATH",
    "DEFAULT_TTL_MINUTES",
]
