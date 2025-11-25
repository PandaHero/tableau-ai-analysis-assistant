# Tableau Assistant 系统化增强需求文档 v2.0

## 文档说明

本文档基于以下分析重新编写：
1. VSCode Copilot 深度分析（意图识别、Agent Mode、工作流程）
2. Tableau Assistant 当前项目结构和功能
3. LangChain/LangGraph 框架能力
4. 系统化功能缺失分析

**核心发现**：
- ✅ 项目已有良好的基础架构（LangGraph 工作流、Agent 系统、Pydantic 模型）
- ❌ 缺少系统化的意图识别、工具调用、上下文管理
- ❌ 未充分利用 LangChain/LangGraph 的高级特性
- ❌ Prompt 管理、错误处理、状态持久化需要增强

**改进方向**：
1. 引入意图识别系统（借鉴 VSCode）
2. 建立工作集和编辑步骤管理（借鉴 Agent Mode）
3. 增强工具调用系统（使用 LangChain Tools）
4. 优化上下文管理（使用 LangChain Retrievers）
5. 改进 Prompt 系统（使用 LangChain PromptTemplate）
6. 增强会话管理（使用 LangGraph Checkpointer）

---

## Introduction

Tableau Assistant 是一个基于 LangChain + LangGraph 的多智能体 Tableau 查询与分析系统。
当前系统已经实现了基本的查询理解、规划和执行功能，但在系统化、框架利用、用户体验等方面还有较大提升空间。

**项目现状**：
- ✅ 7 个专业化 Agent（Understanding、Planning、Boost、Insight、Replanner 等）
- ✅ LangGraph 工作流编排
- ✅ Pydantic 数据模型
- ✅ FastAPI REST API
- ✅ 流式输出支持
- ✅ 基础的元数据管理

**主要问题**：
1. **缺少意图识别系统**：每次都需要 LLM 理解用户意图，慢且不稳定
2. **工具调用不系统**：工具定义分散，缺少统一的调用机制
3. **上下文管理简单**：没有智能的上下文选择和优先级管理
4. **Prompt 管理混乱**：Prompt 分散在各个文件，难以维护和优化
5. **状态管理不完善**：缺少工作集、编辑历史等概念
6. **错误处理不够智能**：缺少自动修正和重试机制
7. **会话管理简单**：缺少会话持久化和恢复功能

**改进目标**：
1. 引入系统化的意图识别（提升响应速度 10x）
2. 建立完善的工具调用系统（提升可扩展性）
3. 优化上下文管理（减少 Token 消耗 50%）
4. 统一 Prompt 管理（提升可维护性）
5. 增强状态管理（支持多轮迭代）
6. 改进错误处理（提升成功率 20%）
7. 完善会话管理（提升用户体验）

---

## Glossary

### 核心概念

- **Intent（意图）**: 用户请求的类型（查询数据、创建可视化、解释结果等）
- **Working Set（工作集）**: 当前正在处理的 Tableau 对象集合（工作簿、图表、计算字段等）
- **Edit Step（编辑步骤）**: 一次完整的编辑操作，包含用户输入、AI 输出、状态变化
- **Tool（工具）**: LLM 可以调用的外部功能（查询元数据、执行 VizQL、搜索字段等）
- **Context Provider（上下文提供器）**: 提供特定类型上下文的组件（元数据、历史记录、相关对象等）
- **Prompt Template（Prompt 模板）**: 结构化的 Prompt 定义，支持变量替换和条件渲染

### LangChain/LangGraph 概念

- **StateGraph**: LangGraph 的状态图，定义工作流的节点和边
- **Checkpointer**: LangGraph 的检查点机制，用于状态持久化
- **Store**: LangGraph 的持久化存储，用于跨会话数据
- **Tool**: LangChain 的工具接口，标准化的函数调用
- **Retriever**: LangChain 的检索器，用于获取相关上下文
- **PromptTemplate**: LangChain 的 Prompt 模板系统
- **Router Chain**: LangChain 的路由链，用于意图识别

### Tableau 概念

- **VizQL**: Tableau 的查询语言
- **Datasource**: Tableau 数据源
- **Workbook**: Tableau 工作簿
- **Sheet**: Tableau 图表
- **Calculated Field**: Tableau 计算字段
- **Metadata**: 数据源元数据（字段、类型、关系等）

