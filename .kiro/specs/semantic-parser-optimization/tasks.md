# 实施计划：语义解析器优化

## 概述

本实施计划将 SemanticParser 从当前架构升级到 vNext 架构，核心目标是降低 Token 成本、减少 LLM 调用、提升准确率。实施分为 Phase 0（工程债务清理）和 Phase 1-4（vNext 功能实现）。

## 任务列表

### Phase 0: 工程债务清理（前置条件）

- [x] 1. 统一语义解析入口与状态契约
  - 统一 `SemanticParserState` 状态定义，所有字段使用可 JSON 化类型
  - 在 subgraph 出口处实现 `_flatten_output()` 函数
  - 删除 `node.py` 中重复的扁平化逻辑
  - 修改主工作流路由统一消费扁平化字段
  - _Requirements: 0.1_

- [x] 2. 让 ReAct 覆盖 Step1/Step2 的解析失败
  - 修改 `subgraph.py` 路由逻辑，增加解析失败分支
  - 在 `state.py` 新增 `step1_parse_error`、`step2_parse_error` 字段
  - 在 `ReactErrorHandler` 增加解析失败处理逻辑
  - _Requirements: 0.2_

- [x] 3. Pipeline 贯通 middleware 能力
  - 修改 `QueryPipeline` 确保所有工具调用都经过 middleware
  - 实现 `_map_fields()` 和 `_execute_query()` 通过 middleware 调用
  - 确保 `MiddlewareRunner` 正确注入
  - _Requirements: 0.3_

- [x] 4. History/Schema token 硬性上限保护
  - 在 `Step1Component` 实现 `_format_history_with_limit()` 函数
  - 在 `Step1Component` 实现 `_format_schema()` 函数
  - 添加硬性截断逻辑（history: 2000 tokens, schema: 3000 tokens）
  - 记录截断发生的频率指标
  - _Requirements: 0.4_


- [x] 5. 基础可观测性
  - 新建 `infra/observability/metrics.py` 定义 `SemanticParserMetrics` 数据类
  - 实现 metrics 通过 `RunnableConfig` 传递（不进入 State）
  - 在各组件中埋点记录耗时、token 数、LLM 调用次数
  - 在 subgraph 出口处输出结构化日志
  - _Requirements: 0.5_

- [x] 6. 组件级解析重试（格式重试闭环）
  - [x] 6.1 实现 Step1 组件级解析重试
    - 在 `Step1Component.execute()` 实现格式重试循环（最大 2 次）
    - 实现 `_build_error_feedback()` 构建结构化错误反馈
    - 记录重试触发的原因和次数
    - _Requirements: 0.6_
  
  - [x] 6.2 实现 Step2 组件级解析重试
    - 在 `Step2Component.execute()` 实现格式重试循环（最大 2 次）
    - 实现 `_build_error_feedback()` 构建结构化错误反馈
    - 记录重试触发的原因和次数
    - _Requirements: 0.6_
  
  - [x] 6.3 保留 OutputValidationMiddleware 作为质量闸门
    - 确保 `OutputValidationMiddleware` 不触发重试，只记录和告警
    - 实现错误分类边界（格式错误 vs 语义错误）
    - 实现分类重试预算管理（格式重试 vs 语义重试独立计数）
    - _Requirements: 0.6_

- [x] 7. JSON 解析增强（JSON Mode + Provider 适配）
  - [x] 7.1 实现 Provider 适配层
    - 新建 `infra/ai/json_mode_adapter.py`
    - 实现 `ProviderType` 枚举和 `get_json_mode_kwargs()` 函数
    - 实现 `detect_provider_from_base_url()` 和 `get_provider_from_config()` 函数
    - _Requirements: 0.7_
  
  - [x] 7.2 集成 JSON Mode 到 model_manager
    - 修改 `create_chat_model()` 支持 `enable_json_mode` 参数
    - 根据 Provider 类型选择不同的参数传递方式
    - 记录 JSON Mode 降级指标
    - _Requirements: 0.7_
  
  - [x] 7.3 增强 parse_json_response（三层防护）
    - 实现 `JSONParseError` 异常类
    - 增强 `parse_json_response()` 的错误处理和日志
    - 记录 JSON 解析相关指标（直接解析成功率、json_repair 修复成功率等）
    - _Requirements: 0.7_
  
  - [x] 7.4 更新 Step1/Step2 prompt 包含 "json" 关键词
    - 修改 `prompts/step1.py` 确保包含 "json" 关键词和格式示例
    - 修改 `prompts/step2.py` 同上
    - _Requirements: 0.7_


