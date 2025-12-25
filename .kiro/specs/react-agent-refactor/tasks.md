# ReAct Agent 重构任务清单 v2.0

## 概述

本任务清单基于 `design.md` v2.0 设计文档，将当前 7 节点 StateGraph 重构为基于 LangGraph Subgraph 的层级 Agent 架构。

**目标架构**:
- 3 Agent 节点: SemanticParserAgent (Subgraph), InsightAgent (Subgraph), ReplannerAgent (单节点)
- 3 Tools: map_fields, build_query, execute_query
- 2 路由函数: route_after_semantic_parser, route_after_replanner

**技术栈**:
- langgraph 1.0.5 (Subgraph 支持)
- langchain 1.1.3 (LLM 抽象层)
- MiddlewareRunner (自定义 middleware 执行器)

**重要决策**：
- 不使用 `create_react_agent` (langgraph-prebuilt)，因为它不支持 middleware 和 token 流式输出
- 使用自定义 StateGraph + MiddlewareRunner 实现固定 QueryPipeline 流程
- 错误直接返回给用户，不做重试循环（字段映射失败等是数据问题，重试无意义）

**规范遵循**: 所有 Prompt 和数据模型遵循 `PROMPT_AND_MODEL_GUIDE.md`

---

## Phase 1: Tool 基础设施与数据模型

### Task 1.1: 创建 Tool 基础设施
**文件**: `orchestration/tools/__init__.py`, `base.py`, `registry.py`

- [ ] 创建 `orchestration/tools/` 目录结构
- [ ] 创建 `base.py`:
  - 定义 `BaseTool` 抽象基类
  - 定义 `ToolResult` 通用返回类型
- [ ] 创建 `registry.py`:
  - 实现 Tool 注册机制 (`@register_tool` 装饰器)
  - 实现 `get_tools()` 获取所有注册工具
- [ ] 更新 `__init__.py` 导出所有工具

**验收标准**: 
- `BaseTool` 包含 `name`, `description`, `input_schema`, `run()` 方法
- `ToolResult` 包含 `success`, `data`, `error` 字段
- 注册机制正常工作

---

### Task 1.2: 实现 map_fields Tool 包
**文件**: `orchestration/tools/map_fields/__init__.py`, `tool.py`, `models.py`

- [ ] 创建 `orchestration/tools/map_fields/` 包目录
- [ ] 创建 `models.py`:
  - `MapFieldsInput` 模型
  - `MapFieldsOutput` 模型
  - `FieldMappingError` 模型 (type: field_not_found | ambiguous_field)
- [ ] 创建 `tool.py`:
  - 从 `agents/field_mapper/` 提取核心映射逻辑
  - 使用 `@tool` 装饰器定义 LangChain Tool
  - 实现 RAG + LLM 混合映射逻辑
  - 返回结构化错误
- [ ] 更新 `__init__.py` 导出 Tool 和模型

**依赖**: Task 1.1

**验收标准**:
- 数据模型通过 Pydantic 验证
- 正常映射返回 `MappedQuery`
- 字段未找到返回 `FieldMappingError` with suggestions
- 单元测试覆盖正常/错误场景

---

### Task 1.3: 实现 build_query Tool 包
**文件**: `orchestration/tools/build_query/__init__.py`, `tool.py`, `models.py`

- [ ] 创建 `orchestration/tools/build_query/` 包目录
- [ ] 创建 `models.py`:
  - `BuildQueryInput` 模型
  - `BuildQueryOutput` 模型
  - `QueryBuildError` 模型 (type: invalid_computation | unsupported_operation)
- [ ] 创建 `tool.py`:
  - 从 `nodes/query_builder/` 提取核心构建逻辑
  - 使用 `@tool` 装饰器定义 LangChain Tool
  - 保留现有 QueryBuilder 的计算转换逻辑
  - 返回结构化错误
- [ ] 更新 `__init__.py` 导出 Tool 和模型

**依赖**: Task 1.1

**验收标准**:
- 数据模型通过 Pydantic 验证
- 正常构建返回 `QueryRequest`
- 无效计算返回 `QueryBuildError`
- 单元测试覆盖正常/错误场景

---

### Task 1.4: 实现 execute_query Tool 包
**文件**: `orchestration/tools/execute_query/__init__.py`, `tool.py`, `models.py`

- [ ] 创建 `orchestration/tools/execute_query/` 包目录
- [ ] 创建 `models.py`:
  - `ExecuteQueryInput` 模型
  - `ExecuteQueryOutput` 模型
  - `ExecutionError` 模型 (type: execution_failed | timeout | auth_error | invalid_query)
- [ ] 创建 `tool.py`:
  - 从 `nodes/execute/` 提取核心执行逻辑
  - 使用 `@tool` 装饰器定义 LangChain Tool
  - 保留现有 VizQL API 调用逻辑
  - 集成 FilesystemMiddleware 大结果处理
  - 返回结构化错误
- [ ] 更新 `__init__.py` 导出 Tool 和模型

**依赖**: Task 1.1

**验收标准**:
- 数据模型通过 Pydantic 验证
- 正常执行返回 `ExecuteResult`
- 大结果自动保存到 files
- 各类错误返回对应 `ExecutionError`
- 单元测试覆盖正常/错误场景

---

## Phase 2: SemanticParser Subgraph 实现

### Task 2.1: 创建 SemanticParser models 包
**文件**: `agents/semantic_parser/models/__init__.py`, `step1.py`, `step2.py`, `parse_result.py`, `pipeline.py`, `react.py`

- [ ] 创建 `agents/semantic_parser/models/` 包目录
- [ ] 创建 `step1.py`: 
  - 从 `core/models/step1.py` 迁移 `Step1Output` 模型
  - **★统一继承关系**：
    - `MeasureSpec` 继承 `core.models.fields.MeasureField`
    - `DimensionSpec` 继承 `core.models.fields.DimensionField`
    - `FilterSpec` 继承 `core.models.filters.Filter`
  - 更新导入路径
- [ ] 创建 `step2.py`: 
  - 从 `core/models/step2.py` 迁移 `Step2Output` 模型
  - 更新导入路径
- [ ] 创建 `parse_result.py`:
  - 从 `core/models/parse_result.py` 迁移 `SemanticParseResult`, `ClarificationQuestion` 模型
  - 更新导入路径
- [ ] 创建 `pipeline.py`: 定义 `QueryResult`, `QueryError` 模型
- [ ] 创建 `react.py`: 定义 `ReActThought`, `ReActAction`, `ReActObservation`, `ReActOutput` 模型
- [ ] 更新 `__init__.py` 导出所有模型
- [ ] 更新所有引用 `core/models/step1.py`、`core/models/step2.py`、`core/models/parse_result.py` 的文件

**模型迁移说明**:
- `core/models/step1.py` → `agents/semantic_parser/models/step1.py`
- `core/models/step2.py` → `agents/semantic_parser/models/step2.py`
- `core/models/parse_result.py` → `agents/semantic_parser/models/parse_result.py`
- 迁移后删除原文件

