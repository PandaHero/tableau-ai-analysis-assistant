# 附件 1：五层架构详细设计

本文档详细说明 Analytics Assistant 的五层架构设计。

## 架构分层原则

### 分层顺序（从下到上）

```
┌─────────────────────────────────────────┐
│ 5. API 层（FastAPI）                     │  ← 最上层
└─────────────────────────────────────────┘
                  ↓ 调用
┌─────────────────────────────────────────┐
│ 4. Orchestration 层（LangGraph）         │
└─────────────────────────────────────────┘
                  ↓ 调用
┌─────────────────────────────────────────┐
│ 3. Agent 层（智能体）                    │
└─────────────────────────────────────────┘
                  ↓ 调用
┌─────────────────────────────────────────┐
│ 2. Platform 层（平台适配）               │
└─────────────────────────────────────────┘
                  ↓ 实现接口
┌─────────────────────────────────────────┐
│ 1. Core 层（核心领域）                   │  ← 最底层
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│ 0. Infrastructure 层（横向）             │  ← 被所有层使用
│    - AI（LLM、Embedding）                │
│    - RAG（检索、索引）                   │
│    - Storage（存储、缓存）               │
│    - Config（配置）                      │
│    - Observability（监控）               │
└─────────────────────────────────────────┘
```

### 依赖规则

1. **Core 层**：不依赖任何其他层，只使用标准库和 Pydantic
2. **Platform 层**：依赖 Core 层，实现 Core 层定义的接口
3. **Agent 层**：依赖 Platform 层和 Core 层，使用 Infrastructure 层提供的服务
4. **Orchestration 层**：依赖 Agent 层、Platform 层和 Core 层
5. **API 层**：依赖 Orchestration 层
6. **Infrastructure 层**：横向层，被所有层使用，但不依赖业务层

### 关键原则

- ✅ 上层可以依赖下层
- ❌ 下层不能依赖上层
- ✅ Infrastructure 层被所有层使用
- ❌ Infrastructure 层不能依赖 Agent/Orchestration/API 层
- ✅ Agent 层通过 Platform 层访问平台特定功能

---

## 1. Core 层（核心领域层）

### 职责

- 定义领域模型和业务实体
- 实现平台无关的业务逻辑
- 定义平台适配器接口
- 提供数据验证和转换逻辑

### 关键组件

#### 领域模型

```python
# core/models/query.py
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from enum import Enum

class QueryIntent(str, Enum):
    """查询意图枚举"""
    COMPARISON = "comparison"
    TREND = "trend"
    RANKING = "ranking"
    DISTRIBUTION = "distribution"
    AGGREGATION = "aggregation"
    FILTER = "filter"

class TimeContext(BaseModel):
    """时间上下文"""
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    granularity: Optional[str] = None  # day, week, month, quarter, year
    relative_period: Optional[str] = None  # last_7_days, this_month, etc.

class SemanticQuery(BaseModel):
    """语义查询模型"""
    raw_query: str = Field(..., description="原始用户查询")
    normalized_query: str = Field(..., description="规范化后的查询")
    intent: QueryIntent = Field(..., description="查询意图")
    entities: List[str] = Field(default_factory=list, description="提取的业务实体")
    time_context: Optional[TimeContext] = None
    filters: Dict[str, any] = Field(default_factory=dict)
    metrics: List[str] = Field(default_factory=list)
    dimensions: List[str] = Field(default_factory=list)

# core/models/schema.py
class FieldType(str, Enum):
    """字段类型"""
    DIMENSION = "dimension"
    MEASURE = "measure"
    CALCULATED = "calculated"

class Field(BaseModel):
    """字段模型"""
    id: str
    name: str
    display_name: str
    field_type: FieldType
    data_type: str  # string, number, date, boolean
    description: Optional[str] = None
    synonyms: List[str] = Field(default_factory=list)
    
class DataModel(BaseModel):
    """数据模型"""
    id: str
    name: str
    fields: List[Field]
    relationships: List[Dict] = Field(default_factory=list)
```

