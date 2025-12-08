# 设计文档：Agent 重构与 RAG 集成

## 概述

本设计文档描述了 Tableau Assistant 的 Agent 重构方案，整合现有的 RAG 增强功能和 LangChain/LangGraph 中间件系统。

### 附件文档

| 附件 | 内容 | 说明 |
|------|------|------|
| [prompt-and-schema-design.md](./design-appendix/prompt-and-schema-design.md) | **Prompt 与 Schema 设计规范** | **核心设计规范：思考与填写的交织、XML 标签、决策树** |
| [data-models.md](./design-appendix/data-models.md) | 数据模型定义 | SemanticQuery、VizQLQuery、VizQLState 等（遵循设计规范） |
| [workflow-design.md](./design-appendix/workflow-design.md) | 工作流层设计 | StateGraph、路由逻辑、工厂函数 |
| [agent-design.md](./design-appendix/agent-design.md) | Agent 节点设计 | Understanding（含原 Boost）、Insight、Replanner 的 Prompt 和逻辑 |
| [node-design.md](./design-appendix/node-design.md) | 非 LLM 节点设计 | QueryBuilder、Execute 节点 |
| [tool-design.md](./design-appendix/tool-design.md) | 工具层设计 | get_metadata、parse_date、get_schema_module 等 |
| [component-design.md](./design-appendix/component-design.md) | 组件层设计 | FieldMapper、ImplementationResolver、ExpressionGenerator |
| [insight-design.md](./design-appendix/insight-design.md) | 洞察系统设计 | Insight Agent + AnalysisCoordinator 完整设计 |
| [middleware-design.md](./design-appendix/middleware-design.md) | 中间件层设计 | FilesystemMiddleware、PatchToolCallsMiddleware |
| [frontend-ui-design.md](./design-appendix/frontend-ui-design.md) | 前端 UI 设计 | Tableau Extension 插件风格的前端设计方案 |

### 参考文档

| 文档 | 路径 | 说明 |
|------|------|------|
| Prompt 和数据模型编写指南 | `tableau_assistant/docs/PROMPT_AND_MODEL_GUIDE.md` | 编写规范 |
| VizQL Data Service API | `openapi.json` | API 规范 |

---

## 设计原则

1. **利用现有框架**：直接使用 LangChain 提供的中间件，不重复造轮子
2. **自主实现关键功能**：FilesystemMiddleware 和 PatchToolCallsMiddleware 由我们自主实现
3. **薄封装策略**：工具层是对现有组件（MetadataManager、DateManager、SemanticMapper）的薄封装
4. **保持 StateGraph 架构**：使用 LangGraph StateGraph 进行工作流编排
5. **职责分离**：渐进式洞察（处理 DataFrame）与 SummarizationMiddleware（处理 Messages）分离
6. **纯语义中间层**：LLM 只做语义理解，所有 VizQL 技术转换由确定性代码完成
7. **思考与填写交织**：LLM 是逐 token 生成的，每填一个字段都是一次"微型思考"，XML 标签为每次微型思考提供精确的规则定位锚点
8. **`<decision_rule>` 桥梁**：Schema 中的 `<decision_rule>` 将 Prompt 中的抽象思考转化为具体填写动作

---

## ⚠️ 生产级别要求

**所有功能实现必须满足以下生产级别要求：**

| 要求 | 说明 |
|------|------|
| **完整实现** | 所有功能必须是完整的，不能简化，不能省略边界条件处理 |
| **真实环境测试** | 测试必须在真实环境进行，不能使用 mock 数据 |
| **配置驱动** | 所有外部依赖（LLM、Tableau API）的配置信息已在 `.env` 文件中配置 |
| **测试完整性** | 测试问题必须完整解决，不能跳过测试，不能忽略失败的测试 |
| **错误处理** | 所有代码必须有完整的错误处理和日志记录 |
| **代码质量** | 代码必须符合生产标准，包括类型注解、文档字符串、合理的抽象 |

