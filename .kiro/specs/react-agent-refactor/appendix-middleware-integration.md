# 附件：中间件集成详细设计

本文档包含中间件集成的详细代码示例和实现细节。

---

## 完整中间件栈（8 个中间件）

| # | 中间件 | 来源 | 功能 | 使用的钩子 |
|---|--------|------|------|-----------|
| 1 | TodoListMiddleware | LangChain | 任务队列管理 | `before_agent`, `after_agent` |
| 2 | SummarizationMiddleware | LangChain | 对话历史自动摘要 | `wrap_model_call` |
| 3 | ModelRetryMiddleware | LangChain | LLM 调用指数退避重试 | `wrap_model_call` |
| 4 | ToolRetryMiddleware | LangChain | 工具调用指数退避重试 | `wrap_tool_call` |
| 5 | FilesystemMiddleware | 自定义 | 大结果自动保存到 files | `wrap_model_call`, `wrap_tool_call` |
| 6 | PatchToolCallsMiddleware | 自定义 | 修复悬空工具调用 | `before_agent`, `wrap_model_call` |
| 7 | HumanInTheLoopMiddleware | LangChain (可选) | 人工确认敏感操作 | `wrap_tool_call` |
| 8 | OutputValidationMiddleware | 自定义 | LLM 输出格式验证 | `after_model`, `after_agent` |

---

## 各中间件详细说明

### 1. TodoListMiddleware (LangChain)
- **功能**：管理任务队列，支持多轮探索问题的调度
- **钩子**：`before_agent`, `after_agent`
- **集成点**：ReplannerAgent 生成的探索问题通过此中间件管理

### 2. SummarizationMiddleware (LangChain)
- **功能**：当对话历史超过 token 阈值时自动摘要
- **钩子**：`wrap_model_call`
- **配置**：
  - `summarization_token_threshold`: 触发摘要的 token 阈值
  - `messages_to_keep`: 保留的最近消息数

### 3. ModelRetryMiddleware (LangChain)
- **功能**：LLM 调用失败时指数退避重试
- **钩子**：`wrap_model_call`
- **配置**：
  - `model_max_retries`: 最大重试次数（默认 3）
  - `model_initial_delay`: 初始延迟（默认 1.0s）
  - `model_backoff_factor`: 退避因子（默认 2.0）
  - `model_max_delay`: 最大延迟（默认 60.0s）
  - `jitter`: 添加随机抖动防止雷群效应

### 4. ToolRetryMiddleware (LangChain)
- **功能**：工具调用失败时指数退避重试
- **钩子**：`wrap_tool_call`
- **配置**：与 ModelRetryMiddleware 类似

### 5. FilesystemMiddleware (自定义)
- **功能**：
  - 大结果自动保存到 `state["files"]`
  - 提供 `read_file`, `write_file`, `edit_file`, `glob`, `grep` 工具
- **钩子**：`wrap_model_call` (注入系统提示), `wrap_tool_call` (拦截大结果)
- **配置**：
  - `tool_token_limit_before_evict`: 触发保存的 token 阈值（默认 20000）
- **返回**：大结果时返回 `Command(update={"files": {...}, "messages": [...]})`

### 6. PatchToolCallsMiddleware (自定义)
- **功能**：检测并修复悬空的工具调用（有 tool_call 但无对应 tool_result）
- **钩子**：`before_agent`, `wrap_model_call`
- **场景**：执行中断、工具执行错误未正确处理、用户在工具完成前发送新消息

### 7. HumanInTheLoopMiddleware (LangChain, 可选)
- **功能**：敏感操作需要人工确认
- **钩子**：`wrap_tool_call`
- **配置**：`interrupt_on`: 需要确认的工具名列表

### 8. OutputValidationMiddleware (自定义)
- **功能**：验证 LLM 输出是否为有效 JSON，使用 Pydantic Schema 验证
- **钩子**：`after_model`, `after_agent`
- **配置**：
  - `expected_schema`: 期望的 Pydantic 模型
  - `required_state_fields`: 必需的状态字段列表
  - `strict`: 严格模式
  - `retry_on_failure`: 失败时触发重试

---

## 中间件钩子执行时机

