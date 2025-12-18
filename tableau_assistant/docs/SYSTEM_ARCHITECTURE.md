# Tableau Assistant 系统架构详解

## 1. Graph 编排详解

### 1.1 工作流构建 (factory.py)

```python
# 创建 StateGraph
graph = StateGraph(VizQLState)

# 添加 6 个节点
graph.add_node("understanding", _semantic_parser_node)
graph.add_node("field_mapper", _field_mapper_node)
graph.add_node("query_builder", _query_builder_node)
graph.add_node("execute", _execute_node)
graph.add_node("insight", _insight_node)
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

# 编译
compiled_graph = graph.compile(checkpointer=MemorySaver())
```

### 1.2 路由逻辑 (routes.py)

**route_after_understanding:**
```python
def route_after_understanding(state) -> Literal["field_mapper", "end"]:
    # 新架构：检查 semantic_parse_result.intent.type
    if semantic_parse_result is not None:
        if intent_type == IntentType.DATA_QUERY:
            return "field_mapper"
        else:  # CLARIFICATION/GENERAL/IRRELEVANT
            return "end"
    
    # 旧架构兼容：检查 is_analysis_question
    if is_analysis_question:
        return "field_mapper"
    return "end"
```

**route_after_replanner:**
```python
def route_after_replanner(state, max_replan_rounds=3) -> Literal["understanding", "end"]:
    if replan_count >= max_replan_rounds:
        return "end"  # 达到最大轮数
    if should_replan:
        return "understanding"  # 继续探索
    return "end"  # 分析完成
```

---

## 2. 中间件详解

### 2.1 中间件栈创建

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
    
    return middleware
```

### 2.2 中间件钩子

| 中间件 | 钩子 | 触发时机 |
|--------|------|----------|
| SummarizationMiddleware | wrap_model_call | LLM 调用前，检查 token 数量 |
| ModelRetryMiddleware | awrap_model_call | LLM 调用失败时重试 |
| ToolRetryMiddleware | awrap_tool_call | 工具调用失败时重试 |
| FilesystemMiddleware | wrap_model_call | 注入 system_prompt |
| FilesystemMiddleware | awrap_tool_call | 拦截大结果，保存到文件 |
| OutputValidationMiddleware | aafter_model | LLM 输出后校验 JSON |
| OutputValidationMiddleware | aafter_agent | Agent 完成后校验状态 |

### 2.3 FilesystemMiddleware 详解

**大结果自动保存:**
```python
def _intercept_large_tool_result(self, tool_result, runtime):
    if len(content) > 4 * self.tool_token_limit_before_evict:  # > 40K chars
        file_path = f"/large_tool_results/{sanitized_id}"
        resolved_backend.write(file_path, content)
        return ToolMessage(
            f"Tool result too large, saved at: {file_path}\n"
            f"Use read_file with offset and limit to read parts."
        )
```

**提供的工具:**
- `ls`: 列出目录
- `read_file`: 读取文件（支持 offset/limit 分页）
- `write_file`: 写入文件
- `edit_file`: 编辑文件
- `glob`: 文件匹配
- `grep`: 文本搜索

### 2.4 OutputValidationMiddleware 详解

```python
async def aafter_model(self, response, request, state, runtime):
    # 1. 提取 JSON
    json_str = self._extract_json(content)  # 支持 ```json``` 和裸 JSON
    parsed = json.loads(json_str)
    
    # 2. Pydantic 校验
    validated = self.expected_schema.model_validate(parsed)
    return {"validated_output": validated}
    
    # 3. 校验失败处理
    if self.retry_on_failure:
        raise OutputValidationError(...)  # 触发 ModelRetryMiddleware