**★模型继承关系统一（本次重构范围）**:
```python
# agents/semantic_parser/models/step1.py
from core.models.fields import MeasureField, DimensionField
from core.models.filters import Filter
from core.models.enums import SortDirection

class MeasureSpec(MeasureField):
    """Step1 特有的度量规格，继承自核心层 MeasureField"""
    sort_direction: SortDirection | None = None
    sort_priority: int = 0

class DimensionSpec(DimensionField):
    """Step1 特有的维度规格，继承自核心层 DimensionField"""
    pass  # 如有 Step1 特有字段，在此添加

class FilterSpec(Filter):
    """Step1 特有的过滤器规格，继承自核心层 Filter"""
    n: int | None = None
    by_field: str | None = None
    direction: SortDirection | None = None
    values: list[str] | None = None
    start_date: str | None = None
    end_date: str | None = None
```

**验收标准**:
- 所有模型通过 Pydantic 验证
- 模型定义与 design.md 一致
- **继承关系正确**：MeasureSpec → MeasureField, DimensionSpec → DimensionField, FilterSpec → Filter
- 无导入错误

---

### Task 2.2: 定义 SemanticParser 内部状态
**文件**: `agents/semantic_parser/state.py`

- [ ] 创建 `SemanticParserState(TypedDict)`:
  - 输入字段: question, history, data_model
  - Step1 输出: step1_output
  - Step2 输出: step2_output
  - Pipeline 状态: semantic_query, pipeline_result
  - 最终输出: mapped_query, vizql_query, query_result, error

**依赖**: Task 2.1

**验收标准**:
- State 定义完整
- 类型注解正确，引用 models 包中的模型

---

### Task 2.3: 实现 Step1 节点
**文件**: `agents/semantic_parser/components/step1.py`

- [ ] 提取现有 Step1 逻辑到独立模块
- [ ] 实现 `step1_node(state: SemanticParserState) -> Dict`
- [ ] 使用 `models.step1.Step1Output` 作为输出类型
- [ ] 保持现有 Prompt 和输出格式

**依赖**: Task 2.1, Task 2.2

**验收标准**:
- Step1 逻辑保持不变
- 输出 Step1Output 正确

---

### Task 2.4: 实现 Step2 节点
**文件**: `agents/semantic_parser/components/step2.py`

- [ ] 提取现有 Step2 逻辑到独立模块
- [ ] 实现 `step2_node(state: SemanticParserState) -> Dict`
- [ ] 使用 `models.step2.Step2Output` 作为输出类型
- [ ] 保持现有 Prompt 和输出格式

**依赖**: Task 2.1, Task 2.2

**验收标准**:
- Step2 逻辑保持不变
- 输出 Step2Output 正确

---

### Task 2.5: 实现 QueryPipeline（核心）
**文件**: `agents/semantic_parser/components/query_pipeline.py`

**重要**：这是语义解析的核心组件，保证执行顺序并集成中间件

- [ ] 实现 `QueryPipeline` 类：
  - `__init__`: 接收 MiddlewareRunner 和 Runtime
  - `execute()`: 执行完整 Pipeline
  - `_execute_step1()`: 使用 `call_model_with_middleware`
  - `_execute_step2()`: 使用 `call_model_with_middleware`
  - `_execute_map_fields()`: 使用 `call_tool_with_middleware`（内部已有 RAG+LLM 混合策略）
  - `_execute_build_query()`: 纯逻辑，无中间件
  - `_execute_query()`: 使用 `call_tool_with_middleware`，处理 FilesystemMiddleware 返回的 Command
- [ ] 使用 `models.pipeline.QueryResult`, `QueryError` 作为返回类型

**字段映射说明**：
- `map_fields` 封装现有 `FieldMapperNode`，保留完整的 RAG+LLM 混合策略
- 映射策略：缓存 → RAG (confidence >= 0.9 直接返回) → LLM Fallback → LLM Only
- 映射失败返回结构化错误，触发 ReAct 错误处理

**中间件集成点**（完整 8 个中间件）:
- Step1/Step2: `call_model_with_middleware`
  - SummarizationMiddleware: 对话历史摘要
  - ModelRetryMiddleware: LLM 调用重试
  - FilesystemMiddleware: 注入系统提示
  - PatchToolCallsMiddleware: 修复悬空工具调用
  - OutputValidationMiddleware: 验证输出格式 (after_model)
- MapFields: `call_tool_with_middleware`
  - ToolRetryMiddleware: 工具调用重试（网络/API 错误，非映射逻辑错误）
- ExecuteQuery: `call_tool_with_middleware`
  - ToolRetryMiddleware: 工具调用重试
  - FilesystemMiddleware: 大结果保存
  - HumanInTheLoopMiddleware: 人工确认 (可选)
- Agent 级别钩子:
  - TodoListMiddleware: before_agent/after_agent 任务管理
  - PatchToolCallsMiddleware: before_agent 修复历史悬空调用
  - OutputValidationMiddleware: after_agent 验证必需字段

**依赖**: Task 1.2, Task 1.3, Task 1.4, Task 2.1

**验收标准**:
- Pipeline 保证执行顺序：Step1 → Step2 → MapFields → BuildQuery → Execute
- 字段映射使用现有 RAG+LLM 混合策略
- 中间件正确集成（特别是 FilesystemMiddleware 大结果处理）
- 返回结构化 QueryResult（含错误信息供 ReAct 处理）

---

### Task 2.6: 实现 ReAct 错误处理
**文件**: `agents/semantic_parser/components/react_error_handler.py`, `agents/semantic_parser/prompts/react_error.py`

**说明**：当 QueryPipeline 中任意工具返回错误时，进入 ReAct 错误处理模式

- [ ] 创建 `prompts/react_error.py`:
  - 实现 `ReActErrorHandlerPrompt` 类
  - 定义 `get_task()` 说明 ReAct 动作选项
  - 定义 `get_user_template()` 包含错误信息和重试次数
  - 使用 `ReActOutput` 作为输出模型
- [ ] 创建 `components/react_error_handler.py`:
  - 使用 `models.react` 中的数据模型（ReActThought, ReActAction, ReActObservation, ReActOutput）
  - 实现 `ReActErrorHandler` 类：
    - `__init__`: 接收 LLM 和 max_retries
    - `handle_error()`: 处理工具错误
    - `_generate_thought_and_action()`: 调用 LLM 生成 Thought + Action
    - `_execute_retry()`: 执行 RETRY 动作
    - `_execute_clarify()`: 执行 CLARIFY 动作
    - `_execute_abort()`: 执行 ABORT 动作
- [ ] 更新 `prompts/__init__.py` 导出 ReActErrorHandlerPrompt

**ReAct 流程**：
- 工具返回错误（初始 Observation）→ Thought（分析错误）→ Action（RETRY/CLARIFY/ABORT）
- RETRY 后执行工具 → Observation（观察结果）→ 成功则结束，失败则回到 Thought
- 最多重试 max_retries 次

**依赖**: Task 2.1, Task 2.5

**验收标准**:
- ReAct 正确分析错误并决策
- RETRY 能使用修正参数重试工具
- CLARIFY 能返回澄清问题给用户
- ABORT 能返回友好错误信息
- 重试次数限制正常工作

---

### Task 2.7: 实现外层决策逻辑
**文件**: `agents/semantic_parser/components/decision_handler.py`

**说明**：整合 QueryPipeline 和 ReAct 错误处理