| 阶段 | 钩子 | 中间件 | 说明 |
|------|------|--------|------|
| Agent 开始 | `before_agent` | TodoListMiddleware | 加载待处理任务 |
| Agent 开始 | `before_agent` | PatchToolCallsMiddleware | 修复历史中的悬空工具调用 |
| Step1/Step2 | `wrap_model_call` | SummarizationMiddleware | 对话历史摘要 |
| Step1/Step2 | `wrap_model_call` | ModelRetryMiddleware | LLM 调用失败时指数退避重试 |
| Step1/Step2 | `wrap_model_call` | FilesystemMiddleware | 注入 filesystem 系统提示 |
| Step1/Step2 | `wrap_model_call` | PatchToolCallsMiddleware | 修复请求中的悬空工具调用 |
| Step1/Step2 | `after_model` | OutputValidationMiddleware | 验证 LLM 输出是否符合 JSON Schema |
| MapFields | `wrap_tool_call` | ToolRetryMiddleware | 字段映射失败时重试 |
| ExecuteQuery | `wrap_tool_call` | ToolRetryMiddleware | 查询执行失败时重试 |
| ExecuteQuery | `wrap_tool_call` | FilesystemMiddleware | 大结果自动保存到 files |
| ExecuteQuery | `wrap_tool_call` | HumanInTheLoopMiddleware | 敏感查询人工确认 (可选) |
| Agent 结束 | `after_agent` | TodoListMiddleware | 保存任务状态 |
| Agent 结束 | `after_agent` | OutputValidationMiddleware | 验证最终状态必需字段 |

---

## 中间件配置代码示例

```python
# orchestration/workflow/factory.py

def create_middleware_stack(
    model_name: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
    chat_model: Optional[BaseChatModel] = None,
) -> List[AgentMiddleware]:
    """创建完整的中间件栈（8 个中间件）"""
    config = {**get_default_config(), **(config or {})}
    middleware: List[AgentMiddleware] = []
    
    # 1. TodoListMiddleware
    middleware.append(TodoListMiddleware())
    
    # 2. SummarizationMiddleware
    if chat_model or model_name:
        middleware.append(SummarizationMiddleware(
            model=chat_model or model_name,
            trigger=("tokens", config["summarization_token_threshold"]),
            keep=("messages", config["messages_to_keep"]),
        ))
    
    # 3. ModelRetryMiddleware
    middleware.append(ModelRetryMiddleware(
        max_retries=config["model_max_retries"],
        initial_delay=config.get("model_initial_delay", 1.0),
        backoff_factor=config.get("model_backoff_factor", 2.0),
        max_delay=config.get("model_max_delay", 60.0),
        jitter=True,
    ))
    
    # 4. ToolRetryMiddleware
    middleware.append(ToolRetryMiddleware(
        max_retries=config["tool_max_retries"],
        initial_delay=config.get("tool_initial_delay", 1.0),
        backoff_factor=config.get("tool_backoff_factor", 2.0),
        max_delay=config.get("tool_max_delay", 60.0),
        jitter=True,
    ))
    
    # 5. FilesystemMiddleware
    middleware.append(FilesystemMiddleware(
        tool_token_limit_before_evict=config["filesystem_token_limit"],
    ))
    
    # 6. PatchToolCallsMiddleware
    middleware.append(PatchToolCallsMiddleware())
    
    # 7. HumanInTheLoopMiddleware (可选)
    interrupt_on = config.get("interrupt_on")
    if interrupt_on:
        if isinstance(interrupt_on, list):
            interrupt_on = {tool_name: True for tool_name in interrupt_on}
        middleware.append(HumanInTheLoopMiddleware(interrupt_on=interrupt_on))
    
    # 8. OutputValidationMiddleware
    middleware.append(OutputValidationMiddleware(
        strict=False,
        retry_on_failure=True,
    ))
    
    return middleware
```

---

## MiddlewareRunner 使用示例

