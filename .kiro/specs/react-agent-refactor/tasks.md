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

- [x] 创建 `orchestration/tools/` 目录结构
- [x] 创建 `base.py`:
  - 使用 `langchain_core.tools.BaseTool` 作为工具基类（LangChain 标准）
  - 定义 `ToolResult` 通用返回类型（包含 `success`, `data`, `error`）
  - 定义 `ToolError` 和 `ToolErrorCode` 错误模型
  - 实现 `format_tool_result()` 格式化函数
  - 实现 `safe_tool_execution` 和 `safe_async_tool_execution` 装饰器
- [x] 创建 `registry.py`:
  - 实现 `ToolRegistry` 单例类
  - 实现 `register_tool()` 注册函数
  - 实现 `get_tools_for_node()` 按节点获取工具
  - 定义 `NodeType` 枚举（SEMANTIC_PARSER, INSIGHT, REPLANNER）
- [x] 更新 `__init__.py` 导出所有工具

**验收标准**: 
- 使用 LangChain 标准 `BaseTool`（包含 `name`, `description`, `args_schema`）
- `ToolResult` 包含 `success`, `data`, `error` 字段
- 注册机制正常工作

---

### Task 1.2: 实现 map_fields Tool 包
**文件**: `orchestration/tools/map_fields/__init__.py`, `tool.py`, `models.py`

- [x] 创建 `orchestration/tools/map_fields/` 包目录
- [x] 创建 `models.py`:
  - `MapFieldsInput` 模型
  - `MapFieldsOutput` 模型
  - `FieldMappingError` 模型 (type: field_not_found | ambiguous_field | no_metadata | mapping_failed)
  - `FieldSuggestion` 模型（字段建议）
  - `MappingResultItem` 模型（单个字段映射结果）
- [x] 创建 `tool.py`:
  - 从 `agents/field_mapper/` 调用核心映射逻辑
  - 使用 `@tool` 装饰器定义 LangChain Tool (`map_fields`)
  - 实现 `map_fields_async` 异步版本
  - 保留 RAG + LLM 混合映射逻辑
  - 返回结构化错误
- [x] 更新 `__init__.py` 导出 Tool 和模型

**依赖**: Task 1.1

**验收标准**:
- 数据模型通过 Pydantic 验证
- 正常映射返回 `MappedQuery`
- 字段未找到返回 `FieldMappingError` with suggestions
- 单元测试覆盖正常/错误场景

---

### Task 1.3: 实现 build_query Tool 包
**文件**: `orchestration/tools/build_query/__init__.py`, `tool.py`, `models.py`

- [x] 创建 `orchestration/tools/build_query/` 包目录
- [x] 创建 `models.py`:
  - `BuildQueryInput` 模型
  - `BuildQueryOutput` 模型
  - `QueryBuildError` 模型 (type: invalid_computation | unsupported_operation)
- [x] 创建 `tool.py`:
  - 从 `nodes/query_builder/` 提取核心构建逻辑
  - 使用 `@tool` 装饰器定义 LangChain Tool
  - 保留现有 QueryBuilder 的计算转换逻辑
  - 返回结构化错误
- [x] 更新 `__init__.py` 导出 Tool 和模型

**依赖**: Task 1.1

**验收标准**:
- 数据模型通过 Pydantic 验证
- 正常构建返回 `QueryRequest`
- 无效计算返回 `QueryBuildError`
- 单元测试覆盖正常/错误场景

---

### Task 1.4: 实现 execute_query Tool 包
**文件**: `orchestration/tools/execute_query/__init__.py`, `tool.py`, `models.py`

- [x] 创建 `orchestration/tools/execute_query/` 包目录
- [x] 创建 `models.py`:
  - `ExecuteQueryInput` 模型
  - `ExecuteQueryOutput` 模型
  - `ExecutionError` 模型 (type: execution_failed | timeout | auth_error | invalid_query)
- [x] 创建 `tool.py`:
  - 从 `nodes/execute/` 提取核心执行逻辑
  - 使用 `@tool` 装饰器定义 LangChain Tool
  - 保留现有 VizQL API 调用逻辑
  - 集成 FilesystemMiddleware 大结果处理
  - 返回结构化错误
- [x] 更新 `__init__.py` 导出 Tool 和模型

**依赖**: Task 1.1

**验收标准**:
- 数据模型通过 Pydantic 验证
- 正常执行返回 `ExecuteResult`
- 大结果自动保存到 files
- 各类错误返回对应 `ExecutionError`
- 单元测试覆盖正常/错误场景

---

## Phase 2: SemanticParser Subgraph 实现

### Task 2.1: 创建 SemanticParser models 包 ✅
**文件**: `agents/semantic_parser/models/__init__.py`, `step1.py`, `step2.py`, `parse_result.py`, `observer.py`, `pipeline.py`, `react.py`

- [x] 创建 `agents/semantic_parser/models/` 包目录
- [x] 创建 `step1.py`: 
  - 从 `core/models/step1.py` 迁移 `Step1Output` 模型
  - **★设计决策**：Step1 直接使用核心层 `MeasureField`, `DimensionField`, `Filter`，不定义 `MeasureSpec`, `DimensionSpec`, `FilterSpec`
  - **★排序设计**：排序嵌入字段定义（`SortSpec` 在 `MeasureField.sort` 和 `DimensionField.sort`），`SemanticQuery` 使用 `get_sorts()` 方法
  - 更新导入路径
- [x] 创建 `step2.py`: 
  - 从 `core/models/step2.py` 迁移 `Step2Output` 模型
  - 更新导入路径
- [x] 创建 `observer.py`:
  - 从 `core/models/observer.py` 迁移 `ObserverOutput` 等模型
  - 更新导入路径
- [x] 创建 `parse_result.py`:
  - 从 `core/models/parse_result.py` 迁移 `SemanticParseResult`, `ClarificationQuestion` 模型
  - 更新导入路径
- [x] 创建 `pipeline.py`: 定义 `QueryResult`, `QueryError` 模型
- [x] 创建 `react.py`: 定义 `ReActThought`, `ReActAction`, `ReActObservation`, `ReActOutput` 模型
- [x] 更新 `__init__.py` 导出所有模型
- [x] 更新所有引用 `core/models/step1.py`、`core/models/step2.py`、`core/models/parse_result.py`、`core/models/observer.py` 的文件
- [x] 删除原 `core/models/step1.py`、`core/models/step2.py`、`core/models/parse_result.py`、`core/models/observer.py`
- [x] 更新 `core/models/__init__.py` 和 `core/__init__.py` 移除已迁移模型的导出

**模型迁移说明**:
- `core/models/step1.py` → `agents/semantic_parser/models/step1.py` ✅ 已完成
- `core/models/step2.py` → `agents/semantic_parser/models/step2.py` ✅ 已完成
- `core/models/parse_result.py` → `agents/semantic_parser/models/parse_result.py` ✅ 已完成
- `core/models/observer.py` → `agents/semantic_parser/models/observer.py` ✅ 已完成
- 迁移后已删除原文件 ✅

**★设计决策（用户确认）**:
1. **不使用继承**：Step1 直接使用核心层 `MeasureField`, `DimensionField`, `Filter`，不定义 `MeasureSpec`, `DimensionSpec`, `FilterSpec`
2. **排序嵌入字段**：`SortSpec` 嵌入 `MeasureField.sort` 和 `DimensionField.sort`，`SemanticQuery` 使用 `get_sorts()` 方法而非 `sorts` 字段
3. **不使用别名**：不使用 `ToolResult = ToolResponse` 等别名，必须正确重命名
4. **不需要兼容旧字段**：迁移后不保留向后兼容字段
5. **彻底解决循环导入**：不使用 `TYPE_CHECKING` 或 `Any` 类型绕过

**验收标准**:
- 所有模型通过 Pydantic 验证
- 模型定义与 design.md 一致
- **继承关系正确**：MeasureSpec → MeasureField, DimensionSpec → DimensionField, FilterSpec → Filter
- 无导入错误