#### 接口定义

```python
# core/interfaces/platform_adapter.py
from abc import ABC, abstractmethod
from typing import List, Dict, Any
from core.models.query import SemanticQuery
from core.models.schema import DataModel

class IPlatformAdapter(ABC):
    """平台适配器接口"""
    
    @abstractmethod
    async def get_data_model(self, workspace_id: str) -> DataModel:
        """获取数据模型"""
        pass
    
    @abstractmethod
    async def execute_query(self, query: SemanticQuery) -> Dict[str, Any]:
        """执行查询"""
        pass
    
    @abstractmethod
    async def get_field_values(self, field_id: str, limit: int = 100) -> List[Any]:
        """获取字段值"""
        pass
```

### 依赖关系

- **不依赖任何其他层**
- 仅使用标准库和 Pydantic
- 被所有上层依赖

---

## 2. Platform 层（平台适配层）

### 职责

- 实现特定平台的适配器（Tableau、Power BI 等）
- 处理平台特定的 API 调用和数据格式
- 将平台数据转换为 Core 层的领域模型

### 关键组件

```python
# platform/tableau/adapter.py
from core.interfaces.platform_adapter import IPlatformAdapter
from core.models.schema import DataModel, Field, FieldType
from core.models.query import SemanticQuery
import tableauserverclient as TSC

class TableauAdapter(IPlatformAdapter):
    """Tableau 平台适配器"""
    
    def __init__(self, server_url: str, token_name: str, token_value: str):
        self.server_url = server_url
        self.auth = TSC.PersonalAccessTokenAuth(token_name, token_value)
        self.server = TSC.Server(server_url, use_server_version=True)
    
    async def get_data_model(self, workspace_id: str) -> DataModel:
        """从 Tableau 获取数据模型"""
        with self.server.auth.sign_in(self.auth):
            # 获取工作簿和数据源
            workbook = self.server.workbooks.get_by_id(workspace_id)
            
            # 转换为 Core 层的 DataModel
            fields = []
            for field in workbook.fields:
                fields.append(Field(
                    id=field.id,
                    name=field.name,
                    display_name=field.caption or field.name,
                    field_type=self._map_field_type(field.role),
                    data_type=self._map_data_type(field.datatype),
                    description=field.description
                ))
            
            return DataModel(
                id=workbook.id,
                name=workbook.name,
                fields=fields
            )
    
    async def execute_query(self, query: SemanticQuery) -> Dict[str, Any]:
        """执行查询并返回结果"""
        # 将 SemanticQuery 转换为 Tableau VizQL
        vizql = self._build_vizql(query)
        
        # 执行查询
        with self.server.auth.sign_in(self.auth):
            result = self.server.views.query(vizql)
        
        return self._parse_result(result)
    
    def _map_field_type(self, tableau_role: str) -> FieldType:
        """映射 Tableau 字段类型到 Core 层类型"""
        mapping = {
            "dimension": FieldType.DIMENSION,
            "measure": FieldType.MEASURE,
        }
        return mapping.get(tableau_role, FieldType.DIMENSION)
```

### 依赖关系

- 依赖 Core 层的接口和模型
- 使用平台特定的 SDK（tableauserverclient）
- 被 Agent 层通过 Core 层接口调用

---

## 3. Agent 层（智能体层）

### 职责

- 实现专业化的 AI Agent
- 处理特定的分析任务
- 组合可复用组件完成复杂逻辑

### Agent 列表

1. **SemanticParser**：理解用户意图，将自然语言转换为语义查询
2. **FieldMapper**：将语义查询中的实体映射到数据模型字段
3. **DimensionHierarchy**：推断维度层级关系
4. **Insight**：生成数据洞察和建议
5. **Replanner**：根据执行结果重新规划查询

### 组件化设计

每个 Agent 由多个可复用组件组成：