```python
async def my_node(state: Dict, config: RunnableConfig) -> Dict:
    # 1. 从 config 获取 middleware
    middleware = get_middleware_from_config(config)
    runner = MiddlewareRunner(middleware) if middleware else None
    runtime = runner.build_runtime(config) if runner else None
    
    # 2. before_agent 钩子
    if runner:
        state = await runner.run_before_agent(state, runtime)
    
    # 3. LLM 调用（带 wrap_model_call 钩子）
    if runner:
        response = await runner.call_model_with_middleware(
            model=llm,
            messages=messages,
            tools=tools,
            state=state,
            runtime=runtime,
        )
    else:
        response = await llm.ainvoke(messages)
    
    # 4. 工具调用（带 wrap_tool_call 钩子）
    if runner:
        tool_result = await runner.call_tool_with_middleware(
            tool=tool,
            tool_call=tool_call,
            state=state,
            runtime=runtime,
        )
    
    # 5. after_agent 钩子
    if runner:
        state = await runner.run_after_agent(state, runtime)
    
    return state
```

---

## QueryPipeline 中间件集成

```python
class QueryPipeline:
    """查询执行 Pipeline，全程集成中间件"""
    
    def __init__(
        self,
        middleware_runner: Optional[MiddlewareRunner] = None,
        runtime: Optional[Runtime] = None,
    ):
        self.runner = middleware_runner
        self.runtime = runtime
    
    async def _execute_step1(self, question, history, data_model):
        """Step1: 使用 call_model_with_middleware"""
        messages = build_step1_messages(question, history, data_model)
        
        if self.runner:
            # 执行的中间件：
            # - SummarizationMiddleware.wrap_model_call
            # - ModelRetryMiddleware.wrap_model_call
            # - FilesystemMiddleware.wrap_model_call
            # - PatchToolCallsMiddleware.wrap_model_call
            # - OutputValidationMiddleware.after_model
            response = await self.runner.call_model_with_middleware(
                model=self._get_llm(),
                messages=messages,
                state={"question": question, "data_model": data_model},
                runtime=self.runtime,
            )
            ai_message = response.result[0]
        else:
            ai_message = await self._get_llm().ainvoke(messages)
        
        return parse_step1_output(ai_message.content)
    
    async def _execute_map_fields(self, semantic_query):
        """
        MapFields: 使用 call_tool_with_middleware
        
        注意：字段映射内部已有完整的 RAG+LLM 混合策略：
        1. 缓存检查 (LangGraph SqliteStore)
        2. RAG 检索 (confidence >= 0.9 → 直接返回)
        3. LLM Fallback (confidence < 0.9 → 从 candidates 中选择)
        4. RAG 不可用 → LLM Only
        
        映射失败（字段不存在/无权限）直接返回错误，不做重试。
        """
        tool_call = {
            "name": "map_fields",
            "args": {"semantic_query": semantic_query.model_dump()},
            "id": f"map_fields_{id(semantic_query)}",
        }
        
        if self.runner:
            # 执行的中间件：ToolRetryMiddleware.wrap_tool_call（仅重试网络/API错误）
            result = await self.runner.call_tool_with_middleware(
                tool=map_fields_tool,
                tool_call=tool_call,
                state={"semantic_query": semantic_query.model_dump()},
                runtime=self.runtime,
            )
        else:
            result = await map_fields_tool.ainvoke(tool_call["args"])
        
        return self._parse_map_fields_result(result)
    
    async def _execute_query(self, vizql_query):
        """ExecuteQuery: 使用 call_tool_with_middleware"""
        tool_call = {
            "name": "execute_query",
            "args": {"query": vizql_query.model_dump()},
            "id": f"execute_query_{id(vizql_query)}",
        }
        
        if self.runner:
            # 执行的中间件：
            # - ToolRetryMiddleware.wrap_tool_call
            # - FilesystemMiddleware.wrap_tool_call (大结果保存)
            # - HumanInTheLoopMiddleware.wrap_tool_call (可选)
            result = await self.runner.call_tool_with_middleware(
                tool=execute_query_tool,
                tool_call=tool_call,
                state={"vizql_query": vizql_query.model_dump()},
                runtime=self.runtime,
            )
            
            # 处理 Command（FilesystemMiddleware 返回）
            if hasattr(result, 'update') and result.update:
                # 大结果被保存到 files
                file_path = self._extract_file_path(result.update.get("messages", []))
                return QueryResult(
                    success=True,
                    query_result=ExecuteResult(file_reference=file_path),
                )
        else:
            result = await execute_query_tool.ainvoke(tool_call["args"])
        
        return self._parse_execute_result(result)
```