```

---

## 3. 工具系统详解

### 3.1 工具注册表 (registry.py)

```python
class ToolRegistry:
    """单例模式的工具注册表"""
    
    def __init__(self):
        self._tools = {
            NodeType.UNDERSTANDING: [],
            NodeType.INSIGHT: [],
            NodeType.REPLANNER: [],
        }
        self._tool_map = {}
        self._dependencies = {}
    
    def auto_discover(self):
        """自动发现并注册工具"""
        # 数据模型工具
        from .data_model_tool import get_data_model
        self.register(NodeType.UNDERSTANDING, get_data_model,
            dependencies=["data_model_manager"],
            tags=["data_model", "metadata"])
        
        # Schema 工具
        from .schema_tool import get_schema_module
        self.register(NodeType.UNDERSTANDING, get_schema_module,
            tags=["schema", "token_optimization"])
        
        # 日期工具
        from .date_tool import process_time_filter, calculate_relative_dates
        self.register(NodeType.UNDERSTANDING, process_time_filter,
            dependencies=["date_manager"], tags=["date"])
```

### 3.2 工具使用方式

```python
# 获取节点的工具
tools = get_tools_for_node(NodeType.UNDERSTANDING)

# 在 Agent 中使用
agent = create_react_agent(llm, tools)
```

---

## 4. 元数据管理

### 4.1 元数据加载流程 (context.py)

```python
async def ensure_metadata_loaded(self, timeout=60.0):
    """确保数据模型已加载"""
    
    # 1. 检查缓存
    if self.metadata is not None:
        if self.metadata.dimension_hierarchy:
            return self
        # 维度层级为空，重新推断
        metadata = await self._ensure_hierarchy_exists(self.metadata)
        return self._with_metadata(metadata)
    
    # 2. 检查预热服务
    preload_service = get_preload_service()
    cache_status = preload_service.get_cache_status(self.datasource_luid)
    
    if cache_status["is_valid"]:
        # 从缓存获取
        metadata = await self._load_metadata_from_cache()
        return self._with_metadata(metadata)
    
    # 3. 检查预热任务
    task_id, status = await preload_service.start_preload(datasource_luid)
    
    if status == PreloadStatus.LOADING:
        # 等待预热完成
        metadata = await self._wait_for_preload(task_id, timeout)
        return self._with_metadata(metadata)
    
    # 4. 同步加载
    metadata = await self._load_metadata_sync()
    return self._with_metadata(metadata)
```

### 4.2 元数据结构

```python
class Metadata(BaseModel):
    datasource_luid: str
    datasource_name: str
    datasource_description: Optional[str]
    fields: List[FieldMetadata]
    field_count: int
    dimension_hierarchy: Optional[Dict[str, Dict]]  # 维度层级
    data_model: Optional[Dict]  # 逻辑表和关系
```

---

## 5. 缓存管理

### 5.1 StoreManager (store_manager.py)

```python
class StoreManager:
    """基于 SQLite 的统一存储管理器"""
    
    def __init__(self, db_path="data/business_cache.db"):
        self._conn = sqlite3.connect(db_path)
        self._create_tables()
    
    # 元数据缓存
    def put_metadata(self, datasource_luid: str, metadata: Metadata):
        """缓存元数据"""
        
    def get_metadata(self, datasource_luid: str) -> Optional[Metadata]:
        """获取缓存的元数据"""
    
    # 维度层级缓存
    def put_dimension_hierarchy(self, datasource_luid: str, hierarchy: Dict):
        """缓存维度层级"""
        
    def get_dimension_hierarchy(self, datasource_luid: str) -> Optional[Dict]:
        """获取缓存的维度层级"""
    
    # 通用 KV 存储
    def put(self, namespace: Tuple[str, ...], key: str, value: Any, ttl: int = None):
        """存储键值对"""
        
    def get(self, namespace: Tuple[str, ...], key: str) -> Optional[StoreItem]:
        """获取键值对"""
```

### 5.2 字段映射缓存 (field_mapper/node.py)

```python
class FieldMapperNode:
    def _get_from_cache(self, term: str, datasource_luid: str):
        """从缓存获取映射"""
        key = hashlib.md5(f"{datasource_luid}:{term.lower()}".encode()).hexdigest()
        item = self._store_manager.get(
            namespace=("field_mapping", datasource_luid),
            key=key
        )
        return CachedMapping(...) if item else None
    
    def _put_to_cache(self, term, datasource_luid, technical_field, confidence):
        """保存映射到缓存"""
        self._store_manager.put(
            namespace=("field_mapping", datasource_luid),
            key=key,
            value={...},
            ttl=24 * 60 * 60  # 24 小时
        )
