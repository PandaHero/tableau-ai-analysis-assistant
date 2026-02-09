# -*- coding: utf-8 -*-
"""
统一缓存管理器

基于 LangGraph BaseStore 的高级缓存功能，提供同步和异步两套 API。
- 命名空间隔离
- TTL 秒→分钟自动转换（LangGraph BaseStore TTL 单位为分钟）
- Hash 计算
- get_or_compute / aget_or_compute 模式
- 统计信息

使用示例:
    from analytics_assistant.src.infra.storage import CacheManager

    cache = CacheManager("embeddings")

    # 同步操作
    cache.set("key1", {"data": "value"}, ttl=3600)
    value = cache.get("key1")

    # 异步操作
    await cache.aset("key1", {"data": "value"}, ttl=3600)
    value = await cache.aget("key1")

    # 自动计算缓存
    result = cache.get_or_compute("key", compute_fn=lambda: expensive(), ttl=3600)
    result = await cache.aget_or_compute("key", compute_fn=async_expensive, ttl=3600)
"""

import hashlib
import json
import logging
from typing import Any, Awaitable, Callable, Dict, Optional

from langgraph.store.base import BaseStore

from .kv_store import get_kv_store

logger = logging.getLogger(__name__)


class CacheManager:
    """统一缓存管理器

    基于 LangGraph BaseStore 的薄封装，提供同步 + 异步双模式 API。

    核心功能：
    - 命名空间绑定：每个 CacheManager 实例绑定一个命名空间
    - TTL 转换：接口接受秒，内部转换为分钟（BaseStore 单位）
    - Hash 计算：compute_hash() 用于生成缓存键
    - 统计信息：命中/未命中/写入/删除计数

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
        store: Optional[BaseStore] = None,
    ):
        """初始化缓存管理器。

        Args:
            namespace: 命名空间
            default_ttl: 默认 TTL（秒），None 使用全局默认
            enable_stats: 是否启用统计
            store: 自定义 BaseStore 实例（可选，默认使用全局单例）
        """
        self.namespace = namespace
        self.default_ttl = default_ttl
        self.enable_stats = enable_stats
        self._namespace_tuple = (namespace,)

        if store is not None:
            self._store = store
        else:
            self._store = get_kv_store()

        self._stats: Dict[str, int] = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0,
        }

        logger.info(f"缓存管理器已初始化: namespace={namespace}")

    # ========================================
    # 同步 API
    # ========================================

    def get(self, key: str, default: Any = None) -> Any:
        """获取缓存值。

        Args:
            key: 缓存键
            default: 默认值

        Returns:
            缓存值或默认值
        """
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
            logger.error(
                f"获取缓存失败: namespace={self.namespace}, "
                f"key={key}, error={e}"
            )
            return default

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """设置缓存值。

        Args:
            key: 缓存键
            value: 缓存值
            ttl: TTL（秒），None 使用默认值

        Returns:
            是否成功
        """
        try:
            ttl_minutes = self._resolve_ttl_minutes(ttl)

            if ttl_minutes is not None:
                self._store.put(self._namespace_tuple, key, value, ttl=ttl_minutes)
            else:
                self._store.put(self._namespace_tuple, key, value)

            if self.enable_stats:
                self._stats["sets"] += 1
            return True
        except Exception as e:
            logger.error(
                f"设置缓存失败: namespace={self.namespace}, "
                f"key={key}, error={e}"
            )
            return False

    def delete(self, key: str) -> bool:
        """删除缓存。

        Args:
            key: 缓存键

        Returns:
            是否成功
        """
        try:
            self._store.delete(self._namespace_tuple, key)
            if self.enable_stats:
                self._stats["deletes"] += 1
            return True
        except Exception as e:
            logger.error(
                f"删除缓存失败: namespace={self.namespace}, "
                f"key={key}, error={e}"
            )
            return False

    def exists(self, key: str) -> bool:
        """检查缓存是否存在。

        Args:
            key: 缓存键

        Returns:
            是否存在
        """
        item = self._store.get(self._namespace_tuple, key)
        return item is not None and item.value is not None

    def clear(self) -> bool:
        """清空命名空间的所有缓存。

        Returns:
            是否成功
        """
        try:
            items = self._store.search(self._namespace_tuple, limit=10000)
            for item in items:
                self._store.delete(self._namespace_tuple, item.key)
            logger.info(f"已清空缓存: namespace={self.namespace}")
            return True
        except Exception as e:
            logger.error(
                f"清空缓存失败: namespace={self.namespace}, error={e}"
            )
            return False

    def get_or_compute(
        self,
        key: str,
        compute_fn: Callable[[], Any],
        ttl: Optional[int] = None,
        force_refresh: bool = False,
    ) -> Any:
        """获取缓存，不存在则计算并缓存（同步版本）。

        Args:
            key: 缓存键
            compute_fn: 计算函数（同步）
            ttl: TTL（秒）
            force_refresh: 是否强制刷新

        Returns:
            缓存值或计算结果
        """
        if force_refresh:
            self.delete(key)

        value = self.get(key)
        if value is not None:
            return value

        logger.debug(
            f"缓存不存在，开始计算: namespace={self.namespace}, key={key}"
        )
        value = compute_fn()
        self.set(key, value, ttl=ttl)
        return value

    # ========================================
    # 异步 API
    # ========================================

    async def aget(self, key: str, default: Any = None) -> Any:
        """异步获取缓存值。

        Args:
            key: 缓存键
            default: 默认值

        Returns:
            缓存值或默认值
        """
        try:
            item = await self._store.aget(self._namespace_tuple, key)
            if item and item.value is not None:
                if self.enable_stats:
                    self._stats["hits"] += 1
                return item.value
            if self.enable_stats:
                self._stats["misses"] += 1
            return default
        except Exception as e:
            logger.error(
                f"异步获取缓存失败: namespace={self.namespace}, "
                f"key={key}, error={e}"
            )
            return default

    async def aset(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """异步设置缓存值。

        Args:
            key: 缓存键
            value: 缓存值
            ttl: TTL（秒）

        Returns:
            是否成功
        """
        try:
            ttl_minutes = self._resolve_ttl_minutes(ttl)

            if ttl_minutes is not None:
                await self._store.aput(
                    self._namespace_tuple, key, value, ttl=ttl_minutes
                )
            else:
                await self._store.aput(self._namespace_tuple, key, value)

            if self.enable_stats:
                self._stats["sets"] += 1
            return True
        except Exception as e:
            logger.error(
                f"异步设置缓存失败: namespace={self.namespace}, "
                f"key={key}, error={e}"
            )
            return False

    async def adelete(self, key: str) -> bool:
        """异步删除缓存。

        Args:
            key: 缓存键

        Returns:
            是否成功
        """
        try:
            await self._store.adelete(self._namespace_tuple, key)
            if self.enable_stats:
                self._stats["deletes"] += 1
            return True
        except Exception as e:
            logger.error(
                f"异步删除缓存失败: namespace={self.namespace}, "
                f"key={key}, error={e}"
            )
            return False

    async def aget_or_compute(
        self,
        key: str,
        compute_fn: Callable[[], Awaitable[Any]],
        ttl: Optional[int] = None,
        force_refresh: bool = False,
    ) -> Any:
        """异步获取缓存，不存在则计算并缓存。

        Args:
            key: 缓存键
            compute_fn: 异步计算函数
            ttl: TTL（秒）
            force_refresh: 是否强制刷新

        Returns:
            缓存值或计算结果
        """
        if force_refresh:
            await self.adelete(key)

        value = await self.aget(key)
        if value is not None:
            return value

        logger.debug(
            f"缓存不存在，开始异步计算: namespace={self.namespace}, key={key}"
        )
        value = await compute_fn()
        await self.aset(key, value, ttl=ttl)
        return value

    # ========================================
    # 工具方法
    # ========================================

    @staticmethod
    def compute_hash(obj: Any) -> str:
        """计算对象的 MD5 Hash 值，用于生成缓存键。

        Args:
            obj: 任意可序列化对象

        Returns:
            MD5 Hash 字符串
        """
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
            return str(hash(str(obj)))

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息。

        Returns:
            统计信息字典
        """
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

    # ========================================
    # 私有方法
    # ========================================

    def _resolve_ttl_minutes(self, ttl_seconds: Optional[int]) -> Optional[int]:
        """将 TTL 秒转换为分钟（BaseStore 单位）。

        Args:
            ttl_seconds: TTL（秒），None 使用默认值

        Returns:
            TTL（分钟），None 表示不设置
        """
        if ttl_seconds is not None:
            return max(1, ttl_seconds // 60)
        elif self.default_ttl is not None:
            return max(1, self.default_ttl // 60)
        return None


__all__ = [
    "CacheManager",
]
