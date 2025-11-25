# Requirements Document

## Introduction

本项目旨在通过深入学习 VSCode Copilot Chat 的先进架构和设计模式，系统化地提升 Tableau Assistant 项目的功能、性能和可维护性。

**项目背景**：
- Tableau Assistant 是基于 LangGraph 的 Tableau 查询助手
- 当前存在 Prompt 管理、工具调用、错误处理等方面的改进空间
- VSCode Copilot 提供了成熟的 AI Agent 架构和最佳实践

**主要目标**：
1. **深入理解** VSCode Copilot 的核心技术和架构设计
2. **识别并借鉴** 可应用于 Tableau Assistant 的设计模式
3. **设计并实现** 功能增强和架构优化
4. **建立** 完善的测试和验证机制
5. **提升** 系统的可维护性和可扩展性

**预期成果**：
- 完整的 VSCode Copilot 架构分析文档 ✅
- Tableau Assistant 改进设计方案
- 可执行的实施计划和任务列表
- 提升查询成功率和用户体验


## Glossary

- **VSCode Copilot**: Microsoft 开发的 AI 编程助手，集成在 Visual Studio Code 中
- **Tableau Assistant**: 基于 LangGraph 的 Tableau 查询助手系统
- **LLM (Large Language Model)**: 大语言模型
- **Prompt Template**: 提示词模板，用于指导 LLM 生成特定格式的输出
- **Prompt-TSX**: VSCode Copilot 开发的 TSX 组件化 Prompt 框架
- **Schema Validation**: 数据结构验证，确保 LLM 输出符合预期格式
- **Tool Calling**: 工具调用，LLM 调用外部功能的机制
- **Agent Mode**: 自主编程模式，AI 自动处理多步骤任务并迭代优化
- **Metadata**: 元数据，描述数据源的字段、类型、关系等信息
- **VizQL**: Tableau 的查询语言
- **Post-processing**: 后处理，查询执行后的数据处理步骤
- **Context Compression**: 上下文压缩，减少输入 Token 数量的技术
- **Multi-modal**: 多模态，支持文本、图片、音频等多种输入方式
- **MCP (Model Context Protocol)**: 模型上下文协议，标准化的工具调用接口
- **Dependency Injection (DI)**: 依赖注入，一种设计模式
- **Prompt Registry**: Prompt 注册表，用于多模型 Prompt 适配
- **Token Budget**: Token 预算，LLM 输入的最大 Token 数量限制
- **Priority-based Pruning**: 基于优先级的裁剪，超出 Token 预算时裁剪低优先级内容


## Requirements

### Requirement 1: VSCode Copilot 架构深度分析

**User Story:** 作为开发者，我想要全面深入地理解 VSCode Copilot 的架构和核心技术，以便能够识别可借鉴的设计模式并应用到 Tableau Assistant 项目中。

#### Acceptance Criteria

1. WHEN 分析 VSCode Copilot 的分层架构 THEN 系统文档 SHALL 包含完整的层级结构、依赖规则、以及每层的职责划分
2. WHEN 分析 Prompt-TSX 系统 THEN 系统文档 SHALL 包含组件化 Prompt 的原理、优先级管理机制、Token 预算控制、以及与传统字符串拼接的对比
3. WHEN 分析 Agent Mode THEN 系统文档 SHALL 包含工作流程、Tool Calling Loop、错误处理机制、以及迭代优化策略
4. WHEN 分析工具系统 THEN 系统文档 SHALL 包含工具定义方式、注册机制、调用流程、以及内置工具分类
5. WHEN 分析上下文管理 THEN 系统文档 SHALL 包含优先级裁剪、对话历史压缩、元数据过滤等策略
6. WHEN 分析 Prompt Registry THEN 系统文档 SHALL 包含多模型适配机制、Resolver 模式、以及不同模型的 Prompt 优化策略
7. WHEN 分析测试策略 THEN 系统文档 SHALL 包含单元测试、集成测试、Simulation Tests 的实现方式和特点



### Requirement 2: Prompt 组件化和优先级管理

**User Story:** 作为系统，我想要实现组件化的 Prompt 管理系统，以便能够更好地控制 Token 预算、实现动态组合、以及提高 Prompt 的可维护性。

#### Acceptance Criteria