```

### 5.3 LLM 响应缓存

```python
from tableau_assistant.src.infra.storage import setup_llm_cache

# 初始化 LLM 缓存
setup_llm_cache(db_path="data/llm_cache.db")

# 内部使用 LangChain 的 SQLiteCache
from langchain_core.globals import set_llm_cache
from langchain_community.cache import SQLiteCache
set_llm_cache(SQLiteCache(database_path=db_path))
```

---

## 6. 上下文管理

### 6.1 WorkflowContext

```python
class WorkflowContext(BaseModel):
    """统一的依赖容器"""
    
    auth: TableauAuthContext      # Tableau 认证
    store: StoreManager           # 持久化存储
    datasource_luid: str          # 数据源 LUID
    metadata: Optional[Metadata]  # 数据模型
    max_replan_rounds: int = 3
    user_id: Optional[str] = None
    metadata_load_status: Optional[MetadataLoadStatus]
    
    def is_auth_valid(self, buffer_seconds=60) -> bool:
        """检查认证是否有效"""
        return not self.auth.is_expired(buffer_seconds)
    
    async def refresh_auth_if_needed(self) -> "WorkflowContext":
        """刷新认证（返回新实例）"""
        if self.is_auth_valid():
            return self
        new_auth = await get_tableau_auth_async(force_refresh=True)
        return WorkflowContext(auth=new_auth, ...)
```

### 6.2 上下文传递

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

## 7. 各节点输入输出详解

### 7.1 Understanding (SemanticParserNode)

**输入:**
```python
state = {
    "question": str,           # 用户问题
    "messages": List[BaseMessage],  # 对话历史
    "metadata": Metadata,      # 数据源元数据
}
```

**处理逻辑:**
```python
async def semantic_parser_node(state, config):
    # 1. 转换消息为历史格式
    history = _convert_messages_to_history(messages[-10:])
    
    # 2. 执行 SemanticParserAgent
    agent = SemanticParserAgent()
    result = await agent.parse(question, history, metadata)
    
    # 3. 根据意图分支
    if intent_type == IntentType.DATA_QUERY:
        return {"semantic_query": result.semantic_query, "is_analysis_question": True}
    elif intent_type == IntentType.CLARIFICATION:
        return {"clarification": result.clarification, "is_analysis_question": False}
    elif intent_type == IntentType.GENERAL:
        return {"general_response": result.general_response, "is_analysis_question": False}
    else:  # IRRELEVANT
        return {"is_analysis_question": False, "non_analysis_response": "..."}
```

**输出:**
```python
{
    "semantic_parse_result": SemanticParseResult,
    "semantic_query": SemanticQuery | None,
    "restated_question": str,
    "is_analysis_question": bool,
    "clarification": ClarificationQuestion | None,
    "general_response": str | None,
    "understanding_complete": True,
}
```

### 7.2 FieldMapper

**输入:**
```python
state = {
    "semantic_query": SemanticQuery,  # 业务术语
    "metadata": Metadata,
    "datasource": str,
    "question": str,  # 用于上下文
}
```

**处理逻辑:**
```python
async def field_mapper_node(state, config):
    # 1. 提取需要映射的术语
    terms_to_map = _extract_terms_from_semantic_query(semantic_query)
    # {"销售额": "measure", "省份": "dimension", ...}
    
    # 2. 批量映射
    mapper = _get_field_mapper(state)  # 初始化 RAG 索引
    mapping_results = await mapper.map_fields_batch(
        terms=list(terms_to_map.keys()),
        datasource_luid=datasource_luid,
        context=question,
        role_filters=terms_to_map
    )
    
    # 3. 构建 MappedQuery
    field_mappings = {term: FieldMapping(...) for term, result in mapping_results.items()}
    mapped_query = MappedQuery(semantic_query=semantic_query, field_mappings=field_mappings)