**测试环境配置**：
```
# .env 文件中已配置的关键参数
LLM_API_BASE=...          # LLM API 地址
LLM_API_KEY=...           # LLM API 密钥
LLM_MODEL_PROVIDER=...    # LLM 提供商
TOOLING_LLM_MODEL=...     # 工具调用使用的模型

TABLEAU_SERVER_URL=...    # Tableau Server 地址
TABLEAU_SITE_ID=...       # Tableau Site ID
VDS_BASE_URL=...          # VizQL Data Service 地址
```

**禁止事项**：
- ❌ 不能使用 mock 数据进行测试
- ❌ 不能简化功能实现
- ❌ 不能跳过失败的测试
- ❌ 不能省略错误处理
- ❌ 不能硬编码配置信息

---

## 核心概念关系

### 概念层级图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           概念层级关系                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  工作流 (Workflow)                                                           │
│  └── 整个执行流程的编排，使用 LangGraph StateGraph                           │
│      │                                                                       │
│      ├── 节点 (Node) ─────────────────────────────────────────────────────┐ │
│      │   └── 工作流中的执行单元                                            │ │
│      │       │                                                             │ │
│      │       ├── LLM 节点 (Agent)                                          │ │
│      │       │   └── 使用 LLM 的节点，可以调用工具                          │ │
│      │       │       例: Understanding Agent（含原 Boost 功能）, Insight    │ │
│      │       │                                                             │ │
│      │       ├── 代码节点                                                  │ │
│      │       │   └── 纯代码逻辑，不使用 LLM                                │ │
│      │       │       例: QueryBuilder Node, Execute Node                   │ │
│      │       │                                                             │ │
│      │       └── RAG + LLM 混合节点                                        │ │
│      │           └── RAG 检索优先，低置信度时 LLM fallback                 │ │
│      │               例: FieldMapper Node                                  │ │
│      │                                                                     │ │
│      ├── 组件 (Component) ────────────────────────────────────────────────┤ │
│      │   └── 不暴露给 LLM 的代码模块，代码直接调用                          │ │
│      │       │                                                             │ │
│      │       ├── 纯代码组件                                                │ │
│      │       │   例: ExpressionGenerator, DateManager                      │ │
│      │       │                                                             │ │
│      │       └── 内部使用 LLM 的组件                                       │ │
│      │           例: AnalysisCoordinator                                   │ │
│      │           对外暴露代码接口，内部可能调用 LLM                          │ │
│      │           注: FieldMapper 已提升为独立节点，不再是组件               │ │
│      │                                                                     │ │
│      ├── 工具 (Tool) ─────────────────────────────────────────────────────┤ │
│      │   └── Agent 可以显式调用的功能单元，有 @tool 装饰器                  │ │
│      │       │                                                             │ │
│      │       ├── 业务工具（我们实现）                                      │ │
│      │       │   例: get_metadata, get_schema_module, parse_date           │ │
│      │       │                                                             │ │
│      │       └── 中间件提供的工具                                          │ │
│      │           例: write_todos (TodoListMiddleware)                      │ │
│      │                read_file (FilesystemMiddleware)                     │ │
│      │                                                                     │ │
│      └── 中间件 (Middleware) ─────────────────────────────────────────────┤ │
│          └── 全局能力增强，自动生效                                         │ │
│              │                                                             │ │
│              ├── 提供工具的中间件                                          │ │
│              │   例: TodoListMiddleware → write_todos                      │ │
│              │                                                             │ │
│              └── 自动触发的中间件                                          │ │
│                  例: SummarizationMiddleware (token 超限时自动总结)        │ │
│                       ModelRetryMiddleware (LLM 调用失败自动重试)          │ │
│                                                                            │ │
└────────────────────────────────────────────────────────────────────────────┘ │
                                                                               │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 组件 vs 工具 的区别

| 特性 | 组件 (Component) | 工具 (Tool) | RAG+LLM 混合节点 |
|------|-----------------|-------------|------------------|
| 调用方式 | 代码直接调用 | Agent 通过 tool_calls 调用 | 工作流自动调用 |
| LLM 可见性 | 不可见 | 可见（在 Agent 的工具列表中） | 不可见（独立节点） |
| 内部实现 | 可以使用 LLM | 通常是薄封装 | RAG 优先 + LLM fallback |
| 示例 | AnalysisCoordinator, ExpressionGenerator | get_metadata, parse_date | FieldMapper Node |

