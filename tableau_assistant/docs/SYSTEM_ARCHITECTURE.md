# Tableau Assistant 系统架构详解

## 1. 系统概述

Tableau Assistant 是一个基于 LangChain/LangGraph 框架的多智能体数据分析系统，通过自然语言理解用户问题，自动生成 VizQL 查询并提供数据洞察。

### 1.1 核心特性

- **语义解析**: 三步 LLM 组合架构（Step1 + Step2 + Observer）
- **智能字段映射**: RAG + LLM 混合策略
- **渐进式分析**: 多轮重规划，深度探索数据
- **流式输出**: 支持 Token 级别的实时响应

### 1.2 技术栈

| 组件 | 技术选型 |
|------|----------|
| 工作流编排 | LangGraph StateGraph |
| LLM 框架 | LangChain |
| 向量检索 | 自研 RAG (Embedding + Reranker) |
| 持久化 | SQLite (StoreManager) |
| API 框架 | FastAPI |
| 前端 | Vue 3 + TypeScript |

---

## 2. 工作流架构

### 2.1 节点概览（6 个节点）

```
START → semantic_parser → field_mapper → query_builder → execute → insight → replanner → END
              ↑                                                                    │
              └──────────────────── (should_replan=True) ──────────────────────────┘
```

| 节点名称 | 实现 | 类型 | 职责 |
|----------|------|------|------|
| semantic_parser | SemanticParserAgent | LLM Agent | 语义解析、意图分类、计算推理（Step1 + Step2 + Observer） |
| FieldMapper | RAG + LLM | 业务术语 → 技术字段映射 |
| QueryBuilder | Pure Code | SemanticQuery → VizQL 转换 |
| Execute | Pure Code | VizQL API 调用 |
| Insight | LLM Agent | 数据分析、洞察生成 |
| Replanner | LLM Agent | 完成度评估、探索问题生成 |

### 2.2 工作流构建 (factory.py)

```python
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

graph = StateGraph(VizQLState)

# 添加 6 个节点
graph.add_node("semantic_parser", semantic_parser_node)  # Step1 + Step2 + Observer
graph.add_node("field_mapper", field_mapper_node)
graph.add_node("query_builder", query_builder_node)
graph.add_node("execute", execute_node)
graph.add_node("insight", insight_node)
graph.add_node("replanner", replanner_node)

# 添加边
graph.add_edge(START, "understanding")
graph.add_conditional_edges("understanding", route_after_understanding,
    {"field_mapper": "field_mapper", "end": END})
graph.add_edge("field_mapper", "query_builder")
graph.add_edge("query_builder", "execute")
graph.add_edge("execute", "insight")
graph.add_edge("insight", "replanner")
graph.add_conditional_edges("replanner", route_after_replanner,
    {"understanding": "understanding", "end": END})

compiled_graph = graph.compile(checkpointer=MemorySaver())
```


### 2.3 路由逻辑 (routes.py)

**route_after_semantic_parser:**
```python
def route_after_semantic_parser(state) -> Literal["field_mapper", "end"]:
    """
    基于 SemanticParseResult.intent.type 进行路由
    
    意图类型：
    - DATA_QUERY: 有效的数据查询 → field_mapper
    - CLARIFICATION: 需要澄清 → end（返回澄清问题）
    - GENERAL: 问元数据/字段信息 → end（返回通用响应）
    - IRRELEVANT: 与数据分析无关 → end（返回提示）
    """
    semantic_parse_result = state.get("semantic_parse_result")
    if semantic_parse_result is not None:
        intent_type = semantic_parse_result.intent.type
        if intent_type == IntentType.DATA_QUERY:
            return "field_mapper"
        else:  # CLARIFICATION/GENERAL/IRRELEVANT
            return "end"
    return "end"
```

**route_after_replanner:**
```python
def route_after_replanner(state, max_replan_rounds=3) -> Literal["semantic_parser", "end"]:
    replan_decision = state.get("replan_decision")
    replan_count = state.get("replan_count", 0)
    
    if replan_count >= max_replan_rounds:
        return "end"  # 达到最大轮数
    if replan_decision and replan_decision.should_replan:
        return "semantic_parser"  # 继续探索
    return "end"  # 分析完成
```

---

## 3. 状态管理 (VizQLState)

