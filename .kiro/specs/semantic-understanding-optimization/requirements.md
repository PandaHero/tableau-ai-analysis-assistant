# Requirements Document

## Introduction

本文档定义了语义理解优化（Phase 14）的需求规格。这是对现有语义解析器的优化架构，旨在通过"规则先行 + 双 LLM 验证"的方式，在保证准确性的同时大幅减少 Token 消耗。

### 核心设计原则

1. **规则先行 (Rules First)**：RulePrefilter 必须执行，提取信息以减轻 LLM 负担
2. **统一流程 (Unified Flow)**：所有查询都经过双 LLM（无分流），确保准确性
3. **第一步轻量 (Lightweight First Step)**：FeatureExtractor 使用快速模型验证+修正规则结果
4. **第二步精简 (Streamlined Second Step)**：基于第一步输出，裁剪 Prompt 和 Schema 以减少 Token
5. **种子文件充分利用 (Full Seed Utilization)**：计算公式种子直接插入 Prompt

### 关键架构约束

**FieldRetriever 必须在 FeatureExtractor 之后执行**，因为：
- FeatureExtractor 输出 `required_measures` 和 `required_dimensions`（如 ["利润", "销售额"], ["城市"]）
- FieldRetriever 使用这些输出进行 **Top-K 检索并返回置信度分数**（非精确匹配）
- Top-K 候选字段及其分数传递给主 LLM 进行最终选择
- **禁止并行执行**，因为 FieldRetriever 需要 LLM 确认的字段需求

### 预期收益

- Token 节省：SemanticUnderstanding 输入减少约 60%
- 准确性提升：规则 + LLM 双重验证
- 延迟影响：+200-300ms（FeatureExtractor），但主 LLM 推理更快
- 总体：Token 成本降低，准确性提升，延迟基本持平

## Glossary

- **RulePrefilter**: 规则预处理器，无 LLM 调用，使用关键词和规则提取特征
- **FeatureExtractor**: 特征提取器，使用快速 LLM 验证和修正规则结果
- **FeatureCache**: 特征缓存，缓存 FeatureExtractor 的输出
- **FieldRetriever**: 字段检索器，基于 FeatureExtractor 输出进行 Top-K 检索
- **DynamicSchemaBuilder**: 动态 Schema 构建器，根据特征裁剪 Schema
- **ModularPromptBuilder**: 模块化 Prompt 构建器，根据特征组装 Prompt 模块
- **OutputValidator**: 输出验证器，预验证 LLM 输出并自动修正
- **PrefilterResult**: 规则预处理结果，包含时间提示、计算种子、复杂度等
- **FeatureExtractionOutput**: 特征提取输出，包含 LLM 验证后的字段需求
- **FieldRAGResult**: 字段检索结果，包含 Top-K 候选字段及置信度分数
- **TimeHintGenerator**: 时间提示生成器，生成时间表达式的解析提示
- **Confidence_Score**: 置信度分数，表示系统对某个结果确定程度的数值（0-1）
- **Phase14Error**: Phase 14 异常基类，用于统一异常处理

## Requirements

### Requirement 1: 11 阶段优化架构

**User Story:** As a 系统架构师, I want 语义解析器采用 11 阶段优化架构, so that 在保证准确性的同时大幅减少 Token 消耗。

#### Acceptance Criteria

1. THE Semantic_Parser SHALL 按以下顺序执行 11 个阶段：IntentRouter → QueryCache → RulePrefilter → FeatureCache → FeatureExtractor → FieldRetriever → DynamicSchemaBuilder + ModularPromptBuilder → SemanticUnderstanding → OutputValidator → FilterValueValidator → QueryAdapter + 执行 + 缓存
2. THE FieldRetriever SHALL 在 FeatureExtractor 之后执行，使用其输出的 required_measures 和 required_dimensions
3. THE 系统 SHALL 禁止 FeatureExtractor 和 FieldRetriever 并行执行
4. THE 系统 SHALL 确保所有查询都经过双 LLM 调用（FeatureExtractor + SemanticUnderstanding）

