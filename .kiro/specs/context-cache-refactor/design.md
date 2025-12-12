# 上下文和缓存架构重构设计

## Overview

本设计旨在统一项目的上下文管理和缓存机制，充分利用 LangGraph 的原生特性，消除重复代码。

## 当前架构问题分析

### 问题 1: 认证获取方式混乱

```
WorkflowExecutor.run()
├── get_tableau_auth_async() → 内存缓存 (_ctx_cache)
└── create_config_with_auth() → RunnableConfig

Execute Node
└── ensure_valid_auth_async(config) ✅ 正确使用 config

DataModelManager.get_data_model_async()
└── get_tableau_config() → 又调用 get_tableau_auth() ❌ 重复
    └── 没有使用 RunnableConfig，自己又获取一次
```

### 问题 2: 依赖注入通过全局变量

```python
# metadata_tool.py
_data_model_manager: Optional[DataModelManager] = None  # 全局变量

# 需要手动调用 set_metadata_manager() 注入
# 但这个函数在哪里调用？工作流启动时没有调用！
```

### 问题 3: 组件职责不清

```
StoreManager (SQLite)     → 业务数据持久化
内存缓存 (_ctx_cache)     → 认证 token 缓存
RunnableConfig            → 配置传递
State                     → 节点间数据传递
ToolRegistry              → 工具注册（但依赖注入不完整）
```

## Architecture