```

**映射策略:**
```python
async def map_field(self, term, datasource_luid, context, role_filter):
    # 1. 缓存查找
    cached = self._get_from_cache(term, datasource_luid)
    if cached:
        return MappingResult(mapping_source="cache_hit", ...)
    
    # 2. RAG 检索
    rag_result = self.semantic_mapper.map_field(term, context, role_filter)
    
    # 3. 高置信度快速路径
    if rag_result.confidence >= 0.9:
        self._put_to_cache(...)
        return MappingResult(mapping_source="rag_direct", ...)
    
    # 4. LLM 候选选择
    if rag_result.confidence < 0.9:
        candidates = self._convert_to_candidates(rag_result.retrieval_results)
        selection = await self.llm_selector.select(term, candidates, context)
        return MappingResult(mapping_source="rag_llm_fallback", ...)
```

**输出:**
```python
{
    "mapped_query": MappedQuery,
    "field_mapper_complete": True,
}
```

### 7.3 QueryBuilder

**输入:**
```python
state = {
    "mapped_query": MappedQuery,  # 包含字段映射
}
```

**处理逻辑:**
```python
async def query_builder_node(state, config):
    builder = QueryBuilderNode()
    vizql_query = await builder.build(mapped_query)
    
async def build(self, mapped_query):
    # 1. 应用字段映射
    mapped_semantic_query = self._apply_field_mappings(
        mapped_query.semantic_query,
        mapped_query.field_mappings
    )
    
    # 2. 使用 TableauQueryBuilder 构建 VizQL
    vizql_request = self._query_builder.build(mapped_semantic_query)
    
    # 3. 转换为 Pydantic 模型
    return VizQLQueryRequest(
        fields=vizql_request.get("fields", []),
        filters=vizql_request.get("filters"),
    )
```

**输出:**
```python
{
    "vizql_query": VizQLQueryRequest,
    "query_builder_complete": True,
}
```

### 7.4 Execute

**输入:**
```python
state = {
    "vizql_query": VizQLQueryRequest,
    "datasource": str,
    "metadata": Metadata,
}
config = {
    "configurable": {
        "tableau_auth": {...},
        "workflow_context": WorkflowContext,
    }
}
```

**处理逻辑:**
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
    
    # 3. 解析响应
    return {"query_result": result}
```

**输出:**
```python
{
    "query_result": ExecuteResult,  # data, columns, row_count, execution_time
    "execute_complete": True,
}
```

### 7.5 Insight

**输入:**
```python
state = {
    "query_result": ExecuteResult,
    "question": str,
    "semantic_query": SemanticQuery,
    "dimension_hierarchy": Dict,
}
```

**处理逻辑:**
```python
async def insight_node(state, config):
    # 1. 构建上下文
    context = {
        "question": question,
        "dimensions": [{"name": d.name} for d in semantic_query.dimensions],
        "measures": [{"name": m.name} for m in semantic_query.measures],
    }
    
    # 2. 执行分析
    agent = InsightAgent(dimension_hierarchy=dimension_hierarchy)
    result = await agent.analyze(query_result, context)
    
    # 3. 生成对话历史消息
    new_messages = [
        HumanMessage(content=question, additional_kwargs={"source": "insight_input"}),
        AIMessage(content=summary_content, additional_kwargs={"source": "insight"}),
    ]
```

**输出:**
```python
{
    "insights": List[Insight],
    "all_insights": List[Insight],  # 累积
    "data_insight_profile": Dict,   # 用于 Replanner
    "current_dimensions": List[str],
    "messages": List[BaseMessage],  # 添加到对话历史
    "answered_questions": [question],  # 用于去重
    "insight_complete": True,
}
```

### 7.6 Replanner

**输入:**
```python
state = {
    "question": str,
    "insights": List[Insight],
    "data_insight_profile": Dict,
    "dimension_hierarchy": Dict,
    "current_dimensions": List[str],
    "answered_questions": List[str],
    "replan_count": int,
}
```

**处理逻辑:**
```python
async def replanner_node(state):
    # 1. 边界处理
    if not insights:
        return {"replan_decision": ReplanDecision(should_replan=False, ...)}
    
    # 2. 执行重规划
    replanner = ReplannerAgent(max_replan_rounds=3)
    decision = await replanner.replan(
        original_question=question,
        insights=insights,
        data_insight_profile=data_insight_profile,
        dimension_hierarchy=dimension_hierarchy,
        current_dimensions=current_dimensions,
        answered_questions=answered_questions,
    )
    
    # 3. 如果需要重规划，设置下一个问题
    if decision.should_replan and decision.exploration_questions:
        next_question = decision.exploration_questions[0].question
        return {
            "replan_decision": decision,
            "question": next_question,  # 更新问题
            "messages": [HumanMessage(content=next_question, ...)],
        }
```

