# ReAct Agent 重构设计文档 v2.0

## 概述

本设计文档描述将当前 7 节点 StateGraph 工作流重构为基于 LangGraph Subgraph + langgraph-supervisor 的层级 Agent 架构。这是一次彻底的重构，不考虑向后兼容性。

### 设计原则

1. **层级编排**：使用 LangGraph Subgraph 实现节点内部编排
2. **Agent 自主决策**：LLM 决定工具调用顺序，而非硬编码流程
3. **结构化错误响应**：工具返回结构化错误，LLM 自主决定如何处理
4. **Tableau Pulse 对齐**：洞察分析对齐 Tableau Pulse 专业级标准
5. **遵循规范**：Prompt 和数据模型遵循 `appendix-e-prompt-model-guide.md`

### 技术栈

| 组件 | 版本 | 用途 |
|------|------|------|
| langgraph | 1.0.5 | 核心编排框架 (Subgraph) |
| langchain | 1.1.3 | LLM 抽象层 |

**重要决策**：不使用 `create_react_agent` (langgraph-prebuilt)，原因：
1. **不支持 Middleware**：项目依赖 FilesystemMiddleware、ModelRetryMiddleware 等
2. **流式输出受限**：无法实现 token 级别的流式输出
3. **自定义 ReAct 循环**：使用 LangGraph StateGraph 实现，完全支持 middleware 和 streaming

---

## 核心架构：层级 Agent 编排

### 架构总览

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         Main Workflow (StateGraph)                               │
│                                                                                  │
│  ┌───────────────────────────────────────────────────────────────────────────┐  │
│  │                    SemanticParserAgent (Subgraph)                          │  │
│  │  Step1 → Step2 → ReAct Loop (map_fields, build_query, execute_query)      │  │
│  └───────────────────────────────────────────────────────────────────────────┘  │
│                                         │                                        │
│                                         ▼                                        │
│  ┌───────────────────────────────────────────────────────────────────────────┐  │
│  │                    InsightAgent (Subgraph)                                 │  │
│  │  EnhancedProfiler → Coordinator → Analyzer → Synthesizer                  │  │
│  └───────────────────────────────────────────────────────────────────────────┘  │
│                                         │                                        │
│                                         ▼                                        │
│  ┌───────────────────────────────────────────────────────────────────────────┐  │
│  │                    ReplannerAgent (单节点)                                 │  │
│  │  评估完成度 → 识别缺失 → 生成探索问题 → 决策: should_replan               │  │
│  └───────────────────────────────────────────────────────────────────────────┘  │
│                                         │                                        │
│                    ┌────────────────────┴────────────────────┐                  │
│                    ▼                                         ▼                  │
│           should_replan=True                        should_replan=False         │
│                    │                                         │                  │
│                    ▼                                         ▼                  │
│           SemanticParserAgent                              END                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### LangGraph Subgraph 机制

Subgraph 是将一个完整的 Graph 作为另一个 Graph 的节点使用：

```python
# 1. 定义 Subgraph（内部编排）
semantic_parser_subgraph = create_semantic_parser_subgraph()

# 2. 在主 Graph 中使用 Subgraph 作为节点
graph = StateGraph(VizQLState)
graph.add_node("semantic_parser", semantic_parser_subgraph)
graph.add_node("insight", insight_subgraph)
graph.add_node("replanner", replanner_node)
```

---

## SemanticParserAgent 设计

### 架构：QueryPipeline（固定流程）

**核心设计决策**：

1. **Pipeline 保证执行顺序**：Step1+Step2 → 字段映射 → 查询构建 → 查询执行 是固定流程
2. **字段映射是 RAG+LLM 混合**：内部已有完整的映射策略（缓存→RAG→LLM fallback），无需外层重试
3. **错误直接返回**：映射失败（字段不存在/无权限）直接返回错误信息给用户，不做重试
4. **澄清在 Step1 处理**：用户意图不清晰的情况在 Step1 阶段已经处理，不在字段映射阶段
5. **中间件全程介入**：MiddlewareRunner 在每个阶段执行对应钩子

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SemanticParserAgent (Subgraph)                            │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    QueryPipeline (固定流程)                          │    │
│  │  Step1 → Step2 → MapFields (RAG+LLM) → BuildQuery → ExecuteQuery    │    │
│  │                                                                      │    │
│  │  字段映射策略 (FieldMapperNode):                                     │    │
│  │  1. 缓存检查 (LangGraph SqliteStore)                                │    │
│  │  2. RAG 检索 (confidence >= 0.9 → 直接返回)                         │    │
│  │  3. LLM Fallback (confidence < 0.9 → 从 candidates 中选择)          │    │
│  │  4. RAG 不可用 → LLM Only                                           │    │
│  │                                                                      │    │
│  │  中间件集成:                                                         │    │
│  │  - Step1/Step2: call_model_with_middleware                          │    │
│  │  - MapFields/ExecuteQuery: call_tool_with_middleware                │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                    │                                         │
│                                    ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    结果处理                                          │    │
│  │  success=True → 进入 Insight                                        │    │
│  │  error (字段不存在/无权限) → 返回错误信息给用户                      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 字段映射错误处理

