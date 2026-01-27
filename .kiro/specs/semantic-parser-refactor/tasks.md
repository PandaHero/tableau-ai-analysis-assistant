# Implementation Tasks

## Overview

本任务列表基于语义解析器重构的设计文档，按照组件依赖关系和实现优先级组织。

**任务统计**：
- 27 个主任务，跨 13 个阶段
- 42 个正确性属性（Property 1-41，含 Property 30.1 和 36.1）
- 对应 42 个 PBT 任务

**测试要求**：
- 使用真实 LLM (DeepSeek) 和真实 Embedding (Zhipu)，不使用 Mock
- 配置文件：`analytics_assistant/config/app.yaml`
- 测试运行目录：`analytics_assistant`
- Property-Based Testing 使用 Hypothesis 库

---

## Phase 1: 核心数据模型与基础组件

### Task 1: Pydantic 数据模型定义
- [x] 1.1 创建 `schemas/output.py` - SemanticOutput, SelfCheck, What, Where, Computation 模型
  - [x] 1.1.1 定义 HowType 枚举 (SIMPLE/COMPLEX)
  - [x] 1.1.2 定义 CalcType 枚举 (RATIO/GROWTH/SHARE/LOD/TABLE_CALC)
  - [x] 1.1.3 定义 MeasureField, DimensionField 模型
  - [x] 1.1.4 定义 SelfCheck 模型（含 4 个置信度字段）
  - [x] 1.1.5 定义 SemanticOutput 模型（含 query_id, parent_query_id 追踪字段）
- [x] 1.2 创建 `schemas/intermediate.py` - 中间数据模型
  - [x] 1.2.1 定义 FieldCandidate 模型
  - [x] 1.2.2 定义 FewShotExample 模型
- [x] 1.3 创建 `schemas/cache.py` - 缓存相关模型
  - [x] 1.3.1 定义 CachedQuery 模型（含 schema_hash 字段）
  - [x] 1.3.2 定义 CachedFieldValues 模型
- [x] 1.4 创建 `schemas/filters.py` - 筛选器验证模型
  - [x] 1.4.1 定义 FilterValidationResult 模型
  - [x] 1.4.2 定义 FilterValidationSummary 模型
  - [x] 1.4.3 定义 FilterConfirmation 模型（多轮确认累积）

### Task 2: SemanticParserState 定义
- [x] 2.1 创建/更新 `state.py` - LangGraph 状态定义
  - [x] 2.1.1 定义 SemanticParserState TypedDict（含所有输入/输出/控制字段）
  - [x] 2.1.2 添加 confirmed_filters 字段（多轮筛选值确认累积）
  - [x] 2.1.3 添加 error_history, correction_abort_reason 字段

---

## Phase 2: 意图路由与缓存组件

### Task 3: IntentRouter 实现
- [x] 3.1 创建 `components/intent_router.py`
  - [x] 3.1.1 定义 IntentType 枚举
  - [x] 3.1.2 定义 IntentRouterOutput 模型
  - [x] 3.1.3 实现 L0 规则匹配（关键词匹配）
  - [x] 3.1.4 实现 L1 可选 LLM 分类（配置开关）
  - [x] 3.1.5 实现 route() 方法
- [ ] 3.2 [PBT] Property 1: Intent Classification Coverage
  - 验证任意问题都被分类为 3 种意图之一，置信度在 0-1 之间

### Task 4: QueryCache 实现
- [x] 4.1 创建 `components/query_cache.py`
  - [x] 4.1.1 实现 compute_schema_hash() 函数
  - [x] 4.1.2 实现 QueryCache 类（基于 SqliteStore）
  - [x] 4.1.3 实现 get() 方法（含 schema_hash 验证）
  - [x] 4.1.4 实现 get_similar() 方法（语义相似匹配）
  - [x] 4.1.5 实现 set() 方法
  - [x] 4.1.6 实现 invalidate_by_datasource() 方法
- [ ] 4.2 [PBT] Property 2: Cache Round-Trip Consistency
  - 验证缓存写入后读取返回等价结果
- [ ] 4.3 [PBT] Property 3: Cache Invalidation on Model Change
  - 验证数据模型变更后缓存失效