- [x] 8. 流式 tool_calls 解析错误显式处理
  - 在 `agents/base/node.py` 实现 `_parse_tool_calls()` 函数
  - 实现 `ParsedToolCall` 数据类
  - 记录 tool_calls 参数解析失败率指标
  - 尝试使用 `json_repair` 修复 tool_calls 参数
  - _Requirements: 0.8_

- [x] 9. LLM 空响应显式处理
  - 在 `agents/base/node.py` 新增 `LLMEmptyResponseError` 异常类
  - 在 `_call_llm_with_tools_and_middleware()` 增强空响应检测
  - 记录空响应发生的频率指标
  - _Requirements: 0.9_

- [x] 10. Step1 history 参数与 SummarizationMiddleware 对齐
  - 修改 `Step1Component.execute()` 从 `state["messages"]` 读取 history
  - 实现 `_convert_messages_to_history()` 函数
  - 实现 `_format_history_with_limit()` 函数（硬性截断作为兜底）
  - 修改 `subgraph.py` 中Step1 调用方式
  - _Requirements: 0.10_

- [x] 11. 完整 middleware 钩子调用（before_agent/after_agent）
  - [x] 11.1 实现 subgraph 入口和出口节点
    - 在 `subgraph.py` 新增 `semantic_parser_entry()` 节点（调用 before_agent）
    - 在 `subgraph.py` 增强 `semantic_parser_exit()` 节点（调用 after_agent）
    - 确保所有终止路径都经过 exit 节点
    - ⚠️ 修复（GPT-5.2 审计）：`semantic_parser_entry()` 使用深拷贝检测变更
      - 浅拷贝场景下，middleware 原地修改 list/dict 时比较不出差异
      - 现在使用 `copy.deepcopy()` 确保正确检测所有变更
    - _Requirements: 0.11_
  
  - [x] 11.2 增强 MiddlewareRunner 钩子执行
    - 在 `middleware_runner.py` 实现 `HookExecutionResult` 数据类
    - 增强 `run_before_agent()` 方法（带 skip_on_error 参数和结果追踪）
    - 增强 `run_after_agent()` 方法（带 skip_on_error 参数和结果追踪）
    - 实现 `_log_hook_summary()` 记录钩子执行摘要
    - 新增 `middleware_hook_failure_count` 指标到 metrics.py
    - ⚠️ 修复（GPT-5.2 审计）：在 `_run_hooks_with_error_handling()` 内部记录失败指标
      - 当 `skip_on_error=True` 时，异常被内部捕获，entry/exit 的 except 块不会触发
      - 现在在 except 块内直接更新 `middleware_hook_failure_count`、`middleware_hook_failure_by_hook`、`middleware_hook_failure_by_middleware`
    - ⚠️ 修复（GPT-5.2 审计）：`middleware_hook_failure_by_hook` 使用 `sync_hook_name` 作为 key
      - 之前使用 `async_hook_name`（如 `abefore_agent`），导致指标 key 不一致
      - 现在统一使用 `before_agent`/`after_agent`，便于看板/告警聚合
    - _Requirements: 0.11_