### 3.1 状态定义

```python
class VizQLState(TypedDict):
    # 对话历史
    messages: Annotated[List[BaseMessage], operator.add]
    answered_questions: Annotated[List[str], operator.add]
    
    # 用户输入
    question: str
    
    # SemanticParser 输出
    semantic_parse_result: Optional[SemanticParseResult]  # 完整解析结果
    semantic_query: Optional[SemanticQuery]  # 语义查询（仅 DATA_QUERY）
    restated_question: Optional[str]  # 重述后的问题
    is_analysis_question: bool  # intent.type == DATA_QUERY（用于路由，兼容字段）
    
    # 字段映射输出
    mapped_query: Optional[MappedQuery]
    
    # 查询构建输出
    vizql_query: Optional[VizQLQuery]
    
    # 执行结果
    query_result: Optional[ExecuteResult]
    
    # 洞察输出
    insights: Annotated[List[Insight], operator.add]
    all_insights: Annotated[List[Insight], operator.add]
    data_insight_profile: Optional[Dict[str, Any]]
    
    # 重规划输出
    replan_decision: Optional[ReplanDecision]
    replan_count: int
    replan_history: Annotated[List[ReplanHistoryRecord], operator.add]
    
    # 元数据
    datasource: Optional[str]
    metadata: Optional[Metadata]
    dimension_hierarchy: Optional[Dict[str, Dict]]
    
    # 控制流
    current_stage: str
    errors: Annotated[List[ErrorRecord], operator.add]
```

### 3.2 状态流转

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ SemanticParser Node                                                          │
│ 输入: question, messages, metadata                                          │
│ 输出: semantic_parse_result, semantic_query, restated_question              │
│       is_analysis_question = (intent.type == DATA_QUERY)                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ FieldMapper Node                                                             │
│ 输入: semantic_query, metadata, question                                    │
│ 输出: mapped_query (包含 field_mappings)                                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ QueryBuilder Node                                                            │
│ 输入: mapped_query                                                          │
│ 输出: vizql_query (VizQL 请求对象)                                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Execute Node                                                                 │
│ 输入: vizql_query, datasource_luid, tableau_auth                            │
│ 输出: query_result (数据行、列信息)                                         │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Insight Node                                                                 │
│ 输入: query_result, question, semantic_query, dimension_hierarchy           │
│ 输出: insights, data_insight_profile, messages (对话历史)                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Replanner Node                                                               │
│ 输入: insights, data_insight_profile, dimension_hierarchy, answered_questions│
│ 输出: replan_decision, exploration_questions, question (更新为探索问题)     │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. 上下文管理 (WorkflowContext)

### 4.1 WorkflowContext 定义

```python
class WorkflowContext(BaseModel):
    """统一的依赖容器，通过 RunnableConfig 传递给所有节点"""
    
    auth: TableauAuthContext      # Tableau 认证
    store: StoreManager           # 持久化存储
    datasource_luid: str          # 数据源 LUID
    metadata: Optional[Metadata]  # 数据模型（包含字段、维度层级）
    max_replan_rounds: int = 3
    user_id: Optional[str] = None
    metadata_load_status: Optional[MetadataLoadStatus]
    
    async def ensure_metadata_loaded(self, timeout=60.0) -> "WorkflowContext":
        """确保数据模型已加载（从缓存或 API）"""
        
    async def refresh_auth_if_needed(self) -> "WorkflowContext":
        """如果认证过期，刷新并返回新实例"""
```

### 4.2 上下文传递

```python
# 创建配置
def create_workflow_config(thread_id: str, context: WorkflowContext):
    return {
        "configurable": {
            "thread_id": thread_id,
            "workflow_context": context,
            "tableau_auth": context.auth.model_dump(),
        }
    }

# 在节点中获取
async def my_node(state, config):
    ctx = get_context_or_raise(config)
    # 使用 ctx.auth, ctx.store, ctx.metadata
```


---

## 5. 各节点详解

### 5.1 SemanticParser Node (SemanticParserAgent)

**架构**: 三步 LLM 组合（Step1 + Step2 + Observer）

**设计文档**: `.kiro/specs/semantic-layer-refactor/design.md`

