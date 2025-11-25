# Requirements Document

## Introduction

本规范定义了 Tableau Assistant 的 Prompt 系统重构需求。当前的 prompt 模板存在冗余、通用性差、数据模型不一致等问题，需要参考优秀项目（如 bettafish）的设计模式，建立清晰、可维护、高效的 prompt 架构。

## Glossary

- **Prompt System**: 提示词系统，包含所有 Agent 的提示词模板和基础架构
- **Question Boost Agent**: 问题增强代理，将模糊问题转化为精确的分析问题
- **Understanding Agent**: 问题理解代理，解析问题并拆分为可执行的子问题
- **Task Planner Agent**: 任务规划代理，将子问题转换为 VizQL 查询规格
- **VizQL**: Tableau 的查询语言，用于数据查询和可视化
- **Dimension Hierarchy**: 维度层级，描述维度字段的粒度级别（1-5级）
- **Metadata**: 元数据，包含数据源的字段信息、类型、统计信息等
- **Pydantic Model**: Python 数据验证库，用于定义结构化数据模型
- **JSON Schema**: JSON 数据结构的规范定义
- **Field Mapping**: 字段映射，将用户使用的业务术语（如"销售额"、"地区"）映射到数据源中的技术字段名（如"收入"、"pro_name"）
- **Business Term**: 业务术语，用户在问题中使用的自然语言词汇
- **Technical Field**: 技术字段，数据源中实际存在的字段名称

## Requirements

### Requirement 1: 维度层级预处理

**User Story:** 作为系统架构师，我希望维度层级推断在问题处理前完成，以便所有 Agent 都能访问完整的元数据信息

#### Acceptance Criteria

1. WHEN THE System 启动时，THE Metadata Manager SHALL 自动执行维度层级推断并缓存结果
2. WHEN 用户提交问题时，THE System SHALL 使用已缓存的维度层级信息，而不是重新推断
3. WHEN Question Boost Agent 执行时，THE Agent SHALL 能够访问包含维度层级的完整元数据
4. WHEN Understanding Agent 执行时，THE Agent SHALL 能够访问包含维度层级的完整元数据
5. WHEN Task Planner Agent 执行时，THE Agent SHALL 能够访问包含维度层级的完整元数据

### Requirement 2: 数据模型严格遵守

**User Story:** 作为开发者，我希望所有 Agent 的输入输出严格遵守 Pydantic 数据模型，以确保数据一致性和类型安全

#### Acceptance Criteria

1. WHEN Question Boost Agent 输出结果时，THE Output SHALL 完全符合 QuestionBoost 模型定义
2. WHEN Understanding Agent 输出结果时，THE Output SHALL 完全符合 QuestionUnderstanding 模型定义
3. WHEN Task Planner Agent 输出结果时，THE Output SHALL 完全符合 QueryPlanningResult 模型定义
4. WHEN Agent 输出包含额外字段时，THE System SHALL 拒绝该输出并报错
5. WHEN Agent 输出缺少必填字段时，THE System SHALL 拒绝该输出并报错
6. WHEN Agent 输出字段类型不匹配时，THE System SHALL 拒绝该输出并报错

### Requirement 3: VizQL 能力完整解析

**User Story:** 作为问题理解专家，我希望 Understanding Agent 能够基于 VizQL 查询能力完整解析问题，以便准确拆分子问题

#### Acceptance Criteria

1. WHEN Understanding Agent 分析问题时，THE Agent SHALL 参考 VIZQL_CAPABILITIES 规则进行问题拆分
2. WHEN 问题可以用单个 VizQL 查询完成时，THE Agent SHALL NOT 拆分问题
3. WHEN 问题需要多个独立 VizQL 查询时，THE Agent SHALL 拆分为多个子问题
4. WHEN 问题包含多时间段对比时，THE Agent SHALL 按时间段拆分子问题
5. WHEN 问题包含占比计算时，THE Agent SHALL 拆分为总计和明细两个子问题
6. WHEN 问题包含"为什么"等探索式分析时，THE Agent SHALL NOT 拆分问题，并标记 needs_exploration=true

### Requirement 4: 子问题关系标注

**User Story:** 作为数据处理器开发者，我希望子问题之间的关系被明确标注，以便正确处理查询结果

#### Acceptance Criteria

