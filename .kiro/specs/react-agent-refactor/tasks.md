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
- 使用自定义 StateGraph + MiddlewareRunner 实现 ReAct 循环

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

### Task 1.2: 定义 Tool 输入输出数据模型
**文件**: `orchestration/tools/models.py`

- [ ] 创建 `MapFieldsInput`, `MapFieldsOutput` 模型
- [ ] 创建 `FieldMappingError` 模型 (type: field_not_found | ambiguous_field)
- [ ] 创建 `BuildQueryInput`, `BuildQueryOutput` 模型
- [ ] 创建 `QueryBuildError` 模型 (type: invalid_computation | unsupported_operation)
- [ ] 创建 `ExecuteQueryInput`, `ExecuteQueryOutput` 模型
- [ ] 创建 `ExecutionError` 模型 (type: execution_failed | timeout | auth_error | invalid_query)

**规范要求**: 遵循 `PROMPT_AND_MODEL_GUIDE.md`

**验收标准**: 
- 所有模型通过 Pydantic 验证
- JSON Schema 输出符合规范

---

### Task 1.3: 实现 map_fields Tool
**文件**: `orchestration/tools/map_fields_tool.py`

- [ ] 从 `agents/field_mapper/` 提取核心映射逻辑
- [ ] 使用 `@tool` 装饰器定义 LangChain Tool
- [ ] 实现 RAG + LLM 混合映射逻辑
- [ ] 返回结构化错误:
  - `field_not_found`: 字段不存在，提供 suggestions
  - `ambiguous_field`: 多个匹配，需要澄清

**依赖**: Task 1.1, Task 1.2

**验收标准**:
- 正常映射返回 `MappedQuery`
- 字段未找到返回 `FieldMappingError` with suggestions
- 单元测试覆盖正常/错误场景

---

### Task 1.4: 实现 build_query Tool
**文件**: `orchestration/tools/build_query_tool.py`

- [ ] 从 `nodes/query_builder/` 提取核心构建逻辑
- [ ] 使用 `@tool` 装饰器定义 LangChain Tool
- [ ] 保留现有 QueryBuilder 的计算转换逻辑
- [ ] 返回结构化错误:
  - `invalid_computation`: 计算定义无效
  - `unsupported_operation`: 平台不支持该操作

**依赖**: Task 1.1, Task 1.2

**验收标准**:
- 正常构建返回 `QueryRequest`
- 无效计算返回 `QueryBuildError`
- 单元测试覆盖正常/错误场景

---

### Task 1.5: 实现 execute_query Tool
**文件**: `orchestration/tools/execute_query_tool.py`

- [ ] 从 `nodes/execute/` 提取核心执行逻辑
- [ ] 使用 `@tool` 装饰器定义 LangChain Tool
- [ ] 保留现有 VizQL API 调用逻辑
- [ ] 集成 FilesystemMiddleware 大结果处理
- [ ] 返回结构化错误:
  - `execution_failed`: 查询执行失败
  - `timeout`: 查询超时
  - `auth_error`: 认证失败
  - `invalid_query`: 查询语法错误

**依赖**: Task 1.1, Task 1.2

**验收标准**:
- 正常执行返回 `ExecuteResult`
- 大结果自动保存到 files
- 各类错误返回对应 `ExecutionError`
- 单元测试覆盖正常/错误场景

---

## Phase 2: SemanticParser Subgraph 实现

### Task 2.1: 定义 SemanticParser 内部状态
**文件**: `agents/semantic_parser/state.py`

- [ ] 创建 `SemanticParserState(TypedDict)`:
  - 输入字段: question, history, data_model
  - Step1 输出: step1_output
  - Step2 输出: step2_output
  - ReAct 循环: semantic_query, react_observations, iteration_count
  - 最终输出: mapped_query, vizql_query, query_result, error

**验收标准**:
- State 定义完整
- 类型注解正确

---

### Task 2.2: 实现 Step1 节点
**文件**: `agents/semantic_parser/components/step1.py`

- [ ] 提取现有 Step1 逻辑到独立模块
- [ ] 实现 `step1_node(state: SemanticParserState) -> Dict`
- [ ] 保持现有 Prompt 和输出格式

