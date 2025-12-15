# Requirements Document

## Introduction

本需求文档定义了将 LangChain AgentMiddleware 机制集成到 Tableau Assistant 自定义节点函数中的功能。当前项目已经配置了 7 个 middleware（SummarizationMiddleware、ModelRetryMiddleware、ToolRetryMiddleware、HumanInTheLoopMiddleware、TodoListMiddleware、FilesystemMiddleware、PatchToolCallsMiddleware），但由于项目使用自定义 StateGraph 节点而非 `create_agent`，这些 middleware 实际上并未生效。

本功能将实现一个生产级的 MiddlewareRunner，使 middleware 能够在自定义节点函数中正确执行。

## Glossary

- **AgentMiddleware**: LangChain 提供的中间件基类，定义了 6 个钩子点用于拦截和修改 Agent 行为
- **MiddlewareRunner**: 本项目实现的中间件运行器，负责在自定义节点中调用 middleware 钩子
- **ModelRequest**: LangChain 定义的模型请求对象，包含 messages、tools、state、runtime 等
- **ModelResponse**: LangChain 定义的模型响应对象，包含 LLM 返回的 AIMessage
- **Runtime**: LangGraph 运行时上下文，包含 context、store、checkpointer 等
- **ToolCallRequest**: LangChain 定义的工具调用请求对象
- **Hook**: 中间件钩子，在特定时机执行的回调函数

## Requirements

### Requirement 1: MiddlewareRunner 核心实现

**User Story:** 作为开发者，我希望有一个 MiddlewareRunner 类来管理和执行 middleware，以便在自定义节点函数中复用 LangChain 的 middleware 机制。

#### Acceptance Criteria

1. WHEN 创建 MiddlewareRunner 实例时 THEN MiddlewareRunner SHALL 接受 middleware 列表并验证每个 middleware 是否为 AgentMiddleware 实例
2. WHEN 初始化 MiddlewareRunner 时 THEN MiddlewareRunner SHALL 按钩子类型分类 middleware（before_agent、before_model、wrap_model_call、after_model、wrap_tool_call、after_agent）
3. WHEN middleware 列表包含重复实例时 THEN MiddlewareRunner SHALL 抛出 ValueError 并提示移除重复项
4. WHEN 获取 middleware 名称时 THEN MiddlewareRunner SHALL 返回所有已注册 middleware 的名称列表

### Requirement 2: before_agent 和 after_agent 钩子

**User Story:** 作为开发者，我希望在 Agent 执行前后运行 middleware 钩子，以便进行状态初始化和清理。

#### Acceptance Criteria

1. WHEN 调用 run_before_agent 时 THEN MiddlewareRunner SHALL 按顺序执行所有实现了 before_agent/abefore_agent 的 middleware
2. WHEN before_agent 钩子返回状态更新时 THEN MiddlewareRunner SHALL 将更新合并到当前状态
3. WHEN 调用 run_after_agent 时 THEN MiddlewareRunner SHALL 按顺序执行所有实现了 after_agent/aafter_agent 的 middleware
4. WHEN after_agent 钩子返回状态更新时 THEN MiddlewareRunner SHALL 将更新合并到当前状态
5. WHEN 钩子执行失败时 THEN MiddlewareRunner SHALL 记录错误并根据配置决定是否继续执行后续钩子

### Requirement 3: before_model 和 after_model 钩子

**User Story:** 作为开发者，我希望在 LLM 调用前后运行 middleware 钩子，以便进行消息预处理（如总结）和后处理。

#### Acceptance Criteria

1. WHEN 调用 run_before_model 时 THEN MiddlewareRunner SHALL 按顺序执行所有实现了 before_model/abefore_model 的 middleware
2. WHEN before_model 钩子返回状态更新时 THEN MiddlewareRunner SHALL 将更新合并到当前状态（如 SummarizationMiddleware 更新 messages）
3. WHEN 调用 run_after_model 时 THEN MiddlewareRunner SHALL 按顺序执行所有实现了 after_model/aafter_model 的 middleware
4. WHEN after_model 钩子返回状态更新时 THEN MiddlewareRunner SHALL 将更新合并到当前状态

### Requirement 4: wrap_model_call 钩子链

**User Story:** 作为开发者，我希望 middleware 能够包装 LLM 调用，以便实现重试、缓存、修改请求/响应等功能。

#### Acceptance Criteria

1. WHEN 调用 wrap_model_call 时 THEN MiddlewareRunner SHALL 将所有 wrap_model_call 钩子链式组合（第一个 middleware 在最外层）
2. WHEN 链式调用时 THEN MiddlewareRunner SHALL 允许 middleware 多次调用 handler（用于重试）
3. WHEN 链式调用时 THEN MiddlewareRunner SHALL 允许 middleware 跳过调用 handler（用于短路/缓存）
4. WHEN 链式调用时 THEN MiddlewareRunner SHALL 允许 middleware 修改 ModelRequest 和 ModelResponse
5. WHEN 使用异步调用时 THEN MiddlewareRunner SHALL 使用 awrap_model_call 钩子