### 目标架构：完整的组件协作图

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              LangGraph Workflow 完整架构                                 │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                         │
│  ┌───────────────────────────────────────────────────────────────────────────────────┐ │
│  │                         WorkflowExecutor.run() - 入口点                            │ │
│  │                                                                                    │ │
│  │  1. 初始化依赖                                                                     │ │
│  │     ├── get_tableau_auth_async() → TableauAuthContext                             │ │
│  │     ├── get_store_manager() → StoreManager (SQLite)                               │ │
│  │     └── create_workflow_context() → WorkflowContext                               │ │
│  │                                                                                    │ │
│  │  2. 创建统一配置                                                                   │ │
│  │     └── RunnableConfig = {                                                        │ │
│  │           "configurable": {                                                        │ │
│  │             "thread_id": str,                                                      │ │
│  │             "workflow_context": WorkflowContext,  // 包含所有依赖                  │ │
│  │           }                                                                        │ │
│  │         }                                                                          │ │
│  │                                                                                    │ │
│  │  3. 执行工作流                                                                     │ │
│  │     └── workflow.ainvoke(state, config)                                           │ │
│  └───────────────────────────────────────────────────────────────────────────────────┘ │
│                                           │                                             │
│                                           ▼                                             │
│  ┌───────────────────────────────────────────────────────────────────────────────────┐ │
│  │                         WorkflowContext (Pydantic 模型)                            │ │
│  │                         统一的依赖容器，通过 RunnableConfig 传递                    │ │
│  │                                                                                    │ │
│  │  class WorkflowContext(BaseModel):                                                │ │
│  │      # 认证                                                                        │ │
│  │      auth: TableauAuthContext                                                      │ │
│  │                                                                                    │ │
│  │      # 存储                                                                        │ │
│  │      store: StoreManager  # SQLite 持久化                                         │ │
│  │                                                                                    │ │
│  │      # 数据源配置                                                                  │ │
│  │      datasource_luid: str                                                          │ │
│  │                                                                                    │ │
│  │      # 工作流配置                                                                  │ │
│  │      max_replan_rounds: int = 3                                                    │ │
│  │      user_id: Optional[str] = None                                                │ │
│  └───────────────────────────────────────────────────────────────────────────────────┘ │
│                                           │                                             │
│              ┌────────────────────────────┼────────────────────────────┐               │
│              │                            │                            │               │
│              ▼                            ▼                            ▼               │
│  ┌─────────────────────┐    ┌─────────────────────┐    ┌─────────────────────┐       │
│  │   Middleware Stack  │    │       Nodes         │    │       Tools         │       │
│  │                     │    │                     │    │                     │       │
│  │ ┌─────────────────┐ │    │ ┌─────────────────┐ │    │ ┌─────────────────┐ │       │
│  │ │ TodoList        │ │    │ │ Understanding   │ │    │ │ get_metadata    │ │       │
│  │ │ Middleware      │ │    │ │ Node            │ │    │ │                 │ │       │
│  │ └─────────────────┘ │    │ │                 │ │    │ │ 通过 ToolRuntime│ │       │
│  │ ┌─────────────────┐ │    │ │ 调用 Tools      │◄┼────┼─│ 访问 config     │ │       │
│  │ │ Summarization   │ │    │ └─────────────────┘ │    │ └─────────────────┘ │       │
│  │ │ Middleware      │ │    │ ┌─────────────────┐ │    │ ┌─────────────────┐ │       │
│  │ └─────────────────┘ │    │ │ FieldMapper     │ │    │ │ get_data_model  │ │       │
│  │ ┌─────────────────┐ │    │ │ Node            │ │    │ │                 │ │       │
│  │ │ ModelRetry      │ │    │ │                 │ │    │ │ 通过 ToolRuntime│ │       │
│  │ │ Middleware      │ │    │ │ 使用 Store 缓存 │◄┼────┼─│ 访问 store      │ │       │
│  │ └─────────────────┘ │    │ └─────────────────┘ │    │ └─────────────────┘ │       │
│  │ ┌─────────────────┐ │    │ ┌─────────────────┐ │    │ ┌─────────────────┐ │       │
│  │ │ ToolRetry       │ │    │ │ Execute Node    │ │    │ │ date_tools      │ │       │
│  │ │ Middleware      │ │    │ │                 │ │    │ │                 │ │       │
│  │ └─────────────────┘ │    │ │ 使用 auth 调用  │ │    │ │ 无需外部依赖    │ │       │
│  │ ┌─────────────────┐ │    │ │ VizQL API       │ │    │ └─────────────────┘ │       │
│  │ │ Filesystem      │ │    │ └─────────────────┘ │    │                     │       │
│  │ │ Middleware      │ │    │ ┌─────────────────┐ │    │                     │       │
│  │ │                 │ │    │ │ Insight Node    │ │    │                     │       │
│  │ │ 提供 read_file  │ │    │ └─────────────────┘ │    │                     │       │
│  │ │ write_file 等   │ │    │ ┌─────────────────┐ │    │                     │       │
│  │ └─────────────────┘ │    │ │ Replanner Node  │ │    │                     │       │
│  │ ┌─────────────────┐ │    │ └─────────────────┘ │    │                     │       │
│  │ │ PatchToolCalls  │ │    │                     │    │                     │       │
│  │ │ Middleware      │ │    │                     │    │                     │       │
│  │ └─────────────────┘ │    │                     │    │                     │       │
│  └─────────────────────┘    └─────────────────────┘    └─────────────────────┘       │
│                                                                                         │
└─────────────────────────────────────────────────────────────────────────────────────────┘
                                           │
                                           ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              持久化层 (StoreManager - SQLite)                            │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                         │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐   │
│  │    metadata     │  │   dimension_    │  │   data_model    │  │ user_preferences│   │
│  │    (1小时)      │  │   hierarchy     │  │    (24小时)     │  │    (永久)       │   │
│  │                 │  │   (24小时)      │  │                 │  │                 │   │
│  │ 字段元数据      │  │ 维度层级结构    │  │ 逻辑表关系      │  │ 用户偏好设置    │   │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  └─────────────────┘   │
│                                                                                         │
│  ┌─────────────────┐  ┌─────────────────┐                                              │
│  │ question_history│  │anomaly_knowledge│                                              │
│  │    (永久)       │  │    (永久)       │                                              │
│  │                 │  │                 │                                              │
│  │ 历史问题记录    │  │ 异常知识库      │                                              │
│  └─────────────────┘  └─────────────────┘                                              │
│                                                                                         │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

