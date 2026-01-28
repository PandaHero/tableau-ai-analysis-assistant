# Requirements Document

## Introduction

本文档定义了 BI 数据分析助手项目中语义解析器（SemanticParser）重构的需求规格。语义解析器是系统的核心组件，负责将用户的自然语言问题转换为准确的数据查询（VizQL）。

本次重构采用 **LLM 驱动的简化架构**，核心设计原则：
1. **信任 LLM 的推理能力**：让 LLM 直接理解用户问题，不做复杂的前置处理
2. **通过 Prompt 和 Few-shot 提升准确性**：动态选择相关示例，提供增强信息
3. **渐进式查询构建**：支持多轮对话逐步完善查询
4. **持续学习**：从用户反馈中学习，不断改进

参考：
- Vanna.ai（GitHub 12k+ stars）：RAG + LLM 架构
- NeurIPS 2024 "The Death of Schema Linking"：强推理模型不需要复杂的 Schema Linking

## Glossary

- **Semantic_Parser**: 语义解析器，将自然语言问题转换为结构化查询的核心组件
- **IntentRouter**: 意图路由器，轻量级意图识别组件，过滤非数据查询
- **CascadeRetriever**: 级联检索器，支持多路召回的向量检索组件
- **Few_Shot_Example**: 少样本示例，用于指导 LLM 生成的示例
- **Feedback_Learner**: 反馈学习器，从用户反馈中学习改进的组件
- **Confidence_Score**: 置信度分数，表示系统对某个结果确定程度的数值（0-1）
- **VizQL**: Tableau 的可视化查询语言
- **LangGraph**: 用于构建 LLM 应用工作流的框架
- **SummarizationMiddleware**: 摘要中间件，自动压缩过长对话历史的 LangChain 中间件

## Requirements

### Requirement 1: 意图路由 - 轻量级意图识别

**User Story:** As a 系统管理员, I want 系统能够快速识别非数据查询意图, so that 减少不必要的 LLM 调用，提升响应速度。

#### Acceptance Criteria

1. THE IntentRouter SHALL 在 LLM 语义理解之前执行，识别问题意图类型
2. THE IntentRouter SHALL 支持以下意图类型：DATA_QUERY（数据查询）、CLARIFICATION（需要澄清）、GENERAL（元数据问答）、IRRELEVANT（无关问题）
3. WHEN 意图为 IRRELEVANT THEN THE IntentRouter SHALL 直接返回礼貌拒绝，不调用 LLM
4. WHEN 意图为 GENERAL THEN THE IntentRouter SHALL 路由到元数据问答流程
5. THE IntentRouter SHALL 使用规则匹配（L0）+ 可选小模型分类（L1）的两层策略
6. THE IntentRouter SHALL 在 50ms 内完成意图识别

### Requirement 2: 查询缓存 - 相似问题快速返回

**User Story:** As a 数据分析师, I want 系统能够记住我之前的查询, so that 相同或相似的问题可以快速返回结果。

#### Acceptance Criteria

1. WHEN 查询成功执行 THEN THE Semantic_Parser SHALL 缓存问题-查询映射
2. WHEN 用户提出相同问题 THEN THE Semantic_Parser SHALL 直接返回缓存的查询
3. WHEN 用户提出相似问题（语义相似度 > 0.95）THEN THE Semantic_Parser SHALL 提示使用缓存查询或生成新查询
4. THE Semantic_Parser SHALL 支持配置缓存过期时间
5. WHEN 数据模型变更 THEN THE Semantic_Parser SHALL 自动失效相关缓存
6. THE Semantic_Parser SHALL 使用 CacheManager 进行缓存管理

### Requirement 3: 字段检索 - Top-K 向量检索

**User Story:** As a 开发者, I want 系统能够高效检索相关字段, so that 在大数据模型场景下也能快速响应。

#### Acceptance Criteria