```
用户问题 + 历史对话
        │
        ▼
┌───────────────────────────────────────────────────────────────┐
│                    Step 1: 直觉（Intuition）                   │
│  • 重述问题为完整独立问题                                       │
│  • 提取结构化信息（What × Where × How）                        │
│  • 分类意图（DATA_QUERY / CLARIFICATION / GENERAL / IRRELEVANT）│
└───────────────────────────────────────────────────────────────┘
        │
        ▼
    intent.type == DATA_QUERY && how_type != SIMPLE?
        │
    ┌───┴───┐
   No       Yes
    │       │
    ▼       ▼
  直接   ┌───────────────────────────────────────────────────────┐
  返回   │                    Step 2: 推理（Reasoning）           │
        │  • 从 restated_question 推断计算定义                    │
        │  • 自我验证推理结果                                     │
        └───────────────────────────────────────────────────────┘
                │
                ▼
         validation.all_valid?
                │
            ┌───┴───┐
           Yes      No
            │       │
            ▼       ▼
         输出   ┌───────────────────────────────────────────────┐
         结果   │              Observer: 元认知                  │
               │  • 检查重述完整性                               │
               │  • 复核结构一致性                               │
               │  决策: ACCEPT / CORRECT / RETRY / CLARIFY      │
               └───────────────────────────────────────────────┘
```

**输出** (SemanticParseResult):
```python
class SemanticParseResult(BaseModel):
    """语义解析完整结果"""
    
    restated_question: str
    """重述后的问题"""
    
    intent: Intent
    """意图分类（DATA_QUERY/CLARIFICATION/GENERAL/IRRELEVANT）"""
    
    semantic_query: SemanticQuery | None = None
    """语义查询（仅 DATA_QUERY 意图）"""
    
    clarification: ClarificationQuestion | None = None
    """澄清问题（仅 CLARIFICATION 意图）"""
    
    general_response: str | None = None
    """通用响应（仅 GENERAL 意图）"""

# 节点返回的 state 更新
{
    "semantic_parse_result": SemanticParseResult,
    "semantic_query": SemanticQuery | None,  # 从 parse_result 提取
    "restated_question": str,
    "is_analysis_question": bool,  # intent.type == DATA_QUERY
    "understanding_complete": True,
}
```

**意图分类**:
| 意图 | 判断条件 | 后续处理 |
|------|---------|---------|
| DATA_QUERY | 有可查询的字段，信息完整 | → FieldMapper |
| CLARIFICATION | 引用了未指定的值或需要澄清 | → END（返回澄清问题） |
| GENERAL | 问数据集描述、字段信息 | → END（返回通用响应） |
| IRRELEVANT | 与数据分析无关 | → END（返回提示） |

### 5.2 FieldMapper Node

**架构**: RAG + LLM 混合策略

```
业务术语 "销售额"
        │
        ▼
┌───────────────────┐
│   1. 缓存查找      │ ← StoreManager (SQLite)
│   TTL: 24小时      │
└───────────────────┘
        │ miss
        ▼
┌───────────────────┐
│   2. RAG 检索      │ ← KnowledgeAssembler + Embedding
│   Top-K 候选       │
└───────────────────┘
        │
        ▼
    confidence >= 0.9?
        │
    ┌───┴───┐
   Yes      No
    │       │
    ▼       ▼
  直接   ┌───────────────────┐
  返回   │   3. LLM 选择      │ ← LLMCandidateSelector
        │   从候选中选择      │
        └───────────────────┘
        │
        ▼
    缓存结果
```

**输出**:
```python
{
    "mapped_query": MappedQuery,  # 包含 field_mappings
    "field_mapper_complete": True,
}
```

### 5.3 QueryBuilder Node

**职责**: 将 MappedQuery 转换为 VizQL 请求

```python
async def build(self, mapped_query: MappedQuery) -> VizQLQueryModel:
    # 1. 应用字段映射
    mapped_semantic_query = self._apply_field_mappings(
        mapped_query.semantic_query,
        mapped_query.field_mappings
    )
    
    # 2. 使用 TableauQueryBuilder 构建 VizQL
    vizql_request = self._query_builder.build(mapped_semantic_query)
    
    # 3. 返回 VizQLQuery Pydantic 模型
    return VizQLQueryModel(
        fields=vizql_request.get("fields", []),
        filters=vizql_request.get("filters"),
    )
```

### 5.4 Execute Node