---

### Task 2.2: 定义 SemanticParser 内部状态 ✅
**文件**: `agents/semantic_parser/state.py`

**★设计决策变更**：创建 `SemanticParserState` 继承自 `VizQLState`，遵循金字塔结构原则。

**金字塔结构**：
1. **核心层 (VizQLState)**：只包含高度抽象的核心类型（SemanticQuery, MappedQuery 等）
2. **Agent 层 (SemanticParserState)**：继承核心层，添加 Agent 特有的类型：
   - `semantic_parse_result`: SemanticParseResult（完整解析结果）
   - `step1_output`: Step1Output（意图 + what/where/how）
   - `step2_output`: Step2Output（计算推理）

**关键修改**：
- 从 `core/state.py` 移除 `SemanticParseResult` 导入（核心层不导入 Agent 层）
- 从 `VizQLState` 移除 `semantic_parse_result` 字段
- `SemanticParserState` 继承 `VizQLState` 并添加 Agent 特有字段
- `semantic_parser_node` 只返回核心层字段（semantic_query, restated_question 等）

**实现方式**：
- Subgraph 内部节点使用 `SemanticParserState` 类型
- 主工作流节点返回核心层字段到 `VizQLState`
- 无循环导入问题

- [x] 创建 `SemanticParserState(VizQLState)` 继承核心层状态
- [x] 添加 `semantic_parse_result` 字段（Agent 层特有）
- [x] 添加 `step1_output`, `step2_output` 字段（Subgraph 内部）
- [x] 从 `core/state.py` 移除 `SemanticParseResult` 导入
- [x] 更新 `semantic_parser_node` 只返回核心层字段

**依赖**: Task 2.1

**验收标准**:
- 金字塔结构正确：Agent 层继承核心层 ✅
- 无循环导入 ✅
- 类型安全（不使用 Any 或 TYPE_CHECKING 绕过）✅

---

### Task 2.3: 实现 Step1 节点 ✅
**文件**: `agents/semantic_parser/node.py`, `agents/semantic_parser/components/step1.py`

- [x] 提取现有 Step1 逻辑到独立模块
- [x] 实现 `step1_node(state: VizQLState) -> Dict`
- [x] 使用 `models.step1.Step1Output` 作为输出类型
- [x] 保持现有 Prompt 和输出格式
- [x] 更新 `current_stage` 为 `semantic_parser.step1`

**★实现说明**：
- `Step1Component` 在 `components/step1.py`：纯业务逻辑，不依赖 `VizQLState`
- `step1_node` 在 `node.py`：状态编排层，正确导入并使用 `VizQLState` 类型
- 这种分离避免了循环导入问题（`core/state.py` 导入 `agents/semantic_parser/models/`）

**依赖**: Task 2.1

**验收标准**:
- Step1 逻辑保持不变 ✅
- 输出 Step1Output 正确 ✅
- `step1_node` 使用 `VizQLState` 类型注解 ✅

---

### Task 2.4: 实现 Step2 节点 ✅
**文件**: `agents/semantic_parser/components/step2.py`, `agents/semantic_parser/node.py`

- [x] 提取现有 Step2 逻辑到独立模块
- [x] 实现 `step2_node(state: VizQLState) -> Dict`
- [x] 使用 `models.step2.Step2Output` 作为输出类型
- [x] 更新 `current_stage` 为 `semantic_parser.step2`
- [x] 保持现有 Prompt 和输出格式

**★实现说明**：
- `Step2Component` 在 `components/step2.py`：纯业务逻辑，不依赖 `VizQLState`
- `step2_node` 在 `node.py`：状态编排层，正确导入并使用 `VizQLState` 类型
- 这种分离避免了循环导入问题（`core/state.py` 导入 `agents/semantic_parser/models/`）
- Step2 只在 `step1_output.how_type != SIMPLE` 时调用

**依赖**: Task 2.1, Task 2.2

**验收标准**:
- Step2 逻辑保持不变 ✅
- 输出 Step2Output 正确 ✅
- `step2_node` 使用 `VizQLState` 类型注解 ✅

---

### Task 2.5: 实现 QueryPipeline（核心）✅
**文件**: `agents/semantic_parser/components/query_pipeline.py`

**重要**：这是语义解析的核心组件，保证执行顺序并集成中间件

- [x] 实现 `QueryPipeline` 类：
  - `__init__`: 接收 MiddlewareRunner 和 Runtime
  - `execute()`: 执行完整 Pipeline
  - `_execute_step1()`: 使用 `call_model_with_middleware`
  - `_execute_step2()`: 使用 `call_model_with_middleware`
  - `_execute_map_fields()`: 使用 `call_tool_with_middleware`（内部已有 RAG+LLM 混合策略）
  - `_execute_build_query()`: 纯逻辑，无中间件
  - `_execute_query()`: 使用 `call_tool_with_middleware`，处理 FilesystemMiddleware 返回的 Command
- [x] 使用 `models.pipeline.QueryResult`, `QueryError` 作为返回类型
- [x] 更新 `pipeline.py` 添加 `step1_output`, `step2_output`, `intent_type` 字段
- [x] 更新 `components/__init__.py` 导出 `QueryPipeline`

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

### Task 2.6: 实现 ReAct 错误处理 ✅
**文件**: `agents/semantic_parser/components/react_error_handler.py`, `agents/semantic_parser/prompts/react_error.py`

**说明**：当 QueryPipeline 中任意工具返回错误时，进入 ReAct 错误处理模式

- [x] 创建 `prompts/react_error.py`:
  - 实现 `ReActErrorHandlerPrompt` 类
  - 定义 `get_task()` 说明 ReAct 动作选项
  - 定义 `get_user_template()` 包含错误信息和重试次数
  - 使用 `ReActOutput` 作为输出模型
- [x] 创建 `components/react_error_handler.py`:
  - 使用 `models.react` 中的数据模型（ReActThought, ReActAction, ReActObservation, ReActOutput）
  - 实现 `ReActErrorHandler` 类：
    - `__init__`: 接收 LLM 和 max_retries
    - `handle_error()`: 处理工具错误
    - `_call_llm_for_analysis()`: 调用 LLM 生成 Thought + Action
    - `_create_max_retry_output()`: 创建最大重试次数达到时的 ABORT 输出
    - `_create_fallback_output()`: 创建 LLM 失败时的兜底输出
    - `create_observation()`: 从步骤执行结果创建 Observation
- [x] 更新 `prompts/__init__.py` 导出 ReActErrorHandlerPrompt
- [x] 更新 `components/__init__.py` 导出 ReActErrorHandler
- [x] 更新 `models/react.py` docstrings 为英文

**★关键设计决策（用户确认）**：
1. **RETRY 可以回到任意步骤**：`RetryTarget` 枚举定义 `step1`, `step2`, `map_fields`, `build_query`
2. **LLM 分析根因**：`ReActThought.root_cause` 字段让 LLM 识别哪个步骤导致了错误
3. **error_feedback 传递给重试步骤**：帮助重试步骤理解之前出了什么问题
4. **所有用户消息由 LLM 生成**：`user_message` 和 `clarification_question` 都由 LLM 生成
5. **兜底消息**：当 LLM 本身失败或达到最大重试次数时，使用简单的兜底消息（这是必要的设计权衡）

**ReAct 流程**：
- 错误发生 → LLM 分析根因 → 决定 RETRY/CLARIFY/ABORT
- RETRY: 回到指定步骤（step1/step2/map_fields/build_query），带上 error_feedback
- CLARIFY: 返回 LLM 生成的澄清问题给用户
- ABORT: 返回 LLM 生成的用户友好消息

**依赖**: Task 2.1, Task 2.5

