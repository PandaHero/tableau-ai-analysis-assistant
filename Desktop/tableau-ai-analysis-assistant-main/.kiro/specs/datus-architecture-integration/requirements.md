# Requirements Document

## Introduction

本规范定义了从 Datus-agent 项目借鉴核心架构能力到 Tableau Assistant 的需求。通过深度分析 Datus-agent 的设计模式，我们识别出可以显著提升 Tableau Assistant 系统能力的关键功能，包括反思机制、配置系统、日期解析、反馈存储和子 Agent 系统。这些功能将帮助 Tableau Assistant 提升查询成功率、系统灵活性和持续学习能力。

## Glossary

- **Reflection Mechanism**: 反思机制，在查询执行后评估结果质量并决定是否需要重试或修复
- **Configuration System**: 配置系统，统一管理 LLM 模型、Agent 参数、环境变量等配置
- **Date Parser**: 日期解析器，使用两阶段 LLM 方法解析自然语言时间表达式
- **Feedback Store**: 反馈存储，收集用户反馈并将成功案例用于 Few-shot 学习
- **Sub-Agent System**: 子 Agent 系统，针对特定领域（如销售、财务）的专业化 Agent
- **VizQL Query**: Tableau 的查询语言，用于数据查询和可视化
- **Query Result**: 查询结果，VizQL 执行后返回的数据
- **Success Case**: 成功案例，用户反馈为正面的查询案例，可用于 Few-shot 示例
- **Reflection Strategy**: 反思策略，包括 SUCCESS、FIELD_MISMATCH、SIMPLE_REGENERATE、METADATA_SEARCH、REASONING 五种
- **Agent Configuration**: Agent 配置，包括使用的模型、温度、最大 token 数等参数
- **Environment Variable**: 环境变量，用于存储敏感信息如 API Key
- **Two-Stage Parsing**: 两阶段解析，先提取时间表达式，再解析具体日期范围

## Requirements

### Requirement 1: 反思机制集成

**User Story:** 作为数据分析师，我希望系统能够自动评估查询结果的质量，并在结果不理想时智能地进行修复，以提高查询成功率

#### Acceptance Criteria

1. WHEN VizQL 查询执行完成后，THE System SHALL 调用 Reflection Agent 评估结果质量
2. WHEN 查询结果为空或数据异常时，THE Reflection Agent SHALL 分类为 FIELD_MISMATCH 或 SIMPLE_REGENERATE 策略
3. WHEN 查询结果正确时，THE Reflection Agent SHALL 分类为 SUCCESS 策略并继续后续流程
4. WHEN 需要更多元数据信息时，THE Reflection Agent SHALL 分类为 METADATA_SEARCH 策略
5. WHEN 需要复杂推理时，THE Reflection Agent SHALL 分类为 REASONING 策略
6. WHEN Reflection Agent 决定重试时，THE System SHALL 根据策略类型执行相应的修复动作
7. WHEN 重试次数超过 3 次时，THE System SHALL 终止重试并返回最佳结果

### Requirement 2: 统一配置系统

**User Story:** 作为系统管理员，我希望通过统一的配置文件管理所有 LLM 模型、Agent 参数和环境变量，以提高系统的灵活性和可维护性

#### Acceptance Criteria

1. WHEN System 启动时，THE Configuration Manager SHALL 从 agent.yml 文件加载所有配置
2. WHEN 配置文件包含环境变量引用时，THE Configuration Manager SHALL 自动替换为实际环境变量值
3. WHEN Agent 初始化时，THE Agent SHALL 从 Configuration Manager 获取专属配置
4. WHEN 配置文件指定节点级模型时，THE System SHALL 为不同 Agent 使用不同的 LLM 模型
5. WHEN 配置文件更新时，THE System SHALL 支持热重载配置而无需重启
6. WHEN 配置文件缺少必填项时，THE Configuration Manager SHALL 抛出明确的错误信息

### Requirement 3: 两阶段日期解析

**User Story:** 作为用户，我希望系统能够准确理解我使用的自然语言时间表达式（如"最近3个月"、"2024年第一季度"），并自动转换为精确的日期范围

#### Acceptance Criteria

1. WHEN 用户问题包含时间表达式时，THE Date Parser SHALL 在第一阶段提取所有时间相关文本
2. WHEN 第一阶段提取到时间表达式时，THE Date Parser SHALL 在第二阶段将每个表达式解析为具体日期范围
3. WHEN 解析相对时间时，THE Date Parser SHALL 基于参考日期（默认为当前日期）计算具体日期
4. WHEN 解析绝对时间时，THE Date Parser SHALL 直接转换为标准日期格式
5. WHEN 解析中文时间表达式时，THE Date Parser SHALL 正确理解"去年"、"上季度"、"本月"等表达
6. WHEN 解析英文时间表达式时，THE Date Parser SHALL 正确理解"last 3 months"、"Q1 2024"等表达
7. WHEN 日期解析完成后，THE System SHALL 将解析结果注入到 Understanding Agent 的输出中

### Requirement 4: 反馈存储与学习

**User Story:** 作为产品经理，我希望系统能够收集用户反馈并从成功案例中学习，以持续提升查询质量

#### Acceptance Criteria