**验收标准**:
- Step1 逻辑保持不变
- 输出 Step1Output 正确

---

### Task 2.3: 实现 Step2 节点
**文件**: `agents/semantic_parser/components/step2.py`

- [ ] 提取现有 Step2 逻辑到独立模块
- [ ] 实现 `step2_node(state: SemanticParserState) -> Dict`
- [ ] 保持现有 Prompt 和输出格式

**验收标准**:
- Step2 逻辑保持不变
- 输出 Step2Output 正确

---

### Task 2.4: 创建 ReAct Prompt 模板
**文件**: `agents/semantic_parser/prompts/react.py`

- [ ] 创建 `ReActDecisionPrompt` 类
- [ ] 实现 4 段式结构: role, task, domain_knowledge, constraints
- [ ] 定义决策规则：success → insight, can_retry → retry, needs_clarification → ask user
- [ ] 定义错误处理策略

**规范要求**: 遵循 `PROMPT_AND_MODEL_GUIDE.md` 4 段式结构

**验收标准**:
- Prompt 包含决策规则说明
- 包含错误处理指导
- 包含 max_retries 限制说明

---

### Task 2.5: 实现 QueryPipeline（核心）
**文件**: `agents/semantic_parser/components/query_pipeline.py`

**重要**：这是语义解析的核心组件，保证执行顺序并集成中间件

- [ ] 定义 `QueryResult` 数据类（success, error）
- [ ] 定义 `QueryError` 数据类（stage, type, message）
- [ ] 实现 `QueryPipeline` 类：
  - `__init__`: 接收 MiddlewareRunner 和 Runtime
  - `execute()`: 执行完整 Pipeline
  - `_execute_step1()`: 使用 `call_model_with_middleware`
  - `_execute_step2()`: 使用 `call_model_with_middleware`
  - `_execute_map_fields()`: 使用 `call_tool_with_middleware`（内部已有 RAG+LLM 混合策略）
  - `_execute_build_query()`: 纯逻辑，无中间件
  - `_execute_query()`: 使用 `call_tool_with_middleware`，处理 FilesystemMiddleware 返回的 Command

**字段映射说明**：
- `map_fields` 封装现有 `FieldMapperNode`，保留完整的 RAG+LLM 混合策略
- 映射策略：缓存 → RAG (confidence >= 0.9 直接返回) → LLM Fallback → LLM Only
- 映射失败（字段不存在/无权限）直接返回错误，不做重试（数据问题，重试无意义）

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

**依赖**: Task 1.3, Task 1.4, Task 1.5

**验收标准**:
- Pipeline 保证执行顺序：Step1 → Step2 → MapFields → BuildQuery → Execute
- 字段映射使用现有 RAG+LLM 混合策略（无额外重试逻辑）
- 中间件正确集成（特别是 FilesystemMiddleware 大结果处理）
- 返回结构化 QueryResult

---

### Task 2.6: 实现外层决策逻辑
**文件**: `agents/semantic_parser/components/decision_handler.py`

**说明**：由于字段映射已有完整的 RAG+LLM 混合策略，外层不需要复杂的 ReAct 决策循环

- [ ] 定义 `DecisionState(TypedDict)` 状态
- [ ] 实现 `pipeline_node`: 调用 QueryPipeline
- [ ] 实现 `handle_result`: 根据 QueryResult 处理结果
  - success=True → 结束，进入 Insight
  - error → 返回错误信息给用户
- [ ] 实现 `route_after_pipeline` 路由函数
- [ ] 创建 `create_semantic_parser_graph()` 构建 StateGraph
- [ ] 实现 `execute_semantic_parser()` 同步执行函数
- [ ] 实现 `stream_semantic_parser()` 流式执行函数
  - 使用 `astream_events` 获取 token 级别流式输出

**依赖**: Task 2.5, Task 2.4

**验收标准**:
- Pipeline 执行正常
- 错误直接返回给用户（无重试循环）
- Token 级别流式输出正常工作

---

### Task 2.7: 创建 SemanticParser Subgraph
**文件**: `agents/semantic_parser/subgraph.py`