```python
# agents/base/components.py
from abc import ABC, abstractmethod
from typing import Any, Dict
from pydantic import BaseModel

class ComponentInput(BaseModel):
    """组件输入基类"""
    pass

class ComponentOutput(BaseModel):
    """组件输出基类"""
    pass

class BaseComponent(ABC):
    """可复用组件基类"""
    
    @abstractmethod
    async def execute(self, input: ComponentInput) -> ComponentOutput:
        """执行组件逻辑"""
        pass
```

### SemanticParser Agent 示例

```python
# agents/semantic_parser/agent.py
from agents.base.components import BaseComponent
from agents.semantic_parser.components.preprocess import PreprocessComponent
from agents.semantic_parser.components.intent_router import IntentRouter
from agents.semantic_parser.components.schema_linker import SchemaLinker
from agents.semantic_parser.components.query_builder import QueryBuilder

class SemanticParserAgent:
    """语义解析器 Agent"""
    
    def __init__(
        self,
        preprocess: PreprocessComponent,
        intent_router: IntentRouter,
        schema_linker: SchemaLinker,
        query_builder: QueryBuilder
    ):
        self.preprocess = preprocess
        self.intent_router = intent_router
        self.schema_linker = schema_linker
        self.query_builder = query_builder
    
    async def parse(self, raw_query: str, data_model: DataModel) -> SemanticQuery:
        """解析用户查询"""
        # 1. 预处理
        preprocess_result = await self.preprocess.execute(
            PreprocessInput(query=raw_query)
        )
        
        # 2. 意图路由
        intent_result = await self.intent_router.execute(
            IntentRouterInput(
                query=preprocess_result.normalized_query,
                context={"entities": preprocess_result.entities}
            )
        )
        
        # 3. Schema Linking
        schema_result = await self.schema_linker.execute(
            SchemaLinkerInput(
                query=preprocess_result.normalized_query,
                entities=preprocess_result.entities,
                data_model=data_model
            )
        )
        
        # 4. 构建语义查询
        query_result = await self.query_builder.execute(
            QueryBuilderInput(
                normalized_query=preprocess_result.normalized_query,
                intent=intent_result.intent,
                matched_fields=schema_result.matched_fields,
                time_context=preprocess_result.time_context
            )
        )
        
        return query_result.semantic_query
```

### 依赖关系

- 依赖 Core 层的模型和接口
- 依赖 Infrastructure 层的 AI 和 RAG 服务
- 不依赖 Platform 层（通过 Core 层接口交互）
- 被 Orchestration 层调用

---

## 4. Orchestration 层（编排层）

### 职责

- 使用 LangGraph 编排多 Agent 工作流
- 管理状态和上下文传递
- 实现中间件和工具
- 处理错误和重试逻辑

### LangGraph 工作流设计

```python
# orchestration/workflow/main_workflow.py
from langgraph.graph import StateGraph, END
from typing import TypedDict, Annotated
import operator

class WorkflowState(TypedDict):
    """工作流状态"""
    raw_query: str
    semantic_query: Optional[SemanticQuery]
    mapped_fields: Optional[Dict]
    query_result: Optional[Dict]
    insights: Optional[List[str]]
    error: Optional[str]
    retry_count: int

def create_workflow() -> StateGraph:
    """创建主工作流"""
    workflow = StateGraph(WorkflowState)
    
    # 添加节点
    workflow.add_node("semantic_parser", semantic_parser_node)
    workflow.add_node("field_mapper", field_mapper_node)
    workflow.add_node("dimension_hierarchy", dimension_hierarchy_node)
    workflow.add_node("execute_query", execute_query_node)
    workflow.add_node("insight_generator", insight_generator_node)
    workflow.add_node("replanner", replanner_node)
    
    # 定义边
    workflow.set_entry_point("semantic_parser")
    workflow.add_edge("semantic_parser", "field_mapper")
    workflow.add_edge("field_mapper", "dimension_hierarchy")
    workflow.add_edge("dimension_hierarchy", "execute_query")
    
    # 条件边：根据查询结果决定是否需要重规划
    workflow.add_conditional_edges(
        "execute_query",
        should_replan,
        {
            "replan": "replanner",
            "continue": "insight_generator"
        }
    )
    
    workflow.add_edge("replanner", "semantic_parser")
    workflow.add_edge("insight_generator", END)
    
    return workflow.compile()
```

