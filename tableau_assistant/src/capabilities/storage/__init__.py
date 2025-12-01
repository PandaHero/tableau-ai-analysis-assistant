"""
存储能力

提供持久化存储功能，用于缓存元数据、维度层级等数据。

主要组件：
- PersistentStore: 持久化存储，基于 SQLite
- StoreManager: 存储管理器，提供高级存储操作

使用示例：
    from tableau_assistant.src.capabilities.storage import StoreManager
    
    store_manager = StoreManager(store)
    metadata = store_manager.get_metadata(datasource_luid)
"""
from tableau_assistant.src.capabilities.storage.persistent_store import PersistentStore
from tableau_assistant.src.capabilities.storage.store_manager import StoreManager

__all__ = [
    "PersistentStore",
    "StoreManager",
]
