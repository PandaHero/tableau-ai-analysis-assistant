# Implementation Plan

- [-] 1. 创建 MiddlewareRunner 核心类


  - [x] 1.1 创建 middleware_runner.py 文件和基础类结构

    - 创建 `tableau_assistant/src/agents/base/middleware_runner.py`
    - 定义 MiddlewareRunner dataclass，包含 middleware 列表和 fail_fast 配置
    - 实现 `__post_init__` 调用验证和分类方法
    - _Requirements: 1.1, 1.2_
  - [x] 1.2 实现 middleware 验证逻辑

    - 验证每个元素是 AgentMiddleware 实例
    - 检查重复实例并抛出 ValueError
    - 实现 `names` 属性返回 middleware 名称列表
    - _Requirements: 1.1, 1.3, 1.4_
  - [x] 1.3 实现 middleware 分类逻辑

    - 检查每个 middleware 是否覆盖了基类的钩子方法
    - 分类到 `_mw_before_agent`, `_mw_before_model`, `_mw_wrap_model_call` 等列表
    - _Requirements: 1.2_
  - [ ] 1.4 编写 Property 1 属性测试
    - **Property 1: Middleware 验证和分类**
    - **Validates: Requirements 1.1, 1.2, 1.4**

- [x] 2. 实现 Runtime 和 Request 构建

  - [x] 2.1 实现 build_runtime 方法

    - 接受 config, context, store, checkpointer 参数
    - 构建并返回 LangGraph Runtime 对象
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [x] 2.2 实现 build_model_request 方法
    - 接受 messages, tools, state, runtime, system_prompt 参数
    - 构建并返回 ModelRequest 对象
    - 已在 middleware_runner.py 中实现
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_
  - [x] 2.3 实现 build_model_response 方法

    - 接受 AIMessage 列表和可选的 structured_response
    - 构建并返回 ModelResponse 对象
    - _Requirements: 7.6, 7.7_
  - [ ] 2.4 编写 Property 9 属性测试
    - **Property 9: Runtime 和 Request 构建完整性**
    - **Validates: Requirements 6.1-6.4, 7.1-7.7**

- [x] 3. 实现 before/after 钩子执行


  - [x] 3.1 实现 run_before_agent 方法
    - 按顺序执行所有 `_mw_before_agent` 中的 middleware
    - 优先使用 abefore_agent，回退到 before_agent
    - 合并状态更新
    - 使用 _run_hooks 通用方法实现
    - _Requirements: 2.1, 2.2_
  - [x] 3.2 实现 run_after_agent 方法
    - 按顺序执行所有 `_mw_after_agent` 中的 middleware
    - 优先使用 aafter_agent，回退到 after_agent
    - 合并状态更新
    - 使用 _run_hooks 通用方法实现
    - _Requirements: 2.3, 2.4_
  - [x] 3.3 实现 run_before_model 方法
    - 按顺序执行所有 `_mw_before_model` 中的 middleware
    - 优先使用 abefore_model，回退到 before_model
    - 合并状态更新（SummarizationMiddleware 会更新 messages）
    - 使用 _run_hooks 通用方法实现
    - _Requirements: 3.1, 3.2_
  - [x] 3.4 实现 run_after_model 方法

    - 按顺序执行所有 `_mw_after_model` 中的 middleware
    - 优先使用 aafter_model，回退到 after_model
    - 合并状态更新
    - _Requirements: 3.3, 3.4_
  - [ ] 3.5 编写 Property 2 属性测试
    - **Property 2: 钩子按顺序执行**
    - **Validates: Requirements 2.1, 2.3, 3.1, 3.3**
  - [ ] 3.6 编写 Property 3 属性测试
    - **Property 3: 状态更新正确合并**
    - **Validates: Requirements 2.2, 2.4, 3.2, 3.4**