- [ ] 实现 `create_semantic_parser_subgraph() -> StateGraph`
- [ ] 添加节点: step1, step2, react_decision_loop
- [ ] 添加边:
  - START → step1
  - step1 → (conditional) → step2 | react_decision_loop | END
  - step2 → react_decision_loop
  - react_decision_loop → END
- [ ] 实现 `route_after_step1()` 路由函数

**依赖**: Task 2.2, Task 2.3, Task 2.6

**验收标准**:
- Subgraph 编译成功
- 流程正确执行

---

### Task 2.8: 更新 SemanticParser Node 适配
**文件**: `agents/semantic_parser/node.py`

- [ ] 修改 `semantic_parser_node()` 函数
- [ ] 调用 Subgraph 而非直接执行
- [ ] 映射 Subgraph 输出到主 State

**依赖**: Task 2.7

**验收标准**:
- Node 正确调用 Subgraph
- State 输出字段正确填充

---

### Task 2.9: 移除 Observer 组件
**文件**: 删除 `agents/semantic_parser/components/observer.py`, `prompts/observer.py`

- [ ] 删除 Observer 相关文件
- [ ] 更新 `__init__.py` 移除导出
- [ ] 搜索并移除所有 Observer 相关导入

**依赖**: Task 2.7

**验收标准**:
- Observer 相关文件已删除
- 无残留导入错误

---

## Phase 3: InsightAgent Subgraph 实现

### Task 3.1: 定义 Insight 内部状态
**文件**: `agents/insight/state.py`

- [ ] 创建 `InsightState(TypedDict)`:
  - 输入: query_result, files, context
  - Phase 1: enhanced_profile
  - Phase 2: coordinator_decisions, current_action
  - Phase 3: chunks, analyzed_chunks, chunk_insights
  - Phase 4: final_insights, summary
  - 控制: iteration_count, should_continue

**验收标准**:
- State 定义完整
- 类型注解正确

---

### Task 3.2: 定义 EnhancedDataProfile 数据模型
**文件**: `agents/insight/models/profile.py`

- [ ] 创建 `EnhancedDataProfile` 模型（继承基础画像）
- [ ] 创建 Tableau Pulse 风格洞察模型:
  - `ContributorAnalysis`: Top/Bottom 贡献者分析
  - `Contributor`: 单个贡献者
  - `ConcentrationRisk`: 集中度风险
  - `PeriodChangeAnalysis`: 同环比分析
  - `TrendAnalysis`: 趋势分析
- [ ] 创建智能索引模型:
  - `DimensionIndex`: 维度值→行号范围
  - `ValueRange`: 值范围
  - `AnomalyIndex`: 异常行号+严重度

**规范要求**: 遵循 `PROMPT_AND_MODEL_GUIDE.md`

**验收标准**:
- 所有模型通过 Pydantic 验证
- 与 design.md 一致

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

**依赖**: Task 3.2

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

### Task 3.5: 定义 Coordinator 决策模型
**文件**: `agents/insight/models/coordinator.py`

- [ ] 创建 `CoordinatorInput` 模型（包含画像摘要）
- [ ] 创建 `CoordinatorDecision` 模型:
  - action: analyze_chunk | analyze_dimension | analyze_anomaly | stop
  - target_chunk_id, target_dimension, target_dimension_value, target_anomaly_indices
  - reasoning, completeness_estimate, should_continue

**验收标准**:
- 模型定义完整
- 支持多种分析动作

---

### Task 3.6: 增强 AnalysisCoordinator
**文件**: `agents/insight/components/coordinator.py`

- [ ] 更新主持人 Prompt 展示 Tableau Pulse 洞察摘要
- [ ] 实现 `decide()` 方法返回 `CoordinatorDecision`
- [ ] 支持按维度/异常精准分析决策

**依赖**: Task 3.5

**验收标准**:
- 主持人能看到画像摘要
- 决策更智能

---

### Task 3.7: 实现 Coordinator 节点
**文件**: `agents/insight/components/coordinator_node.py`

- [ ] 实现 `coordinator_node(state: InsightState) -> Dict`
- [ ] 调用 AnalysisCoordinator.decide()
- [ ] 更新 State 决策字段

