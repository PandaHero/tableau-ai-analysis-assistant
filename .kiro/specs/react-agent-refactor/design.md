# ReAct Agent 重构设计文档 v2.0

## 概述

本设计文档描述将当前 7 节点 StateGraph 工作流重构为基于 **LangGraph Subgraph + 动态并行执行** 的层级 Agent 架构。这是一次彻底的重构，不考虑向后兼容性。

### 设计原则

1. **层级编排**：使用 LangGraph Subgraph 实现节点内部编排
2. **动态并行**：使用 Send() API 实现运行时动态并行分支
3. **结构化错误响应**：工具返回结构化错误，直接返回给用户
4. **Tableau Pulse 对齐**：洞察分析对齐 Tableau Pulse 专业级标准
5. **遵循规范**：Prompt 和数据模型遵循 `appendix-e-prompt-model-guide.md`

### 架构分层概览

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                    API 层 (api/)                                     │
│                          HTTP 端点、请求处理、响应格式化                              │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                          │
                                          ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                  编排层 (orchestration/)                             │
│                     工作流编排 (workflow/)、中间件 (middleware/)、工具 (tools/)       │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                          │
                                          ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                  Agent 层 (agents/)                                  │
│              SemanticParser (Subgraph)、Insight (Subgraph)、Replanner                │
│                        每个 Agent 有自己的 models/ 和 prompts/                        │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                          │
                                          ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                  核心层 (core/)                                      │
│                                                                                      │
│  ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────────────┐  │
│  │   interfaces/       │  │     models/         │  │   state.py, exceptions.py   │  │
│  │   平台适配器接口     │  │   语义层核心模型     │  │   工作流状态、核心异常       │  │
│  │   (PlatformAdapter) │  │   (SemanticQuery,   │  │                             │  │
│  │                     │  │    Computation,     │  │                             │  │
│  │                     │  │    Filter, ...)     │  │                             │  │
│  └─────────────────────┘  └─────────────────────┘  └─────────────────────────────┘  │
│                                                                                      │
│  ★ 核心层定义平台无关的"契约"，是整个系统的语义抽象层                                 │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                          │
                    ┌─────────────────────┴─────────────────────┐
                    ▼                                           ▼
┌───────────────────────────────────┐       ┌───────────────────────────────────────┐
│        平台层 (platforms/)         │       │        基础设施层 (infra/)             │
│                                   │       │                                       │
│  ┌─────────────────────────────┐  │       │  ┌─────────────┐  ┌─────────────────┐ │
│  │  tableau/                   │  │       │  │    ai/      │  │    storage/     │ │
│  │  ├── adapter.py             │  │       │  │  LLM 客户端  │  │  数据存储       │ │
│  │  ├── tableau_data_model.py  │  │       │  │  嵌入模型    │  │  缓存管理       │ │
│  │  ├── query_builder.py       │  │       │  │  重排序器    │  │                 │ │
│  │  └── vizql_client.py        │  │       │  └─────────────┘  └─────────────────┘ │
│  └─────────────────────────────┘  │       │                                       │
│                                   │       │  ┌─────────────┐                      │
│  ┌─────────────────────────────┐  │       │  │   config/   │                      │
│  │  powerbi/ (未来)            │  │       │  │  配置管理    │                      │
│  └─────────────────────────────┘  │       │  └─────────────┘                      │
│                                   │       │  ★ monitoring/ 已删除，使用 LangSmith  │
│  ★ 实现 core/interfaces/ 定义的接口│       │  ★ 提供 AI、存储、配置等基础能力        │
└───────────────────────────────────┘       └───────────────────────────────────────┘
```

**层级依赖规则**：
- API 层 → 编排层 → Agent 层 → 核心层
- 平台层 → 核心层（实现核心层定义的接口）
- 基础设施层 → 被所有层使用（但核心层不依赖）
- **核心层不依赖任何其他层**（零依赖原则）

### 技术栈

| 组件 | 版本 | 用途 |
|------|------|------|
| langgraph | 1.0.5 | 核心编排框架 (Subgraph + Send() API) |
| langchain | 1.1.3 | LLM 抽象层 |

**重要决策**：
1. **不使用 `create_react_agent`** (langgraph-prebuilt)：不支持 Middleware 和 token 流式输出
2. **不使用 `langgraph-supervisor`**：我们的流程是固定的，不需要 Supervisor 动态选择
3. **使用 Send() API 实现动态并行**：Replanner 生成的问题数量运行时确定，需要动态分支

---

## 重构后目录结构

```
tableau_assistant/src/
│
├── api/                                 # API 层（保持不变）
│   ├── __init__.py
│   ├── cache.py                         # 缓存管理
│   ├── chat.py                          # 聊天 API 端点
│   ├── custom_models.py                 # 自定义模型
│   └── models.py                        # API 数据模型
│
├── core/                                # 核心层（平台无关的抽象）
│   ├── __init__.py
│   ├── exceptions.py                    # 核心异常定义
│   ├── state.py                         # VizQLState 主状态定义
│   │
│   ├── interfaces/                      # 核心接口定义（平台适配器需实现）
│   │   ├── __init__.py
│   │   ├── platform_adapter.py          # PlatformAdapter 抽象基类
│   │   ├── field_mapper.py              # FieldMapper 接口
│   │   └── query_builder.py             # QueryBuilder 接口
│   │
│   └── models/                          # ★核心数据模型（仅保留 7 个文件）
│       ├── __init__.py
│       ├── enums.py                     # 语义层枚举（IntentType, CalcType, FilterType, ...）
│       ├── fields.py                    # 字段抽象（DimensionField, MeasureField, Sort）
│       ├── filters.py                   # 过滤器抽象（SetFilter, DateRangeFilter, ...）
│       ├── computations.py              # ★核心：Computation = Target × CalcType × Partition × Params
│       ├── query.py                     # ★核心输出：SemanticQuery（语义解析的最终产物）
│       ├── execute_result.py            # 执行结果抽象（平台无关）
│       └── validation.py                # 验证结果抽象
│       # ===== 以下文件将被迁移 =====
│       # data_model.py                  # → infra/storage/data_model.py
│       # dimension_hierarchy.py         # → agents/dimension_hierarchy/models/
│       # query_request.py               # → platforms/base.py
│       # field_mapping.py               # → agents/field_mapper/models/mapping.py
│       # parse_result.py                # → agents/semantic_parser/models/parse_result.py
│       # step1.py                       # → agents/semantic_parser/models/step1.py
│       # step2.py                       # → agents/semantic_parser/models/step2.py
│       # insight.py                     # → agents/insight/models/insight.py
│       # replan.py                      # → agents/replanner/models/output.py
│       # observer.py                    # → 删除，由 ReAct 替代
│
├── infra/                               # 基础设施层（保持不变）
│   ├── __init__.py
│   ├── errors.py                        # 错误定义
│   ├── exceptions.py                    # 异常定义
│   │
│   ├── ai/                              # AI 相关基础设施
│   │   ├── __init__.py
│   │   ├── deepseek_r1.py               # DeepSeek R1 集成
│   │   ├── embeddings.py                # 嵌入模型
│   │   ├── llm.py                       # LLM 客户端
│   │   └── reranker.py                  # 重排序器
│   │   # rag/                           # ★已移动到 agents/field_mapper/rag/
│   │
│   ├── certs/                           # 证书管理
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── fetcher.py
│   │   ├── hot_reload.py
│   │   ├── manager.py
│   │   ├── models.py
│   │   ├── self_signed.py
│   │   ├── service_registry.py
│   │   ├── validator.py
│   │   └── store/
│   │
│   ├── config/                          # 配置管理
│   │   ├── __init__.py
│   │   └── settings.py                  # 全局设置
│   │   # tableau_env.py                 # ★已删除：多环境配置不需要
│   │
│   # monitoring/                        # ★已删除：使用 LangSmith 进行监控
│   #     └── callbacks.py               # SQLiteTrackingCallback 不再需要
│   │
│   ├── storage/                         # 存储
│   │   ├── __init__.py
│   │   ├── data_model_cache.py          # 数据模型缓存
│   │   ├── data_model_loader.py         # 数据模型加载器
│   │   ├── golden_queries.py            # 黄金查询存储
│   │   └── langgraph_store.py           # LangGraph 状态存储
│   │
│   # utils/                              # ★已删除：功能过于简单
│   #     └── conversation.py            # trim_answered_questions() 移到使用处
│
├── platforms/                           # 平台适配层（可扩展支持其他 BI 平台）
│   ├── __init__.py
│   ├── base.py                          # PlatformAdapter 基类实现
│   │
│   └── tableau/                         # Tableau 平台实现
│       ├── __init__.py
│       ├── adapter.py                   # TableauAdapter（实现 PlatformAdapter）
│       ├── auth.py                      # Tableau 认证
│       ├── vizql_client.py              # VizQL Data Service 客户端（主客户端）
│       ├── tableau_data_model.py        # ★重命名：Tableau 数据模型处理（原 metadata.py）
│       ├── query_builder.py             # Tableau 查询构建器（实现 QueryBuilder 接口）
│       └── models/                      # Tableau 特定模型
│           ├── __init__.py
│           ├── vizql_types.py           # VizQL API 类型（字段、过滤器、查询请求/响应）
│           ├── table_calc.py            # 表计算规格（TableCalcSpecification 等）
│           ├── lod.py                   # LOD 表达式（LODType, LODExpression）
│           └── execute_result.py        # 执行结果（ExecuteResult, ColumnMetadata）
│
├── agents/                              # Agent 层（Subgraph 实现）
│   │
│   ├── base/                            # Agent 基类
│   │   ├── __init__.py
│   │   ├── middleware_runner.py         # 中间件执行器
│   │   ├── node.py                      # 节点基类
│   │   └── prompt.py                    # Prompt 基类
│   │
│   ├── field_mapper/                    # ★保留在 agents：LLM 字段映射 Agent
│   │   ├── __init__.py
│   │   ├── node.py                      # 字段映射节点
│   │   ├── prompt.py                    # 字段映射 Prompt
│   │   ├── models/                      # Agent 特有模型
│   │   │   ├── __init__.py
│   │   │   └── mapping.py               # MappedQuery, FieldMapping, AlternativeMapping
│   │   └── rag/                         # ★RAG 放在 Agent 内（LLM 调用的一部分）
│   │       ├── __init__.py
│   │       ├── assembler.py             # RAG 组装器
│   │       ├── cache.py                 # 映射缓存（LangGraph SqliteStore）
│   │       ├── dimension_pattern.py     # 维度模式识别
│   │       ├── embeddings.py            # 嵌入模型
│   │       ├── field_indexer.py         # 字段索引器
│   │       ├── models.py                # RAG 数据模型（FieldCandidate, MappingResult）
│   │       ├── observability.py         # 可观测性
│   │       ├── reranker.py              # 重排序器
│   │       ├── retriever.py             # 检索器
│   │       └── semantic_mapper.py       # 语义映射器（RAG+LLM 混合策略）
│   │
│   ├── dimension_hierarchy/             # 维度层级 Agent
│   │   ├── __init__.py
│   │   ├── node.py                      # 节点实现
│   │   ├── prompt.py                    # Prompt 定义
│   │   └── models/                      # ★新增：Agent 特有模型
│   │       ├── __init__.py
│   │       └── hierarchy.py             # DimensionHierarchyResult, DimensionAttributes（从 core/models/ 迁移）
│   │
│   ├── semantic_parser/                 # SemanticParserAgent (Subgraph)
│   │   ├── __init__.py
│   │   ├── state.py                     # SemanticParserState 定义
│   │   ├── subgraph.py                  # create_semantic_parser_subgraph()
│   │   ├── node.py                      # semantic_parser_node() 适配主工作流
│   │   │
│   │   ├── components/                  # 内部组件
│   │   │   ├── __init__.py
│   │   │   ├── step1.py                 # Step1 节点（意图识别）
│   │   │   ├── step2.py                 # Step2 节点（复杂查询分解）
│   │   │   ├── query_pipeline.py        # QueryPipeline（核心：MapFields→BuildQuery→Execute）
│   │   │   ├── react_error_handler.py   # ReAct 错误处理（Thought→Action→Observation）★新增
│   │   │   └── decision_handler.py      # 外层决策逻辑（整合 Pipeline + ReAct）
│   │   │
│   │   ├── models/                      # 数据模型 ★新增包
│   │   │   ├── __init__.py
│   │   │   ├── step1.py                 # Step1Output（从 core/models/step1.py 迁移）
│   │   │   ├── step2.py                 # Step2Output（从 core/models/step2.py 迁移）
│   │   │   ├── pipeline.py              # QueryResult, QueryError
│   │   │   └── react.py                 # ReActThought, ReActAction, ReActObservation, ReActOutput ★新增
│   │   │
│   │   └── prompts/                     # Prompt 定义
│   │       ├── __init__.py
│   │       ├── step1.py                 # Step1Prompt
│   │       ├── step2.py                 # Step2Prompt
│   │       └── react_error.py           # ReActErrorHandlerPrompt ★新增
│   │
│   ├── insight/                         # InsightAgent (Subgraph)
│   │   ├── __init__.py
│   │   ├── state.py                     # InsightState 定义
│   │   ├── subgraph.py                  # create_insight_subgraph()
│   │   ├── node.py                      # insight_node() 适配主工作流
│   │   │
│   │   ├── components/                  # 内部组件
│   │   │   ├── __init__.py
│   │   │   ├── profiler.py              # EnhancedDataProfiler（纯代码，Tableau Pulse 对齐）
│   │   │   ├── profiler_node.py         # profiler_node()
│   │   │   ├── director.py              # AnalysisDirector（总监 LLM）★重命名
│   │   │   ├── director_node.py         # director_node() ★重命名
│   │   │   ├── analyzer.py              # ChunkAnalyzer（分析师 LLM）
│   │   │   ├── analyzer_node.py         # analyzer_node()
│   │   │   └── accumulator.py           # 洞察累积辅助（代码级去重）
│   │   │   # synthesizer.py             # ★已移除，功能合并到 Director
│   │   │
│   │   ├── models/                      # 数据模型 ★新增包
│   │   │   ├── __init__.py
│   │   │   ├── profile.py               # EnhancedDataProfile, ContributorAnalysis, ConcentrationRisk, PeriodChangeAnalysis, TrendAnalysis, DimensionIndex, AnomalyIndex
│   │   │   ├── insight.py               # Insight, InsightQuality（从 core/models/insight.py 迁移）
│   │   │   ├── director.py              # DirectorInput, DirectorDecision, DirectorOutputWithAccumulation ★重命名
│   │   │   └── analyst.py               # AnalystOutputWithHistory, HistoricalInsightAction ★新增
│   │   │
│   │   └── prompts/                     # Prompt 定义
│   │       ├── __init__.py
│   │       ├── analyst.py               # AnalystPrompt, AnalystPromptWithHistory ★增强
│   │       └── director.py              # DirectorPrompt, DirectorPromptWithAccumulation ★重命名+增强
│   │
│   └── replanner/                       # ReplannerAgent（单 LLM 节点）
│       ├── __init__.py
│       ├── node.py                      # replanner_node()（支持并行问题生成）
│       ├── models/                      # 数据模型 ★新增包
│       │   ├── __init__.py
│       │   └── output.py                # ReplannerOutput（从 core/models/replan.py 迁移）
│       └── prompts/                     # Prompt 定义 ★改为包
│           ├── __init__.py
│           └── replanner.py             # ReplannerPrompt
│
├── orchestration/                       # 编排层
│   │
│   ├── tools/                           # Tool 定义 ★新增目录
│   │   ├── __init__.py
│   │   ├── base.py                      # BaseTool, ToolResult
│   │   ├── registry.py                  # @register_tool, get_tools()
│   │   │
│   │   ├── map_fields/                  # map_fields Tool ★改为包
│   │   │   ├── __init__.py
│   │   │   ├── tool.py                  # map_fields Tool 实现（调用 PlatformAdapter.field_mapper）
│   │   │   └── models.py                # MapFieldsInput, MapFieldsOutput, FieldMappingError
│   │   │
│   │   ├── build_query/                 # build_query Tool ★改为包
│   │   │   ├── __init__.py
│   │   │   ├── tool.py                  # build_query Tool 实现（调用 PlatformAdapter.query_builder）
│   │   │   └── models.py                # BuildQueryInput, BuildQueryOutput, QueryBuildError
│   │   │
│   │   └── execute_query/               # execute_query Tool ★改为包
│   │       ├── __init__.py
│   │       ├── tool.py                  # execute_query Tool 实现（调用 PlatformAdapter.execute）
│   │       └── models.py                # ExecuteQueryInput, ExecuteQueryOutput, ExecutionError
│   │
│   ├── workflow/                        # 主工作流
│   │   ├── __init__.py
│   │   ├── factory.py                   # create_workflow()（3 节点：2 Subgraph + 1 单节点）
│   │   ├── routes.py                    # route_after_semantic_parser(), route_after_replanner()（支持 Send()）
│   │   └── state.py                     # VizQLState（含 accumulated_insights + merge_insights reducer）
│   │
│   └── middleware/                      # 中间件
│       ├── __init__.py
│       ├── runner.py                    # MiddlewareRunner
│       ├── todo_list.py                 # TodoListMiddleware
│       ├── summarization.py             # SummarizationMiddleware
│       ├── model_retry.py               # ModelRetryMiddleware
│       ├── tool_retry.py                # ToolRetryMiddleware
│       ├── filesystem.py                # FilesystemMiddleware
│       ├── patch_tool_calls.py          # PatchToolCallsMiddleware
│       ├── human_in_the_loop.py         # HumanInTheLoopMiddleware
│       └── output_validation.py         # OutputValidationMiddleware
│
├── __init__.py
└── main.py                              # 应用入口