### Requirement 5: wrap_tool_call 钩子链

**User Story:** 作为开发者，我希望 middleware 能够包装工具调用，以便实现重试、监控、修改请求/响应等功能。

#### Acceptance Criteria

1. WHEN 调用 wrap_tool_call 时 THEN MiddlewareRunner SHALL 将所有 wrap_tool_call 钩子链式组合
2. WHEN 链式调用时 THEN MiddlewareRunner SHALL 允许 middleware 多次调用 handler（用于重试）
3. WHEN 链式调用时 THEN MiddlewareRunner SHALL 允许 middleware 修改 ToolCallRequest 和结果
4. WHEN 使用异步调用时 THEN MiddlewareRunner SHALL 使用 awrap_tool_call 钩子

### Requirement 6: Runtime 构建

**User Story:** 作为开发者，我希望 MiddlewareRunner 能够正确构建 Runtime 对象，以便 middleware 能够访问运行时上下文。

#### Acceptance Criteria

1. WHEN 构建 Runtime 时 THEN MiddlewareRunner SHALL 包含 context（用户自定义上下文）
2. WHEN 构建 Runtime 时 THEN MiddlewareRunner SHALL 包含 store（跨线程持久化存储）
3. WHEN 构建 Runtime 时 THEN MiddlewareRunner SHALL 包含 checkpointer（单线程状态持久化）
4. WHEN 构建 Runtime 时 THEN MiddlewareRunner SHALL 包含 config（LangGraph RunnableConfig）

### Requirement 7: ModelRequest 和 ModelResponse 构建

**User Story:** 作为开发者，我希望 MiddlewareRunner 能够正确构建 ModelRequest 和 ModelResponse 对象，以便与 LangChain middleware 兼容。

#### Acceptance Criteria

1. WHEN 构建 ModelRequest 时 THEN MiddlewareRunner SHALL 包含 messages（LangChain 消息列表）
2. WHEN 构建 ModelRequest 时 THEN MiddlewareRunner SHALL 包含 tools（可用工具列表）
3. WHEN 构建 ModelRequest 时 THEN MiddlewareRunner SHALL 包含 state（当前 Agent 状态）
4. WHEN 构建 ModelRequest 时 THEN MiddlewareRunner SHALL 包含 runtime（运行时上下文）
5. WHEN 构建 ModelRequest 时 THEN MiddlewareRunner SHALL 包含 system_prompt（可选的系统提示）
6. WHEN 构建 ModelResponse 时 THEN MiddlewareRunner SHALL 包含 result（AIMessage 列表）
7. WHEN 构建 ModelResponse 时 THEN MiddlewareRunner SHALL 包含 structured_response（可选的结构化响应）

### Requirement 8: 集成到 call_llm_with_tools

**User Story:** 作为开发者，我希望 call_llm_with_tools 函数能够自动应用 middleware，以便现有节点函数无需大改即可使用 middleware。

#### Acceptance Criteria

1. WHEN call_llm_with_tools 接收 middleware 参数时 THEN call_llm_with_tools SHALL 创建 MiddlewareRunner 并应用所有钩子
2. WHEN call_llm_with_tools 未接收 middleware 参数时 THEN call_llm_with_tools SHALL 保持原有行为不变
3. WHEN 应用 middleware 时 THEN call_llm_with_tools SHALL 按正确顺序调用钩子（before_model → wrap_model_call → after_model）
4. WHEN 工具调用发生时 THEN call_llm_with_tools SHALL 应用 wrap_tool_call 钩子

### Requirement 9: 集成到 Workflow Factory

**User Story:** 作为开发者，我希望 workflow factory 创建的 middleware 能够自动传递给节点函数，以便 middleware 在整个工作流中生效。

#### Acceptance Criteria

1. WHEN 创建 workflow 时 THEN create_tableau_workflow SHALL 将 middleware 栈存储在 compiled_graph 上
2. WHEN 节点函数执行时 THEN 节点函数 SHALL 能够从 config 或 graph 获取 middleware 栈
3. WHEN 节点函数获取 middleware 时 THEN 节点函数 SHALL 将 middleware 传递给 call_llm_with_tools

### Requirement 13: 对话历史管理

**User Story:** 作为用户，我希望 LLM 能够看到之前的对话内容，以便理解上下文并给出连贯的回答。

#### Acceptance Criteria

