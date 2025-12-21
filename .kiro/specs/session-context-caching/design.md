# 设计文档：会话级上下文缓存

## 概述

本设计使用 LangGraph 框架提供的 `SqliteStore` 替代自定义的 `StoreManager`，实现数据模型和维度层级的持久化缓存。核心目标是避免每次请求都重新加载数据模型和推断维度层级。

## 架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                           API Layer                                  │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    chat.py / preload.py                      │   │
│  │  - 解析 datasource_luid                                      │   │
│  │  - 调用 WorkflowExecutor                                     │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      WorkflowExecutor                                │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  1. 获取全局 SqliteStore 实例                                │   │
│  │  2. 调用 DataModelCache.get_or_load()                       │   │
│  │  3. 创建 WorkflowContext（包含 data_model）                  │   │
│  │  4. 执行工作流                                               │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       DataModelCache                                 │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  - 封装 SqliteStore 的缓存操作                               │   │
│  │  - 命名空间: ("data_model", datasource_luid)                 │   │
│  │  - TTL: 24 小时                                              │   │
│  │  - 方法: get_or_load(), invalidate()                        │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                              │                                       │
│                              ▼                                       │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    LangGraph SqliteStore                     │   │
│  │  - 持久化到 data/langgraph_store.db                         │   │
│  │  - 支持 TTL 自动过期                                         │   │
│  │  - 支持命名空间层级                                          │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

## 组件和接口

### 1. 全局 SqliteStore 实例

```python
# tableau_assistant/src/infra/storage/langgraph_store.py

from langgraph.store.sqlite import SqliteStore
from typing import Optional
import sqlite3
import logging

logger = logging.getLogger(__name__)

_global_store: Optional[SqliteStore] = None
_store_lock = threading.Lock()

def get_langgraph_store(db_path: str = "data/langgraph_store.db") -> SqliteStore:
    """
    获取全局 LangGraph SqliteStore 实例（单例模式）
    
    Args:
        db_path: SQLite 数据库路径
    
    Returns:
        SqliteStore 实例
    """
    global _global_store
    
    if _global_store is None:
        with _store_lock:
            if _global_store is None:
                from pathlib import Path
                Path(db_path).parent.mkdir(parents=True, exist_ok=True)
                
                conn = sqlite3.connect(db_path, check_same_thread=False)
                _global_store = SqliteStore(
                    conn,
                    ttl_config={
                        "default_ttl": 1440,  # 24 小时（分钟）
                        "refresh_on_read": True,  # 读取时刷新 TTL
                        "sweep_interval_minutes": 60,  # 每小时清理过期数据
                    }
                )
                _global_store.setup()  # 运行迁移
                logger.info(f"LangGraph SqliteStore 初始化完成: {db_path}")
    
    return _global_store


def reset_langgraph_store():
    """重置全局实例（主要用于测试）"""
    global _global_store
    if _global_store:
        _global_store = None
```

### 2. DataModelCache 封装类