**职责**: 执行 VizQL API 调用

```python
async def execute_node(state, config):
    # 1. 获取认证
    auth_ctx = await ensure_valid_auth_async(config)
    
    # 2. 执行查询
    executor = ExecuteNode()
    result = await executor.execute(
        vizql_query=vizql_query,
        datasource_luid=datasource_luid,
        api_key=auth_ctx.api_key,
        site=auth_ctx.site,
    )
    
    return {"query_result": result}
```

### 5.5 Insight Node

**职责**: 分析查询结果，生成洞察

**组件**:
- Profiler: 数据画像
- AnomalyDetector: 异常检测
- StatisticalAnalyzer: 统计分析
- Synthesizer: 洞察合成

**输出**:
```python
{
    "insights": List[Insight],
    "all_insights": List[Insight],  # 累积
    "data_insight_profile": Dict,   # 用于 Replanner
    "messages": List[BaseMessage],  # 添加到对话历史
    "answered_questions": [question],
}
```

### 5.6 Replanner Node

**职责**: 评估完成度，生成探索问题

```python
async def replanner_node(state):
    replanner = ReplannerAgent(max_replan_rounds=3)
    
    decision = await replanner.replan(
        original_question=question,
        insights=insights,
        data_insight_profile=data_insight_profile,
        dimension_hierarchy=dimension_hierarchy,
        answered_questions=answered_questions,
    )
    
    if decision.should_replan and decision.exploration_questions:
        next_question = decision.exploration_questions[0].question
        return {
            "replan_decision": decision,
            "question": next_question,  # 更新问题
            "messages": [HumanMessage(content=next_question)],
        }
    
    return {"replan_decision": decision}
```


---

## 6. 中间件系统

### 6.1 中间件栈

```python
def create_middleware_stack(model_name, config, chat_model):
    middleware = []
    
    # 1. TodoListMiddleware - 任务队列
    middleware.append(TodoListMiddleware())
    
    # 2. SummarizationMiddleware - 对话摘要
    middleware.append(SummarizationMiddleware(
        model=summarization_model,
        trigger=("tokens", 60000),  # 超过 60K tokens 触发
        keep=("messages", 10),      # 保留最近 10 条
    ))
    
    # 3. ModelRetryMiddleware - LLM 重试
    middleware.append(ModelRetryMiddleware(
        max_retries=3,
        initial_delay=1.0,
        backoff_factor=2.0,  # 1s, 2s, 4s
        jitter=True,
    ))
    
    # 4. ToolRetryMiddleware - 工具重试
    middleware.append(ToolRetryMiddleware(
        max_retries=2,
        initial_delay=1.0,
        backoff_factor=2.0,
    ))
    
    # 5. FilesystemMiddleware - 大结果保存
    middleware.append(FilesystemMiddleware(
        tool_token_limit_before_evict=10000,
    ))
    
    # 6. PatchToolCallsMiddleware - 修复悬空调用
    middleware.append(PatchToolCallsMiddleware())
    
    # 7. OutputValidationMiddleware - 输出校验
    middleware.append(OutputValidationMiddleware(
        strict=False,
        retry_on_failure=True,
    ))
    
    # 8. HumanInTheLoopMiddleware - 人工确认（可选）
    if config.get("interrupt_on"):
        middleware.append(HumanInTheLoopMiddleware(
            interrupt_on=config["interrupt_on"]
        ))
    
    return middleware
```

### 6.2 中间件钩子

| 中间件 | 钩子 | 触发时机 |
|--------|------|----------|
| SummarizationMiddleware | wrap_model_call | LLM 调用前，检查 token 数量 |
| ModelRetryMiddleware | awrap_model_call | LLM 调用失败时重试 |
| ToolRetryMiddleware | awrap_tool_call | 工具调用失败时重试 |
| FilesystemMiddleware | wrap_model_call | 注入 system_prompt |
| FilesystemMiddleware | awrap_tool_call | 拦截大结果，保存到文件 |
| OutputValidationMiddleware | aafter_model | LLM 输出后校验 JSON |
| PatchToolCallsMiddleware | aafter_agent | 修复悬空的工具调用 |

---

## 7. 缓存系统

### 7.1 StoreManager (SQLite)