1. THE Semantic_Parser SHALL 使用 CascadeRetriever 进行字段向量检索
2. WHEN 数据模型字段数超过阈值（如 500）THEN THE Semantic_Parser SHALL 使用 Top-K 检索而非完整字段列表
3. THE Semantic_Parser SHALL 支持配置 Top-K 的 K 值（默认 10）
4. THE Semantic_Parser SHALL 在检索结果中包含字段名、字段描述、数据类型、样例值
5. THE Semantic_Parser SHALL 支持精确匹配 + 向量检索的混合策略
6. THE Semantic_Parser SHALL 在 100ms 内完成字段检索

### Requirement 4: LLM 语义理解 - 核心理解能力

**User Story:** As a 数据分析师, I want 系统能够准确理解我的自然语言问题, so that 生成正确的数据查询。

#### Acceptance Criteria

1. THE Semantic_Parser SHALL 依赖 LLM 原生能力理解用户问题
2. THE Semantic_Parser SHALL 在 Prompt 中包含：用户问题、对话历史、Top-K 字段列表、Few-shot 示例、当前日期和配置
3. THE Semantic_Parser SHALL 输出结构化结果：restated_question、what（度量）、where（维度、过滤）、how（计算类型）
4. THE Semantic_Parser SHALL 依赖 LLM 原生能力处理指代消解（"它"、"这个"等代词）
5. THE Semantic_Parser SHALL 依赖 LLM 原生能力处理省略恢复（"那北京呢？"等省略句式）
6. THE Semantic_Parser SHALL 依赖 LLM 原生能力解析时间表达式（上个月、去年同期、最近30天等）
7. THE Semantic_Parser SHALL 在 restated_question 中输出完整独立的问题描述

### Requirement 5: 计算逻辑理解 - 派生度量分解

**User Story:** As a 数据分析师, I want 系统能够理解复杂的计算逻辑, so that 我可以用自然语言描述比率、增长率等派生指标。

#### Acceptance Criteria

1. WHEN 用户问题包含派生度量（如"利润率"）THEN THE Semantic_Parser SHALL 分解为基础度量的计算公式（利润/销售额）
2. THE Semantic_Parser SHALL 识别常见的派生度量模式：比率（A/B）、增长率（(A-B)/B）、占比（A/SUM(A)）
3. THE Semantic_Parser SHALL 在输出中包含 computations 字段，描述计算逻辑
4. THE Semantic_Parser SHALL 支持同比（YoY）、环比（MoM）等时间相关的计算
5. THE Semantic_Parser SHALL 在 Few-shot 示例中包含常见派生度量的分解示例
6. WHEN 派生度量的基础字段不存在 THEN THE Semantic_Parser SHALL 提示用户或请求澄清
7. THE Semantic_Parser SHALL 支持子查询/聚合粒度控制（平台无关的 SUBQUERY 类型，由 QueryAdapter 转换为具体实现）

### Requirement 6: 渐进式查询 - 多轮对话支持

**User Story:** As a 数据分析师, I want 系统能够引导我逐步完善查询, so that 我不需要一次性提供所有信息。

#### Acceptance Criteria

1. WHEN 用户问题信息不完整 THEN THE Semantic_Parser SHALL 输出 needs_clarification: true 和澄清问题
2. THE Semantic_Parser SHALL 在每轮对话中输出当前理解的完整状态
3. THE Semantic_Parser SHALL 支持用户跳过澄清直接执行当前查询
4. THE Semantic_Parser SHALL 根据数据模型动态生成澄清问题的候选选项
5. WHEN 用户提供新信息 THEN THE Semantic_Parser SHALL 增量更新查询状态
6. THE Semantic_Parser SHALL 与 SummarizationMiddleware 协同管理对话历史

### Requirement 7: Few-shot 示例 - 动态示例选择

**User Story:** As a 系统管理员, I want 系统能够动态选择相关示例指导查询生成, so that 查询生成质量持续提升。

#### Acceptance Criteria