### 数据流分层

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                    数据流分层                                            │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                         │
│  Layer 1: State (节点间传递的可变数据)                                                   │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐   │
│  │  VizQLState:                                                                     │   │
│  │  # 工作流数据                                                                    │   │
│  │  - question: str                    # 用户问题                                   │   │
│  │  - semantic_query: SemanticQuery    # 语义查询                                   │   │
│  │  - mapped_query: MappedQuery        # 映射后的查询                               │   │
│  │  - vizql_query: VizQLQuery          # VizQL 查询                                 │   │
│  │  - query_result: ExecuteResult      # 查询结果                                   │   │
│  │  - insights: List[Insight]          # 洞察列表                                   │   │
│  │  - replan_decision: ReplanDecision  # 重规划决策                                 │   │
│  │  - errors: List[dict]               # 错误列表                                   │   │
│  │                                                                                  │   │
│  │  # 数据模型（在工作流启动时加载，所有节点共享）                                   │   │
│  │  - metadata: Metadata               # 完整数据模型（字段、维度层级、逻辑表）      │   │
│  │  - dimension_hierarchy: Dict        # 维度层级（Replanner 使用）                 │   │
│  │  - data_insight_profile: Dict       # 数据洞察画像（Replanner 使用）             │   │
│  │  - current_dimensions: List[str]    # 当前已分析的维度                           │   │
│  └─────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                         │
│  Layer 2: RunnableConfig (不可变配置，所有节点/工具可访问)                               │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐   │
│  │  config["configurable"]:                                                         │   │
│  │  - thread_id: str                   # 会话 ID                                    │   │
│  │  - workflow_context: WorkflowContext # 统一依赖容器                              │   │
│  │    ├── auth: TableauAuthContext     # 认证上下文                                 │   │
│  │    ├── store: StoreManager          # 持久化存储                                 │   │
│  │    ├── datasource_luid: str         # 数据源 ID                                  │   │
│  │    ├── metadata: Metadata           # 完整数据模型（备份，与 State 同步）        │   │
│  │    └── max_replan_rounds: int       # 最大重规划轮数                             │   │
│  └─────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                         │
│  Layer 3: Store (跨会话持久化)                                                          │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐   │
│  │  StoreManager (SQLite):                                                          │   │
│  │  - metadata: 元数据缓存 (1小时 TTL)                                              │   │
│  │  - dimension_hierarchy: 维度层级 (24小时 TTL)                                    │   │
│  │  - data_model: 数据模型 (24小时 TTL)                                             │   │
│  │  - user_preferences: 用户偏好 (永久)                                             │   │
│  │  - question_history: 问题历史 (永久)                                             │   │
│  │  - anomaly_knowledge: 异常知识库 (永久)                                          │   │
│  └─────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                         │
│  Layer 4: Checkpointer (会话状态持久化)                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐   │
│  │  SqliteSaver / MemorySaver:                                                      │   │
│  │  - 保存工作流执行状态                                                            │   │
│  │  - 支持断点恢复                                                                  │   │
│  │  - 支持会话历史查询                                                              │   │
│  └─────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                         │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

