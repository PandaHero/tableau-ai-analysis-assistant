# Requirements Document

## Introduction

本规范定义了 Tableau Assistant 日期解析系统的增强需求。当前系统依赖 LLM 在 Understanding Agent 中识别日期表达式，但缺少独立的提取和验证阶段，对复杂时间表达式（如"从1月到3月"、"2024年底到现在"）的支持不完整。通过借鉴 Datus-agent 的两阶段日期解析思路，使用代码逻辑实现日期提取、解析和验证，提升日期处理的准确性和可靠性。

## Glossary

- **Date Expression**: 日期表达式，用户在问题中使用的时间相关文本（如"最近3个月"、"2024年第一季度"）
- **Time Range**: 时间范围，解析后的具体日期区间（如 2024-10-15 to 2025-01-15）
- **Reference Date**: 参考日期，用于计算相对时间的基准日期（通常为当前日期或数据最大日期）
- **Absolute Time**: 绝对时间，明确指定的日期或时间段（如"2016年"、"2024-Q1"）
- **Relative Time**: 相对时间，相对于参考日期的时间表达式（如"最近3个月"、"上周"）
- **Date Extraction**: 日期提取，从自然语言中识别所有时间相关表达式的过程
- **Date Parsing**: 日期解析，将时间表达式转换为具体日期范围的过程
- **Date Validation**: 日期验证，检查解析后的日期范围是否合理的过程
- **Confidence Score**: 置信度分数，表示日期解析结果可靠性的数值（0.0-1.0）
- **Understanding Agent**: 问题理解代理，负责理解用户问题并提取关键信息
- **TimeRange Model**: 时间范围模型，Pydantic 数据模型，用于存储时间范围信息
- **max_date**: 数据源中的最大日期，用作相对时间计算的参考点
- **Week Start Day**: 周起始日，指定一周从哪一天开始（周一或周日）
- **Holiday**: 节假日，特殊的日期标记（如春节、国庆节等）

## Requirements

### Requirement 1: 日期表达式提取增强

**User Story:** 作为系统开发者，我希望 Understanding Agent 能够准确识别问题中的所有日期表达式，包括复杂的范围表达式和中文表达式

#### Acceptance Criteria

1. WHEN 用户问题包含单个日期时，THE System SHALL 提取该日期表达式（如"2024年"、"去年12月"）
2. WHEN 用户问题包含日期范围时，THE System SHALL 提取完整的范围表达式（如"从1月到3月"、"2024年初到现在"）
3. WHEN 用户问题包含多个日期表达式时，THE System SHALL 提取所有日期表达式并保持顺序
4. WHEN 用户问题包含中文日期表达式时，THE System SHALL 正确识别中文表达（如"最近3个月"、"上季度"、"去年同期"）
5. WHEN 用户问题包含英文日期表达式时，THE System SHALL 正确识别英文表达（如"last 3 months"、"Q1 2024"）
6. WHEN 用户问题不包含日期表达式时，THE System SHALL 返回空列表而不是错误

### Requirement 2: TimeRange 模型扩展

**User Story:** 作为数据模型设计者，我希望 TimeRange 模型能够支持更复杂的时间表达式，包括范围起止、置信度等信息

#### Acceptance Criteria

1. WHEN TimeRange 存储日期范围时，THE Model SHALL 同时包含 start_date 和 end_date 字段
2. WHEN TimeRange 存储单个日期时，THE Model SHALL 允许 start_date 和 end_date 相同
3. WHEN TimeRange 被创建时，THE Model SHALL 包含 original_text 字段存储原始表达式
4. WHEN TimeRange 被创建时，THE Model SHALL 包含 confidence 字段存储置信度分数（0.0-1.0）
5. WHEN TimeRange 包含相对时间时，THE Model SHALL 同时存储 relative_type、period_type 和解析后的具体日期
6. WHEN TimeRange 被序列化时，THE Model SHALL 保留所有字段信息以便追溯

### Requirement 3: 复杂时间表达式支持

**User Story:** 作为用户，我希望系统能够理解复杂的时间表达式，如"从X到Y"、"X年底到现在"等