- [x] 12. IntentRouter 意图识别（两阶段路由）
  - [x] 12.1 实现 IntentRouter 组件
    - 新建 `components/intent_router.py`
    - 实现 `IntentType` 枚举和 `IntentRouterOutput` 数据类
    - 实现 L0 规则层（0 LLM 调用）
    - 实现 L1 小模型分类（占位实现，默认禁用，MVP 范围外）
    - 实现 L2 Step1 兜底
    - _Requirements: 0.12_
  
  - [x] 12.2 集成 IntentRouter 到 subgraph
    - 在 `subgraph.py` 新增 `intent_router` 节点
    - 修改路由逻辑，仅在 `intent_type == DATA_QUERY` 时进入重路径
    - 记录各层命中率指标
    - ⚠️ 修复（GPT-5.2 审计）：`_flatten_output()` 现在优先从 `intent_router_output` 读取 `intent_type`
      - 当 IntentRouter 返回 CLARIFICATION/GENERAL/IRRELEVANT 时，不会运行 Step1
      - 之前只从 `step1_output` 读取，导致 `intent_type=None`
      - 现在先检查 `intent_router_output`，非 DATA_QUERY 时直接使用其 intent_type
    - ⚠️ 新增 `intent_router_l1_call_count` 指标（用于计算 L1 调用率）
    - ⚠️ 修复（GPT-5.2 审计）：`semantic_parser_node` 现在正确读取 subgraph 的文案字段
      - CLARIFICATION：优先使用 `clarification_question`（含 slots 的具体澄清问题）
      - GENERAL：优先使用 `user_message`（IntentRouter 生成的元数据问答响应）
      - IRRELEVANT：优先使用 `user_message`（IntentRouter 生成的礼貌拒绝消息）
    - _Requirements: 0.12_


- [x] 13. Schema Linking 回退路径（正确性护栏）
  - 在 `components/schema_linking.py` 实现 `SchemaLinkingResult` 数据类
  - 实现回退触发条件检测（候选集为空、低置信度、超时、异常）
  - 实现 `_check_low_coverage_signal()` 检测低覆盖信号
  - 记录回退触发的原因和频率指标
  - 支持配置回退阈值
  - _Requirements: 0.13_

- [x] 14. 灰度开关与回滚机制
  - [x] 14.1 实现灰度开关配置
    - 新建 `config/feature_flags.py` 定义 `FeatureFlags` 类
    - 实现 vNext 总开关和子功能开关
    - 支持通过环境变量控制
    - _Requirements: 0.14_
  
  - [x] 14.2 实现版本化存储
    - 新建 `infra/storage/vnext_store.py` 实现 `VNextStore` 类
    - 使用版本化 namespace 存储 vNext 缓存
    - 实现 `_filter_sensitive_fields()` 过滤敏感字段
    - 实现 `delete_vnext_data()` 支持数据回滚
    - _Requirements: 0.14_
  
  - [x] 14.3 实现灰度路由
    - 在 `subgraph.py` 实现 `route_by_feature_flag()` 函数
    - 支持请求级别覆盖（通过请求头）
    - 记录灰度开关状态变更日志
    - _Requirements: 0.14_

- [x] 15. Checkpoint - Phase 0 完成验证
  - 确保所有 Phase 0 任务的测试通过
  - 验证自愈率（Step1/Step2 解析失败后 ReAct 修复成功率 ≥ 70%）
  - 验证 JSON 解析成功率（直接解析 + json_repair 修复后 ≥ 95%）
  - 验证 token 上限保护生效（history ≤ 2000 tokens，schema ≤ 3000 tokens）
  - 询问用户是否有问题或需要调整

### Phase 1: 预处理 + Schema Linking（最大增益）

- [x] 16. 实现预处理层 - Preprocess Node
  - [x] 16.1 定义数据结构
    - 在 `components/preprocess.py` 定义 `TimeContext` 数据类
    - 定义 `MemorySlots` 数据类
    - 定义 `PreprocessResult` 数据类
    - _Requirements: 1_
  
  - [x] 16.2 实现 PreprocessComponent
    - 实现 `normalize()` 函数（全角半角归一、空白归一、单位归一）
    - 实现 `extract_time()` 函数（规则解析相对时间）
    - 实现 `extract_slots()` 函数（从历史抽取已确认项）
    - 实现 `build_canonical()` 函数（生成稳定的 canonical_question）
      - 去除 emoji 和特殊符号
      - 统一全角/半角
      - 去除冗余空白
      - 把时间表达替换成标准形式（如"上月"→`time:last_month`）
      - 确保相似问题映射到同一个 key（用于缓存）
    - 实现 `extract_terms()` 函数（提取候选业务术语）
    - _Requirements: 1_
  
  - [x] 16.3 集成到 subgraph
    - 在 `subgraph.py` 新增 `preprocess` 节点
    - 在 `SemanticParserState` 新增相关字段
    - 删除 `Step1Component` 中的 `current_time` 秒级依赖
    - _Requirements: 1_