### 中间件系统

中间件系统基于 **LangChain AgentMiddleware** 实现，提供可复用的横切关注点处理。

#### 中间件分类

**LangChain 框架自带中间件**（5个）：

1. **TodoListMiddleware**：任务队列管理
2. **SummarizationMiddleware**：自动摘要对话历史（长对话压缩）
3. **ModelRetryMiddleware**：LLM 调用自动重试（指数退避）
4. **ToolRetryMiddleware**：工具调用自动重试（指数退避）
5. **HumanInTheLoopMiddleware**：人工确认（可选）

**自定义中间件**（基于 deepagents 设计，3个）：

1. **FilesystemMiddleware**：文件系统工具 + 大型结果自动保存
2. **PatchToolCallsMiddleware**：修复悬空工具调用
3. **OutputValidationMiddleware**：输出验证（质量闸门）

#### 重构后的中间件策略

**保留的中间件**（LangChain 自带）：
- ✅ TodoListMiddleware
- ✅ SummarizationMiddleware
- ✅ ModelRetryMiddleware
- ✅ ToolRetryMiddleware
- ✅ HumanInTheLoopMiddleware（可选）

**保留的自定义中间件**：
- ✅ FilesystemMiddleware（提供文件工具，处理大型结果）

**可能移除的中间件**（重构后评估）：
- ⚠️ **PatchToolCallsMiddleware**：LangGraph 可能已内置处理悬空工具调用
- ⚠️ **OutputValidationMiddleware**：格式校验已在组件级完成（Step1/Step2 内部重试）

#### 1. LangChain 自带中间件

这些中间件由 LangChain 框架提供，开箱即用：

```python
# orchestration/workflow/factory.py
from langchain.agents.middleware import (
    TodoListMiddleware,
    SummarizationMiddleware,
    ModelRetryMiddleware,
    ToolRetryMiddleware,
    HumanInTheLoopMiddleware,
)

def create_middleware_stack():
    middleware = []
    
    # 1. 任务队列管理
    middleware.append(TodoListMiddleware())
    
    # 2. 对话摘要（长对话压缩）
    middleware.append(SummarizationMiddleware(
        model=chat_model,
        trigger=("tokens", 60000),  # 60K tokens 触发摘要
        keep=("messages", 10),      # 保留最近 10 条消息
    ))
    
    # 3. LLM 调用重试（指数退避）
    middleware.append(ModelRetryMiddleware(
        max_retries=3,
        initial_delay=1.0,
        backoff_factor=2.0,  # 1s, 2s, 4s
        max_delay=60.0,
        jitter=True,
    ))
    
    # 4. 工具调用重试（指数退避）
    middleware.append(ToolRetryMiddleware(
        max_retries=3,
        initial_delay=1.0,
        backoff_factor=2.0,
        max_delay=60.0,
        jitter=True,
    ))
    
    # 5. 人工确认（必选）
    middleware.append(HumanInTheLoopMiddleware(
        interrupt_on={
            "write_file": True,
            "delete_data": True,
            "execute_custom_sql": True,
            "write_todos": True,
            "bulk_export": True,
        }
    ))
    
    return middleware
```

#### HumanInTheLoopMiddleware 详细配置（必选）

**重要**：HumanInTheLoopMiddleware 是**必选**的，不是可选的。

**介入场景**：
- **探索任务规划**（`write_todos`）：当 Replanner Agent 生成探索问题时，需要用户审核和确认