1. WHEN 定义 Prompt 组件 THEN 系统 SHALL 支持为每个组件设置优先级（priority）
2. WHEN 渲染 Prompt THEN 系统 SHALL 根据 Token 预算自动裁剪低优先级组件
3. WHEN 组合 Prompt THEN 系统 SHALL 支持嵌套组件和条件渲染
4. WHEN 复用 Prompt 组件 THEN 系统 SHALL 提供通用组件（SafetyRules、Metadata、ConversationHistory 等）
5. WHEN 计算 Token 数量 THEN 系统 SHALL 使用准确的 Token 计数工具（如 tiktoken）
6. WHEN 超出 Token 预算 THEN 系统 SHALL 保留高优先级组件并裁剪低优先级组件
7. WHEN 渲染完成 THEN 系统 SHALL 记录实际使用的 Token 数量和裁剪的组件信息



### Requirement 3: 显式工具系统设计

**User Story:** 作为系统架构师，我想要设计一个显式的工具调用系统，以便 LLM 能够自主决定调用哪些工具来完成任务，并提供更好的错误处理和可扩展性。

#### Acceptance Criteria

1. WHEN 定义工具 THEN 系统 SHALL 使用标准化的工具描述格式（名称、描述、输入 Schema、输出格式）
2. WHEN LLM 需要获取元数据 THEN 系统 SHALL 提供 get_metadata 工具
3. WHEN LLM 需要搜索字段 THEN 系统 SHALL 提供 search_fields 工具（支持语义搜索和关键词搜索）
4. WHEN LLM 需要执行查询 THEN 系统 SHALL 提供 execute_query 工具
5. WHEN LLM 需要验证查询 THEN 系统 SHALL 提供 validate_query 工具
6. WHEN 工具调用失败 THEN 系统 SHALL 返回结构化的错误信息供 LLM 分析和处理
7. WHEN 注册工具 THEN 系统 SHALL 支持动态注册和发现工具
8. WHEN 调用工具 THEN 系统 SHALL 记录工具调用的输入、输出、耗时等信息用于调试和优化



### Requirement 4: 查询验证和错误修正循环

**User Story:** 作为系统，我想要在查询执行前后进行验证和错误修正，以便提高查询成功率并减少用户等待时间。

#### Acceptance Criteria

1. WHEN 生成查询计划后 THEN 系统 SHALL 验证所有字段是否存在于元数据中
2. WHEN 验证发现字段不存在 THEN 系统 SHALL 使用 LLM 搜索相似字段并修正字段名
3. WHEN 验证发现聚合函数不合法 THEN 系统 SHALL 使用 LLM 分析并修正聚合函数
4. WHEN 查询执行失败 THEN 系统 SHALL 捕获错误信息并使用 LLM 生成修正方案
5. WHEN 执行修正后的查询 THEN 系统 SHALL 最多重试 3 次
6. WHEN 重试次数超限 THEN 系统 SHALL 返回详细的错误信息、已尝试的修正方案、以及建议给用户
7. WHEN 修正成功 THEN 系统 SHALL 记录修正前后的查询计划用于学习和优化



### Requirement 5: 多模型 Prompt 适配系统

**User Story:** 作为系统，我想要支持多种 LLM 模型并为每种模型提供优化的 Prompt，以便提高输出质量并支持灵活的模型切换。

#### Acceptance Criteria

1. WHEN 配置 LLM 模型 THEN 系统 SHALL 支持 GPT-4、GPT-3.5、Claude、Gemini 等主流模型
2. WHEN 注册 Prompt THEN 系统 SHALL 支持为不同模型族（model family）注册不同的 Prompt Resolver
3. WHEN 选择 Prompt THEN 系统 SHALL 根据当前使用的模型自动选择对应的 Prompt 类
4. WHEN 使用 GPT-4 THEN 系统 SHALL 使用详细的指令和复杂的思维链
5. WHEN 使用 GPT-3.5 THEN 系统 SHALL 使用简化的指令以减少 Token 消耗
6. WHEN 使用 Claude THEN 系统 SHALL 使用结构化标签格式（如 `<task>`, `<output_format>`）
7. WHEN 模型调用失败 THEN 系统 SHALL 支持自动降级到备用模型
8. WHEN 记录模型使用情况 THEN 系统 SHALL 统计每个模型的调用次数、成功率、平均响应时间、Token 消耗