- [ ] 4.4 [PBT] Property 32: Cache Schema Validation on Read
  - 验证 schema_hash 不匹配时返回 None

---

## Phase 3: 检索组件

### Task 5: FieldRetriever 实现
- [x] 5.1 创建 `components/field_retriever.py`
  - [x] 5.1.1 实现 FieldRetriever 类（复用 CascadeRetriever）
  - [x] 5.1.2 实现 retrieve() 方法（Top-K 检索，默认 K=10）
  - [x] 5.1.3 实现精确匹配优先逻辑
- [ ] 5.2 [PBT] Property 4: Top-K Retrieval Threshold
  - 验证返回结果不超过 K 个
- [ ] 5.3 [PBT] Property 5: Exact Match Priority
  - 验证精确匹配的置信度高于语义匹配

### Task 6: FewShotManager 实现
- [ ] 6.1 创建 `components/few_shot_manager.py`
  - [ ] 6.1.1 实现 FewShotManager 类
  - [ ] 6.1.2 实现 retrieve() 方法（返回 0-3 个示例）
  - [ ] 6.1.3 实现 add() 方法
  - [ ] 6.1.4 实现 update_accepted_count() 方法
  - [ ] 6.1.5 实现用户接受示例优先排序
- [ ] 6.2 [PBT] Property 10: Few-Shot Example Count
  - 验证返回示例数在 0-3 之间
- [ ] 6.3 [PBT] Property 11: Accepted Example Priority
  - 验证接受过的示例排名更高

---

## Phase 4: 核心语义理解

### Task 7: TimeHintGenerator 实现
- [ ] 7.1 创建 `prompts/time_hint_generator.py`
  - [ ] 7.1.1 实现静态时间模式匹配（今天、上个月、本季度等）
  - [ ] 7.1.2 实现动态时间模式匹配（最近N天/周/月）
  - [ ] 7.1.3 实现财年相关表达式（本财年、上财年、财年Q1-Q4）
  - [ ] 7.1.4 实现 generate_hints() 方法
  - [ ] 7.1.5 实现 format_for_prompt() 方法
- [ ] 7.2 [PBT] Property 33: Time Hint Generation
  - 验证识别的时间表达式生成正确的日期范围

### Task 8: DynamicPromptBuilder 实现
- [ ] 8.1 创建 `prompts/prompt_builder.py`
  - [ ] 8.1.1 实现 _detect_complexity() 方法（检测派生度量关键词）
  - [ ] 8.1.2 实现简化版 Prompt 模板
  - [ ] 8.1.3 实现完整版 Prompt 模板
  - [ ] 8.1.4 实现 build() 方法（动态选择模板）
  - [ ] 8.1.5 集成 TimeHintGenerator
- [ ] 8.2 [PBT] Property 25: Prompt Complexity Adaptation
  - 验证包含派生度量关键词时使用 COMPLEX 模板
- [ ] 8.3 [PBT] Property 26: Time Expression Context
  - 验证 Prompt 包含 current_date, timezone, fiscal_year_start_month

### Task 9: SemanticUnderstanding 实现
- [ ] 9.1 创建 `components/semantic_understanding.py`
  - [ ] 9.1.1 实现 SemanticUnderstanding 类
  - [ ] 9.1.2 实现 understand() 方法（调用 LLM）
  - [ ] 9.1.3 集成 stream_llm_structured() 流式输出
  - [ ] 9.1.4 实现 JSON 解析和 Pydantic 验证
- [ ] 9.2 [PBT] Property 6: Restated Question Completeness
  - 验证 restated_question 包含完整独立的问题描述
- [ ] 9.3 [PBT] Property 7: Clarification Detection
  - 验证不完整问题返回 needs_clarification=true
- [ ] 9.4 [PBT] Property 8: State Completeness
  - 验证输出包含所有必需字段
- [ ] 9.5 [PBT] Property 12: Self-Check Presence
  - 验证 self_check 字段存在且置信度在 0-1 之间
- [ ] 9.6 [PBT] Property 13: Low Confidence Flagging
  - 验证低置信度时 potential_issues 非空
- [ ] 9.7 [PBT] Property 18: Streaming Output Validity
  - 验证流式输出完成后是有效的 Pydantic 对象