```python
class StoreManager:
    """基于 SQLite 的统一存储管理器"""
    
    def __init__(self, db_path="data/business_cache.db"):
        self._conn = sqlite3.connect(db_path)
        self._create_tables()
    
    # 元数据缓存
    def put_metadata(self, datasource_luid: str, metadata: Metadata): ...
    def get_metadata(self, datasource_luid: str) -> Optional[Metadata]: ...
    
    # 维度层级缓存
    def put_dimension_hierarchy(self, datasource_luid: str, hierarchy: Dict): ...
    def get_dimension_hierarchy(self, datasource_luid: str) -> Optional[Dict]: ...
    
    # 通用 KV 存储
    def put(self, namespace: Tuple[str, ...], key: str, value: Any, ttl: int = None): ...
    def get(self, namespace: Tuple[str, ...], key: str) -> Optional[StoreItem]: ...
```

### 7.2 字段映射缓存

```python
class FieldMapperNode:
    def _get_from_cache(self, term: str, datasource_luid: str):
        key = hashlib.md5(f"{datasource_luid}:{term.lower()}".encode()).hexdigest()
        item = self._store_manager.get(
            namespace=("field_mapping", datasource_luid),
            key=key
        )
        return CachedMapping(...) if item else None
    
    def _put_to_cache(self, term, datasource_luid, technical_field, confidence):
        self._store_manager.put(
            namespace=("field_mapping", datasource_luid),
            key=key,
            value={...},
            ttl=24 * 60 * 60  # 24 小时
        )
```

### 7.3 LLM 响应缓存

```python
from langchain_core.globals import set_llm_cache
from langchain_community.cache import SQLiteCache

set_llm_cache(SQLiteCache(database_path="data/llm_cache.db"))
```

---

## 8. 预加载服务

### 8.1 PreloadService 架构

```
Tableau 看板打开
        │
        ▼
┌───────────────────┐
│  PreloadService   │
│  start_preload()  │
└───────────────────┘
        │
        ▼
    缓存有效?
        │
    ┌───┴───┐
   Yes      No
    │       │
    ▼       ▼
  返回   ┌───────────────────┐
  READY  │  后台任务执行      │
        │  asyncio.create_task │
        └───────────────────┘
                │
                ▼
        ┌───────────────────┐
        │ 1. 获取 Tableau 认证 │
        │ 2. 获取元数据        │
        │ 3. 推断维度层级      │
        │ 4. 缓存结果          │
        └───────────────────┘
```

### 8.2 预热状态

```python
class PreloadStatus(str, Enum):
    PENDING = "pending"      # 等待开始
    LOADING = "loading"      # 正在加载
    READY = "ready"          # 已就绪
    FAILED = "failed"        # 失败
    EXPIRED = "expired"      # 已过期
```


---

## 9. 错误处理

### 9.1 错误分类

```python
class ErrorCategory(str, Enum):
    TRANSIENT = "transient"  # 可重试（网络超时、限流）
    PERMANENT = "permanent"  # 不可重试（配置错误、认证失败）
    USER = "user"            # 需用户操作（输入无效、字段不存在）
```

### 9.2 异常类型

```python
# VizQL API 异常
class VizQLError(Exception): ...
class VizQLAuthError(VizQLError): ...
class VizQLValidationError(VizQLError): ...
class VizQLServerError(VizQLError): ...
class VizQLRateLimitError(VizQLError): ...
class VizQLTimeoutError(VizQLError): ...

# 通用异常
class TransientError(Exception): ...
class PermanentError(Exception): ...
class UserError(Exception): ...
```

### 9.3 错误处理策略

| 错误类型 | 处理策略 |
|----------|----------|
| TransientError | 指数退避重试（1s, 2s, 4s），最多 3 次 |
| PermanentError | 立即终止，记录日志，返回清晰消息 |
| UserError | 返回用户友好消息和建议 |

---

## 10. API 接口

### 10.1 聊天 API

```python
@router.post("/api/chat")
async def chat_query(request: ChatRequest) -> ChatResponse:
    """同步查询 API"""
    executor = WorkflowExecutor(datasource_luid=datasource_luid)
    result = await executor.run(question=request.question)
    return ChatResponse(
        executive_summary=...,
        key_findings=...,
        analysis_path=...,
    )

@router.post("/api/chat/stream")
async def chat_query_stream(request: ChatRequest):
    """流式查询 API (SSE)"""
    return StreamingResponse(
        generate_sse_events(question, session_id, datasource_luid),
        media_type="text/event-stream",
    )
```