### 各节点如何使用数据模型

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              节点与数据模型的关系                                        │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                         │
│  Understanding Node                                                                     │
│  ├── 输入: state.metadata (完整数据模型)                                               │
│  ├── 使用: fields (字段元数据) 用于理解用户问题                                        │
│  └── 输出: semantic_query                                                              │
│                                                                                         │
│  FieldMapper Node                                                                       │
│  ├── 输入: state.metadata.fields                                                       │
│  ├── 使用: 字段名称、类型、样本值 用于语义匹配                                         │
│  └── 输出: mapped_query                                                                │
│                                                                                         │
│  QueryBuilder Node                                                                      │
│  ├── 输入: mapped_query                                                                │
│  ├── 使用: 纯代码转换，不需要数据模型                                                  │
│  └── 输出: vizql_query                                                                 │
│                                                                                         │
│  Execute Node                                                                           │
│  ├── 输入: vizql_query, ctx.auth (认证)                                                │
│  ├── 使用: 调用 VizQL API                                                              │
│  └── 输出: query_result                                                                │
│                                                                                         │
│  Insight Node                                                                           │
│  ├── 输入: query_result                                                                │
│  ├── 使用: 分析数据，生成洞察                                                          │
│  └── 输出: insights, data_insight_profile                                              │
│                                                                                         │
│  Replanner Node                                                                         │
│  ├── 输入: insights, state.dimension_hierarchy, state.data_insight_profile             │
│  ├── 使用: 维度层级 用于生成探索问题                                                   │
│  └── 输出: replan_decision, exploration_questions                                      │
│                                                                                         │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

## Components and Interfaces

### 1. WorkflowContext - 统一依赖容器

```python
# tableau_assistant/src/workflow/context.py

from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
from tableau_assistant.src.bi_platforms.tableau import TableauAuthContext
from tableau_assistant.src.capabilities.storage import StoreManager
from tableau_assistant.src.models.metadata import Metadata

class WorkflowContext(BaseModel):
    """
    工作流上下文 - 统一的依赖容器
    
    通过 RunnableConfig["configurable"]["workflow_context"] 传递给所有节点和工具。
    这是唯一的依赖注入点，消除全局变量和重复获取。
    
    数据模型说明：
    - metadata: 完整的数据模型，包含：
      - fields: 字段元数据列表（FieldMetadata）
      - dimension_hierarchy: 维度层级结构
      - data_model: 逻辑表和表关系（DataModel）
      - datasource_name, datasource_description 等
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    # 认证
    auth: TableauAuthContext = Field(description="Tableau 认证上下文")
    
    # 存储
    store: StoreManager = Field(description="持久化存储管理器")
    
    # 数据源配置
    datasource_luid: str = Field(description="数据源 LUID")
    
    # 数据模型（完整的 Tableau 数据模型，包含元数据、维度层级、逻辑表关系）
    # 在工作流启动时加载，所有节点共享
    metadata: Optional[Metadata] = Field(default=None, description="完整的数据模型")
    
    # 工作流配置
    max_replan_rounds: int = Field(default=3, description="最大重规划轮数")
    user_id: Optional[str] = Field(default=None, description="用户 ID")
    
    def is_auth_valid(self) -> bool:
        """检查认证是否有效"""
        return not self.auth.is_expired()
    
    async def refresh_auth_if_needed(self) -> "WorkflowContext":
        """如果认证过期，刷新并返回新的上下文"""
        if self.is_auth_valid():
            return self
        
        from tableau_assistant.src.bi_platforms.tableau import get_tableau_auth_async
        new_auth = await get_tableau_auth_async(force_refresh=True)
        
        return WorkflowContext(
            auth=new_auth,
            store=self.store,
            datasource_luid=self.datasource_luid,
            metadata=self.metadata,
            max_replan_rounds=self.max_replan_rounds,
            user_id=self.user_id,
        )
    
    async def ensure_metadata_loaded(self) -> "WorkflowContext":
        """
        确保数据模型已加载（包含维度层级推断）
        
        流程:
        1. 检查 store 缓存（metadata 命名空间，1小时 TTL）
        2. 如果缓存命中:
           a. 检查 dimension_hierarchy 缓存（24小时 TTL）
           b. 如果维度层级缓存存在，直接返回
           c. 如果维度层级缓存不存在，调用 dimension_hierarchy_node Agent 推断
        3. 如果缓存未命中:
           a. 调用 Tableau Metadata API 获取字段元数据
           b. 调用 dimension_hierarchy_node Agent 推断维度层级
           c. 缓存 metadata（1小时）和 dimension_hierarchy（24小时）
        """
        if self.metadata is not None:
            return self
        
        # 使用 DataModelManager 获取完整数据模型（包含维度层级推断）
        from tableau_assistant.src.capabilities.data_model.manager import DataModelManager
        
        # 创建临时 manager（不再需要 Runtime 对象）
        manager = DataModelManager()
        
        # get_data_model_async 会:
        # 1. 检查缓存
        # 2. 如果需要，调用 Tableau API
        # 3. 如果需要，调用 dimension_hierarchy_node Agent 推断维度层级
        # 4. 缓存结果
        metadata = await manager.get_data_model_async(
            ctx=self,  # 传递 WorkflowContext
            use_cache=True,
            enhance=True,  # 启用维度层级推断
        )
        
        return WorkflowContext(
            auth=self.auth,
            store=self.store,
            datasource_luid=self.datasource_luid,
            metadata=metadata,
            max_replan_rounds=self.max_replan_rounds,
            user_id=self.user_id,
        )
```