**为什么只在探索任务介入**：
- 探索问题会影响后续的查询方向，需要用户确认是否继续探索
- 其他操作（数据查询、可视化生成等）是系统的核心功能，不需要人工介入
- 保持流畅的用户体验，避免过多的确认步骤

**配置方式**：
```python
# 方式 1：环境变量（推荐）
INTERRUPT_ON=write_todos

# 方式 2：代码配置
HumanInTheLoopMiddleware(
    interrupt_on={
        "write_todos": True
    }
)
```

**工作流程**：
1. Replanner Agent 调用 `write_todos` 工具生成探索问题
2. HumanInTheLoopMiddleware 拦截调用
3. 系统暂停，向用户展示探索问题列表
4. 用户审核：
   - 批准 → 继续执行探索问题
   - 拒绝 → 结束当前会话
   - 修改 → 用户可以调整探索问题

#### 2. FilesystemMiddleware（自定义，保留）

**功能**：
- 提供文件系统工具（ls, read_file, write_file, edit_file, glob, grep）
- 自动将大型工具结果保存到文件系统（超过 token 限制时）
- 支持分页读取（offset/limit）
- 使用 StateBackend 存储文件到 LangGraph 状态

**设计原则**：
- 基于 deepagents FilesystemMiddleware 设计
- 自动处理大型输出（避免 context 溢出）
- 提供完整的文件操作能力

**示例**：
```python
# orchestration/middleware/filesystem.py
from langchain.agents.middleware import AgentMiddleware

class FilesystemMiddleware(AgentMiddleware):
    """文件系统中间件（基于 deepagents 设计）"""
    
    def __init__(
        self,
        backend: BackendProtocol | None = None,
        tool_token_limit_before_evict: int = 20000,
    ):
        self.tool_token_limit_before_evict = tool_token_limit_before_evict
        self.backend = backend or StateBackend
        self.tools = _get_filesystem_tools(self.backend)
    
    def wrap_tool_call(self, request, handler):
        """拦截工具调用，处理大型结果"""
        tool_result = handler(request)
        
        # 如果结果过大，保存到文件系统
        if len(tool_result.content) > 4 * self.tool_token_limit_before_evict:
            file_path = f"/large_tool_results/{tool_call_id}"
            self.backend.write(file_path, tool_result.content)
            return ToolMessage(
                f"Result saved to {file_path}. Use read_file to view.",
                tool_call_id=tool_call_id
            )
        
        return tool_result
```

#### 3. PatchToolCallsMiddleware（自定义，重构后评估）

**功能**：
- 检测并修复"悬空"工具调用（dangling tool calls）
- 在 AIMessage 有 tool_call 但没有对应 ToolMessage 时自动插入占位符

**重构后评估**：
- ⚠️ LangGraph 可能已内置处理悬空工具调用
- ⚠️ 如果 LangGraph 已处理，此中间件可移除

#### 4. OutputValidationMiddleware（自定义，重构后评估）

**功能**：
- 作为最终质量闸门（final quality gate），不是重试触发器
- 验证 LLM 输出是否符合 Pydantic Schema
- 记录验证错误和告警

**重构后评估**：
- ⚠️ 格式校验已在组件级完成（Step1/Step2 内部重试）
- ⚠️ 语义错误由 ReAct 处理
- ⚠️ 此中间件可能不再需要，或仅用于监控

**设计原则（Requirements 0.6）**：
- **格式错误**（JSON/Pydantic）由组件级重试处理（Step1/Step2 内部）
- **语义错误**（字段未找到）由 ReAct 处理
- **此中间件**仅记录和告警，默认不触发重试

#### 中间件配置

所有中间件配置通过 `.env` 文件管理：

```python
# .env
SUMMARIZATION_TOKEN_THRESHOLD=60000  # 60K tokens
MESSAGES_TO_KEEP=10
MODEL_MAX_RETRIES=3
TOOL_MAX_RETRIES=3
FILESYSTEM_TOKEN_LIMIT=20000
INTERRUPT_ON=write_todos
```