- [ ] 9.8 [PBT] Property 19: Derived Metric Decomposition
  - 验证派生度量被正确分解为计算公式
- [ ] 9.9 [PBT] Property 20: Computation Pattern Recognition
  - 验证计算类型被正确识别

---

## Phase 5: 筛选值验证与确认机制

### Task 10: FieldValueCache 实现
- [ ] 10.1 创建 `components/field_value_cache.py`
  - [ ] 10.1.1 实现分段锁架构（16 个分片）
  - [ ] 10.1.2 实现 _get_shard() 方法
  - [ ] 10.1.3 实现 get() 方法（异步，线程安全）
  - [ ] 10.1.4 实现 set() 方法（含 LRU 淘汰）
  - [ ] 10.1.5 实现 clear() 方法
  - [ ] 10.1.6 实现 preload_common_fields() 方法
- [ ] 10.2 [PBT] Property 36: Field Value Cache LRU Eviction
  - 验证达到容量上限时淘汰最久未使用的条目
- [ ] 10.3 [PBT] Property 36.1: Field Value Cache Sharded Lock Concurrency
  - 验证不同分片的操作可以并行执行
- [ ] 10.4 [PBT] Property 37: Field Value Cache Preload Threshold
  - 验证只预加载基数 < 500 的维度字段

### Task 11: ValidateFilterValueTool 实现
- [ ] 11.1 创建 `components/validate_filter_tool.py`
  - [ ] 11.1.1 定义 ValidateFilterValueResult 模型
  - [ ] 11.1.2 实现 ValidateFilterValueTool 类
  - [ ] 11.1.3 实现 _arun() 方法（精确匹配 + 模糊匹配）
  - [ ] 11.1.4 实现 _find_similar() 方法（编辑距离 + 包含关系）

### Task 12: FilterValueValidator 实现
- [ ] 12.1 创建 `components/filter_validator.py`
  - [ ] 12.1.1 实现 FilterValueValidator 类
  - [ ] 12.1.2 实现 should_validate() 方法（跳过时间字段、高基数字段）
  - [ ] 12.1.3 实现 validate() 方法
  - [ ] 12.1.4 实现 apply_confirmations() 方法
  - [ ] 12.1.5 实现 apply_single_confirmation() 方法
- [ ] 12.2 [PBT] Property 23: Filter Validation Before Execution
  - 验证所有筛选条件在执行前被验证
- [ ] 12.3 [PBT] Property 29: Filter Validation Skip for Time Fields
  - 验证时间字段跳过验证
- [ ] 12.4 [PBT] Property 38: Unresolvable Filter Detection
  - 验证无匹配且无相似值时 has_unresolvable_filters=true
- [ ] 12.5 [PBT] Property 39: Filter Validation interrupt() Condition
  - 验证 needs_confirmation=true 且有相似值时触发 interrupt()
- [ ] 12.6 [PBT] Property 40: Multi-Round Filter Confirmation Accumulation
  - 验证多轮确认时 confirmed_filters 正确累积

---

## Phase 6: 查询适配与错误修正

### Task 13: QueryAdapter 实现
- [ ] 13.1 创建 `components/query_adapter.py`
  - [ ] 13.1.1 定义 QueryAdapter 抽象基类
  - [ ] 13.1.2 实现 VizQLAdapter 类（复用现有 query_builder）
  - [ ] 13.1.3 实现 adapt() 方法（SemanticOutput → VizQL）
  - [ ] 13.1.4 实现 validate() 方法
- [ ] 13.2 [PBT] Property 41: QueryAdapter Syntax Validity
  - 验证生成的查询语法有效

### Task 14: ErrorCorrector 实现
- [ ] 14.1 创建 `components/error_corrector.py`
  - [ ] 14.1.1 定义 ErrorCorrectionHistory 模型
  - [ ] 14.1.2 实现 ErrorCorrector 类
  - [ ] 14.1.3 实现 _compute_error_hash() 方法
  - [ ] 14.1.4 实现 _normalize_error_message() 方法
  - [ ] 14.1.5 实现 should_retry() 方法（含总历史长度检查）
  - [ ] 14.1.6 实现 correct() 方法
  - [ ] 14.1.7 实现 reset_history() 方法
- [ ] 14.2 [PBT] Property 14: Retry Limit Enforcement
  - 验证重试次数不超过 3 次