### 数据模型结构

```python
# Metadata 包含完整的 Tableau 数据模型

class Metadata(BaseModel):
    """完整的数据模型"""
    
    # 数据源信息
    datasource_luid: str
    datasource_name: str
    datasource_description: Optional[str] = None
    datasource_owner: Optional[str] = None
    
    # 字段元数据
    fields: List[FieldMetadata]  # 包含 name, role, dataType, category, level 等
    field_count: int
    
    # 维度层级（由 DimensionHierarchy Agent 推断）
    dimension_hierarchy: Optional[Dict[str, Any]] = None
    
    # 逻辑表和关系（来自 VizQL API）
    data_model: Optional[DataModel] = None
    
    # 原始响应（调试用）
    raw_response: Optional[Dict[str, Any]] = None

class FieldMetadata(BaseModel):
    """字段元数据"""
    name: str
    fieldCaption: str
    role: str  # DIMENSION 或 MEASURE
    dataType: str  # STRING, INTEGER, REAL, DATE, DATETIME
    
    # 维度层级信息（由推断填充）
    category: Optional[str] = None  # time, geography, product 等
    category_detail: Optional[str] = None
    level: Optional[int] = None
    granularity: Optional[str] = None
    parent_dimension: Optional[str] = None
    child_dimension: Optional[str] = None
    
    # 样本值
    sample_values: Optional[List[str]] = None

class DataModel(BaseModel):
    """逻辑表和关系"""
    logicalTables: List[LogicalTable]
    logicalTableRelationships: List[LogicalTableRelationship]
```

### 2. Config 创建和访问函数

```python
# tableau_assistant/src/workflow/context.py

from langgraph.types import RunnableConfig

def create_workflow_config(
    thread_id: str,
    context: WorkflowContext,
) -> RunnableConfig:
    """
    创建工作流配置
    
    所有节点和工具都可以通过 config["configurable"]["workflow_context"] 访问上下文。
    """
    return {
        "configurable": {
            "thread_id": thread_id,
            "workflow_context": context,
        }
    }

def get_context(config: Optional[RunnableConfig]) -> Optional[WorkflowContext]:
    """从 RunnableConfig 获取 WorkflowContext"""
    if config is None:
        return None
    return config.get("configurable", {}).get("workflow_context")

def get_context_or_raise(config: Optional[RunnableConfig]) -> WorkflowContext:
    """从 RunnableConfig 获取 WorkflowContext，如果不存在则抛出异常"""
    ctx = get_context(config)
    if ctx is None:
        raise ValueError("WorkflowContext not found in config")
    return ctx
```

### 3. 节点使用示例

```python
# 所有节点统一使用 get_context() 获取依赖

async def execute_node(state: VizQLState, config: RunnableConfig) -> dict:
    # 获取上下文
    ctx = get_context_or_raise(config)
    
    # 如果认证过期，自动刷新
    if not ctx.is_auth_valid():
        ctx = await ctx.refresh_auth_if_needed()
    
    # 使用认证
    api_key = ctx.auth.api_key
    site = ctx.auth.site
    
    # 使用存储
    cached_data = ctx.store.get_metadata(ctx.datasource_luid)
    
    # 执行查询...
```