字段映射失败的原因：
- **字段不存在**：数据源中没有对应的字段
- **无权限**：用户没有权限查看该字段/数据

这些情况**不需要重试或澄清**，直接返回友好的错误信息给用户即可。

### QueryResult 结构

```python
@dataclass
class QueryResult:
    """Pipeline 执行结果"""
    success: bool
    mapped_query: Optional[MappedQuery] = None
    vizql_query: Optional[QueryRequest] = None
    query_result: Optional[ExecuteResult] = None
    error: Optional[QueryError] = None
    
@dataclass
class QueryError:
    """查询错误"""
    stage: str  # "step1" | "step2" | "map_fields" | "build_query" | "execute"
    type: str   # 错误类型
    message: str  # 用户友好的错误信息
```

---

## InsightAgent 设计

### Tableau Pulse 洞察类型对齐

| Tableau Pulse 洞察类型 | 优先级 | 我们的实现 |
|----------------------|-------|-----------|
| Period Over Period Change | P0 | PeriodChangeAnalysis |
| Unexpected Values | P0 | AnomalyIndex |
| Top Contributors | P0 | ContributorAnalysis |
| Concentrated Contribution Alert | P0 | ConcentrationRisk |
| Bottom Contributors | P1 | ContributorAnalysis |
| Current Trend | P1 | TrendAnalysis |
| Trend Change Alert | P2 | TrendAnalysis.change_points |

### EnhancedDataProfile 核心字段

```python
class EnhancedDataProfile(BaseModel):
    # 基础画像
    row_count: int
    column_count: int
    density: float
    statistics: Dict[str, ColumnStats]
    semantic_groups: List[SemanticGroup]
    
    # Tableau Pulse 风格洞察
    contributors: Optional[ContributorAnalysis] = None
    concentration_risk: Optional[ConcentrationRisk] = None
    period_changes: Optional[PeriodChangeAnalysis] = None
    trends: Optional[TrendAnalysis] = None
    
    # 智能索引（支持精准读取）
    dimension_index: Dict[str, DimensionIndex] = Field(default_factory=dict)
    anomaly_index: Optional[AnomalyIndex] = None
    
    # 分块策略推荐
    recommended_strategy: str = "by_position"
```

### Insight Subgraph 流程

```
START → profiler → coordinator → [analyzer] → synthesizer → END
                       ↑              │
                       └──────────────┘ (循环直到完成)
```

---

## 中间件集成架构

### 完整中间件栈（8 个中间件）

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

### 中间件钩子执行时机

| 阶段 | 钩子 | 中间件 | 说明 |
|------|------|--------|------|
| Agent 开始 | `before_agent` | TodoListMiddleware | 加载待处理任务 |
| Agent 开始 | `before_agent` | PatchToolCallsMiddleware | 修复历史中的悬空工具调用 |
| Step1/Step2 | `wrap_model_call` | SummarizationMiddleware | 对话历史摘要 |
| Step1/Step2 | `wrap_model_call` | ModelRetryMiddleware | LLM 调用失败时重试 |
| Step1/Step2 | `wrap_model_call` | FilesystemMiddleware | 注入 filesystem 系统提示 |
| Step1/Step2 | `wrap_model_call` | PatchToolCallsMiddleware | 修复请求中的悬空工具调用 |
| Step1/Step2 | `after_model` | OutputValidationMiddleware | 验证 LLM 输出格式 |
| MapFields | `wrap_tool_call` | ToolRetryMiddleware | 字段映射失败时重试 |
| ExecuteQuery | `wrap_tool_call` | ToolRetryMiddleware | 查询执行失败时重试 |
| ExecuteQuery | `wrap_tool_call` | FilesystemMiddleware | 大结果自动保存 |
| ExecuteQuery | `wrap_tool_call` | HumanInTheLoopMiddleware | 敏感查询人工确认 |
| Agent 结束 | `after_agent` | TodoListMiddleware | 保存任务状态 |
| Agent 结束 | `after_agent` | OutputValidationMiddleware | 验证最终状态必需字段 |

> 详细的中间件配置代码和使用示例请参考 [appendix-middleware-integration.md](./appendix-middleware-integration.md)

---

## Tool 定义

### 3 个核心 Tools

| Tool | 输入 | 输出 | 错误类型 |
|------|------|------|---------|
| map_fields | SemanticQuery | MappedQuery | field_not_found (字段不存在/无权限) |
| build_query | MappedQuery | QueryRequest | invalid_computation, unsupported_operation |
| execute_query | QueryRequest | ExecuteResult | execution_failed, timeout, auth_error, invalid_query |

