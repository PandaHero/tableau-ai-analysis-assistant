# -*- coding: utf-8 -*-
"""
数据模型缓存封装类

使用 LangGraph SqliteStore 实现持久化缓存。

命名空间结构:
- ("data_model", datasource_luid) -> DataModel 对象（不含维度层级）

架构说明：
- DataModelCache 只缓存 DataModel 元数据（字段定义等）
- 维度层级由 DimensionHierarchyCacheStorage 管理，使用 field_hash 机制实现"仅字段变化时失效"
- 每次读取 DataModel 时，从 DimensionHierarchyCacheStorage 获取最新的 hierarchy
- 这样确保 hierarchy 的缓存失效严格遵循 field_hash 语义

使用示例:
    from tableau_assistant.src.infra.storage import get_langgraph_store, DataModelCache
    
    store = get_langgraph_store()
    cache = DataModelCache(store)
    
    data_model, is_cache_hit = await cache.get_or_load(datasource_luid, loader)
    cache.invalidate(datasource_luid)

Requirements: 2.1, 2.2, 2.3, 2.5
"""
import logging
import time
from typing import Optional, Dict, Any, Tuple

from langgraph.store.base import BaseStore
from tableau_assistant.src.infra.storage.data_model import DataModel
from tableau_assistant.src.infra.storage.data_model_loader import DataModelLoader

logger = logging.getLogger(__name__)

# 缓存命名空间
DATA_MODEL_NAMESPACE = ("data_model",)

# 缓存 TTL（分钟）
DEFAULT_TTL_MINUTES = 1440  # 24 小时（DataModel 元数据）


