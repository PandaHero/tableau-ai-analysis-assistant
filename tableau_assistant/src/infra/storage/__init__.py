# -*- coding: utf-8 -*-
"""
存储管理

提供统一的存储管理功能。

主要组件：
- StoreManager: 统一存储管理器，基于 SQLite 持久化

使用示例：
    from tableau_assistant.src.infra.storage import get_store_manager
    
    store = get_store_manager()
    store.put_metadata(datasource_luid, metadata)
    metadata = store.get_metadata(datasource_luid)
"""
import logging
from pathlib import Path

# 从本地模块导入
from tableau_assistant.src.infra.storage.store_manager import (
    StoreManager,
    StoreItem,
    get_store_manager,
    reset_store_manager,
)

logger = logging.getLogger(__name__)

_llm_cache_initialized = False


def setup_llm_cache(db_path: str = "data/llm_cache.db", force: bool = False) -> bool:
    """初始化 LLM 响应缓存"""
    global _llm_cache_initialized
    
    if _llm_cache_initialized and not force:
        return True
    
    try:
        from langchain_core.globals import set_llm_cache
        from langchain_community.cache import SQLiteCache
        
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        cache = SQLiteCache(database_path=db_path)
        set_llm_cache(cache)
        _llm_cache_initialized = True
        logger.info(f"LLM cache initialized: {db_path}")
        return True
    except ImportError as e:
        logger.warning(f"LLM cache not available: {e}")
        return False
    except Exception as e:
        logger.error(f"Failed to initialize LLM cache: {e}")
        return False


def get_llm_cache_stats() -> dict:
    try:
        from langchain_core.globals import get_llm_cache
        cache = get_llm_cache()
        if cache is None:
            return {"status": "not_initialized"}
        return {"status": "initialized", "type": type(cache).__name__}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def clear_llm_cache() -> bool:
    try:
        from langchain_core.globals import get_llm_cache
        cache = get_llm_cache()
        if cache is not None:
            cache.clear()
            return True
        return False
    except Exception:
        return False


__all__ = [
    "StoreManager", "StoreItem", "get_store_manager", "reset_store_manager",
    "setup_llm_cache", "get_llm_cache_stats", "clear_llm_cache",
]
