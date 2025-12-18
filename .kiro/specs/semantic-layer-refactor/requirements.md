# 需求文档

## 简介

本规格文档定义了 Semantic Parser Agent（语义解析 Agent）和语义层重构的需求。核心目标是：
1. 建立一个**高度抽象、平台无关**的语义层，支持多 BI 平台（Tableau、Power BI、Superset 等）
2. 让 LLM 输出纯粹的**用户意图表示**，而非平台特定的技术实现
3. 增强问题理解能力，支持问题重述、意图分类、澄清问题等功能
4. 平台适配器负责将语义层转换为具体平台的查询语句

### 背景

当前系统存在以下问题：
1. **语义层与 Tableau 强耦合**：现有模型使用 Tableau 特定概念（LOD、TableCalc），无法扩展到其他 BI 平台
2. **表计算/LOD 决策硬编码**：`ImplementationResolver` 使用硬编码规则，无法处理复杂场景
3. **转换逻辑复杂**：QueryBuilder 需要理解业务意图并推断技术实现，容易出错
4. **问题理解不完整**：缺少问题重述、意图分类、澄清问题等关键功能

### 解决方案

重构后的架构采用**意图驱动、平台无关**的设计：

- **Semantic Parser Agent**：输出 `SemanticParseResult`，包含重述问题、意图分类、语义查询
- **SemanticQuery**：平台无关的语义层模型
- **PlatformAdapter**：平台适配器，将 SemanticQuery 转换为平台特定查询

### 核心理论

**三元模型**：所有查询 = What × Where × How
- What（目标）：要计算什么数据（度量 + 聚合方式）
- Where（范围）：在什么范围内查看（维度 + 筛选）
- How（操作）：怎么计算（简单聚合 / 复杂计算）

**计算模型**：计算 = 目标 × 分区 × 操作
- partition_by 是统一所有复杂计算的核心抽象

**LLM 组合架构**：Step 1 + Step 2 + Observer 形成闭环
- Step 1：语义理解与问题重述（直觉）
- Step 2：计算推理与自我验证（推理）
- Observer：一致性检查（元认知，按需介入）

## 术语表

- **Semantic Parser Agent**: 语义解析 Agent
- **SemanticParseResult**: Agent 输出的完整解析结果
- **SemanticQuery**: 平台无关的语义查询模型
- **Computation**: 计算定义 = 目标 × 分区 × 操作
- **partition_by**: 分区维度，决定计算的粒度和方向
- **HowType**: 计算类型枚举（SIMPLE、RANKING、CUMULATIVE、COMPARISON、GRANULARITY）
- **OperationType**: 操作类型枚举（RANK、RUNNING_SUM、PERCENT、FIXED 等）
- **IntentType**: 意图类型枚举（DATA_QUERY、CLARIFICATION、GENERAL、IRRELEVANT）
- **PlatformAdapter**: 平台适配器接口
- **FieldMapper**: 字段映射器
- **Step2Validation**: Step 2 的自我验证结果
- **Observer**: 一致性检查器（按需介入）
- **ObserverDecision**: Observer 的决策（ACCEPT/CORRECT/RETRY/CLARIFY）

## 需求

### 需求 1：问题重述（Step 1 核心功能）

**用户故事：** 作为系统用户，我希望系统能够将跟进问题补全为完整问题。

#### 验收标准

1. WHEN 用户提出跟进问题且存在历史对话 THEN 系统 SHALL 将跟进问题与历史上下文合并为完整的三元组（What × Where × How）
2. WHEN 用户问题引用了历史对话中的实体 THEN 系统 SHALL 将引用替换为具体实体
3. WHEN 用户问题是独立问题 THEN 系统 SHALL 原样保留问题
4. WHEN 系统重述问题 THEN 系统 SHALL 生成语义化重述，必须保留分区意图（每月、每省、当月、全国等）

### 需求 2：意图分类（Step 1 核心功能）

**用户故事：** 作为系统开发者，我希望系统能够准确分类用户问题的意图。

#### 验收标准

1. WHEN 用户问题包含可查询的字段且信息完整 THEN 系统 SHALL 将意图分类为 DATA_QUERY
2. WHEN 用户问题引用了未指定的值或需要澄清 THEN 系统 SHALL 将意图分类为 CLARIFICATION
3. WHEN 用户问题询问数据集描述、字段信息 THEN 系统 SHALL 将意图分类为 GENERAL
4. WHEN 用户问题与数据分析无关 THEN 系统 SHALL 将意图分类为 IRRELEVANT
5. WHEN 系统分类意图 THEN 系统 SHALL 同时输出分类理由（reasoning）

### 需求 3：意图分支处理

**用户故事：** 作为系统架构师，我希望不同意图走不同的处理分支。

#### 验收标准

1. WHEN 意图为 DATA_QUERY THEN 系统 SHALL 继续处理（判断 how_type）
2. WHEN 意图为 CLARIFICATION THEN 系统 SHALL 生成澄清问题并返回
3. WHEN 意图为 GENERAL THEN 系统 SHALL 生成通用响应并返回
4. WHEN 意图为 IRRELEVANT THEN 系统 SHALL 拒绝处理并返回提示

