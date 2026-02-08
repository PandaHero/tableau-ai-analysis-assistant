# 实现计划：字段语义增强服务

## 概述

将现有 `dimension_hierarchy` 模块重构为 `field_semantic` 模块，支持维度和度量字段的统一语义分析，并生成增强的索引文本以改进 RAG 检索效果。

## 任务

- [x] 1. 创建模块目录结构和基础文件
  - [x] 1.1 创建 `field_semantic` 模块目录结构
    - 创建 `analytics_assistant/src/agents/field_semantic/` 目录
    - 创建 `schemas/`、`prompts/` 子目录
    - 创建各目录的 `__init__.py` 文件
    - _Requirements: 1.1, 1.2_
  
  - [x] 1.2 添加 MeasureCategory 枚举到 core/schemas/enums.py
    - 定义 MeasureCategory 枚举：revenue、cost、profit、quantity、ratio、count、average、other
    - _Requirements: 2.2_

- [x] 2. 实现数据模型
  - [x] 2.1 创建 FieldSemanticAttributes 模型
    - 在 `schemas/output.py` 中定义 FieldSemanticAttributes
    - 包含通用属性：role、business_description、aliases、confidence、reasoning
    - 包含维度属性：category、category_detail、level、granularity、parent_dimension、child_dimension
    - 包含度量属性：measure_category
    - 实现 model_validator 验证角色特定字段
    - _Requirements: 2.1, 2.3, 2.4_
  
  - [x] 2.2 编写 FieldSemanticAttributes 属性测试
    - **Property 1: 维度属性完整性**
    - **Property 2: 度量属性完整性**
    - **Validates: Requirements 2.3, 2.4**
  
  - [x] 2.3 创建 FieldSemanticResult 和 LLM 输出模型
    - 定义 FieldSemanticResult 模型
    - 定义 LLMFieldSemanticItem 和 LLMFieldSemanticOutput 模型
    - 实现 to_field_semantic_result() 转换方法
    - _Requirements: 2.5, 3.5, 3.6_
  
  - [x] 2.4 编写 LLM 输出转换属性测试
    - **Property 4: LLM 输出转换一致性**
    - **Validates: Requirements 3.6**

- [x] 3. 实现 Prompt 模板
  - [x] 3.1 创建统一的 System Prompt
    - 在 `prompts/prompt.py` 中定义 SYSTEM_PROMPT
    - 包含维度类别和度量类别的定义说明
    - 包含业务描述和别名生成的指导规则
    - 包含输出格式说明
    - _Requirements: 3.1, 3.2, 3.3_
  
  - [x] 3.2 实现 build_user_prompt 函数
    - 构建包含字段信息的用户提示
    - 支持 few-shot 示例
    - 包含 caption、data_type、role、sample_values 信息
    - _Requirements: 3.4_
  
  - [x] 3.3 编写 User Prompt 属性测试
    - **Property 3: User Prompt 字段信息完整性**
    - **Validates: Requirements 3.4**

- [x] 4. Checkpoint - 确保数据模型和 Prompt 测试通过
  - 运行所有测试，确保通过
  - 如有问题，询问用户

- [x] 5. 创建度量种子数据
  - [x] 5.1 创建 measure.py 种子数据文件
    - 在 `infra/seeds/measure.py` 中定义 MEASURE_SEEDS
    - 覆盖所有度量类别：revenue、cost、profit、quantity、ratio、count、average
    - 包含中文和英文字段名称
    - 每个条目包含：field_caption、data_type、measure_category、business_description、aliases、reasoning
    - _Requirements: 5.1, 5.2, 5.3, 5.4_
  
  - [x] 5.2 更新 seeds/__init__.py 导出
    - 导出 MEASURE_SEEDS 和 get_measure_few_shot_examples
    - _Requirements: 5.1_
  
  - [x] 5.3 编写种子数据结构属性测试
    - **Property 6: 度量种子数据结构完整性**
    - **Validates: Requirements 5.3**

- [x] 6. 实现索引文本增强
  - [x] 6.1 实现 build_enhanced_index_text 函数
    - 在 `inference.py` 中实现索引文本构建函数
    - 格式：`{caption}: {business_description}。别名: {aliases}。类型: {role}, {data_type}`
    - 处理空业务描述和空别名的边界情况
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_
  
  - [x] 6.2 编写索引文本格式属性测试
    - **Property 7: 索引文本格式正确性**
    - **Validates: Requirements 6.1, 6.2, 6.3**