```python
# tableau_assistant/src/infra/storage/data_model_cache.py

from langgraph.store.sqlite import SqliteStore
from langgraph.store.base import Item
from typing import Optional, Dict, Any, Tuple
from tableau_assistant.src.core.models import DataModel
import logging
import time

logger = logging.getLogger(__name__)

# 缓存命名空间
DATA_MODEL_NAMESPACE = ("data_model",)
HIERARCHY_NAMESPACE = ("dimension_hierarchy",)

# 缓存 TTL（分钟）
DEFAULT_TTL_MINUTES = 1440  # 24 小时


class DataModelCache:
    """
    数据模型缓存封装类
    
    使用 LangGraph SqliteStore 实现持久化缓存。
    
    命名空间结构:
    - ("data_model", datasource_luid) -> DataModel 对象
    - ("dimension_hierarchy", datasource_luid) -> 维度层级字典
    """
    
    def __init__(self, store: SqliteStore):
        self._store = store
    
    async def get_or_load(
        self,
        datasource_luid: str,
        loader: "DataModelLoader",
    ) -> Tuple[DataModel, bool]:
        """
        获取或加载数据模型（缓存优先）
        
        Args:
            datasource_luid: 数据源 LUID
            loader: 数据模型加载器（用于缓存未命中时加载）
        
        Returns:
            (DataModel, is_cache_hit) 元组
        """
        start_time = time.time()
        
        # 1. 尝试从缓存获取
        cached = self._get_from_cache(datasource_luid)
        if cached is not None:
            duration = (time.time() - start_time) * 1000
            logger.info(f"缓存命中: {datasource_luid}, 耗时: {duration:.1f}ms")
            return cached, True
        
        # 2. 缓存未命中，加载数据
        logger.info(f"缓存未命中: {datasource_luid}, 开始加载...")
        
        data_model = await loader.load_data_model(datasource_luid)
        
        # 3. 推断维度层级（如果需要）
        if not data_model.dimension_hierarchy:
            hierarchy = await loader.infer_dimension_hierarchy(data_model)
            data_model.dimension_hierarchy = hierarchy
        
        # 4. 存入缓存
        self._put_to_cache(datasource_luid, data_model)
        
        duration = (time.time() - start_time) * 1000
        logger.info(f"缓存未命中: {datasource_luid}, 加载完成, 耗时: {duration:.1f}ms")
        
        return data_model, False
    
    def _get_from_cache(self, datasource_luid: str) -> Optional[DataModel]:
        """从缓存获取数据模型"""
        try:
            # 获取 data_model
            item = self._store.get(
                namespace=(*DATA_MODEL_NAMESPACE, datasource_luid),
                key="data"
            )
            if item is None:
                return None
            
            # 获取维度层级
            hierarchy_item = self._store.get(
                namespace=(*HIERARCHY_NAMESPACE, datasource_luid),
                key="data"
            )
            
            # 反序列化
            data_model = DataModel.model_validate(item.value)
            if hierarchy_item:
                data_model.dimension_hierarchy = hierarchy_item.value
            
            return data_model
            
        except Exception as e:
            logger.warning(f"缓存读取失败: {datasource_luid}, error={e}")
            return None
    
    def _put_to_cache(self, datasource_luid: str, data_model: DataModel) -> bool:
        """存入缓存"""
        try:
            # 存储 data_model（不含维度层级）
            data_model_dict = data_model.model_dump(exclude={"dimension_hierarchy"})
            self._store.put(
                namespace=(*DATA_MODEL_NAMESPACE, datasource_luid),
                key="data",
                value=data_model_dict,
                ttl=DEFAULT_TTL_MINUTES,
            )
            
            # 单独存储维度层级
            if data_model.dimension_hierarchy:
                self._store.put(
                    namespace=(*HIERARCHY_NAMESPACE, datasource_luid),
                    key="data",
                    value=data_model.dimension_hierarchy,
                    ttl=DEFAULT_TTL_MINUTES,
                )
            
            logger.debug(f"缓存写入: {datasource_luid}, TTL: {DEFAULT_TTL_MINUTES}min")
            return True
            
        except Exception as e:
            logger.warning(f"缓存写入失败: {datasource_luid}, error={e}")
            return False
    
    def invalidate(self, datasource_luid: str) -> bool:
        """使缓存失效"""
        try:
            self._store.delete(
                namespace=(*DATA_MODEL_NAMESPACE, datasource_luid),
                key="data"
            )
            self._store.delete(
                namespace=(*HIERARCHY_NAMESPACE, datasource_luid),
                key="data"
            )
            logger.info(f"缓存已失效: {datasource_luid}")
            return True
        except Exception as e:
            logger.warning(f"缓存失效失败: {datasource_luid}, error={e}")
            return False
```

### 3. DataModelLoader 接口