**验收标准**:
- [x] ReAct 正确分析错误并决策
- [x] RETRY 能指定回到哪个步骤（step1/step2/map_fields/build_query）
- [x] RETRY 带有 error_feedback 帮助重试步骤理解问题
- [x] CLARIFY 能返回 LLM 生成的澄清问题给用户
- [x] ABORT 能返回 LLM 生成的友好错误信息
- [x] 重试次数限制正常工作

---

### Task 2.7: 实现外层决策逻辑 ✅
**文件**: `agents/semantic_parser/components/decision_handler.py`

**说明**：整合 QueryPipeline 和 ReAct 错误处理

- [x] 定义 `DecisionResult` 数据类（包含 success, query_result, action_type, clarification_question, user_message, retry_history）
- [x] 实现 `DecisionHandler` 类：
  - `__init__`: 接收 QueryPipeline, ReActErrorHandler, max_total_retries
  - `execute()`: 执行完整的错误处理循环
  - `_build_pipeline_context()`: 构建 pipeline 上下文供错误分析
  - `_prepare_retry_state()`: 准备重试状态（清除指定步骤及后续步骤的输出）
- [x] 更新 `QueryPipeline.execute()` 支持从指定步骤开始执行：
  - 检查 state 中是否有现有输出，有则跳过对应步骤
  - 支持 `error_feedback` 通过 state 传递给各步骤
- [x] 更新 `_execute_step1()` 支持 error_feedback 参数
- [x] 更新 `_execute_step2()` 支持 error_feedback 参数
- [x] 更新 `_execute_build_query()` 支持 error_feedback 参数
- [x] 更新 `Step2Component.execute()` 支持 error_feedback 参数
- [x] 更新 `components/__init__.py` 导出 DecisionHandler, DecisionResult

**错误处理流程**：
```
1. 执行 QueryPipeline
2. 成功 → 返回 DecisionResult(success=True)
3. 失败 → 调用 ReActErrorHandler
4. ABORT → 返回 DecisionResult(user_message=LLM生成的消息)
5. CLARIFY → 返回 DecisionResult(clarification_question=LLM生成的问题)
6. RETRY → 准备重试状态，回到步骤1
   - 清除 retry_from 及后续步骤的输出
   - 将 error_feedback 传递给重试步骤
```

**依赖**: Task 2.5, Task 2.6

**验收标准**:
- [x] Pipeline 执行正常
- [x] 错误触发 ReAct 处理
- [x] RETRY 能从指定步骤重新执行
- [x] error_feedback 正确传递给重试步骤
- [x] 最大重试次数限制正常工作

---

### Task 2.8: 创建 SemanticParser Subgraph ✅
**文件**: `agents/semantic_parser/subgraph.py`, `agents/semantic_parser/state.py`

**★重要设计变更**：使用 LangGraph 节点路由循环实现 ReAct 错误处理，而非 Python while 循环

- [x] 实现 `create_semantic_parser_subgraph() -> StateGraph`
- [x] 添加节点: step1, step2, pipeline, react_error_handler
- [x] 添加边 (LangGraph 节点路由循环):
  - START → step1
  - step1 → (conditional) → step2 | pipeline | END
  - step2 → (conditional) → pipeline | END
  - pipeline → (conditional) → react_error_handler | END
  - react_error_handler → (conditional) → step1 | step2 | pipeline | END
- [x] 实现路由函数:
  - `route_after_step1()`: step2 | pipeline | END
  - `route_after_step2()`: pipeline | END
  - `route_after_pipeline()`: react_error_handler | END
  - `route_after_react()`: step1 | step2 | pipeline | END (基于 retry_from)
- [x] 更新 `SemanticParserState` 添加 LangGraph 路由循环字段:
  - `retry_from: Optional[RetryTarget]` - 重试目标步骤
  - `error_feedback: Optional[str]` - 错误反馈
  - `react_action: Optional[ReActActionType]` - ReAct 动作类型
  - `pipeline_error: Optional[QueryError]` - Pipeline 错误
  - `retry_count: Optional[int]` - 重试次数
  - `clarification_question: Optional[str]` - 澄清问题 (CLARIFY)
  - `user_message: Optional[str]` - 用户消息 (ABORT)

**架构 (LangGraph 节点路由循环)**:
```
START → step1 → (conditional) → step2 | pipeline | END
step2 → (conditional) → pipeline | END
pipeline → (conditional) → react_error_handler | END
react_error_handler → (conditional) → step1 | step2 | pipeline | END
```

**ReAct 重试流程**:
1. pipeline 失败 → 路由到 react_error_handler
2. react_error_handler 分析错误，决定 RETRY from step2
3. 路由到 step2 (带 error_feedback)
4. step2 执行 → 路由到 pipeline
5. pipeline 成功 → END

**关键设计决策**:
- ReAct 错误处理是独立的 LangGraph 节点，不是 Python while 循环
- 重试循环通过 LangGraph 条件边实现
- State 携带 retry_from 和 error_feedback 用于重试逻辑
- 最大重试次数 (MAX_RETRIES=3) 在 route_after_react 中检查

**依赖**: Task 2.3, Task 2.4, Task 2.6, Task 2.7

**验收标准**:
- [x] Subgraph 编译成功
- [x] 正常流程正确执行 (step1 → step2 → pipeline → END)
- [x] 错误流程触发 ReAct 处理 (pipeline → react_error_handler)
- [x] RETRY 通过 LangGraph 路由回到正确步骤
- [x] CLARIFY/ABORT 正确结束并返回消息
- [x] 最大重试次数限制正常工作

---

### Task 2.9: 更新 SemanticParser Node 适配 ✅
**文件**: `agents/semantic_parser/node.py`

- [x] 修改 `semantic_parser_node()` 函数
- [x] 调用 Subgraph 而非直接执行
- [x] 映射 Subgraph 输出到主 State

**依赖**: Task 2.8

**验收标准**:
- Node 正确调用 Subgraph ✅
- State 输出字段正确填充 ✅

---

### Task 2.10: 移除 Observer 组件（由 ReAct 替代）✅
**文件**: 删除 `agents/semantic_parser/components/observer.py`, `prompts/observer.py`

- [x] 删除 Observer 相关文件
- [x] 更新 `__init__.py` 移除导出
- [x] 搜索并移除所有 Observer 相关导入
- [x] 确认 ReAct 错误处理已承担 Observer 功能

**依赖**: Task 2.8

**验收标准**:
- Observer 相关文件已删除 ✅
- 无残留导入错误 ✅
- ReAct 错误处理正常工作 ✅

---

## Phase 3: InsightAgent Subgraph 实现

### Task 3.1: 创建 InsightAgent models 包 ✅
**文件**: `agents/insight/models/__init__.py`, `profile.py`, `insight.py`, `director.py`, `analyst.py`

- [x] 创建 `agents/insight/models/` 包目录
- [x] 创建 `profile.py`: 定义 EnhancedDataProfile, ContributorAnalysis, ConcentrationRisk, PeriodChangeAnalysis, TrendAnalysis, DimensionIndex, AnomalyIndex 模型
- [x] 创建 `insight.py`: 
  - 从 `core/models/insight.py` 迁移 `Insight`, `InsightQuality` 模型
  - 更新导入路径
- [x] 创建 `director.py`: 定义 DirectorInput, DirectorDecision, DirectorOutputWithAccumulation 模型
- [x] 创建 `analyst.py`: 定义 AnalystOutputWithHistory, HistoricalInsightAction 模型
- [x] 更新 `__init__.py` 导出所有模型
- [x] 更新所有引用 `core/models/insight.py` 的文件
- [x] 删除原 `core/models/insight.py` 文件

**模型迁移说明**:
- `core/models/insight.py` → `agents/insight/models/insight.py` ✅ 已完成
- 迁移后已删除原文件 ✅

**规范要求**: 遵循 `PROMPT_AND_MODEL_GUIDE.md`

**验收标准**:
- 所有模型通过 Pydantic 验证 ✅
- 模型定义与 design.md 一致 ✅
- 无导入错误 ✅

---

### Task 3.2: 定义 Insight 内部状态 ✅
**文件**: `agents/insight/state.py`

