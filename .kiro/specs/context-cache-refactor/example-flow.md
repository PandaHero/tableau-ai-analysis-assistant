# 完整流程示例

## 用户问题
"2024年各地区的销售额是多少？"

## 阶段 1: WorkflowExecutor 初始化

```python
# 用户调用
executor = WorkflowExecutor(datasource_luid="ds_12345")
result = await executor.run("2024年各地区的销售额是多少？")
```

### 1.1 获取认证
```python
auth_ctx = await get_tableau_auth_async()
# 返回:
# TableauAuthContext(
#     api_key="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
#     site="mysite",
#     domain="https://tableau.example.com",
#     expires_at=1702468800.0,
#     auth_method="jwt"
# )
```

### 1.2 获取 StoreManager
```python
store = get_store_manager()  # 全局单例，SQLite 持久化
```

### 1.3 创建 WorkflowContext
```python
ctx = WorkflowContext(
    auth=auth_ctx,
    store=store,
    datasource_luid="ds_12345",
    max_replan_rounds=3,
)
```

### 1.4 加载数据模型（包含维度层级推断）
```python
ctx = await ctx.ensure_metadata_loaded()
# 完整流程:
# 1. 检查 store 缓存（metadata 命名空间，1小时 TTL）
# 2. 如果缓存命中:
#    a. 检查 dimension_hierarchy 缓存（24小时 TTL）
#    b. 如果维度层级缓存存在，直接返回
#    c. 如果维度层级缓存不存在，调用 dimension_hierarchy_node Agent 推断
# 3. 如果缓存未命中:
#    a. 调用 Tableau Metadata API 获取字段元数据
#    b. 调用 dimension_hierarchy_node Agent 推断维度层级
#    c. 缓存 metadata（1小时）和 dimension_hierarchy（24小时）
```

### 1.4.1 维度层级推断（dimension_hierarchy_node Agent）
```python
# 在 DataModelManager._enhance_data_model() 中调用
from tableau_assistant.src.agents.dimension_hierarchy.node import dimension_hierarchy_node

result = await dimension_hierarchy_node(
    metadata=metadata,
    datasource_luid=datasource_luid,
)

# Agent 使用 LLM 分析字段名称、数据类型、样本值等
# 推断出每个维度的:
# - category: 类别（time, geography, product, customer 等）
# - level: 层级（1=最高级，2=次级...）
# - granularity: 粒度（year, quarter, month, day 等）
# - parent_dimension: 父维度
# - child_dimension: 子维度

# 结果缓存到 store（24小时 TTL）
store.put_dimension_hierarchy(datasource_luid, hierarchy_dict)
```

### 1.5 ctx.metadata 内容
```python
Metadata(
    datasource_luid="ds_12345",
    datasource_name="销售数据",
    fields=[
        FieldMetadata(name="Region", role="DIMENSION", dataType="STRING", 
                      category="geography", level=1),
        FieldMetadata(name="Province", role="DIMENSION", dataType="STRING",
                      category="geography", level=2, parent_dimension="Region"),
        FieldMetadata(name="City", role="DIMENSION", dataType="STRING",
                      category="geography", level=3, parent_dimension="Province"),
        FieldMetadata(name="Order Date", role="DIMENSION", dataType="DATE",
                      category="time", granularity="day"),
        FieldMetadata(name="Sales", role="MEASURE", dataType="REAL"),
        FieldMetadata(name="Profit", role="MEASURE", dataType="REAL"),
        # ... 更多字段
    ],
    dimension_hierarchy={
        "Region": {"category": "geography", "level": 1, "child_dimension": "Province"},
        "Province": {"category": "geography", "level": 2, "parent_dimension": "Region", "child_dimension": "City"},
        "City": {"category": "geography", "level": 3, "parent_dimension": "Province"},
        "Order Date": {"category": "time", "granularity": "day"},
        # ...
    },
    data_model=DataModel(
        logicalTables=[LogicalTable(logicalTableId="t1", caption="Orders"), ...],
        logicalTableRelationships=[...]
    )
)
```

### 1.6 创建 RunnableConfig
```python
config = create_workflow_config(thread_id="thread_abc123", context=ctx)
# 结果:
# {
#     "configurable": {
#         "thread_id": "thread_abc123",
#         "workflow_context": ctx  # WorkflowContext 对象
#     }
# }
```