- [ ] 定义 `DecisionState(TypedDict)` 状态
- [ ] 实现 `pipeline_node`: 调用 QueryPipeline
- [ ] 实现 `react_error_node`: 调用 ReActErrorHandler
- [ ] 实现 `handle_result`: 根据结果处理
  - success=True → 结束，进入 Insight
  - error + can_retry → ReAct 错误处理
  - error + ABORT → 返回错误信息给用户
  - CLARIFY → 返回澄清问题给用户
- [ ] 实现 `route_after_pipeline` 路由函数
- [ ] 实现 `route_after_react` 路由函数
- [ ] 创建 `create_semantic_parser_graph()` 构建 StateGraph
- [ ] 实现 `execute_semantic_parser()` 同步执行函数
- [ ] 实现 `stream_semantic_parser()` 流式执行函数
  - 使用 `astream_events` 获取 token 级别流式输出

**依赖**: Task 2.5, Task 2.6

**验收标准**:
- Pipeline 执行正常
- 错误触发 ReAct 处理
- Token 级别流式输出正常工作

---

### Task 2.8: 创建 SemanticParser Subgraph
**文件**: `agents/semantic_parser/subgraph.py`

- [ ] 实现 `create_semantic_parser_subgraph() -> StateGraph`
- [ ] 添加节点: step1, step2, pipeline, react_error_handler
- [ ] 添加边:
  - START → step1
  - step1 → (conditional) → step2 | pipeline | END
  - step2 → pipeline
  - pipeline → (conditional) → react_error_handler | END
  - react_error_handler → (conditional) → pipeline | END
- [ ] 实现 `route_after_step1()` 路由函数
- [ ] 实现 `route_after_pipeline()` 路由函数
- [ ] 实现 `route_after_react()` 路由函数

**依赖**: Task 2.3, Task 2.4, Task 2.7

**验收标准**:
- Subgraph 编译成功
- 正常流程正确执行
- 错误流程触发 ReAct 处理

---

### Task 2.9: 更新 SemanticParser Node 适配
**文件**: `agents/semantic_parser/node.py`

- [ ] 修改 `semantic_parser_node()` 函数
- [ ] 调用 Subgraph 而非直接执行
- [ ] 映射 Subgraph 输出到主 State

**依赖**: Task 2.8

**验收标准**:
- Node 正确调用 Subgraph
- State 输出字段正确填充

---

### Task 2.10: 移除 Observer 组件（由 ReAct 替代）
**文件**: 删除 `agents/semantic_parser/components/observer.py`, `prompts/observer.py`

- [ ] 删除 Observer 相关文件
- [ ] 更新 `__init__.py` 移除导出
- [ ] 搜索并移除所有 Observer 相关导入
- [ ] 确认 ReAct 错误处理已承担 Observer 功能

**依赖**: Task 2.8

**验收标准**:
- Observer 相关文件已删除
- 无残留导入错误
- ReAct 错误处理正常工作

---

## Phase 3: InsightAgent Subgraph 实现

### Task 3.1: 创建 InsightAgent models 包
**文件**: `agents/insight/models/__init__.py`, `profile.py`, `insight.py`, `director.py`, `analyst.py`

- [ ] 创建 `agents/insight/models/` 包目录
- [ ] 创建 `profile.py`: 定义 EnhancedDataProfile, ContributorAnalysis, ConcentrationRisk, PeriodChangeAnalysis, TrendAnalysis, DimensionIndex, AnomalyIndex 模型
- [ ] 创建 `insight.py`: 
  - 从 `core/models/insight.py` 迁移 `Insight`, `InsightQuality` 模型
  - 更新导入路径
- [ ] 创建 `director.py`: 定义 DirectorInput, DirectorDecision, DirectorOutputWithAccumulation 模型
- [ ] 创建 `analyst.py`: 定义 AnalystOutputWithHistory, HistoricalInsightAction 模型
- [ ] 更新 `__init__.py` 导出所有模型
- [ ] 更新所有引用 `core/models/insight.py` 的文件

**模型迁移说明**:
- `core/models/insight.py` → `agents/insight/models/insight.py`
- 迁移后删除原文件

**规范要求**: 遵循 `PROMPT_AND_MODEL_GUIDE.md`

**验收标准**:
- 所有模型通过 Pydantic 验证
- 模型定义与 design.md 一致
- 无导入错误

---

### Task 3.2: 定义 Insight 内部状态
**文件**: `agents/insight/state.py`

- [ ] 创建 `InsightState(TypedDict)`:
  - 输入: query_result, files, context
  - Phase 1: enhanced_profile
  - Phase 2: director_decisions, current_action
  - Phase 3: chunks, analyzed_chunks, chunk_insights
  - Phase 4: final_insights, summary
  - 控制: iteration_count, should_continue

**依赖**: Task 3.1

**验收标准**:
- State 定义完整
- 类型注解正确，引用 models 包中的模型

---

### Task 3.3: 实现 EnhancedDataProfiler
**文件**: `agents/insight/components/profiler.py`

- [ ] 增强 `DataProfiler` 类为 `EnhancedDataProfiler`
- [ ] 实现 `_analyze_contributors()`: Top/Bottom 贡献者分析
- [ ] 实现 `_analyze_concentration()`: 集中度风险检测
- [ ] 实现 `_analyze_period_changes()`: 同环比分析
- [ ] 实现 `_analyze_trends()`: 趋势检测
- [ ] 实现 `_build_dimension_index()`: 维度索引构建
- [ ] 实现 `_build_anomaly_index()`: 异常索引构建
- [ ] 实现 `_recommend_strategy()`: 分块策略推荐
- [ ] 使用 `models.profile` 中的数据模型

**依赖**: Task 3.1

**验收标准**:
- 生成 Tableau Pulse 风格洞察
- 索引构建正确
- 策略推荐合理

---

### Task 3.4: 实现 Profiler 节点
**文件**: `agents/insight/components/profiler_node.py`

- [ ] 实现 `profiler_node(state: InsightState) -> Dict`
- [ ] 检测大文件引用，从 files 读取
- [ ] 调用 EnhancedDataProfiler 生成画像
- [ ] 基于画像推荐策略分块

**依赖**: Task 3.3

**验收标准**:
- 小数据直接处理
- 大数据从 files 读取
- 画像和分块正确生成

---

### Task 3.5: 增强 AnalysisDirector
**文件**: `agents/insight/components/director.py`

- [ ] 使用 `models.director` 中的数据模型（DirectorInput, DirectorDecision, DirectorOutputWithAccumulation）
- [ ] 更新总监 Prompt 展示 Tableau Pulse 洞察摘要
- [ ] 实现 `decide()` 方法返回 `DirectorDecision`
- [ ] 支持按维度/异常精准分析决策

**依赖**: Task 3.1

**验收标准**:
- 总监能看到画像摘要
- 决策更智能

---

### Task 3.6: 实现 Director 节点
**文件**: `agents/insight/components/director_node.py`

- [ ] 实现 `director_node(state: InsightState) -> Dict`
- [ ] 调用 AnalysisDirector.decide()
- [ ] 更新 State 决策字段

**依赖**: Task 3.5

**验收标准**:
- 决策正确生成
- State 正确更新

---

### Task 3.7: 增强分析师 Prompt 支持历史洞察处理
**文件**: `agents/insight/prompts/analyst.py`