- [x] 创建 `InsightState(TypedDict)`:
  - 输入: query_result, files, context
  - Phase 1: enhanced_profile, chunks
  - Phase 2: director_decision, current_action, current_target
  - Phase 3: analyzed_chunk_ids, analyst_output
  - Phase 4: accumulated_insights, final_summary, insight_result
  - 控制: iteration_count, should_continue, max_iterations, error_message

**依赖**: Task 3.1 ✅

**验收标准**:
- State 定义完整 ✅
- 类型注解正确，引用 models 包中的模型 ✅

---

### Task 3.3: 实现 EnhancedDataProfiler
**文件**: `agents/insight/components/profiler.py`

- [x] 增强 `DataProfiler` 类为 `EnhancedDataProfiler`
- [x] 实现 `_analyze_contributors()`: Top/Bottom 贡献者分析
- [x] 实现 `_analyze_concentration()`: 集中度风险检测
- [x] 实现 `_analyze_period_changes()`: 同环比分析
- [x] 实现 `_analyze_trends()`: 趋势检测
- [x] 实现 `_build_dimension_index()`: 维度索引构建
- [x] 实现 `_build_anomaly_index()`: 异常索引构建
- [x] 实现 `_recommend_strategy()`: 分块策略推荐
- [x] 使用 `models.profile` 中的数据模型

**依赖**: Task 3.1

**验收标准**:
- 生成 Tableau Pulse 风格洞察
- 索引构建正确
- 策略推荐合理

---

### Task 3.3.1: 合并 Profiler 和 StatisticalAnalyzer（P0 优化）✅
**文件**: `agents/insight/components/profiler.py`, `agents/insight/components/coordinator.py`

**问题**: `EnhancedDataProfiler` 和 `StatisticalAnalyzer` 存在严重功能重复：
- 趋势检测：两者都有 `_analyze_trends()` / `_detect_trend()`
- 异常检测：两者都有 `_build_anomaly_index()` / `_detect_anomalies()`
- 策略推荐：两者都有 `_recommend_strategy()` / `_recommend_chunking_strategy()`

**解决方案**: `EnhancedDataProfiler` 成为单一入口，内部委托给 `StatisticalAnalyzer` 和 `AnomalyDetector`

- [x] 重构 `EnhancedDataProfiler.__init__()`:
  - 接收 `StatisticalAnalyzer` 和 `AnomalyDetector` 作为构造函数依赖
  - 默认创建实例（向后兼容）
- [x] 重构 `EnhancedDataProfiler.profile()`:
  - 移除重复的 `_analyze_trends()` - 委托给 `StatisticalAnalyzer._detect_trend()`
  - 移除重复的异常检测 - 委托给 `AnomalyDetector.detect()`
  - 统一策略推荐（只保留一处）
- [x] 更新 `AnalysisCoordinator.analyze()`:
  - 只调用 `EnhancedDataProfiler.profile()` 而非 3 个独立组件
  - 移除对 `StatisticalAnalyzer.analyze()` 的直接调用
  - 移除对 `AnomalyDetector.detect()` 的直接调用
- [x] 添加 `get_insight_profile()` 方法:
  - 提供 `DataInsightProfile` 访问（向后兼容）
  - 内部委托给 `StatisticalAnalyzer.analyze()`
- [x] 更新 `analyze_streaming()` 方法:
  - 使用 `EnhancedDataProfiler` 作为单一入口
  - 移除对 `self.statistical_analyzer` 和 `self.anomaly_detector` 的直接调用
- [x] 更新所有中文注释和消息为英文

**设计决策**:
- 保留 `DataInsightProfile` 模型（用于分块策略）
- `EnhancedDataProfile` 用于 UI 展示，`DataInsightProfile` 用于内部分块逻辑
- 两者都需要，但通过 `EnhancedDataProfiler` 统一入口访问

**依赖**: Task 3.3

**验收标准**:
- [x] 无重复代码
- [x] `AnalysisCoordinator` 只调用一个入口
- [x] 所有现有功能保持不变
- [x] 导入验证通过
- [x] 功能测试通过

---

### Task 3.3.2: 从 Step2 获取同环比（P1 优化）- 不实现 ✅
**文件**: `agents/insight/components/profiler.py`, `agents/insight/state.py`

**问题**: Step2 已经做了表计算推理（YoY, MoM 等），Profiler 不应重复计算

**决定**: 不实现

**原因**:
1. Tableau 表计算已经能计算同环比，不需要在 Phase 1 重复计算
2. 如果用户需要同环比，SemanticParser 会生成相应的表计算
3. Phase 1 的目标是快速了解数据整体特征，不是做精确计算

**依赖**: Task 3.3.1

**验收标准**:
- ✅ 明确不需要实现，已记录原因

---

### Task 3.3.3: 鲁棒变点检测（P1 优化）✅
**文件**: `agents/insight/components/statistical_analyzer.py`, `agents/insight/models/insight.py`, `agents/insight/models/profile.py`, `agents/insight/components/profiler.py`

**问题**: 当前变点检测过于简单（基于滚动均值 + 2σ），容易误报

**解决方案**: 使用 `ruptures` 库的 PELT 算法，带简单回退

- [x] 添加 `ruptures` 到 `requirements.txt`（可选依赖）
- [x] 实现 `_detect_change_points_robust()`:
  - 尝试使用 `ruptures.Pelt` 算法
  - 如果 `ruptures` 未安装或失败，回退到当前简单方法
- [x] 更新 `_detect_trend()` 使用新的变点检测方法（在 `statistical_analyzer.py` 中）
- [x] 添加变点检测方法到 `TrendAnalysis` 模型（`change_point_method: Optional[str]`）
- [x] 添加变点检测方法到 `DataInsightProfile` 模型（`change_point_method: Optional[str]`）
- [x] 更新 `_convert_trend_from_insight_profile()` 传递 `change_point_method`

**依赖**: Task 3.3.1

**验收标准**:
- 有 `ruptures` 时使用 PELT 算法 ✅
- 无 `ruptures` 时优雅回退 ✅
- 变点检测更准确 ✅

---

### Task 3.3.4: 性能优化 - pandas 向量化（P0 优化） ✅
**文件**: `agents/insight/components/profiler.py`

**问题**: `_build_dimension_indices()` 使用 Python 循环，大数据集性能差

**解决方案**: 使用 pandas `groupby` 向量化操作

- [x] 重构 `_build_single_dimension_index()`:
  - 使用 `df.groupby(col).groups` 获取索引映射
  - 使用 `df[col].value_counts()` 获取计数
- [x] 重构 `_build_anomaly_index()`:
  - AnomalyDetector 已使用向量化的 IQR 计算
  - 使用 pandas 布尔索引替代循环
- [x] 添加性能基准测试
  - `test_large_data_perf.py` 验证 10 万行 0.2s 完成
- [x] 移除聚类分析（O(n²) 性能瓶颈）
  - 参考 Tableau Pulse，聚类不是核心洞察类型
  - 保留 Top Contributors、Pareto、Trend 等 O(n) 洞察

**依赖**: Task 3.3.1

**验收标准**:
- ✅ 大数据集（>10000 行）性能提升 >50%（实际：10万行 0.2s）
- ✅ 功能保持不变

---

### Task 3.3.5: 缓存机制（P1 优化）- 不实现 ✅
**文件**: `agents/insight/components/profiler.py`

**问题**: 相同数据集可能被多次分析，浪费计算资源

**决定**: 不实现查询结果缓存

**原因**:
1. 大数据序列化/反序列化比重新查询还慢（性能瓶颈）
2. 占用大量内存/存储空间
3. 数据时效性问题，重新查询能拿到最新数据
4. 每次用户问题不同，查询结果也不同，缓存命中率低

**替代方案**:
- 元数据（DataModel）已有 `DataModelCache` 持久化缓存
- 查询结果不缓存，需要时重新执行查询

