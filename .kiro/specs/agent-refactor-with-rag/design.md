# 设计文档：Agent 重构与 RAG 集成

## 概述

本设计文档描述了 Tableau Assistant 的 Agent 重构方案，整合现有的 RAG 增强功能和 LangChain/LangGraph 中间件系统。

### 附件文档

| 附件 | 内容 | 说明 |
|------|------|------|
| [prompt-and-schema-design.md](./design-appendix/prompt-and-schema-design.md) | **Prompt 与 Schema 设计规范** | **核心设计规范：思考与填写的交织、XML 标签、决策树** |
| [data-models.md](./design-appendix/data-models.md) | 数据模型定义 | SemanticQuery、VizQLQuery、VizQLState 等（遵循设计规范） |
| [workflow-design.md](./design-appendix/workflow-design.md) | 工作流层设计 | StateGraph、路由逻辑、工厂函数 |
| [agent-design.md](./design-appendix/agent-design.md) | Agent 节点设计 | Boost、Understanding、Replanner 的 Prompt 和逻辑 |
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
│      │       │       例: Understanding Agent, Insight Agent                │ │
│      │       │                                                             │ │
│      │       ├── 代码节点                                                  │ │
│      │       │   └── 纯代码逻辑，不使用 LLM                                │ │
│      │       │       例: Execute Node                                      │ │
│      │       │                                                             │ │
│      │       └── 混合节点                                                  │ │
│      │           └── 代码优先 + LLM fallback                               │ │
│      │               例: QueryBuilder Node                                 │ │
│      │                                                                     │ │
│      ├── 组件 (Component) ────────────────────────────────────────────────┤ │
│      │   └── 不暴露给 LLM 的代码模块，代码直接调用                          │ │
│      │       │                                                             │ │
│      │       ├── 纯代码组件                                                │ │
│      │       │   例: ExpressionGenerator, DateManager                      │ │
│      │       │                                                             │ │
│      │       └── 内部使用 LLM 的组件                                       │ │
│      │           例: FieldMapper (RAG+LLM), AnalysisCoordinator            │ │
│      │           对外暴露代码接口，内部可能调用 LLM                          │ │
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

| 特性 | 组件 (Component) | 工具 (Tool) |
|------|-----------------|-------------|
| 调用方式 | 代码直接调用 | Agent 通过 tool_calls 调用 |
| LLM 可见性 | 不可见 | 可见（在 Agent 的工具列表中） |
| 内部实现 | 可以使用 LLM | 通常是薄封装 |
| 示例 | FieldMapper, AnalysisCoordinator | get_metadata, parse_date |

**关键设计决策**：
- **组件可以内部使用 LLM**，但对外暴露代码接口
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
│   │   ├── boost/
│   │   │   ├── node.py                # boost_node() 函数
│   │   │   └── prompt.py              # Boost Prompt 模板
│   │   │
│   │   ├── understanding/
│   │   │   ├── node.py                # understanding_node() 函数
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
│   ├── nodes/                         # 非 LLM 节点
│   │   ├── query_builder/
│   │   │   └── node.py                # query_builder_node() 函数
│   │   │
│   │   └── execute/
│   │       └── node.py                # execute_node() 函数
│   │
│   ├── tools/                         # 工具层 (给 Agent 调用)
│   │   ├── registry.py                # ToolRegistry 工具注册表
│   │   ├── metadata_tool.py           # @tool get_metadata()
│   │   ├── date_tool.py               # @tool parse_date(), detect_date_format()
│   │   ├── rag_tool.py                # @tool semantic_map_fields()
│   │   └── schema_tool.py             # @tool get_schema_module()
│   │
│   ├── components/                    # 组件层 (代码直接调用)
│   │   ├── field_mapper/
│   │   │   ├── mapper.py              # FieldMapper 类
│   │   │   └── cache.py               # 缓存逻辑
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
│  │  │ Agent 节点   │  │ 代码节点    │  │ 混合节点    │                  │    │
│  │  │ (LLM)       │  │ (非 LLM)    │  │ (代码+LLM)  │                  │    │
│  │  │             │  │             │  │             │                  │    │
│  │  │ Boost       │  │ Execute     │  │ QueryBuilder│                  │    │
│  │  │ Understanding│  │             │  │             │                  │    │
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
│  │  │ @tool get_metadata  │    │  │ FieldMapper         │              │    │
│  │  │ @tool parse_date    │    │  │ ImplementationResolver│            │    │
│  │  │ @tool write_todos   │    │  │ ExpressionGenerator │              │    │
│  │  │ ...                 │    │  │ AnalysisCoordinator │              │    │
│  │  └─────────────────────┘    │  └─────────────────────┘              │    │
│  │  LLM 决定调用               │  代码直接调用                          │    │
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
│ [Boost Agent] - LLM 节点                                                     │
│                                                                              │
│   LLM 思考: "我需要知道有哪些字段..."                                        │
│   LLM 调用工具: get_metadata()                                               │
│        │                                                                     │
│        ▼                                                                     │
│   @tool get_metadata() ──委托──→ MetadataManager.get_metadata_async()       │
│        │                                                                     │
│        ▼                                                                     │
│   输出: boosted_question (增强后的问题)                                      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ [Understanding Agent] - LLM 节点                                             │
│                                                                              │
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
│   输出: SemanticQuery {                                                      │
│       measures: [{name: "销售额", aggregation: "sum"}],                      │
│       dimensions: [{name: "省份"}, {name: "日期", time_granularity: "month"}],│
│       analyses: [{type: "cumulative", target_measure: "销售额",              │
│                   computation_scope: "per_group"}]                           │
│   }                                                                          │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ [QueryBuilder Node] - 混合节点 (代码优先 + LLM fallback)                     │
│                                                                              │
│   代码直接调用组件 (不是工具！):                                             │
│                                                                              │
│   1. FieldMapper.map(["销售额", "省份", "日期"])                             │
│      │                                                                       │
│      ├─ RAG 检索: SemanticMapper.search()                                   │
│      ├─ 置信度 > 0.9? → 直接返回                                            │
│      └─ 置信度 < 0.9? → LLM 判断 (fallback)                                 │
│      │                                                                       │
│      ▼                                                                       │
│      映射结果: {销售额 → Sales, 省份 → Province, 日期 → Order_Date}         │
│                                                                              │
│   2. ImplementationResolver.resolve(analyses, context)                       │
│      │                                                                       │
│      ├─ 多维度 + cumulative + per_group                                     │
│      ├─ 代码规则: addressing = [Order_Date]                                 │
│      └─ 输出: 使用表计算，addressing = [Order_Date]                         │
│                                                                              │
│   3. ExpressionGenerator.generate(...)                                       │
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