**输出:**
```python
{
    "replan_decision": ReplanDecision,
    "replan_count": int,
    "replan_history": List[Dict],
    "question": str,  # 可能更新为探索问题
    "messages": List[BaseMessage],
    "pending_questions": List[Dict],
}
```

---

## 8. RAG 系统详解

### 8.1 FieldMapper 架构

FieldMapper 使用 RAG + LLM 混合策略将业务术语映射到技术字段名：

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

### 8.2 映射策略代码

```python
async def map_field(self, term, datasource_luid, context, role_filter):
    # 1. 缓存查找（最快）
    cached = self._get_from_cache(term, datasource_luid)
    if cached:
        return MappingResult(mapping_source="cache_hit", ...)
    
    # 2. RAG 检索
    rag_result = self.semantic_mapper.map_field(term, context, role_filter)
    
    # 3. 高置信度快速路径（confidence >= 0.9）
    if rag_result.confidence >= HIGH_CONFIDENCE_THRESHOLD:
        self._put_to_cache(...)
        return MappingResult(mapping_source="rag_direct", ...)
    
    # 4. LLM 候选选择（confidence < 0.9）
    candidates = self._convert_to_candidates(rag_result.retrieval_results)
    selection = await self.llm_selector.select(term, candidates, context)
    
    self._put_to_cache(...)
    return MappingResult(mapping_source="rag_llm_fallback", ...)
```

### 8.3 KnowledgeAssembler

```python
class KnowledgeAssembler:
    """元数据知识组装器"""
    
    def __init__(self, datasource_luid, config, embedding_provider):
        self.chunk_strategy = config.chunk_strategy  # BY_FIELD
        self.max_samples = config.max_samples        # 5
    
    def load_metadata(self, fields: List[FieldMetadata]) -> int:
        """
        加载字段元数据并构建向量索引
        
        每个字段生成一个 FieldChunk:
        - field_name: 技术字段名
        - field_caption: 显示名称
        - role: dimension/measure
        - data_type: 数据类型
        - sample_values: 样本值（最多5个）
        - category: 维度类别
        - metadata: 额外元数据
        """
        chunks = []
        for field in fields:
            chunk = FieldChunk(
                field_name=field.name,
                field_caption=field.caption,
                role=field.role,
                data_type=field.data_type,
                sample_values=field.sample_values[:self.max_samples],
                category=field.category,
            )
            chunks.append(chunk)
        
        # 构建向量索引
        self._build_index(chunks)
        return len(chunks)
```

### 8.4 LLMCandidateSelector

```python
class LLMCandidateSelector:
    """LLM 候选选择器"""
    
    async def select(
        self,
        term: str,
        candidates: List[FieldCandidate],
        context: Optional[str] = None
    ) -> SingleSelectionResult:
        """
        使用 LLM 从候选字段中选择最匹配的
        
        Prompt 包含:
        - 业务术语
        - 候选字段列表（名称、类型、样本值）
        - 问题上下文
        
        输出:
        - selected_field: 选中的字段名
        - confidence: 置信度
        - reasoning: 选择理由
        """
```

---

## 9. 预加载服务详解

### 9.1 PreloadService 架构

预加载服务在 Tableau 看板打开时触发，后台异步执行维度层级推断：

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

### 9.2 预热状态枚举

```python
class PreloadStatus(str, Enum):
    PENDING = "pending"      # 等待开始
    LOADING = "loading"      # 正在加载
    READY = "ready"          # 已就绪
    FAILED = "failed"        # 失败
    EXPIRED = "expired"      # 已过期
```

### 9.3 预热流程代码