1. WHEN 用户对查询结果进行反馈时，THE Feedback Store SHALL 存储完整的问题、查询、结果和反馈信息
2. WHEN 用户反馈为正面时，THE Feedback Store SHALL 将该案例标记为成功案例
3. WHEN Task Planner Agent 生成查询时，THE Agent SHALL 从 Feedback Store 检索相似的成功案例作为 Few-shot 示例
4. WHEN 检索成功案例时，THE Feedback Store SHALL 基于问题类型和语义相似度排序
5. WHEN 成功案例数量超过 100 条时，THE Feedback Store SHALL 自动清理低质量案例
6. WHEN 管理员查询反馈统计时，THE Feedback Store SHALL 提供按时间、问题类型、成功率等维度的统计报告

### Requirement 5: 领域专业化子 Agent

**User Story:** 作为企业用户，我希望系统能够针对不同业务领域（如销售、财务、运营）提供专业化的分析能力，以提高分析的准确性和相关性

#### Acceptance Criteria

1. WHEN System 初始化时，THE Sub-Agent Manager SHALL 从配置文件加载所有子 Agent 定义
2. WHEN 用户问题涉及特定领域时，THE System SHALL 自动选择对应的子 Agent 处理
3. WHEN 子 Agent 处理问题时，THE Sub-Agent SHALL 仅访问其配置中允许的数据源和字段
4. WHEN 子 Agent 生成查询时，THE Sub-Agent SHALL 应用领域特定的业务规则
5. WHEN 问题不属于任何子 Agent 范围时，THE System SHALL 使用通用 Agent 处理
6. WHEN 子 Agent 配置更新时，THE System SHALL 支持动态加载新的子 Agent 而无需重启

### Requirement 6: 反思策略执行引擎

**User Story:** 作为系统开发者，我希望系统能够根据反思策略自动执行相应的修复动作，而不是简单地重试

#### Acceptance Criteria

1. WHEN Reflection Agent 返回 FIELD_MISMATCH 策略时，THE System SHALL 重新执行字段映射并生成新查询
2. WHEN Reflection Agent 返回 SIMPLE_REGENERATE 策略时，THE System SHALL 直接重新生成查询
3. WHEN Reflection Agent 返回 METADATA_SEARCH 策略时，THE System SHALL 扩展元数据搜索范围并重新规划
4. WHEN Reflection Agent 返回 REASONING 策略时，THE System SHALL 调用推理增强模式重新分析问题
5. WHEN Reflection Agent 返回 SUCCESS 策略时，THE System SHALL 继续执行后续的洞察分析流程
6. WHEN 策略执行失败时，THE System SHALL 记录失败原因并尝试降级策略

### Requirement 7: 配置驱动的工作流

**User Story:** 作为系统架构师，我希望通过配置文件定义不同的工作流，以支持标准分析、带反思的分析、领域专业分析等多种场景

#### Acceptance Criteria

1. WHEN System 启动时，THE Workflow Engine SHALL 从 workflows.yml 加载所有工作流定义
2. WHEN 用户指定工作流名称时，THE System SHALL 按照配置的节点顺序执行工作流
3. WHEN 工作流包含条件分支时，THE Workflow Engine SHALL 根据状态动态选择执行路径
4. WHEN 工作流包含并行节点时，THE Workflow Engine SHALL 同时执行多个节点并合并结果
5. WHEN 工作流执行失败时，THE Workflow Engine SHALL 记录失败节点并支持从断点恢复
6. WHEN 添加新工作流时，THE System SHALL 支持通过配置文件添加而无需修改代码

### Requirement 8: 成功案例智能检索

**User Story:** 作为 AI 工程师，我希望系统能够智能地检索最相关的成功案例作为 Few-shot 示例，以提高 LLM 的生成质量

#### Acceptance Criteria

1. WHEN Task Planner Agent 需要 Few-shot 示例时，THE System SHALL 基于当前问题的语义向量检索相似案例
2. WHEN 检索成功案例时，THE System SHALL 优先选择问题类型匹配的案例
3. WHEN 检索成功案例时，THE System SHALL 考虑案例的成功评分和时效性
4. WHEN 检索到多个候选案例时，THE System SHALL 选择多样性最高的 3-5 个案例
5. WHEN 没有相似案例时，THE System SHALL 使用预定义的通用示例
6. WHEN 成功案例被使用后，THE System SHALL 更新案例的使用统计信息

### Requirement 9: 日期解析结果验证

**User Story:** 作为质量保证工程师，我希望日期解析结果能够被验证和审计，以确保时间范围的准确性

#### Acceptance Criteria

1. WHEN Date Parser 完成解析时，THE System SHALL 返回原始表达式和解析后的日期范围对照
2. WHEN 解析结果不确定时，THE Date Parser SHALL 在结果中标记置信度分数
3. WHEN 解析失败时，THE Date Parser SHALL 返回明确的错误信息和失败原因
4. WHEN 解析结果被使用时，THE System SHALL 在日志中记录完整的解析过程
5. WHEN 用户质疑日期范围时，THE System SHALL 提供解析依据和参考日期信息

### Requirement 10: 反馈数据隐私保护

**User Story:** 作为安全管理员，我希望用户反馈数据能够被安全存储，并支持数据脱敏和访问控制

#### Acceptance Criteria

1. WHEN 存储用户反馈时，THE Feedback Store SHALL 对敏感字段进行加密存储
2. WHEN 访问反馈数据时，THE System SHALL 验证访问者的权限级别
3. WHEN 导出反馈数据时，THE System SHALL 自动脱敏个人身份信息
4. WHEN 用户请求删除反馈时，THE Feedback Store SHALL 支持完全删除相关数据
5. WHEN 反馈数据超过保留期限时，THE System SHALL 自动归档或删除过期数据