1. THE Semantic_Parser SHALL 维护一个 Few-shot 示例库
2. WHEN 生成查询时 THEN THE Semantic_Parser SHALL 从示例库中检索语义相关的 2-3 个示例
3. THE Semantic_Parser SHALL 优先选择用户接受过的查询作为示例
4. THE Semantic_Parser SHALL 在示例中包含：问题、restated_question、what/where/how、生成的查询
5. THE Semantic_Parser SHALL 支持按数据源分类管理示例
6. THE Semantic_Parser SHALL 支持手动添加、编辑和删除示例

### Requirement 8: LLM 自检 - 单次调用内自检

**User Story:** As a 数据分析师, I want 系统能够自我检查生成结果的可靠性, so that 我可以了解系统对结果的确定程度。

#### Acceptance Criteria

1. THE Semantic_Parser SHALL 在 LLM 输出中包含自检结果（self_check）
2. THE Semantic_Parser SHALL 评估字段映射置信度
3. THE Semantic_Parser SHALL 评估时间范围解析置信度
4. THE Semantic_Parser SHALL 评估计算逻辑置信度
5. WHEN 任一置信度低于阈值（如 0.7）THEN THE Semantic_Parser SHALL 在自检结果中标注潜在问题
6. THE Semantic_Parser SHALL 计算整体查询的综合置信度

### Requirement 9: 执行后修正 - 基于错误反馈的修正

**User Story:** As a 数据分析师, I want 系统能够自动修正查询错误, so that 我不需要手动调试查询问题。

#### Acceptance Criteria

1. WHEN 查询执行失败 THEN THE Semantic_Parser SHALL 将错误信息反馈给 LLM 重新生成
2. THE Semantic_Parser SHALL 最多重试 3 次
3. THE Semantic_Parser SHALL 在重试时包含：原始问题、之前的查询、执行错误信息
4. WHEN 自动修正成功 THEN THE Semantic_Parser SHALL 向用户说明修正内容
5. WHEN 自动修正失败 THEN THE Semantic_Parser SHALL 提供详细的错误信息和修正建议
6. THE Semantic_Parser SHALL 记录修正历史用于后续学习

### Requirement 10: 用户反馈学习 - 持续改进

**User Story:** As a 系统管理员, I want 系统能够从用户反馈中学习, so that 系统准确性持续提升。

#### Acceptance Criteria

1. THE Feedback_Learner SHALL 记录用户对查询的接受（accept）操作
2. THE Feedback_Learner SHALL 记录用户对查询的修改（modify）操作及修改内容
3. THE Feedback_Learner SHALL 记录用户对查询的拒绝（reject）操作及拒绝原因
4. WHEN 用户接受查询 THEN THE Feedback_Learner SHALL 将该查询添加到 Few-shot 示例库候选
5. WHEN 用户修改字段映射 THEN THE Feedback_Learner SHALL 记录原始术语和正确字段的映射
6. WHEN 同一映射被多个用户确认（次数 >= 3）THEN THE Feedback_Learner SHALL 自动添加到同义词表

### Requirement 11: 时间与配置 - 业务日历支持

**User Story:** As a 跨国企业用户, I want 系统能够正确处理时区和业务日历, so that 时间相关的查询结果准确无误。

#### Acceptance Criteria

1. THE Semantic_Parser SHALL 在 Prompt 中提供当前日期作为时间计算的基准
2. THE Semantic_Parser SHALL 支持在配置中设置默认时区
3. THE Semantic_Parser SHALL 支持在配置中设置财年起始月份（默认1月，可配置为4月等）
4. THE Semantic_Parser SHALL 在 Few-shot 示例中包含常见时间表达式的解析示例
5. THE Semantic_Parser SHALL 支持在配置中定义业务日历（工作日、节假日）
6. THE Semantic_Parser SHALL 依赖 LLM 根据配置正确解析时间表达式

### Requirement 12: Prompt 优化 - Token 效率

**User Story:** As a 系统管理员, I want Prompt 设计能够优化 Token 使用, so that 系统既准确又高效。

#### Acceptance Criteria