### Requirement 2: RulePrefilter - 规则预处理

**User Story:** As a 系统管理员, I want 系统在 LLM 调用前进行规则预处理, so that 减轻 LLM 负担并提高准确性。

#### Acceptance Criteria

1. THE RulePrefilter SHALL 在 FeatureExtractor 之前执行，不调用 LLM
2. THE RulePrefilter SHALL 使用 keywords_data.py 进行意图分类和复杂度检测
3. THE RulePrefilter SHALL 使用 computation_seeds.py 进行计算公式匹配
4. THE RulePrefilter SHALL 使用 TimeHintGenerator 生成时间表达式解析提示
5. THE RulePrefilter SHALL 输出 PrefilterResult，包含：time_hints、matched_computations、detected_complexity、match_confidence
6. WHEN 规则匹配置信度低于阈值 THEN THE RulePrefilter SHALL 在输出中标记 low_confidence=true
7. THE RulePrefilter SHALL 在 50ms 内完成处理

### Requirement 3: FeatureExtractor - 特征提取

**User Story:** As a 开发者, I want 系统使用快速 LLM 验证规则结果, so that 在低延迟下确保特征提取的准确性。

#### Acceptance Criteria

1. THE FeatureExtractor SHALL 使用快速模型（如 DeepSeek-V3）进行特征提取
2. THE FeatureExtractor SHALL 接收 RulePrefilter 的输出作为输入
3. THE FeatureExtractor SHALL 验证并修正规则提取的时间提示和计算类型
4. THE FeatureExtractor SHALL 输出 FeatureExtractionOutput，包含：required_measures、required_dimensions、confirmed_time_hints、confirmed_computations、confirmation_confidence
5. THE FeatureExtractor SHALL 控制输入 Token 在 200 以内
6. WHEN FeatureExtractor 超时 THEN THE 系统 SHALL 降级使用规则模式（直接使用 PrefilterResult）
7. THE FeatureExtractor SHALL 在 300ms 内完成处理

### Requirement 4: FeatureCache - 特征缓存

**User Story:** As a 系统管理员, I want 系统缓存特征提取结果, so that 相似问题可以复用特征。

#### Acceptance Criteria

1. THE FeatureCache SHALL 缓存 FeatureExtractor 的输出
2. THE FeatureCache SHALL 使用问题文本的语义相似度作为缓存键
3. WHEN 语义相似度 > 0.95 THEN THE FeatureCache SHALL 返回缓存的特征
4. THE FeatureCache SHALL 支持配置缓存过期时间（默认 1 小时）
5. THE FeatureCache SHALL 与 QueryCache 独立管理
6. THE FeatureCache SHALL 在缓存键设计中包含 datasource_luid 以区分不同数据源

### Requirement 5: FieldRetriever - Top-K 字段检索

**User Story:** As a 开发者, I want 字段检索器输出 Top-K 候选字段及置信度分数, so that 主 LLM 可以从候选中选择正确字段。

#### Acceptance Criteria

1. THE FieldRetriever SHALL 在 FeatureExtractor 之后执行
2. THE FieldRetriever SHALL 使用 FeatureExtractionOutput 中的 required_measures 和 required_dimensions 进行检索
3. THE FieldRetriever SHALL 输出 FieldRAGResult，包含 measures、dimensions、time_fields 三个列表
4. THE FieldRAGResult 中每个字段 SHALL 包含：field_name、confidence、description、sample_values
5. THE FieldRetriever SHALL 为每类字段返回 Top-K 候选（默认 K=5）
6. THE FieldRetriever SHALL 按置信度降序排列候选字段
7. THE FieldRetriever SHALL 在 100ms 内完成检索