```python
# tableau_assistant/src/infra/storage/data_model_loader.py

from abc import ABC, abstractmethod
from typing import Dict, Any
from tableau_assistant.src.core.models import DataModel


class DataModelLoader(ABC):
    """数据模型加载器接口"""
    
    @abstractmethod
    async def load_data_model(self, datasource_luid: str) -> DataModel:
        """从 Tableau API 加载数据模型"""
        pass
    
    @abstractmethod
    async def infer_dimension_hierarchy(self, data_model: DataModel) -> Dict[str, Any]:
        """推断维度层级"""
        pass


class TableauDataModelLoader(DataModelLoader):
    """Tableau 数据模型加载器实现"""
    
    def __init__(self, auth_ctx: "TableauAuthContext"):
        self._auth = auth_ctx
    
    async def load_data_model(self, datasource_luid: str) -> DataModel:
        """从 Tableau API 加载数据模型"""
        from tableau_assistant.src.platforms.tableau.metadata import get_datasource_metadata
        from tableau_assistant.src.core.models import DataModel, FieldMetadata, LogicalTable, LogicalTableRelationship
        
        raw = await get_datasource_metadata(
            datasource_luid=datasource_luid,
            tableau_token=self._auth.api_key,
            tableau_site=self._auth.site,
            tableau_domain=self._auth.domain,
        )
        
        fields = [FieldMetadata(**f) for f in raw.get("fields", [])]
        
        # 解析逻辑表结构（支持单表和多表场景）
        logical_tables = []
        logical_table_relationships = []
        raw_data_model = raw.get("data_model")
        if raw_data_model and isinstance(raw_data_model, dict):
            for t in raw_data_model.get("logicalTables", []):
                logical_tables.append(LogicalTable(
                    logicalTableId=t.get("logicalTableId", ""),
                    caption=t.get("caption", "")
                ))
            for r in raw_data_model.get("logicalTableRelationships", []):
                logical_table_relationships.append(LogicalTableRelationship(
                    fromLogicalTableId=r.get("fromLogicalTableId", ""),
                    toLogicalTableId=r.get("toLogicalTableId", "")
                ))
        
        return DataModel(
            datasource_luid=datasource_luid,
            datasource_name=raw.get("datasource_name", "Unknown"),
            datasource_description=raw.get("datasource_description"),
            datasource_owner=raw.get("datasource_owner"),
            logical_tables=logical_tables,
            logical_table_relationships=logical_table_relationships,
            fields=fields,
            field_count=len(fields),
            raw_response=raw.get("raw_response"),
        )
    
    async def infer_dimension_hierarchy(self, data_model: DataModel) -> Dict[str, Any]:
        """推断维度层级"""
        from tableau_assistant.src.agents.dimension_hierarchy.node import dimension_hierarchy_node
        import logging
        import time
        
        logger = logging.getLogger(__name__)
        start_time = time.time()
        
        try:
            result = await dimension_hierarchy_node(
                data_model=data_model,
                datasource_luid=data_model.datasource_luid,
            )
            
            hierarchy_dict = {}
            for field_name, attrs in result.dimension_hierarchy.items():
                hierarchy_dict[field_name] = attrs.model_dump()
            
            duration = (time.time() - start_time) * 1000
            logger.info(f"维度层级推断完成: {len(hierarchy_dict)} 个字段, 耗时: {duration:.1f}ms")
            
            return hierarchy_dict
            
        except Exception as e:
            logger.error(f"维度层级推断失败: {e}")
            return {}
```

### 4. 修改 WorkflowExecutor

```python
# tableau_assistant/src/orchestration/workflow/executor.py (修改)

class WorkflowExecutor:
    def __init__(self, ...):
        # ... 现有代码 ...
        
        # 使用 LangGraph SqliteStore
        from tableau_assistant.src.infra.storage.langgraph_store import get_langgraph_store
        self._langgraph_store = get_langgraph_store()
        
        # 创建 DataModelCache
        from tableau_assistant.src.infra.storage.data_model_cache import DataModelCache
        self._data_model_cache = DataModelCache(self._langgraph_store)
    
    async def run(self, question: str, thread_id: str = None, ...) -> WorkflowResult:
        # ... 认证代码 ...
        
        # 使用 DataModelCache 获取或加载数据模型
        from tableau_assistant.src.infra.storage.data_model_loader import TableauDataModelLoader
        loader = TableauDataModelLoader(auth_ctx)
        
        data_model, is_cache_hit = await self._data_model_cache.get_or_load(
            datasource_luid=ds_luid,
            loader=loader,
        )
        
        # 创建 WorkflowContext（data_model 已加载）
        ctx = WorkflowContext(
            auth=auth_ctx,
            store=self._store,  # 保留旧的 StoreManager 用于其他用途
            datasource_luid=ds_luid,
            data_model=data_model,  # 直接传入已加载的 data_model
            # ...
        )
        
        # 不再调用 ctx.ensure_metadata_loaded()
        # data_model 已经通过 DataModelCache 加载
        
        # ... 执行工作流 ...
```

## 数据模型

### SqliteStore 命名空间结构

```
langgraph_store.db
├── store (表)
│   ├── ("data_model", "ds_12345") / "data" -> DataModel JSON
│   ├── ("data_model", "ds_67890") / "data" -> DataModel JSON
│   ├── ("dimension_hierarchy", "ds_12345") / "data" -> Hierarchy JSON
│   └── ("dimension_hierarchy", "ds_67890") / "data" -> Hierarchy JSON
```

### 缓存数据结构