```python
async def start_preload(self, datasource_luid, force=False):
    # 1. 检查是否有正在运行的任务
    if datasource_luid in self._running_tasks:
        return existing_task_id, PreloadStatus.LOADING
    
    # 2. 检查缓存状态
    if not force:
        cache_status = self.get_cache_status(datasource_luid)
        if cache_status["is_valid"]:
            return None, PreloadStatus.READY
    
    # 3. 启动后台任务
    task_id = self._create_task(datasource_luid)
    asyncio.create_task(self._execute_preload(task_id, datasource_luid))
    
    return task_id, PreloadStatus.LOADING

async def _execute_preload(self, task_id, datasource_luid):
    # 1. 获取 Tableau 认证
    auth_ctx = await get_tableau_auth_async()
    
    # 2. 获取元数据
    raw_metadata = await get_datasource_metadata(...)
    
    # 3. 推断维度层级
    result = await dimension_hierarchy_node(metadata, datasource_luid)
    
    # 4. 缓存结果（TTL: 24小时）
    self._store.put_dimension_hierarchy(datasource_luid, hierarchy_dict)
```

### 9.4 WorkflowContext 集成

```python
async def ensure_metadata_loaded(self, timeout=60.0):
    """确保数据模型已加载"""
    
    # 1. 检查缓存
    if self.metadata is not None:
        return self
    
    # 2. 检查预热服务状态
    preload_service = get_preload_service()
    cache_status = preload_service.get_cache_status(self.datasource_luid)
    
    if cache_status["is_valid"]:
        # 从缓存获取
        metadata = await self._load_metadata_from_cache()
        return self._with_metadata(metadata)
    
    # 3. 检查预热任务
    task_id, status = await preload_service.start_preload(datasource_luid)
    
    if status == PreloadStatus.LOADING:
        # 等待预热完成（带超时）
        metadata = await self._wait_for_preload(task_id, timeout)
        return self._with_metadata(metadata)
    
    # 4. 同步加载（预热失败时的后备）
    metadata = await self._load_metadata_sync()
    return self._with_metadata(metadata)
```

---

## 10. Semantic Parser Agent 详解（新架构）

### 10.1 LLM 组合架构

新的 Semantic Parser Agent 采用 Step 1 + Step 2 + Observer 的 LLM 组合模式：

```
用户问题 + 历史对话
        │
        ▼
┌───────────────────────────────────────────────────────────────┐
│                    Step 1: 直觉（Intuition）                   │
│                                                                │
│  • 理解问题，重述为完整的独立问题                               │
│  • 提取结构化信息（What × Where × How）                        │
│  • 分类意图（DATA_QUERY / CLARIFICATION / GENERAL / IRRELEVANT）│
│                                                                │
│  输出: restated_question + what/where/how_type + intent        │
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
        │                                                        │
        │  • 从 restated_question 推断计算定义                    │
        │  • 用 Step 1 的结构化输出验证推理结果                   │
        │                                                        │
        │  输出: computations + validation（自我验证结果）         │
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
               │                                                │
               │  • 检查重述完整性                               │
               │  • 复核结构一致性                               │
               │  • 检查语义一致性                               │
               │                                                │
               │  决策: ACCEPT / CORRECT / RETRY / CLARIFY      │
               └───────────────────────────────────────────────┘
```

### 10.2 核心数据模型

```python
# Step 1 输出
class Step1Output(BaseModel):
    restated_question: str      # 重述后的完整问题
    what: What                  # 目标（度量）
    where: Where                # 范围（维度 + 筛选）
    how_type: HowType           # 计算类型
    intent: Intent              # 意图分类

# Step 2 输出
class Step2Output(BaseModel):
    computations: list[Computation]  # 计算定义
    reasoning: str                   # 推理过程
    validation: Step2Validation      # 自我验证结果

# Step 2 验证
class Step2Validation(BaseModel):
    target_check: ValidationCheck      # target 是否在 what.measures 中
    partition_by_check: ValidationCheck # partition_by 是否在 where.dimensions 中
    operation_check: ValidationCheck   # operation.type 是否与 how_type 匹配
    all_valid: bool                    # 所有检查是否通过
    inconsistencies: list[str]         # 不一致之处

# Observer 输出
class ObserverOutput(BaseModel):
    is_consistent: bool              # 是否一致
    conflicts: list[Conflict]        # 发现的冲突
    decision: ObserverDecision       # 决策
    correction: Correction | None    # 修正内容
    final_result: Computation | None # 最终结果
```

