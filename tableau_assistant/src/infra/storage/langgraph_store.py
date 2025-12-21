# -*- coding: utf-8 -*-
"""
LangGraph SqliteStore 全局实例

提供 LangGraph 框架的 SqliteStore 持久化存储，用于元数据和维度层级缓存。

使用示例:
    from tableau_assistant.src.infra.storage import get_langgraph_store
    
    store = get_langgraph_store()
    store.put(namespace=("metadata", "ds_123"), key="data", value={"...": "..."})
    item = store.get(namespace=("metadata", "ds_123"), key="data")

Requirements: 1.1, 1.2
"""
import logging
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 全局实例
_global_store: Optional["SqliteStore"] = None
_store_lock = threading.Lock()

# 默认配置
DEFAULT_DB_PATH = "data/langgraph_store.db"
DEFAULT_TTL_MINUTES = 1440  # 24 小时


def get_langgraph_store(db_path: str = DEFAULT_DB_PATH) -> "SqliteStore":
    """
    获取全局 LangGraph SqliteStore 实例（单例模式）
    
    Args:
        db_path: SQLite 数据库路径
    
    Returns:
        SqliteStore 实例
    
    Raises:
        ImportError: 如果 langgraph 未安装
    """
    global _global_store
    
    if _global_store is None:
        with _store_lock:
            if _global_store is None:
                _global_store = _create_store(db_path)
    
    return _global_store


def _create_store(db_path: str) -> "SqliteStore":
    """创建 SqliteStore 实例"""
    from langgraph.store.sqlite import SqliteStore
    from langgraph.store.base import TTLConfig
    import sqlite3
    
    # 确保目录存在
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    
    # 创建连接
    # 设置 isolation_level=None 以使用自动提交模式，避免事务冲突
    conn = sqlite3.connect(db_path, check_same_thread=False, isolation_level=None)
    
    # TTL 配置
    ttl_config: TTLConfig = {
        "default_ttl": DEFAULT_TTL_MINUTES,  # 24 小时（分钟）
        "refresh_on_read": True,  # 读取时刷新 TTL
        "sweep_interval_minutes": 60,  # 每小时清理过期数据
    }
    
    # 创建 SqliteStore
    store = SqliteStore(conn, ttl=ttl_config)
    
    # 运行迁移，创建必要的表
    store.setup()
    
    logger.info(f"LangGraph SqliteStore 初始化完成: {db_path}, TTL={DEFAULT_TTL_MINUTES}min")
    
    return store


def reset_langgraph_store() -> None:
    """
    重置全局实例（主要用于测试）
    
    调用后，下次 get_langgraph_store() 将创建新实例。
    """
    global _global_store
    
    with _store_lock:
        if _global_store is not None:
            try:
                # 尝试关闭连接
                if hasattr(_global_store, '_conn'):
                    _global_store._conn.close()
            except Exception as e:
                logger.warning(f"关闭 SqliteStore 连接时出错: {e}")
            
            _global_store = None
            logger.info("LangGraph SqliteStore 已重置")


__all__ = [
    "get_langgraph_store",
    "reset_langgraph_store",
    "DEFAULT_DB_PATH",
    "DEFAULT_TTL_MINUTES",
]
