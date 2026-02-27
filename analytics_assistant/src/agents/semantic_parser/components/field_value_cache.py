# -*- coding: utf-8 -*-
"""
Field Value Cache - 字段值缓存

用于缓存字段的可能值，避免重复查询数据库。
支持筛选值验证时快速查找。

缓存策略:
- 最大缓存条目数: 100 个字段 (LRU 淘汰)
- 每个字段最多缓存: 1000 个值
- TTL: 1 小时
- 预热: 会话开始时加载低基数维度字段 (<500 唯一值)

并发安全:
- 使用分段锁（Sharded Lock）提升并发性能
- 16 个分片，每个分片独立的 OrderedDict + Lock
- 不同 key 的操作可以并行执行

配置来源：analytics_assistant/config/app.yaml -> semantic_parser.field_value_cache
"""

import asyncio
import logging
from collections import OrderedDict
from datetime import datetime, timedelta
from typing import Any, Callable, Coroutine, Optional

from analytics_assistant.src.infra.config import get_config
from analytics_assistant.src.core.schemas.data_model import DataModel

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
# 配置加载
# ═══════════════════════════════════════════════════════════════════════════

def _get_config() -> dict[str, Any]:
    """获取 field_value_cache 配置。"""
    try:
        config = get_config()
        return config.config.get("semantic_parser", {}).get("field_value_cache", {})
    except Exception as e:
        logger.warning(f"无法加载配置，使用默认值: {e}")
        return {}

# ═══════════════════════════════════════════════════════════════════════════
# 内部缓存条目（轻量级，仅用于内存缓存）
# ═══════════════════════════════════════════════════════════════════════════

class _CacheEntry:
    """内部缓存条目（轻量级）
    
    注意：这是内部实现细节，不对外暴露。
    对外 API 使用 schemas/cache.py 中的 CachedFieldValues。
    """
    __slots__ = ('values', 'expires_at', 'cached_at', 'cardinality')
    
    def __init__(
        self,
        values: list[str],
        expires_at: datetime,
        cached_at: datetime,
        cardinality: int = 0,
    ):
        self.values = values
        self.expires_at = expires_at
        self.cached_at = cached_at
        self.cardinality = cardinality
    
    @property
    def is_expired(self) -> bool:
        """检查是否过期"""
        return datetime.now() > self.expires_at