---

## Requirements


### Requirement 1: 意图识别系统（Intent Recognition System）

**User Story:** 作为系统，我想要快速准确地识别用户意图，以便选择合适的处理流程并提升响应速度。

**背景**：
- 当前系统每次都需要 LLM 理解用户意图，慢且不稳定
- VSCode Copilot 使用预定义意图枚举 + 上下文推断，速度快且准确
- 可以使用 LangChain 的 Router Chain 实现

#### Acceptance Criteria

1. WHEN 定义 Tableau 意图类型 THEN 系统 SHALL 支持以下预定义意图：
   - `QUERY_DATA`: 查询数据
   - `CREATE_VIZ`: 创建可视化
   - `MODIFY_VIZ`: 修改可视化
   - `EXPLAIN_VIZ`: 解释可视化
   - `CREATE_CALC`: 创建计算字段
   - `FIX_CALC`: 修复计算错误
   - `EXPLAIN_CALC`: 解释计算
   - `OPTIMIZE_WORKBOOK`: 优化工作簿
   - `ANALYZE_PERFORMANCE`: 分析性能
   - `HELP`: 帮助
   - `UNKNOWN`: 未知意图

2. WHEN 推断意图 THEN 系统 SHALL 使用以下规则（无需调用 LLM）：
   - 如果有选中的计算字段 + 有错误 → `FIX_CALC`
   - 如果有选中的图表 + 查询包含 "why" → `EXPLAIN_VIZ`
   - 如果查询包含 "create" + "calculation" → `CREATE_CALC`
   - 如果查询包含 "slow" 或 "performance" → `ANALYZE_PERFORMANCE`
   - 如果没有上下文 + 查询是问题 → `HELP`

3. WHEN 规则推断失败 THEN 系统 SHALL 使用 LangChain Router Chain 调用 LLM 分类

4. WHEN 实现意图接口 THEN 系统 SHALL 为每个意图创建一个类，实现以下方法：
   - `id`: 意图 ID
   - `description`: 意图描述
   - `invoke(context)`: 调用意图，返回处理结果

5. WHEN 选择处理流程 THEN 系统 SHALL 根据意图选择对应的 Agent 或工作流

6. WHEN 记录意图识别 THEN 系统 SHALL 记录识别方式（规则/LLM）、耗时、准确性

7. WHEN 评估效果 THEN 系统 SHALL 统计意图识别速度提升（目标：10x）和准确率（目标：90%+）

---

### Requirement 2: 工作集和编辑步骤管理（Working Set & Edit Step Management）

**User Story:** 作为系统，我想要跟踪用户正在处理的 Tableau 对象和编辑历史，以便支持多轮迭代和状态恢复。

**背景**：
- 当前系统缺少工作集概念，无法跟踪正在编辑的对象
- VSCode Agent Mode 使用 Working Set 跟踪所有文件，支持多轮迭代
- 可以使用 LangGraph 的状态管理实现

#### Acceptance Criteria

1. WHEN 定义工作集条目 THEN 系统 SHALL 包含以下字段：
   - `object_type`: 对象类型（sheet, calc_field, data_source 等）
   - `object_id`: 对象 ID
   - `object_name`: 对象名称
   - `state`: 状态（INITIAL, UNDECIDED, ACCEPTED, REJECTED）
   - `snapshot`: 对象快照（用于回滚）

2. WHEN 创建工作集 THEN 系统 SHALL 从用户上下文中提取对象（选中的图表、计算字段等）

3. WHEN AI 提出修改建议 THEN 系统 SHALL 更新对象状态为 UNDECIDED

4. WHEN 用户接受/拒绝建议 THEN 系统 SHALL 更新对象状态为 ACCEPTED/REJECTED

5. WHEN 下一轮对话 THEN 系统 SHALL 继承上一轮的工作集状态

6. WHEN 定义编辑步骤 THEN 系统 SHALL 包含以下字段：
   - `previous_step`: 上一个步骤（用于多轮对话）
   - `working_set`: 工作集
   - `user_message`: 用户消息
   - `assistant_reply`: AI 回复
   - `generated_vizql`: 生成的 VizQL 代码
   - `telemetry`: 遥测信息

