# -*- coding: utf-8 -*-
"""
KV 存储与缓存管理模块

提供 LangGraph SqliteStore 单例和基于 KV 存储的缓存管理器。

本模块不依赖 infra.ai，可被 infra.ai 安全导入。

使用示例:
    from analytics_assistant.src.infra.storage import (
        get_kv_store,
        CacheManager,
    )

    # KV 存储
    store = get_kv_store()
    store.put(namespace=("cache", "embeddings"), key="key1", value={"data": "..."})

    # 缓存管理
    cache = CacheManager("my_namespace")
    cache.set("key", value, ttl=3600)
"""

import hashlib
import json
import logging
import sqlite3
import threading
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from langgraph.store.base import TTLConfig
from langgraph.store.sqlite import SqliteStore

from ..config import get_config

logger = logging.getLogger(__name__)


# ============================================
# 配置获取
# ============================================


def _get_storage_config() -> Dict[str, Any]:
    """从统一配置获取存储配置"""
    try:
        config = get_config()
        return config.get_storage_config()
    except Exception as e:
        logger.warning(f"获取存储配置失败，使用默认值: {e}")
        return {}


def _get_default_db_path() -> str:
    """获取默认数据库路径"""
    storage_config = _get_storage_config()
    return storage_config.get("connection_string", "analytics_assistant/data/storage.db")


def _get_default_ttl_minutes() -> int:
    """获取默认 TTL（分钟）"""
    storage_config = _get_storage_config()
    return storage_config.get("ttl", 1440)  # 默认 24 小时


# ============================================
# KV 存储（LangGraph SqliteStore 单例）
# ============================================

_kv_store = None
_kv_store_lock = threading.Lock()

# 保留常量用于向后兼容（但实际值从配置读取）
DEFAULT_DB_PATH = "analytics_assistant/data/storage.db"
DEFAULT_TTL_MINUTES = 1440  # 24 小时


def get_kv_store(db_path: str = None):
    """获取全局 KV 存储实例（LangGraph SqliteStore 单例）

    Args:
        db_path: SQLite 数据库路径（可选，默认从配置读取）

    Returns:
        LangGraph SqliteStore 实例
    """
    global _kv_store

    if _kv_store is None:
        with _kv_store_lock:
            if _kv_store is None:
                actual_db_path = db_path or _get_default_db_path()
                _kv_store = _create_kv_store(actual_db_path)

    return _kv_store


def _create_kv_store(db_path: str):
    """创建 KV 存储实例"""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path, check_same_thread=False, isolation_level=None)

    ttl_minutes = _get_default_ttl_minutes()
    ttl_config: TTLConfig = {
        "default_ttl": ttl_minutes,
        "refresh_on_read": True,
        "sweep_interval_minutes": 60,
    }

    store = SqliteStore(conn, ttl=ttl_config)
    store.setup()

    logger.info(f"KV 存储已初始化: {db_path}, TTL={ttl_minutes}min")
    return store


def reset_kv_store() -> None:
    """重置 KV 存储（主要用于测试）"""
    global _kv_store

    with _kv_store_lock:
        if _kv_store is not None:
            try:
                if hasattr(_kv_store, "_conn"):
                    _kv_store._conn.close()
            except Exception as e:
                logger.warning(f"关闭 KV 存储时出错: {e}")
            _kv_store = None
            logger.info("KV 存储已重置")


# ============================================
# 缓存管理器
# ============================================