### Requirement 6: DynamicSchemaBuilder - 动态 Schema 构建

**User Story:** As a 系统管理员, I want 系统根据特征动态构建 Schema, so that 减少 Token 消耗。

#### Acceptance Criteria

1. THE DynamicSchemaBuilder SHALL 根据 FeatureExtractionOutput 选择 Schema 模块
2. THE DynamicSchemaBuilder SHALL 支持 5 种 Schema 模块：base、time、computation、filter、clarification
3. THE base 模块 SHALL 始终包含（核心字段和基础指令）
4. THE time 模块 SHALL 在检测到时间表达式时包含
5. THE computation 模块 SHALL 在检测到派生度量时包含
6. THE filter 模块 SHALL 在检测到筛选条件时包含
7. THE DynamicSchemaBuilder SHALL 限制返回字段数量不超过 MAX_FIELDS（默认 20）

### Requirement 7: ModularPromptBuilder - 模块化 Prompt 构建

**User Story:** As a 系统管理员, I want 系统根据特征模块化组装 Prompt, so that 优化 Token 使用并提升准确性。

#### Acceptance Criteria

1. THE ModularPromptBuilder SHALL 根据 FeatureExtractionOutput 选择 Prompt 模块
2. THE ModularPromptBuilder SHALL 将匹配的计算种子（computation_seeds.py）直接插入 Prompt
3. THE ModularPromptBuilder SHALL 将时间提示（TimeHintGenerator 输出）插入 Prompt
4. THE ModularPromptBuilder SHALL 根据检测到的语言调整 Prompt 内容
5. WHEN 置信度低于阈值 THEN THE ModularPromptBuilder SHALL 不插入计算种子（避免误导 LLM）
6. THE ModularPromptBuilder SHALL 确保 Prompt 总 Token 减少约 60%

### Requirement 8: OutputValidator - 输出预验证与自动修正

**User Story:** As a 开发者, I want 系统在执行前验证 LLM 输出, so that 减少不必要的执行错误和重试。

#### Acceptance Criteria

1. THE OutputValidator SHALL 在 SemanticUnderstanding 输出后立即执行
2. THE OutputValidator SHALL 验证字段引用的有效性（字段是否存在于 FieldRAGResult 中）
3. THE OutputValidator SHALL 验证计算表达式的语法正确性
4. WHEN 发现可自动修正的错误 THEN THE OutputValidator SHALL 自动修正
5. WHEN 发现不可修正的错误 THEN THE OutputValidator SHALL 标记并请求澄清
6. THE OutputValidator SHALL 减少对 ErrorCorrector 的依赖

### Requirement 9: 置信度传播机制

**User Story:** As a 开发者, I want 系统在各阶段传播置信度分数, so that 可以追踪和调试准确性问题。

#### Acceptance Criteria

1. THE PrefilterResult SHALL 包含 match_confidence 字段，表示规则匹配的置信度
2. THE FeatureExtractionOutput SHALL 包含 confirmation_confidence 字段，表示 LLM 确认的置信度
3. THE FieldRAGResult 中每个字段 SHALL 包含 confidence 字段
4. THE SemanticOutput SHALL 包含 overall_confidence 字段，综合各阶段置信度
5. WHEN 任一阶段置信度低于阈值（默认 0.7）THEN THE 系统 SHALL 在日志中记录警告

### Requirement 10: 降级策略

**User Story:** As a 系统管理员, I want 系统在异常情况下能够降级运行, so that 保证服务可用性。

#### Acceptance Criteria

1. WHEN FeatureExtractor 超时 THEN THE 系统 SHALL 降级使用规则模式（直接使用 PrefilterResult）
2. WHEN FeatureCache 不可用 THEN THE 系统 SHALL 跳过缓存直接调用 FeatureExtractor
3. WHEN FieldRetriever 失败 THEN THE 系统 SHALL 降级使用全量字段列表
4. THE 系统 SHALL 在降级时记录日志并设置 degraded=true 标记
5. THE 系统 SHALL 支持配置降级超时阈值（默认 FeatureExtractor 500ms）