#### Acceptance Criteria

1. WHEN 用户输入"从1月到3月"时，THE System SHALL 解析为当年1月1日到3月31日的日期范围
2. WHEN 用户输入"2024年初到现在"时，THE System SHALL 解析为2024-01-01到参考日期的范围
3. WHEN 用户输入"去年同期"时，THE System SHALL 基于当前日期计算去年对应的时间段
4. WHEN 用户输入"最近6个月"时，THE System SHALL 计算从参考日期往前推6个月的范围
5. WHEN 用户输入"2024年底"时，THE System SHALL 解析为2024-12-31或2024年第四季度
6. WHEN 用户输入"上半年"时，THE System SHALL 解析为当年1月1日到6月30日

### Requirement 4: 日期解析验证机制

**User Story:** 作为质量保证工程师，我希望系统能够验证解析后的日期范围是否合理，并在不合理时给出警告

#### Acceptance Criteria

1. WHEN 解析后的 start_date 晚于 end_date 时，THE System SHALL 标记为无效并记录警告
2. WHEN 解析后的日期范围超过数据源的最大日期时，THE System SHALL 调整 end_date 为 max_date 并记录警告
3. WHEN 解析后的日期范围早于数据源的最小日期时，THE System SHALL 记录警告但保留原始范围
4. WHEN 解析后的日期范围跨度超过10年时，THE System SHALL 记录警告提示可能的异常
5. WHEN 解析后的日期格式不符合 ISO 标准时，THE System SHALL 自动转换为 YYYY-MM-DD 格式
6. WHEN 验证失败时，THE System SHALL 在 TimeRange 中设置 is_valid=false 并记录 validation_error

### Requirement 5: 置信度评分机制

**User Story:** 作为系统监控者，我希望每个日期解析结果都有置信度分数，以便评估解析质量

#### Acceptance Criteria

1. WHEN 日期表达式为明确的绝对日期时，THE System SHALL 设置置信度为 1.0
2. WHEN 日期表达式为标准相对时间时，THE System SHALL 设置置信度为 0.9
3. WHEN 日期表达式为模糊表达时，THE System SHALL 设置置信度为 0.5-0.8
4. WHEN 日期表达式包含歧义时，THE System SHALL 设置置信度为 0.3-0.5
5. WHEN 日期表达式无法解析时，THE System SHALL 设置置信度为 0.0
6. WHEN 置信度低于 0.5 时，THE System SHALL 在日志中记录低置信度警告

### Requirement 6: 参考日期智能选择

**User Story:** 作为数据分析师，我希望系统能够智能选择参考日期，优先使用数据源的最大日期而非当前系统日期

#### Acceptance Criteria

1. WHEN 元数据包含 max_date 信息时，THE System SHALL 优先使用 max_date 作为参考日期
2. WHEN 元数据不包含 max_date 时，THE System SHALL 使用当前系统日期作为参考日期
3. WHEN 用户明确指定参考日期时，THE System SHALL 使用用户指定的日期
4. WHEN 计算相对时间时，THE System SHALL 基于选定的参考日期进行计算
5. WHEN 参考日期被使用时，THE System SHALL 在 TimeRange 中记录使用的参考日期
6. WHEN 参考日期与当前日期差异超过30天时，THE System SHALL 记录警告提示数据可能不是最新的

### Requirement 7: 日期解析结果追溯

**User Story:** 作为调试工程师，我希望能够追溯日期解析的完整过程，包括原始表达式、解析步骤和最终结果

#### Acceptance Criteria

1. WHEN 日期解析完成时，THE System SHALL 在 TimeRange 中保存 original_text 字段
2. WHEN 日期解析完成时，THE System SHALL 在 TimeRange 中保存 reference_date 字段
3. WHEN 日期解析完成时，THE System SHALL 在 TimeRange 中保存 parsing_method 字段（absolute/relative/complex）
4. WHEN 日期解析失败时，THE System SHALL 在 TimeRange 中保存 error_message 字段
5. WHEN 日期解析过程中有警告时，THE System SHALL 在 TimeRange 中保存 warnings 列表
6. WHEN 需要调试时，THE System SHALL 提供完整的解析日志包含所有中间步骤