### 10.2 健康检查

```python
@router.get("/api/health")
async def health_check():
    """检查 LLM、Tableau API、存储服务状态"""
    return {
        "status": "healthy" | "degraded" | "unhealthy",
        "checks": {
            "llm": {"status": "ok", "message": "..."},
            "tableau": {"status": "ok", "message": "..."},
            "storage": {"status": "ok", "message": "..."},
        }
    }
```

---

## 11. 目录结构

```
src/
├── core/                              # 核心层（平台无关）
│   ├── models/                        # 核心数据模型
│   │   ├── enums.py                   # 公共枚举
│   │   ├── fields.py                  # DimensionField, MeasureField
│   │   ├── computations.py            # Computation
│   │   ├── filters.py                 # Filter 及其子类
│   │   ├── query.py                   # SemanticQuery
│   │   ├── field_mapping.py           # MappedQuery, FieldMapping
│   │   ├── step1.py                   # Step1Output
│   │   ├── step2.py                   # Step2Output
│   │   ├── observer.py                # ObserverOutput
│   │   ├── parse_result.py            # SemanticParseResult
│   │   ├── insight.py                 # Insight, InsightResult
│   │   └── replan.py                  # ReplanDecision
│   └── interfaces/                    # 抽象接口
│       ├── platform_adapter.py
│       ├── query_builder.py
│       └── field_mapper.py
│
├── platforms/                         # 平台层
│   └── tableau/                       # Tableau 实现
│       ├── adapter.py
│       ├── query_builder.py           # TableauQueryBuilder
│       ├── field_mapper.py
│       ├── vizql_client.py            # VizQL API 客户端
│       ├── auth.py                    # 认证管理
│       ├── metadata.py                # 元数据获取
│       └── models/                    # Tableau 特定模型
│           ├── vizql_types.py
│           └── execute_result.py
│
├── agents/                            # Agent 层
│   ├── base/                          # 基础组件
│   │   ├── node.py
│   │   ├── prompt.py
│   │   └── middleware_runner.py
│   ├── semantic_parser/               # 语义解析 Agent
│   │   ├── agent.py                   # SemanticParserAgent
│   │   ├── node.py                    # semantic_parser_node
│   │   ├── components/                # Step1, Step2, Observer
│   │   └── prompts/
│   ├── field_mapper/                  # 字段映射
│   │   ├── node.py                    # FieldMapperNode
│   │   └── llm_selector.py
│   ├── insight/                       # 洞察 Agent
│   │   ├── node.py
│   │   └── components/
│   ├── replanner/                     # 重规划 Agent
│   │   ├── agent.py
│   │   └── prompt.py
│   └── dimension_hierarchy/           # 维度层级推断
│
├── nodes/                             # 非 Agent 节点
│   ├── query_builder/                 # 查询构建
│   │   └── node.py
│   └── execute/                       # 查询执行
│       └── node.py
│
├── orchestration/                     # 编排层
│   ├── workflow/                      # LangGraph 工作流
│   │   ├── factory.py                 # create_workflow()
│   │   ├── executor.py                # WorkflowExecutor
│   │   ├── context.py                 # WorkflowContext
│   │   ├── routes.py                  # 路由逻辑
│   │   └── state.py                   # VizQLState
│   ├── tools/                         # 工具定义
│   │   ├── registry.py
│   │   ├── data_model_tool.py
│   │   └── schema_tool.py
│   └── middleware/                    # 中间件
│       ├── filesystem.py
│       ├── output_validation.py
│       ├── patch_tool_calls.py
│       └── backends/
│
├── infra/                             # 基础设施层
│   ├── ai/                            # AI 模型管理
│   │   ├── llm.py                     # LLM 客户端
│   │   ├── embeddings.py
│   │   ├── reranker.py
│   │   └── rag/                       # RAG 组件
│   │       ├── assembler.py
│   │       ├── field_indexer.py
│   │       ├── semantic_mapper.py
│   │       └── reranker.py
│   ├── storage/                       # 存储管理
│   │   └── store_manager.py
│   ├── config/                        # 配置管理
│   │   └── settings.py
│   ├── monitoring/                    # 监控
│   │   └── callbacks.py
│   ├── errors.py                      # 错误类型
│   └── exceptions.py                  # 异常定义
│
└── api/                               # 服务层
    ├── chat.py                        # 聊天 API
    ├── models.py                      # API 模型
    ├── preload.py                     # 预加载 API
    └── preload_service.py             # 预加载服务
```