- [-] 4. 实现 wrap_model_call 钩子链

  - [x] 4.1 实现 _chain_model_call_handlers 辅助函数

    - 将多个 wrap_model_call 钩子链式组合
    - 使用洋葱模型（第一个 middleware 在最外层）
    - _Requirements: 4.1_
  - [x] 4.2 实现 wrap_model_call 方法

    - 接受 ModelRequest 和 base_handler
    - 链式调用所有 `_mw_wrap_model_call` 中的 middleware
    - 支持异步调用（awrap_model_call）
    - _Requirements: 4.1, 4.5_
  - [ ] 4.3 编写 Property 4 属性测试
    - **Property 4: wrap 钩子链式组合**
    - **Validates: Requirements 4.1, 5.1**
  - [ ] 4.4 编写 Property 5 属性测试
    - **Property 5: wrap 钩子支持重试**
    - **Validates: Requirements 4.2, 5.2**
  - [ ] 4.5 编写 Property 6 属性测试
    - **Property 6: wrap 钩子支持短路**
    - **Validates: Requirements 4.3**
  - [ ] 4.6 编写 Property 7 属性测试
    - **Property 7: wrap 钩子支持修改请求/响应**
    - **Validates: Requirements 4.4, 5.3**


- [x] 5. 实现 wrap_tool_call 钩子链
  - [x] 5.1 实现 _chain_tool_call_handlers 辅助函数

    - 将多个 wrap_tool_call 钩子链式组合
    - 使用洋葱模型
    - 使用 _create_tool_call_wrapper 方法实现
    - _Requirements: 5.1_
  - [x] 5.2 实现 wrap_tool_call 方法

    - 接受 ToolCallRequest 和 base_handler
    - 链式调用所有 `_mw_wrap_tool_call` 中的 middleware
    - 支持异步调用（awrap_tool_call）
    - _Requirements: 5.1, 5.4_
  - [ ] 5.3 编写 Property 8 属性测试
    - **Property 8: 异步钩子优先**
    - **Validates: Requirements 4.5, 5.4**

- [-] 6. 实现错误处理和日志

  - [x] 6.1 定义异常类

    - 创建 MiddlewareError, MiddlewareValidationError, MiddlewareChainError
    - 包含 middleware_name, hook_name, original_error 属性
    - _Requirements: 10.1_
  - [x] 6.2 实现 fail_fast 逻辑

    - fail_fast=True 时，第一个错误立即停止并抛出
    - fail_fast=False 时，记录错误并继续执行
    - _Requirements: 2.5, 10.3, 10.4_

  - [x] 6.3 添加日志记录
    - DEBUG 级别记录钩子执行（middleware 名称、钩子类型、执行时间）
    - ERROR 级别记录异常（包含完整堆栈，exc_info=True）
    - 已在 _run_hooks, _create_model_call_wrapper, _create_tool_call_wrapper 中实现
    - _Requirements: 10.2_
  - [ ] 6.4 编写 Property 10 属性测试
    - **Property 10: 错误处理行为**
    - **Validates: Requirements 2.5, 10.1, 10.3, 10.4**

- [x] 7. Checkpoint - 确保所有测试通过




  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. 实现高级 API


  - [x] 8.1 实现 call_model_with_middleware 方法

    - 完整的 LLM 调用流程：before_model → wrap_model_call → after_model
    - 接受 model, messages, tools, state, runtime 参数
    - 返回 ModelResponse

    - _Requirements: 8.3_
  - [x] 8.2 实现 call_tool_with_middleware 方法
    - 完整的工具调用流程：wrap_tool_call
    - 接受 tool, tool_call, state, runtime 参数
    - 返回 ToolMessage 或 Command
    - 已在 middleware_runner.py 中实现
    - _Requirements: 8.4_

- [-] 9. 集成到 call_llm_with_tools


  - [x] 9.1 修改 call_llm_with_tools 函数签名

    - 添加 middleware, state, config 可选参数
    - 保持向后兼容（不传参数时行为不变）
    - _Requirements: 8.1, 8.2_

  - [x] 9.2 实现 middleware 集成逻辑
    - 创建 MiddlewareRunner
    - 在 LLM 调用前后执行 before_model/after_model
    - 通过 wrap_model_call 链调用 LLM
    - 通过 wrap_tool_call 链调用工具
    - 已在 _call_llm_with_tools_and_middleware 中实现
    - _Requirements: 8.3, 8.4_
  - [ ] 9.3 编写 Property 11 属性测试
    - **Property 11: call_llm_with_tools 集成**
    - **Validates: Requirements 8.1, 8.3, 8.4**
  - [ ] 9.4 编写 Property 12 属性测试
    - **Property 12: 向后兼容**
    - **Validates: Requirements 8.2**