#### 总结

**中间件来源**：
- ✅ **5个 LangChain 自带**：TodoList, Summarization, ModelRetry, ToolRetry, HumanInTheLoop
- ✅ **1个自定义保留**：FilesystemMiddleware（基于 deepagents）
- ⚠️ **2个自定义评估**：PatchToolCalls, OutputValidation（重构后可能移除）

**重构策略**：
1. 保留所有 LangChain 自带中间件（框架提供，稳定可靠）
2. 保留 FilesystemMiddleware（提供文件工具，处理大型结果）
3. 评估 PatchToolCallsMiddleware（LangGraph 可能已处理）
4. 评估 OutputValidationMiddleware（组件级校验已完成）

### 依赖关系

- 依赖 Agent 层的 Agent 实现
- 依赖 Core 层的模型
- 使用 LangGraph 和 LangChain
- 被 API 层调用

---

## 5. Infrastructure 层（基础设施层）

### 职责

- 提供横向的基础设施服务
- 管理 AI 模型和 Embedding
- 实现 RAG 检索
- 处理存储、配置和可观测性

### AI 模块 - ModelManager

**功能**：
- 统一管理多个 LLM 和 Embedding 模型
- 支持多种提供商（OpenAI、Azure、智谱、自定义端点）
- 模型配置的 CRUD 操作
- 持久化存储（LangGraph SqliteStore）
- 模型健康检查和使用统计
- 默认模型管理

**设计原则**：
- 单例模式（全局唯一实例）
- 支持 OpenAI 兼容 API（大多数模型）
- 支持自定义端点（非 OpenAI 兼容）
- 智能路由（根据配置选择合适的客户端）

**示例**：
```python
# infra/ai/model_manager.py
from typing import Dict, Optional, List
from enum import Enum
from pydantic import BaseModel

class ModelType(str, Enum):
    """模型类型"""
    LLM = "llm"
    EMBEDDING = "embedding"

class AuthType(str, Enum):
    """认证类型"""
    BEARER = "bearer"
    API_KEY_HEADER = "apikey"
    CUSTOM_HEADER = "custom"
    NONE = "none"

class ModelConfig(BaseModel):
    """模型配置"""
    id: str
    name: str
    model_type: ModelType
    provider: str  # openai, azure, zhipu, custom
    api_base: str
    model_name: str
    openai_compatible: bool = True  # 是否 OpenAI 兼容
    auth_type: AuthType = AuthType.BEARER
    api_key: str
    temperature: Optional[float] = None  # None = 使用模型默认值
    max_tokens: Optional[int] = None
    supports_streaming: bool = True
    supports_thinking: bool = False
    supports_json_mode: Optional[bool] = None

class ModelManager:
    """模型管理器 - 单例"""
    
    _instance: Optional["ModelManager"] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        
        self._configs: Dict[str, ModelConfig] = {}
        self._stats: Dict[str, ModelStats] = {}
        self._defaults: Dict[ModelType, str] = {}
        self._store = get_langgraph_store()
        
        # 从存储加载配置
        self._load_from_store()
        # 从环境变量加载预配置模型
        self._load_from_env()
        
        self._initialized = True
    
    def create_llm(self, model_id: Optional[str] = None, **kwargs):
        """创建 LLM 实例
        
        路由逻辑：
        1. Azure OpenAI → AzureChatOpenAI
        2. 非 OpenAI 兼容 → CustomLLMChat
        3. OpenAI 兼容 → ChatOpenAI
        """
        config = self.get(model_id) if model_id else self.get_default(ModelType.LLM)
        
        if config.provider == "azure":
            return AzureChatOpenAI(...)
        
        if not config.openai_compatible:
            return CustomLLMChat(config=custom_config)
        
        return ChatOpenAI(
            model_name=config.model_name,
            api_key=config.api_key,
            base_url=config.api_base,
            temperature=kwargs.get('temperature', config.temperature),
        )
    
    def create_embedding(self, model_id: Optional[str] = None, **kwargs):
        """创建 Embedding 实例
        
        路由逻辑：
        1. provider=zhipu → ZhipuEmbedding（专用 SDK）
        2. openai_compatible=True → OpenAIEmbedding
        """
        config = self.get(model_id) if model_id else self.get_default(ModelType.EMBEDDING)
        
        if config.provider == "zhipu":
            return ZhipuEmbedding(api_key=config.api_key, ...)
        
        if config.openai_compatible:
            return OpenAIEmbedding(
                api_key=config.api_key,
                base_url=config.api_base,
                ...
            )

# 单例访问
def get_model_manager() -> ModelManager:
    """获取模型管理器单例"""
    return ModelManager()
```