---

## FilesystemMiddleware 大结果处理

```python
# 当工具返回结果超过 token_limit (默认 20000) 时：
# 1. 自动保存到 state["files"]
# 2. 返回文件引用而非完整内容
# 3. 提供 read_file 工具用于分页读取

tool_result = await runner.call_tool_with_middleware(
    tool=execute_query_tool,
    tool_call={"name": "execute_query", "args": {...}},
    state=state,
    runtime=runtime,
)

# 如果结果太大，tool_result 是 Command：
# Command(update={
#     "files": {"/large_tool_results/xxx": FileData(...)},
#     "messages": [ToolMessage("Tool result saved at: /large_tool_results/xxx")]
# })
```

---

## 决策处理实现

```python
# agents/semantic_parser/components/decision_handler.py

class DecisionState(TypedDict):
    """决策状态"""
    question: str
    history: List[BaseMessage]
    data_model: Dict[str, Any]
    pipeline_result: Optional[QueryResult]
    mapped_query: Optional[MappedQuery]
    vizql_query: Optional[QueryRequest]
    query_result: Optional[ExecuteResult]
    error: Optional[QueryError]
    files: Dict[str, Any]


def create_semantic_parser_graph(llm: BaseChatModel) -> StateGraph:
    """
    创建语义解析 StateGraph
    
    流程: START → pipeline → handle_result → END
    
    注意：字段映射内部已有完整的 RAG+LLM 混合策略，
    外层不需要复杂的重试循环。映射失败直接返回错误给用户。
    """
    graph = StateGraph(DecisionState)
    
    async def pipeline_node(state: DecisionState, config: RunnableConfig) -> Dict:
        """执行 QueryPipeline"""
        middleware = get_middleware_from_config(config)
        runner = MiddlewareRunner(middleware) if middleware else None
        runtime = runner.build_runtime(config) if runner else None
        
        pipeline = QueryPipeline(middleware_runner=runner, runtime=runtime)
        result = await pipeline.execute(
            question=state["question"],
            history=state["history"],
            data_model=state["data_model"],
        )
        
        return {"pipeline_result": result}
    
    async def handle_result_node(state: DecisionState, config: RunnableConfig) -> Dict:
        """处理 Pipeline 结果"""
        result = state["pipeline_result"]
        
        if result.success:
            return {
                "mapped_query": result.mapped_query,
                "vizql_query": result.vizql_query,
                "query_result": result.query_result,
                "error": None,
            }
        
        # 映射失败直接返回错误（字段不存在/无权限是数据问题，重试无意义）
        return {
            "error": result.error,
            "mapped_query": None,
            "vizql_query": None,
            "query_result": None,
        }
    
    def route_after_handle(state: DecisionState) -> str:
        return "end"
    
    graph.add_node("pipeline", pipeline_node)
    graph.add_node("handle_result", handle_result_node)
    graph.add_edge(START, "pipeline")
    graph.add_edge("pipeline", "handle_result")
    graph.add_edge("handle_result", END)
    
    return graph.compile()
```

---

## Token 级别流式输出

```python
async def stream_semantic_parser(
    question: str,
    history: List[BaseMessage],
    data_model: Dict[str, Any],
    config: Optional[RunnableConfig] = None,
    max_retries: int = 3,
) -> AsyncIterator[Dict[str, Any]]:
    """
    流式执行语义解析，支持 token 级别的流式输出
    
    Yields:
        - {"type": "stage", "stage": "step1"} - 阶段开始
        - {"type": "token", "content": "..."} - LLM token
        - {"type": "retry", "reason": "...", "hint": "..."} - 重试
        - {"type": "complete", "result": {...}} - 完成
    """
    semantic_parser_graph = create_semantic_parser_graph(get_llm())
    
    initial_state = {
        "question": question,
        "history": history,
        "data_model": data_model,
        "retry_count": 0,
        "max_retries": max_retries,
        "should_continue": True,
        "files": {},
    }
    
    async for event in semantic_parser_graph.astream_events(initial_state, config, version="v2"):
        event_type = event.get("event")
        
        if event_type == "on_chat_model_stream":
            chunk = event.get("data", {}).get("chunk")
            if chunk and hasattr(chunk, "content") and chunk.content:
                yield {"type": "token", "content": chunk.content}
        
        elif event_type == "on_chain_start":
            node_name = event.get("name", "")
            if node_name in ["step1", "step2", "map_fields", "build_query", "execute"]:
                yield {"type": "stage", "stage": node_name}
        
        elif event_type == "on_chain_end":
            node_name = event.get("name", "")
            if node_name == "LangGraph":
                output = event.get("data", {}).get("output", {})
                yield {"type": "complete", "result": output}
```