### 4. Tool 使用示例 (通过 ToolRuntime)

```python
# LangGraph 的 Tool 可以通过 ToolRuntime 访问 config

from langchain_core.tools import tool
from langchain.tools import ToolRuntime

@tool
async def get_metadata(
    runtime: ToolRuntime,  # LangGraph 自动注入
    use_cache: bool = True,
) -> str:
    """获取数据源元数据"""
    # 从 runtime 获取 config
    config = runtime.config
    ctx = get_context_or_raise(config)
    
    # 使用存储
    if use_cache:
        cached = ctx.store.get_metadata(ctx.datasource_luid)
        if cached:
            return format_metadata(cached)
    
    # 使用认证获取新数据
    metadata = await fetch_metadata(
        datasource_luid=ctx.datasource_luid,
        api_key=ctx.auth.api_key,
        domain=ctx.auth.domain,
    )
    
    # 缓存
    ctx.store.put_metadata(ctx.datasource_luid, metadata)
    
    return format_metadata(metadata)
```

### 5. DataModelManager 重构

```python
# 重构后的 DataModelManager - 不再需要 Runtime 对象

class DataModelManager:
    """
    数据模型管理器
    
    重构后：
    - 不再持有 Runtime 对象
    - 所有方法接收 WorkflowContext 参数
    - 不再自己获取认证
    """
    
    def __init__(self):
        """初始化 - 不需要任何依赖"""
        pass
    
    async def get_data_model_async(
        self,
        ctx: WorkflowContext,
        use_cache: bool = True,
        enhance: bool = True,
    ) -> Metadata:
        """
        获取数据源数据模型
        
        Args:
            ctx: 工作流上下文（包含 auth 和 store）
            use_cache: 是否使用缓存
            enhance: 是否增强数据模型
        """
        # 1. 尝试从缓存获取
        if use_cache:
            cached = ctx.store.get_metadata(ctx.datasource_luid)
            if cached:
                return cached
        
        # 2. 从 Tableau API 获取
        raw_metadata = await get_datasource_metadata(
            datasource_luid=ctx.datasource_luid,
            tableau_token=ctx.auth.api_key,
            tableau_site=ctx.auth.site,
            tableau_domain=ctx.auth.domain,
        )
        
        # 3. 转换为 Metadata 模型
        metadata = self._convert_to_metadata_model(raw_metadata)
        
        # 4. 缓存
        ctx.store.put_metadata(ctx.datasource_luid, metadata)
        
        # 5. 增强（如果需要）
        if enhance:
            await self._enhance_data_model(ctx, metadata)
        
        return metadata
```

### 6. WorkflowExecutor 重构

