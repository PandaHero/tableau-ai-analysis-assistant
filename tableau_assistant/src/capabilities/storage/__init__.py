"""
存储能力

提供统一的存储管理功能。

主要组件：
- StoreManager: 统一存储管理器，基于 SQLite 持久化
  - 业务数据缓存（元数据、维度层级、数据模型等）
  - 用户偏好、问题历史、异常知识库

LLM 缓存：
- 使用 LangChain 内置的 SQLiteCache（不重复造轮子）
- 通过 setup_llm_cache() 初始化

使用示例：
    # 业务数据缓存
    from tableau_assistant.src.capabilities.storage import get_store_manager
    
    store = get_store_manager()
    store.put_metadata(datasource_luid, metadata)
    metadata = store.get_metadata(datasource_luid)
    
    # LLM 响应缓存（应用启动时调用一次）
    from tableau_assistant.src.capabilities.storage import setup_llm_cache
    setup_llm_cache()
"""
import logging
from pathlib import Path

from tableau_assistant.src.capabilities.storage.store_manager import (
    StoreManager,
    StoreItem,
    get_store_manager,
    reset_store_manager,
)

logger = logging.getLogger(__name__)

# LLM 缓存是否已初始化
_llm_cache_initialized = False


def setup_llm_cache(
    db_path: str = "data/llm_cache.db",
    force: bool = False
) -> bool:
    """
    初始化 LLM 响应缓存
    
    使用 LangChain 内置的 SQLiteCache，缓存 LLM 调用结果以节省成本。
    
    Args:
        db_path: SQLite 数据库文件路径
        force: 是否强制重新初始化
    
    Returns:
        是否成功初始化
    """
    global _llm_cache_initialized
    
    if _llm_cache_initialized and not force:
        logger.debug("LLM cache already initialized")
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
        logger.warning(f"LLM cache not available (missing dependency): {e}")
        return False
    except Exception as e:
        logger.error(f"Failed to initialize LLM cache: {e}")
        return False


def get_llm_cache_stats() -> dict:
    """获取 LLM 缓存统计信息"""
    try:
        from langchain_core.globals import get_llm_cache
        
        cache = get_llm_cache()
        if cache is None:
            return {"status": "not_initialized"}
        
        return {
            "status": "initialized",
            "type": type(cache).__name__,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def clear_llm_cache() -> bool:
    """清除 LLM 缓存"""
    try:
        from langchain_core.globals import get_llm_cache
        
        cache = get_llm_cache()
        if cache is not None:
            cache.clear()
            logger.info("LLM cache cleared")
            return True
        return False
    except Exception as e:
        logger.error(f"Failed to clear LLM cache: {e}")
        return False


__all__ = [
    # 业务数据存储
    "StoreManager",
    "StoreItem",
    "get_store_manager",
    "reset_store_manager",
    # LLM 缓存管理
    "setup_llm_cache",
    "get_llm_cache_stats",
    "clear_llm_cache",
]
