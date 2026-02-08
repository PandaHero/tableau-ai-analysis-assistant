# Implementation Plan: Semantic Understanding Optimization (Phase 14)

## Overview

本实现计划将 Phase 14 优化架构分解为可执行的编码任务。采用增量式开发，每个任务构建在前一个任务的基础上，确保代码始终可运行。

## Tasks

- [x] 1. 基础设施准备
  - [x] 1.1 创建 Phase14 异常类
    - 在 `analytics_assistant/src/core/exceptions.py` 中添加 Phase14Error 及其子类
    - 包含：Phase14Error、RulePrefilterError、FeatureExtractionError、FeatureExtractorTimeoutError、FieldRetrievalError、OutputValidationError
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7_
  
  - [x] 1.2 创建 Phase14 数据模型
    - 创建 `analytics_assistant/src/agents/semantic_parser/schemas/phase14.py`
    - 定义：ComplexityType、PrefilterResult、FeatureExtractionOutput、FieldRAGResult、FieldCandidate、TimeHint、MatchedComputation、ValidationResult、ValidationError、ValidationErrorType
    - _Requirements: 2.5, 3.4, 5.3, 5.4_
  
  - [x] 1.3 添加 Phase14 配置到 app.yaml
    - 在 `analytics_assistant/config/app.yaml` 中添加 semantic_parser.phase14 配置节
    - 包含所有可配置参数：
      - 全局配置：enabled、global_confidence_threshold
      - RulePrefilter：low_confidence_threshold、rule_prefilter_max_time_ms
      - FeatureExtractor：timeout_ms、model、max_input_tokens
      - FeatureCache：ttl_seconds、similarity_threshold、max_size
      - FieldRetriever：top_k、fallback_multiplier、enable_category_filter
      - DynamicSchemaBuilder：max_schema_fields
      - OutputValidator：fuzzy_match_threshold、auto_correct_case
      - 降级配置：enable_degradation、degradation_log_level
    - _Requirements: 2.6, 3.6, 4.4, 5.5, 6.7_

- [x] 2. RulePrefilter 实现
  - [x] 2.1 实现 RulePrefilter 核心逻辑
    - 创建 `analytics_assistant/src/agents/semantic_parser/components/rule_prefilter.py`
    - 实现语言检测、时间提示生成、计算种子匹配、复杂度检测
    - 使用 keywords_data.py 和 computation_seeds.py
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_
  
  - [ ] 2.2 编写 RulePrefilter 单元测试


    - 测试关键词匹配逻辑
    - 测试时间提示生成
    - 测试计算种子匹配
    - 测试置信度计算
    - _Requirements: 15.1_
  

  - [ ] 2.3 编写 RulePrefilter 属性测试


    - **Property 4: RulePrefilter 无 LLM 调用**
    - **Property 5: RulePrefilter 输入处理完整性**
    - **Property 6: 低置信度标记正确性**
    - **Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.6**

- [-] 3. FeatureExtractor 实现
  - [x] 3.1 实现 FeatureExtractor 核心逻辑
    - 创建 `analytics_assistant/src/agents/semantic_parser/components/feature_extractor.py`
    - 实现 LLM 调用、超时处理、降级逻辑
    - 使用快速模型（DeepSeek-V3）
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.6_
  
  - [x] 3.2 实现 FeatureExtractor Prompt
    - 创建 `analytics_assistant/src/agents/semantic_parser/prompts/feature_extractor_prompt.py`
    - 实现精简 Prompt（目标 ~200 tokens）
    - _Requirements: 3.5_
  
  - [ ] 3.3 编写 FeatureExtractor 单元测试


    - 测试超时降级行为
    - 测试输出结构验证
    - _Requirements: 15.2_
  

  - [ ] 3.4 编写 FeatureExtractor 属性测试


    - **Property 8: FeatureExtractor 超时降级**
    - **Property 9: FeatureExtractor Token 约束**
    - **Validates: Requirements 3.5, 3.6, 10.1**

- [ ] 4. Checkpoint - 确保所有测试通过
  - 运行 RulePrefilter 和 FeatureExtractor 测试
  - 确保所有测试通过，如有问题请询问用户