### map_fields Tool 说明

`map_fields` 封装现有的 `FieldMapperNode`，保留 RAG+LLM 混合策略：

```python
# 内部映射策略（已实现）
1. 缓存检查 (LangGraph SqliteStore) → 命中直接返回
2. RAG 检索 (SemanticMapper.map_field)
   - confidence >= 0.9 → Fast Path，直接返回
   - confidence < 0.9 → LLM Fallback
3. LLM Fallback (LLMCandidateSelector.select)
   - 从 RAG 返回的 top-k candidates 中选择最佳匹配
4. RAG 不可用 → LLM Only
   - 直接用 LLM 从所有字段中选择
```

**错误处理**：映射失败直接返回错误，不做重试（字段不存在或无权限是数据问题，重试无意义）

### 结构化错误示例

```python
class FieldMappingError(BaseModel):
    type: Literal["field_not_found"]
    field: str
    message: str  # 用户友好的错误信息，如 "字段 '销售额' 在数据源中不存在"
```

---

## 主工作流 Factory

### 简化后的架构

```python
def create_workflow() -> StateGraph:
    """
    创建主工作流
    
    架构: 3 个 Agent 节点（2 个 Subgraph + 1 个单节点）
    """
    graph = StateGraph(VizQLState)
    
    # Subgraph 作为节点
    graph.add_node("semantic_parser", create_semantic_parser_subgraph())
    graph.add_node("insight", create_insight_subgraph())
    graph.add_node("replanner", replanner_node)
    
    # 边定义
    graph.add_edge(START, "semantic_parser")
    graph.add_conditional_edges("semantic_parser", route_after_semantic_parser, 
                                {"insight": "insight", "end": END})
    graph.add_edge("insight", "replanner")
    graph.add_conditional_edges("replanner", route_after_replanner,
                                {"semantic_parser": "semantic_parser", "end": END})
    
    return graph.compile(checkpointer=MemorySaver())
```

### 路由函数

| 路由函数 | 条件 | 目标 |
|---------|------|------|
| route_after_semantic_parser | intent=DATA_QUERY && query_result.success | insight |
| route_after_semantic_parser | 其他 | end |
| route_after_replanner | should_replan=True && replan_count < max | semantic_parser |
| route_after_replanner | 其他 | end |

---

## State 定义更新

### 移除的字段
- `correction_count`, `correction_exhausted` (由 ReAct 循环替代)
- `field_mapper_complete`, `query_builder_complete`, `execute_complete` (合并到 semantic_parser)

### 新增的字段
- `tool_observations: List[Dict[str, Any]]` - ReAct 工具调用记录
- `enhanced_profile: Optional[EnhancedDataProfile]` - 增强版数据画像

### 简化的完成标志
- `semantic_parser_complete`
- `insight_complete`
- `replanner_complete`

---

## 对比总结

| 方面 | 当前架构 | 新架构 |
|------|---------|--------|
| 节点数 | 7 | 3 (2 Subgraph + 1 单节点) |
| 路由函数 | 4 | 2 |
| 错误处理 | Observer + SelfCorrection | ReAct 循环内 |
| 工具调用 | 无 | 3 个 Tools |
| 内部编排 | 无 | Subgraph |
| 洞察分析 | 简单画像 | Tableau Pulse 对齐 |
| 代码量 | 多 | 减少 ~30% |
| 灵活性 | 固定流程 | LLM 自主决策 |

---

## 关键设计决策

| 决策 | 原因 | 影响 |
|------|------|------|
| 使用 Subgraph | LangGraph 原生支持，节点内部可编排 | 复杂逻辑封装 |
| ReAct 替代 Observer | 减少 LLM 调用，错误处理更自然 | 延迟降低 |
| Tableau Pulse 对齐 | 专业级数据分析标准 | 洞察质量提升 |
| 维度索引 | 支持精准读取 | 大数据处理效率 |
| 策略推荐 | 自动选择最佳分块策略 | 适应不同数据 |

---

## 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| Subgraph 状态传递 | 高 | 明确定义输入输出 Schema |
| ReAct 循环不稳定 | 高 | 设置 max_iterations，详细日志 |
| 大数据内存溢出 | 高 | FilesystemMiddleware + 索引精准读取 |
| 重规划死循环 | 高 | max_replan_rounds + answered_questions 去重 |

---

## 依赖更新

```txt
# 使用现有依赖，无需新增:
# - langgraph 1.0.5
# - langchain 1.1.3
# - 自定义 MiddlewareRunner (已存在)

# 移除（如果之前添加了）:
# - langgraph-prebuilt (不使用 create_react_agent)
# - langgraph-supervisor (不需要)
```

---

## 附录

- [appendix-middleware-integration.md](./appendix-middleware-integration.md) - 中间件集成详细代码示例
