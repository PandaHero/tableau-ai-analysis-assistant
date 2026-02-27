# -*- coding: utf-8 -*-
"""
KV 存储单例模块

提供 LangGraph BaseStore 全局单例访问。
底层通过 StoreFactory 创建，后端类型由 app.yaml 配置决定。

使用示例:
    from analytics_assistant.src.infra.storage import get_kv_store

    store = get_kv_store()
    store.put(namespace=("cache", "embeddings"), key="key1", value={"data": "..."})
"""

import logging
import threading
from typing import Optional

from langgraph.store.base import BaseStore

logger = logging.getLogger(__name__)

# 全局单例
_kv_store: Optional[BaseStore] = None
_kv_store_lock = threading.Lock()

# 保留常量用于向后兼容
DEFAULT_DB_PATH = "analytics_assistant/data/storage.db"
DEFAULT_TTL_MINUTES = 1440  # 24 小时

def get_kv_store(db_path: Optional[str] = None) -> BaseStore:
    """获取全局 KV 存储实例（单例）。

    底层通过 StoreFactory 创建，后端类型由 app.yaml storage.backend 决定。

    Args:
        db_path: 数据库路径（仅 sqlite 后端有效，可选，默认从配置读取）

    Returns:
        LangGraph BaseStore 实例
    """
    global _kv_store

    if _kv_store is None:
        with _kv_store_lock:
            if _kv_store is None:
                # 延迟导入：获取全局单例，避免模块加载时循环初始化
                from .store_factory import StoreFactory

                if db_path is not None:
                    _kv_store = StoreFactory.create_store(
                        backend="sqlite",
                        connection_string=db_path,
                    )
                    logger.info(f"KV 存储已初始化（指定路径）: {db_path}")
                else:
                    _kv_store = StoreFactory.get_default_store()
                    logger.info("KV 存储已初始化（使用默认配置）")

    return _kv_store

def reset_kv_store() -> None:
    """重置 KV 存储（主要用于测试）。"""
    global _kv_store

    with _kv_store_lock:
        if _kv_store is not None:
            # 延迟导入：获取全局单例，避免模块加载时循环初始化
            from .store_factory import StoreFactory

            StoreFactory._close_store(_kv_store)
            _kv_store = None
            logger.info("KV 存储已重置")

__all__ = [
    "get_kv_store",
    "reset_kv_store",
    "DEFAULT_DB_PATH",
    "DEFAULT_TTL_MINUTES",
]