- [x] 7. 实现推断服务核心逻辑
  - [x] 7.1 创建 FieldSemanticInference 类框架
    - 在 `inference.py` 中定义类结构
    - 实现 __init__ 方法，加载配置
    - 定义缓存和 RAG 相关属性
    - _Requirements: 4.1, 8.1, 8.2, 8.3_
  
  - [x] 7.2 实现缓存和增量计算逻辑
    - 复用现有的 CacheManager
    - 实现 compute_incremental_fields 函数
    - 实现缓存读写方法
    - _Requirements: 4.2, 4.4_
  
  - [x] 7.3 实现种子匹配逻辑
    - 构建维度和度量种子索引
    - 实现精确匹配方法
    - _Requirements: 4.2_
  
  - [x] 7.4 实现 RAG 检索逻辑
    - 复用现有的 RAGService
    - 实现 _rag_search 方法
    - 使用新的索引名称 `field_semantic_patterns`
    - _Requirements: 4.5, 7.1_
  
  - [x] 7.5 实现 LLM 推断逻辑
    - 实现 _llm_infer 方法
    - 使用 stream_llm_structured 获取结构化输出
    - 支持 on_token 回调
    - 实现重试机制
    - _Requirements: 4.6, 4.7, 9.1, 9.2_
  
  - [x] 7.6 实现自学习存储逻辑
    - 实现 _store_to_rag 方法
    - 存储高置信度结果到 RAG 索引
    - 使用增强的 index_text 作为检索内容
    - _Requirements: 7.2, 7.3, 7.4, 7.5_
  
  - [x] 7.7 编写高置信度存储属性测试
    - **Property 8: 高置信度结果存储**
    - **Validates: Requirements 7.2**
  
  - [x] 7.8 编写 RAG 文档结构属性测试
    - **Property 9: RAG 文档结构完整性**
    - **Validates: Requirements 7.3, 7.4**

- [x] 8. 实现主推断方法
  - [x] 8.1 实现 infer 异步方法
    - 整合缓存检查、增量计算、种子匹配、RAG 检索、LLM 推断、自学习存储
    - 实现并发控制（按 cache_key 粒度加锁）
    - 实现错误处理和降级策略
    - _Requirements: 4.1, 4.2, 4.3, 9.3, 9.4, 9.5_
  
  - [x] 8.2 编写增量推断缓存复用属性测试
    - **Property 5: 增量推断缓存复用**
    - **Validates: Requirements 4.2**
  
  - [x] 8.3 实现辅助方法
    - 实现 enrich_fields 方法
    - 实现 clear_cache 方法
    - 实现 get_result 方法
    - _Requirements: 4.1_

- [x] 9. Checkpoint - 确保推断服务测试通过
  - 运行所有测试，确保通过
  - 如有问题，询问用户

- [x] 10. 更新配置和模块导出
  - [x] 10.1 添加 app.yaml 配置节
    - 添加 `field_semantic` 配置节
    - 包含 high_confidence_threshold、max_retry_attempts、cache_namespace、pattern_namespace、incremental.enabled
    - _Requirements: 8.1, 8.2_
  
  - [x] 10.2 创建模块 __init__.py 导出
    - 导出 FieldSemanticInference、FieldSemanticResult、FieldSemanticAttributes
    - 导出 MeasureCategory、DimensionCategory
    - 导出便捷函数 infer_field_semantic
    - _Requirements: 1.4_

- [x] 11. 删除旧模块
  - [x] 11.1 删除 dimension_hierarchy 目录
    - 删除 `analytics_assistant/src/agents/dimension_hierarchy/` 目录
    - _Requirements: 1.3_
  
  - [x] 11.2 更新所有引用
    - 搜索并更新所有对 dimension_hierarchy 的引用
    - 更新为使用 field_semantic 模块
    - _Requirements: 1.3_

- [x] 12. Final Checkpoint - 确保所有测试通过
  - 运行完整测试套件
  - 确保所有属性测试和单元测试通过
  - 如有问题，询问用户

## 备注

- 每个任务引用具体的需求编号以便追溯
- Checkpoint 任务用于阶段性验证
- 属性测试验证通用正确性属性
- 单元测试验证特定示例和边界情况