### 1.7 创建初始 State
```python
state = {
    "question": "2024年各地区的销售额是多少？",
    "messages": [],
    "metadata": ctx.metadata,
    "dimension_hierarchy": ctx.metadata.dimension_hierarchy,
    "data_insight_profile": None,
    "current_dimensions": [],
}
```

## 阶段 2: Understanding Node

### 2.1 节点输入
```python
async def understanding_node(state, config):
    # state 包含:
    # - question: "2024年各地区的销售额是多少？"
    # - metadata: Metadata 对象
    # - dimension_hierarchy: {...}
    
    # config 包含:
    # - configurable.thread_id: "thread_abc123"
    # - configurable.workflow_context: WorkflowContext 对象
```

### 2.2 获取数据模型
```python
    metadata = state.get("metadata")
    # 或者从 ctx 获取:
    # ctx = get_context(config)
    # metadata = ctx.metadata
```

### 2.3 调用 get_metadata 工具（如果需要）
```python
    # 工具通过 ToolRuntime 访问 config
    @tool
    async def get_metadata(runtime: ToolRuntime, ...):
        ctx = get_context_or_raise(runtime.config)
        # ctx.metadata 已经加载，直接返回
        return format_metadata(ctx.metadata)
```

### 2.4 LLM 分析
```python
    # 构建 Prompt，包含字段信息
    prompt = UNDERSTANDING_PROMPT.format_messages(
        question="2024年各地区的销售额是多少？",
        metadata_summary="Dimensions: Region, Province, City, Order Date\nMeasures: Sales, Profit",
        current_date="2024-12-12"
    )
    
    # 调用 LLM
    response = await call_llm_with_tools(llm, prompt, tools)
```

### 2.5 节点输出
```python
    return {
        "semantic_query": SemanticQuery(
            dimensions=["Region"],
            measures=["Sales"],
            filters=[TimeFilter(field="Order Date", range="2024")],
            analyses=[AnalysisType.COMPARISON]
        ),
        "is_analysis_question": True,
        "understanding_complete": True,
    }
```

## 阶段 3: FieldMapper Node

### 3.1 节点输入
```python
async def field_mapper_node(state, config):
    # state 包含:
    # - semantic_query: SemanticQuery 对象
    # - metadata: Metadata 对象（包含字段信息）
```

### 3.2 使用字段元数据进行映射
```python
    # 从 metadata 获取字段列表
    fields = state["metadata"].fields
    
    # 语义匹配: "地区" → "Region"
    # 使用 RAG + LLM 混合方式
```

### 3.3 节点输出
```python
    return {
        "mapped_query": MappedQuery(
            dimensions=[MappedField(semantic="地区", technical="Region")],
            measures=[MappedField(semantic="销售额", technical="Sales")],
            filters=[...],
        )
    }
```

## 阶段 4: QueryBuilder Node

### 4.1 纯代码转换（不需要数据模型）
```python
async def query_builder_node(state, config):
    mapped_query = state["mapped_query"]
    
    # 转换为 VizQL 查询
    vizql_query = VizQLQuery(
        fields=[
            {"fieldCaption": "Region"},
            {"fieldCaption": "Sales", "function": "SUM"}
        ],
        filters=[
            {"field": "Order Date", "filterType": "RANGE", "min": "2024-01-01", "max": "2024-12-31"}
        ]
    )
    
    return {"vizql_query": vizql_query}
```

## 阶段 5: Execute Node

### 5.1 从 config 获取认证
```python
async def execute_node(state, config):
    ctx = get_context_or_raise(config)
    
    # 检查认证是否过期
    if not ctx.is_auth_valid():
        ctx = await ctx.refresh_auth_if_needed()
    
    # 使用认证调用 VizQL API
    api_key = ctx.auth.api_key
    site = ctx.auth.site
```

### 5.2 执行查询
```python
    executor = ExecuteNode()
    result = await executor.execute(
        vizql_query=state["vizql_query"],
        datasource_luid=ctx.datasource_luid,
        api_key=api_key,
        site=site,
    )
    
    return {"query_result": result}
```

## 阶段 6: Insight Node

### 6.1 分析查询结果
```python
async def insight_node(state, config):
    query_result = state["query_result"]
    
    # 分析数据，生成洞察
    insights = analyze_data(query_result)
    
    # 生成数据洞察画像（供 Replanner 使用）
    data_insight_profile = {
        "distribution_type": "normal",
        "skewness": 0.3,
        "pareto_ratio": 0.65,
        "anomaly_ratio": 0.02,
        "clusters": [...],
        "recommended_chunking_strategy": "by_category"
    }
```