### 10.3 三元模型

所有查询都可以用 What × Where × How 描述：

| 元素 | 含义 | 示例 |
|------|------|------|
| What | 要计算什么数据 | 销售额、订单数 |
| Where | 在什么范围内查看 | 按省份、按月份、2024年 |
| How | 怎么计算 | 简单聚合、排名、占比 |

### 10.4 计算模型

```python
class Computation(BaseModel):
    """计算 = 目标 × 分区 × 操作"""
    target: str              # 计算目标（度量字段）
    partition_by: list[str]  # 分区维度
    operation: Operation     # 计算操作

# partition_by 的含义
# [] → 全局计算（所有数据）
# ["月份"] → 按月份分区
# ["省份", "月份"] → 按省份和月份分区
```

### 10.5 意图分支处理

```python
async def parse(self, question, history, metadata):
    # Step 1: 语义理解
    step1_output = await self.step1.execute(question, history, metadata)
    
    # 意图分支
    if step1_output.intent.type == IntentType.CLARIFICATION:
        return SemanticParseResult(clarification=self._generate_clarification())
    
    if step1_output.intent.type == IntentType.GENERAL:
        return SemanticParseResult(general_response=self._generate_general_response())
    
    if step1_output.intent.type == IntentType.IRRELEVANT:
        return SemanticParseResult(...)
    
    # DATA_QUERY: 继续处理
    if step1_output.how_type == HowType.SIMPLE:
        # 简单查询，跳过 Step 2
        return SemanticParseResult(semantic_query=self._build_simple_query())
    
    # Step 2: 计算推理
    step2_output = await self.step2.execute(step1_output)
    
    # Observer: 一致性检查（仅当验证不通过时）
    if not step2_output.validation.all_valid:
        observer_output = await self.observer.execute(question, step1_output, step2_output)
        # 根据 Observer 决策处理
    
    return SemanticParseResult(semantic_query=self._build_semantic_query())
```

---

## 11. 完整执行流程

### 11.1 工作流执行代码

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

### 11.2 完整数据流图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              用户问题                                        │
│                    "各省份2024年销售额排名"                                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         1. Understanding Node                                │
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
│  ├─ "销售额" → "[Sales].[Amount]" (confidence: 0.95, source: rag_direct)    │
│  ├─ "省份" → "[Geography].[Province]" (confidence: 0.92, source: rag_direct)│
│  └─ "年份" → "[Date].[Year]" (confidence: 0.88, source: rag_llm_fallback)   │
│                                                                              │
│  输出: MappedQuery                                                           │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         3. QueryBuilder Node                                 │
│                      (TableauQueryBuilder)                                   │
│                                                                              │
│  SemanticQuery → VizQL 请求:                                                 │
│  ├─ Computation(RANK, partition_by=[]) → TableCalc(RANK, Partitioning=无)   │
│  ├─ DateRangeFilter → VizQL DATE Filter                                     │
│  └─ 自动填充默认值（aggregation=SUM, direction=DESC）                        │
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
│  ├─ API: POST /api/v1/vizql/query                                           │
│  └─ 响应解析: columns, rows, row_count                                       │
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

## 12. 目录结构总览