### Requirement 6: 基于 Category 的元数据过滤

**User Story:** 作为系统，我想要基于字段 Category 过滤元数据，以便减少 Token 消耗并提高查询效率。

#### Acceptance Criteria

1. WHEN 问题理解阶段识别字段 THEN 系统 SHALL 同时识别每个字段所属的 Category（地理、时间、产品、客户等）
2. WHEN 识别字段 Category THEN 系统 SHALL 优先从维度层级（dimension_hierarchy）中查找
3. WHEN 维度层级中找不到字段 THEN 系统 SHALL 使用 LLM 推断字段的 Category
4. WHEN 查询规划阶段 THEN 系统 SHALL 只获取问题中涉及的 Category 的元数据
5. WHEN 过滤元数据 THEN 系统 SHALL 保留所有相关 Category 的维度字段
6. WHEN 过滤元数据 THEN 系统 SHALL 可选择保留所有度量字段或只保留相关 Category 的度量字段
7. WHEN 元数据过滤后 THEN 系统 SHALL 减少至少 50% 的 Token 消耗
8. WHEN 记录过滤效果 THEN 系统 SHALL 统计过滤前后的字段数量和 Token 数量



### Requirement 7: 上下文管理和压缩优化

**User Story:** 作为系统，我想要优化上下文管理，以便在保持对话连贯性的同时减少 Token 消耗并提高响应速度。

#### Acceptance Criteria

1. WHEN 对话历史超过 10 轮 THEN 系统 SHALL 压缩早期对话内容
2. WHEN 压缩对话历史 THEN 系统 SHALL 保留系统提示和最近 5 轮对话
3. WHEN 生成对话摘要 THEN 系统 SHALL 使用 LLM 生成简洁的摘要保留关键信息
4. WHEN 元数据超过 1000 Token THEN 系统 SHALL 只提供与当前问题相关的字段
5. WHEN 需要引用历史信息 THEN 系统 SHALL 使用摘要而非完整内容
6. WHEN 计算 Token 数量 THEN 系统 SHALL 使用 tiktoken 库进行准确计算
7. WHEN 监控 Token 使用 THEN 系统 SHALL 记录每次请求的 Token 消耗并生成统计报告



### Requirement 8: Post-processing 功能增强

**User Story:** 作为系统，我想要扩展 Post-processing 功能，以便支持更复杂的数据处理和分析需求。

#### Acceptance Criteria

1. WHEN 需要合并多个查询结果 THEN 系统 SHALL 支持数据合并操作（UNION、JOIN）
2. WHEN 需要计算派生指标 THEN 系统 SHALL 支持增长率、占比、排名、移动平均等计算
3. WHEN 需要筛选数据 THEN 系统 SHALL 支持 Top N、Bottom N、条件过滤等操作
4. WHEN 需要排序数据 THEN 系统 SHALL 支持单字段和多字段排序
5. WHEN 需要格式化输出 THEN 系统 SHALL 将数据转换为前端需要的格式（JSON、CSV、表格）
6. WHEN 定义 Post-processing 操作 THEN 系统 SHALL 使用结构化的操作链表示
7. WHEN 执行 Post-processing THEN 系统 SHALL 验证操作的合法性并提供错误提示



### Requirement 9: 性能监控和优化

**User Story:** 作为系统管理员，我想要监控系统性能，以便识别瓶颈并进行优化。

#### Acceptance Criteria

1. WHEN 执行查询 THEN 系统 SHALL 记录每个阶段的耗时（理解、规划、执行、后处理）
2. WHEN 调用 LLM THEN 系统 SHALL 记录 Token 消耗、响应时间、模型名称
3. WHEN 查询失败 THEN 系统 SHALL 记录失败原因、重试次数、最终状态
4. WHEN 分析性能数据 THEN 系统 SHALL 生成性能报告（平均响应时间、成功率、Token 消耗、瓶颈分析）
5. WHEN 发现性能问题 THEN 系统 SHALL 提供优化建议（缓存、并行、模型选择、Prompt 优化）
6. WHEN 监控系统健康 THEN 系统 SHALL 提供实时监控面板显示关键指标
7. WHEN 导出性能数据 THEN 系统 SHALL 支持导出为 CSV、JSON 格式用于进一步分析