- [ ] 使用 `models.analyst` 中的数据模型（AnalystOutputWithHistory, HistoricalInsightAction）
- [ ] 创建 `AnalystPromptWithHistory` 类:
  - 增加历史洞察输入（带索引）
  - 增加历史洞察处理建议输出要求
  - 使用 `AnalystOutputWithHistory` 作为输出模型
- [ ] 更新 `get_user_template()` 包含历史洞察
- [ ] 更新 `get_task()` 说明处理建议要求

**依赖**: Task 3.1

**验收标准**:
- Prompt 包含历史洞察处理说明
- 输出模型正确

---

### Task 3.8: 增强总监 Prompt 支持洞察累积和最终综合
**文件**: `agents/insight/prompts/director.py`

- [ ] 使用 `models.director` 中的数据模型（DirectorOutputWithAccumulation）
- [ ] 创建 `DirectorPromptWithAccumulation` 类:
  - 增加分析师输出（新洞察 + 历史处理建议）
  - 增加洞察处理执行要求
  - 增加最终摘要生成要求（当 should_continue=False 时）
  - 使用 `DirectorOutputWithAccumulation` 作为输出模型
- [ ] 更新 `get_user_template()` 包含分析师建议
- [ ] 更新 `get_task()` 说明洞察处理执行要求和最终摘要生成

**依赖**: Task 3.1

**验收标准**:
- Prompt 包含洞察处理执行说明
- Prompt 包含最终摘要生成说明
- 输出模型正确

---

### Task 3.9: 更新 ChunkAnalyzer 支持渐进式累积
**文件**: `agents/insight/components/analyzer.py`

- [ ] 更新 `analyze_chunk_with_analyst()`:
  - 使用 `AnalystPromptWithHistory`
  - 传入历史洞察（带索引）
  - 返回 `AnalystOutputWithHistory`
- [ ] 更新 `decide_next_with_director()`:
  - 使用 `DirectorPromptWithAccumulation`
  - 传入分析师输出（新洞察 + 历史处理建议）
  - 返回 `DirectorOutputWithAccumulation`
- [ ] 更新 `_parse_analyst_response()` 解析增强输出
- [ ] 更新 `_parse_director_response()` 解析增强输出

**依赖**: Task 3.7, Task 3.8

**验收标准**:
- 分析师正确输出历史洞察处理建议
- 总监正确执行洞察处理
- 解析逻辑正确

---

### Task 3.10: 实现洞察累积辅助模块
**文件**: `agents/insight/components/accumulator.py`

**说明**：提供代码级别的洞察去重和累积辅助功能

- [ ] 创建 `InsightAccumulator` 类:
  - `__init__`: 初始化累积器
  - `add_insights()`: 添加新洞察
  - `get_accumulated()`: 获取累积洞察列表
  - `_is_duplicate()`: 基于标题的简单去重（作为 LLM 决策的兜底）
- [ ] 实现 `format_insights_with_index()`: 格式化历史洞察（带索引）供 LLM 使用
- [ ] 实现 `apply_actions()`: 应用 LLM 的处理建议（MERGE/REPLACE/KEEP/DISCARD）

**依赖**: Task 3.1

**验收标准**:
- 累积器正确管理洞察列表
- 格式化输出包含索引
- 处理建议应用正确

---

### Task 3.11: 实现 Analyzer 节点
**文件**: `agents/insight/components/analyzer_node.py`

- [ ] 实现 `analyzer_node(state: InsightState) -> Dict`
- [ ] 根据 decision.action 执行不同分析:
  - analyze_chunk: 分析指定分块
  - analyze_dimension: 按维度值精准读取
  - analyze_anomaly: 分析指定异常
- [ ] 实现 `read_by_dimension()` 精准读取
- [ ] 实现 `read_by_indices()` 按行号读取

**依赖**: Task 3.6, Task 3.10

**验收标准**:
- 支持多种分析动作
- 精准读取正确

---

### Task 3.12: 创建 Insight Subgraph
**文件**: `agents/insight/subgraph.py`

- [ ] 实现 `create_insight_subgraph() -> StateGraph`
- [ ] 添加节点: profiler, director, analyzer（无 synthesizer）
- [ ] 添加边:
  - START → profiler
  - profiler → director
  - director → (conditional) → analyzer | END
  - analyzer → director (循环)
- [ ] 实现 `route_after_director()` 路由函数:
  - should_continue=True → analyzer
  - should_continue=False → END

**依赖**: Task 3.4, Task 3.6, Task 3.11

**验收标准**:
- Subgraph 编译成功
- 循环正确执行
- 总监决定停止时直接结束（无 Synthesizer）

---

### Task 3.13: 更新 Insight Node 适配
**文件**: `agents/insight/node.py`

- [ ] 修改 `insight_node()` 函数
- [ ] 调用 Subgraph 而非直接执行
- [ ] 映射 Subgraph 输出到主 State:
  - `accumulated_insights`: 总监输出的累积洞察（结构化 Insight 对象列表）
  - `final_summary`: 总监输出的最终摘要（自然语言）
- [ ] 使用 `accumulated_insights` 而非简单追加

**依赖**: Task 3.12

**验收标准**:
- Node 正确调用 Subgraph
- State 输出字段正确填充
- 渐进式累积正确工作

---

### Task 3.14: 移除 Synthesizer 组件
**文件**: 删除或标记废弃 `agents/insight/components/synthesizer.py`

- [ ] 标记 `InsightSynthesizer` 类为废弃（或删除）
- [ ] 更新 `__init__.py` 移除导出
- [ ] 搜索并移除所有 Synthesizer 相关导入
- [ ] 确保总监 LLM 承担原 Synthesizer 的功能

**依赖**: Task 3.12

**验收标准**:
- Synthesizer 不再被使用
- 总监 LLM 正确生成最终摘要

---

### Task 3.15: 创建 Replanner models 包
**文件**: `agents/replanner/models/__init__.py`, `output.py`

- [ ] 创建 `agents/replanner/models/` 包目录
- [ ] 创建 `output.py`: 
  - 从 `core/models/replan.py` 迁移 `ReplannerOutput` 模型
  - 更新导入路径
- [ ] 更新 `__init__.py` 导出模型
- [ ] 更新所有引用 `core/models/replan.py` 的文件

**模型迁移说明**:
- `core/models/replan.py` → `agents/replanner/models/output.py`
- 迁移后删除原文件

**验收标准**:
- 模型通过 Pydantic 验证
- 模型定义与 design.md 一致
- 无导入错误

---

### Task 3.16: 更新 Replanner prompts 为包结构
**文件**: `agents/replanner/prompts/__init__.py`, `replanner.py`

- [ ] 将 `agents/replanner/prompt.py` 改为 `agents/replanner/prompts/` 包
- [ ] 创建 `prompts/replanner.py`: 移动 ReplannerPrompt
- [ ] 更新 `__init__.py` 导出 Prompt

**验收标准**:
- Prompt 包结构正确
- 导入路径更新

---

## Phase 4: 主工作流重构

### Task 4.1: 更新 State 定义
**文件**: `core/state.py`

- [ ] 移除不再需要的字段:
  - `correction_count`, `correction_exhausted`
  - `field_mapper_complete`, `query_builder_complete`, `execute_complete`