**依赖**: Task 3.3.1

**验收标准**:
- ✅ 明确不需要实现，已记录原因

---

### Task 3.3.6: 相关性和季节性检测（P1 优化）- 不实现 ✅
**文件**: `agents/insight/components/profiler.py`, `agents/insight/models/profile.py`

**问题**: 当前缺少相关性分析和季节性检测

**决定**: 不实现

**原因**:
1. **相关性分析已有** - `StatisticalAnalyzer._calculate_correlations()` 已实现
2. **季节性检测价值不大**:
   - 需要足够长的时间序列（至少 2 个周期）
   - 大多数业务数据时间跨度不够
   - LLM 洞察场景更关心趋势方向，不是周期模式
   - Tableau Pulse 也没有专门的季节性洞察类型

**依赖**: Task 3.3.1

**验收标准**:
- ✅ 相关性分析已有
- ✅ 季节性检测明确不需要，已记录原因

---

### Task 3.4: 实现 Profiler 节点 ✅
**文件**: `agents/insight/nodes/profiler_node.py`

- [x] 实现 `profiler_node(state: InsightState) -> Dict`
- [x] 检测大文件引用，从 files 读取
- [x] 调用 EnhancedDataProfiler 生成画像
- [x] 基于画像推荐策略分块
- [x] 创建 `agents/insight/nodes/` 目录（节点函数与业务组件分离）
- [x] 更新 `nodes/__init__.py` 导出 `profiler_node`

**架构修正**:
- 节点函数放在 `nodes/` 目录，不是 `components/`
- `components/` 只放业务逻辑组件（EnhancedDataProfiler, SemanticChunker 等）
- `nodes/` 放 LangGraph 节点函数（状态编排层）

**聚类策略清理**:
- 移除 `BY_CLUSTER` 策略（依赖已删除的聚类计算）
- 新增 `BY_ANOMALY` 策略（隔离异常值优先分析，不依赖聚类）
- 更新 `ChunkingStrategy` 枚举
- 更新 `_recommend_strategy()` 逻辑
- 更新 `SemanticChunker._chunk_by_anomaly()` 实现

**实现说明**:
- `profiler_node` 是 LangGraph 节点函数，不是类
- 从 `state.query_result` 提取数据（支持 ExecuteResult 对象或 dict）
- 检测 FilesystemMiddleware 的大文件引用模式（`__file_reference__` 或 `file_path`）
- 使用 `EnhancedDataProfiler.profile()` 生成 Tableau Pulse 风格画像
- 使用 `SemanticChunker.chunk_by_strategy()` 基于推荐策略分块
- 返回 `{"enhanced_profile": ..., "chunks": ..., "error_message": ...}`

**依赖**: Task 3.3

**验收标准**:
- ✅ 小数据直接处理
- ✅ 大数据从 files 读取
- ✅ 画像和分块正确生成
- ✅ 节点函数与业务组件正确分离

---

### Task 3.5: 增强 AnalysisDirector ✅
**文件**: `agents/insight/components/director.py`

- [x] 使用 `models.director` 中的数据模型（DirectorInput, DirectorDecision, DirectorOutputWithAccumulation）
- [x] 更新总监 Prompt 展示 Tableau Pulse 洞察摘要
- [x] 实现 `decide()` 方法返回 `DirectorDecision`
- [x] 支持按维度/异常精准分析决策

**依赖**: Task 3.1

**验收标准**:
- 总监能看到画像摘要 ✅
- 决策更智能 ✅

---

### Task 3.6: 实现 Director 节点 ✅
**文件**: `agents/insight/nodes/director_node.py`

- [x] 实现 `director_node(state: InsightState) -> Dict`
- [x] 调用 AnalysisDirector.decide()
- [x] 更新 State 决策字段

**依赖**: Task 3.5

**验收标准**:
- 决策正确生成 ✅
- State 正确更新 ✅

---

### Task 3.7: 增强分析师 Prompt 支持历史洞察处理 ✅
**文件**: `agents/insight/prompts/analyst.py`

- [x] 使用 `models.analyst` 中的数据模型（AnalystOutputWithHistory, HistoricalInsightAction）
- [x] 创建 `AnalystPromptWithHistory` 类:
  - 增加历史洞察输入（带索引）
  - 增加历史洞察处理建议输出要求
  - 使用 `AnalystOutputWithHistory` 作为输出模型
- [x] 更新 `get_user_template()` 包含历史洞察
- [x] 更新 `get_task()` 说明处理建议要求

**依赖**: Task 3.1

**验收标准**:
- Prompt 包含历史洞察处理说明 ✅
- 输出模型正确 ✅

---

### Task 3.8: 增强总监 Prompt 支持洞察累积和最终综合 ✅
**文件**: `agents/insight/prompts/director.py`

- [x] 使用 `models.director` 中的数据模型（DirectorOutputWithAccumulation）
- [x] 创建 `DirectorPromptWithAccumulation` 类:
  - 增加分析师输出（新洞察 + 历史处理建议）
  - 增加洞察处理执行要求
  - 增加最终摘要生成要求（当 should_continue=False 时）
  - 使用 `DirectorOutputWithAccumulation` 作为输出模型
- [x] 更新 `get_user_template()` 包含分析师建议
- [x] 更新 `get_task()` 说明洞察处理执行要求和最终摘要生成

**依赖**: Task 3.1

**验收标准**:
- Prompt 包含洞察处理执行说明 ✅
- Prompt 包含最终摘要生成说明 ✅
- 输出模型正确 ✅

---

### Task 3.9: 更新 ChunkAnalyzer 支持渐进式累积 ✅
**文件**: `agents/insight/components/analyzer.py`

- [x] 更新 `analyze_chunk_with_analyst()`:
  - 使用 `AnalystPromptWithHistory`
  - 传入历史洞察（带索引）
  - 返回 `AnalystOutputWithHistory`
- [x] 实现 `analyze_chunk_with_history()`:
  - 使用 `ANALYST_PROMPT_WITH_HISTORY`
  - 传入历史洞察（带索引）
  - 返回 `AnalystOutputWithHistory`
- [x] 更新 `_parse_analyst_output_with_history()` 解析增强输出
- [x] 实现 `_parse_historical_action()` 解析历史洞察动作

**依赖**: Task 3.7, Task 3.8

**验收标准**:
- 分析师正确输出历史洞察处理建议 ✅
- 总监正确执行洞察处理 ✅
- 解析逻辑正确 ✅

---

### Task 3.10: 实现洞察累积辅助模块 ✅
**文件**: `agents/insight/components/accumulator.py`

**说明**：提供代码级别的洞察去重和累积辅助功能

- [x] 创建 `InsightAccumulator` 类:
  - `__init__`: 初始化累积器
  - `accumulate()`: 添加新洞察（带去重）
  - `get_accumulated()`: 获取累积洞察列表
  - `_is_duplicate()`: 基于标题的简单去重（作为 LLM 决策的兜底）
- [x] 实现 `format_insights_with_index()`: 格式化历史洞察（带索引）供 LLM 使用
- [x] 实现 `apply_analyst_actions()`: 应用分析师的处理建议（MERGE/REPLACE/KEEP/DISCARD）
- [x] 实现 `apply_director_actions()`: 应用总监的处理建议

**依赖**: Task 3.1

**验收标准**:
- 累积器正确管理洞察列表 ✅
- 格式化输出包含索引 ✅
- 处理建议应用正确 ✅

---

### Task 3.11: 实现 Analyzer 节点 ✅
**文件**: `agents/insight/nodes/analyzer_node.py`

- [x] 实现 `analyzer_node(state: InsightState) -> Dict`
- [x] 根据 decision.action 执行不同分析:
  - analyze_chunk: 分析指定分块 (`_analyze_chunk()`)
  - analyze_dimension: 按维度值精准读取 (`_analyze_dimension()`)
  - analyze_anomaly: 分析指定异常 (`_analyze_anomaly()`)