1. THE Semantic_Parser SHALL 使用结构化 Prompt 模板
2. THE Semantic_Parser SHALL 在 Prompt 中使用简洁的 XML 标签描述字段约束
3. THE Semantic_Parser SHALL 使用 Top-K 检索结果而非完整数据模型
4. WHEN 对话历史超过 MAX_HISTORY_TOKENS 阈值 THEN THE Semantic_Parser SHALL 截断早期历史
5. THE Semantic_Parser SHALL 优先使用 SummarizationMiddleware 压缩后的历史
6. THE Semantic_Parser SHALL 记录 Token 使用指标，用于监控和调优

### Requirement 13: 流式输出 - 实时反馈

**User Story:** As a 前端开发者, I want 语义解析器支持流式输出, so that 用户可以实时看到解析进度。

#### Acceptance Criteria

1. THE Semantic_Parser SHALL 使用 stream_llm_structured() 进行流式结构化输出
2. THE Semantic_Parser SHALL 支持 token 级别的流式回调
3. THE Semantic_Parser SHALL 支持部分 JSON 对象的流式回调
4. THE Semantic_Parser SHALL 在流式输出完成后返回完整的 Pydantic 对象
5. WHEN 流式输出中断 THEN THE Semantic_Parser SHALL 优雅处理并返回错误信息

### Requirement 14: 技术架构 - LangGraph 子图

**User Story:** As a 开发者, I want 语义解析器作为 LangGraph 子图实现, so that 它可以与主工作流无缝集成。

#### Acceptance Criteria

1. THE Semantic_Parser SHALL 实现为 LangGraph StateGraph 子图
2. THE Semantic_Parser SHALL 定义清晰的输入/输出状态契约
3. THE Semantic_Parser SHALL 支持通过 RunnableConfig 传递配置
4. THE Semantic_Parser SHALL 支持 LangSmith 可观测性集成
5. THE Semantic_Parser SHALL 支持子图内部的条件路由和循环

### Requirement 15: 测试覆盖

**User Story:** As a 开发者, I want 语义解析器有充分的测试覆盖, so that 代码质量得到保证。

#### Acceptance Criteria

1. THE Semantic_Parser SHALL 达到 80% 以上的单元测试覆盖率
2. THE Semantic_Parser SHALL 包含各组件的集成测试
3. THE Semantic_Parser SHALL 包含端到端的功能测试
4. THE Semantic_Parser SHALL 包含性能基准测试
5. THE Semantic_Parser SHALL 包含边界条件和异常情况的测试用例


---

## 新增需求：动态 Prompt 与 Schema 优化

### Requirement 16: 多语言支持

**User Story:** As a 跨国企业用户, I want 系统能够理解多种语言的查询, so that 不同语言背景的用户都能使用系统。

#### Acceptance Criteria

1. THE RulePrefilter SHALL 支持中文(zh)、英文(en)、日文(ja)的时间表达式识别
2. THE RulePrefilter SHALL 支持多语言的计算类型关键词匹配
3. THE RulePrefilter SHALL 自动检测用户问题的语言
4. THE ModularPromptBuilder SHALL 根据检测到的语言调整 Prompt 内容

### Requirement 17: 细粒度计算类型识别

**User Story:** As a 数据分析师, I want 系统能够准确识别不同类型的计算需求, so that 生成的查询更加精准。

#### Acceptance Criteria

1. THE SemanticParser SHALL 支持 7 种计算类型：SIMPLE、RATIO、RANK、SHARE、TIME_COMPARE、CUMULATIVE、SUBQUERY
2. THE RulePrefilter SHALL 通过关键词匹配快速识别计算类型
3. THE FeatureExtractor SHALL 在规则无法识别时使用 LLM 进行深度理解
4. THE ModularPromptBuilder SHALL 根据计算类型选择对应的 Prompt 模块
5. THE SUBQUERY 类型 SHALL 是平台无关的，由 QueryAdapter 根据上下文决定具体实现（Tableau: FIXED/INCLUDE/EXCLUDE, SQL: 子查询）