---

## 完整数据流示例

```
用户问题: "各省份销售额排名"
        │
        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SemanticParserAgent (Subgraph)                            │
│                                                                              │
│  Step1 Node:                                                                 │
│  - 输入: question="各省份销售额排名"                                         │
│  - 中间件: SummarizationMiddleware, ModelRetryMiddleware, OutputValidation  │
│  - 输出: Step1Output {what: ["销售额"], where: ["省份"], how_type: RANKING}  │
│                                    │                                         │
│                                    │ (how_type != COMPLEX, 跳过 Step2)       │
│                                    ▼                                         │
│  QueryPipeline:                                                              │
│  - MapFields (RAG+LLM 混合策略):                                             │
│    1. 缓存检查 → miss                                                        │
│    2. RAG 检索 "销售额" → confidence=0.95 → Fast Path                       │
│    3. RAG 检索 "省份" → confidence=0.85 → LLM Fallback → 选择 "Province"    │
│  - BuildQuery → {query: {...}}                                              │
│  - ExecuteQuery → {result: {data: [...], row_count: 31}}                    │
│                                                                              │
│  Subgraph 输出: {query_result: ExecuteResult}                               │
│                                                                              │
│  错误处理:                                                                   │
│  - 字段不存在 → 直接返回错误信息给用户                                       │
│  - 无权限 → 直接返回错误信息给用户                                           │
│  - (不做重试，因为这些是数据问题)                                            │
└─────────────────────────────────────────────────────────────────────────────┘
        │
        │ route: query_result.is_success() → insight
        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    InsightAgent (Subgraph)                                   │
│                                                                              │
│  Profiler Node:                                                              │
│  - EnhancedDataProfiler 输出:                                                │
│    - contributors: {top: [广东 25%, 江苏 18%, ...]}                          │
│    - concentration_risk: {is_risky: true, level: "medium"}                  │
│    - dimension_index: {省份: {广东: rows 0-5, 江苏: rows 6-10, ...}}        │
│                                    │                                         │
│                                    ▼                                         │
│  Director Node (总监 LLM):                                                   │
│  - 决策: {action: "analyze_dimension", target: "广东"}                       │
│                                    │                                         │
│                                    ▼                                         │
│  Analyzer Node:                                                              │
│  - 按维度精准读取: 只读取广东省数据 (rows 0-5)                               │
│  - 生成洞察: [Insight("广东省销售额最高，占比 25%")]                         │
│                                    │                                         │
│                                    │ (循环回 Coordinator)                    │
│                                    ▼                                         │
│  Coordinator Node (第 2 轮):                                                 │
│  - 决策: {action: "stop", completeness: 0.9}                                │
│                                    │                                         │
│                                    ▼                                         │
│  Synthesizer Node:                                                           │
│  - 综合洞察: "广东省销售额最高，占比 25%，存在中等集中度风险..."             │
└─────────────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    ReplannerAgent (单节点)                                   │
│                                                                              │
│  评估: completeness_score = 0.7                                             │
│  缺失: ["城市级别分析", "时间趋势"]                                          │
│  探索问题: ["广东省各城市销售额排名"]                                         │
│  决策: should_replan = True                                                 │
└─────────────────────────────────────────────────────────────────────────────┘
        │
        │ route: should_replan=True → semantic_parser
        ▼
       (继续循环直到 should_replan=False 或达到 max_rounds)
```
