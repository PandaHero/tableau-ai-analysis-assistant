# 需求文档

## 简介

字段语义增强服务（Field Semantic Service）是对现有 `dimension_hierarchy` 模块的重构和扩展。该服务将支持所有字段类型（维度和度量）的语义分析，为每个字段生成业务描述和别名，以改进 RAG 检索的准确性。

核心目标是通过一次批量 LLM 调用同时获取：
- 维度字段的层级属性（category、level、granularity）
- 度量字段的类别属性（measure_category）
- 所有字段的业务描述（business_description）
- 所有字段的别名列表（aliases）

## 术语表

- **Field_Semantic_Service**: 字段语义增强服务，负责推断和管理字段的语义属性
- **Dimension_Field**: 维度字段，用于分组和筛选的字段（如地区、时间、产品类别）
- **Measure_Field**: 度量字段，用于聚合计算的数值字段（如销售额、数量、利润）
- **Semantic_Attributes**: 语义属性，包含字段的类别、层级、业务描述和别名
- **Measure_Category**: 度量类别枚举，包括 revenue/cost/profit/quantity/ratio/count/average/other
- **Dimension_Category**: 维度类别枚举，包括 time/geography/product/customer/organization/channel/financial/other
- **Index_Text**: 索引文本，用于向量检索的增强文本，包含业务描述和别名
- **RAG_Service**: 检索增强生成服务，用于向量检索和索引管理
- **Cache_Manager**: 缓存管理器，用于增量缓存策略

## 需求

### 需求 1：模块重命名与目录结构

**用户故事：** 作为开发者，我希望将 `dimension_hierarchy` 模块重命名为 `field_semantic`，以便模块名称准确反映其扩展后的功能范围。

#### 验收标准

1. THE Field_Semantic_Service SHALL 位于 `analytics_assistant/src/agents/field_semantic/` 目录下
2. THE Field_Semantic_Service SHALL 遵循现有 Agent 模块目录结构（schemas/、prompts/、components/）
3. WHEN 模块迁移完成后，THE System SHALL 删除旧的 `dimension_hierarchy` 目录
4. THE Field_Semantic_Service SHALL 在 `__init__.py` 中导出所有公共接口

### 需求 2：统一字段语义属性模型

**用户故事：** 作为开发者，我希望有一个统一的数据模型来表示维度和度量字段的语义属性，以便简化代码结构和数据处理。

#### 验收标准

1. THE Field_Semantic_Service SHALL 定义 `FieldSemanticAttributes` 模型，包含以下字段：
   - `role`: 字段角色（dimension/measure）
   - `category`: 维度类别（仅维度字段）
   - `category_detail`: 详细类别
   - `level`: 层级 1-5（仅维度字段）
   - `granularity`: 粒度描述（仅维度字段）
   - `measure_category`: 度量类别（仅度量字段）
   - `business_description`: 业务描述（所有字段）
   - `aliases`: 别名列表（所有字段）
   - `confidence`: 推断置信度
   - `reasoning`: 推断理由
2. THE Field_Semantic_Service SHALL 定义 `MeasureCategory` 枚举，包含：revenue、cost、profit、quantity、ratio、count、average、other
3. WHEN 字段为维度类型时，THE FieldSemanticAttributes SHALL 包含有效的 category、level、granularity 值
4. WHEN 字段为度量类型时，THE FieldSemanticAttributes SHALL 包含有效的 measure_category 值
5. THE Field_Semantic_Service SHALL 定义 `FieldSemanticResult` 模型，包含字段名到 FieldSemanticAttributes 的映射

### 需求 3：统一 LLM 推断 Prompt

**用户故事：** 作为开发者，我希望通过一次 LLM 调用同时获取所有字段的语义属性，以便减少 API 调用次数和延迟。

#### 验收标准

1. THE Field_Semantic_Service SHALL 定义统一的 System Prompt，指导 LLM 同时分析维度和度量字段
2. THE System Prompt SHALL 包含维度类别和度量类别的定义说明
3. THE System Prompt SHALL 包含业务描述和别名生成的指导规则
4. WHEN 构建 User Prompt 时，THE Field_Semantic_Service SHALL 包含字段的 caption、data_type、role、sample_values 信息
5. THE Field_Semantic_Service SHALL 定义 `LLMFieldSemanticOutput` 模型作为 LLM 结构化输出的 Schema
6. WHEN LLM 返回结果时，THE Field_Semantic_Service SHALL 将其转换为 FieldSemanticResult 模型

### 需求 4：推断服务实现

**用户故事：** 作为开发者，我希望有一个统一的推断服务来处理所有字段的语义分析，以便复用现有的缓存和 RAG 机制。

#### 验收标准