```python
# DataModel 缓存值
{
    "datasource_luid": "ds_12345",
    "datasource_name": "示例数据源",
    "datasource_description": "...",
    "datasource_owner": "...",
    "logical_tables": [...],  # 逻辑表列表（单表场景为空列表）
    "logical_table_relationships": [...],  # 表关系（单表场景为空列表）
    "fields": [...],
    "field_count": 50,
    # 注意：dimension_hierarchy 单独存储
}

# Dimension Hierarchy 缓存值
{
    "产品类别": {
        "is_dimension": true,
        "hierarchy_level": 1,
        "parent_field": null,
        "child_fields": ["产品子类别"],
        ...
    },
    "产品子类别": {
        "is_dimension": true,
        "hierarchy_level": 2,
        "parent_field": "产品类别",
        ...
    },
    ...
}
```



## 正确性属性

*属性是一种特征或行为，应该在系统的所有有效执行中保持为真——本质上是关于系统应该做什么的形式化陈述。属性是人类可读规范和机器可验证正确性保证之间的桥梁。*

### Property 1: 缓存存储命名空间一致性

*对于任意* datasource_luid，存储到缓存的数据应该位于 `("data_model", datasource_luid)` 命名空间下，且可以通过相同的命名空间检索到。

**验证: 需求 1.4**

### Property 2: 缓存命中时跳过 API 调用

*对于任意* 有效的缓存数据（未过期），调用 `get_or_load()` 应该返回缓存数据且不触发 Tableau API 调用。

**验证: 需求 2.2, 3.2, 3.3**

### Property 3: 缓存写入 TTL 一致性

*对于任意* 新加载的 DataModel，存入缓存时应该设置 TTL=24h（1440 分钟），且在 TTL 过期前可以检索到。

**验证: 需求 2.5**

### Property 4: TTL 过期后重新加载

*对于任意* 已过期的缓存数据，调用 `get_or_load()` 应该触发重新加载（调用 API 和推断）。

**验证: 需求 4.1**

### Property 5: 缓存读写往返一致性

*对于任意* 有效的 DataModel 对象，存入缓存后再读取应该得到等价的对象（字段值相同）。

**验证: 需求 2.5, 2.6**

## 错误处理

| 错误场景 | 处理方式 | 日志级别 |
|---------|---------|---------|
| SqliteStore 读取失败 | 回退到直接 API 加载 | WARNING |
| SqliteStore 写入失败 | 继续处理请求，不阻塞 | WARNING |
| 维度层级推断失败 | 使用空层级继续执行 | ERROR |
| Tableau API 调用失败 | 抛出异常，返回错误响应 | ERROR |

## 测试策略

### 单元测试

- `DataModelCache.get_or_load()` 缓存命中场景
- `DataModelCache.get_or_load()` 缓存未命中场景
- `DataModelCache.invalidate()` 缓存失效
- `get_langgraph_store()` 单例模式

### 属性测试

使用 Hypothesis (Python) 进行属性测试：

1. **Property 1**: 生成随机 datasource_luid，验证命名空间结构
2. **Property 2**: 预填充缓存，验证不触发 API 调用
3. **Property 3**: 存入数据，验证 TTL 设置
4. **Property 4**: 模拟 TTL 过期，验证重新加载
5. **Property 5**: 生成随机 DataModel，验证读写往返一致性

### 集成测试

- 完整请求流程（缓存未命中 → 加载 → 缓存 → 后续请求命中）
- 多数据源并发请求
- 服务重启后缓存恢复

## 迁移计划

### 阶段 1：添加新组件

1. 创建 `langgraph_store.py` - 全局 SqliteStore 实例
2. 创建 `data_model_cache.py` - DataModelCache 封装类
3. 创建 `data_model_loader.py` - DataModelLoader 接口

### 阶段 2：修改 WorkflowExecutor

1. 在 `WorkflowExecutor.__init__()` 中初始化 DataModelCache
2. 在 `WorkflowExecutor.run()` 中使用 DataModelCache.get_or_load()
3. 移除 `ctx.ensure_metadata_loaded()` 调用

### 阶段 3：清理旧代码

1. 删除 `StoreManager` 中的 metadata 相关方法
2. 删除 `PreloadService` 类及相关文件
3. 删除 `WorkflowContext.ensure_metadata_loaded()` 方法
4. 删除 `WorkflowContext._load_data_model_from_cache()` 等私有方法
5. 更新所有引用旧方法的代码