---

## 12. 配置说明

### 12.1 环境变量 (.env)

```bash
# Tableau 配置
TABLEAU_DOMAIN=https://xxx.tableau.com
TABLEAU_SITE=xxx
TABLEAU_API_VERSION=3.24
TABLEAU_USER=xxx
TABLEAU_JWT_CLIENT_ID=xxx
TABLEAU_JWT_SECRET_ID=xxx
TABLEAU_JWT_SECRET=xxx
DATASOURCE_LUID=xxx

# LLM 配置
LLM_MODEL_PROVIDER=qwen           # qwen, deepseek, openai
LLM_API_BASE=http://localhost:8000/v1
LLM_API_KEY=xxx
LLM_TEMPERATURE=0.2
TOOLING_LLM_MODEL=qwen3-30b       # 工具模型（轻量）
EMBEDDING_MODEL=text-embedding-3-small

# 中间件配置
SUMMARIZATION_TOKEN_THRESHOLD=20000  # 摘要触发阈值
MESSAGES_TO_KEEP=10                  # 保留消息数
MODEL_MAX_RETRIES=3                  # LLM 重试次数
TOOL_MAX_RETRIES=3                   # 工具重试次数
FILESYSTEM_TOKEN_LIMIT=20000         # 大结果保存阈值

# 工作流配置
MAX_REPLAN_ROUNDS=3                  # 最大重规划轮数

# 缓存配置
METADATA_CACHE_TTL=86400             # 元数据缓存 TTL（秒）
DIMENSION_HIERARCHY_CACHE_TTL=86400  # 维度层级缓存 TTL

# API 配置
HOST=127.0.0.1
PORT=8000
CORS_ORIGINS=https://localhost:5173

# VizQL 配置
VIZQL_RETURN_FORMAT=OBJECTS
VIZQL_TIMEOUT=30
VIZQL_MAX_RETRIES=3
DECIMAL_PRECISION=2
```

### 12.2 中间件配置详解

| 中间件 | 配置项 | 默认值 | 说明 |
|--------|--------|--------|------|
| SummarizationMiddleware | summarization_token_threshold | 20000 | 超过此 token 数触发摘要 |
| SummarizationMiddleware | messages_to_keep | 10 | 摘要后保留的消息数 |
| ModelRetryMiddleware | model_max_retries | 3 | LLM 调用最大重试次数 |
| ModelRetryMiddleware | model_backoff_factor | 2.0 | 指数退避因子 |
| ToolRetryMiddleware | tool_max_retries | 3 | 工具调用最大重试次数 |
| FilesystemMiddleware | filesystem_token_limit | 20000 | 超过此大小保存到文件 |
| HumanInTheLoopMiddleware | interrupt_on | [] | 需要人工确认的工具列表 |

---

## 13. 完整执行流程

### 13.1 工作流执行代码

```python
# 1. 创建执行器
executor = WorkflowExecutor(datasource_luid="xxx", max_replan_rounds=3)

# 2. 执行
result = await executor.run("各产品类别的销售额是多少?")

# 内部流程:
# 2.1 获取 Tableau 认证
auth_ctx = await get_tableau_auth_async()

# 2.2 创建 WorkflowContext
ctx = WorkflowContext(auth=auth_ctx, store=store, datasource_luid=ds_luid)

# 2.3 加载元数据（从缓存或 API）
ctx = await ctx.ensure_metadata_loaded()

# 2.4 创建配置
config = create_workflow_config(thread_id, ctx)

# 2.5 构建初始状态
state = {
    "question": question,
    "messages": [],
    "metadata": ctx.metadata,
    "dimension_hierarchy": ctx.dimension_hierarchy,
}

# 2.6 执行工作流
result = await workflow.ainvoke(state, config)
```