1. THE Field_Semantic_Service SHALL 实现 `FieldSemanticInference` 类，提供 `infer` 异步方法
2. THE FieldSemanticInference SHALL 支持增量推断策略：缓存 → 种子匹配 → RAG → LLM → 自学习
3. WHEN 调用 infer 方法时，THE FieldSemanticInference SHALL 接受 datasource_luid、fields、table_id 参数
4. THE FieldSemanticInference SHALL 复用现有的 CacheManager 进行缓存管理
5. THE FieldSemanticInference SHALL 复用现有的 RAGService 进行向量检索
6. WHEN 字段列表包含维度和度量时，THE FieldSemanticInference SHALL 在一次 LLM 调用中处理所有字段
7. THE FieldSemanticInference SHALL 支持 on_token 回调用于流式输出展示

### 需求 5：度量种子数据

**用户故事：** 作为开发者，我希望有预置的度量种子数据，以便通过精确匹配快速识别常见度量字段。

#### 验收标准

1. THE Field_Semantic_Service SHALL 在 `infra/seeds/` 目录下定义 `MEASURE_SEEDS` 数据
2. THE MEASURE_SEEDS SHALL 包含常见度量字段的语义属性，覆盖以下类别：
   - revenue: 收入类（销售额、营业收入、GMV 等）
   - cost: 成本类（成本、费用、支出等）
   - profit: 利润类（利润、毛利、净利等）
   - quantity: 数量类（数量、件数、订单数等）
   - ratio: 比率类（占比、增长率、转化率等）
   - count: 计数类（人数、次数、频次等）
   - average: 平均类（均价、平均值等）
3. EACH MEASURE_SEEDS 条目 SHALL 包含：field_caption、data_type、measure_category、business_description、aliases、reasoning
4. THE MEASURE_SEEDS SHALL 同时包含中文和英文字段名称

### 需求 6：索引文本增强

**用户故事：** 作为开发者，我希望使用增强后的索引文本构建向量索引，以便提高字段检索的准确性。

#### 验收标准

1. WHEN 构建 FieldChunk 时，THE Field_Semantic_Service SHALL 生成增强的 index_text
2. THE 增强的 index_text SHALL 采用自然语言描述格式，包含：
   - 字段显示名称（caption）
   - 业务描述（business_description）
   - 别名列表（aliases）
   - 字段角色（role）
   - 数据类型（data_type）
3. THE index_text 格式 SHALL 为：`{caption}: {business_description}。别名: {aliases}。类型: {role}, {data_type}`
4. WHEN 字段没有业务描述时，THE Field_Semantic_Service SHALL 使用字段 caption 作为默认描述
5. WHEN 字段没有别名时，THE Field_Semantic_Service SHALL 省略别名部分

### 需求 7：RAG 索引更新

**用户故事：** 作为开发者，我希望字段语义属性能够自动更新到 RAG 索引，以便后续检索能够利用增强的语义信息。

#### 验收标准

1. THE Field_Semantic_Service SHALL 定义新的 RAG 索引名称 `field_semantic_patterns`
2. WHEN 高置信度推断结果产生时，THE Field_Semantic_Service SHALL 将其存入 RAG 索引
3. THE RAG 索引文档 SHALL 包含增强的 index_text 作为检索内容
4. THE RAG 索引文档 metadata SHALL 包含：field_caption、role、category/measure_category、source、verified
5. THE Field_Semantic_Service SHALL 支持增量更新 RAG 索引

### 需求 8：配置管理

**用户故事：** 作为开发者，我希望所有可配置参数都在 app.yaml 中管理，以便灵活调整服务行为。

#### 验收标准

1. THE Field_Semantic_Service SHALL 从 `app.yaml` 读取配置，配置节名称为 `field_semantic`
2. THE 配置 SHALL 包含以下参数：
   - `high_confidence_threshold`: 高置信度阈值（默认 0.85）
   - `max_retry_attempts`: 最大重试次数（默认 3）
   - `cache_namespace`: 缓存命名空间
   - `pattern_namespace`: 模式存储命名空间
   - `incremental.enabled`: 是否启用增量推断
3. IF 配置读取失败，THEN THE Field_Semantic_Service SHALL 使用默认值并记录警告日志

### 需求 9：错误处理

**用户故事：** 作为开发者，我希望服务能够优雅地处理各种错误情况，以便保证系统稳定性。

#### 验收标准

1. IF LLM 调用失败，THEN THE Field_Semantic_Service SHALL 重试最多 max_retry_attempts 次
2. IF 所有重试都失败，THEN THE Field_Semantic_Service SHALL 返回空结果并记录错误日志
3. IF RAG 检索失败，THEN THE Field_Semantic_Service SHALL 跳过 RAG 阶段，继续 LLM 推断
4. IF 缓存操作失败，THEN THE Field_Semantic_Service SHALL 继续执行推断，不影响主流程
5. WHEN 发生错误时，THE Field_Semantic_Service SHALL 记录详细的错误信息和上下文