**关键设计决策**：
- **FieldMapper 提升为独立节点**：从 QueryBuilder 内部组件提升为工作流节点，清晰分离职责
- **RAG + LLM 混合模式**：置信度 >= 0.9 时直接返回（快速路径），< 0.9 时使用 LLM fallback
- **洞察系统封装为组件**（AnalysisCoordinator），而不是暴露为工具
- 好处：流程由代码控制，更可靠；LLM 只负责"思考"，不负责"决策流程"

---

## 完整项目结构

```
tableau_assistant/
├── src/
│   │
│   ├── workflow/                      # 工作流层
│   │   ├── factory.py                 # create_tableau_workflow() 工厂函数
│   │   ├── state.py                   # VizQLState 状态定义
│   │   └── routes.py                  # 路由逻辑 (route_after_replanner)
│   │
│   ├── agents/                        # Agent 层 (LLM 节点)
│   │   │   # 注: Boost Agent 已移除，功能合并到 Understanding Agent
│   │   │
│   │   ├── understanding/
│   │   │   ├── node.py                # understanding_node() 函数（含原 Boost 功能）
│   │   │   └── prompt.py              # Understanding Prompt 模板
│   │   │
│   │   ├── insight/
│   │   │   ├── node.py                # insight_node() 函数
│   │   │   └── prompt.py              # Insight Prompt 模板
│   │   │
│   │   └── replanner/
│   │       ├── node.py                # replanner_node() 函数
│   │       └── prompt.py              # Replanner Prompt 模板
│   │
│   ├── nodes/                         # 非 LLM Agent 节点
│   │   ├── field_mapper/              # RAG + LLM 混合节点
│   │   │   ├── node.py                # field_mapper_node() 函数
│   │   │   └── llm_selector.py        # LLM 候选选择逻辑
│   │   │
│   │   ├── query_builder/             # 纯代码节点
│   │   │   └── node.py                # query_builder_node() 函数
│   │   │
│   │   └── execute/                   # 纯代码节点
│   │       └── node.py                # execute_node() 函数
│   │
│   ├── tools/                         # 工具层 (给 Agent 调用)
│   │   ├── registry.py                # ToolRegistry 工具注册表
│   │   ├── metadata_tool.py           # @tool get_metadata()
│   │   ├── date_tool.py               # @tool parse_date(), detect_date_format()
│   │   └── schema_tool.py             # @tool get_schema_module()
│   │   # 注: semantic_map_fields 已移除，FieldMapper 作为独立节点
│   │
│   ├── components/                    # 组件层 (代码直接调用)
│   │   │   # 注: FieldMapper 已提升为独立节点，见 nodes/field_mapper/
│   │   │
│   │   ├── implementation_resolver/
│   │   │   └── resolver.py            # ImplementationResolver 类
│   │   │
│   │   ├── expression_generator/
│   │   │   ├── generator.py           # ExpressionGenerator 类
│   │   │   └── templates.py           # 表达式模板
│   │   │
│   │   └── insight/
│   │       ├── coordinator.py         # AnalysisCoordinator 类
│   │       ├── profiler.py            # DataProfiler 类
│   │       ├── anomaly_detector.py    # AnomalyDetector 类
│   │       ├── chunker.py             # SemanticChunker 类
│   │       ├── analyzer.py            # ChunkAnalyzer 类
│   │       ├── accumulator.py         # InsightAccumulator 类
│   │       └── synthesizer.py         # InsightSynthesizer 类
│   │
│   ├── middleware/                    # 中间件层 (自动生效)
│   │   ├── filesystem.py              # FilesystemMiddleware (自主实现)
│   │   └── patch_tool_calls.py        # PatchToolCallsMiddleware (自主实现)
│   │   # LangChain 内置中间件直接 import 使用
│   │
│   ├── capabilities/                  # 现有能力层 (已实现)
│   │   ├── metadata/
│   │   │   └── manager.py             # MetadataManager (已实现)
│   │   │
│   │   ├── date_processing/
│   │   │   └── manager.py             # DateManager (已实现)
│   │   │
│   │   ├── rag/
│   │   │   ├── semantic_mapper.py     # SemanticMapper (已实现)
│   │   │   ├── field_indexer.py       # FieldIndexer (已实现)
│   │   │   └── reranker.py            # Reranker (已实现)
│   │   │
│   │   └── query/
│   │       └── builder.py             # QueryBuilder (需完善)
│   │
│   ├── models/                        # 数据模型层
│   │   ├── semantic/
│   │   │   ├── query.py               # SemanticQuery, AnalysisSpec
│   │   │   └── enums.py               # AnalysisType, ComputationScope
│   │   │
│   │   ├── vizql/
│   │   │   ├── query.py               # VizQLQuery
│   │   │   └── result.py              # QueryResult
│   │   │
│   │   └── errors.py                  # TransientError, PermanentError, UserError
│   │
│   ├── config/                        # 配置层
│   │   └── manager.py                 # ConfigManager
│   │
│   └── observability/                 # 可观测性层
│       └── logger.py                  # 日志记录
│
└── tests/
    ├── unit/
    │   ├── tools/
    │   ├── components/
    │   └── middleware/
    │
    └── property/                      # Property-Based Tests
        ├── test_workflow.py
        ├── test_field_mapper.py
        └── test_expression_generator.py
```