### 需求 4：澄清问题生成

**用户故事：** 作为系统用户，我希望当我的问题不够清晰时，系统能够生成澄清问题。

#### 验收标准

1. WHEN 意图为 CLARIFICATION THEN 系统 SHALL 生成具体的澄清问题
2. WHEN 用户问题引用了未指定的值 THEN 系统 SHALL 基于数据源元数据提供可选值列表（options）
3. WHEN 系统生成澄清问题 THEN 系统 SHALL 保持友好和简洁的语气

### 需求 5：语义查询输出

**用户故事：** 作为系统架构师，我希望 Agent 输出平台无关的语义查询。

#### 验收标准

1. WHEN Agent 处理 DATA_QUERY 意图 THEN 系统 SHALL 输出平台无关的 SemanticQuery
2. WHEN Agent 输出语义查询 THEN 系统 SHALL 使用业务术语作为字段名
3. WHEN how_type 为 SIMPLE THEN 系统 SHALL 跳过 Step 2，直接构建查询

### 需求 6：Step 2 计算推理

**用户故事：** 作为开发者，我希望 Step 2 能够从重述问题推断计算定义。

#### 验收标准

1. WHEN how_type 不为 SIMPLE THEN 系统 SHALL 触发 Step 2 计算推理
2. WHEN Step 2 推断计算 THEN 系统 SHALL 从 restated_question 推断 target、partition_by、operation
3. WHEN Step 2 输出 THEN 系统 SHALL 包含推理过程（reasoning）

### 需求 7：Step 2 自我验证

**用户故事：** 作为系统架构师，我希望 Step 2 能够自我验证推理结果。

#### 验收标准

1. WHEN Step 2 推断 target THEN 系统 SHALL 验证 target 是否在 what.measures 中（target_check）
2. WHEN Step 2 推断 partition_by THEN 系统 SHALL 验证 partition_by 中的维度是否都在 where.dimensions 中（partition_by_check）
3. WHEN Step 2 推断 operation.type THEN 系统 SHALL 验证 operation.type 是否与 how_type 匹配（operation_check）
4. WHEN Step 2 验证不通过 THEN 系统 SHALL 输出 inconsistencies 列表并设置 all_valid 为 False

### 需求 8：Observer 一致性检查

**用户故事：** 作为系统架构师，我希望有 Observer 检查 Step 1 和 Step 2 的一致性。

#### 验收标准

1. WHEN Step 2 验证通过（all_valid == True）THEN 系统 SHALL 不触发 Observer，直接输出结果
2. WHEN Step 2 验证不通过（all_valid == False）THEN 系统 SHALL 触发 Observer 介入
3. WHEN Observer 检查一致性 THEN 系统 SHALL 检查重述完整性、结构一致性、语义一致性
4. WHEN Observer 发现小冲突 THEN 系统 SHALL 尝试修正并输出 CORRECT 决策
5. WHEN Observer 发现大冲突 THEN 系统 SHALL 输出 RETRY 或 CLARIFY 决策

### 需求 9：支持复杂计算类型

**用户故事：** 作为开发者，我希望新语义层支持多种复杂计算类型。

#### 验收标准

1. WHEN 用户询问排名 THEN 系统 SHALL 生成 Computation，operation.type 为 RANK 或 DENSE_RANK
2. WHEN 用户询问累计 THEN 系统 SHALL 生成 Computation，operation.type 为 RUNNING_SUM 或 RUNNING_AVG
3. WHEN 用户询问移动计算 THEN 系统 SHALL 生成 Computation，operation.type 为 MOVING_AVG 或 MOVING_SUM
4. WHEN 用户询问占比 THEN 系统 SHALL 生成 Computation，operation.type 为 PERCENT
5. WHEN 用户询问同比/环比 THEN 系统 SHALL 生成 Computation，operation.type 为 YEAR_AGO 或 PERIOD_AGO
6. WHEN 用户询问固定粒度聚合 THEN 系统 SHALL 生成 Computation，operation.type 为 FIXED

### 需求 10：支持过滤器类型

**用户故事：** 作为开发者，我希望新语义层支持多种过滤器类型。

#### 验收标准

1. WHEN 用户指定集合筛选 THEN 系统 SHALL 生成 SetFilter
2. WHEN 用户指定日期范围筛选 THEN 系统 SHALL 生成 DateRangeFilter
3. WHEN 用户指定数值范围筛选 THEN 系统 SHALL 生成 NumericRangeFilter
4. WHEN 用户指定文本匹配筛选 THEN 系统 SHALL 生成 TextMatchFilter
5. WHEN 用户指定 Top N 筛选 THEN 系统 SHALL 生成 TopNFilter

### 需求 11：平台适配器转换

**用户故事：** 作为开发者，我希望平台适配器负责将语义层转换为平台特定查询。

#### 验收标准

