# Implementation Plan

## 1. DeepAgent 工厂配置完善

- [ ] 1.1 配置中间件参数
  - 更新 `tableau_assistant/src/agents/deep_agent_factory.py`
  - 配置 SummarizationMiddleware: `max_tokens_before_summary=170000`, `messages_to_keep=6`
  - 配置 FilesystemMiddleware: `tool_token_limit_before_evict=20000`
  - 配置 AnthropicPromptCachingMiddleware: `unsupported_model_behavior="ignore"`
  - 配置 CompositeBackend 支持混合存储
  - _Requirements: 1.1, 1.2, 3.4, 3.5, 4.4, 6.3_

- [ ]* 1.2 编写中间件配置测试
  - **Property 1: DeepAgent 中间件完整性**
  - **Validates: Requirements 1.2**

## 2. Understanding Agent 表计算识别

- [ ] 2.1 更新 QuestionUnderstanding 模型
  - 更新 `tableau_assistant/src/models/question.py`
  - 添加 `table_calc_type: Optional[TableCalcType]` 字段（引用 vizql_types.py 中已有的类型）
  - 添加 `table_calc_dimensions: Optional[List[TableCalcFieldReference]]` 字段
  - _Requirements: 9.5, 9.6_

- [ ] 2.2 增强 Understanding Prompt
  - 更新 `tableau_assistant/prompts/understanding.py`
  - 添加表计算关键词识别规则（Step 6）
  - 添加 table_calc_dimensions 推断规则（Step 7）
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

- [ ]* 2.3 编写表计算识别测试
  - **Property 11: 表计算关键词识别正确性**
  - **Validates: Requirements 9.1, 9.2, 9.3, 9.4**

## 3. Boost Agent 元数据默认使用

- [ ] 3.1 修改 Boost Agent 默认行为
  - 更新 `tableau_assistant/src/agents/nodes/question_boost.py`
  - 设置 `use_metadata=True` 为默认值
  - 添加元数据降级处理
  - _Requirements: 10.1, 10.4_

- [ ]* 3.2 编写 Boost Agent 测试
  - **Property 12: Boost Agent 元数据默认使用**
  - **Validates: Requirements 10.1**

## 4. Insight Agent 渐进式分析

- [ ] 4.1 实现 Insight 数据模型
  - 创建 `tableau_assistant/src/models/insight.py`
  - 定义 InsightType、InsightPriority 枚举
  - 定义 Insight、InsightCollection 模型
  - _Requirements: 11.6_

- [ ] 4.2 实现渐进式分析
  - 更新 `tableau_assistant/src/agents/nodes/insight.py`
  - 实现 `_intelligent_chunking()` - 优先级分块（URGENT → HIGH → MEDIUM → LOW → DEFERRED）
  - 实现 `_progressive_analysis()` - 渐进式分析循环
  - 实现 `_direct_analysis()` - 小数据直接分析（<= 100 行）
  - 实现早停机制
  - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_

- [ ]* 4.3 编写渐进式分析测试
  - **Property 13: 渐进式分析触发正确性**
  - **Property 14: 渐进式分析优先级正确性**
  - **Property 15: 渐进式分析早停正确性**
  - **Validates: Requirements 11.1, 11.2, 11.4**

- [ ] 4.4 Checkpoint
  - Ensure all tests pass, ask the user if questions arise.

## 5. Replanner Agent 智能重规划

- [ ] 5.1 更新完成度评估模型
  - 更新 `tableau_assistant/src/models/replan_decision.py`
  - 添加 CompletenessEvaluation 模型（score, question_coverage, data_completeness, insight_depth, anomaly_handling, missing_aspects）
  - _Requirements: 12.3, 12.4, 12.5_

- [ ] 5.2 实现智能重规划逻辑
  - 更新 `tableau_assistant/src/agents/nodes/replanner.py`
  - 实现 `_evaluate_completeness()` 方法
  - 实现智能终止策略（score >= 0.9 终止，replan_count >= max 终止）
  - 生成补充问题（基于已有洞察，不重复原问题）
  - _Requirements: 12.1, 12.3, 12.5, 12.7_

- [ ] 5.3 更新重规划路由逻辑
  - 更新 `tableau_assistant/src/agents/workflows/vizql_workflow.py`
  - 实现 `should_replan()` 路由函数
  - 重规划时跳过 Understanding 直接到 Planning
  - 记录终止原因到 replan_history
  - _Requirements: 12.1, 12.2, 12.6_

- [ ]* 5.4 编写 Replanner 测试
  - **Property 17: 重规划路由正确性**
  - **Property 18: 智能终止策略正确性**
  - **Property 19: 重规划问题生成正确性**
  - **Property 20: 重规划历史记录正确性**
  - **Validates: Requirements 12.1, 12.2, 12.3, 12.6, 12.7**

- [ ] 5.5 Checkpoint
  - Ensure all tests pass, ask the user if questions arise.

## 6. 集成测试

- [ ] 6.1 端到端工作流测试
  - 测试完整流程：Boost → Understanding → Planning → Execute → Insight → Replanner
  - 测试表计算查询端到端
  - 测试重规划循环
  - _Requirements: All_

- [ ] 6.2 Final Checkpoint
  - Ensure all tests pass, ask the user if questions arise.