- [ ] 14.3 [PBT] Property 30: Duplicate Error Detection
  - 验证相同错误出现 2 次时终止
- [ ] 14.4 [PBT] Property 30.1: Alternating Error Detection
  - 验证总错误历史达到上限时终止（防止 A→B→A→B 模式）
- [ ] 14.5 [PBT] Property 31: Non-Retryable Error Handling
  - 验证不可重试错误类型不进行重试

---

## Phase 7: 反馈学习

### Task 15: FeedbackLearner 实现
- [ ] 15.1 创建 `components/feedback_learner.py`
  - [ ] 15.1.1 定义 FeedbackType 枚举
  - [ ] 15.1.2 定义 FeedbackRecord 模型
  - [ ] 15.1.3 实现 FeedbackLearner 类
  - [ ] 15.1.4 实现 record() 方法
  - [ ] 15.1.5 实现 learn_synonym() 方法
  - [ ] 15.1.6 实现 promote_to_example() 方法
- [ ] 15.2 [PBT] Property 15: Feedback to Example Promotion
  - 验证接受的查询被添加到示例候选池
- [ ] 15.3 [PBT] Property 16: Synonym Learning Threshold
  - 验证 3 次以上确认的映射自动添加到同义词表

---

## Phase 8: LangGraph 子图集成

### Task 16: 节点函数实现
- [ ] 16.1 创建 `graph.py` - 节点函数
  - [ ] 16.1.1 实现 intent_router_node()
  - [ ] 16.1.2 实现 query_cache_node()
  - [ ] 16.1.3 实现 field_retriever_node()
  - [ ] 16.1.4 实现 few_shot_manager_node()
  - [ ] 16.1.5 实现 semantic_understanding_node()
  - [ ] 16.1.6 实现 filter_validator_node()（含 interrupt() 调用）
  - [ ] 16.1.7 实现 query_adapter_node()
  - [ ] 16.1.8 实现 error_corrector_node()
  - [ ] 16.1.9 实现 feedback_learner_node()

### Task 17: 路由函数实现
- [ ] 17.1 在 `graph.py` 中添加路由函数
  - [ ] 17.1.1 实现 route_by_intent()
  - [ ] 17.1.2 实现 route_by_cache()
  - [ ] 17.1.3 实现 route_after_understanding()
  - [ ] 17.1.4 实现 route_after_validation()
  - [ ] 17.1.5 实现 route_after_query()
  - [ ] 17.1.6 实现 route_after_correction()

### Task 18: 子图组装
- [ ] 18.1 实现 create_semantic_parser_graph() 函数
  - [ ] 18.1.1 添加所有节点
  - [ ] 18.1.2 设置入口点
  - [ ] 18.1.3 添加条件边
  - [ ] 18.1.4 配置 checkpointer
- [ ] 18.2 [PBT] Property 34: Filter Confirmation via LangGraph interrupt()
  - 验证筛选值确认时正确调用 interrupt()
- [ ] 18.3 [PBT] Property 35: Filter Value Update After Confirmation
  - 验证确认后 filters 被正确更新

---

## Phase 9: 上下文与配置集成

### Task 19: WorkflowContext 扩展
- [ ] 19.1 更新 `orchestration/workflow/context.py`
  - [ ] 19.1.1 添加 current_time 字段
  - [ ] 19.1.2 添加 timezone 字段
  - [ ] 19.1.3 添加 fiscal_year_start_month 字段
  - [ ] 19.1.4 添加 field_values_cache 字段
  - [ ] 19.1.5 添加 field_samples 字段
- [ ] 19.2 [PBT] Property 21: Context Data Model Caching
  - 验证同一会话内数据模型只加载一次
- [ ] 19.3 [PBT] Property 22: Context State Persistence
  - 验证上下文状态在会话内持久化

### Task 20: 配置集成
- [ ] 20.1 更新 `config/app.yaml` 添加 semantic_parser 配置节
  - [ ] 20.1.1 添加 intent_router 配置
  - [ ] 20.1.2 添加 cache 配置
  - [ ] 20.1.3 添加 field_retriever 配置（top_k=10）
  - [ ] 20.1.4 添加 few_shot 配置
  - [ ] 20.1.5 添加 llm 配置
  - [ ] 20.1.6 添加 error_correction 配置
  - [ ] 20.1.7 添加 token_optimization 配置