- [ ] 添加新字段:
  - `tool_observations: List[Dict[str, Any]]`
  - `enhanced_profile: Optional[EnhancedDataProfile]`
- [ ] 添加并行执行相关字段:
  - `parallel_questions: List[str]` - 待并行执行的问题列表
  - `accumulated_insights: Annotated[List[Insight], merge_insights]` - 渐进式累积洞察（使用自定义 reducer）
- [ ] 实现 `merge_insights` reducer 函数
- [ ] 更新 `query_result` 类型注解支持文件引用
- [ ] 简化节点完成标志

**验收标准**:
- State 定义与 design.md 一致
- 并行执行字段正确定义
- `merge_insights` reducer 正确合并洞察列表
- 无类型错误

---

### Task 4.2: 简化 routes.py
**文件**: `orchestration/workflow/routes.py`

- [ ] 从 4 个路由函数减少到 2 个:
  - `route_after_semantic_parser()`: 决定 insight | end
  - `route_after_replanner()`: 决定 semantic_parser | end（支持 Send() 并行）
- [ ] 移除路由函数:
  - `route_after_execute()`
  - `route_after_self_correction()`
- [ ] 更新 `route_after_replanner()` 支持并行执行:
  - `len(exploration_questions) > 1` → 返回 `List[Send]` 并行分发
  - `len(exploration_questions) == 1` → semantic_parser（串行）
  - `should_replan=False` → end

**验收标准**:
- 路由函数支持 Send() API 并行执行
- 路由逻辑与 design.md 一致
- 无 FanIn/FanOut 节点

---

### Task 4.3: 重构 factory.py
**文件**: `orchestration/workflow/factory.py`

- [ ] 从 7 节点减少到 3 节点:
  - `semantic_parser` (Subgraph)
  - `insight` (Subgraph)
  - `replanner` (单节点)
- [ ] 移除节点:
  - `field_mapper`, `query_builder`, `execute`, `self_correction`
  - `fanout`, `fanin`（不需要，LangGraph 自动处理）
- [ ] 更新边定义:
  - START → semantic_parser
  - semantic_parser → insight
  - insight → replanner
  - replanner → (conditional) → semantic_parser | END
  - 并行执行通过 Send() API 在 route_after_replanner 中处理
- [ ] 更新 `create_workflow()` 函数

**依赖**: Task 2.8, Task 3.11, Task 4.1, Task 4.2

**验收标准**:
- 工作流支持并行执行（通过 Send() API）
- 无 FanIn/FanOut 节点
- 边定义正确
- 编译成功

---

### Task 4.4: 移除 SelfCorrection 节点
**文件**: 删除 `nodes/self_correction/` 目录

- [ ] 删除 `nodes/self_correction/` 整个目录
- [ ] 更新 `nodes/__init__.py` 移除导出
- [ ] 搜索并移除所有 SelfCorrection 相关导入

**依赖**: Task 4.3

**验收标准**:
- SelfCorrection 目录已删除
- 无残留导入错误

---

### Task 4.5: 清理旧节点代码
**文件**: `nodes/field_mapper/`, `nodes/query_builder/`, `nodes/execute/`

- [ ] 删除 `nodes/field_mapper/` 目录 (逻辑已移到 Tool)
- [ ] 删除 `nodes/query_builder/` 目录 (逻辑已移到 Tool)
- [ ] 删除 `nodes/execute/` 目录 (逻辑已移到 Tool)
- [ ] 更新 `nodes/__init__.py`
- [ ] 最终删除整个 `nodes/` 目录

**依赖**: Task 1.2, Task 1.3, Task 1.4

**验收标准**:
- 旧节点代码已删除
- 无残留导入错误

---

### Task 4.6: 更新 Replanner 节点支持并行
**文件**: `agents/replanner/node.py`

- [ ] 更新 `replanner_node()` 设置 `parallel_questions`:
  - 当 `len(exploration_questions) > 1` 时，设置 `parallel_questions`
  - 当 `len(exploration_questions) == 1` 时，设置 `question`（串行执行）
- [ ] 添加并行执行日志

**依赖**: Task 4.1

**验收标准**:
- Replanner 正确设置并行问题列表
- 单问题时保持串行执行

---

### Task 4.7: 清理 core/models 中已迁移的文件
**文件**: `core/models/`

**迁移到其他层的文件**:
- [ ] 迁移 `core/models/data_model.py` → `infra/storage/data_model.py`
- [ ] 迁移 `core/models/dimension_hierarchy.py` → `agents/dimension_hierarchy/models/hierarchy.py`
- [ ] 迁移 `core/models/query_request.py` → `platforms/base.py`
- [ ] 迁移 `core/models/field_mapping.py` → `agents/field_mapper/models/mapping.py`
- [ ] 迁移 `core/models/parse_result.py` → `agents/semantic_parser/models/parse_result.py`
- [ ] 迁移 `core/models/step1.py` → `agents/semantic_parser/models/step1.py`
  - [ ] 更新 `MeasureSpec` 继承 `MeasureField`
  - [ ] 更新 `DimensionSpec` 继承 `DimensionField`
  - [ ] 更新 `FilterSpec` 继承 `Filter`
- [ ] 迁移 `core/models/step2.py` → `agents/semantic_parser/models/step2.py`
- [ ] 迁移 `core/models/insight.py` → `agents/insight/models/insight.py`
- [ ] 迁移 `core/models/replan.py` → `agents/replanner/models/output.py`

**删除的文件**:
- [ ] 删除 `core/models/observer.py`（由 ReAct 替代）

**更新导入路径**:
- [ ] 更新 `core/models/__init__.py` 移除已迁移模型的导出
- [ ] 更新所有引用已迁移模型的文件
- [ ] 确认所有导入路径已更新

**验证核心层只保留 7 个文件**:
- [ ] `enums.py` - 语义层枚举
- [ ] `fields.py` - 字段抽象（DimensionField, MeasureField, Sort）
- [ ] `filters.py` - 过滤器抽象（Filter 及其子类）
- [ ] `computations.py` - 计算抽象（Computation, CalcParams）
- [ ] `query.py` - SemanticQuery（核心输出）
- [ ] `execute_result.py` - 执行结果抽象
- [ ] `validation.py` - 验证结果抽象

**依赖**: Task 2.1, Task 3.1, Task 3.14

**验收标准**:
- 已迁移的模型文件已删除
- 无导入错误
- `core/models/` 只保留 7 个文件（真正的核心层）
- 核心层零依赖原则验证通过（core/ 不导入 platforms/、infra/、agents/）
- 继承关系统一（MeasureSpec → MeasureField 等）

---

### Task 4.8: 清理 infra 层不需要的文件
**文件**: `infra/config/`, `infra/utils/`, `infra/ai/rag/`, `infra/monitoring/`

**删除的目录/文件**:
- [ ] 删除 `infra/config/tableau_env.py`（多环境配置不需要）
- [ ] 删除 `infra/utils/` 整个目录
  - [ ] `conversation.py` 中的 `trim_answered_questions()` 移到使用处（如 `agents/replanner/node.py`）
- [ ] 删除 `infra/monitoring/` 整个目录（使用 LangSmith 进行监控）
  - [ ] 删除 `callbacks.py`（SQLiteTrackingCallback 不再需要）
  - [ ] 删除 `__init__.py`