- [x] 17. 实现 Schema Linking 层 - 候选字段前置检索
  - [x] 17.1 定义数据结构
    - 在 `components/schema_linking.py` 定义 `FieldCandidate` 数据类
    - 定义 `SchemaCandidates` 数据类
    - 定义 `ScoringWeights` 数据类
    - _Requirements: 2_
  
  - [x] 17.2 实现 FieldIndexerV2（优化版字段索引）
    - 实现精确匹配索引（O(1) 哈希查找，使用 dict）
    - 实现 N-gram 倒排索引（支持容错）
    - 实现 `build_index()` 函数
    - 实现 `exact_match()` 函数（确保 O(1) 复杂度）
    - 实现 `fuzzy_match()` 函数
    - 验证：10000 字段下精确匹配耗时 < 1ms
    - _Requirements: 2, 8_
  
  - [x] 17.3 实现 TermExtractor（增强版术语提取）
    - 实现字段名词典构建
    - 实现别名映射
    - 集成 jieba 自定义词典
    - 实现 N-gram 补充捕获复合词
    - _Requirements: 2_
  
  - [x] 17.4 实现 BatchEmbeddingOptimizer（批量 Embedding）
    - 实现批量 Embedding 队列管理
    - 实现 `embed_query()` 入口函数
    - 实现 `_flush_batch()` 批处理逻辑
    - 实现 `_auto_flush()` 超时自动 flush
    - _Requirements: 2, 7_
  
  - [x] 17.5 实现 SchemaLinkingComponent
    - 实现 `_determine_search_pool()` 判断检索池（维度/度量/全部）
    - 实现 `_vector_search()` 向量检索
    - 实现 `_merge_candidates()` 合并去重
    - 实现两阶段打分融合（精确匹配 + N-gram + embedding）
    - 实现降级策略（字段数 > 2000 时）
    - _Requirements: 2_
  
  - [x] 17.6 集成到 subgraph
    - 在 `subgraph.py` 新增 `schema_linking` 节点
    - 在 `SemanticParserState` 新增 `schema_candidates` 字段
    - _Requirements: 2_