# ===== 已删除的目录/文件 =====
# nodes/                                 # ★整个目录已删除
#   ├── execute/                         # → 逻辑移到 orchestration/tools/execute_query/
#   ├── query_builder/                   # → 逻辑移到 orchestration/tools/build_query/
#   └── self_correction/                 # → 功能由 ReAct 错误处理替代
#
# agents/semantic_parser/components/observer.py  # ★已删除，功能由 ReAct 替代
# agents/insight/components/synthesizer.py       # ★已删除，功能合并到 Director
# core/models/observer.py                # ★已删除，功能由 ReAct 替代
#
# infra/config/tableau_env.py            # ★已删除：多环境配置不需要
# infra/utils/                           # ★整个目录已删除
#   └── conversation.py                  # trim_answered_questions() 移到使用处
# infra/ai/rag/                          # ★已移动到 agents/field_mapper/rag/
#
# platforms/tableau/client.py            # ★已删除：薄包装器不需要，直接使用 vizql_client.py
# platforms/tableau/metadata.py          # ★已重命名为 tableau_data_model.py
```

### 架构分层说明

本项目采用**分层架构**，实现平台无关的通用 AI 数据分析能力：

| 层级 | 目录 | 职责 | 平台依赖 |
|------|------|------|---------|
| **API 层** | `api/` | HTTP 端点、请求处理 | 无 |
| **核心层** | `core/` | 抽象接口、核心模型、状态定义 | 无 |
| **Agent 层** | `agents/` | AI Agent 实现（Subgraph） | 无 |
| **编排层** | `orchestration/` | 工作流编排、中间件、工具 | 无 |
| **平台层** | `platforms/` | 平台适配器实现 | **有**（Tableau/PowerBI/...） |
| **基础设施层** | `infra/` | LLM、存储、配置、监控 | 部分（配置相关） |

### 平台扩展性

通过 `platforms/` 目录的适配器模式，可以轻松支持其他 BI 平台：

```
platforms/
├── base.py                    # PlatformAdapter 抽象基类
├── tableau/                   # Tableau 实现
│   ├── adapter.py
│   ├── field_mapper.py
│   ├── query_builder.py
│   └── vizql_client.py
├── powerbi/                   # ★未来：Power BI 实现
│   ├── adapter.py
│   ├── field_mapper.py
│   ├── query_builder.py
│   └── dax_client.py
└── superset/                  # ★未来：Apache Superset 实现
    └── ...