### 13.2 完整数据流图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              用户问题                                        │
│                    "各省份2024年销售额排名"                                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         1. SemanticParser Node                               │
│                      (SemanticParserAgent)                                   │
│                                                                              │
│  Step 1: 语义理解                                                            │
│  ├─ restated_question: "按省份分组，计算2024年销售额总和，并按销售额降序排名"   │
│  ├─ what: {measures: [{field: "销售额", aggregation: SUM}]}                  │
│  ├─ where: {dimensions: [{field: "省份"}], filters: [{field: "年份", ...}]}  │
│  ├─ how_type: RANKING                                                        │
│  └─ intent: {type: DATA_QUERY}                                               │
│                                                                              │
│  Step 2: 计算推理                                                            │
│  └─ computations: [{target: "销售额", partition_by: [], operation: RANK}]    │
│                                                                              │
│  输出: SemanticQuery                                                         │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         2. FieldMapper Node                                  │
│                      (RAG + LLM Hybrid)                                      │
│                                                                              │
│  映射业务术语 → 技术字段名:                                                   │
│  ├─ "销售额" → "Sales" (confidence: 0.95, source: rag_direct)               │
│  ├─ "省份" → "State/Province" (confidence: 0.92, source: rag_direct)        │
│  └─ "年份" → "Order Date" (confidence: 0.88, source: rag_llm_fallback)      │
│                                                                              │
│  输出: MappedQuery                                                           │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         3. QueryBuilder Node                                 │
│                      (TableauQueryBuilder)                                   │
│                                                                              │
│  MappedQuery → VizQL 请求:                                                   │
│  ├─ fields: [{fieldCaption: "State/Province"}, {fieldCaption: "Sales", ...}]│
│  └─ filters: [{field: "Order Date", filterType: "QUANTITATIVE_DATE", ...}]  │
│                                                                              │
│  输出: VizQLQueryRequest                                                     │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         4. Execute Node                                      │
│                      (VizQL API Client)                                      │
│                                                                              │
│  执行 VizQL 查询:                                                            │
│  ├─ 认证: TableauAuthContext (自动刷新)                                      │
│  ├─ API: POST /api/v1/vizql-data-service/query-datasource                   │
│  └─ 响应解析: data, columns, row_count                                       │
│                                                                              │
│  输出: ExecuteResult                                                         │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         5. Insight Node                                      │
│                      (InsightAgent)                                          │
│                                                                              │
│  数据分析:                                                                   │
│  ├─ 数据画像 (Profiler)                                                     │
│  ├─ 异常检测 (AnomalyDetector)                                              │
│  ├─ 统计分析 (StatisticalAnalyzer)                                          │
│  └─ 洞察合成 (Synthesizer)                                                  │
│                                                                              │
│  输出: List[Insight], data_insight_profile                                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         6. Replanner Node                                    │
│                      (ReplannerAgent)                                        │
│                                                                              │
│  重规划决策:                                                                 │
│  ├─ 评估完成度 (completeness_score)                                         │
│  ├─ 识别缺失方面 (missing_aspects)                                          │
│  ├─ 生成探索问题 (exploration_questions)                                    │
│  └─ 路由决策: should_replan=True → Understanding, False → END               │
│                                                                              │
│  输出: ReplanDecision                                                        │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                            ┌───────┴───────┐
                            │               │
                    should_replan?          │
                            │               │
                        ┌───┴───┐           │
                       Yes      No          │
                        │       │           │
                        ▼       ▼           │
                  回到 Understanding    结束 ◄─┘
```

---

## 14. 监控与日志

### 14.1 LangChain Callbacks

```python
class SQLiteTrackingCallback(BaseCallbackHandler):
    """基于 SQLite 的追踪 Callback"""
    
    def on_llm_start(self, serialized, prompts, *, run_id, ...):
        # 记录 LLM 调用开始
        
    def on_llm_end(self, response, *, run_id, ...):
        # 记录 token 使用、延迟等
        
    def on_llm_error(self, error, *, run_id, ...):
        # 记录错误
```

### 14.2 性能指标

| 指标 | 说明 |
|------|------|
| total_calls | LLM 调用总数 |
| total_tokens | Token 消耗总量 |
| avg_duration_ms | 平均响应时间 |
| cache_hit_rate | 缓存命中率 |
| fast_path_hits | RAG 快速路径命中数 |
| llm_fallback_count | LLM 回退次数 |