7. WHEN 持久化编辑历史 THEN 系统 SHALL 使用 LangGraph Store 存储所有编辑步骤

8. WHEN 恢复会话 THEN 系统 SHALL 从 Store 加载编辑历史并恢复工作集状态

---

### Requirement 3: 系统化工具调用（Systematic Tool Calling）

**User Story:** 作为系统，我想要建立统一的工具调用机制，以便 LLM 能够自主调用工具并提供更好的可扩展性。

**背景**：
- 当前系统的工具定义分散，缺少统一的调用机制
- VSCode Copilot 使用标准化的工具接口和调用循环
- 可以使用 LangChain 的 Tool 接口实现

#### Acceptance Criteria

1. WHEN 定义工具接口 THEN 系统 SHALL 使用 LangChain 的 Tool 基类，包含：
   - `name`: 工具名称
   - `description`: 工具描述
   - `args_schema`: 输入参数 Schema（Pydantic）
   - `_run()`: 同步执行方法
   - `_arun()`: 异步执行方法

2. WHEN 实现 Tableau 工具 THEN 系统 SHALL 提供以下工具：
   - `GetMetadataTool`: 获取数据源元数据
   - `SearchFieldsTool`: 搜索字段（支持语义搜索和关键词搜索）
   - `ExecuteVizQLTool`: 执行 VizQL 查询
   - `ValidateVizQLTool`: 验证 VizQL 查询
   - `GetDimensionHierarchyTool`: 获取维度层级
   - `GetRelatedObjectsTool`: 获取相关对象（相关图表、计算字段等）

3. WHEN 注册工具 THEN 系统 SHALL 使用 LangChain 的工具注册机制，支持动态发现

4. WHEN LLM 调用工具 THEN 系统 SHALL 使用 LangChain 的 AgentExecutor 执行工具调用循环

5. WHEN 工具调用失败 THEN 系统 SHALL 返回结构化的错误信息，包含：
   - `error_type`: 错误类型
   - `error_message`: 错误消息
   - `suggestions`: 修正建议

6. WHEN 实现工具调用循环 THEN 系统 SHALL 最多调用 5 次工具（防止无限循环）

7. WHEN 记录工具调用 THEN 系统 SHALL 记录工具名称、输入、输出、耗时、成功/失败

8. WHEN 优化工具调用 THEN 系统 SHALL 缓存常用工具的结果（如元数据）

---

### Requirement 4: 智能上下文管理（Intelligent Context Management）

**User Story:** 作为系统，我想要智能地选择和管理上下文，以便减少 Token 消耗并提高 AI 输出质量。

**背景**：
- 当前系统的上下文管理简单，没有优先级和裁剪机制
- VSCode Copilot 使用上下文提供器和优先级裁剪
- 可以使用 LangChain 的 Retriever 实现

#### Acceptance Criteria

1. WHEN 定义上下文提供器接口 THEN 系统 SHALL 包含以下方法：
   - `get_context(query, max_tokens)`: 获取上下文
   - `priority`: 上下文优先级（1-10）

2. WHEN 实现上下文提供器 THEN 系统 SHALL 提供以下提供器：
   - `MetadataContextProvider`: 元数据上下文（优先级：9）
   - `DimensionHierarchyContextProvider`: 维度层级上下文（优先级：8）
   - `ConversationHistoryContextProvider`: 对话历史上下文（优先级：7）
   - `RelatedObjectsContextProvider`: 相关对象上下文（优先级：6）
   - `ExamplesContextProvider`: 示例上下文（优先级：5）

3. WHEN 获取元数据上下文 THEN 系统 SHALL 只返回与查询相关的字段（基于 Category 过滤）

4. WHEN 获取对话历史 THEN 系统 SHALL 压缩早期对话（保留最近 5 轮 + 摘要）

5. WHEN 计算 Token 数量 THEN 系统 SHALL 使用 tiktoken 库进行准确计算

6. WHEN 超出 Token 预算 THEN 系统 SHALL 按优先级裁剪低优先级上下文

7. WHEN 实现语义搜索 THEN 系统 SHALL 使用 LangChain 的 VectorStore 存储和检索相关对象