### Requirement 18: 智能 Schema 筛选

**User Story:** As a 系统管理员, I want 系统能够智能筛选相关字段, so that 减少 Token 消耗，提升响应速度。

#### Acceptance Criteria

1. THE SmartSchemaFilter SHALL 根据 RAG 匹配结果筛选相关字段
2. THE SmartSchemaFilter SHALL 根据计算类型添加必要的辅助字段
3. THE SmartSchemaFilter SHALL 限制返回字段数量不超过 MAX_FIELDS (20)
4. THE SmartSchemaFilter SHALL 优先保留高置信度匹配的字段

### Requirement 19: 双 LLM 调用架构

**User Story:** As a 开发者, I want 系统采用双 LLM 调用架构, so that 在保证准确性的同时实现动态 Schema 优化。

#### Acceptance Criteria

1. THE FeatureExtractor SHALL 始终执行（第一次 LLM 调用），提取查询特征
2. THE SemanticUnderstanding SHALL 始终执行（第二次 LLM 调用），生成最终输出
3. THE FeatureExtractor 输出 SHALL 用于动态选择 Schema 模块
4. THE 系统 SHALL 接受两次 LLM 调用的延迟开销以换取更高的准确性

### Requirement 20: 筛选值验证

**User Story:** As a 数据分析师, I want 系统能够验证筛选值的有效性, so that 减少无效查询。

#### Acceptance Criteria

1. THE FilterValueValidator SHALL 在 SemanticUnderstanding 之后执行
2. THE FilterValueValidator SHALL 验证 LLM 输出中的所有筛选条件
3. THE FilterValueValidator SHALL 使用 FieldValueCache 缓存字段值
4. WHEN 发现无效筛选值 THEN THE FilterValueValidator SHALL 提供相似值建议
5. THE FilterValueValidator SHALL 跳过时间字段和高基数字段的验证

### Requirement 21: 动态 Schema 模块选择

**User Story:** As a 系统管理员, I want 系统能够根据查询特征动态选择 Schema 模块, so that 优化 Token 使用并提升准确性。

#### Acceptance Criteria

1. THE DynamicSchemaBuilder SHALL 支持 5 种 Schema 模块：base、time、computation、filter、clarification
2. THE base 模块 SHALL 始终包含（核心字段和基础指令）
3. THE time 模块 SHALL 在检测到时间表达式时包含
4. THE computation 模块 SHALL 在检测到派生度量时包含
5. THE filter 模块 SHALL 在检测到筛选条件时包含
6. THE clarification 模块 SHALL 在需要澄清时包含
7. THE DynamicSchemaBuilder SHALL 根据 FeatureExtractor 输出选择模块

### Requirement 22: 特征缓存

**User Story:** As a 系统管理员, I want 系统能够缓存特征提取结果, so that 相似问题可以复用特征。

#### Acceptance Criteria

1. THE FeatureCache SHALL 缓存 FeatureExtractor 的输出
2. THE FeatureCache SHALL 使用问题文本的语义相似度作为缓存键
3. WHEN 语义相似度 > 0.95 THEN THE FeatureCache SHALL 返回缓存的特征
4. THE FeatureCache SHALL 支持配置缓存过期时间
5. THE FeatureCache SHALL 与 QueryCache 独立管理

### Requirement 23: 输出预验证与自动修正

**User Story:** As a 开发者, I want 系统能够在执行前验证 LLM 输出, so that 减少不必要的执行错误和重试。

#### Acceptance Criteria

1. THE OutputValidator SHALL 在 SemanticUnderstanding 输出后立即执行
2. THE OutputValidator SHALL 验证字段引用的有效性
3. THE OutputValidator SHALL 验证计算表达式的语法正确性
4. WHEN 发现可自动修正的错误 THEN THE OutputValidator SHALL 自动修正
5. WHEN 发现不可修正的错误 THEN THE OutputValidator SHALL 标记并请求澄清
6. THE OutputValidator SHALL 减少对 ErrorCorrector 的依赖