---

## Phase 10: 多轮对话与历史管理

### Task 21: 对话历史管理
- [ ] 21.1 实现对话历史截断逻辑
  - [ ] 21.1.1 实现 MAX_HISTORY_TOKENS 检查
  - [ ] 21.1.2 实现历史截断（保留最近消息）
  - [ ] 21.1.3 集成 SummarizationMiddleware（可选）
- [ ] 21.2 [PBT] Property 17: History Truncation
  - 验证截断后保留最近的消息
- [ ] 21.3 [PBT] Property 9: Incremental State Update
  - 验证多轮对话中新信息与现有状态合并

### Task 22: 澄清来源追踪
- [ ] 22.1 实现澄清来源追踪
  - [ ] 22.1.1 在 SemanticParserState 中添加 clarification_source 字段
  - [ ] 22.1.2 在 SemanticUnderstanding 中设置来源
  - [ ] 22.1.3 在 FilterValueValidator 中设置来源
- [ ] 22.2 [PBT] Property 24: Clarification Source Tracking
  - 验证澄清请求包含正确的来源标识

---

## Phase 11: 数据模型集成

### Task 23: Schema Hash 机制
- [ ] 23.1 实现 schema_hash 计算与验证
  - [ ] 23.1.1 在 DataModel 中添加 schema_hash 属性
  - [ ] 23.1.2 实现 compute_schema_hash() 函数
  - [ ] 23.1.3 在 QueryCache 中集成 schema_hash 验证
- [ ] 23.2 [PBT] Property 27: Schema Hash Consistency
  - 验证字段变更时 schema_hash 变化

### Task 24: 维度层级集成
- [ ] 24.1 集成 DimensionHierarchyInference
  - [ ] 24.1.1 在 WorkflowExecutor 中调用层级推断
  - [ ] 24.1.2 在 Prompt 中包含层级信息
- [ ] 24.2 [PBT] Property 28: Hierarchy Enrichment
  - 验证维度字段包含下钻选项

---

## Phase 12: 集成测试

### Task 25: 端到端流程测试
- [ ] 25.1 创建 `tests/integration/test_graph_flow.py`
  - [ ] 25.1.1 测试简单查询完整流程
  - [ ] 25.1.2 测试缓存命中流程
  - [ ] 25.1.3 测试需要澄清的流程
  - [ ] 25.1.4 测试筛选值确认流程（interrupt/resume）
  - [ ] 25.1.5 测试错误修正流程
  - [ ] 25.1.6 测试边界条件：空字段列表
  - [ ] 25.1.7 测试边界条件：空 Few-shot 示例库
  - [ ] 25.1.8 测试边界条件：网络超时降级

### Task 26: 多轮对话测试
- [ ] 26.1 创建 `tests/integration/test_multi_turn.py`
  - [ ] 26.1.1 测试渐进式查询构建
  - [ ] 26.1.2 测试多轮筛选值确认
  - [ ] 26.1.3 测试对话历史管理

---

## Phase 13: 性能测试

### Task 27: 性能基准测试
- [ ] 27.1 创建 `tests/performance/test_benchmarks.py`
  - [ ] 27.1.1 测试 IntentRouter 延迟 (< 50ms)
  - [ ] 27.1.2 测试 FieldRetriever 延迟 (< 100ms)
  - [ ] 27.1.3 测试完整流程延迟 (< 3s)
  - [ ] 27.1.4 测试 FieldValueCache 并发性能

---

## 依赖关系

```
Phase 1 (数据模型) 
    ↓
Phase 2 (意图路由/缓存) ← Phase 3 (检索)
    ↓                        ↓
Phase 4 (语义理解) ←─────────┘
    ↓
Phase 5 (筛选值验证)
    ↓
Phase 6 (查询适配/错误修正)
    ↓
Phase 7 (反馈学习)
    ↓
Phase 8 (LangGraph 集成) ← Phase 9 (上下文/配置)
    ↓
Phase 10 (多轮对话) ← Phase 11 (数据模型集成)
    ↓
Phase 12 (集成测试) → Phase 13 (性能测试)
```