- [x] 17.7 统一 RAG 基础设施（以 FieldMapper RAG 为基础，融合 SchemaLinking 优化）
  - [x] 17.7.1 迁移 FieldMapper RAG 到 `infra/rag/`
    - 将 `agents/field_mapper/rag/` 核心模块迁移到 `infra/rag/`
    - 迁移的模块：
      - `models.py`（FieldChunk, RetrievalResult 等数据模型）
      - `field_indexer.py`（FAISS 索引 + 持久化）
      - `retriever.py`（HybridRetriever + 三路召回）
      - `reranker.py`（RRFReranker + LLMReranker）
      - `embeddings.py`（EmbeddingProvider）
      - `cache.py`（LangGraph SqliteStore 缓存 + CachedEmbeddingProvider）
      - `observability.py`（RAGMetrics + LatencyBreakdown）
    - 保留在 field_mapper/rag/ 的专用模块：
      - `assembler.py`（知识组装器，FieldMapper 专用）
      - `dimension_pattern.py`（维度模式，FieldMapper 专用）
      - `field_value_indexer.py`（字段值索引，FieldMapper 专用）
      - `semantic_mapper.py`（语义映射器，FieldMapper 专用）
    - 更新 `field_mapper/rag/__init__.py` 从 infra/rag 重新导出（向后兼容）
    - 更新 `infra/rag/__init__.py` 的导出
    - _Requirements: 技术债务清理_
  
  - [x] 17.7.2 融合 SchemaLinking 的优化到统一 RAG
    - 新增 `infra/rag/exact_retriever.py` 实现 O(1) 精确匹配
      - 从 SchemaLinking 的 `FieldIndexerV2.exact_match()` 提取
      - 实现 `ExactRetriever` 类
      - 支持 name/caption 双索引
      - 性能目标：10000 字段下耗时 < 1ms
    - 新增 `infra/rag/batch_optimizer.py` 实现批量 Embedding 优化
      - 从 SchemaLinking 的 `BatchEmbeddingOptimizer` 提取
      - 实现批量队列管理（accumulate → flush）
      - 实现自动 flush（timeout=50ms）
      - 与 `CachedEmbeddingProvider` 配合使用
    - （待实现）`infra/rag/cascade_retriever.py` 级联检索
    - _Requirements: 技术债务清理_
  
  - [x] 17.7.3 实现 `RetrievalMode` 配置
    - 在 `infra/rag/config.py` 定义 `RetrievalMode` 枚举
      - `FAST_RECALL`：快速召回模式（SchemaLinking 用）
      - `HIGH_PRECISION`：高精度模式（FieldMapper 用）
    - 实现 `create_retriever(mode: RetrievalMode, field_indexer: FieldIndexer)` 工厂函数
    - 定义预设配置：`FAST_RECALL_CONFIG`, `HIGH_PRECISION_CONFIG`
    - _Requirements: 技术债务清理_
  
  - [x] 17.7.4 迁移 SchemaLinking 使用统一 RAG
    - 修改 `schema_linking.py` 使用 `create_retriever(mode=FAST_RECALL)`
    - 删除以下类（已迁移到 infra/rag）：
      - `FieldIndexerV2`（→ ExactRetriever + 复用 FieldIndexer）
      - `BatchEmbeddingOptimizer`（→ infra/rag/batch_optimizer.py）
    - 保留以下组件（应用层逻辑）：
      - `TermExtractor`（术语提取，与 Preprocess 配合）
      - `SchemaLinkingComponent`（应用层封装）
      - 降级策略（字段数 > 2000）
      - 回退护栏（低覆盖度检测）
    - 统一数据模型：`FieldCandidate` 在应用层转换为 `RetrievalResult`
    - 确保所有 SchemaLinking 测试通过
    - _Requirements: 技术债务清理_
  
  - [x] 17.7.5 更新 FieldMapper 使用统一 RAG
    - 修改 `field_mapper/node.py` 使用 `create_retriever(mode=HIGH_PRECISION)`
    - 保留 `field_mapper/rag/` 目录中的专用模块（assembler, dimension_pattern, field_value_indexer, semantic_mapper）
    - 保留 `SemanticMapper` 作为应用层封装
    - 确保所有 FieldMapper 测试通过
    - _Requirements: 技术债务清理_

- [ ] 18. 重构 Step1 - 受约束生成
  - [ ] 18.1 定义新的数据结构
    - 定义 `FieldReference` 数据类（字段引用协议），包含以下字段：
      - `candidate_id: str`（候选 ID，来自 SchemaCandidates）
      - `canonical_name: str`（规范化字段名）
      - `role: Literal["dimension", "measure"]`
      - `confidence: float`（置信度 0-1）
      - `table_name: str | None`（多表场景）
      - `original_term: str | None`（原始业务术语）
    - 重构 `Step1Output` 删除 `restated_question`，新增 `field_references`
    - _Requirements: 3_
  
  - [ ] 18.2 重构 Step1Component
    - 修改 `execute()` 输入参数（使用 canonical_question + schema_candidates）
    - 删除 `_format_data_model()` 中的全量字段注入
    - 修改 prompt 注入候选摘要（非全量）
    - _Requirements: 3_
  
  - [ ] 18.3 更新 Step1 prompt
    - 修改 `prompts/step1.py` 指导模型从候选中选择
    - 确保字段引用使用候选 ID/规范名
    - _Requirements: 3_


- [ ] 19. Checkpoint - Phase 1 完成验证
  - 确保 Preprocess、Schema Linking、Step1 重构的测试通过
  - 验证 Step1 prompt token 从 O(|fields|) 降到 O(k)
  - 询问用户是否有问题或需要调整

### Phase 2: 计算规划 + 校验（减少 LLM 调用）