8. WHEN 记录上下文使用 THEN 系统 SHALL 记录每个提供器的 Token 消耗和裁剪情况

---

### Requirement 5: 统一 Prompt 管理（Unified Prompt Management）

**User Story:** 作为开发者，我想要统一管理所有 Prompt，以便提高可维护性和支持多模型适配。

**背景**：
- 当前系统的 Prompt 分散在各个文件，难以维护
- VSCode Copilot 使用组件化的 Prompt 系统
- 可以使用 LangChain 的 PromptTemplate 实现

#### Acceptance Criteria

1. WHEN 定义 Prompt 模板 THEN 系统 SHALL 使用 LangChain 的 ChatPromptTemplate

2. WHEN 组织 Prompt THEN 系统 SHALL 将所有 Prompt 集中在 `prompts/` 目录

3. WHEN 定义 Prompt 组件 THEN 系统 SHALL 支持以下通用组件：
   - `SystemMessage`: 系统消息（角色定义、规则等）
   - `MetadataContext`: 元数据上下文
   - `ConversationHistory`: 对话历史
   - `Examples`: 示例
   - `OutputFormat`: 输出格式说明

4. WHEN 渲染 Prompt THEN 系统 SHALL 支持变量替换和条件渲染

5. WHEN 支持多模型 THEN 系统 SHALL 为不同模型族提供不同的 Prompt 变体：
   - GPT-4: 详细指令 + 复杂思维链
   - GPT-3.5: 简化指令 + 减少 Token
   - Claude: 结构化标签格式

6. WHEN 选择 Prompt THEN 系统 SHALL 根据当前使用的模型自动选择对应的 Prompt

7. WHEN 优化 Prompt THEN 系统 SHALL 记录每个 Prompt 的效果（成功率、Token 消耗）

8. WHEN 版本管理 THEN 系统 SHALL 支持 Prompt 版本控制和 A/B 测试

---

### Requirement 6: 增强错误处理和自动修正（Enhanced Error Handling & Auto-correction）

**User Story:** 作为系统，我想要智能地处理错误并自动修正，以便提高查询成功率并减少用户等待时间。

**背景**：
- 当前系统的错误处理简单，缺少自动修正机制
- VSCode Copilot 使用 LLM 分析错误并生成修正方案
- 可以使用 LangChain 的 Agent 实现

#### Acceptance Criteria

1. WHEN 验证查询计划 THEN 系统 SHALL 检查以下错误：
   - 字段不存在
   - 聚合函数不合法
   - 过滤器语法错误
   - 数据类型不匹配

2. WHEN 发现字段不存在 THEN 系统 SHALL 使用 SearchFieldsTool 搜索相似字段

3. WHEN 发现聚合函数错误 THEN 系统 SHALL 使用 LLM 分析并修正聚合函数

4. WHEN 查询执行失败 THEN 系统 SHALL 捕获错误信息并使用 LLM 生成修正方案

5. WHEN 执行修正 THEN 系统 SHALL 最多重试 3 次

6. WHEN 重试失败 THEN 系统 SHALL 返回详细的错误信息和建议

7. WHEN 修正成功 THEN 系统 SHALL 记录修正前后的查询计划（用于学习）

8. WHEN 分析错误模式 THEN 系统 SHALL 统计常见错误类型和修正成功率

---

### Requirement 7: 完善会话管理（Complete Session Management）

**User Story:** 作为用户，我想要恢复之前的会话并继续对话，以便提升使用体验。

**背景**：
- 当前系统缺少会话持久化和恢复功能
- VSCode Copilot 支持会话历史和重放
- 可以使用 LangGraph 的 Checkpointer 实现

#### Acceptance Criteria

1. WHEN 创建会话 THEN 系统 SHALL 生成唯一的 session_id

2. WHEN 保存会话 THEN 系统 SHALL 使用 LangGraph Checkpointer 持久化状态

3. WHEN 恢复会话 THEN 系统 SHALL 从 Checkpointer 加载历史状态

4. WHEN 列出会话 THEN 系统 SHALL 返回用户的所有会话（包含创建时间、最后更新时间、摘要）

5. WHEN 删除会话 THEN 系统 SHALL 删除 Checkpointer 中的所有相关数据