```

**核心接口**（`core/interfaces/`）：
- `PlatformAdapter`：平台适配器接口
- `FieldMapper`：字段映射接口
- `QueryBuilder`：查询构建接口

**Tool 与平台的关系**：
- `orchestration/tools/` 中的 Tool 调用 `PlatformAdapter` 接口
- 具体实现由 `platforms/` 中的适配器提供
- Agent 层完全平台无关

### 目录结构对比

| 方面 | 重构前 | 重构后 |
|------|--------|--------|
| 节点目录 | `nodes/` (3 个子目录) | ★已删除，逻辑移到 Tools |
| Tool 目录 | 无 | `orchestration/tools/` ★新增（每个 Tool 一个包） |
| Agent 目录 | 5 个 Agent | 5 个 Agent (field_mapper + dimension_hierarchy + 3 个 Subgraph) |
| Observer | `observer.py` | ★已删除，由 ReAct 替代 |
| Synthesizer | `synthesizer.py` | ★已删除，合并到 Director |
| 主持人/总监 | `coordinator.py` | `director.py` ★重命名 |
| 错误处理 | SelfCorrection 节点 | `react_error_handler.py` ★新增 |
| 数据模型 | 集中在 `core/models/` | Agent 特有模型分散到各 Agent 的 `models/` 包中 |
| RAG | `infra/ai/rag/` | `agents/field_mapper/rag/` ★移到 Agent 内 |
| 平台层 | `platforms/` | 保持不变，提供平台适配器 |
| 基础设施层 | `infra/` | 保持不变，提供 AI/存储/配置 |
| API 层 | `api/` | 保持不变 |
| 核心接口 | `core/interfaces/` | 保持不变，定义平台无关接口 |

### 核心层定义与职责

**核心层 (`core/`) 的本质**：定义**平台无关的语义层抽象**，是整个系统的"契约层"。

核心层包含三类内容：

| 类别 | 目录 | 职责 | 示例 |
|------|------|------|------|
| **接口定义** | `core/interfaces/` | 定义平台适配器必须实现的抽象接口 | `PlatformAdapter`, `FieldMapper`, `QueryBuilder` |
| **核心模型** | `core/models/` | 定义平台无关的语义层数据结构 | `SemanticQuery`, `Computation`, `Filter` |
| **状态定义** | `core/state.py` | 定义工作流全局状态 | `VizQLState` |
| **异常定义** | `core/exceptions.py` | 定义核心异常类型 | `SemanticParseError`, `ValidationError` |

**核心层的设计原则**：
1. **零平台依赖**：核心层代码不能导入 `platforms/` 或 `infra/` 中的任何内容
2. **契约优先**：核心层定义的接口和模型是各层之间的"契约"
3. **稳定性**：核心层变更需要谨慎，因为会影响所有依赖层

### 核心模型分类标准

**判断标准**：模型是否代表**平台无关的语义概念**？

| 分类 | 判断标准 | 保留在 `core/models/` | 迁移到 Agent `models/` |
|------|---------|----------------------|----------------------|
| **语义层核心** | 表示用户意图的平台无关抽象 | ✅ | |
| **Agent 处理中间态** | 仅在特定 Agent 内部使用 | | ✅ |
| **LLM 输入/输出** | 特定 Prompt 的结构化输出 | | ✅ |

### 金字塔继承结构（重要设计原则）

核心层定义**最小颗粒度的基础抽象**，Agent 层的模型应该**继承或组合**核心层模型：

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              核心层 (core/models/)                                   │
│                           最小颗粒度的基础抽象（金字塔底层）                           │
│                                                                                      │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌───────────────┐  │
│  │   字段抽象       │  │   过滤器抽象     │  │   计算抽象       │  │   结果抽象     │  │
│  │  DimensionField │  │  Filter (基类)  │  │  Computation    │  │  ExecuteResult│  │
│  │  MeasureField   │  │  ├─SetFilter    │  │  CalcParams     │  │  ColumnMeta   │  │
│  │  Sort           │  │  ├─DateRange    │  │                 │  │               │  │
│  │                 │  │  └─...          │  │                 │  │               │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  └───────────────┘  │
│                                    │                                                │
│                                    ▼                                                │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                        SemanticQuery (组合模型)                              │   │
│  │              组合 DimensionField + MeasureField + Filter + Computation       │   │
│  │                      ★ 语义解析的最终产物，平台适配器的输入                    │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         │ 继承/组合
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              Agent 层 (agents/*/models/)                             │
│                           Agent 特有的处理模型（金字塔上层）                          │
│                                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │  SemanticParser models/                                                      │   │
│  │  ├── Step1Output                                                             │   │
│  │  │   ├── MeasureSpec (使用 MeasureField 的字段 + 额外的 LLM 输出字段)         │   │
│  │  │   ├── DimensionSpec (使用 DimensionField 的字段 + 额外的 LLM 输出字段)     │   │
│  │  │   └── FilterSpec (使用 Filter 的字段 + 额外的 LLM 输出字段)                │   │
│  │  ├── Step2Output (组合 Computation)                                          │   │
│  │  └── ReActOutput (Agent 特有)                                                │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │  InsightAgent models/                                                        │   │
│  │  ├── Insight (Agent 特有的洞察输出)                                          │   │
│  │  ├── EnhancedDataProfile (组合 ColumnStats 等核心统计模型)                    │   │
│  │  └── DirectorOutput (Agent 特有)                                             │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │  Replanner models/                                                           │   │
│  │  └── ReplanDecision (Agent 特有的决策输出)                                   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### 当前问题与解决方案

**问题**：当前 `Step1Output` 中的 `MeasureSpec`, `DimensionSpec`, `FilterSpec` 与核心层的 `MeasureField`, `DimensionField`, `Filter` 是**重复定义**，而不是继承关系。

**解决方案**：

| 当前模型 | 问题 | 解决方案 |
|---------|------|---------|
| `MeasureSpec` | 与 `MeasureField` 重复 | 继承 `MeasureField` 或直接使用 |
| `DimensionSpec` | 与 `DimensionField` 重复 | 继承 `DimensionField` 或直接使用 |
| `FilterSpec` | 与 `Filter` 重复 | 继承 `Filter` 或直接使用 |
| `Insight` | 无核心层基类 | 保持独立（Agent 特有输出） |
| `ReplanDecision` | 无核心层基类 | 保持独立（Agent 特有输出） |

**重构建议**：

```python
# 方案 1: 直接使用核心层模型
class Step1Output(BaseModel):
    what: What  # What.measures: List[MeasureField]
    where: Where  # Where.dimensions: List[DimensionField], Where.filters: List[Filter]
    
# 方案 2: 继承并扩展
class MeasureSpec(MeasureField):
    """Step1 特有的度量规格，继承自核心层 MeasureField"""
    sort_direction: SortDirection | None = None  # Step1 特有字段
    sort_priority: int = 0  # Step1 特有字段
```

**本次重构范围**：
- 模型迁移时保持现有结构（避免大规模重构）
- 在设计文档中记录理想的金字塔结构
- 后续迭代中逐步统一模型继承关系

### 核心模型详细分类

**保留在 `core/models/`（真正的核心层 - 最小颗粒度的基础抽象）**：

| 文件 | 模型 | 保留原因 |
|------|------|---------|
| `enums.py` | `IntentType`, `CalcType`, `FilterType`, `AggregationType`, ... | 基础枚举，定义语义层的"词汇表"，所有层都使用 |
| `fields.py` | `DimensionField`, `MeasureField`, `Sort` | 字段基础抽象，所有 BI 平台都有维度/度量概念 |
| `filters.py` | `Filter`, `SetFilter`, `DateRangeFilter`, `NumericRangeFilter`, `TextMatchFilter`, `TopNFilter` | 过滤器基础抽象，所有 BI 平台都支持 |
| `computations.py` | `Computation`, `CalcParams` | **核心抽象**：`Computation = Target × CalcType × Partition × Params`，统一 Tableau/PowerBI/SQL 的计算表达 |
| `query.py` | `SemanticQuery` | **核心输出**：组合 Field + Filter + Computation，语义解析的最终产物 |
| `execute_result.py` | `ExecuteResult`, `ColumnMetadata`, `RowData` | 执行结果基础抽象，平台无关的结果表示 |
| `validation.py` | `ValidationResult`, `ValidationError`, `ValidationErrorType` | 验证基础抽象，所有平台都需要 |

**重构后 `core/models/` 只保留 7 个文件（真正的核心层）**

**迁移到其他层的模型**：

| 原文件 | 迁移目标 | 迁移原因 |
|--------|---------|---------|
| `data_model.py` | `infra/storage/data_model.py` | `DataModel`, `FieldMetadata` 是 Tableau 数据源的元数据，不是平台无关的抽象 |
| `dimension_hierarchy.py` | `agents/dimension_hierarchy/models/` | `DimensionHierarchyResult` 是 DimensionHierarchy Agent 的输出 |
| `query_request.py` | `platforms/base.py` | `QueryRequest` 是平台特定查询请求的基类，应该在平台层 |
| `field_mapping.py` | `orchestration/tools/map_fields/models.py` | `MappedQuery`, `FieldMapping` 是字段映射工具的输出 |
| `parse_result.py` | `agents/semantic_parser/models/parse_result.py` | `SemanticParseResult` 是 SemanticParser Agent 的输出 |
| `step1.py` | `agents/semantic_parser/models/step1.py` | `Step1Output` 是 SemanticParser 的内部处理步骤 |
| `step2.py` | `agents/semantic_parser/models/step2.py` | `Step2Output` 是 SemanticParser 的内部处理步骤 |
| `insight.py` | `agents/insight/models/insight.py` | `Insight`, `InsightResult` 是 InsightAgent 的输出 |
| `replan.py` | `agents/replanner/models/output.py` | `ReplanDecision` 是 Replanner 的输出 |
| `observer.py` | **删除** | 由 ReAct 错误处理替代 |

### 模型继承关系统一（本次重构范围）

**问题**：当前 `Step1Output` 中的 `MeasureSpec`, `DimensionSpec`, `FilterSpec` 与核心层的 `MeasureField`, `DimensionField`, `Filter` 是**重复定义**。

**解决方案**：迁移时统一继承关系

```python
# agents/semantic_parser/models/step1.py

from core.models.fields import MeasureField, DimensionField
from core.models.filters import Filter
from core.models.enums import SortDirection

class MeasureSpec(MeasureField):
    """Step1 特有的度量规格，继承自核心层 MeasureField"""
    sort_direction: SortDirection | None = None  # Step1 特有字段
    sort_priority: int = 0  # Step1 特有字段

class DimensionSpec(DimensionField):
    """Step1 特有的维度规格，继承自核心层 DimensionField"""
    # 如果有 Step1 特有字段，在此添加
    pass

class FilterSpec(Filter):
    """Step1 特有的过滤器规格，继承自核心层 Filter"""
    # Step1 特有字段（如 TOP_N 的 n, by_field 等）
    n: int | None = None
    by_field: str | None = None
    direction: SortDirection | None = None
    values: list[str] | None = None
    start_date: str | None = None
    end_date: str | None = None
```

**继承关系图**：

```
core/models/ (金字塔底层 - 最小颗粒度)
├── MeasureField ◄─────────────── agents/semantic_parser/models/MeasureSpec
├── DimensionField ◄───────────── agents/semantic_parser/models/DimensionSpec  
├── Filter ◄───────────────────── agents/semantic_parser/models/FilterSpec
├── Computation ◄──────────────── agents/semantic_parser/models/Step2Output (组合)
└── SemanticQuery ◄────────────── 最终输出，组合所有核心模型
```

### 数据模型组织原则

**核心原则**：
1. **平台无关的核心模型**保留在 `core/models/`（如 `computations.py`, `fields.py`, `filters.py`）
2. **Agent 特有的模型**放在各 Agent 的 `models/` 包中，与 `prompts/` 包平级
3. **Tool 特有的模型**放在各 Tool 包的 `models.py` 中

| 模型类型 | 位置 | 示例 |
|---------|------|------|
| 核心数据模型（平台无关） | `core/models/` | computations.py, fields.py, filters.py, query_request.py |
| SemanticParser 模型 | `agents/semantic_parser/models/` | step1.py, step2.py, pipeline.py, react.py |
| InsightAgent 模型 | `agents/insight/models/` | profile.py, insight.py, director.py, analyst.py |
| Replanner 模型 | `agents/replanner/models/` | output.py |
| Tool 模型 | `orchestration/tools/{tool}/models.py` | MapFieldsInput, BuildQueryInput, ExecuteQueryInput |

### 各 models/ 包详细内容

**core/models/**（★重构后仅保留 7 个文件）:
```
core/models/
├── __init__.py
├── enums.py                 # 语义层枚举（IntentType, CalcType, FilterType, AggregationType, ...）
├── fields.py                # 字段抽象（DimensionField, MeasureField, Sort）
├── filters.py               # 过滤器抽象（SetFilter, DateRangeFilter, NumericRangeFilter, TextMatchFilter, TopNFilter）
├── computations.py          # ★核心：Computation = Target × CalcType × Partition × Params
├── query.py                 # ★核心输出：SemanticQuery（语义解析的最终产物，平台适配器的输入）
├── execute_result.py        # 执行结果抽象（ExecuteResult, ColumnMetadata, RowData）
└── validation.py            # 验证结果抽象（ValidationResult, ValidationError）
```

**为什么只保留这 7 个文件？**
- 这些是**最小颗粒度的基础抽象**，定义了语义层的"词汇表"
- 所有 BI 平台（Tableau/PowerBI/Superset）都有这些概念
- Agent 层的模型应该**继承或组合**这些核心模型
- 核心层零依赖原则：不导入 `platforms/`、`infra/`、`agents/`

**infra/storage/**（新增 data_model.py）:
```
infra/storage/
├── __init__.py
├── data_model.py            # ★从 core/models/ 迁移：DataModel, FieldMetadata, LogicalTable
├── data_model_cache.py      # 数据模型缓存
├── data_model_loader.py     # 数据模型加载器
├── golden_queries.py        # 黄金查询存储
└── langgraph_store.py       # LangGraph 状态存储
```

**platforms/base.py**（新增 QueryRequest）:
```python
# platforms/base.py
from abc import ABC, abstractmethod
from pydantic import BaseModel