- [ ] 20. 实现计算规划层 - ComputationPlanner
  - [ ] 20.1 定义计算模板库
    - 新建 `components/computation_planner.py`
    - 定义 `HOW_TYPE_TO_TABLE_CALC_TYPE` 映射
    - 定义 `ScoringWeights` 和 `ComputationTemplate` 数据类
    - _Requirements: 4_
  
  - [ ] 20.2 实现 partition_by 推断逻辑
    - 实现 `_infer_partition_by()` 函数
    - 实现 `map_partition_to_api()` 内部 IR 到 OpenAPI 映射
    - 处理 RUNNING_TOTAL 的 restartEvery 特殊逻辑：
      - `partition_by → restartEvery`（单字段）
      - `dimensions` 固定为 `[]`（使用 Tableau 默认 addressing）
      - 如果 partition_by 多字段，记录降级警告并选择第一个
    - _Requirements: 4_
  
  - [ ] 20.3 实现 ComputationPlannerComponent
    - 实现模板匹配逻辑（同比/环比/排名/占比/移动平均/累计）
    - 实现约束求解（通过粒度+层级决定 partition_by）
    - 实现 LLM fallback（仅模板无法覆盖时调用）
    - _Requirements: 4_
  
  - [ ] 20.4 弱化 Step2Component
    - 修改 Step2 仅作为 fallback（heavy path）
    - 把 Step2 的 self-validation 改为代码校验的输入
    - _Requirements: 4_

- [ ] 21. 实现后处理层 - Validator 组件
  - [ ] 21.1 实现强校验逻辑
    - 新建 `components/validator.py`
    - 实现字段存在性校验
    - 实现类型匹配校验
    - 实现聚合合法性校验
    - 实现 `partition_by ⊆ query_dimensions` 校验
    - 实现字段唯一性校验（去重）
    - _Requirements: 5_
  
  - [ ] 21.2 实现可规则修复
    - 实现去重 measures 修复
    - 实现纠正聚合修复
    - 实现字段不存在转澄清列表
    - 实现权限错误快速失败
    - _Requirements: 5_
  
  - [ ] 21.3 实现统一澄清协议
    - 定义 `ClarificationRequest` 数据类
    - 定义 `ClarificationType` 枚举（FIELD_AMBIGUOUS | LOW_CONFIDENCE | FILTER_VALUE_NOT_FOUND | MULTIPLE_INTERPRETATION）
    - 定义 `ClarificationOption` 数据类
    - _Requirements: 5, 14_

- [ ] 21.4 统一所有组件的澄清输出格式
  - 修改 Preprocess 组件，当时间解析失败时返回 `ClarificationRequest`
  - 修改 SchemaLinking 组件，当候选集为空或低置信度时返回 `ClarificationRequest`
  - 修改 ReAct 组件，当规则无法修复时返回 `ClarificationRequest`
  - 确保所有澄清都走 `ClarificationType` 枚举
  - _Requirements: 14_

- [ ] 22. 重构 ReAct - 规则化优先
  - [ ] 22.1 实现 deterministic error classifier
    - 修改 `components/react_error_handler.py`
    - 实现 `ERROR_ACTION_MAP` 错误类型映射
    - 实现 `ErrorAction` 枚举（ABORT/CLARIFY/FIX/LLM_REACT）
    - _Requirements: 6_
  
  - [ ] 22.2 实现规则化错误处理
    - 实现 FIELD_NOT_FOUND → 快速失败或转澄清
    - 实现 PERMISSION_DENIED → 快速失败
    - 实现 TYPE_MISMATCH → 尝试规则修复
    - 实现 AGGREGATION_CONFLICT → 尝试规则修复
    - _Requirements: 6_
  
  - [ ] 22.3 记录错误分类分布指标
    - 记录各错误类型的发生频率
    - 记录规则修复成功率
    - 记录 LLM ReAct 调用率
    - _Requirements: 6_

- [ ] 23. Checkpoint - Phase 2 完成验证
  - 确保 ComputationPlanner、Validator、ReAct 重构的测试通过
  - 验证 Step2 LLM 调用减少 70%+（模板覆盖率）
  - 验证 ReAct LLM 调用减少 50%+（规则化优先）
  - 验证所有组件的澄清输出都使用统一的 `ClarificationRequest` 格式
  - 询问用户是否有问题或需要调整


### Phase 3: 性能优化（缓存 + 并行）