---

## 层级关系图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              层级关系                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  工作流层 (Workflow)                                                 │    │
│  │  create_tableau_workflow() → StateGraph                             │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                              │                                               │
│                              │ 编排                                          │
│                              ▼                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  节点层 (Nodes)                                                      │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                  │    │
│  │  │ Agent 节点   │  │ 代码节点    │  │ RAG+LLM 节点│                  │    │
│  │  │ (LLM)       │  │ (非 LLM)    │  │ (混合)      │                  │    │
│  │  │             │  │             │  │             │                  │    │
│  │  │ Understanding│  │ QueryBuilder│  │ FieldMapper │                  │    │
│  │  │ (含Boost)   │  │ Execute     │  │             │                  │    │
│  │  │ Insight     │  │             │  │             │                  │    │
│  │  │ Replanner   │  │             │  │             │                  │    │
│  │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘                  │    │
│  └─────────┼────────────────┼────────────────┼─────────────────────────┘    │
│            │                │                │                               │
│            │ 调用           │ 调用           │ 调用                          │
│            ▼                ▼                ▼                               │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  工具层 (Tools)              │  组件层 (Components)                  │    │
│  │  ┌─────────────────────┐    │  ┌─────────────────────┐              │    │
│  │  │ @tool get_metadata  │    │  │ ImplementationResolver│            │    │
│  │  │ @tool parse_date    │    │  │ ExpressionGenerator │              │    │
│  │  │ @tool write_todos   │    │  │ AnalysisCoordinator │              │    │
│  │  │ ...                 │    │  │ SemanticMapper      │              │    │
│  │  └─────────────────────┘    │  └─────────────────────┘              │    │
│  │  LLM 决定调用               │  代码/节点直接调用                      │    │
│  │                             │  (FieldMapper Node 调用 SemanticMapper)│    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                              │                                               │
│                              │ 委托                                          │
│                              ▼                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  能力层 (Capabilities) - 已实现的核心功能                            │    │
│  │  ┌─────────────────────────────────────────────────────────────┐    │    │
│  │  │ MetadataManager │ DateManager │ SemanticMapper │ QueryBuilder│    │    │
│  │  └─────────────────────────────────────────────────────────────┘    │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  中间件层 (Middleware) - 全局增强，自动生效                          │    │
│  │  ┌─────────────────────────────────────────────────────────────┐    │    │
│  │  │ ModelRetry │ ToolRetry │ Filesystem │ Summarization │ ...   │    │    │
│  │  └─────────────────────────────────────────────────────────────┘    │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 数据流转示例