class QueryRequest(BaseModel):
    """平台特定查询请求的基类，从 core/models/query_request.py 迁移"""
    # ... 原有定义 ...

class PlatformAdapter(ABC):
    """平台适配器抽象基类"""
    # ...
```

**platforms/tableau/models/**（Tableau 特定模型）:
```
platforms/tableau/models/
├── __init__.py              # 导出所有 Tableau 模型
├── vizql_types.py           # VizQL API 类型定义
│                            # ├── VizQLFunction, VizQLSortDirection, VizQLDataType
│                            # ├── VizQLFieldRole, VizQLColumnClass
│                            # ├── VizQLFieldBase, VizQLDimensionField, VizQLMeasureField, VizQLCalculatedField
│                            # ├── VizQLFilterType, VizQLFilterBase, VizQLSetFilter, VizQLDateFilter, ...
│                            # └── VizQLQueryRequest (继承 QueryRequest), VizQLQueryResponse
├── table_calc.py            # 表计算规格
│                            # ├── TableCalcType, TableCalcAggregation, RankType, RelativeTo
│                            # ├── TableCalcSpecification (基类)
│                            # ├── RankTableCalcSpecification, PercentOfTotalTableCalcSpecification
│                            # ├── RunningTotalTableCalcSpecification, MovingTableCalcSpecification
│                            # └── DifferenceTableCalcSpecification, PercentDifferenceTableCalcSpecification
├── lod.py                   # LOD 表达式
│                            # ├── LODType (FIXED, INCLUDE, EXCLUDE)
│                            # └── LODExpression, determine_lod_type()
└── execute_result.py        # 执行结果
                             # ├── ExecuteResult, ColumnMetadata
                             # └── RowData, RowValue
```

**agents/field_mapper/**（★保留在 agents：LLM 字段映射 Agent）:
```
agents/field_mapper/
├── __init__.py
├── node.py                  # 字段映射节点
├── prompt.py                # 字段映射 Prompt
├── models/                  # Agent 特有模型
│   ├── __init__.py
│   └── mapping.py           # MappedQuery, FieldMapping, AlternativeMapping
└── rag/                     # ★RAG 放在 Agent 内（LLM 调用的一部分）
    ├── __init__.py
    ├── assembler.py         # RAG 组装器
    ├── cache.py             # 映射缓存（LangGraph SqliteStore）
    ├── dimension_pattern.py # 维度模式识别
    ├── embeddings.py        # 嵌入模型
    ├── field_indexer.py     # 字段索引器
    ├── models.py            # RAG 数据模型（FieldCandidate, MappingResult）
    ├── observability.py     # 可观测性
    ├── reranker.py          # 重排序器
    ├── retriever.py         # 检索器
    └── semantic_mapper.py   # 语义映射器（RAG+LLM 混合策略）
```

**agents/dimension_hierarchy/**（维度层级 Agent）:
```
agents/dimension_hierarchy/
├── __init__.py
├── node.py                  # 节点实现
├── prompt.py                # Prompt 定义
└── models/                  # ★Agent 特有模型
    ├── __init__.py
    └── hierarchy.py         # DimensionHierarchyResult, DimensionAttributes（从 core/models/ 迁移）
```

**agents/dimension_hierarchy/models/**（新增）:
```
agents/dimension_hierarchy/models/
├── __init__.py
└── hierarchy.py             # ★从 core/models/ 迁移：DimensionHierarchyResult, DimensionAttributes
```

**SemanticParser models/**（Agent 特有模型）:
```
agents/semantic_parser/models/
├── __init__.py
├── step1.py                 # ★从 core/models/ 迁移：Step1Output, MeasureSpec, DimensionSpec, FilterSpec
│                            #   MeasureSpec 继承 MeasureField
│                            #   DimensionSpec 继承 DimensionField
│                            #   FilterSpec 继承 Filter
├── step2.py                 # ★从 core/models/ 迁移：Step2Output
├── parse_result.py          # ★从 core/models/ 迁移：SemanticParseResult, ClarificationQuestion
├── pipeline.py              # QueryResult, QueryError
└── react.py                 # ReActThought, ReActAction, ReActObservation, ReActOutput
```

**InsightAgent models/**（Agent 特有模型）:
```
agents/insight/models/
├── __init__.py
├── profile.py               # EnhancedDataProfile, ContributorAnalysis, ConcentrationRisk, 
│                            # PeriodChangeAnalysis, TrendAnalysis, DimensionIndex, AnomalyIndex
├── insight.py               # ★从 core/models/ 迁移：Insight, InsightQuality, InsightResult
├── director.py              # DirectorInput, DirectorDecision, DirectorOutputWithAccumulation
└── analyst.py               # AnalystOutputWithHistory, HistoricalInsightAction
```

**Replanner models/**（Agent 特有模型）:
```
agents/replanner/models/
├── __init__.py
└── output.py                # ★从 core/models/ 迁移：ReplanDecision, ExplorationQuestion
```

**Tool models/**（Tool 特有模型）:
```
orchestration/tools/map_fields/              # ★包装 agents/field_mapper 的 Tool
├── __init__.py
├── tool.py                  # MapFieldsTool（调用 agents/field_mapper）
└── models.py                # MapFieldsInput, MapFieldsOutput, FieldMappingError
                             # 注意：MappedQuery, FieldMapping 等核心模型在 agents/field_mapper/models/

orchestration/tools/build_query/
├── __init__.py
├── tool.py                  # BuildQueryTool
└── models.py                # BuildQueryInput, BuildQueryOutput, QueryBuildError