- [-] 5. FeatureCache 实现
  - [x] 5.1 实现 FeatureCache 核心逻辑
    - 创建 `analytics_assistant/src/agents/semantic_parser/components/feature_cache.py`
    - 实现精确匹配和语义相似匹配
    - 实现 TTL 过期和数据源隔离
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.6_
  
  - [ ] 5.2 编写 FeatureCache 单元测试


    - 测试精确匹配
    - 测试语义相似匹配
    - 测试 TTL 过期
    - 测试数据源隔离
    - _Requirements: 15.2_
  
  - [ ] 5.3 编写 FeatureCache 属性测试


    - **Property 10: FeatureCache 语义匹配**
    - **Property 11: FeatureCache 数据源隔离**
    - **Property 12: FeatureCache TTL 过期**
    - **Validates: Requirements 4.2, 4.3, 4.4, 4.6**

- [ ] 6. FieldRetriever 重构
  - [x] 6.1 重写 FieldRetriever 支持 Top-K + 置信度
    - 重写 `analytics_assistant/src/agents/semantic_parser/components/field_retriever.py`
    - 删除旧的 FieldRetriever 实现，直接替换为新实现
    - 实现基于 FeatureExtractionOutput 的检索
    - 返回 FieldRAGResult（Top-K 候选 + 置信度）
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_
  
  - [x] 6.2 清理历史遗留代码
    - 删除旧的 FieldRetriever 相关代码和测试
    - 更新所有引用 FieldRetriever 的调用方
    - 确保没有向下兼容的包袱
    - _Requirements: 5.1_
  
  - [ ] 6.3 编写 FieldRetriever 单元测试


    - 测试 Top-K 检索
    - 测试置信度排序
    - 测试降级模式
    - _Requirements: 15.3_
  
  - [ ] 6.4 编写 FieldRetriever 属性测试


    - **Property 13: FieldRetriever 基于特征检索**
    - **Property 14: FieldRAGResult 结构完整性**
    - **Property 15: FieldRetriever Top-K 约束**
    - **Property 16: FieldRetriever 置信度排序**
    - **Validates: Requirements 5.2, 5.3, 5.4, 5.5, 5.6**

- [x] 7. Checkpoint - 确保所有测试通过
  - 运行 FeatureCache 和 FieldRetriever 测试
  - 确保所有测试通过，如有问题请询问用户


- [ ] 8. DynamicSchemaBuilder 实现
  - [x] 8.1 实现 DynamicSchemaBuilder 核心逻辑
    - 创建 `analytics_assistant/src/agents/semantic_parser/components/dynamic_schema_builder.py`
    - 实现模块选择逻辑（base/time/computation/filter/clarification）
    - 实现字段收集和数量限制
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_
  
  - [ ] 8.2 编写 DynamicSchemaBuilder 单元测试


    - 测试模块选择逻辑
    - 测试字段数量限制
    - _Requirements: 15.4_
  
  - [ ]* 8.3 编写 DynamicSchemaBuilder 属性测试

    - **Property 17: DynamicSchemaBuilder 模块选择**
    - **Property 18: DynamicSchemaBuilder BASE 模块不变性**
    - **Property 19: DynamicSchemaBuilder 字段数量约束**
    - **Validates: Requirements 6.1, 6.3, 6.4, 6.5, 6.6, 6.7**

- [ ] 9. ModularPromptBuilder 实现
  - [x] 9.1 实现 ModularPromptBuilder 核心逻辑
    - 创建 `analytics_assistant/src/agents/semantic_parser/prompts/modular_prompt_builder.py`
    - 实现模块化 Prompt 组装
    - 实现计算种子插入和低置信度回退
    - 实现语言适配
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_
  
  - [ ]* 9.2 编写 ModularPromptBuilder 单元测试

    - 测试计算种子插入
    - 测试低置信度回退
    - 测试语言适配
    - _Requirements: 15.5_
  
  - [ ]* 9.3 编写 ModularPromptBuilder 属性测试

    - **Property 20: ModularPromptBuilder 内容插入**
    - **Property 21: ModularPromptBuilder 低置信度回退**
    - **Property 22: ModularPromptBuilder 语言适配**
    - **Validates: Requirements 7.2, 7.3, 7.4, 7.5, 13.1**

- [ ] 10. Checkpoint - 确保所有测试通过
  - 运行 DynamicSchemaBuilder 和 ModularPromptBuilder 测试
  - 确保所有测试通过，如有问题请询问用户