6. WHEN 导出会话 THEN 系统 SHALL 支持导出为 JSON 格式（用于分析和调试）

7. WHEN 重放会话 THEN 系统 SHALL 支持重新执行历史对话（用于调试）

8. WHEN 管理会话 THEN 系统 SHALL 提供 API 端点用于会话的 CRUD 操作

---

### Requirement 8: 性能监控和优化（Performance Monitoring & Optimization）

**User Story:** 作为系统管理员，我想要监控系统性能并识别瓶颈，以便进行优化。

**背景**：
- 当前系统缺少系统化的性能监控
- 需要识别瓶颈并优化响应速度

#### Acceptance Criteria

1. WHEN 执行查询 THEN 系统 SHALL 记录每个阶段的耗时：
   - 意图识别
   - 问题理解
   - 查询规划
   - 工具调用
   - 查询执行
   - 后处理

2. WHEN 调用 LLM THEN 系统 SHALL 记录：
   - Token 消耗（输入/输出）
   - 响应时间
   - 模型名称
   - 成功/失败

3. WHEN 调用工具 THEN 系统 SHALL 记录：
   - 工具名称
   - 输入参数
   - 输出结果
   - 耗时
   - 成功/失败

4. WHEN 查询失败 THEN 系统 SHALL 记录：
   - 失败原因
   - 重试次数
   - 最终状态

5. WHEN 生成性能报告 THEN 系统 SHALL 包含：
   - 平均响应时间
   - 成功率
   - Token 消耗统计
   - 瓶颈分析
   - 优化建议

6. WHEN 实时监控 THEN 系统 SHALL 提供监控面板显示关键指标

7. WHEN 导出数据 THEN 系统 SHALL 支持导出为 CSV/JSON 格式

8. WHEN 设置告警 THEN 系统 SHALL 支持性能阈值告警（响应时间、成功率等）

---

### Requirement 9: 测试和验证框架（Testing & Validation Framework）

**User Story:** 作为开发者，我想要建立完善的测试框架，以便验证系统改进的效果并防止回归。

**背景**：
- 当前系统缺少系统化的测试框架
- 需要验证改进效果并防止回归

#### Acceptance Criteria

1. WHEN 测试意图识别 THEN 系统 SHALL 使用标准测试集评估准确率（目标：90%+）

2. WHEN 测试工具调用 THEN 系统 SHALL 验证所有工具都能正确执行

3. WHEN 测试错误处理 THEN 系统 SHALL 验证能够捕获和修正所有类型的错误

4. WHEN 测试上下文管理 THEN 系统 SHALL 验证 Token 消耗减少（目标：50%）

5. WHEN 测试会话管理 THEN 系统 SHALL 验证会话能够正确保存和恢复

6. WHEN 进行回归测试 THEN 系统 SHALL 确保新功能不影响现有功能

7. WHEN 测试性能 THEN 系统 SHALL 验证响应速度提升（目标：意图识别 10x，整体 2x）

8. WHEN 生成测试报告 THEN 系统 SHALL 包含测试覆盖率、通过率、失败原因分析

---

### Requirement 10: 文档和知识管理（Documentation & Knowledge Management）

**User Story:** 作为团队成员，我想要完善的文档，以便快速理解系统设计并进行协作开发。

**背景**：
- 当前系统缺少完善的文档
- 需要建立知识管理系统

#### Acceptance Criteria

1. WHEN 创建架构文档 THEN 系统 SHALL 包含：
   - 完整的架构图
   - 模块说明
   - 数据流图
   - 设计决策（ADR）

2. WHEN 编写 API 文档 THEN 系统 SHALL 包含：
   - 所有公共接口的说明
   - 参数和返回值
   - 示例代码

3. WHEN 编写开发指南 THEN 系统 SHALL 包含：
   - 环境搭建
   - 代码规范
   - 测试指南
   - 部署流程

4. WHEN 更新文档 THEN 系统 SHALL 确保文档与代码保持同步

5. WHEN 建立知识库 THEN 系统 SHALL 记录：
   - 常见问题
   - 最佳实践
   - 故障排查

6. WHEN 进行代码审查 THEN 系统 SHALL 使用 Checklist 确保代码质量