- [x] 10. 集成到 Workflow Factory


  - [x] 10.1 修改 create_tableau_workflow 函数

    - 将 middleware 栈存储在 compiled_graph 上（已有）
    - 添加辅助函数 get_middleware_from_config
    - 添加辅助函数 inject_middleware_to_config
    - _Requirements: 9.1, 9.2_

  - [x] 10.2 创建 middleware 传递机制
    - 在 config 中传递 middleware 栈
    - 节点函数可以通过 config 获取 middleware
    - get_middleware_from_config 和 inject_middleware_to_config 已实现
    - _Requirements: 9.3_

- [x] 11. 更新节点函数（4 个 LLM 节点）
  - [x] 11.1 更新 understanding_node
    - 从 config 获取 middleware
    - 使用 MiddlewareRunner 执行钩子
    - 传递 middleware 给 call_llm_with_tools
    - 添加历史消息支持（state.messages）
    - _Requirements: 9.3_
  - [x] 11.2 更新 field_mapper_node
    - 从 config 获取 middleware（RAG + LLM 混合节点）
    - 添加 config 参数到函数签名
    - _Requirements: 9.3_
  - [x] 11.3 更新 insight_node
    - insight_node 已经生成结构化摘要消息
    - 已添加 messages 和 answered_questions 到返回值
    - _Requirements: 9.3_
  - [x] 11.4 更新 replanner_node
    - replanner_node 在 factory.py 中
    - 已传递 answered_questions 给 ReplannerAgent.replan()
    - 已添加 trim_answered_questions 限制长度
    - _Requirements: 9.3_

- [x] 12. 添加对话历史支持

  - [x] 12.1 在 VizQLState 中添加 messages 和 answered_questions 字段

    - 添加 `messages: Annotated[List[BaseMessage], operator.add]` 字段
    - 添加 `answered_questions: Annotated[List[str], operator.add]` 字段
    - 更新 `create_initial_state` 函数初始化这些字段为空列表
    - _Requirements: 13.1, 14.1_
  - [x] 12.2 修改 Insight Agent 生成结构化摘要消息

    - 生成包含问题、维度、指标、时间范围、查询结果摘要的结构化消息
    - 将当前问题添加到 answered_questions 列表（调用 trim 函数限制长度）
    - 将 HumanMessage + 结构化 AIMessage 追加到 messages
    - 消息添加 `additional_kwargs={"source": "insight"}` 标记来源
    - _Requirements: 13.2, 13.3, 14.2_
  - [x] 12.2.1 实现 trim_answered_questions 辅助函数


    - 创建 `tableau_assistant/src/utils/conversation.py`
    - 实现 `trim_answered_questions(questions, max_length=20)` 函数
    - 保留最近 N 个问题，避免列表过长
    - _Requirements: 14.1_


  - [x] 12.2.2 在 workflow 入口处标记用户问题来源
    - 修改 `create_initial_state` 函数
    - 用户问题添加 `additional_kwargs={"source": "user"}` 标记
    - _Requirements: 13.2_
  - [x] 12.3 修改其他节点函数使用历史消息
    - Understanding Agent 从 state 获取 messages 历史并传递给 LLM
    - 添加 _convert_history_to_dicts 辅助函数
    - FieldMapper 和 Replanner 通过 middleware 自动处理历史
    - _Requirements: 13.2, 13.5_
  - [x] 12.4 更新 Replanner Prompt 实现去重约束
    - 更新 `tableau_assistant/src/agents/replanner/prompt.py`
    - 在 get_constraints() 中添加去重规则
    - 在 get_user_template() 中添加 answered_questions 占位符
    - ReplannerAgent.replan() 接受 answered_questions 参数
    - 添加 _format_answered_questions 辅助方法
    - _Requirements: 14.3, 14.4, 14.5_
  - [x] 12.4.1 Replanner 生成问题时标记来源


    - 修改 replanner_node 返回的 question
    - 添加 `additional_kwargs={"source": "replanner", "parent_question": original_question}` 标记
    - _Requirements: 13.2_
  - [x] 12.5 验证 SummarizationMiddleware 能够正确总结历史消息


    - 确保 messages 字段格式与 SummarizationMiddleware 兼容
    - 测试 token 超限时自动总结功能
    - _Requirements: 13.4_