1. WHEN VizQLState 初始化时 THEN VizQLState SHALL 包含 messages 字段用于存储对话历史
2. WHEN 节点函数调用 LLM 时 THEN 节点函数 SHALL 从 state 获取历史消息并传递给 LLM
3. WHEN Insight Agent 完成分析时 THEN Insight Agent SHALL 生成结构化摘要消息（包含问题、维度、指标、时间范围、查询结果摘要、回答）
4. WHEN 对话历史过长时 THEN SummarizationMiddleware SHALL 自动总结历史消息以保持 token 在限制内
5. WHEN 用户问后续问题时 THEN LLM SHALL 能够看到之前的问题和回答以理解上下文
6. WHEN 生成消息时 THEN 系统 SHALL 在消息的 additional_kwargs 中标记来源（user/replanner/insight）
7. WHEN Replanner 生成探索问题时 THEN 系统 SHALL 在消息中标记 parent_question 以关联原始问题

### Requirement 14: Replanner 问题去重

**User Story:** 作为用户，我希望 Replanner 生成的探索问题不会与已回答的问题重复，以避免重复分析。

#### Acceptance Criteria

1. WHEN VizQLState 初始化时 THEN VizQLState SHALL 包含 answered_questions 字段用于记录已回答的问题
2. WHEN Insight Agent 完成分析时 THEN Insight Agent SHALL 将当前问题添加到 answered_questions 列表
3. WHEN Replanner 生成探索问题时 THEN Replanner SHALL 检查问题是否与 answered_questions 中的问题重复
4. WHEN 探索问题的目标维度已在 current_dimensions 中时 THEN Replanner SHALL 过滤该问题
5. WHEN 探索问题与已回答问题文本相似度超过阈值时 THEN Replanner SHALL 过滤该问题
6. WHEN answered_questions 列表超过 20 个时 THEN 系统 SHALL 只保留最近 20 个问题以避免 Prompt 过长
7. WHEN Replanner 生成多个探索问题时 THEN 系统 SHALL 串行执行这些问题（每轮执行一个）

### Requirement 15: 输出校验中间件

**User Story:** 作为开发者，我希望有一个 OutputValidationMiddleware 来校验 LLM 输出，以便确保输出符合预期的 Pydantic Schema。

#### Acceptance Criteria

1. WHEN LLM 返回响应后 THEN OutputValidationMiddleware SHALL 在 after_model 钩子中校验输出是否为有效 JSON
2. WHEN JSON 有效时 THEN OutputValidationMiddleware SHALL 使用配置的 Pydantic Schema 进行校验
3. WHEN 校验失败且 strict=True 时 THEN OutputValidationMiddleware SHALL 抛出 ValueError 异常
4. WHEN 校验失败且 strict=False 且 retry_on_failure=False 时 THEN OutputValidationMiddleware SHALL 记录警告并将错误添加到 state.validation_errors
5. WHEN 校验失败且 retry_on_failure=True 时 THEN OutputValidationMiddleware SHALL 抛出 OutputValidationError 异常以触发 ModelRetryMiddleware 重试
6. WHEN Agent 执行完成后 THEN OutputValidationMiddleware SHALL 在 after_agent 钩子中检查必需的状态字段是否存在

### Requirement 10: 错误处理和日志

**User Story:** 作为开发者，我希望 MiddlewareRunner 有完善的错误处理和日志，以便调试和监控 middleware 执行。

#### Acceptance Criteria

1. WHEN middleware 钩子抛出异常时 THEN MiddlewareRunner SHALL 记录详细错误信息（middleware 名称、钩子类型、异常信息）
2. WHEN middleware 钩子执行时 THEN MiddlewareRunner SHALL 记录 DEBUG 级别日志（middleware 名称、钩子类型、执行时间）
3. WHEN 配置 fail_fast=True 时 THEN MiddlewareRunner SHALL 在第一个错误时停止执行并抛出异常
4. WHEN 配置 fail_fast=False 时 THEN MiddlewareRunner SHALL 记录错误并继续执行后续 middleware（优雅降级）

### Requirement 11: 状态 Schema 合并

**User Story:** 作为开发者，我希望 MiddlewareRunner 能够合并 middleware 的状态 schema，以便 middleware 可以扩展 Agent 状态。

#### Acceptance Criteria

1. WHEN middleware 定义了 state_schema 时 THEN MiddlewareRunner SHALL 收集所有 middleware 的 state_schema
2. WHEN 合并状态时 THEN MiddlewareRunner SHALL 将 middleware 状态更新正确合并到 Agent 状态
3. WHEN FilesystemMiddleware 添加 files 字段时 THEN MiddlewareRunner SHALL 正确处理 files 字段的 reducer

### Requirement 12: 单元测试

**User Story:** 作为开发者，我希望 MiddlewareRunner 有完整的单元测试，以便确保功能正确性。

#### Acceptance Criteria

1. WHEN 测试 MiddlewareRunner 时 THEN 测试 SHALL 覆盖所有 6 个钩子类型
2. WHEN 测试链式调用时 THEN 测试 SHALL 验证 middleware 执行顺序
3. WHEN 测试错误处理时 THEN 测试 SHALL 验证 fail_fast 和优雅降级行为
4. WHEN 测试状态更新时 THEN 测试 SHALL 验证状态正确合并