```
用户问题: "2024年各省份销售额按月趋势，显示累计总额"
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ [Understanding Agent] - LLM 节点（合并原 Boost 功能）                        │
│                                                                              │
│   Step 1: 获取元数据（原 Boost 功能）                                        │
│   LLM 思考: "我需要知道有哪些字段..."                                        │
│   LLM 调用工具: get_metadata()                                               │
│        │                                                                     │
│        ▼                                                                     │
│   @tool get_metadata() ──委托──→ MetadataManager.get_metadata_async()       │
│                                                                              │
│   Step 2: 问题分类（原 Boost 功能）                                          │
│   LLM 思考: "这是一个数据分析问题，需要查询销售额趋势..."                    │
│   输出: is_analysis_question = True                                          │
│                                                                              │
│   Step 3: 语义理解                                                           │
│   LLM 思考: "问题中有'2024年'，我需要解析日期..."                            │
│   LLM 调用工具: parse_date("2024年")                                         │
│        │                                                                     │
│        ▼                                                                     │
│   @tool parse_date() ──委托──→ DateManager.parse_time_range()               │
│        │                                                                     │
│        ▼                                                                     │
│   LLM 思考: "问题中有'累计'，我需要填写 AnalysisSpec..."                     │
│   LLM 调用工具: get_schema_module("analysis")                                │
│        │                                                                     │
│        ▼                                                                     │
│   输出到 VizQLState:                                                         │
│   - is_analysis_question: true  (路由决策字段)                               │
│   - semantic_query: SemanticQuery {                                          │
│       measures: [{name: "销售额", aggregation: "sum"}],                      │
│       dimensions: [{name: "省份"}, {name: "日期", time_granularity: "month"}],│
│       analyses: [{type: "cumulative", target_measure: "销售额",              │
│                   computation_scope: "per_group"}]                           │
│     }                                                                        │
│                                                                              │
│   ⚠️ 如果 is_analysis_question=False，直接路由到 END 返回友好提示           │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ [FieldMapper Node] - RAG + LLM 混合节点（独立节点）                          │
│                                                                              │
│   输入: SemanticQuery（业务术语：销售额、省份、日期）                         │
│                                                                              │
│   1. RAG 检索: SemanticMapper.search("销售额")                               │
│      │                                                                       │
│      ├─ 置信度 = 0.95 (>= 0.9) → 直接返回 Sales（快速路径，无需 LLM）       │
│      │                                                                       │
│   2. RAG 检索: SemanticMapper.search("省份")                                 │
│      │                                                                       │
│      ├─ 置信度 = 0.85 (< 0.9) → 需要 LLM 判断                               │
│      ├─ 候选: [Province(0.85), Region(0.72), City(0.65)]                    │
│      └─ LLM 判断: "省份" 最匹配 Province → 返回 Province                    │
│      │                                                                       │
│   3. RAG 检索: SemanticMapper.search("日期")                                 │
│      │                                                                       │
│      └─ 置信度 = 0.92 (>= 0.9) → 直接返回 Order_Date                        │
│                                                                              │
│   输出: MappedQuery {                                                        │
│       field_mappings: {销售额 → Sales, 省份 → Province, 日期 → Order_Date}, │
│       confidence_scores: {Sales: 0.95, Province: 0.85, Order_Date: 0.92}    │
│   }                                                                          │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ [QueryBuilder Node] - 纯代码节点（无 LLM）                                   │
│                                                                              │
│   输入: MappedQuery（技术字段已确定）                                        │
│                                                                              │
│   1. ImplementationResolver.resolve(analyses, context)                       │
│      │                                                                       │
│      ├─ 多维度 + cumulative + per_group                                     │
│      ├─ 代码规则: addressing = [Order_Date]                                 │
│      └─ 输出: 使用表计算，addressing = [Order_Date]                         │
│                                                                              │
│   2. ExpressionGenerator.generate(...)                                       │
│      │                                                                       │
│      └─ 代码模板: RUNNING_SUM(SUM([Sales]))                                 │
│                                                                              │
│   输出: VizQLQuery {                                                         │
│       dimensions: [Province, Order_Date],                                    │
│       measures: [Sales],                                                     │
│       tableCalcFields: [{                                                    │
│           calculation: "RUNNING_SUM(SUM([Sales]))",                          │
│           addressing: ["Order_Date"]                                         │
│       }]                                                                     │
│   }                                                                          │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ [Execute Node] - 代码节点 (非 LLM)                                           │
│                                                                              │
│   代码直接执行:                                                              │
│   result = vizql_api.query(vizql_query)                                      │
│                                                                              │
│   输出: QueryResult { data: [...], row_count: 156, execution_time: 1.2s }   │
│                                                                              │
│   ⚠️ 如果结果太大 (>20000 tokens):                                          │
│      FilesystemMiddleware 自动介入，保存到文件                               │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ [Insight Agent] - LLM 节点                                                   │
│                                                                              │
│   代码直接调用组件 (不是工具！):                                             │
│                                                                              │
│   AnalysisCoordinator.analyze(data, context)                                 │
│      │                                                                       │
│      ├─ DataProfiler.profile() → 数据画像                                   │
│      ├─ AnomalyDetector.detect() → 异常检测                                 │
│      ├─ 选择策略: progressive (100-1000 行)                                 │
│      ├─ SemanticChunker.chunk() → 按省份分块                                │
│      ├─ ChunkAnalyzer.analyze() → 分析每个块 (调用 LLM)                     │
│      ├─ InsightAccumulator.accumulate() → 累积洞察                          │
│      └─ InsightSynthesizer.synthesize() → 合成最终洞察                      │
│                                                                              │
│   输出: accumulated_insights                                                 │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ [Replanner Agent] - LLM 节点                                                 │
│                                                                              │
│   LLM 思考: "分析是否完整？是否需要继续探索？"                               │
│   LLM 调用工具: write_todos([...]) (来自 TodoListMiddleware)                │
│                                                                              │
│   输出: ReplanDecision { should_replan: true/false, next_questions: [...] } │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### 工作流层属性

**Property 1: 中间件配置完整性**
*For any* 工厂函数配置，创建的工作流应包含所有 7 个必需的中间件类型（TodoListMiddleware、SummarizationMiddleware、ModelRetryMiddleware、ToolRetryMiddleware、FilesystemMiddleware、PatchToolCallsMiddleware，以及可选的 HumanInTheLoopMiddleware）
**Validates: Requirements 1.1, 1.2**

**Property 2: 工作流节点顺序保持**
*For any* 工作流执行，节点执行顺序应始终为：Understanding → FieldMapper → QueryBuilder → Execute → Insight → Replanner（除非条件跳过）
**Validates: Requirements 2.2**

**Property 3: 非分析类问题路由**
*For any* Understanding 输出中 is_analysis_question=False，工作流应直接路由到 END 并返回友好提示
**Validates: Requirements 2.3**

**Property 4: 智能重规划路由正确性**
*For any* Replanner 输出，当 should_replan=True 且 replan_count < max 时应路由到 Understanding，否则应路由到 END
**Validates: Requirements 2.4, 2.5, 17.4, 17.5, 17.7**

**Property 5: 状态累积保持**
*For any* 状态转换，累积数据（insights、results、errors）应在转换后保持不变或正确追加
**Validates: Requirements 2.6, 18.2**

**Property 5.1: Understanding Agent 元数据获取**
*For any* Understanding Agent 执行，应调用 get_metadata 工具获取字段信息（原 Boost 功能）
**Validates: Requirements 2.9**

### 工具层属性

**Property 6: 工具输入验证**
*For any* 工具调用，无效输入应被 Pydantic 验证拒绝并返回结构化错误响应
**Validates: Requirements 3.2, 3.3**

**Property 7: 大输出文件转存**
*For any* 工具输出超过 20000 tokens，FilesystemMiddleware 应自动保存到文件并返回文件引用
**Validates: Requirements 3.5, 12.1**

### RAG 语义映射属性

**Property 8: FieldMapper 高置信度快速路径**
*For any* 字段映射请求，当 RAG 检索 top-1 置信度 >= 0.9 时，FieldMapper Node 应跳过 LLM 判断直接返回结果
**Validates: Requirements 4.3, 7.2.6**

**Property 9: FieldMapper 低置信度 LLM Fallback**
*For any* 字段映射请求，当置信度 < 0.9 时，FieldMapper Node 应使用 LLM 从 top-k 候选中选择最佳匹配
**Validates: Requirements 4.4, 4.5**

**Property 10: 字段映射缓存一致性**
*For any* 相同的字段映射请求，在 TTL（1 小时）内第二次调用应命中缓存并返回相同结果
**Validates: Requirements 4.6**

**Property 11: 维度层级 RAG 增强**
*For any* 维度层级推断请求，当存在相似度 > 0.8 的历史模式时，应将 top-3 模式作为 few-shot 示例
**Validates: Requirements 4.1.1, 4.1.2**

### 元数据和日期工具属性

**Property 12: 元数据工具委托**
*For any* get_metadata 工具调用，应正确委托给 MetadataManager 并返回 LLM 友好格式的字段列表
**Validates: Requirements 5.1, 5.3**

**Property 13: 日期解析往返一致性**
*For any* 有效的日期表达式（相对或绝对），parse_date 应返回正确的 start_date 和 end_date（YYYY-MM-DD 格式）
**Validates: Requirements 6.2, 6.3**

### 查询构建属性

**Property 14: 查询构建正确性**
*For any* 有效的 SemanticQuery，QueryBuilder 应生成语法正确的 VizQLQuery（包含正确的 TableCalcField 或 CalculatedField）
**Validates: Requirements 7.1**

### 渐进式洞察属性

**Property 15: 渐进式分析策略选择**
*For any* 数据集，AnalysisCoordinator 应根据行数选择正确策略：<100 行 → direct，100-1000 行 → progressive，>1000 行 → hybrid
**Validates: Requirements 8.2**

**Property 16: 洞察累积去重**
*For any* 洞察累积过程，InsightAccumulator 应检测并去除重复洞察，保持唯一性
**Validates: Requirements 8.5**

### 中间件属性

**Property 17: LLM 重试指数退避**
*For any* LLM 调用失败重试，重试间隔应符合指数退避策略（1s、2s、4s）
**Validates: Requirements 9.2**

**Property 18: 对话总结职责分离**
*For any* 对话总结触发，SummarizationMiddleware 应只总结对话消息，不影响 VizQLState.insights
**Validates: Requirements 11.5**

**Property 19: 悬空工具调用修复**
*For any* AIMessage 有 tool_calls 但缺少对应 ToolMessages，PatchToolCallsMiddleware 应自动补充取消 ToolMessages
**Validates: Requirements 13.1**

### 错误处理属性

**Property 20: 错误分类正确性**
*For any* 错误发生，Error_Handler 应正确分类为 TransientError（可重试）、PermanentError（不可重试）或 UserError（需用户修正）
**Validates: Requirements 21.1**

### 纯语义中间层属性

**Property 21: ImplementationResolver LOD 判断**
*For any* AnalysisSpec，当 requires_external_dimension=true 或 target_granularity 与视图维度不同时，应选择 LOD 实现
**Validates: Requirements 7.2.8, 7.2.9**

**Property 22: ExpressionGenerator 表达式语法正确性**
*For any* 表达式生成请求，生成的 VizQL 表达式应 100% 语法正确（括号匹配、函数名正确）
**Validates: Requirements 7.2.14**

**Property 23: SemanticQuery computation_scope 条件填写**
*For any* SemanticQuery，当 dimensions.length <= 1 时，analyses 中的 computation_scope 应为 null；当 dimensions.length > 1 时，应根据问题语义设置 per_group 或 across_all
**Validates: Requirements 7.2.3, 7.2.11**

### Schema 模块工具属性

**Property 24: Schema 模块按需加载**
*For any* get_schema_module 调用，应只返回请求的模块内容，不返回未请求的模块
**Validates: tool-design.md Schema 模块选择工具**

**Property 25: Schema 模块名称验证**
*For any* get_schema_module 调用，无效的模块名称应返回错误消息和可用模块列表
**Validates: tool-design.md Schema 模块选择工具**