**依赖**: Task 3.6

**验收标准**:
- 决策正确生成
- State 正确更新

---

### Task 3.8: 实现 Analyzer 节点
**文件**: `agents/insight/components/analyzer_node.py`

- [ ] 实现 `analyzer_node(state: InsightState) -> Dict`
- [ ] 根据 decision.action 执行不同分析:
  - analyze_chunk: 分析指定分块
  - analyze_dimension: 按维度值精准读取
  - analyze_anomaly: 分析指定异常
- [ ] 实现 `read_by_dimension()` 精准读取
- [ ] 实现 `read_by_indices()` 按行号读取

**依赖**: Task 3.7

**验收标准**:
- 支持多种分析动作
- 精准读取正确

---

### Task 3.9: 实现 Synthesizer 节点
**文件**: `agents/insight/components/synthesizer_node.py`

- [ ] 实现 `synthesizer_node(state: InsightState) -> Dict`
- [ ] 调用 InsightSynthesizer 综合洞察
- [ ] 生成最终洞察和摘要

**验收标准**:
- 洞察综合正确
- 摘要生成正确

---

### Task 3.10: 创建 Insight Subgraph
**文件**: `agents/insight/subgraph.py`

- [ ] 实现 `create_insight_subgraph() -> StateGraph`
- [ ] 添加节点: profiler, coordinator, analyzer, synthesizer
- [ ] 添加边:
  - START → profiler
  - profiler → coordinator
  - coordinator → (conditional) → analyzer | synthesizer
  - analyzer → coordinator (循环)
  - synthesizer → END
- [ ] 实现 `route_after_coordinator()` 路由函数

**依赖**: Task 3.4, Task 3.7, Task 3.8, Task 3.9

**验收标准**:
- Subgraph 编译成功
- 循环正确执行

---

### Task 3.11: 更新 Insight Node 适配
**文件**: `agents/insight/node.py`

- [ ] 修改 `insight_node()` 函数
- [ ] 调用 Subgraph 而非直接执行
- [ ] 映射 Subgraph 输出到主 State

**依赖**: Task 3.10

**验收标准**:
- Node 正确调用 Subgraph
- State 输出字段正确填充

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
- [ ] 更新 `query_result` 类型注解支持文件引用
- [ ] 简化节点完成标志

**验收标准**:
- State 定义与 design.md 一致
- 无类型错误

---

### Task 4.2: 简化 routes.py
**文件**: `orchestration/workflow/routes.py`

- [ ] 从 4 个路由函数减少到 2 个:
  - `route_after_semantic_parser()`: 决定 insight | end
  - `route_after_replanner()`: 决定 semantic_parser | end
- [ ] 移除路由函数:
  - `route_after_execute()`
  - `route_after_self_correction()`

**验收标准**:
- 只有 2 个路由函数
- 路由逻辑与 design.md 一致

---

### Task 4.3: 重构 factory.py
**文件**: `orchestration/workflow/factory.py`

- [ ] 从 7 节点减少到 3 节点:
  - `semantic_parser` (Subgraph)
  - `insight` (Subgraph)
  - `replanner` (单节点)
- [ ] 移除节点:
  - `field_mapper`, `query_builder`, `execute`, `self_correction`
- [ ] 更新边定义:
  - START → semantic_parser
  - semantic_parser → (conditional) → insight | END
  - insight → replanner
  - replanner → (conditional) → semantic_parser | END
- [ ] 更新 `create_workflow()` 函数

**依赖**: Task 2.7, Task 3.11, Task 4.1, Task 4.2

**验收标准**:
- 工作流只有 3 个节点
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

**依赖**: Task 1.3, Task 1.4, Task 1.5

**验收标准**:
- 旧节点代码已删除
- 无残留导入错误

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
  - 测试 Step1 → ReAct Decision 流程 (SIMPLE)
  - 测试 Step1 → Step2 → ReAct Decision 流程 (COMPLEX)
  - 测试非 DATA_QUERY 意图直接结束