- [x] 实现 `_create_dimension_chunk()` 精准读取
- [x] 实现 `_create_anomaly_chunk()` 按行号读取

**依赖**: Task 3.6, Task 3.10

**验收标准**:
- 支持多种分析动作 ✅
- 精准读取正确 ✅

---

### Task 3.12: 创建 Insight Subgraph ✅
**文件**: `agents/insight/subgraph.py`

- [x] 实现 `create_insight_subgraph() -> StateGraph`
- [x] 添加节点: profiler, director, analyzer（无 synthesizer）
- [x] 添加边:
  - START → profiler
  - profiler → (conditional) → director | END
  - director → (conditional) → analyzer | END
  - analyzer → director (循环)
- [x] 实现路由函数:
  - `route_after_profiler()`: director | END
  - `route_after_director()`: analyzer | END
  - `route_after_analyzer()`: director (always)

**依赖**: Task 3.4, Task 3.6, Task 3.11

**验收标准**:
- Subgraph 编译成功 ✅
- 循环正确执行 ✅
- 总监决定停止时直接结束（无 Synthesizer）✅

---

### Task 3.13: 更新 Insight Node 适配 ✅
**文件**: `agents/insight/node.py`

- [x] 修改 `insight_node()` 函数
- [x] 调用 Subgraph 而非直接执行 (`_run_insight_subgraph()`)
- [x] 映射 Subgraph 输出到主 State:
  - `insights`: 累积洞察（结构化 Insight 对象列表）
  - `final_summary`: 总监输出的最终摘要（自然语言）
  - `insight_result`: InsightResult 包含 summary 和 findings
- [x] 使用 `accumulated_insights` 而非简单追加

**依赖**: Task 3.12

**验收标准**:
- Node 正确调用 Subgraph ✅
- State 输出字段正确填充 ✅
- 渐进式累积正确工作 ✅

---

### Task 3.14: 移除 Synthesizer 组件 ✅
**文件**: 删除 `agents/insight/components/synthesizer.py`

- [x] 删除 `InsightSynthesizer` 类（已删除 synthesizer.py 文件）
- [x] 更新 `components/__init__.py` 移除导出
- [x] 更新 `insight/__init__.py` 移除导出
- [x] 更新 `coordinator.py` 移除 Synthesizer 依赖
- [x] 将 `synthesize()` 方法移到 `InsightAccumulator` 中

**依赖**: Task 3.12

**验收标准**:
- Synthesizer 不再被使用 ✅
- `InsightAccumulator.synthesize()` 承担原 Synthesizer 的功能 ✅

---

### Task 3.15: 创建 Replanner models 包 ✅
**文件**: `agents/replanner/models/__init__.py`, `output.py`

- [x] 创建 `agents/replanner/models/` 包目录
- [x] 创建 `output.py`: 
  - 从 `core/models/replan.py` 迁移 `ExplorationQuestion` 模型
  - 从 `core/models/replan.py` 迁移 `ReplanDecision` 模型
  - 更新导入路径
- [x] 更新 `__init__.py` 导出模型
- [x] 更新所有引用 `core/models/replan.py` 的文件:
  - `orchestration/workflow/state.py`
  - `orchestration/workflow/routes.py`
  - `orchestration/workflow/printer.py`
  - `orchestration/workflow/factory.py`
  - `orchestration/workflow/executor.py`
  - `agents/replanner/prompt.py`
  - `agents/replanner/agent.py`
- [x] 更新 `core/models/__init__.py` 保持向后兼容导出

**模型迁移说明**:
- `core/models/replan.py` → `agents/replanner/models/output.py` ✅ 已完成
- 原文件已删除（不保留向后兼容）

**验收标准**:
- 模型通过 Pydantic 验证 ✅
- 模型定义与 design.md 一致 ✅
- 无导入错误 ✅

---

### Task 3.16: 更新 Replanner prompts 为包结构 ✅
**文件**: `agents/replanner/prompts/__init__.py`, `replanner.py`

- [x] 将 `agents/replanner/prompt.py` 改为 `agents/replanner/prompts/` 包
- [x] 创建 `prompts/replanner.py`: 移动 ReplannerPrompt
- [x] 创建 `prompts/__init__.py` 导出 Prompt
- [x] 更新 `agents/replanner/__init__.py` 从 `.prompts` 导入
- [x] 更新 `agents/replanner/agent.py` 从 `.prompts` 导入
- [x] 删除旧的 `prompt.py` 文件
- [x] 验证导入正常工作

**验收标准**:
- Prompt 包结构正确 ✅
- 导入路径更新 ✅

---

## Phase 4: 主工作流重构

### Task 4.1: 更新 State 定义 ✅
**文件**: `orchestration/workflow/state.py`

- [x] 移除不再需要的字段:
  - `correction_count`, `correction_exhausted`
  - `field_mapper_complete`, `query_builder_complete`, `execute_complete`
- [x] 添加新字段:
  - `tool_observations: List[Dict[str, Any]]`
  - `enhanced_profile: Optional[EnhancedDataProfile]`
- [x] 添加并行执行相关字段:
  - `parallel_questions: List[str]` - 待并行执行的问题列表
  - `accumulated_insights: Annotated[List[Insight], merge_insights]` - 渐进式累积洞察（使用自定义 reducer）
- [x] 实现 `merge_insights` reducer 函数
- [x] 更新 `query_result` 类型注解支持文件引用
- [x] 简化节点完成标志

**验收标准**:
- State 定义与 design.md 一致 ✅
- 并行执行字段正确定义 ✅
- `merge_insights` reducer 正确合并洞察列表 ✅
- 无类型错误 ✅

---

### Task 4.2: 简化 routes.py ✅
**文件**: `orchestration/workflow/routes.py`

- [x] 从 4 个路由函数减少到 2 个:
  - `route_after_semantic_parser()`: 决定 insight | end
  - `route_after_replanner()`: 决定 semantic_parser | end（支持 Send() 并行）
- [x] 移除路由函数:
  - `route_after_execute()`
  - `route_after_self_correction()`
- [x] 更新 `route_after_replanner()` 支持并行执行:
  - `len(exploration_questions) > 1` → 返回 `List[Send]` 并行分发
  - `len(exploration_questions) == 1` → semantic_parser（串行）
  - `should_replan=False` → end

**验收标准**:
- 路由函数支持 Send() API 并行执行 ✅
- 路由逻辑与 design.md 一致 ✅
- 无 FanIn/FanOut 节点 ✅

---

### Task 4.3: 重构 factory.py ✅
**文件**: `orchestration/workflow/factory.py`

- [x] 从 7 节点减少到 3 节点:
  - `semantic_parser` (Subgraph)
  - `insight` (Subgraph)
  - `replanner` (单节点)
- [x] 移除节点:
  - `field_mapper`, `query_builder`, `execute`, `self_correction`
  - `fanout`, `fanin`（不需要，LangGraph 自动处理）
- [x] 更新边定义:
  - START → semantic_parser
  - semantic_parser → insight
  - insight → replanner
  - replanner → (conditional) → semantic_parser | END
  - 并行执行通过 Send() API 在 route_after_replanner 中处理
- [x] 更新 `create_workflow()` 函数

**依赖**: Task 2.8, Task 3.11, Task 4.1, Task 4.2

**验收标准**:
- 工作流支持并行执行（通过 Send() API）✅
- 无 FanIn/FanOut 节点 ✅
- 边定义正确 ✅
- 编译成功 ✅

---

### Task 4.4: 移除 SelfCorrection 节点 ✅
**文件**: 删除 `nodes/self_correction/` 目录

- [x] 删除 `nodes/self_correction/` 整个目录
- [x] 更新 `nodes/__init__.py` 移除导出
- [x] 搜索并移除所有 SelfCorrection 相关导入

**依赖**: Task 4.3

**验收标准**:
- SelfCorrection 目录已删除 ✅
- 无残留导入错误 ✅

---