**迁移的目录**:
- [ ] 迁移 `infra/ai/rag/` → `agents/field_mapper/rag/`（RAG 是字段映射 Agent 的实现细节）
  - [ ] 迁移 `assembler.py`
  - [ ] 迁移 `cache.py`
  - [ ] 迁移 `dimension_pattern.py`
  - [ ] 迁移 `embeddings.py`
  - [ ] 迁移 `field_indexer.py`
  - [ ] 迁移 `models.py`
  - [ ] 迁移 `observability.py`
  - [ ] 迁移 `reranker.py`
  - [ ] 迁移 `retriever.py`
  - [ ] 迁移 `semantic_mapper.py`

**更新导入路径**:
- [ ] 更新所有引用 `infra/ai/rag/` 的文件，改为 `agents/field_mapper/rag/`
- [ ] 更新 `infra/config/__init__.py` 移除 `tableau_env` 导出
- [ ] 更新 `infra/__init__.py` 移除 `utils` 和 `monitoring` 导出
- [ ] 移除所有引用 `infra/monitoring/` 的代码

**依赖**: Task 4.7

**验收标准**:
- `infra/ai/` 只保留 LLM 相关文件（llm.py, embeddings.py, reranker.py, deepseek_r1.py）
- `infra/config/` 只保留 `settings.py`
- `infra/utils/` 目录已删除
- `infra/monitoring/` 目录已删除
- RAG 功能在 `agents/field_mapper/rag/` 正常工作
- 无导入错误

---

### Task 4.9: 清理 platforms/tableau 层
**文件**: `platforms/tableau/`

**删除的文件**:
- [ ] 删除 `platforms/tableau/client.py`（薄包装器不需要，直接使用 vizql_client.py）

**重命名的文件**:
- [ ] 重命名 `platforms/tableau/metadata.py` → `platforms/tableau/tableau_data_model.py`
  - [ ] 更新文件内的 docstring 说明
  - [ ] 更新所有引用 `metadata.py` 的文件

**更新导入路径**:
- [ ] 更新所有引用 `platforms/tableau/client.py` 的文件，改为直接使用 `vizql_client.py`
- [ ] 更新所有引用 `platforms/tableau/metadata.py` 的文件

**依赖**: Task 4.8

**验收标准**:
- `client.py` 已删除
- `metadata.py` 已重命名为 `tableau_data_model.py`
- 无导入错误

---

## Phase 5: 测试与验证

### Task 5.1: Tool 单元测试
**文件**: `tests/orchestration/tools/`

- [ ] 创建 `test_map_fields_tool.py`:
  - 测试正常映射
  - 测试 field_not_found 错误
  - 测试 ambiguous_field 错误
- [ ] 创建 `test_build_query_tool.py`:
  - 测试正常构建
  - 测试 invalid_computation 错误
  - 测试 unsupported_operation 错误
- [ ] 创建 `test_execute_query_tool.py`:
  - 测试正常执行
  - 测试各类错误

**验收标准**:
- 所有 Tool 测试通过
- 覆盖正常和错误场景

---

### Task 5.2: SemanticParser Subgraph 测试
**文件**: `tests/agents/semantic_parser/`

- [ ] 创建 `test_subgraph.py`:
  - 测试 Step1 → Pipeline 流程 (SIMPLE)
  - 测试 Step1 → Step2 → Pipeline 流程 (COMPLEX)
  - 测试非 DATA_QUERY 意图直接结束
- [ ] 创建 `test_query_pipeline.py`:
  - 测试正常流程: Step1 → Step2 → MapFields → BuildQuery → Execute
  - 测试字段映射 RAG+LLM 混合策略（缓存→RAG→LLM Fallback→LLM Only）
  - 测试所有 8 个 Middleware 集成
- [ ] 创建 `test_react_error_handler.py`:
  - 测试 RETRY 动作：修正参数后重试成功
  - 测试 RETRY 动作：达到最大重试次数后 ABORT
  - 测试 CLARIFY 动作：返回澄清问题
  - 测试 ABORT 动作：返回友好错误信息
  - 测试 Thought 分析正确性
- [ ] 创建 `test_decision_handler.py`:
  - 测试成功场景：Pipeline 成功 → 结束
  - 测试错误场景：触发 ReAct 错误处理
  - 测试 Token 级别流式输出

**验收标准**:
- Subgraph 测试通过
- QueryPipeline 测试通过
- ReAct 错误处理测试通过
- Decision Handler 测试通过
- 所有 8 个 Middleware 集成测试通过
- 流式输出测试通过

---

### Task 5.3: EnhancedDataProfiler 单元测试
**文件**: `tests/agents/insight/test_enhanced_profiler.py`

- [ ] 测试 `_analyze_contributors()`:
  - 正确识别 Top/Bottom 贡献者
  - 计算百分比正确
- [ ] 测试 `_analyze_concentration()`:
  - 正确检测集中度风险
  - 风险等级判断正确
- [ ] 测试 `_analyze_period_changes()`:
  - 正确计算同环比
  - 变化方向判断正确
- [ ] 测试 `_analyze_trends()`:
  - 正确检测趋势方向
  - 变点检测正确
- [ ] 测试 `_build_dimension_index()`:
  - 索引构建正确
  - 行号范围准确
- [ ] 测试 `_build_anomaly_index()`:
  - 异常检测正确
  - 严重度分组正确
- [ ] 测试 `_recommend_strategy()`:
  - 策略推荐合理

**验收标准**:
- 所有 Tableau Pulse 风格洞察测试通过
- 索引构建测试通过

---

### Task 5.4: Insight Subgraph 测试
**文件**: `tests/agents/insight/test_subgraph.py`

- [ ] 测试 profiler → director → analyzer 循环流程
- [ ] 测试 director 循环决策
- [ ] 测试按维度精准读取
- [ ] 测试按异常精准读取
- [ ] 测试大文件场景
- [ ] 测试总监生成最终摘要（无 Synthesizer）

**验收标准**:
- Subgraph 测试通过
- 循环正确执行
- 总监正确生成 final_summary

---

### Task 5.5: 渐进式洞察累积测试
**文件**: `tests/agents/insight/test_progressive_accumulation.py`

- [ ] 测试分析师输出历史洞察处理建议:
  - 测试 MERGE 建议生成
  - 测试 REPLACE 建议生成
  - 测试 KEEP 建议生成
  - 测试 DISCARD 建议生成
- [ ] 测试总监执行洞察处理:
  - 测试 MERGE 执行（洞察合并）
  - 测试 REPLACE 执行（洞察替换）
  - 测试 KEEP 执行（洞察保留）
  - 测试 DISCARD 执行（洞察丢弃）
- [ ] 测试多轮累积场景:
  - 第一轮：生成初始洞察
  - 第二轮：部分 MERGE + 部分 KEEP
  - 第三轮：部分 REPLACE + 部分 DISCARD
- [ ] 测试解析失败时的默认 KEEP 策略

**验收标准**:
- 分析师正确生成处理建议
- 总监正确执行处理
- 多轮累积正确工作
- 解析失败时不丢失洞察

---

### Task 5.6: 集成测试
**文件**: `tests/integration/`

- [ ] 创建 `test_semantic_parser_flow.py`:
  - 测试简单查询完整流程
  - 测试复杂查询完整流程
  - 测试错误处理场景