- [ ] 创建 `test_query_pipeline.py`:
  - 测试正常流程: Step1 → Step2 → MapFields → BuildQuery → Execute
  - 测试字段映射 RAG+LLM 混合策略（缓存→RAG→LLM Fallback→LLM Only）
  - 测试所有 8 个 Middleware 集成：
    - TodoListMiddleware: 任务队列管理
    - SummarizationMiddleware: 对话历史摘要
    - ModelRetryMiddleware: LLM 调用重试
    - ToolRetryMiddleware: 工具调用重试
    - FilesystemMiddleware: 大结果保存
    - PatchToolCallsMiddleware: 悬空工具调用修复
    - HumanInTheLoopMiddleware: 人工确认 (可选)
    - OutputValidationMiddleware: 输出格式验证
- [ ] 创建 `test_decision_handler.py`:
  - 测试成功场景：Pipeline 成功 → 结束
  - 测试错误场景：映射失败 → 返回错误信息
  - 测试 Token 级别流式输出

**验收标准**:
- Subgraph 测试通过
- QueryPipeline 测试通过
- ReAct Decision Loop 测试通过
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

- [ ] 测试 profiler → coordinator → analyzer → synthesizer 流程
- [ ] 测试 coordinator 循环决策
- [ ] 测试按维度精准读取
- [ ] 测试按异常精准读取
- [ ] 测试大文件场景

**验收标准**:
- Subgraph 测试通过
- 循环正确执行

---

### Task 5.5: 集成测试
**文件**: `tests/integration/`

- [ ] 创建 `test_semantic_parser_flow.py`:
  - 测试简单查询完整流程
  - 测试复杂查询完整流程
  - 测试错误处理场景
- [ ] 创建 `test_insight_flow.py`:
  - 测试 InsightAgent 使用 EnhancedDataProfiler
  - 测试主持人基于画像决策
  - 测试按维度/异常精准分析
- [ ] 创建 `test_replan_loop.py`:
  - 测试单轮: SemanticParser → Insight → Replanner (end)
  - 测试多轮重规划循环
  - 测试最大轮数限制

**验收标准**:
- 集成测试通过
- 重规划循环正确工作

---

### Task 5.6: 端到端测试
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
├── Task 1.2: 数据模型 (依赖 1.1)
├── Task 1.3: map_fields Tool (依赖 1.1, 1.2)
├── Task 1.4: build_query Tool (依赖 1.1, 1.2)
└── Task 1.5: execute_query Tool (依赖 1.1, 1.2)
        │
        ▼
Phase 2: SemanticParser Subgraph
├── Task 2.1: 内部状态定义
├── Task 2.2: Step1 节点
├── Task 2.3: Step2 节点
├── Task 2.4: ReAct Decision Prompt
├── Task 2.5: QueryPipeline (依赖 1.3-1.5) ★核心
├── Task 2.6: ReAct Decision Loop (依赖 2.5, 2.4)
├── Task 2.7: Subgraph 创建 (依赖 2.2, 2.3, 2.6)
├── Task 2.8: Node 适配 (依赖 2.7)
└── Task 2.9: 移除 Observer (依赖 2.7)
        │
        ▼
Phase 3: InsightAgent Subgraph
├── Task 3.1: 内部状态定义
├── Task 3.2: EnhancedDataProfile 模型
├── Task 3.3: EnhancedDataProfiler (依赖 3.2)
├── Task 3.4: Profiler 节点 (依赖 3.3)
├── Task 3.5: Coordinator 决策模型
├── Task 3.6: AnalysisCoordinator 增强 (依赖 3.5)
├── Task 3.7: Coordinator 节点 (依赖 3.6)
├── Task 3.8: Analyzer 节点 (依赖 3.7)
├── Task 3.9: Synthesizer 节点
├── Task 3.10: Subgraph 创建 (依赖 3.4, 3.7, 3.8, 3.9)
└── Task 3.11: Node 适配 (依赖 3.10)
        │
        ▼
Phase 4: 主工作流重构
├── Task 4.1: 更新 State
├── Task 4.2: 简化 routes.py
├── Task 4.3: 重构 factory.py (依赖 2.8, 3.11, 4.1, 4.2)
├── Task 4.4: 移除 SelfCorrection (依赖 4.3)
└── Task 4.5: 清理旧节点 (依赖 1.3-1.5)
        │
        ▼