### Requirement 10: 测试和验证框架

**User Story:** 作为开发者，我想要建立完善的测试框架，以便验证系统改进的效果并防止回归。

#### Acceptance Criteria

1. WHEN 测试 Prompt 模板 THEN 系统 SHALL 使用标准测试集评估输出质量（准确性、完整性、格式）
2. WHEN 测试查询验证 THEN 系统 SHALL 验证能够捕获所有类型的错误（字段不存在、聚合函数错误、语法错误）
3. WHEN 测试错误修正 THEN 系统 SHALL 验证修正后的查询能够成功执行
4. WHEN 测试 Post-processing THEN 系统 SHALL 验证数据处理结果的正确性
5. WHEN 进行回归测试 THEN 系统 SHALL 确保新功能不影响现有功能
6. WHEN 测试多模型适配 THEN 系统 SHALL 验证每个模型都能正确工作
7. WHEN 生成测试报告 THEN 系统 SHALL 包含测试覆盖率、通过率、失败原因分析



### Requirement 11: 架构重构和分层设计

**User Story:** 作为系统架构师，我想要重构系统架构并建立清晰的分层设计，以便提高代码的可维护性和可扩展性。

#### Acceptance Criteria

1. WHEN 组织代码结构 THEN 系统 SHALL 采用三层架构（util、platform、src）
2. WHEN 定义依赖规则 THEN 系统 SHALL 确保 src 可以导入 platform 和 util，platform 可以导入 util，util 不能导入其他层
3. WHEN 实现服务 THEN 系统 SHALL 使用依赖注入模式
4. WHEN 注册服务 THEN 系统 SHALL 使用服务容器管理服务的生命周期
5. WHEN 添加新功能 THEN 系统 SHALL 遵循分层架构的约束
6. WHEN 重构现有代码 THEN 系统 SHALL 逐步迁移到新的架构而不影响现有功能
7. WHEN 验证架构 THEN 系统 SHALL 使用静态分析工具检查依赖规则的遵守情况



### Requirement 12: 文档和知识管理

**User Story:** 作为团队成员，我想要完善的文档和知识管理系统，以便快速理解系统设计并进行协作开发。

#### Acceptance Criteria

1. WHEN 创建架构文档 THEN 系统 SHALL 包含完整的架构图、模块说明、数据流图
2. WHEN 编写 API 文档 THEN 系统 SHALL 包含所有公共接口的说明、参数、返回值、示例
3. WHEN 记录设计决策 THEN 系统 SHALL 使用 ADR（Architecture Decision Record）格式
4. WHEN 编写开发指南 THEN 系统 SHALL 包含环境搭建、代码规范、测试指南、部署流程
5. WHEN 更新文档 THEN 系统 SHALL 确保文档与代码保持同步
6. WHEN 分享知识 THEN 系统 SHALL 建立知识库记录常见问题、最佳实践、故障排查
7. WHEN 进行代码审查 THEN 系统 SHALL 使用 Checklist 确保代码质量和文档完整性

---

## 优先级和实施阶段

### 第一阶段（高优先级，1-2 周）

**目标**：快速见效的改进

- ✅ Requirement 1: VSCode Copilot 架构深度分析（已完成）
- 🔄 Requirement 2: Prompt 组件化和优先级管理
- 🔄 Requirement 3: 显式工具系统设计
- 🔄 Requirement 4: 查询验证和错误修正循环
- 🔄 Requirement 5: 多模型 Prompt 适配系统

### 第二阶段（中优先级，1-2 月）

**目标**：架构优化和功能增强

- ⏳ Requirement 6: 元数据搜索和语义理解
- ⏳ Requirement 7: 上下文管理和压缩优化
- ⏳ Requirement 8: Post-processing 功能增强
- ⏳ Requirement 9: 性能监控和优化
- ⏳ Requirement 11: 架构重构和分层设计

### 第三阶段（低优先级，3-6 月）

**目标**：完善和长期规划

- 🔮 Requirement 10: 测试和验证框架
- 🔮 Requirement 12: 文档和知识管理
- 🔮 多模态支持（未来规划）
- 🔮 MCP 协议支持（未来规划）
- 🔮 Agent Mode 实现（未来规划）

