# -*- coding: utf-8 -*-
"""
字段索引缓存封装类

使用 LangGraph SqliteStore 实现持久化缓存。

命名空间结构:
- ("field_index", datasource_luid) -> 索引数据（chunks, vectors, metadata_hash, field_names）

使用示例:
    from tableau_assistant.src.infra.storage import get_langgraph_store, FieldIndexCache
    
    store = get_langgraph_store()
    cache = FieldIndexCache(store)
    
    # 尝试从缓存加载
    cached_data = cache.get(datasource_luid)
    if cached_data:
        indexer.restore_from_cache(cached_data)
    else:
        indexer.index_fields(fields)
        cache.put(datasource_luid, indexer.export_for_cache())

Requirements: 6.3
"""
import logging
import time
from typing import Optional, Dict, Any, List

from langgraph.store.sqlite import SqliteStore

logger = logging.getLogger(__name__)

# 缓存命名空间
FIELD_INDEX_NAMESPACE = ("field_index",)

# 缓存 TTL（分钟）
DEFAULT_TTL_MINUTES = 1440  # 24 小时


class FieldIndexCache:
    """
    字段索引缓存封装类
    
    使用 LangGraph SqliteStore 实现持久化缓存。
    缓存内容包括：
    - metadata_hash: 元数据哈希（用于增量更新检测）
    - field_names: 字段名列表（保持顺序）
    - chunks: 字段分块数据
    - vectors: 向量数据
    
    命名空间结构:
    - ("field_index", datasource_luid) -> 索引数据
    """
    
    def __init__(self, store: SqliteStore):
        """
        初始化缓存
        
        Args:
            store: LangGraph SqliteStore 实例
        """
        self._store = store
    
    def get(self, datasource_luid: str) -> Optional[Dict[str, Any]]:
        """
        从缓存获取索引数据
        
        Args:
            datasource_luid: 数据源 LUID
        
        Returns:
            索引数据字典，如果缓存未命中则返回 None
            包含: metadata_hash, field_names, chunks, vectors
        """
        try:
            item = self._store.get(
                namespace=(*FIELD_INDEX_NAMESPACE, datasource_luid),
                key="data"
            )
            if item is None:
                logger.debug(f"字段索引缓存未命中: {datasource_luid}")
                return None
            
            logger.info(f"字段索引缓存命中: {datasource_luid}")
            return item.value
            
        except Exception as e:
            logger.warning(f"字段索引缓存读取失败: {datasource_luid}, error={e}")
            return None
    
    def put(
        self,
        datasource_luid: str,
        index_data: Dict[str, Any],
        ttl_minutes: int = DEFAULT_TTL_MINUTES
    ) -> bool:
        """
        存入缓存
        
        Args:
            datasource_luid: 数据源 LUID
            index_data: 索引数据字典
                - metadata_hash: 元数据哈希
                - field_names: 字段名列表
                - chunks: 字段分块数据
                - vectors: 向量数据
            ttl_minutes: 缓存过期时间（分钟）
        
        Returns:
            是否成功
        """
        if not index_data:
            logger.warning(f"索引数据为空，跳过缓存: {datasource_luid}")
            return False
        
        try:
            self._store.put(
                namespace=(*FIELD_INDEX_NAMESPACE, datasource_luid),
                key="data",
                value=index_data,
                ttl=ttl_minutes,
            )
            
            field_count = len(index_data.get("field_names", []))
            logger.info(f"字段索引缓存写入: {datasource_luid}, {field_count} 个字段, TTL: {ttl_minutes}min")
            return True
            
        except Exception as e:
            logger.warning(f"字段索引缓存写入失败: {datasource_luid}, error={e}")
            return False
    
    def invalidate(self, datasource_luid: str) -> bool:
        """
        使缓存失效
        
        Args:
            datasource_luid: 数据源 LUID
        
        Returns:
            是否成功
        """
        try:
            self._store.delete(
                namespace=(*FIELD_INDEX_NAMESPACE, datasource_luid),
                key="data"
            )
            logger.info(f"字段索引缓存已失效: {datasource_luid}")
            return True
        except Exception as e:
            logger.warning(f"字段索引缓存失效失败: {datasource_luid}, error={e}")
            return False
    
    def get_metadata_hash(self, datasource_luid: str) -> Optional[str]:
        """
        仅获取元数据哈希（用于快速检查是否需要更新）
        
        Args:
            datasource_luid: 数据源 LUID
        
        Returns:
            元数据哈希，如果缓存未命中则返回 None
        """
        cached = self.get(datasource_luid)
        if cached:
            return cached.get("metadata_hash")
        return None


__all__ = [
    "FieldIndexCache",
    "FIELD_INDEX_NAMESPACE",
    "DEFAULT_TTL_MINUTES",
]