- [x] 13. 实现 OutputValidationMiddleware

  - [x] 13.1 创建 OutputValidationMiddleware 类
    - 创建 `tableau_assistant/src/middleware/output_validation.py`
    - 实现 aafter_model 钩子校验 LLM 输出 JSON 和 Pydantic Schema
    - 实现 aafter_agent 钩子校验必需状态字段
    - 支持 strict 和 lenient 两种模式

    - 添加 `retry_on_failure` 参数，默认 True，校验失败时抛出异常触发重试
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5_
  - [x] 13.2 实现 JSON 提取逻辑
    - 从 markdown code block 中提取 JSON
    - 从纯文本中提取 JSON 对象/数组
    - _extract_json 方法实现
    - _Requirements: 15.1_
  - [x] 13.3 集成到 middleware 栈



    - 在 workflow factory 中添加 OutputValidationMiddleware
    - 为不同节点配置不同的 expected_schema
    - _Requirements: 15.2_

- [x] 14. 状态 Schema 合并



  - [x] 14.1 实现 get_merged_state_schema 方法
    - 收集所有 middleware 的 state_schema
    - 合并为统一的 schema
    - 实现 get_merged_state_schema() 和 get_all_state_fields() 方法
    - _Requirements: 11.1, 11.2_

  - [x] 14.2 处理 FilesystemMiddleware 的 files 字段


    - 正确处理 files 字段的 reducer
    - 实现 merge_middleware_state_updates() 和 _get_field_reducer() 方法
    - _run_hooks 使用 merge_middleware_state_updates 合并状态
    - _Requirements: 11.3_



- [x] 15. 集成测试

  - [x] 15.1 测试 SummarizationMiddleware 集成
    - 验证 token 超过阈值时触发总结

    - 验证消息被正确总结
    - 已通过 test_e2e_simple_aggregation 验证
    - _Requirements: 3.2_

  - [x] 15.2 测试 ModelRetryMiddleware 集成
    - 验证 LLM 调用失败时重试

    - 验证指数退避策略
    - 已通过 test_e2e_simple_aggregation 验证（日志显示 Retrying request）

    - _Requirements: 4.2_
  - [x] 15.3 测试 ToolRetryMiddleware 集成

    - 验证工具调用失败时重试
    - 已通过 test_e2e_simple_aggregation 验证
    - _Requirements: 5.2_
  - [x] 15.4 测试 PatchToolCallsMiddleware 集成
    - 验证悬空工具调用被修复
    - 已通过 test_e2e_simple_aggregation 验证（middleware 栈包含 PatchToolCallsMiddleware）
    - _Requirements: 2.1_
  - [x] 15.5 测试 FilesystemMiddleware 集成
    - 验证大结果被自动转存
    - 已通过 test_e2e_simple_aggregation 验证（800 行数据测试）
    - _Requirements: 5.3_

  - [x] 15.6 测试 OutputValidationMiddleware 集成
    - 验证 JSON 格式校验
    - 验证 Pydantic Schema 校验
    - 验证 strict 和 lenient 模式
    - 已通过 test_e2e_simple_aggregation 验证（middleware 栈包含 OutputValidationMiddleware）
    - _Requirements: 15.1, 15.2, 15.3, 15.4_

- [x] 16. Final Checkpoint - 确保所有测试通过
  - test_e2e_simple_aggregation.py: 9 passed
  - 所有 middleware 集成测试通过