- [ ] 24. 实现候选集缓存
  - [ ] 24.1 实现两级缓存
    - 新建 `infra/storage/candidate_cache.py`
    - 实现 L1 请求内 memo（同一轮重试复用）
    - 实现 L2 SqliteStore（跨请求复用）
    - _Requirements: 10_
  
  - [ ] 24.2 实现缓存键和失效策略
    - 使用 `hash(canonical_question + current_date + datasource_luid)` 作为缓存键
    - 对"含相对时间"条目跨天自动失效
    - 支持配置缓存 TTL（默认 24 小时）
    - _Requirements: 10_

- [ ] 25. 实现异步 Reranker + 超时降级
  - 修改 `field_mapper/rag/reranker.py` 支持异步调用
  - 实现超时降级（超时时直接返回未 rerank 的候选）
  - 支持配置 Reranker 超时时间（默认 3 秒）
  - 记录 Reranker 超时率指标
  - _Requirements: 9_

- [ ] 26. 实现 FAISS 索引懒加载/预热
  - 修改 `field_mapper/rag/faiss_store.py` 支持持久化存储
  - 实现 FAISS 索引的懒加载
  - 支持配置索引预热策略
  - 支持增量更新 FAISS 索引（避免全量重建）
  - _Requirements: 11_

- [ ] 27. Checkpoint - Phase 3 完成验证
  - 确保缓存、Reranker、FAISS 优化的测试通过
  - 验证缓存命中率 ≥ 30%
  - 验证批量 embedding 减少 API 调用
  - 询问用户是否有问题或需要调整

### Phase 4: 可观测性 + 收尾

- [ ] 28. 可观测性增强
  - [ ] 28.1 实现延迟指标
    - 记录 Preprocess、Schema Linking、Step1、Step2、Pipeline 各阶段耗时
    - 记录 embedding/检索/rerank 分段耗时
    - 记录缓存命中率（L1/L2 分别统计）
    - _Requirements: 12_
  
  - [ ] 28.2 实现吞吐/并发指标
    - 实现 `requests_per_minute` 每分钟请求数
    - 实现 `concurrent_requests` 并发请求数
    - 实现 `batch_embedding_batch_size_distribution` 批量 embedding 的 batch size 分布
    - 实现 `batch_embedding_utilization` 批量 embedding 利用率
    - _Requirements: 12_
  
  - [ ] 28.3 支持结构化日志和 OpenTelemetry
    - 实现结构化日志输出（JSON 格式）
    - 支持 OpenTelemetry 集成（可选）
    - _Requirements: 12_

- [ ] 29. 重试预算管理
  - 实现分类重试预算（格式重试 vs 语义重试独立计数）
  - 支持配置总重试预算（按 Token 或时间）
  - 实现预算耗尽时返回 ABORT
  - 记录重试次数分布指标（按类型分类）
  - _Requirements: 13_

- [ ] 30. MapFields 瘦身
  - 修改 `field_mapper/node.py` 实现 Fast Path（校验+落地）
  - 实现 RAG Fallback（检索+重排）
  - 把 MapFields 输入升级为"带候选/带置信度策略"的映射请求
  - 支持批量与并行映射
  - _Requirements: 15_

- [ ] 31. ResolveFilterValues 前置检索
  - 修改 `components/query_pipeline.py` 实现前置检索策略
  - 在 Schema Linking 阶段检索候选过滤值
  - 实现过滤值不在候选中时立即触发澄清
  - _Requirements: 16_

- [ ] 32. Final Checkpoint - 全部完成验证
  - 确保所有测试通过
  - 验证性能目标达成（Step1 prompt token O(k)、LLM 调用 ≤ 1.5 次/请求、P95 延迟 ≤ 2s）
  - 验证质量目标达成（Build 成功率 ≥ 95%、Execute 成功率 ≥ 90%）
  - 询问用户是否有问题或需要调整

## 注意事项

- 任务标记 `*` 的为可选任务，可跳过以加快 MVP 进度
- 每个任务都引用了具体的需求编号以便追溯
- Checkpoint 任务用于确保阶段性验证，如有问题请及时反馈
- Phase 0 是后续所有功能的前置条件，必须优先完成