```
src/
├── core/                              # 核心层（平台无关）
│   ├── models/                        # 核心数据模型
│   │   ├── enums.py                   # 公共枚举
│   │   ├── fields.py                  # DimensionField, MeasureField
│   │   ├── computations.py            # Computation（核心抽象）
│   │   ├── filters.py                 # Filter 及其子类
│   │   ├── query.py                   # SemanticQuery
│   │   ├── step1.py                   # Step1Output
│   │   ├── step2.py                   # Step2Output
│   │   ├── observer.py                # ObserverOutput
│   │   └── parse_result.py            # SemanticParseResult
│   └── interfaces/                    # 抽象接口
│       ├── platform_adapter.py        # BasePlatformAdapter
│       ├── query_builder.py           # BaseQueryBuilder
│       └── field_mapper.py            # BaseFieldMapper
│
├── platforms/                         # 平台层
│   ├── base.py                        # PlatformRegistry
│   └── tableau/                       # Tableau 实现
│       ├── adapter.py                 # TableauAdapter
│       ├── query_builder.py           # TableauQueryBuilder
│       ├── field_mapper.py            # TableauFieldMapper
│       ├── client.py                  # VizQL API 客户端
│       ├── auth.py                    # 认证管理
│       ├── metadata.py                # 元数据获取
│       └── models/                    # Tableau 特定模型
│
├── agents/                            # Agent 层
│   ├── semantic_parser/               # 语义解析 Agent（新架构）
│   │   ├── agent.py                   # SemanticParserAgent
│   │   ├── node.py                    # SemanticParserNode
│   │   ├── components/                # Step1, Step2, Observer
│   │   └── prompts/                   # Prompt 模板
│   ├── field_mapper/                  # 字段映射 Agent
│   ├── insight/                       # 洞察 Agent
│   ├── replanner/                     # 重规划 Agent
│   └── dimension_hierarchy/           # 维度层级 Agent
│
├── nodes/                             # 非 Agent 节点
│   ├── query_builder/                 # 查询构建节点
│   └── execute/                       # 查询执行节点
│
├── orchestration/                     # 编排层
│   ├── workflow/                      # LangGraph 工作流
│   │   ├── factory.py                 # 工作流工厂
│   │   ├── executor.py                # 工作流执行器
│   │   ├── context.py                 # WorkflowContext
│   │   ├── routes.py                  # 路由定义
│   │   └── state.py                   # VizQLState
│   ├── tools/                         # 工具定义
│   └── middleware/                    # 中间件
│
├── infra/                             # 基础设施层
│   ├── ai/                            # AI 模型管理
│   │   ├── llm.py                     # LLM 客户端
│   │   ├── embeddings.py              # Embedding 模型
│   │   ├── reranker.py                # Reranker 模型
│   │   └── rag/                       # RAG 组件
│   ├── storage/                       # 存储管理
│   │   ├── store_manager.py           # StoreManager (SQLite)
│   │   └── cache.py                   # 缓存
│   ├── config/                        # 配置管理
│   └── monitoring/                    # 监控与日志
│
└── api/                               # 服务层
    ├── chat.py                        # 聊天 API
    ├── preload.py                     # 预加载 API
    └── preload_service.py             # 预加载服务
```

---

## 13. 配置说明

### 13.1 环境变量 (.env)

```bash
# LLM 配置
LLM_MODEL_PROVIDER=qwen           # qwen, deepseek, openai
LLM_MODEL_NAME=qwen3-235b         # 主模型
TOOLING_LLM_MODEL=qwen3-30b       # 工具模型（轻量）

# 中间件配置
SUMMARIZATION_TOKEN_THRESHOLD=60000  # 摘要触发阈值
MESSAGES_TO_KEEP=10                  # 保留消息数
MODEL_MAX_RETRIES=3                  # LLM 重试次数
TOOL_MAX_RETRIES=2                   # 工具重试次数
FILESYSTEM_TOKEN_LIMIT=10000         # 大结果保存阈值

# 工作流配置
MAX_REPLAN_ROUNDS=3                  # 最大重规划轮数

# Tableau 配置
TABLEAU_DOMAIN=https://xxx.tableau.com
TABLEAU_SITE=xxx
TABLEAU_CLIENT_ID=xxx
TABLEAU_CLIENT_SECRET=xxx
```

### 13.2 中间件配置详解

| 中间件 | 配置项 | 默认值 | 说明 |
|--------|--------|--------|------|
| SummarizationMiddleware | summarization_token_threshold | 60000 | 超过此 token 数触发摘要 |
| SummarizationMiddleware | messages_to_keep | 10 | 摘要后保留的消息数 |
| ModelRetryMiddleware | model_max_retries | 3 | LLM 调用最大重试次数 |
| ModelRetryMiddleware | model_backoff_factor | 2.0 | 指数退避因子 |
| ToolRetryMiddleware | tool_max_retries | 2 | 工具调用最大重试次数 |
| FilesystemMiddleware | filesystem_token_limit | 10000 | 超过此大小保存到文件 |
| HumanInTheLoopMiddleware | interrupt_on | [] | 需要人工确认的工具列表 |
