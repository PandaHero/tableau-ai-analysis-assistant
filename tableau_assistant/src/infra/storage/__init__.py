# -*- coding: utf-8 -*-
"""
存储管理

统一使用 LangGraph SqliteStore 作为持久化存储。

主要组件：
- get_langgraph_store(): 获取 LangGraph SqliteStore 单例
- DataModelCache: 数据模型缓存封装类
- DataModelLoader: 数据模型加载器接口

使用示例：
    from tableau_assistant.src.infra.storage import (
        get_langgraph_store,
        DataModelCache,
        DataModelLoader,
    )
    from tableau_assistant.src.platforms.tableau import TableauDataModelLoader
    
    # 获取 store
    store = get_langgraph_store()
    
    # 直接使用 store 存储数据
    store.put(namespace=("user_preferences", user_id), key="data", value=prefs)
    item = store.get(namespace=("user_preferences", user_id), key="data")
    
    # 使用 DataModelCache（数据模型缓存）
    cache = DataModelCache(store)
    data_model, is_cache_hit = await cache.get_or_load(datasource_luid, loader)
"""
import logging

from tableau_assistant.src.infra.storage.langgraph_store import (
    get_langgraph_store,
    reset_langgraph_store,
    DEFAULT_DB_PATH,
    DEFAULT_TTL_MINUTES,
)
from tableau_assistant.src.infra.storage.data_model_cache import (
    DataModelCache,
    DATA_MODEL_NAMESPACE,
)
from tableau_assistant.src.infra.storage.field_index_cache import (
    FieldIndexCache,
    FIELD_INDEX_NAMESPACE,
)
from tableau_assistant.src.infra.storage.data_model_loader import (
    DataModelLoader,
)
from tableau_assistant.src.infra.storage.data_model import (
    DataModel,
    FieldMetadata,
    LogicalTable,
    LogicalTableRelationship,
)
from tableau_assistant.src.infra.storage.golden_queries import (
    GoldenQuery,
    GoldenQueryStore,
    get_golden_query_store,
)

logger = logging.getLogger(__name__)

__all__ = [
    # LangGraph Store
    "get_langgraph_store",
    "reset_langgraph_store",
    "DEFAULT_DB_PATH",
    "DEFAULT_TTL_MINUTES",
    # DataModelCache
    "DataModelCache",
    "DATA_MODEL_NAMESPACE",
    # FieldIndexCache
    "FieldIndexCache",
    "FIELD_INDEX_NAMESPACE",
    # DataModelLoader
    "DataModelLoader",
    # DataModel
    "DataModel",
    "FieldMetadata",
    "LogicalTable",
    "LogicalTableRelationship",
    # Golden Queries
    "GoldenQuery",
    "GoldenQueryStore",
    "get_golden_query_store",
]