- [ ] 创建 `test_insight_flow.py`:
  - 测试 InsightAgent 使用 EnhancedDataProfiler
  - 测试总监基于画像决策
  - 测试按维度/异常精准分析
  - 测试渐进式洞察累积
- [ ] 创建 `test_replan_loop.py`:
  - 测试单轮: SemanticParser → Insight → Replanner (end)
  - 测试多轮重规划循环
  - 测试最大轮数限制
- [ ] 创建 `test_parallel_execution.py`:
  - 测试 Send() API 正确分发多个问题
  - 测试并行分支独立执行
  - 测试 LangGraph 自动合并 accumulated_insights
  - 测试单分支失败不影响其他分支

**验收标准**:
- 集成测试通过
- 重规划循环正确工作
- 并行执行正确工作
- 渐进式累积正确工作

---

### Task 5.7: 端到端测试
**文件**: `tests/e2e/test_complete_workflow.py`

- [ ] 测试完整对话流程
- [ ] 测试流式输出 (InsightAgent)
- [ ] 测试错误恢复流程
- [ ] 测试大数据场景（FilesystemMiddleware + EnhancedDataProfiler）

**验收标准**:
- 端到端测试通过
- 与旧架构行为一致

---

## Phase 6: 文档与清理

### Task 6.1: 更新代码注释
**文件**: 各相关文件

- [ ] 更新 `factory.py` 注释说明新架构
- [ ] 更新 `subgraph.py` 注释说明 Subgraph 模式
- [ ] 更新 Tool 文件注释

**验收标准**:
- 注释清晰说明新架构

---

### Task 6.2: 更新 README
**文件**: `tableau_assistant/README.md`

- [ ] 更新架构说明
- [ ] 更新工作流图
- [ ] 更新 API 文档
- [ ] 添加 Subgraph 说明

**验收标准**:
- README 反映新架构

---

### Task 6.3: 清理遗留代码
**文件**: 各相关文件

- [ ] 搜索并移除所有 TODO 注释
- [ ] 移除未使用的导入
- [ ] 运行 linter 确保代码质量
- [ ] 删除空目录

**验收标准**:
- 无遗留 TODO
- 代码通过 linter 检查

---

### Task 6.4: 更新依赖
**文件**: `requirements.txt`

- [ ] 确认 `langgraph` 版本 >= 1.0.5
- [ ] 确认 `langchain` 版本 >= 1.1.3
- [ ] 移除 `langgraph-prebuilt`（如果之前添加了）
- [ ] 移除 `langgraph-supervisor`（如果之前添加了）
- [ ] 移除不再需要的依赖

**验收标准**:
- 依赖列表正确
- 安装无错误
- 不包含未使用的依赖

---

## 依赖关系图

```
Phase 1: Tool 基础设施
├── Task 1.1: Tool 基础设施
├── Task 1.2: map_fields Tool 包 (依赖 1.1)
├── Task 1.3: build_query Tool 包 (依赖 1.1)
└── Task 1.4: execute_query Tool 包 (依赖 1.1)
        │
        ▼
Phase 2: SemanticParser Subgraph
├── Task 2.1: models 包 ★含模型迁移
├── Task 2.2: 内部状态定义 (依赖 2.1)
├── Task 2.3: Step1 节点 (依赖 2.1, 2.2)
├── Task 2.4: Step2 节点 (依赖 2.1, 2.2)
├── Task 2.5: QueryPipeline (依赖 1.2-1.4, 2.1) ★核心
├── Task 2.6: ReAct 错误处理 (依赖 2.1, 2.5) ★新增
├── Task 2.7: Decision Handler (依赖 2.5, 2.6)
├── Task 2.8: Subgraph 创建 (依赖 2.3, 2.4, 2.7)
├── Task 2.9: Node 适配 (依赖 2.8)
└── Task 2.10: 移除 Observer (依赖 2.8) ★由 ReAct 替代
        │
        ▼
Phase 3: InsightAgent Subgraph
├── Task 3.1: models 包 ★含模型迁移
├── Task 3.2: 内部状态定义 (依赖 3.1)
├── Task 3.3: EnhancedDataProfiler (依赖 3.1)
├── Task 3.4: Profiler 节点 (依赖 3.3)
├── Task 3.5: AnalysisDirector 增强 (依赖 3.1)
├── Task 3.6: Director 节点 (依赖 3.5)
├── Task 3.7: 分析师 Prompt 增强 (依赖 3.1) ★新增
├── Task 3.8: 总监 Prompt 增强 (依赖 3.1) ★含最终综合
├── Task 3.9: ChunkAnalyzer 支持渐进式累积 (依赖 3.7, 3.8) ★新增
├── Task 3.10: 洞察累积辅助模块 (依赖 3.1) ★新增
├── Task 3.11: Analyzer 节点 (依赖 3.6, 3.10)
├── Task 3.12: Subgraph 创建 (依赖 3.4, 3.6, 3.11) ★无 Synthesizer
├── Task 3.13: Node 适配 (依赖 3.12)
├── Task 3.14: 移除 Synthesizer (依赖 3.12) ★新增
├── Task 3.15: Replanner models 包 ★含模型迁移
└── Task 3.16: Replanner prompts 包 ★新增
        │
        ▼
Phase 4: 主工作流重构
├── Task 4.1: 更新 State (含并行执行字段 + accumulated_insights)
├── Task 4.2: 简化 routes.py (支持 Send() API 并行)
├── Task 4.3: 重构 factory.py (依赖 2.8, 3.12, 4.1, 4.2)
├── Task 4.4: 移除 SelfCorrection (依赖 4.3)
├── Task 4.5: 清理旧节点 (依赖 1.2-1.4)
├── Task 4.6: 更新 Replanner 节点支持并行 (依赖 4.1)
├── Task 4.7: 清理 core/models (依赖 2.1, 3.1, 3.15) ★重要：只保留 7 个核心文件
│   ├── 迁移 data_model.py → infra/storage/
│   ├── 迁移 dimension_hierarchy.py → agents/dimension_hierarchy/models/
│   ├── 迁移 query_request.py → platforms/base.py
│   ├── 迁移 field_mapping.py → agents/field_mapper/models/mapping.py
│   ├── 迁移 parse_result.py → agents/semantic_parser/models/
│   ├── 统一继承关系 (MeasureSpec → MeasureField 等)
│   └── 删除 observer.py
├── Task 4.8: 清理 infra 层 (依赖 4.7) ★新增
│   ├── 删除 tableau_env.py（多环境配置不需要）
│   ├── 删除 utils/ 目录
│   ├── 删除 monitoring/ 目录（使用 LangSmith）
│   └── 迁移 rag/ → agents/field_mapper/rag/
└── Task 4.9: 清理 platforms/tableau 层 (依赖 4.8) ★新增
    ├── 删除 client.py
    └── 重命名 metadata.py → tableau_data_model.py
        │
        ▼
Phase 5: 测试
├── Task 5.1: Tool 单元测试 (依赖 Phase 1)
├── Task 5.2: SemanticParser Subgraph 测试 (依赖 Phase 2)
├── Task 5.3: EnhancedDataProfiler 测试 (依赖 Task 3.3)
├── Task 5.4: Insight Subgraph 测试 (依赖 Phase 3)
├── Task 5.5: 渐进式洞察累积测试 (依赖 Task 3.9, 3.10) ★新增
├── Task 5.6: 集成测试 (依赖 Phase 4)
└── Task 5.7: 端到端测试 (依赖 Phase 4)
        │
        ▼
Phase 6: 文档与清理
├── Task 6.1: 更新注释
├── Task 6.2: 更新 README
├── Task 6.3: 清理遗留代码
└── Task 6.4: 更新依赖
```