- [ ] 11. OutputValidator 实现
  - [x] 11.1 实现 OutputValidator 核心逻辑
    - 创建 `analytics_assistant/src/agents/semantic_parser/components/output_validator.py`
    - 实现字段验证、语法验证
    - 实现自动修正和澄清请求
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_
  
  - [ ]* 11.2 编写 OutputValidator 单元测试

    - 测试字段验证
    - 测试语法验证
    - 测试自动修正
    - _Requirements: 15.6_
  
  - [ ]* 11.3 编写 OutputValidator 属性测试

    - **Property 24: OutputValidator 字段验证**
    - **Property 25: OutputValidator 语法验证**
    - **Property 26: OutputValidator 自动修正**
    - **Property 27: OutputValidator 澄清请求**
    - **Validates: Requirements 8.2, 8.3, 8.4, 8.5**

- [x] 12. 集成与连接
  - [x] 12.1 更新 SemanticParser State
    - 修改 `analytics_assistant/src/agents/semantic_parser/state.py`
    - 添加 Phase14 相关状态字段：
      - `prefilter_result: Optional[PrefilterResult]`
      - `feature_extraction_output: Optional[FeatureExtractionOutput]`
      - `field_rag_result: Optional[FieldRAGResult]`
      - `dynamic_schema: Optional[dict]`
      - `modular_prompt: Optional[str]`
      - `validation_result: Optional[ValidationResult]`
      - `is_degraded: bool`
      - `phase14_metrics: Optional[dict]`
    - _Requirements: 1.1_
  
  - [x] 12.2 创建 Phase14 节点函数
    - 创建 `analytics_assistant/src/agents/semantic_parser/nodes/phase14_nodes.py`
    - 实现各阶段的 LangGraph 节点函数：
      - `rule_prefilter_node`: 调用 RulePrefilter
      - `feature_cache_node`: 检查 FeatureCache
      - `feature_extractor_node`: 调用 FeatureExtractor
      - `field_retriever_node`: 调用 FieldRetriever
      - `dynamic_schema_builder_node`: 调用 DynamicSchemaBuilder
      - `modular_prompt_builder_node`: 调用 ModularPromptBuilder
      - `output_validator_node`: 调用 OutputValidator
    - _Requirements: 1.1, 1.2, 1.3_
  
  - [x] 12.3 更新 SemanticParser Graph
    - 修改 `analytics_assistant/src/agents/semantic_parser/graph.py`
    - 集成 Phase14 节点到工作流
    - 添加条件路由：FeatureCache 命中时跳过 FeatureExtractor
    - 确保 11 阶段顺序执行
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 13. Checkpoint - 确保所有测试通过
  - 运行 OutputValidator 测试
  - 运行集成测试
  - 确保所有测试通过，如有问题请询问用户

- [ ] 14. 端到端测试与性能验证
  - [ ] 14.1 编写端到端集成测试


    - 测试完整 11 阶段执行流程
    - 测试缓存命中场景
    - 测试超时降级场景
    - 测试低置信度场景
    - _Requirements: 15.7_
  

  - [ ] 14.2 编写阶段顺序属性测试


    - **Property 1: 阶段执行顺序不变性**
    - **Property 2: FieldRetriever 依赖 FeatureExtractor**
    - **Property 3: 双 LLM 调用保证**
    - **Validates: Requirements 1.1, 1.2, 1.3, 1.4**
  
  - [ ] 14.3 编写置信度和降级属性测试


    - **Property 28: 置信度范围有效性**
    - **Property 29: 降级标记一致性**
    - **Validates: Requirements 9.1, 9.2, 9.3, 10.1, 10.2, 10.3, 10.4**
  
  - [ ] 14.4 编写性能基准测试


    - **Property 7: RulePrefilter 性能约束（50ms）**
    - **Property 23: ModularPromptBuilder Token 优化（60% 减少）**
    - 验证 Token 减少目标
    - _Requirements: 2.7, 7.6_

- [ ] 15. Final Checkpoint - 确保所有测试通过
  - 运行所有单元测试、属性测试、集成测试
  - 验证性能指标
  - 确保所有测试通过，如有问题请询问用户

## Notes

- 任务标记 `*` 为可选任务，可跳过以加快 MVP 开发
- 每个任务引用具体的需求以便追溯
- Checkpoint 任务确保增量验证
- 属性测试验证正确性属性，每个测试至少运行 100 次迭代
