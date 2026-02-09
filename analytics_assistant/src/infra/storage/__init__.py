"""
存储模块

统一使用 LangGraph/LangChain 提供的存储能力：
- StoreFactory: 根据配置创建不同后端的 BaseStore（sqlite/memory/postgres/redis）
- KV 存储: LangGraph BaseStore 全局单例（通过 StoreFactory 创建）
- CacheManager: 基于 BaseStore 的高级缓存功能（同步 + 异步）
- BaseRepository: 基于 BaseStore 的 CRUD 抽象（用于 API 层数据）
- 向量存储: LangChain FAISS / ChromaDB

模块拆分说明：
- store_factory.py: 存储工厂，根据配置创建 BaseStore 实例
- kv_store.py: KV 存储全局单例（不依赖 infra.ai）
- cache.py: 统一 CacheManager（同步 + 异步，不依赖 infra.ai）
- repository.py: BaseRepository CRUD 抽象（用于 API 层）
- vector_store.py: 向量存储（依赖 infra.ai 的 get_model_manager）

拆分原因：消除 infra.ai ↔ infra.storage 的循环导入。
infra.ai.model_persistence 需要 CacheManager，而 vector_store 需要 infra.ai。

向量存储使用方式：
    from analytics_assistant.src.infra.storage.vector_store import get_vector_store
"""

from .cache import CacheManager
from .kv_store import (
    DEFAULT_DB_PATH,
    DEFAULT_TTL_MINUTES,
    get_kv_store,
    reset_kv_store,
)
from .repository import BaseRepository
from .store_factory import StoreFactory

__all__ = [
    # 存储工厂
    "StoreFactory",
    # KV 存储
    "get_kv_store",
    "reset_kv_store",
    # 缓存管理
    "CacheManager",
    # CRUD 抽象
    "BaseRepository",
    # 常量
    "DEFAULT_DB_PATH",
    "DEFAULT_TTL_MINUTES",
]