1. WHEN Understanding Agent 拆分出多个子问题时，THE Agent SHALL 在 sub_question_relationships 字段中标注关系
2. WHEN 子问题是时间对比时，THE Relationship type SHALL 为 "comparison"，comparison_dimension SHALL 为 "time"
3. WHEN 子问题是维度对比时，THE Relationship type SHALL 为 "comparison"，comparison_dimension SHALL 为 "dimension"
4. WHEN 子问题是总体与部分关系时，THE Relationship type SHALL 为 "breakdown"
5. WHEN 子问题是粒度钻取时，THE Relationship type SHALL 为 "drill_down"
6. WHEN 子问题之间无关联时，THE Relationship type SHALL 为 "independent"

### Requirement 5: Prompt 模板重构

**User Story:** 作为 Prompt 工程师，我希望 Prompt 模板简洁、清晰、通用性强，以提高 LLM 的理解和执行效果

#### Acceptance Criteria

1. WHEN 创建新的 Prompt 基类时，THE BasePrompt SHALL 包含 get_system_message、get_user_template、get_output_model 三个抽象方法
2. WHEN 格式化消息时，THE BasePrompt SHALL 自动注入 JSON Schema 到提示词中
3. WHEN Question Boost Prompt 执行时，THE Prompt SHALL 专注于问题增强任务，使用业务术语而非技术字段名
4. WHEN Understanding Prompt 执行时，THE Prompt SHALL 专注于问题理解和拆分，使用业务术语而非技术字段名
5. WHEN Task Planner Prompt 执行时，THE Prompt SHALL 专注于查询规划，负责将业务术语映射到技术字段并生成 VizQL 规格
6. WHEN Prompt 包含业务规则时，THE Rules SHALL 以原则（Principles）形式呈现，而非详细的步骤列表
7. WHEN Prompt 需要示例时，THE Examples SHALL 简洁且具有代表性，不超过 3 个

### Requirement 6: 智能字段映射

**User Story:** 作为任务规划专家，我希望 Task Planner Agent 能够基于元数据信息智能地将业务术语映射到技术字段名，而不依赖硬编码规则

#### Acceptance Criteria

1. WHEN Task Planner Agent 接收到业务术语时，THE Agent SHALL 分析 metadata 中所有字段的 fieldCaption、category、dataType 信息
2. WHEN Task Planner Agent 映射维度字段时，THE Agent SHALL 基于 dimension_hierarchy 中的 level 和 unique_count 选择合适粒度
3. WHEN Task Planner Agent 选择维度粒度时，THE Agent SHALL 优先选择 level=1-2（粗粒度）的字段，避免 level=5（细粒度）的字段
4. WHEN Task Planner Agent 映射度量字段时，THE Agent SHALL 基于字段的 dataType（数值型）和语义相似度选择最匹配的字段
5. WHEN Task Planner Agent 无法确定唯一匹配时，THE Agent SHALL 在 rationale 中说明选择理由
6. WHEN 元数据包含字段描述或别名时，THE Agent SHALL 利用这些信息提高映射准确性

### Requirement 7: Agent 职责分离

**User Story:** 作为系统架构师，我希望各个 Agent 的职责清晰分离，避免职责重叠和信息泄露

#### Acceptance Criteria

1. WHEN Question Boost Agent 执行时，THE Agent SHALL ONLY 使用业务术语，不涉及技术字段名
2. WHEN Understanding Agent 执行时，THE Agent SHALL ONLY 使用业务术语，不涉及技术字段名
3. WHEN Task Planner Agent 执行时，THE Agent SHALL 负责将业务术语映射到技术字段名
4. WHEN Question Boost Agent 输出时，THE Output SHALL NOT 包含任何技术字段名或元数据引用
5. WHEN Understanding Agent 输出时，THE Output SHALL NOT 包含任何技术字段名或元数据引用
6. WHEN Task Planner Agent 输出时，THE Output SHALL ONLY 包含技术字段名，不使用业务术语

### Requirement 8: 测试流程优化

**User Story:** 作为测试工程师，我希望测试流程能够正确反映实际运行流程，以发现潜在问题

#### Acceptance Criteria

1. WHEN 测试开始时，THE Test SHALL 首先执行元数据获取和维度层级推断
2. WHEN 测试执行 Agent 时，THE Test SHALL 传递包含完整元数据的状态对象
3. WHEN 测试验证输出时，THE Test SHALL 检查输出是否符合对应的 Pydantic 模型
4. WHEN 测试发现数据模型不一致时，THE Test SHALL 报告详细的错误信息
5. WHEN 测试验证子问题关系时，THE Test SHALL 检查 sub_question_relationships 字段是否正确标注