**关键特性**：

1. **统一接口**：所有 Agent 通过 `get_model_manager()` 获取模型
2. **智能路由**：根据 `openai_compatible` 标记选择合适的客户端
3. **持久化**：配置存储在 LangGraph SqliteStore
4. **健康检查**：定期检查模型可用性
5. **使用统计**：记录请求次数、成功率、延迟等

**使用示例**：

```python
# agents/field_mapper/node.py
from analytics_assistant.src.infra.ai.model_manager import get_model_manager
from analytics_assistant.src.agents.base import call_llm_with_tools, parse_json_response

async def select_field_with_llm(term, candidates, context):
    """使用 LLM 选择最佳字段（当 RAG 置信度低时）"""
    # 使用 ModelManager 获取 LLM
    manager = get_model_manager()
    llm = manager.create_llm()
    
    # 构建 prompt
    messages = FIELD_MAPPER_PROMPT.format_messages(
        term=term,
        candidates=format_candidates(candidates),
        context=context
    )
    
    # 调用 LLM（支持流式输出）
    response = await call_llm_with_tools(
        llm=llm,
        messages=messages,
        streaming=True,
    )
    
    return parse_json_response(response.content, SingleSelectionResult)
```

**总结**：
- **ModelManager**：全局模型管理器，提供统一的模型创建接口
- **直接使用**：Agent 直接使用 ModelManager 和 base 工具函数，无需额外封装
- **简洁高效**：减少不必要的抽象层，代码更易维护

### RAG 模块 - 统一检索器

```python
# infra/rag/retriever.py
from typing import List, Dict, Optional
from enum import Enum

class RetrievalStrategy(str, Enum):
    """检索策略"""
    VECTOR = "vector"
    KEYWORD = "keyword"
    EXACT = "exact"
    HYBRID = "hybrid"

class UnifiedRetriever:
    """统一检索器 - 支持多种检索策略"""
    
    def __init__(
        self,
        vector_store,
        keyword_index,
        model_manager: ModelManager
    ):
        self.vector_store = vector_store
        self.keyword_index = keyword_index
        self.model_manager = model_manager
    
    async def retrieve(
        self,
        query: str,
        strategy: RetrievalStrategy = RetrievalStrategy.HYBRID,
        top_k: int = 20,
        filters: Optional[Dict] = None
    ) -> List[RetrievalResult]:
        """执行检索"""
        if strategy == RetrievalStrategy.HYBRID:
            return await self._hybrid_retrieve(query, top_k, filters)
        # ... 其他策略
```

### 依赖关系

- **不依赖其他层**（横向层）
- 被所有其他层使用
- 提供基础设施服务

---

## 层次依赖图

```
API 层
  ↓
Orchestration 层
  ↓
Agent 层
  ↓
Platform 层
  ↓
Core 层

Infrastructure 层 (横向，被所有层使用)
```

**依赖规则**：
- 上层可以依赖下层
- 下层不能依赖上层
- Infrastructure 层被所有层使用
- 所有层通过 Core 层的接口与 Platform 层交互