class FieldValueCache:
    """字段值缓存
    
    缓存每个字段的可能值，避免重复查询数据库。
    使用分段锁（Sharded Lock）提升并发性能。
    
    配置来源：app.yaml -> semantic_parser.field_value_cache
    """
    
    # 默认配置（作为 fallback）
    _DEFAULT_MAX_FIELDS = 100
    _DEFAULT_MAX_VALUES_PER_FIELD = 1000
    _DEFAULT_TTL = 3600
    _DEFAULT_SHARD_COUNT = 16
    _DEFAULT_PRELOAD_CARDINALITY_THRESHOLD = 500
    _DEFAULT_MAX_PRELOAD_FIELDS = 20
    
    # 需要跳过的数据类型
    SKIP_DATA_TYPES = {"date", "datetime", "timestamp"}
    
    def __init__(
        self,
        max_fields: Optional[int] = None,
        max_values_per_field: Optional[int] = None,
        default_ttl: Optional[int] = None,
        shard_count: Optional[int] = None,
    ):
        """初始化字段值缓存
        
        Args:
            max_fields: 最大缓存字段数（None 从配置读取）
            max_values_per_field: 每个字段最大缓存值数（None 从配置读取）
            default_ttl: 默认 TTL（秒）（None 从配置读取）
            shard_count: 分片数量（None 从配置读取）
        """
        # 从配置加载参数
        self._load_config(max_fields, max_values_per_field, default_ttl, shard_count)
        
        # 分段锁：每个分片有独立的缓存和锁
        self._shards: list[dict[str, Any]] = [
            {
                "cache": OrderedDict(),
                "lock": asyncio.Lock(),
            }
            for _ in range(self._shard_count)
        ]
    
    def _load_config(
        self,
        max_fields: Optional[int],
        max_values_per_field: Optional[int],
        default_ttl: Optional[int],
        shard_count: Optional[int],
    ) -> None:
        """从配置加载参数。"""
        config = _get_config()
        
        self._max_fields = (
            max_fields
            if max_fields is not None
            else config.get("max_fields", self._DEFAULT_MAX_FIELDS)
        )
        self._max_values_per_field = (
            max_values_per_field
            if max_values_per_field is not None
            else config.get("max_values_per_field", self._DEFAULT_MAX_VALUES_PER_FIELD)
        )
        self._default_ttl = (
            default_ttl
            if default_ttl is not None
            else config.get("default_ttl", self._DEFAULT_TTL)
        )
        self._shard_count = (
            shard_count
            if shard_count is not None
            else config.get("shard_count", self._DEFAULT_SHARD_COUNT)
        )
        self._preload_cardinality_threshold = config.get(
            "preload_cardinality_threshold", self._DEFAULT_PRELOAD_CARDINALITY_THRESHOLD
        )
        self._max_preload_fields = config.get(
            "max_preload_fields", self._DEFAULT_MAX_PRELOAD_FIELDS
        )
    
    def _make_key(self, field_name: str, datasource_luid: str) -> str:
        """生成缓存 key"""
        return f"{datasource_luid}:{field_name}"
    
    def _get_shard(self, key: str) -> dict[str, Any]:
        """根据 key 获取对应的分片
        
        使用 hash 函数将 key 映射到分片索引。
        """
        shard_idx = hash(key) % self._shard_count
        return self._shards[shard_idx]
    
    def _get_shard_index(self, key: str) -> int:
        """获取 key 对应的分片索引"""
        return hash(key) % self._shard_count
    
    def _get_total_size(self) -> int:
        """获取所有分片的总缓存条目数（用于 LRU 淘汰判断）"""
        return sum(len(shard["cache"]) for shard in self._shards)
    
    async def _evict_if_needed(self) -> int:
        """全局 LRU 淘汰：如果总数超过限制，淘汰最老的条目
        
        Returns:
            淘汰的条目数
        """
        evicted = 0
        
        while self._get_total_size() > self._max_fields:
            # 找到所有分片中最老的条目
            oldest_shard_idx = -1
            oldest_key = None
            oldest_time = None
            
            for idx, shard in enumerate(self._shards):
                cache: OrderedDict = shard["cache"]
                if not cache:
                    continue
                
                # OrderedDict 的第一个元素是最老的
                first_key = next(iter(cache))
                first_item: _CacheEntry = cache[first_key]
                
                if oldest_time is None or first_item.cached_at < oldest_time:
                    oldest_time = first_item.cached_at
                    oldest_key = first_key
                    oldest_shard_idx = idx
            
            if oldest_shard_idx < 0:
                break
            
            # 删除最老的条目
            shard = self._shards[oldest_shard_idx]
            async with shard["lock"]:
                cache: OrderedDict = shard["cache"]
                if oldest_key in cache:
                    del cache[oldest_key]
                    evicted += 1
        
        return evicted
    
    async def get(
        self,
        field_name: str,
        datasource_luid: str,
    ) -> Optional[list[str]]:
        """获取缓存的字段值（异步，线程安全）
        
        使用分段锁，不同 key 的读取可以并行执行。
        
        Args:
            field_name: 字段名
            datasource_luid: 数据源 LUID
            
        Returns:
            字段值列表，如果未缓存或已过期则返回 None
        """
        key = self._make_key(field_name, datasource_luid)
        shard = self._get_shard(key)
        
        async with shard["lock"]:
            cache: OrderedDict = shard["cache"]
            
            if key not in cache:
                return None
            
            cached: _CacheEntry = cache[key]
            
            # TTL 检查
            if cached.is_expired:
                del cache[key]
                return None
            
            # LRU: 移动到末尾（最近使用）
            cache.move_to_end(key)
            
            return cached.values
    
    async def set(
        self,
        field_name: str,
        datasource_luid: str,
        values: list[str],
        ttl: Optional[int] = None,
        cardinality: int = 0,
    ) -> None:
        """缓存字段值（异步，线程安全）
        
        使用分段锁，不同 key 的写入可以并行执行。
        LRU 淘汰在分片内部进行。
        
        自动处理:
        - 值列表截断（超过 MAX_VALUES_PER_FIELD）
        - LRU 淘汰（全局总数超过 MAX_FIELDS 时淘汰最老条目）
        
        Args:
            field_name: 字段名
            datasource_luid: 数据源 LUID
            values: 字段值列表
            ttl: TTL（秒），默认使用 DEFAULT_TTL
            cardinality: 字段基数
        """
        if ttl is None:
            ttl = self._default_ttl
        
        key = self._make_key(field_name, datasource_luid)
        shard = self._get_shard(key)
        
        # 截断过长的值列表
        if len(values) > self._max_values_per_field:
            values = values[:self._max_values_per_field]
        
        async with shard["lock"]:
            cache: OrderedDict = shard["cache"]
            
            # 如果 key 已存在，先删除（后面会重新添加到末尾）
            if key in cache:
                del cache[key]
            
            # 添加新条目
            cache[key] = _CacheEntry(
                values=values,
                expires_at=datetime.now() + timedelta(seconds=ttl),
                cached_at=datetime.now(),
                cardinality=cardinality,
            )
        
        # 全局 LRU 淘汰：如果总数超过限制，淘汰最老的条目
        await self._evict_if_needed()
    
    async def delete(
        self,
        field_name: str,
        datasource_luid: str,
    ) -> bool:
        """删除缓存的字段值
        
        Args:
            field_name: 字段名
            datasource_luid: 数据源 LUID
            
        Returns:
            是否成功删除
        """
        key = self._make_key(field_name, datasource_luid)
        shard = self._get_shard(key)
        
        async with shard["lock"]:
            cache: OrderedDict = shard["cache"]
            
            if key in cache:
                del cache[key]
                return True
            return False
    
    async def clear(self, datasource_luid: Optional[str] = None) -> int:
        """清空缓存
        
        Args:
            datasource_luid: 如果指定，只清空该数据源的缓存；否则清空所有
            
        Returns:
            清空的条目数
        """
        cleared_count = 0
        
        for shard in self._shards:
            async with shard["lock"]:
                cache: OrderedDict = shard["cache"]
                
                if datasource_luid is None:
                    # 清空所有
                    cleared_count += len(cache)
                    cache.clear()
                else:
                    # 只清空指定数据源的缓存
                    keys_to_delete = [
                        k for k in cache.keys()
                        if k.startswith(f"{datasource_luid}:")
                    ]
                    for k in keys_to_delete:
                        del cache[k]
                        cleared_count += 1
        
        return cleared_count
    
    async def preload_common_fields(
        self,
        data_model: DataModel,
        datasource_luid: str,
        fetch_field_values_func: Callable[[str], Coroutine[Any, Any, list[str]]],
    ) -> int:
        """预加载常用字段值（低基数维度字段）
        
        在会话开始时异步调用，提升后续验证性能。
        
        预热策略:
        - 只加载维度字段（DIMENSION role）
        - 只加载低基数字段（<500 唯一值）
        - 排除时间类型字段
        - 最多预加载 20 个字段
        
        Args:
            data_model: 数据模型
            datasource_luid: 数据源 LUID
            fetch_field_values_func: 获取字段值的异步函数
                签名: async def fetch(field_name: str) -> list[str]
                
        Returns:
            成功预加载的字段数
        """
        # 筛选候选字段
        candidates = []
        for f in data_model.fields:
            # 只加载维度字段
            if getattr(f, 'role', '').upper() != 'DIMENSION':
                continue
            
            # 排除时间类型字段
            data_type = getattr(f, 'data_type', '').lower()
            if data_type in self.SKIP_DATA_TYPES:
                continue
            
            # 只加载低基数字段
            cardinality = getattr(f, 'cardinality', 0)
            if cardinality > 0 and cardinality >= self._preload_cardinality_threshold:
                continue
            
            candidates.append(f)
            
            if len(candidates) >= self._max_preload_fields:
                break
        
        if not candidates:
            return 0
        
        # 并发加载
        async def load_field(field) -> bool:
            try:
                field_name = getattr(field, 'name', '') or getattr(field, 'field_name', '')
                if not field_name:
                    return False
                
                values = await fetch_field_values_func(field_name)
                if values:
                    cardinality = getattr(field, 'cardinality', len(values))
                    await self.set(
                        field_name=field_name,
                        datasource_luid=datasource_luid,
                        values=values,
                        cardinality=cardinality,
                    )
                    return True
            except Exception as e:
                logger.warning(f"预加载字段值失败: field={getattr(field, 'name', '?')}, error={e}")
            return False
        
        # 并发执行
        results = await asyncio.gather(
            *[load_field(f) for f in candidates],
            return_exceptions=True,
        )
        
        # 统计成功数
        success_count = sum(1 for r in results if r is True)
        return success_count
    
    def get_stats(self) -> dict[str, Any]:
        """获取缓存统计信息"""
        total_entries = 0
        total_values = 0
        shard_sizes = []
        
        for shard in self._shards:
            cache: OrderedDict = shard["cache"]
            shard_size = len(cache)
            shard_sizes.append(shard_size)
            total_entries += shard_size
            
            for cached in cache.values():
                total_values += len(cached.values)
        
        return {
            "total_entries": total_entries,
            "total_values": total_values,
            "shard_count": self._shard_count,
            "shard_sizes": shard_sizes,
            "max_fields": self._max_fields,
            "max_values_per_field": self._max_values_per_field,
            "default_ttl": self._default_ttl,
        }
    
    def get_cardinality(
        self,
        field_name: str,
        datasource_luid: str,
    ) -> Optional[int]:
        """获取缓存字段的基数（同步方法，用于快速检查）
        
        注意：这是同步方法，不获取锁，只用于快速检查。
        如果需要精确值，请使用 get() 方法。
        
        Args:
            field_name: 字段名
            datasource_luid: 数据源 LUID
            
        Returns:
            字段基数，如果未缓存则返回 None
        """
        key = self._make_key(field_name, datasource_luid)
        shard = self._get_shard(key)
        cache: OrderedDict = shard["cache"]
        
        if key not in cache:
            return None
        
        cached: _CacheEntry = cache[key]
        
        # TTL 检查（不删除，只返回 None）
        if cached.is_expired:
            return None
        
        return cached.cardinality