### Requirement 8: 特殊日期需求处理

**User Story:** 作为用户，我希望系统能够处理特殊的日期需求，如节假日、周起始日等

#### Acceptance Criteria

1. WHEN 用户提及节假日时，THE System SHALL 在 DateRequirements 中记录 holidays 信息
2. WHEN 用户提及周起始日时，THE System SHALL 在 DateRequirements 中记录 week_start_day 信息
3. WHEN 用户提及"工作日"或"周末"时，THE System SHALL 在 DateRequirements 中记录相应标记
4. WHEN 特殊日期需求被识别时，THE System SHALL 在后续查询生成中考虑这些需求
5. WHEN 特殊日期需求无法处理时，THE System SHALL 记录警告并使用默认行为

### Requirement 9: 日期解析代码逻辑实现

**User Story:** 作为系统架构师，我希望日期解析使用代码逻辑实现，而不是完全依赖 LLM，以提高性能和可靠性

#### Acceptance Criteria

1. WHEN 日期表达式为标准格式时，THE System SHALL 使用正则表达式直接解析
2. WHEN 日期表达式为相对时间时，THE System SHALL 使用 dateutil 或 arrow 库计算具体日期
3. WHEN 日期表达式为中文时，THE System SHALL 使用中文日期解析规则辅助解析
4. WHEN 日期表达式复杂且代码无法处理时，THE System SHALL 回退到 LLM 解析
5. WHEN 使用代码解析时，THE System SHALL 设置更高的置信度分数
6. WHEN 使用 LLM 解析时，THE System SHALL 对结果进行代码验证

### Requirement 10: 日期解析性能优化

**User Story:** 作为性能工程师，我希望日期解析过程高效快速，不成为系统瓶颈

#### Acceptance Criteria

1. WHEN 日期表达式为常见格式时，THE System SHALL 在 10ms 内完成解析
2. WHEN 日期表达式需要 LLM 辅助时，THE System SHALL 使用缓存避免重复调用
3. WHEN 相同的日期表达式被多次解析时，THE System SHALL 从缓存中返回结果
4. WHEN 缓存大小超过限制时，THE System SHALL 使用 LRU 策略清理旧条目
5. WHEN 日期解析超时时，THE System SHALL 返回默认值并记录错误
6. WHEN 系统启动时，THE System SHALL 预加载常用日期表达式的解析结果

### Requirement 11: 日期解析错误处理

**User Story:** 作为系统可靠性工程师，我希望日期解析失败不会导致整个查询流程中断

#### Acceptance Criteria

1. WHEN 日期解析失败时，THE System SHALL 返回 None 而不是抛出异常
2. WHEN 日期解析失败时，THE System SHALL 在日志中记录详细错误信息
3. WHEN 日期解析失败时，THE System SHALL 继续执行后续流程而不中断
4. WHEN 日期解析失败时，THE System SHALL 在 Understanding 结果中标记 date_parsing_failed=true
5. WHEN 日期解析失败时，THE System SHALL 提供降级方案（如使用全部数据）
6. WHEN 日期解析失败率超过阈值时，THE System SHALL 发送告警通知

### Requirement 12: 日期解析测试覆盖

**User Story:** 作为测试工程师，我希望日期解析功能有完整的测试覆盖，确保各种场景都能正确处理

#### Acceptance Criteria

1. WHEN 测试绝对日期时，THE Test SHALL 覆盖年、季度、月、日等各种粒度
2. WHEN 测试相对日期时，THE Test SHALL 覆盖 CURRENT、LAST、NEXT、LASTN 等所有类型
3. WHEN 测试复杂表达式时，THE Test SHALL 覆盖"从X到Y"、"X到现在"等各种组合
4. WHEN 测试中文表达式时，THE Test SHALL 覆盖常见的中文时间词汇
5. WHEN 测试边界情况时，THE Test SHALL 覆盖跨年、跨月、闰年等特殊情况
6. WHEN 测试错误情况时，THE Test SHALL 覆盖无效日期、格式错误等异常场景