Phase 5: 测试
├── Task 5.1: Tool 单元测试 (依赖 Phase 1)
├── Task 5.2: SemanticParser Subgraph 测试 (依赖 Phase 2)
│   ├── test_subgraph.py
│   ├── test_query_pipeline.py ★核心
│   └── test_react_decision_loop.py
├── Task 5.3: EnhancedDataProfiler 测试 (依赖 Task 3.3)
├── Task 5.4: Insight Subgraph 测试 (依赖 Phase 3)
├── Task 5.5: 集成测试 (依赖 Phase 4)
└── Task 5.6: 端到端测试 (依赖 Phase 4)
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
| Phase 1 | 5 | 1.5-2 天 | Tool 实现，提取现有逻辑 |
| Phase 2 | 8 | 2.5-3 天 | SemanticParser Subgraph，核心重构 |
| Phase 3 | 11 | 3-4 天 | InsightAgent Subgraph + EnhancedDataProfiler |
| Phase 4 | 5 | 1-1.5 天 | 主工作流重构，删除代码为主 |
| Phase 5 | 6 | 2.5-3 天 | 测试覆盖 |
| Phase 6 | 4 | 0.5-1 天 | 文档更新 |
| **总计** | **39** | **11-14.5 天** | |

---

## 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| Subgraph 状态传递复杂 | 高 | 明确定义输入输出 Schema，单元测试覆盖 |
| ReAct 循环不稳定 | 高 | 设置 max_iterations，添加详细日志 |
| 大数据内存溢出 | 高 | FilesystemMiddleware + 索引精准读取 |
| 重规划死循环 | 高 | max_replan_rounds + answered_questions 去重 |
| Subgraph 调试困难 | 中 | 添加 execution_path 追踪，详细日志 |

---

## 检查清单

### Phase 1 完成检查
- [ ] 所有 3 个 Tool 实现完成
- [ ] 数据模型符合规范
- [ ] Tool 单元测试通过

### Phase 2 完成检查
- [ ] SemanticParser Subgraph 正常运行
- [ ] Step1 + Step2 逻辑保持不变
- [ ] QueryPipeline 正确集成所有 8 个中间件：
  - [ ] TodoListMiddleware: before_agent/after_agent 任务管理
  - [ ] SummarizationMiddleware: wrap_model_call 对话历史摘要
  - [ ] ModelRetryMiddleware: wrap_model_call LLM 调用重试
  - [ ] ToolRetryMiddleware: wrap_tool_call 工具调用重试
  - [ ] FilesystemMiddleware: wrap_model_call 系统提示 + wrap_tool_call 大结果保存
  - [ ] PatchToolCallsMiddleware: before_agent + wrap_model_call 修复悬空调用
  - [ ] HumanInTheLoopMiddleware: wrap_tool_call 人工确认 (可选)
  - [ ] OutputValidationMiddleware: after_model + after_agent 输出验证
- [ ] 字段映射使用现有 RAG+LLM 混合策略（无额外重试逻辑）
- [ ] Observer 已移除

### Phase 3 完成检查
- [ ] InsightAgent Subgraph 正常运行
- [ ] EnhancedDataProfile 数据模型完成
- [ ] EnhancedDataProfiler 实现完成（含 Tableau Pulse 洞察）
- [ ] Coordinator 支持按维度/异常精准分析
- [ ] 循环决策正确执行

### Phase 4 完成检查
- [ ] 主工作流只有 3 个节点
- [ ] 路由函数只有 2 个
- [ ] State 定义已更新
- [ ] 旧节点代码已删除

### Phase 5 完成检查
- [ ] 所有测试通过
- [ ] Subgraph 测试通过
- [ ] QueryPipeline 测试通过（含所有 8 个中间件集成）
- [ ] 字段映射 RAG+LLM 混合策略测试通过
- [ ] EnhancedDataProfiler 测试通过
- [ ] 与旧架构行为一致

### Phase 6 完成检查
- [ ] 文档已更新
- [ ] 代码已清理
- [ ] 依赖已更新