class DataModelCache:
    """
    数据模型缓存封装类
    
    使用 LangGraph SqliteStore 实现持久化缓存。
    支持单表和多表数据源。
    
    架构说明：
    - 只缓存 DataModel 元数据（不含维度层级）
    - 维度层级由 DimensionHierarchyCacheStorage 管理（有 field_hash 机制）
    - 每次读取时从 DimensionHierarchyCacheStorage 获取 hierarchy
    """
    
    def __init__(self, store: BaseStore):
        """
        初始化缓存
        
        Args:
            store: LangGraph SqliteStore 实例
        """
        self._store = store
    
    async def get_or_load(
        self,
        datasource_luid: str,
        loader: DataModelLoader,
    ) -> Tuple[DataModel, bool]:
        """
        获取或加载数据模型（缓存优先）
        
        流程：
        1. 尝试从缓存获取 DataModel 元数据
        2. 缓存命中时，从 DimensionHierarchyCacheStorage 获取 hierarchy
        3. 缓存未命中时，加载数据并推断 hierarchy
        
        Args:
            datasource_luid: 数据源 LUID
            loader: 数据模型加载器（用于缓存未命中时加载）
        
        Returns:
            (DataModel, is_cache_hit) 元组
        """
        start_time = time.time()
        
        # 1. 尝试从缓存获取 DataModel 元数据
        cached = self._get_from_cache(datasource_luid)
        if cached is not None and cached.field_count > 0:
            # 2. 从 DimensionHierarchyCacheStorage 获取 hierarchy
            hierarchy = await self._get_hierarchy_from_storage(datasource_luid, cached)
            if hierarchy:
                cached.dimension_hierarchy = hierarchy
            
            duration = (time.time() - start_time) * 1000
            logger.info(f"缓存命中: {datasource_luid}, {cached.field_count} 个字段, 耗时: {duration:.1f}ms")
            return cached, True
        
        # 3. 缓存未命中或缓存数据无效，加载数据
        if cached is not None and cached.field_count == 0:
            logger.warning(f"缓存数据无效（0个字段），重新加载: {datasource_luid}")
            self.invalidate(datasource_luid)
        else:
            logger.info(f"缓存未命中: {datasource_luid}, 开始加载...")
        
        data_model = await loader.load_data_model(datasource_luid)
        
        # 检查加载的数据是否有效
        if not data_model.fields or data_model.field_count == 0:
            logger.error(f"加载的数据模型为空: {datasource_luid}")
            # 返回空模型但不缓存
            return data_model, False
        
        # 4. 推断维度层级（如果需要）
        if not data_model.dimension_hierarchy:
            hierarchy = await loader.infer_dimension_hierarchy(data_model)
            data_model.dimension_hierarchy = hierarchy
        
        # 5. 存入缓存（只存 DataModel 元数据，不存 hierarchy）
        self._put_to_cache(datasource_luid, data_model)
        
        duration = (time.time() - start_time) * 1000
        logger.info(f"数据加载完成: {datasource_luid}, {data_model.field_count} 个字段, 耗时: {duration:.1f}ms")
        
        return data_model, False
    
    async def _get_hierarchy_from_storage(
        self,
        datasource_luid: str,
        data_model: DataModel,
    ) -> Optional[Dict[str, Any]]:
        """
        从 DimensionHierarchyCacheStorage 获取维度层级
        
        DimensionHierarchyCacheStorage 使用 field_hash 机制：
        - 如果 field_hash 匹配，返回缓存的 hierarchy
        - 如果 field_hash 不匹配，返回 None（需要重新推断）
        
        Args:
            datasource_luid: 数据源 LUID
            data_model: DataModel 对象（用于计算 field_hash）
        
        Returns:
            维度层级字典，如果缓存未命中或 field_hash 不匹配则返回 None
        """
        try:
            from tableau_assistant.src.agents.dimension_hierarchy.cache_storage import (
                DimensionHierarchyCacheStorage,
                compute_field_hash_metadata_only,
            )
            
            cache_storage = DimensionHierarchyCacheStorage()
            
            # 获取缓存
            cached = cache_storage.get_hierarchy_cache(datasource_luid)
            if not cached:
                return None
            
            # 验证 field_hash（关键：确保 hierarchy 与当前字段一致）
            dimension_fields = data_model.get_dimensions()
            if not dimension_fields:
                return None
            
            # 转换为 dict 格式计算 hash
            fields_for_hash = []
            for f in dimension_fields:
                fields_for_hash.append({
                    "field_name": f.name,
                    "field_caption": f.fieldCaption,
                    "data_type": f.dataType,
                })
            
            current_hash = compute_field_hash_metadata_only(fields_for_hash)
            cached_hash = cached.get("field_hash")
            
            if current_hash != cached_hash:
                logger.debug(f"field_hash 不匹配，需要重新推断: {datasource_luid}")
                return None
            
            # field_hash 匹配，返回缓存的 hierarchy
            hierarchy_data = cached.get("hierarchy_data", {})
            logger.debug(f"从 DimensionHierarchyCacheStorage 获取 hierarchy: {len(hierarchy_data)} 个字段")
            return hierarchy_data
            
        except Exception as e:
            logger.warning(f"获取 hierarchy 失败: {e}")
            return None

    def _get_from_cache(self, datasource_luid: str) -> Optional[DataModel]:
        """
        从缓存获取数据模型（不含维度层级）
        
        Args:
            datasource_luid: 数据源 LUID
        
        Returns:
            DataModel 对象，如果缓存未命中则返回 None
        """
        try:
            # 获取 data_model（不含 hierarchy）
            item = self._store.get(
                namespace=(*DATA_MODEL_NAMESPACE, datasource_luid),
                key="data"
            )
            if item is None:
                return None
            
            # 反序列化
            data_model = DataModel.model_validate(item.value)
            return data_model
            
        except Exception as e:
            logger.warning(f"缓存读取失败: {datasource_luid}, error={e}")
            return None
    
    def _put_to_cache(self, datasource_luid: str, data_model: DataModel) -> bool:
        """
        存入缓存（只存 DataModel 元数据，不存 hierarchy）
        
        Args:
            datasource_luid: 数据源 LUID
            data_model: DataModel 对象
        
        Returns:
            是否成功
        """
        # 检查数据模型是否有效（必须有字段）
        if not data_model.fields or data_model.field_count == 0:
            logger.warning(f"数据模型为空，跳过缓存: {datasource_luid}")
            return False
        
        try:
            # 存储 data_model（不含维度层级）
            # hierarchy 由 DimensionHierarchyCacheStorage 管理
            data_model_dict = data_model.model_dump(exclude={"dimension_hierarchy"})
            self._store.put(
                namespace=(*DATA_MODEL_NAMESPACE, datasource_luid),
                key="data",
                value=data_model_dict,
                ttl=DEFAULT_TTL_MINUTES,
            )
            
            logger.debug(f"缓存写入: {datasource_luid}, TTL: {DEFAULT_TTL_MINUTES}min (hierarchy 由 DimensionHierarchyCacheStorage 管理)")
            return True
            
        except Exception as e:
            logger.warning(f"缓存写入失败: {datasource_luid}, error={e}")
            return False
    
    def invalidate(self, datasource_luid: str) -> bool:
        """
        使缓存失效
        
        注意：只清除 DataModel 缓存，不清除 DimensionHierarchyCacheStorage 的缓存
        DimensionHierarchyCacheStorage 的缓存由 field_hash 机制自动管理
        
        Args:
            datasource_luid: 数据源 LUID
        
        Returns:
            是否成功
        """
        try:
            self._store.delete(
                namespace=(*DATA_MODEL_NAMESPACE, datasource_luid),
                key="data"
            )
            logger.info(f"缓存已失效: {datasource_luid}")
            return True
        except Exception as e:
            logger.warning(f"缓存失效失败: {datasource_luid}, error={e}")
            return False


__all__ = [
    "DataModelCache",
    "DATA_MODEL_NAMESPACE",
    "DEFAULT_TTL_MINUTES",
]