```python
# 重构后的 WorkflowExecutor

class WorkflowExecutor:
    def __init__(
        self,
        datasource_luid: Optional[str] = None,
        max_replan_rounds: int = 2,
        use_memory_checkpointer: bool = True,
    ):
        self._datasource_luid = datasource_luid or os.getenv("DATASOURCE_LUID", "")
        self._max_replan_rounds = max_replan_rounds
        self._store = get_store_manager()  # 全局单例
        self._workflow = create_tableau_workflow(
            use_memory_checkpointer=use_memory_checkpointer,
            config={"max_replan_rounds": max_replan_rounds}
        )
    
    async def run(
        self,
        question: str,
        thread_id: Optional[str] = None,
    ) -> WorkflowResult:
        thread_id = thread_id or f"thread_{uuid.uuid4().hex[:8]}"
        
        # 1. 获取认证
        auth_ctx = await get_tableau_auth_async()
        
        # 2. 创建初始上下文
        ctx = WorkflowContext(
            auth=auth_ctx,
            store=self._store,
            datasource_luid=self._datasource_luid,
            max_replan_rounds=self._max_replan_rounds,
        )
        
        # 3. 加载数据模型（从缓存或 API）
        # 这一步确保 metadata 在工作流开始前就已加载
        ctx = await ctx.ensure_metadata_loaded()
        
        # 4. 创建配置
        config = create_workflow_config(thread_id, ctx)
        
        # 5. 执行工作流
        # 数据模型通过 state 传递给所有节点
        state = {
            "question": question,
            "messages": [],
            # 数据模型（所有节点共享）
            "metadata": ctx.metadata,
            "dimension_hierarchy": ctx.metadata.dimension_hierarchy if ctx.metadata else None,
            # Replanner 需要的额外数据（初始为空，由 Insight 节点填充）
            "data_insight_profile": None,
            "current_dimensions": [],
        }
        result = await self._workflow.ainvoke(state, config)
        
        return WorkflowResult.from_state(question, result, ...)
```

### 7. 各节点如何使用数据模型

```python
# Understanding 节点 - 使用 metadata 理解用户问题
async def understanding_node(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
    # 从 state 获取数据模型
    metadata = state.get("metadata")
    
    # 使用字段元数据理解问题
    fields_summary = _format_metadata_summary(metadata)
    
    # 调用 LLM 生成 SemanticQuery
    ...

# Replanner 节点 - 使用 dimension_hierarchy 生成探索问题
async def replanner_node(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
    # 从 state 获取维度层级
    dimension_hierarchy = state.get("dimension_hierarchy")
    data_insight_profile = state.get("data_insight_profile")
    current_dimensions = state.get("current_dimensions", [])
    
    # 创建 ReplannerAgent
    replanner = ReplannerAgent(...)
    
    # 执行重规划 - 使用维度层级生成探索问题
    decision = await replanner.replan(
        original_question=state.get("question"),
        insights=state.get("insights"),
        dimension_hierarchy=dimension_hierarchy,  # 关键：用于生成探索问题
        data_insight_profile=data_insight_profile,
        current_dimensions=current_dimensions,
    )
    
    return {"replan_decision": decision, ...}

# get_metadata 工具 - 从 ctx 获取数据模型
@tool
async def get_metadata(runtime: ToolRuntime, use_cache: bool = True) -> str:
    ctx = get_context_or_raise(runtime.config)
    
    # 优先从 ctx 获取（已在工作流启动时加载）
    if ctx.metadata:
        return format_metadata(ctx.metadata)
    
    # 否则从缓存或 API 获取
    cached = ctx.store.get_metadata(ctx.datasource_luid)
    if cached:
        return format_metadata(cached)
    
    # 从 API 获取并缓存
    ...
```

## Data Models

### WorkflowContext 结构

```python
class WorkflowContext(BaseModel):
    """统一依赖容器"""
    
    # 认证（必需）
    auth: TableauAuthContext
    
    # 存储（必需）
    store: StoreManager
    
    # 数据源配置（必需）
    datasource_luid: str
    
    # 数据模型（在工作流启动时加载）
    metadata: Optional[Metadata] = None  # 包含 fields, dimension_hierarchy, data_model
    
    # 工作流配置（可选）
    max_replan_rounds: int = 3
    user_id: Optional[str] = None
```

### RunnableConfig 结构

```python
RunnableConfig = {
    "configurable": {
        "thread_id": str,                    # 会话 ID
        "workflow_context": WorkflowContext, # 统一依赖容器
    }
}
```

### 缓存层次

| 层次 | 机制 | 生命周期 | 用途 | 访问方式 |
|------|------|----------|------|----------|
| L1 | WorkflowContext | 单次工作流执行 | 认证、配置、依赖 | `get_context(config)` |
| L2 | State | 单次工作流执行 | 节点间数据传递 | 函数参数 `state` |
| L3 | StoreManager | 跨会话持久化 | 元数据、维度层级 | `ctx.store.get_xxx()` |
| L4 | Checkpointer | 会话状态持久化 | 工作流断点恢复 | LangGraph 自动管理 |