---

## 时间估算

| Phase | 任务数 | 预计时间 | 说明 |
|-------|--------|---------|------|
| Phase 1 | 4 | 1-1.5 天 | Tool 包实现，提取现有逻辑 |
| Phase 2 | 10 | 3-3.5 天 | SemanticParser Subgraph + models 包迁移 + ReAct 错误处理 + 继承关系统一 |
| Phase 3 | 16 | 4-5 天 | InsightAgent Subgraph + models 包迁移 + 渐进式累积 + 累积辅助模块 |
| Phase 4 | 9 | 2.5-3 天 | 主工作流重构 + 并行执行 + core/models 大规模迁移 + infra/platforms 清理 |
| Phase 5 | 7 | 3-3.5 天 | 测试覆盖（含 ReAct + 渐进式累积测试） |
| Phase 6 | 4 | 0.5-1 天 | 文档更新 |
| **总计** | **50** | **14-18 天** | |

---

## 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| Subgraph 状态传递复杂 | 高 | 明确定义输入输出 Schema，单元测试覆盖 |
| 大数据内存溢出 | 高 | FilesystemMiddleware + 索引精准读取 |
| 重规划死循环 | 高 | max_replan_rounds + answered_questions 去重 |
| 模型迁移导入错误 | 高 | 逐步迁移，每次迁移后运行测试 |
| **继承关系重构影响范围大** | **高** | **先迁移再重构，保持向后兼容的别名导出** |
| Subgraph 调试困难 | 中 | 添加 execution_path 追踪，详细日志 |
| 洞察累积 LLM 决策不一致 | 中 | 提供清晰的处理规则，使用结构化输出 |
| 历史洞察处理建议解析失败 | 中 | 提供默认 KEEP 策略，确保不丢失洞察 |
| ReAct 重试死循环 | 中 | max_retries 限制 + ABORT 兜底 |

---

## 检查清单

### Phase 1 完成检查
- [ ] 所有 3 个 Tool 实现完成
- [ ] 数据模型符合规范
- [ ] Tool 单元测试通过

### Phase 2 完成检查
- [ ] SemanticParser Subgraph 正常运行
- [ ] Step1 + Step2 逻辑保持不变
- [ ] models 包迁移完成：
  - [ ] step1.py 从 core/models 迁移
  - [ ] step2.py 从 core/models 迁移
  - [ ] parse_result.py 从 core/models 迁移
- [ ] **继承关系统一**：
  - [ ] MeasureSpec 继承 MeasureField
  - [ ] DimensionSpec 继承 DimensionField
  - [ ] FilterSpec 继承 Filter
- [ ] QueryPipeline 正确集成所有 8 个中间件
- [ ] 字段映射使用现有 RAG+LLM 混合策略
- [ ] ReAct 错误处理正常工作：
  - [ ] RETRY 动作正确执行
  - [ ] CLARIFY 动作正确执行
  - [ ] ABORT 动作正确执行
  - [ ] 重试次数限制正常
- [ ] Observer 已移除，功能由 ReAct 替代

### Phase 3 完成检查
- [ ] InsightAgent Subgraph 正常运行
- [ ] models 包迁移完成（insight.py 从 core/models 迁移）
- [ ] EnhancedDataProfile 数据模型完成
- [ ] EnhancedDataProfiler 实现完成（含 Tableau Pulse 洞察）
- [ ] Director 支持按维度/异常精准分析
- [ ] 循环决策正确执行
- [ ] 渐进式洞察累积数据模型完成（HistoricalInsightAction, AnalystOutputWithHistory, DirectorOutputWithAccumulation）
- [ ] 分析师 Prompt 增强完成（输出历史洞察处理建议）
- [ ] 总监 Prompt 增强完成（执行洞察处理 + 生成最终摘要）
- [ ] ChunkAnalyzer 支持渐进式累积
- [ ] 洞察累积辅助模块完成（InsightAccumulator）
- [ ] Synthesizer 已移除，功能由总监 LLM 承担
- [ ] Replanner models 包迁移完成（replan.py 从 core/models 迁移）
- [ ] Replanner prompts 包结构完成

### Phase 4 完成检查
- [ ] 主工作流支持并行执行（通过 Send() API）
- [ ] 路由函数支持 Send() 返回值
- [ ] State 定义已更新（含 accumulated_insights + merge_insights reducer）
- [ ] 旧节点代码已删除
- [ ] 无 FanIn/FanOut 节点（LangGraph 自动处理）
- [ ] Replanner 正确设置 parallel_questions
- [ ] core/models 已迁移文件已删除：
  - [ ] data_model.py → infra/storage/
  - [ ] dimension_hierarchy.py → agents/dimension_hierarchy/models/
  - [ ] query_request.py → platforms/base.py
  - [ ] field_mapping.py → agents/field_mapper/models/mapping.py
  - [ ] parse_result.py → agents/semantic_parser/models/
  - [ ] step1.py → agents/semantic_parser/models/
  - [ ] step2.py → agents/semantic_parser/models/
  - [ ] insight.py → agents/insight/models/
  - [ ] replan.py → agents/replanner/models/
  - [ ] observer.py → 删除
- [ ] core/models 只保留 7 个文件（真正的核心层）：
  - [ ] enums.py
  - [ ] fields.py
  - [ ] filters.py
  - [ ] computations.py
  - [ ] query.py
  - [ ] execute_result.py
  - [ ] validation.py
- [ ] 核心层零依赖原则验证通过（core/ 不导入 platforms/、infra/、agents/）
- [ ] 继承关系统一（MeasureSpec → MeasureField, DimensionSpec → DimensionField, FilterSpec → Filter）
- [ ] infra 层清理完成：
  - [ ] `infra/config/tableau_env.py` 已删除
  - [ ] `infra/utils/` 目录已删除
  - [ ] `infra/monitoring/` 目录已删除（使用 LangSmith）
  - [ ] `infra/ai/rag/` 已迁移到 `agents/field_mapper/rag/`
- [ ] platforms/tableau 层清理完成：
  - [ ] `client.py` 已删除
  - [ ] `metadata.py` 已重命名为 `tableau_data_model.py`

### Phase 5 完成检查
- [ ] 所有测试通过
- [ ] Subgraph 测试通过
- [ ] QueryPipeline 测试通过（含所有 8 个中间件集成）
- [ ] 字段映射 RAG+LLM 混合策略测试通过
- [ ] EnhancedDataProfiler 测试通过
- [ ] 渐进式洞察累积测试通过（MERGE/REPLACE/KEEP/DISCARD）
- [ ] 并行执行测试通过（Send() API + 自动合并）
- [ ] 与旧架构行为一致

### Phase 6 完成检查
- [ ] 文档已更新
- [ ] 代码已清理
- [ ] 依赖已更新