orchestration/tools/execute_query/
├── __init__.py
├── tool.py                  # ExecuteQueryTool
└── models.py                # ExecuteQueryInput, ExecuteQueryOutput, ExecutionError
```

### 模型迁移说明

| 原位置 | 新位置 | 说明 |
|--------|--------|------|
| `core/models/data_model.py` | `infra/storage/data_model.py` | 数据源元数据，不是平台无关抽象 |
| `core/models/dimension_hierarchy.py` | `agents/dimension_hierarchy/models/hierarchy.py` | Agent 输出模型（需要 DataModel 依赖） |
| `core/models/query_request.py` | `platforms/base.py` | 平台特定查询请求基类 |
| `core/models/field_mapping.py` | `agents/field_mapper/models/mapping.py` | ★字段映射 Agent 的输出模型 |
| `core/models/parse_result.py` | `agents/semantic_parser/models/parse_result.py` | Agent 输出模型 |
| `core/models/step1.py` | `agents/semantic_parser/models/step1.py` | Agent 内部处理步骤，MeasureSpec/DimensionSpec/FilterSpec 继承核心层 |
| `core/models/step2.py` | `agents/semantic_parser/models/step2.py` | Agent 内部处理步骤 |
| `core/models/insight.py` | `agents/insight/models/insight.py` | Agent 输出模型 |
| `core/models/replan.py` | `agents/replanner/models/output.py` | Agent 输出模型 |
| `core/models/observer.py` | ★删除 | 由 ReAct 替代 |
| `infra/ai/rag/*` | `agents/field_mapper/rag/` | ★RAG 是字段映射 Agent 的实现细节（LLM 调用的一部分） |
| `infra/config/tableau_env.py` | ★删除 | 多环境配置不需要 |
| `infra/utils/conversation.py` | ★删除 | 功能过于简单，移到使用处 |
| `platforms/tableau/client.py` | ★删除 | 薄包装器不需要，直接使用 vizql_client.py |
| `platforms/tableau/metadata.py` | `platforms/tableau/tableau_data_model.py` | ★重命名：Tableau 数据模型处理 |
| `core/models/enums.py` | 保持不变 | 平台无关的核心模型（基础枚举） |
| `core/models/fields.py` | 保持不变 | 平台无关的核心模型（字段抽象） |
| `core/models/filters.py` | 保持不变 | 平台无关的核心模型（过滤器抽象） |
| `core/models/computations.py` | 保持不变 | 平台无关的核心模型（计算抽象） |
| `core/models/query.py` | 保持不变 | 平台无关的核心模型（SemanticQuery） |
| `core/models/execute_result.py` | 保持不变 | 平台无关的核心模型（执行结果） |
| `core/models/validation.py` | 保持不变 | 平台无关的核心模型（验证结果） |

---

## 核心架构：层级 Agent 编排

### 架构总览

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                              Main Workflow (StateGraph)                               │
│                                                                                       │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐ │
│  │                      SemanticParserAgent (Subgraph)                              │ │
│  │  Step1 → Step2 → QueryPipeline (MapFields → BuildQuery → ExecuteQuery)          │ │
│  │  任意工具错误 → ReAct 错误处理 (Thought → Action → Observation)                  │ │
│  └─────────────────────────────────────────────────────────────────────────────────┘ │
│                                          │                                            │
│                                          ▼                                            │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐ │
│  │                      InsightAgent (Subgraph)                                     │ │
│  │  Profiler(CODE) → Director ⟷ Analyst (双 LLM 协作 + 渐进式累积) → END           │ │
│  │  总监负责：决策 + 洞察累积 + 最终综合（无 Synthesizer）                           │ │
│  └─────────────────────────────────────────────────────────────────────────────────┘ │
│                                          │                                            │
│                                          ▼                                            │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐ │
│  │                      ReplannerAgent (单 LLM 节点)                                │ │
│  │  评估完成度 → 识别缺失 → 生成探索问题 → 决策: should_replan                      │ │
│  └─────────────────────────────────────────────────────────────────────────────────┘ │
│                                          │                                            │
│              ┌───────────────────────────┼───────────────────────────┐               │
│              ▼                           ▼                           ▼               │
│      should_replan=False          单问题 (N=1)                 多问题 (N>1)          │
│              │                           │                           │               │
│              ▼                           ▼                           ▼               │
│            END                   串行: semantic_parser      Send() 动态并行分支      │
│                                          │                           │               │
│                                          │         ┌─────────────────┼─────────────┐ │
│                                          │         ▼                 ▼             ▼ │
│                                          │   SemanticParser(Q1) SemanticParser(Q2) ...│
│                                          │         │                 │             │ │
│                                          │         ▼                 ▼             ▼ │
│                                          │     Insight(Q1)       Insight(Q2)      ...│
│                                          │         │                 │             │ │
│                                          │         └─────────────────┴─────────────┘ │
│                                          │                           │               │
│                                          │              LangGraph 自动合并状态        │
│                                          │              (merge_insights reducer)     │
│                                          │                           │               │
│                                          └───────────────────────────┘               │
│                                                      │                               │
│                                                      ▼                               │
│                                                  Replanner                           │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

### 并行执行说明

| 场景 | 执行方式 | 实现机制 |
|------|---------|---------|
| 用户初始问题 | 单次执行 | 普通边 |
| Replanner 生成 1 个问题 | 串行执行 | 返回节点名 |
| Replanner 生成 N 个问题 (N>1) | 动态并行 | Send() API |
| 用户选择特定问题 | 单次执行 | 普通边 |

**与 ai-hedge-fund-main 的区别**：
- ai-hedge-fund-main 使用**静态并行边**（编译时确定分析师数量）
- 我们使用 **Send() API 动态并行**（运行时确定问题数量）
- 两者都使用 reducer 合并并行分支状态

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

### Send() API 动态并行机制

当 Replanner 生成多个探索问题时，使用 Send() API 动态创建并行分支：

```python
from langgraph.constants import Send

def route_after_replanner(state: VizQLState) -> Union[str, List[Send]]:
    """
    Replanner 后的路由决策
    - 完成 → END
    - 单问题 → semantic_parser（串行）
    - 多问题 → Send() 并行分发
    """
    questions = state.get("exploration_questions", [])
    
    if not questions:
        return "end"
    elif len(questions) == 1:
        return "semantic_parser"  # 串行执行
    else:
        # 动态创建 N 个并行分支
        return [
            Send("semantic_parser", {"question": q, "branch_id": i})
            for i, q in enumerate(questions)
        ]
```

**状态合并**：并行分支完成后，LangGraph 自动使用 reducer 合并状态：

```python
def merge_insights(existing: List[Insight], new: List[Insight]) -> List[Insight]:
    """洞察合并 reducer - 并行分支的洞察自动合并"""
    return existing + new

class VizQLState(TypedDict):
    accumulated_insights: Annotated[List[Insight], merge_insights]
```

---

## SemanticParserAgent 设计

### 架构：固定流程 + ReAct 错误处理

**核心设计决策**：

1. **正常流程是固定的**：Step1 → Step2 → MapFields → BuildQuery → ExecuteQuery
2. **工具错误触发 ReAct**：任意工具返回错误时，进入 ReAct 错误处理模式
3. **ReAct 完整循环**：Thought → Action → Observation（工具返回的结构化错误作为初始 Observation，RETRY 后观察新结果）
4. **ReAct 替代 Observer**：原 Observer 的功能由 ReAct 错误处理承担
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
│                          ┌─────────┴─────────┐                              │
│                          ▼                   ▼                              │
│                     success=True        error 发生                          │
│                          │                   │                              │
│                          ▼                   ▼                              │
│                    进入 Insight      ReAct 错误处理                         │
│                                              │                              │
│  ┌───────────────────────────────────────────┴──────────────────────────┐  │
│  │              ReAct 错误处理 (Thought → Action → Observation)          │  │
│  │                                                                       │  │
│  │  初始 Observation：工具返回的结构化错误                               │  │
│  │                                                                       │  │
│  │  ┌─────────┐     ┌─────────┐     ┌─────────────┐                     │  │
│  │  │ Thought │────▶│ Action  │────▶│ Observation │──┐                  │  │
│  │  └─────────┘     └─────────┘     └─────────────┘  │                  │  │
│  │       ▲                                           │                  │  │
│  │       └───────────────────────────────────────────┘                  │  │
│  │                        (循环直到成功或 ABORT)                         │  │
│  │                                                                       │  │
│  │  Action 选项：                                                        │  │
│  │  ├── RETRY: 使用修正后的参数重试工具 → 观察结果                       │  │
│  │  ├── CLARIFY: 向用户请求澄清 → 结束循环，等待用户                     │  │
│  │  └── ABORT: 放弃并返回错误 → 结束循环                                 │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### ReAct 错误处理详细设计

**标准 ReAct 循环**：
```
Thought → Action → Observation → Thought → Action → Observation → ...
```

**我们的 ReAct 错误处理流程**：
```
工具返回错误（初始 Observation）
     │
     ▼
┌─────────────┐
│   Thought   │  LLM 分析：
│             │  - 错误类型是什么？
│             │  - 能否通过修正参数解决？
│             │  - 是否需要用户澄清？
│             │  - 是否无法恢复？
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Action    │  三选一：
│             │  - RETRY: 重试工具（带修正参数）
│             │  - CLARIFY: 请求用户澄清
│             │  - ABORT: 返回错误
└──────┬──────┘
       │
       ├── RETRY ──────────────────┐
       │                           ▼
       │                    重新执行工具
       │                           │
       │                           ▼
       │                    ┌─────────────┐
       │                    │ Observation │  观察工具执行结果
       │                    └──────┬──────┘
       │                           │
       │              ┌────────────┴────────────┐
       │              ▼                         ▼
       │         success=True              再次 error
       │              │                         │
       │              ▼                         ▼
       │         进入 Insight            回到 Thought
       │                                  (最多 N 次)
       │
       ├── CLARIFY ────────────────┐
       │                           ▼
       │                    返回澄清问题
       │                    等待用户输入
       │
       └── ABORT ──────────────────┐
                                   ▼
                            返回错误信息
```

**完整 ReAct 循环示例**：
```
1. 正常流程执行 MapFields 工具
2. 工具返回错误: field_not_found "销售额字段不存在"
   └── Observation: 错误信息 + suggestions: ["销售金额", "营业额"]

3. Thought: 分析错误，发现可以用 suggestions 中的字段重试
   └── 决定: RETRY

4. Action: RETRY，使用 "销售金额" 替换 "销售额"
   └── 执行 MapFields 工具

5. Observation: 工具返回成功，映射完成
   └── 结束 ReAct，继续正常流程

或者：

5. Observation: 工具返回新错误 "销售金额字段无权限"
   └── 回到 Thought

6. Thought: 分析错误，发现是权限问题，无法通过修正参数解决
   └── 决定: ABORT

7. Action: ABORT，返回友好错误信息给用户
```

### ReAct 数据模型

```python
class RetryTarget(str, Enum):
    """Target step to retry from."""
    STEP1 = "step1"              # Retry semantic understanding
    STEP2 = "step2"              # Retry computation reasoning
    MAP_FIELDS = "map_fields"    # Retry field mapping
    BUILD_QUERY = "build_query"  # Retry query building

class ReActThought(BaseModel):
    """ReAct 思考输出 - LLM 分析错误根因"""
    error_analysis: str  # 错误分析
    root_cause: str  # 根因识别 - 哪个步骤导致了错误
    can_retry: bool  # 是否可以重试
    needs_clarification: bool  # 是否需要澄清
    reasoning: str  # 推理过程

class ReActAction(BaseModel):
    """ReAct 动作 - 基于 Thought 决定下一步"""
    action_type: Literal["RETRY", "CLARIFY", "ABORT"]
    
    # RETRY: 从哪个步骤重试
    retry_from: Optional[RetryTarget] = None
    
    # RETRY: 传递给重试步骤的错误反馈
    error_feedback: Optional[str] = None
    
    # CLARIFY: 澄清问题（LLM 生成）
    clarification_question: Optional[str] = None
    
    # ABORT: 用户友好消息（LLM 生成）
    user_message: Optional[str] = None

class ReActObservation(BaseModel):
    """ReAct 观察结果 - 步骤执行结果"""
    success: bool
    step: str  # 哪个步骤产生的结果
    result: Optional[Any] = None  # 成功时的结果
    error_type: Optional[str] = None  # 失败时的错误类型
    error_message: Optional[str] = None  # 失败时的错误消息
    error_details: Optional[Dict[str, Any]] = None  # 额外错误详情

class ReActOutput(BaseModel):
    """ReAct 完整输出（单轮）"""
    thought: ReActThought
    action: ReActAction
```

### 错误处理流程示例

```
场景：execute_query 返回 LOD 表达式错误

1. QueryPipeline 执行到 execute_query
2. Tableau 服务器返回错误: "FIXED requires at least one dimension"
3. ReActErrorHandler 分析错误:
   - Thought: 
     - error_analysis: "LOD 表达式缺少维度"
     - root_cause: "step2"  # 计算推理阶段设计的 LOD 有问题
     - can_retry: True
     - reasoning: "LOD 表达式需要至少一个维度，需要回到 step2 重新设计计算"
   - Action:
     - action_type: RETRY
     - retry_from: "step2"
     - error_feedback: "LOD 表达式需要至少一个维度，请确保 FIXED 计算包含维度字段"
4. DecisionHandler 准备重试:
   - 保留 step1_output
   - 清除 step2_output, mapped_query, vizql_query
   - 将 error_feedback 传递给 step2
5. QueryPipeline 从 step2 重新执行
```

### ReAct Prompt

```python
class ReActErrorHandlerPrompt(VizQLPrompt):
    """ReAct 错误处理 Prompt"""
    
    def get_task(self) -> str:
        return """You are handling a tool execution error. Analyze the error and decide the next action.

Actions available:
- RETRY: Retry the tool with corrected parameters
- CLARIFY: Ask the user for clarification
- ABORT: Give up and return an error message to the user

Guidelines:
- RETRY if the error can be fixed by adjusting parameters (e.g., field name typo, wrong filter value)
- CLARIFY if the user's intent is ambiguous or multiple interpretations exist
- ABORT if the error is unrecoverable (e.g., no permission, data source doesn't exist)"""
    
    def get_user_template(self) -> str:
        return """## 原始问题
{question}

## 执行的工具
{tool_name}

## 工具参数
{tool_params}

## 错误信息
- 类型: {error_type}
- 消息: {error_message}
- 建议: {suggestions}

## 重试次数
{retry_count} / {max_retries}

## 请分析错误并决定下一步动作"""
    
    def get_output_model(self) -> Type[BaseModel]:
        return ReActOutput
```

### ReAct 替代 Observer

| 方面 | 原 Observer | ReAct 错误处理 |
|------|------------|---------------|
| 触发时机 | 每次工具调用后 | 仅工具返回错误时 |
| 输入 | 工具输出 | 结构化错误（作为 Observation） |
| 流程 | 观察 + 判断 | Thought → Action → Observation 循环 |
| 输出 | 继续/重试/停止 | RETRY/CLARIFY/ABORT |
| 复杂度 | 每次都调用 LLM | 仅错误时进入循环 |
| 标准性 | 自定义 | 标准 ReAct 模式 |

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
START → profiler → director ⟷ analyst → END
                       ↑            │
                       └────────────┘ (循环直到总监决定停止)
```

**关键说明**：
- **Profiler**：纯代码实现，生成 EnhancedDataProfile
- **Director（总监 LLM）**：决策 + 洞察累积 + 最终综合
- **Analyst（分析师 LLM）**：分析数据块，生成新洞察 + 历史洞察处理建议
- **无 Synthesizer**：洞察综合由总监 LLM 在最后一轮完成

**总监 LLM 职责**：
1. 决定下一块分析（analyze_chunk | analyze_dimension | analyze_anomaly）
2. 执行洞察累积（MERGE/REPLACE/KEEP/DISCARD）
3. 评估完成度，决定是否早停
4. 最后一轮生成最终摘要（替代 Synthesizer）

---

## 渐进式洞察累积设计

### 设计目标

在多轮分析中，洞察不是简单追加，而是由 LLM 智能决定如何处理历史洞察：
- **MERGE**：与新洞察合并（主题相似，信息互补）
- **REPLACE**：被新洞察替换（新洞察更准确/更新）
- **KEEP**：保留（仍然有价值）
- **DISCARD**：丢弃（已过时/不再相关）

### 双 LLM 协作模式（总监 + 分析师）

**InsightAgent 只有 2 个 LLM**：
- **总监 LLM (Director)**：决策、洞察累积、最终综合
- **分析师 LLM (Analyst)**：分析数据块、生成洞察

**协作流程**：
```
┌─────────────────────────────────────────────────────────────────┐
│                    InsightAgent Subgraph                         │
│                                                                  │
│  ┌──────────────┐                                               │
│  │   Profiler   │  ← 纯代码：统计分析、索引构建、策略推荐        │
│  │    (CODE)    │                                               │
│  └──────┬───────┘                                               │
│         │                                                        │
│         ▼                                                        │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              双 LLM 协作循环                              │   │
│  │                                                          │   │
│  │  ┌─────────────┐         ┌─────────────────────────┐    │   │
│  │  │ 分析师 LLM  │────────▶│       总监 LLM          │    │   │
│  │  │  (Analyst)  │         │      (Director)         │    │   │
│  │  └─────────────┘         └───────────┬─────────────┘    │   │
│  │        ▲                             │                   │   │
│  │        │                             │                   │   │
│  │        │         继续分析            │                   │   │
│  │        └─────────────────────────────┘                   │   │
│  │                                      │                   │   │
│  │                                      │ 停止              │   │
│  │                                      ▼                   │   │
│  │                            输出最终洞察                  │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

**分析师 LLM 输出**：
```
输入：数据块 + 历史洞察（带索引）
输出：
  ├── new_insights: 新发现的洞察
  └── historical_actions: 历史洞察处理建议
      - MERGE: 与新洞察合并
      - REPLACE: 被新洞察替换
      - KEEP: 保留
      - DISCARD: 丢弃
```

**总监 LLM 输出**：
```
输入：分析师输出 + 剩余数据块 + 画像摘要
输出：
  ├── accumulated_insights: 处理后的累积洞察（结构化 Insight 对象列表）
  ├── next_action: 下一步动作 (analyze_chunk | analyze_dimension | stop)
  ├── should_continue: 是否继续
  └── final_summary: 最终摘要（自然语言，仅当 should_continue=False 时输出）
```

**无 Synthesizer 组件**：
- 现有 `synthesizer.py` 的功能（排序、去重、摘要生成）由总监 LLM 在最后一轮完成
- 总监 LLM 在决定停止时，同时输出 `final_summary`

### 新增数据模型

```python
class HistoricalInsightAction(BaseModel):
    """历史洞察处理建议"""
    insight_index: int  # 历史洞察索引（从 0 开始）
    action: Literal["MERGE", "REPLACE", "KEEP", "DISCARD"]
    merge_with_new_index: Optional[int] = None  # MERGE 时，与哪个新洞察合并
    reason: str  # 处理原因

class AnalystOutputWithHistory(BaseModel):
    """分析师输出（增强版）"""
    new_insights: List[Insight]  # 新洞察
    historical_actions: List[HistoricalInsightAction]  # 历史洞察处理建议

class DirectorOutputWithAccumulation(BaseModel):
    """总监输出（增强版）"""
    accumulated_insights: List[Insight]  # 处理后的累积洞察（结构化对象）
    next_action: Literal["analyze_chunk", "analyze_dimension", "analyze_anomaly", "stop"]
    target_chunk_id: Optional[int] = None  # analyze_chunk 时指定
    target_dimension: Optional[str] = None  # analyze_dimension 时指定
    target_dimension_value: Optional[str] = None
    should_continue: bool  # 是否继续分析
    final_summary: Optional[str] = None  # 自然语言摘要（仅当 should_continue=False 时输出）
    insights_quality: InsightQuality  # 洞察质量评估
```

### 分析师 Prompt 增强

```python
class AnalystPromptWithHistory(VizQLPrompt):
    """分析师 LLM Prompt（增强版）"""
    
    def get_task(self) -> str:
        return """Analyze the current data chunk and extract meaningful insights.
        
Additionally, evaluate each historical insight and suggest how to handle it:
- MERGE: Combine with a new insight (similar topic, complementary info)
- REPLACE: Replace with a new insight (new insight is more accurate/updated)
- KEEP: Keep as is (still valuable)
- DISCARD: Remove (outdated or no longer relevant)"""
    
    def get_user_template(self) -> str:
        return """## 原始问题
{question}

## 整体数据画像（用于对比）
- 分布类型：{distribution_type}
- 统计信息：{statistics}
- 帕累托比率：{pareto_ratio}

## Top N 数据摘要（用于排名对比）
{top_n_summary}

## 当前数据块
- 类型：{chunk_type}
- 行数：{row_count}
- 描述：{chunk_description}

数据样本：
{data_sample}

## 历史洞察（需要评估处理方式）
{existing_insights_with_index}

## 输出要求
1. new_insights: 新发现的洞察
2. historical_actions: 对每个历史洞察的处理建议
   - MERGE: 与新洞察合并（指定 merge_with_new_index）
   - REPLACE: 被新洞察替换
   - KEEP: 保留
   - DISCARD: 丢弃"""
    
    def get_output_model(self) -> Type[BaseModel]:
        return AnalystOutputWithHistory
```

### 总监 Prompt 增强

```python
class DirectorPromptWithAccumulation(VizQLPrompt):
    """总监 LLM Prompt（增强版）"""
    
    def get_task(self) -> str:
        return """Evaluate current analysis progress and decide next steps.

Your responsibilities:
1. Process historical insights based on analyst's suggestions (MERGE/REPLACE/KEEP/DISCARD)
2. Output the final accumulated insights list
3. Decide whether to continue analysis or stop
4. If stopping, generate a final summary of all insights"""
    
    def get_user_template(self) -> str:
        return """## 原始问题
{question}

## 整体数据画像（Phase 1 统计分析结果）
- 分布类型：{distribution_type}
- 帕累托比率：{pareto_ratio}
- 异常比例：{anomaly_ratio}
- 聚类数：{cluster_count}
- 推荐分块策略：{chunking_strategy}

## 分析师输出
### 新洞察
{new_insights}

### 历史洞察处理建议
{historical_actions}

## 当前历史洞察
{historical_insights}

## 剩余数据块
{remaining_chunks}

## 已分析块数
{analyzed_count}

## 你的任务
1. 根据分析师的建议处理历史洞察
2. 执行合并/替换/丢弃操作
3. 输出最终的累积洞察列表
4. 决定是否继续分析
5. 如果决定停止，生成最终摘要（final_summary）"""
    
    def get_output_model(self) -> Type[BaseModel]:
        return DirectorOutputWithAccumulation
```

**总监生成最终摘要**：
- 当 `should_continue=False` 时，总监必须输出 `final_summary`
- 摘要包含：洞察数量、类型分布、最重要发现
- 替代原有 Synthesizer 的 `_generate_summary()` 功能

### 处理逻辑说明

**总监 LLM 执行洞察处理**（不是代码实现）：

1. **KEEP**：将历史洞察原样保留到累积列表
2. **DISCARD**：不将历史洞察加入累积列表
3. **REPLACE**：不保留历史洞察，新洞察会自动加入
4. **MERGE**：
   - 找到对应的新洞察（通过 `merge_with_new_index`）
   - 将历史洞察的信息合并到新洞察中
   - 输出合并后的洞察

### 与现有代码的对比

| 方面 | 现有实现 | 增强后 |
|------|---------|--------|
| 分析师输出 | `List[Insight]` | `AnalystOutputWithHistory` |
| 洞察累积 | 代码简单追加 + 标题去重 | **总监 LLM 根据分析师建议处理** |
| 总监输出 | `NextBiteDecision + InsightQuality` | `DirectorOutputWithAccumulation` |
| 处理逻辑 | `_is_duplicate()` 代码实现 | **LLM 实现** |
| 最终综合 | `InsightSynthesizer` 代码实现 | **总监 LLM 生成 final_summary** |
| Synthesizer | 独立组件 | **移除，功能合并到总监** |

---

## 并行执行与洞察合并

### 并行分支输出处理

当 Replanner 生成多个问题并行执行时，每个分支独立运行 SemanticParser → Insight：

```
Replanner 生成 N 个问题
         │
         ▼
    Send() 动态并行
         │
    ┌────┴────┬────────────┐
    ▼         ▼            ▼
Branch 0   Branch 1    Branch N
    │         │            │
    ▼         ▼            ▼
SemanticParser → Insight (各自独立)
    │         │            │
    ▼         ▼            ▼
accumulated_insights_0  accumulated_insights_1  accumulated_insights_N
    │         │            │
    └────┬────┴────────────┘
         │
         ▼
  LangGraph 自动合并
  (merge_insights reducer)
         │
         ▼
  合并后的 accumulated_insights
         │
         ▼
     Replanner
```

### merge_insights Reducer

```python
from typing import Annotated, List

def merge_insights(existing: List[Insight], new: List[Insight]) -> List[Insight]:
    """
    洞察合并 reducer
    
    - 并行分支的洞察自动合并到同一个列表
    - 简单追加，不做去重（去重由下一轮总监 LLM 处理）
    - LangGraph 在并行分支完成后自动调用
    """
    return existing + new

class VizQLState(TypedDict):
    # ... 其他字段 ...
    
    # 渐进式累积洞察（使用自定义 reducer）
    accumulated_insights: Annotated[List[Insight], merge_insights]
```

### 并行后的处理

并行分支合并后，Replanner 接收合并后的洞察：
1. 评估所有洞察的完成度
2. 识别是否还有缺失的分析角度
3. 决定是否继续重规划

如果继续重规划，下一轮的 InsightAgent 总监会看到所有历史洞察（包括并行分支的），并进行智能累积处理。

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

## 中间件、工具与节点的编排详解

本节详细说明中间件、工具和节点如何协同工作，以及状态如何在各组件间流转。

### 整体编排架构

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              Main Workflow (StateGraph)                              │
│                                                                                      │
│  VizQLState (全局状态)                                                               │
│  ├── question: str                    # 用户问题                                     │
│  ├── history: List[Message]           # 对话历史                                     │
│  ├── query_result: QueryResult        # 查询结果                                     │
│  ├── accumulated_insights: List[Insight]  # 累积洞察 (reducer 合并)                  │
│  ├── enhanced_profile: EnhancedDataProfile  # 数据画像                               │
│  └── ...                                                                             │
│                                                                                      │
│  ┌────────────────────────────────────────────────────────────────────────────────┐ │
│  │                    SemanticParserAgent (Subgraph)                               │ │
│  │                                                                                 │ │
│  │  SemanticParserState (子图状态)                                                 │ │
│  │  ├── 继承自 VizQLState 的字段                                                   │ │
│  │  ├── step1_output: Step1Output                                                  │ │
│  │  ├── step2_output: Step2Output                                                  │ │
│  │  ├── pipeline_result: QueryResult                                               │ │
│  │  └── react_state: ReActState (错误处理状态)                                     │ │
│  │                                                                                 │ │
│  │  ┌─────────────────────────────────────────────────────────────────────────┐   │ │
│  │  │                    MiddlewareRunner                                      │   │ │
│  │  │  before_agent() → [节点执行] → after_agent()                             │   │ │
│  │  │                                                                          │   │ │
│  │  │  节点执行时:                                                              │   │ │
│  │  │  - LLM 调用: wrap_model_call() → model.invoke() → after_model()          │   │ │
│  │  │  - Tool 调用: wrap_tool_call() → tool.run() → after_tool()               │   │ │
│  │  └─────────────────────────────────────────────────────────────────────────┘   │ │
│  └────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### 节点与中间件的配合

#### 1. SemanticParserAgent 内部节点

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│  SemanticParserAgent Subgraph                                                        │
│                                                                                      │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────────────────────────┐   │
│  │   Step1      │───▶│   Step2      │───▶│         QueryPipeline                │   │
│  │   (LLM)      │    │   (LLM)      │    │  MapFields → BuildQuery → Execute    │   │
│  └──────────────┘    └──────────────┘    └──────────────────────────────────────┘   │
│        │                   │                              │                          │
│        │                   │                              │                          │
│        ▼                   ▼                              ▼                          │
│  ┌──────────────────────────────────────────────────────────────────────────────┐   │
│  │                         中间件介入点                                          │   │
│  │                                                                               │   │
│  │  Step1/Step2 (LLM 调用):                                                      │   │
│  │  ├── SummarizationMiddleware.wrap_model_call()  # 摘要对话历史                │   │
│  │  ├── ModelRetryMiddleware.wrap_model_call()     # 失败重试                    │   │
│  │  ├── FilesystemMiddleware.wrap_model_call()     # 注入 files 系统提示         │   │
│  │  ├── PatchToolCallsMiddleware.wrap_model_call() # 修复悬空调用                │   │
│  │  └── OutputValidationMiddleware.after_model()   # 验证输出格式                │   │
│  │                                                                               │   │
│  │  MapFields (Tool 调用):                                                       │   │
│  │  └── ToolRetryMiddleware.wrap_tool_call()       # 网络错误重试                │   │
│  │                                                                               │   │
│  │  ExecuteQuery (Tool 调用):                                                    │   │
│  │  ├── ToolRetryMiddleware.wrap_tool_call()       # 网络错误重试                │   │
│  │  ├── FilesystemMiddleware.wrap_tool_call()      # 大结果保存到 files          │   │
│  │  └── HumanInTheLoopMiddleware.wrap_tool_call()  # 敏感操作确认                │   │
│  └──────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                      │
│  ┌──────────────────────────────────────────────────────────────────────────────┐   │
│  │                         ReAct 错误处理                                        │   │
│  │                                                                               │   │
│  │  当 QueryPipeline 中任意 Tool 返回错误时:                                     │   │
│  │                                                                               │   │
│  │  工具错误 (初始 Observation)                                                  │   │
│  │       │                                                                       │   │
│  │       ▼                                                                       │   │
│  │  ┌─────────┐     ┌─────────┐     ┌─────────────┐                             │   │
│  │  │ Thought │────▶│ Action  │────▶│ Observation │──┐                          │   │
│  │  │  (LLM)  │     │         │     │ (Tool结果)  │  │                          │   │
│  │  └─────────┘     └─────────┘     └─────────────┘  │                          │   │
│  │       ▲                                           │                          │   │
│  │       └───────────────────────────────────────────┘                          │   │
│  │                                                                               │   │
│  │  Action 类型:                                                                 │   │
│  │  - RETRY: 修正参数，重新调用 Tool → 观察新结果                                │   │
│  │  - CLARIFY: 返回澄清问题给用户 → 结束                                         │   │
│  │  - ABORT: 返回错误信息给用户 → 结束                                           │   │
│  └──────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

#### 2. InsightAgent 内部节点

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│  InsightAgent Subgraph                                                               │
│                                                                                      │
│  InsightState (子图状态)                                                             │
│  ├── query_result: QueryResult        # 从 SemanticParser 传入                       │
│  ├── enhanced_profile: EnhancedDataProfile  # Profiler 生成                          │
│  ├── chunks: List[DataChunk]          # 数据分块                                     │
│  ├── accumulated_insights: List[Insight]  # 累积洞察                                 │
│  └── final_summary: str               # 最终摘要                                     │
│                                                                                      │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                           │
│  │   Profiler   │───▶│   Director   │◀──▶│   Analyst    │                           │
│  │   (CODE)     │    │   (LLM)      │    │   (LLM)      │                           │
│  └──────────────┘    └──────────────┘    └──────────────┘                           │
│        │                   │                   │                                     │
│        │                   │                   │                                     │
│        ▼                   ▼                   ▼                                     │
│  ┌──────────────────────────────────────────────────────────────────────────────┐   │
│  │                         组件职责                                              │   │
│  │                                                                               │   │
│  │  Profiler (纯代码):                                                           │   │
│  │  ├── 统计分析: 分布检测、异常检测、聚类分析                                   │   │
│  │  ├── 索引构建: dimension_index, anomaly_index                                 │   │
│  │  ├── 策略推荐: 推荐最佳分块策略                                               │   │
│  │  └── 输出: EnhancedDataProfile                                                │   │
│  │                                                                               │   │
│  │  Analyst (分析师 LLM):                                                        │   │
│  │  ├── 输入: 数据块 + 历史洞察                                                  │   │
│  │  ├── 分析: 提取数据洞察                                                       │   │
│  │  ├── 建议: 历史洞察处理建议 (MERGE/REPLACE/KEEP/DISCARD)                      │   │
│  │  └── 输出: AnalystOutputWithHistory                                           │   │
│  │                                                                               │   │
│  │  Director (总监 LLM):                                                         │   │
│  │  ├── 输入: 分析师输出 + 画像摘要 + 剩余数据块                                 │   │
│  │  ├── 决策: 下一步动作 (analyze_chunk | analyze_dimension | stop)              │   │
│  │  ├── 累积: 执行洞察处理 (MERGE/REPLACE/KEEP/DISCARD)                          │   │
│  │  ├── 综合: 生成最终摘要 (当 should_continue=False)                            │   │
│  │  └── 输出: DirectorOutputWithAccumulation                                     │   │
│  │           ├── accumulated_insights: List[Insight]  # 结构化洞察               │   │
│  │           └── final_summary: str                   # 自然语言摘要             │   │
│  └──────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### 工具调用流程

#### QueryPipeline 工具调用顺序

```
QueryPipeline.execute()
│
├── 1. _execute_step1()
│   └── call_model_with_middleware(step1_prompt)
│       ├── SummarizationMiddleware: 摘要对话历史
│       ├── ModelRetryMiddleware: 失败重试
│       └── OutputValidationMiddleware: 验证输出
│
├── 2. _execute_step2() (如果 Step1 判断需要)
│   └── call_model_with_middleware(step2_prompt)
│       └── (同上)
│
├── 3. _execute_map_fields()
│   └── call_tool_with_middleware(map_fields_tool)
│       ├── ToolRetryMiddleware: 网络错误重试
│       └── 返回: MappedQuery | FieldMappingError
│
├── 4. _execute_build_query()
│   └── build_query(mapped_query)  # 纯逻辑，无中间件
│       └── 返回: QueryRequest | QueryBuildError
│
└── 5. _execute_query()
    └── call_tool_with_middleware(execute_query_tool)
        ├── ToolRetryMiddleware: 网络错误重试
        ├── FilesystemMiddleware: 大结果保存
        │   └── 如果结果 > 阈值，保存到 files，返回 file_reference
        └── 返回: ExecuteResult | ExecutionError
```

#### 工具错误触发 ReAct

```
任意工具返回错误
│
├── FieldMappingError (map_fields)
│   ├── type: "field_not_found"
│   ├── field: "销售额"
│   ├── message: "字段 '销售额' 在数据源中不存在"
│   └── suggestions: ["销售金额", "营业额"]
│
├── QueryBuildError (build_query)
│   ├── type: "invalid_computation"
│   └── message: "不支持的聚合函数: MEDIAN"
│
└── ExecutionError (execute_query)
    ├── type: "timeout"
    └── message: "查询超时，请简化查询条件"
│
▼
ReAct 错误处理
│
├── Thought: 分析错误，决定策略
│   ├── 可修正 → RETRY
│   ├── 需澄清 → CLARIFY
│   └── 无法恢复 → ABORT
│
├── Action: 执行决策
│   ├── RETRY: 修正参数，重新调用工具
│   ├── CLARIFY: 返回澄清问题
│   └── ABORT: 返回错误信息
│
└── Observation: 观察结果 (RETRY 时)
    ├── 成功 → 继续正常流程
    └── 失败 → 回到 Thought (最多 N 次)
```

### 状态流转详解

#### 1. 主工作流状态流转

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              状态流转图                                              │
│                                                                                      │
│  用户输入                                                                            │
│  │                                                                                   │
│  ▼                                                                                   │
│  VizQLState {                                                                        │
│    question: "各省销售额是多少？",                                                   │
│    history: [...],                                                                   │
│    accumulated_insights: [],  # 初始为空                                             │
│  }                                                                                   │
│  │                                                                                   │
│  ▼                                                                                   │
│  SemanticParserAgent                                                                 │
│  │                                                                                   │
│  │  内部状态更新:                                                                    │
│  │  ├── step1_output: {intent: DATA_QUERY, complexity: SIMPLE}                       │
│  │  ├── step2_output: null (SIMPLE 不需要)                                           │
│  │  └── pipeline_result: {success: true, query_result: {...}}                        │
│  │                                                                                   │
│  ▼                                                                                   │
│  VizQLState {                                                                        │
│    ...,                                                                              │
│    query_result: {                                                                   │
│      success: true,                                                                  │
│      data: [...] | file_reference: "files/result_xxx.json"                           │
│    },                                                                                │
│  }                                                                                   │
│  │                                                                                   │
│  ▼                                                                                   │
│  InsightAgent                                                                        │
│  │                                                                                   │
│  │  内部状态更新:                                                                    │
│  │  ├── enhanced_profile: {contributors: [...], trends: [...]}                       │
│  │  ├── chunks: [{chunk_id: 0, ...}, {chunk_id: 1, ...}]                             │
│  │  └── 循环: Analyst → Director → Analyst → Director → ...                          │
│  │                                                                                   │
│  ▼                                                                                   │
│  VizQLState {                                                                        │
│    ...,                                                                              │
│    accumulated_insights: [                                                           │
│      {type: "contributor", title: "广东省贡献最大", ...},                            │
│      {type: "trend", title: "整体呈上升趋势", ...},                                  │
│    ],                                                                                │
│    final_summary: "本次分析发现2个关键洞察：1) 广东省销售额占比45%...",              │
│    enhanced_profile: {...},                                                          │
│  }                                                                                   │
│  │                                                                                   │
│  ▼                                                                                   │
│  ReplannerAgent                                                                      │
│  │                                                                                   │
│  │  评估完成度，决定是否继续                                                         │
│  │  ├── should_replan: false → END                                                   │
│  │  └── should_replan: true → 生成探索问题                                           │
│  │                                                                                   │
│  ▼                                                                                   │
│  (如果 should_replan=true)                                                           │
│  VizQLState {                                                                        │
│    ...,                                                                              │
│    exploration_questions: ["广东省的销售趋势如何？", "哪些产品贡献最大？"],          │
│  }                                                                                   │
│  │                                                                                   │
│  ▼                                                                                   │
│  Send() 动态并行 (如果 N > 1)                                                        │
│  │                                                                                   │
│  ├── Branch 0: SemanticParser(Q1) → Insight → accumulated_insights_0                 │
│  └── Branch 1: SemanticParser(Q2) → Insight → accumulated_insights_1                 │
│  │                                                                                   │
│  ▼                                                                                   │
│  LangGraph 自动合并 (merge_insights reducer)                                         │
│  │                                                                                   │
│  ▼                                                                                   │
│  VizQLState {                                                                        │
│    accumulated_insights: [...原有洞察..., ...Branch0洞察..., ...Branch1洞察...],     │
│  }                                                                                   │
│  │                                                                                   │
│  ▼                                                                                   │
│  ReplannerAgent (再次评估)                                                           │
│                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

#### 2. 错误状态流转

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              错误状态流转                                            │
│                                                                                      │
│  QueryPipeline 执行                                                                  │
│  │                                                                                   │
│  ├── map_fields 返回错误                                                             │
│  │   │                                                                               │
│  │   ▼                                                                               │
│  │   SemanticParserState {                                                           │
│  │     pipeline_result: {                                                            │
│  │       success: false,                                                             │
│  │       error: {                                                                    │
│  │         stage: "map_fields",                                                      │
│  │         type: "field_not_found",                                                  │
│  │         message: "字段 '销售额' 不存在",                                          │
│  │         suggestions: ["销售金额", "营业额"]                                       │
│  │       }                                                                           │
│  │     }                                                                             │
│  │   }                                                                               │
│  │   │                                                                               │
│  │   ▼                                                                               │
│  │   ReAct 错误处理                                                                  │
│  │   │                                                                               │
│  │   ├── Thought: "可以用 suggestions 中的字段重试"                                  │
│  │   ├── Action: RETRY, corrected_params: {field: "销售金额"}                        │
│  │   ├── 重新调用 map_fields                                                         │
│  │   └── Observation: 成功 → 继续 build_query                                        │
│  │                                                                                   │
│  └── 或者: ABORT                                                                     │
│      │                                                                               │
│      ▼                                                                               │
│      VizQLState {                                                                    │
│        query_result: {                                                               │
│          success: false,                                                             │
│          error: {                                                                    │
│            message: "无法找到匹配的字段，请检查字段名称"                             │
│          }                                                                           │
│        }                                                                             │
│      }                                                                               │
│      │                                                                               │
│      ▼                                                                               │
│      route_after_semantic_parser → END (不进入 Insight)                              │
│                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### 中间件执行顺序

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              中间件执行顺序                                          │
│                                                                                      │
│  Agent 开始                                                                          │
│  │                                                                                   │
│  ├── 1. TodoListMiddleware.before_agent()      # 加载待处理任务                      │
│  └── 2. PatchToolCallsMiddleware.before_agent() # 修复历史悬空调用                   │
│  │                                                                                   │
│  ▼                                                                                   │
│  LLM 调用 (Step1/Step2/Analyst/Director)                                             │
│  │                                                                                   │
│  ├── 3. SummarizationMiddleware.wrap_model_call()                                    │
│  │      └── 检查对话历史长度，必要时摘要                                             │
│  ├── 4. ModelRetryMiddleware.wrap_model_call()                                       │
│  │      └── 包装调用，失败时指数退避重试                                             │
│  ├── 5. FilesystemMiddleware.wrap_model_call()                                       │
│  │      └── 注入 files 系统提示                                                      │
│  ├── 6. PatchToolCallsMiddleware.wrap_model_call()                                   │
│  │      └── 修复请求中的悬空工具调用                                                 │
│  │                                                                                   │
│  ├── [实际 LLM 调用]                                                                 │
│  │                                                                                   │
│  └── 7. OutputValidationMiddleware.after_model()                                     │
│         └── 验证 LLM 输出格式                                                        │
│  │                                                                                   │
│  ▼                                                                                   │
│  Tool 调用 (MapFields/ExecuteQuery)                                                  │
│  │                                                                                   │
│  ├── 8. ToolRetryMiddleware.wrap_tool_call()                                         │
│  │      └── 包装调用，网络错误时重试                                                 │
│  ├── 9. FilesystemMiddleware.wrap_tool_call() (仅 ExecuteQuery)                      │
│  │      └── 大结果自动保存到 files                                                   │
│  ├── 10. HumanInTheLoopMiddleware.wrap_tool_call() (可选)                            │
│  │       └── 敏感操作人工确认                                                        │
│  │                                                                                   │
│  └── [实际 Tool 调用]                                                                │
│  │                                                                                   │
│  ▼                                                                                   │
│  Agent 结束                                                                          │
│  │                                                                                   │
│  ├── 11. TodoListMiddleware.after_agent()       # 保存任务状态                       │
│  └── 12. OutputValidationMiddleware.after_agent() # 验证最终状态必需字段             │
│                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

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
| route_after_replanner | should_replan=False | end |
| route_after_replanner | should_replan=True && len(questions) == 1 | semantic_parser (串行) |
| route_after_replanner | should_replan=True && len(questions) > 1 | List[Send] (动态并行) |

---

## State 定义更新

### 移除的字段
- `correction_count`, `correction_exhausted` (不再需要，错误直接返回给用户)
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
| 错误处理 | Observer + SelfCorrection | **ReAct 错误处理 (Thought → Action → Observation)** |
| 工具调用 | 无 | 3 个 Tools (封装现有逻辑) |
| 内部编排 | 无 | Subgraph |
| 洞察分析 | 简单画像 + Synthesizer | Tableau Pulse 对齐 + **总监综合** |
| 代码量 | 多 | 减少 ~30% |
| 并行执行 | 无 | Send() API 动态并行 |

---

## 关键设计决策

| 决策 | 原因 | 影响 |
|------|------|------|
| 使用 Subgraph | LangGraph 原生支持，节点内部可编排 | 复杂逻辑封装 |
| ReAct 替代 Observer | 仅错误时调用 LLM，更高效 | 简化流程，降低成本 |
| ReAct 完整循环 | Thought → Action → Observation，RETRY 后观察结果 | 标准 ReAct 模式 |
| 移除 Synthesizer | 总监 LLM 承担综合功能 | 减少组件，统一职责 |
| Send() API 动态并行 | Replanner 生成的问题数量运行时确定 | 提高效率 |
| Tableau Pulse 对齐 | 专业级数据分析标准 | 洞察质量提升 |
| 维度索引 | 支持精准读取 | 大数据处理效率 |
| 策略推荐 | 自动选择最佳分块策略 | 适应不同数据 |

---

## 并行执行架构

> 详细的 Send() API 使用方式已在"核心架构"部分说明。

### 简化流程图

```
START
  │
  ▼
SemanticParser → Insight (单次执行，处理用户初始问题)
  │
  ▼
Replanner
  │
  ├── 完成 → END
  │
  ├── 单问题 → SemanticParser → Insight (渐进式累积) → Replanner
  │
  └── 多问题 (N>1) → Send() 动态并行
                      │
                      ├── Branch 0: SemanticParser(Q1) → Insight
                      ├── Branch 1: SemanticParser(Q2) → Insight
                      └── Branch N: SemanticParser(QN) → Insight
                      │
                      ▼
                  LangGraph 自动合并 accumulated_insights
                  (使用 merge_insights reducer)
                      │
                      ▼
                  Replanner (接收合并后的洞察)
```

### State 设计（参考 ai-hedge-fund-main）

```python
from typing import Annotated, List, Optional

def merge_insights(existing: List[Insight], new: List[Insight]) -> List[Insight]:
    """
    洞察合并 reducer
    - 并行分支的洞察会自动合并到同一个列表
    - 去重逻辑在 Insight 节点内部由总监 LLM 处理
    """
    return existing + new

class VizQLState(TypedDict):
    # ... 其他字段 ...
    
    # 渐进式累积洞察（使用自定义 reducer）
    accumulated_insights: Annotated[List[Insight], merge_insights]
    
    # 并行执行相关
    parallel_questions: List[str]  # Replanner 生成的多个问题
```

### 工作流定义

```python
def create_workflow():
    graph = StateGraph(VizQLState)
    
    # 主节点
    graph.add_node("semantic_parser", semantic_parser_node)
    graph.add_node("insight", insight_node)  # 包含渐进式累积
    graph.add_node("replanner", replanner_node)
    
    # 边
    graph.add_edge(START, "semantic_parser")
    graph.add_edge("semantic_parser", "insight")
    graph.add_edge("insight", "replanner")
    
    # Replanner 路由（支持并行）
    graph.add_conditional_edges(
        "replanner",
        route_after_replanner,
        {
            "end": END,
            "semantic_parser": "semantic_parser",
            # 多问题并行由 Send() 处理，自动路由到 semantic_parser
        }
    )
    
    return graph.compile()
```

---

## 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| Subgraph 状态传递 | 高 | 明确定义输入输出 Schema |
| 大数据内存溢出 | 高 | FilesystemMiddleware + 索引精准读取 |
| 重规划死循环 | 高 | max_replan_rounds + answered_questions 去重 |
| 并行分支失败 | 中 | 单分支失败不影响其他分支，LangGraph 自动收集结果 |
| 洞察累积 LLM 决策不一致 | 中 | 提供清晰的处理规则，使用结构化输出 |
| 历史洞察处理建议解析失败 | 中 | 提供默认 KEEP 策略，确保不丢失洞察 |
| ReAct 重试死循环 | 中 | max_retries 限制 + ABORT 兜底 |

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