### 移除的组件

| 组件 | 原因 |
|------|------|
| `get_tableau_config()` | 被 `ctx.auth` 替代 |
| `_data_model_manager` 全局变量 | 被 `WorkflowContext` 替代 |
| `set_metadata_manager()` | 不再需要手动注入 |
| `VizQLContext` dataclass | 被 `WorkflowContext` 替代 |
| `_ctx_cache` 内存缓存 | 仅在 `get_tableau_auth()` 内部使用 |

## Middleware 集成

### 中间件如何访问上下文

```python
# 中间件通过 request.config 访问 WorkflowContext

class CustomMiddleware(AgentMiddleware):
    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        # 从 request 获取 config
        config = request.config
        ctx = get_context(config)
        
        if ctx:
            # 使用上下文
            logger.info(f"Processing request for datasource: {ctx.datasource_luid}")
        
        return await handler(request)
```

### FilesystemMiddleware 与 Store 的关系

```
FilesystemMiddleware                    StoreManager
├── 临时文件存储                        ├── 业务数据持久化
│   └── 大结果自动保存到 /large_tool_   │   └── metadata, dimension_hierarchy
│       results/                        │
├── 生命周期: 单次工作流执行            ├── 生命周期: 跨会话
└── 用途: 处理超大 Tool 输出            └── 用途: 缓存 Tableau 数据
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: 上下文一致性
*For any* 工作流执行，所有节点和工具通过 `get_context(config)` 获取的 WorkflowContext SHALL 是同一个实例
**Validates: Requirements 1.1, 1.2**

### Property 2: 认证自动刷新
*For any* 过期的 token，调用 `ctx.refresh_auth_if_needed()` SHALL 返回包含有效 token 的新 WorkflowContext
**Validates: Requirements 1.3**

### Property 3: 缓存统一性
*For any* 业务数据缓存操作，系统 SHALL 通过 `ctx.store` 使用 StoreManager
**Validates: Requirements 2.1**

### Property 4: 依赖可访问性
*For any* 节点或工具，如果需要 StoreManager 或 TableauAuthContext，SHALL 能从 WorkflowContext 获取
**Validates: Requirements 3.3**

### Property 5: 无全局变量依赖
*For any* 工具函数，SHALL 不依赖全局变量 `_data_model_manager`，而是从 `ToolRuntime.config` 获取依赖
**Validates: Requirements 5.2**

## Error Handling

| 错误类型 | 处理方式 | 恢复策略 |
|----------|----------|----------|
| 认证失败 | 抛出 `TableauAuthError` | 工作流终止，返回错误信息 |
| 认证过期 | 调用 `refresh_auth_if_needed()` | 自动刷新，继续执行 |
| Store 不可用 | 记录警告日志 | 降级为无缓存模式 |
| Config 缺失 | 抛出 `ValueError` | 工作流终止，明确指出缺失项 |
| 数据源不存在 | 抛出 `NotFoundError` | 工作流终止，提示检查配置 |

## Testing Strategy

### Unit Tests
- 测试 `WorkflowContext` 创建和序列化
- 测试 `create_workflow_config` 创建正确的配置结构
- 测试 `get_context` 正确解析 WorkflowContext
- 测试 `refresh_auth_if_needed` 正确刷新过期 token

### Integration Tests
- 测试完整工作流执行，验证上下文在所有节点间正确传递
- 测试 Tool 通过 ToolRuntime 正确访问上下文
- 测试中间件正确访问上下文

### Property-Based Tests
- **Property 1**: 生成随机工作流执行，验证所有节点获取的上下文一致
- **Property 2**: 生成过期 token，验证自动刷新机制
- **Property 3**: 生成随机缓存操作，验证都通过 StoreManager