### Task 4.5: 清理旧节点代码 ✅
**文件**: `nodes/field_mapper/`, `nodes/query_builder/`, `nodes/execute/`

- [x] 删除 `nodes/field_mapper/` 目录 (逻辑已移到 Tool) - 已在 Task 4.4 中删除
- [x] 删除 `nodes/query_builder/` 目录 (逻辑已移到 Tool)
- [x] 删除 `nodes/execute/` 目录 (逻辑已移到 Tool)
- [x] 更新 `nodes/__init__.py`
- [x] 最终删除整个 `nodes/` 目录
- [x] 更新 `orchestration/tools/build_query/tool.py` 直接使用 `TableauQueryBuilder`
- [x] 更新 `orchestration/tools/execute_query/tool.py` 直接使用 `VizQLClient`

**依赖**: Task 1.2, Task 1.3, Task 1.4

**验收标准**:
- 旧节点代码已删除 ✅
- 无残留导入错误 ✅
- Tool 文件直接使用底层实现 ✅

---

### Task 4.6: 更新 Replanner 节点支持并行 ✅
**文件**: `orchestration/workflow/factory.py` (replanner_node 定义在 factory.py 中)

- [x] 更新 `replanner_node()` 设置 `parallel_questions`:
  - 当 `len(exploration_questions) > 1` 时，设置 `parallel_questions`
  - 当 `len(exploration_questions) == 1` 时，设置 `question`（串行执行）
- [x] 添加并行执行日志

**依赖**: Task 4.1

**验收标准**:
- Replanner 正确设置并行问题列表 ✅
- 单问题时保持串行执行 ✅

---

### Task 4.7: 清理 core/models 中已迁移的文件 ✅
**文件**: `core/models/`

**★设计决策审查（2024-01 重新评估）**:

经过仔细分析设计文档的"核心层零依赖原则"和"金字塔继承结构"，对原计划进行了修订：