### Requirement 11: 异常定义与处理

**User Story:** As a 开发者, I want 系统有清晰的异常层次结构, so that 便于调试和错误处理。

#### Acceptance Criteria

1. THE 系统 SHALL 定义 Phase14Error 作为异常基类
2. THE 系统 SHALL 定义 RulePrefilterError 用于规则预处理异常
3. THE 系统 SHALL 定义 FeatureExtractionError 用于特征提取异常
4. THE 系统 SHALL 定义 FeatureExtractorTimeoutError 用于特征提取超时
5. THE 系统 SHALL 定义 FieldRetrievalError 用于字段检索异常
6. THE 系统 SHALL 定义 OutputValidationError 用于输出验证异常
7. THE 所有异常 SHALL 包含 context 字段，记录异常发生时的上下文信息

### Requirement 12: 种子文件使用规范

**User Story:** As a 开发者, I want 系统正确使用各种种子文件, so that 充分利用领域知识。

#### Acceptance Criteria

1. THE keywords_data.py SHALL 用于 IntentRouter 和 RulePrefilter 的意图分类和复杂度检测
2. THE computation_seeds.py SHALL 用于 RulePrefilter 的公式匹配和 ModularPromptBuilder 的 Prompt 插入
3. THE rules_data.py SHALL 用于 IntentRouter 的无关问题过滤
4. THE seed_data.py SHALL 用于 DimensionHierarchyInference 的维度分类（现有功能）
5. THE 系统 SHALL 禁止将种子数据放入 app.yaml 配置文件

### Requirement 13: 低置信度回退

**User Story:** As a 系统管理员, I want 系统在低置信度时采取保守策略, so that 避免错误的计算种子误导 LLM。

#### Acceptance Criteria

1. WHEN PrefilterResult.match_confidence < 0.7 THEN THE ModularPromptBuilder SHALL 不插入计算种子
2. WHEN FeatureExtractionOutput.confirmation_confidence < 0.7 THEN THE 系统 SHALL 在日志中记录警告
3. WHEN 字段检索置信度 < 0.5 THEN THE FieldRetriever SHALL 扩大检索范围（增加 K 值）
4. THE 系统 SHALL 支持配置各阶段的置信度阈值

### Requirement 14: 性能监控与指标

**User Story:** As a 系统管理员, I want 系统记录各阶段的性能指标, so that 便于监控和调优。

#### Acceptance Criteria

1. THE 系统 SHALL 记录每个阶段的执行时间
2. THE 系统 SHALL 记录 FeatureExtractor 的输入/输出 Token 数
3. THE 系统 SHALL 记录 SemanticUnderstanding 的输入/输出 Token 数
4. THE 系统 SHALL 记录缓存命中率（QueryCache、FeatureCache）
5. THE 系统 SHALL 记录降级发生次数和原因
6. THE 系统 SHALL 支持通过 LangSmith 进行可观测性集成

### Requirement 15: 测试覆盖

**User Story:** As a 开发者, I want 优化架构有充分的测试覆盖, so that 代码质量得到保证。

#### Acceptance Criteria

1. THE RulePrefilter SHALL 包含关键词匹配和时间提示生成的单元测试
2. THE FeatureExtractor SHALL 包含超时降级的集成测试
3. THE FieldRetriever SHALL 包含 Top-K 检索和置信度排序的单元测试
4. THE DynamicSchemaBuilder SHALL 包含模块选择逻辑的单元测试
5. THE ModularPromptBuilder SHALL 包含种子插入和 Token 优化的单元测试
6. THE OutputValidator SHALL 包含自动修正逻辑的单元测试
7. THE 系统 SHALL 包含端到端的性能基准测试，验证 Token 减少 60% 的目标