7. WHEN 分享知识 THEN 系统 SHALL 定期组织技术分享会

8. WHEN 收集反馈 THEN 系统 SHALL 建立反馈机制并持续改进

---

## 实施优先级

### 🔴 第一阶段：核心系统化功能（2-3 周）

**目标**：建立系统化的核心功能，快速见效

1. **Requirement 1: 意图识别系统** ⭐⭐⭐⭐⭐
   - 预期效果：响应速度提升 10x，准确率 90%+
   - 实施难度：中
   - 使用框架：LangChain Router Chain

2. **Requirement 3: 系统化工具调用** ⭐⭐⭐⭐⭐
   - 预期效果：提升可扩展性，统一工具管理
   - 实施难度：中
   - 使用框架：LangChain Tool

3. **Requirement 5: 统一 Prompt 管理** ⭐⭐⭐⭐
   - 预期效果：提升可维护性，支持多模型
   - 实施难度：低
   - 使用框架：LangChain PromptTemplate

### 🟡 第二阶段：增强功能（3-4 周）

**目标**：增强用户体验和系统能力

4. **Requirement 2: 工作集和编辑步骤管理** ⭐⭐⭐⭐
   - 预期效果：支持多轮迭代，提升用户体验
   - 实施难度：中
   - 使用框架：LangGraph State Management

5. **Requirement 4: 智能上下文管理** ⭐⭐⭐⭐
   - 预期效果：Token 消耗减少 50%，提升输出质量
   - 实施难度：中
   - 使用框架：LangChain Retriever + VectorStore

6. **Requirement 6: 增强错误处理和自动修正** ⭐⭐⭐⭐
   - 预期效果：成功率提升 20%
   - 实施难度：中
   - 使用框架：LangChain Agent

### 🟢 第三阶段：完善和优化（2-3 周）

**目标**：完善系统功能，优化性能

7. **Requirement 7: 完善会话管理** ⭐⭐⭐
   - 预期效果：支持会话恢复，提升用户体验
   - 实施难度：低
   - 使用框架：LangGraph Checkpointer

8. **Requirement 8: 性能监控和优化** ⭐⭐⭐
   - 预期效果：识别瓶颈，优化性能
   - 实施难度：低
   - 使用框架：自定义监控

9. **Requirement 9: 测试和验证框架** ⭐⭐⭐
   - 预期效果：防止回归，验证改进效果
   - 实施难度：中
   - 使用框架：pytest + 自定义测试工具

10. **Requirement 10: 文档和知识管理** ⭐⭐
    - 预期效果：提升团队协作效率
    - 实施难度：低
    - 使用框架：Markdown + MkDocs

---

## 预期成果

### 量化指标

| 指标 | 当前 | 目标 | 提升 |
|------|------|------|------|
| 意图识别速度 | ~2s | ~0.2s | 10x |
| 查询成功率 | ~70% | ~90% | +20% |
| Token 消耗 | 100% | 50% | -50% |
| 响应速度 | 100% | 50% | 2x |
| 代码可维护性 | 中 | 高 | +50% |

### 质量指标

- ✅ 系统化的意图识别
- ✅ 统一的工具调用机制
- ✅ 智能的上下文管理
- ✅ 完善的错误处理
- ✅ 良好的用户体验
- ✅ 高可维护性
- ✅ 高可扩展性

---

## 技术栈

### 核心框架

- **LangChain 0.3.21**: 工具调用、Prompt 管理、上下文管理
- **LangGraph 0.3.21**: 工作流编排、状态管理、会话持久化
- **Pydantic 2.x**: 数据验证和序列化
- **FastAPI**: REST API
- **SQLite**: 持久化存储

### 新增组件

- **LangChain Router Chain**: 意图识别
- **LangChain Tool**: 工具调用
- **LangChain Retriever**: 上下文检索
- **LangChain VectorStore**: 语义搜索
- **LangChain PromptTemplate**: Prompt 管理
- **LangGraph Checkpointer**: 会话持久化
- **tiktoken**: Token 计数

---

**文档版本**: v2.0  
**创建时间**: 2025-11-20  
**作者**: Kiro AI Assistant  
**状态**: 待审核