1. WHEN 平台适配器接收 SemanticQuery THEN 系统 SHALL 将其转换为平台特定查询
2. WHEN 平台适配器转换 Computation THEN 系统 SHALL 根据 partition_by 转换为平台分区语法
3. WHEN 语义层输出不符合平台要求 THEN 适配器 SHALL 尝试自动修正（填充默认值）
4. WHEN 自动修正无法解决问题 THEN 适配器 SHALL 返回详细的错误信息（ValidationResult）

### 需求 12：FieldMapper 保持不变

**用户故事：** 作为开发者，我希望 FieldMapper 保持不变。

#### 验收标准

1. WHEN FieldMapper 接收语义查询 THEN 系统 SHALL 使用现有的两阶段检索将业务术语映射到技术字段名
2. WHEN FieldMapper 处理 Computation 中的字段名 THEN 系统 SHALL 映射 target 和 partition_by 中的每个字段

### 需求 13：完整的验证逻辑

**用户故事：** 作为开发者，我希望新语义层模型有完整的验证。

#### 验收标准

1. WHEN 创建 Computation THEN 系统 SHALL 验证 target 不为空
2. WHEN 创建 Computation THEN 系统 SHALL 验证 partition_by 是字符串列表
3. WHEN 验证失败 THEN 系统 SHALL 返回 ValidationResult，包含错误类型、字段路径、消息和修复建议

### 需求 14：Schema 字段描述精简化

**用户故事：** 作为开发者，我希望 Schema 字段描述简洁且自包含，以便 LLM 注意力在字段生成时集中在最相关的信息上。

#### 验收标准

1. WHEN 定义 Schema 字段描述 THEN 系统 SHALL 将每个字段的描述限制在 100 tokens 以内
2. WHEN 定义 Schema 字段描述 THEN 系统 SHALL 使用 XML 标签（`<what>`、`<when>`、`<rule>`、`<must_not>`）来结构化内容
3. WHEN 定义 Schema 字段描述 THEN 系统 SHALL 在字段描述本身中包含所有必要的决策规则（自包含）
4. WHEN 定义条件字段 THEN 系统 SHALL 使用 `<must_not>` 标签强调负面约束

### 需求 15：Prompt 和 Schema 职责分离

**用户故事：** 作为开发者，我希望 Prompt 和 Schema 有清晰的职责分离，以便没有冗余且每个组件服务于其独特目的。

#### 验收标准

1. WHEN 编写 Prompt 内容 THEN 系统 SHALL 仅包含高层概念（什么是维度、什么是度量），不引用具体字段名
2. WHEN 编写 Schema 内容 THEN 系统 SHALL 包含所有具体的填写规则
3. WHEN 相同信息同时出现在 Prompt 和 Schema 中 THEN 系统 SHALL 从 Prompt 中删除重复内容，仅保留在 Schema 中
4. WHEN 定义决策规则 THEN 系统 SHALL 使用 `<rule>` 标签将其放在 Schema 字段描述中

### 需求 16：决策树格式优化

**用户故事：** 作为开发者，我希望决策树格式针对 LLM tokenization 进行优化，以便决策逻辑被模型高效处理。

#### 验收标准

1. WHEN 表示决策树 THEN 系统 SHALL 使用简单文本格式而非 ASCII 艺术（│、├、─、►）
2. WHEN 表示填写顺序 THEN 系统 SHALL 使用带括号条件的编号列表
3. WHEN 表示条件逻辑 THEN 系统 SHALL 使用内联格式（如"4. order (if type=ranking)"）
4. WHEN 决策树复杂 THEN 系统 SHALL 将其拆分为多个较小的决策块

### 需求 17：负面约束强调

**用户故事：** 作为开发者，我希望负面约束被突出强调，以便 LLM 更可能避免常见错误。

#### 验收标准

1. WHEN 字段有不可违反的关键约束 THEN 系统 SHALL 使用 `<must_not>` 标签并提供清晰的错误描述
2. WHEN 定义反模式 THEN 系统 SHALL 将其放在 `<rule>` 部分之后以获得最大可见性
3. WHEN 约束违反会导致系统错误 THEN 系统 SHALL 在约束描述中包含"(will cause error)"
4. WHEN 存在多个负面约束 THEN 系统 SHALL 按严重程度排序（最关键的在前）

### 需求 18：Class Docstring 精简

**用户故事：** 作为开发者，我希望 Class Docstring 示例简洁，以便复杂示例不会稀释对字段级描述的注意力。

#### 验收标准

1. WHEN 编写 Class Docstring 示例 THEN 系统 SHALL 在 docstring 中最多包含 2 个简单示例
2. WHEN 需要复杂示例 THEN 系统 SHALL 将其放在 Prompt 的 few-shot 部分而非 Schema 中
3. WHEN 编写 Class Docstring THEN 系统 SHALL 专注于模型的目的和关键约束，而非详尽的示例
4. WHEN 在 Class Docstring 中包含反模式 THEN 系统 SHALL 限制为 2-3 个最常见的错误