### 6.2 节点输出
```python
    return {
        "insights": insights,
        "data_insight_profile": data_insight_profile,
        "current_dimensions": ["Region"],  # 已分析的维度
    }
```

## 阶段 7: Replanner Node

### 7.1 获取维度层级
```python
async def replanner_node(state, config):
    # 从 state 获取维度层级（在工作流启动时加载）
    dimension_hierarchy = state.get("dimension_hierarchy")
    # {
    #     "Region": {"category": "geography", "level": 1, "child_dimension": "Province"},
    #     "Province": {"category": "geography", "level": 2, ...},
    #     ...
    # }
    
    data_insight_profile = state.get("data_insight_profile")
    current_dimensions = state.get("current_dimensions", [])  # ["Region"]
```

### 7.2 创建 ReplannerAgent
```python
    replanner = ReplannerAgent(
        max_replan_rounds=config.get("max_replan_rounds", 3),
        max_questions_per_round=3,
    )
```

### 7.3 执行重规划
```python
    decision = await replanner.replan(
        original_question="2024年各地区的销售额是多少？",
        insights=state["insights"],
        dimension_hierarchy=dimension_hierarchy,  # 关键：用于生成探索问题
        data_insight_profile=data_insight_profile,
        current_dimensions=current_dimensions,
        current_round=1,
    )
```

### 7.4 LLM 使用维度层级生成探索问题
```python
    # Replanner Prompt 包含维度层级信息:
    # "Region: geography (level=1), child_dimension: Province"
    # "Province: geography (level=2), parent_dimension: Region, child_dimension: City"
    
    # LLM 生成探索问题:
    # 1. "华东地区各省份的销售额是多少？" (drill_down, target: Province)
    # 2. "各地区的利润率如何？" (cross_dimension, target: Profit)
```

### 7.5 节点输出
```python
    return {
        "replan_decision": ReplanDecision(
            completeness_score=0.6,
            should_replan=True,
            reason="可以进一步下钻到省份级别",
            exploration_questions=[
                ExplorationQuestion(
                    question="华东地区各省份的销售额是多少？",
                    exploration_type="drill_down",
                    target_dimension="Province",
                    priority=1,
                ),
                # ...
            ]
        ),
        "replan_count": 1,
    }
```

## 阶段 8: 重规划循环（如果 should_replan=True）

工作流回到 Understanding Node，使用新问题继续分析...

---

## 中间件在各阶段的作用

### TodoListMiddleware
- 在 Replanner 生成探索问题后，可以调用 `write_todos` 工具存储问题队列
- 支持并行执行多个探索问题

### SummarizationMiddleware
- 当消息历史过长时，自动摘要
- 保持上下文窗口在合理范围内

### ModelRetryMiddleware
- LLM 调用失败时自动重试
- 指数退避策略

### ToolRetryMiddleware
- 工具调用失败时自动重试

### FilesystemMiddleware
- 当工具输出过大时，自动保存到文件
- 提供 `read_file`, `write_file` 等工具

### PatchToolCallsMiddleware
- 修复消息历史中的悬空工具调用

---

## 缓存层次总结

| 数据 | 存储位置 | 生命周期 | 访问方式 |
|------|----------|----------|----------|
| TableauAuthContext | WorkflowContext | 单次工作流 | `ctx.auth` |
| Metadata | State + WorkflowContext | 单次工作流 | `state["metadata"]` 或 `ctx.metadata` |
| dimension_hierarchy | State | 单次工作流 | `state["dimension_hierarchy"]` |
| data_insight_profile | State | 单次工作流 | `state["data_insight_profile"]` |
| 元数据缓存 | StoreManager (SQLite) | 1小时 | `ctx.store.get_metadata()` |
| 维度层级缓存 | StoreManager (SQLite) | 24小时 | `ctx.store.get_dimension_hierarchy()` |
| 工作流状态 | Checkpointer | 跨会话 | LangGraph 自动管理 |

---

## 关键改进点

1. **消除重复获取**: 数据模型在工作流启动时加载一次，通过 State 传递给所有节点
2. **统一依赖注入**: 所有依赖通过 WorkflowContext 传递，不再使用全局变量
3. **认证自动刷新**: 如果 token 过期，自动刷新
4. **缓存分层**: 短期缓存（State）+ 长期缓存（StoreManager）+ 会话持久化（Checkpointer）