class CacheManager:
    """缓存管理器

    基于 LangGraph SqliteStore 的高级缓存功能：
    - 自动 Hash 计算
    - TTL 配置
    - 命名空间隔离
    - 统计信息

    Examples:
        cache = CacheManager("embeddings")

        # 基本操作
        cache.set("key1", {"data": "value"}, ttl=3600)
        value = cache.get("key1")

        # 自动计算缓存
        result = cache.get_or_compute(
            key="expensive_result",
            compute_fn=lambda: expensive_computation(),
            ttl=3600
        )
    """

    def __init__(
        self,
        namespace: str,
        default_ttl: Optional[int] = None,
        enable_stats: bool = True,
    ):
        """初始化缓存管理器

        Args:
            namespace: 命名空间
            default_ttl: 默认 TTL（秒），None 使用全局默认
            enable_stats: 是否启用统计
        """
        self.namespace = namespace
        self.default_ttl = default_ttl
        self.enable_stats = enable_stats
        self._store = get_kv_store()
        self._namespace_tuple = (namespace,)

        self._stats = {"hits": 0, "misses": 0, "sets": 0, "deletes": 0}

        logger.info(f"缓存管理器已初始化: namespace={namespace}")

    def get(self, key: str, default: Any = None) -> Any:
        """获取缓存"""
        try:
            item = self._store.get(self._namespace_tuple, key)
            if item and item.value is not None:
                if self.enable_stats:
                    self._stats["hits"] += 1
                return item.value
            if self.enable_stats:
                self._stats["misses"] += 1
            return default
        except Exception as e:
            logger.error(f"获取缓存失败: key={key}, error={e}")
            return default

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """设置缓存"""
        try:
            ttl_minutes = None
            if ttl is not None:
                ttl_minutes = ttl // 60
            elif self.default_ttl is not None:
                ttl_minutes = self.default_ttl // 60

            if ttl_minutes:
                self._store.put(self._namespace_tuple, key, value, ttl=ttl_minutes)
            else:
                self._store.put(self._namespace_tuple, key, value)

            if self.enable_stats:
                self._stats["sets"] += 1
            return True
        except Exception as e:
            logger.error(f"设置缓存失败: key={key}, error={e}")
            return False

    def delete(self, key: str) -> bool:
        """删除缓存"""
        try:
            self._store.delete(self._namespace_tuple, key)
            if self.enable_stats:
                self._stats["deletes"] += 1
            return True
        except Exception as e:
            logger.error(f"删除缓存失败: key={key}, error={e}")
            return False

    def exists(self, key: str) -> bool:
        """检查缓存是否存在"""
        item = self._store.get(self._namespace_tuple, key)
        return item is not None and item.value is not None

    def clear(self) -> bool:
        """清空命名空间的所有缓存"""
        try:
            items = self._store.search(self._namespace_tuple, limit=10000)
            for item in items:
                self._store.delete(self._namespace_tuple, item.key)
            logger.info(f"已清空缓存: namespace={self.namespace}")
            return True
        except Exception as e:
            logger.error(f"清空缓存失败: error={e}")
            return False

    def compute_hash(self, obj: Any) -> str:
        """计算对象的 Hash 值"""
        try:
            if isinstance(obj, (str, int, float, bool)):
                json_str = str(obj)
            elif isinstance(obj, (dict, list, tuple)):
                json_str = json.dumps(obj, sort_keys=True, ensure_ascii=False)
            else:
                json_str = json.dumps(
                    obj.__dict__, sort_keys=True, ensure_ascii=False
                )
            return hashlib.md5(json_str.encode("utf-8")).hexdigest()
        except Exception:
            # 序列化失败时回退到 Python 内置 hash，不影响功能
            return str(hash(str(obj)))

    def get_or_compute(
        self,
        key: str,
        compute_fn: Callable,
        ttl: Optional[int] = None,
        force_refresh: bool = False,
    ) -> Any:
        """获取缓存，不存在则计算并缓存"""
        if force_refresh:
            self.delete(key)

        value = self.get(key)
        if value is not None:
            return value

        logger.debug(f"缓存不存在，开始计算: key={key}")
        value = compute_fn()
        self.set(key, value, ttl=ttl)
        return value

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        if not self.enable_stats:
            return {"enabled": False}

        total = self._stats["hits"] + self._stats["misses"]
        hit_rate = self._stats["hits"] / total if total > 0 else 0.0

        return {
            "namespace": self.namespace,
            "hits": self._stats["hits"],
            "misses": self._stats["misses"],
            "sets": self._stats["sets"],
            "deletes": self._stats["deletes"],
            "hit_rate": f"{hit_rate:.2%}",
        }


__all__ = [
    "get_kv_store",
    "reset_kv_store",
    "CacheManager",
    "DEFAULT_DB_PATH",
    "DEFAULT_TTL_MINUTES",
]