| 原计划 | 最终决策 | 原因 |
|--------|---------|------|
| `query_request.py` → `platforms/base.py` | **保留在 core/models/** | 平台无关的抽象基类，依赖方向应是 platforms/ → core/ |
| `data_model.py` → `infra/storage/` | **迁移到 infra/storage/** | 数据源元数据，不是平台无关抽象，已迁移 |
| `dimension_hierarchy.py` → `agents/` | **迁移到 agents/dimension_hierarchy/models/** | Agent 特有输出，已迁移 |
| `field_mapping.py` → `agents/` | **迁移到 agents/field_mapper/models/** | 字段映射 Agent 的输出模型，已迁移 |

**已完成的迁移（Phase 2/3/4）**:
- [x] `core/models/step1.py` → `agents/semantic_parser/models/step1.py` ✅
- [x] `core/models/step2.py` → `agents/semantic_parser/models/step2.py` ✅
- [x] `core/models/parse_result.py` → `agents/semantic_parser/models/parse_result.py` ✅
- [x] `core/models/observer.py` → 已删除（由 ReAct 替代）✅
- [x] `core/models/insight.py` → `agents/insight/models/insight.py` ✅
- [x] `core/models/replan.py` → `agents/replanner/models/output.py` ✅
- [x] `core/models/data_model.py` → `infra/storage/data_model.py` ✅
- [x] `core/models/dimension_hierarchy.py` → `agents/dimension_hierarchy/models/hierarchy.py` ✅
- [x] `core/models/field_mapping.py` → `agents/field_mapper/models/mapping.py` ✅
- [x] `core/models/query_request.py` → 已删除（VizQLQueryRequest 独立定义）✅

**保留在 core/models/ 的文件（共 7 个）**:
- [x] `enums.py` - 语义层枚举（IntentType, CalcType, FilterType 等）
- [x] `fields.py` - 字段抽象（DimensionField, MeasureField, SortSpec）
- [x] `filters.py` - 过滤器抽象（Filter 及其子类）
- [x] `computations.py` - 计算抽象（Computation, TableCalc, LODExpression）
- [x] `query.py` - SemanticQuery（语义解析核心输出）
- [x] `execute_result.py` - 执行结果抽象（ExecuteResult, ColumnMetadata）
- [x] `validation.py` - 验证结果抽象（ValidationResult, ValidationError）

**核心层设计原则确认**:
1. ✅ **零依赖原则**：core/models/ 不导入 platforms/、infra/、agents/
2. ✅ **语义抽象**：所有保留的模型都是平台无关的语义概念
3. ✅ **金字塔结构**：Agent 层模型（Step1Output 等）继承/组合核心层模型

**验收标准**:
- [x] Agent 特有模型已迁移到各自 Agent 的 models/ 目录
- [x] 核心层只保留平台无关的语义抽象（7 个文件）
- [x] 无导入错误
- [x] 核心层零依赖原则验证通过

---

### Task 4.7.1: 修复延迟导入和 TYPE_CHECKING 问题 ✅
**文件**: 多个文件

**问题说明**:
根据用户要求，不允许使用以下模式来解决循环导入问题：
1. **延迟导入（函数内导入）** - 所有导入必须在模块顶层
2. **TYPE_CHECKING** - 不允许使用 `if TYPE_CHECKING:` 模式

**已修复的文件**:
- [x] `tableau_assistant/src/orchestration/tools/map_fields/tool.py`
  - 移除 `_map_fields_impl()` 中的延迟导入（lines 125-127）
  - 将 `SemanticQuery`, `MappedQuery`, `FieldMapping`, `FieldMapperNode` 导入移到顶层
- [x] `tableau_assistant/src/agents/field_mapper/node.py`
  - 移除 `field_mapper_node()` 中的延迟导入
  - 移除 `_get_field_mapper()` 中的延迟导入
  - 将 `MappedQuery`, `FieldMapping`, `SemanticQuery`, `SemanticMapper`, `FieldIndexer` 导入移到顶层
- [x] `tableau_assistant/src/infra/storage/data_model_loader.py`
  - 移除 `TYPE_CHECKING` 模式（lines 21-24）
  - 将 `DataModel`, `TableauAuthContext` 导入移到顶层
- [x] `tableau_assistant/src/infra/storage/data_model_cache.py`
  - 移除 `TYPE_CHECKING` 模式（lines 27-30）
  - 移除 `_get_from_cache()` 中的延迟导入
  - 将 `DataModel`, `DataModelLoader`, `BaseStore` 导入移到顶层
- [x] `tableau_assistant/src/platforms/tableau/metadata.py`
  - 移除 `get_datasource_metadata()` 中的延迟导入（lines 705-710）
  - 将 `DataModel`, `FieldMetadata`, `LogicalTable`, `LogicalTableRelationship` 导入移到顶层

**验收标准**:
- [x] 所有文件无延迟导入（函数内导入）
- [x] 所有文件无 `TYPE_CHECKING` 模式
- [x] 所有文件通过诊断检查（无导入错误）
- [x] 循环导入问题通过正确的模块依赖顺序解决

---

### Task 4.8: 清理 infra 层不需要的文件
**文件**: `infra/config/`, `infra/utils/`, `infra/ai/rag/`, `infra/monitoring/`

**删除的目录/文件**:
- [x] 删除 `infra/config/tableau_env.py`（多环境配置不需要）- **已删除**
- [x] 删除 `infra/utils/` 整个目录
  - [x] `conversation.py` 中的 `trim_answered_questions()` 移到使用处（`agents/replanner/utils.py`）
- [x] 删除 `infra/monitoring/` 整个目录（使用 LangSmith 进行监控）
  - [x] 删除 `callbacks.py`（SQLiteTrackingCallback 不再需要）
  - [x] 删除 `__init__.py`

**迁移的目录**:
- [x] 迁移 `infra/ai/rag/` → `agents/field_mapper/rag/`（RAG 是字段映射 Agent 的实现细节）- **已完成**
  - [x] 迁移 `assembler.py`
  - [x] 迁移 `cache.py`
  - [x] 迁移 `dimension_pattern.py`
  - [x] 迁移 `embeddings.py`
  - [x] 迁移 `field_indexer.py`
  - [x] 迁移 `models.py`
  - [x] 迁移 `observability.py`
  - [x] 迁移 `reranker.py`
  - [x] 迁移 `retriever.py`
  - [x] 迁移 `semantic_mapper.py`

**更新导入路径**:
- [x] 更新所有引用 `infra/ai/rag/` 的文件，改为 `agents/field_mapper/rag/`
- [x] 更新 `infra/config/__init__.py` 移除 `tableau_env` 导出 - **已删除 tableau_env**
- [x] 更新 `infra/__init__.py` 移除 `utils` 和 `monitoring` 导出
- [x] 移除所有引用 `infra/monitoring/` 的代码

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
- [x] 删除 `platforms/tableau/client.py`（薄包装器不需要，直接使用 vizql_client.py）

**重命名的文件**:
- [x] 重命名 `platforms/tableau/metadata.py` → `platforms/tableau/tableau_data_model.py`
  - [x] 更新文件内的 docstring 说明
  - [x] 更新所有引用 `metadata.py` 的文件

**更新导入路径**:
- [x] 更新所有引用 `platforms/tableau/client.py` 的文件，改为直接使用 `vizql_client.py`
- [x] 更新所有引用 `platforms/tableau/metadata.py` 的文件

**依赖**: Task 4.8

**验收标准**:
- `client.py` 已删除
- `metadata.py` 已重命名为 `tableau_data_model.py`
- 无导入错误

---

## Phase 5: 测试与验证

### Task 5.1: Tool 单元测试 ✅
**文件**: `tests/orchestration/tools/`

- [x] 创建 `test_map_fields_tool.py`:
  - 测试正常映射
  - 测试 field_not_found 错误
  - 测试 ambiguous_field 错误
- [x] 创建 `test_build_query_tool.py`:
  - 测试正常构建
  - 测试 invalid_computation 错误
  - 测试 unsupported_operation 错误
- [x] 创建 `test_execute_query_tool.py`:
  - 测试正常执行
  - 测试各类错误

**验收标准**:
- 所有 Tool 测试通过 ✅
- 覆盖正常和错误场景 ✅

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
├── Task 3.3: EnhancedDataProfiler (依赖 3.1) ✅
│   ├── Task 3.3.1: 合并 Profiler 和 StatisticalAnalyzer (依赖 3.3) ✅ P0 优化
│   ├── Task 3.3.2: 从 Step2 获取同环比 (依赖 3.3.1) ★P1 优化
│   ├── Task 3.3.3: 鲁棒变点检测 ruptures (依赖 3.3.1) ★P1 优化
│   ├── Task 3.3.4: 性能优化 pandas 向量化 (依赖 3.3.1) ★P0 优化
│   ├── Task 3.3.5: 缓存机制 (依赖 3.3.1) ★P1 优化
│   └── Task 3.3.6: 相关性和季节性检测 (依赖 3.3.1) ★P1 优化
├── Task 3.4: Profiler 节点 (依赖 3.3.1)
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
| Phase 3 | 22 | 5-6 天 | InsightAgent Subgraph + models 包迁移 + 渐进式累积 + Profiler 优化（6 个子任务） |
| Phase 4 | 9 | 2.5-3 天 | 主工作流重构 + 并行执行 + core/models 大规模迁移 + infra/platforms 清理 |
| Phase 5 | 7 | 3-3.5 天 | 测试覆盖（含 ReAct + 渐进式累积测试） |
| Phase 6 | 4 | 0.5-1 天 | 文档更新 |
| **总计** | **56** | **15-20 天** | |

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
| **ruptures 库兼容性** | **低** | **提供简单回退方案** |
| **缓存内存占用** | **低** | **LRU 策略 + 可配置大小限制** |
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
- [x] InsightAgent Subgraph 正常运行
- [x] models 包迁移完成（insight.py 从 core/models 迁移）
- [x] EnhancedDataProfile 数据模型完成
- [x] EnhancedDataProfiler 实现完成（含 Tableau Pulse 洞察）
- [x] **Profiler 优化完成（Task 3.3.x）**：
  - [x] Task 3.3.1: Profiler 和 StatisticalAnalyzer 合并完成
  - [x] Task 3.3.2: 从 Step2 获取同环比完成（决定不实现）
  - [x] Task 3.3.3: 鲁棒变点检测（ruptures）完成
  - [x] Task 3.3.4: pandas 向量化性能优化完成
  - [x] Task 3.3.5: 缓存机制完成（决定不实现）
  - [x] Task 3.3.6: 相关性和季节性检测完成（决定不实现）
- [x] Director 支持按维度/异常精准分析
- [x] 循环决策正确执行
- [x] 渐进式洞察累积数据模型完成（HistoricalInsightAction, AnalystOutputWithHistory, DirectorOutputWithAccumulation）
- [x] 分析师 Prompt 增强完成（输出历史洞察处理建议）
- [x] 总监 Prompt 增强完成（执行洞察处理 + 生成最终摘要）
- [x] ChunkAnalyzer 支持渐进式累积
- [x] 洞察累积辅助模块完成（InsightAccumulator）
- [x] Synthesizer 已移除，功能由总监 LLM 承担
- [ ] Replanner models 包迁移完成（replan.py 从 core/models 迁移）
- [ ] Replanner prompts 包结构完成

### Phase 4 完成检查
- [ ] 主工作流支持并行执行（通过 Send() API）
- [ ] 路由函数支持 Send() 返回值
- [ ] State 定义已更新（含 accumulated_insights + merge_insights reducer）
- [ ] 旧节点代码已删除
- [ ] 无 FanIn/FanOut 节点（LangGraph 自动处理）
- [ ] Replanner 正确设置 parallel_questions
- [x] core/models 已迁移文件已删除：
  - [x] data_model.py → infra/storage/
  - [x] dimension_hierarchy.py → agents/dimension_hierarchy/models/
  - [x] query_request.py → 已删除（VizQLQueryRequest 独立定义）
  - [x] field_mapping.py → agents/field_mapper/models/mapping.py
  - [x] parse_result.py → agents/semantic_parser/models/
  - [x] step1.py → agents/semantic_parser/models/
  - [x] step2.py → agents/semantic_parser/models/
  - [x] insight.py → agents/insight/models/
  - [x] replan.py → agents/replanner/models/
  - [x] observer.py → 删除
- [x] core/models 只保留 7 个文件（真正的核心层）：
  - [x] enums.py
  - [x] fields.py
  - [x] filters.py
  - [x] computations.py
  - [x] query.py
  - [x] execute_result.py
  - [x] validation.py
- [x] 核心层零依赖原则验证通过（core/ 不导入 platforms/、infra/、agents/）
- [ ] 继承关系统一（MeasureSpec → MeasureField, DimensionSpec → DimensionField, FilterSpec → Filter）
- [x] 延迟导入和 TYPE_CHECKING 问题已修复（Task 4.7.1）：
  - [x] `orchestration/tools/map_fields/tool.py` - 延迟导入已移到顶层
  - [x] `agents/field_mapper/node.py` - 延迟导入已移到顶层
  - [x] `infra/storage/data_model_loader.py` - TYPE_CHECKING 已移除
  - [x] `infra/storage/data_model_cache.py` - TYPE_CHECKING 和延迟导入已移除
  - [x] `platforms/tableau/metadata.py` - 延迟导入已移到顶层
- [ ] infra 层清理完成：
  - [x] `infra/config/tableau_env.py` 已删除
  - [x] `infra/utils/` 目录已删除
  - [ ] `infra/monitoring/` 目录已删除（使用 LangSmith）
  - [ ] `infra/ai/rag/` 已迁移到 `agents/field_mapper/rag/`
- [x] platforms/tableau 层清理完成：
  - [x] `client.py` 已删除
  - [x] `metadata.py` 已重命名为 `tableau_data_model.py`

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
