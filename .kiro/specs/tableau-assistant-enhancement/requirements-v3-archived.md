# Tableau Assistant 系统化增强需求文档 v4.0 (Final)

## 文档说明

本文档基于深入理解累积洞察、重规划机制和任务调度器的配合关系重新编写。

**核心理解**：
- ✅ **累积洞察**：多个 AI 并行分析一批查询结果，智能合成洞察（参考 BettaFish）
- ✅ **重规划**：循环迭代直到充分回答问题
- ✅ **任务调度器**：包含 Query Builder、Query Executor、Data Processor、Date Utils
- ✅ **任务 ID**：带轮次的唯一标识（r1_q0, r2_q0）
- ✅ **数据分块**：根据问题类型决定并行/串行策略

**项目现状分析**：
- ✅ **Prompt 系统已经很好**：使用结构化的 4-section 模板
- ✅ **意图识别已实现**：在 Understanding Agent 中由 LLM 识别
- ✅ **基础架构完善**：LangGraph 工作流、Pydantic 模型、BaseAgent 架构
- ❌ **任务调度缺失**：QuerySubTask 生成后没有自动调度执行
- ❌ **累积洞察缺失**：没有多 AI 并行分析和智能合成机制
- ❌ **数据分块策略缺失**：不能根据问题类型智能分块
- ❌ **任务 ID 会重复**：重规划后可能出现 ID 冲突
- ❌ **上下文管理简单**：缺少智能的上下文选择、优先级管理
- ❌ **会话管理不完善**：缺少持久化、恢复、历史管理

**核心改进方向**（4 个）：
1. **任务调度器与查询执行**：Query Builder + Query Executor + Data Processor + Date Utils
2. **累积洞察分析系统**：多 AI 并行分析 + 智能合成（参考 BettaFish）
3. **智能上下文管理**：优化 Token 消耗
4. **完善会话管理**：支持持久化和恢复

**🔴 关键设计理念：累积洞察的正确理解**

累积洞察不是对单个查询结果分析，而是对一批查询结果进行并行分析和智能合成：

1. **累积洞察的真实含义**：
   ```
   Task Planner 生成一批任务：
   - r1_q0: 查询华东地区利润率
   - r1_q1: 查询华北地区利润率
   - r1_q2: 查询华南地区利润率
   - r1_q3: 查询全国平均利润率
   
   累积洞察分析：
   ┌─────────────────────────────────────────┐
   │ 多个 AI 宝宝并行吃饭                     │
   ├─────────────────────────────────────────┤
   │ AI宝宝1 分析 r1_q0（华东数据）           │
   │   → 如果数据量大，分块分析               │
   │   → 提取洞察：华东利润率 12%             │
   │                                          │
   │ AI宝宝2 分析 r1_q1（华北数据）           │
   │   → 分块分析                             │
   │   → 提取洞察：华北利润率 18%             │
   │                                          │
   │ AI宝宝3 分析 r1_q2（华南数据）           │
   │   → 分块分析                             │
   │   → 提取洞察：华南利润率 15%             │
   │                                          │
   │ AI宝宝4 分析 r1_q3（全国数据）           │
   │   → 分块分析                             │
   │   → 提取洞察：全国平均 15%               │
   └─────────────────────────────────────────┘
                     ↓
   ┌─────────────────────────────────────────┐
   │ Insight Coordinator 智能合成             │
   ├─────────────────────────────────────────┤
   │ - 识别关键发现：华东利润率最低           │
   │ - 对比分析：华东 < 华南 < 华北           │
   │ - 合成洞察："华东地区利润率最低（12%）， │
   │   低于全国平均 3 个百分点"               │
   └─────────────────────────────────────────┘
   ```

2. **重规划的真实流程**：
   ```
   第1轮 → 累积洞察分析 → Replan Agent 判断
     ├─ 是否充分回答问题？
     ├─ 是 → 返回结果
     └─ 否 → 生成新问题 → 第2轮
   
   第2轮 → 重新执行 Understanding → Task Planner → ...
     → 累积洞察分析 → Replan Agent 判断
     → 循环直到充分回答
   ```

3. **数据分块的关键问题**：
   - 排名问题：不能简单分块（每个 AI 都会说自己的最高）
   - 需要根据问题类型决定：并行还是串行、如何分块

---

## Introduction

Tableau Assistant 是一个基于 LangChain + LangGraph 的多智能体 Tableau 查询与分析系统。
当前系统已经实现了良好的基础架构，但在工具调用、上下文管理、会话管理等方面还需要系统化改进。

**项目优势**：
- ✅ 结构化的 Prompt 系统（4-section 模板 + JSON Schema）
- ✅ 清晰的 Agent 架构（BaseAgent + 7 个专业化 Agent）
- ✅ 完善的数据模型（Pydantic）
- ✅ 流式输出支持
- ✅ 基础的元数据管理和缓存

**核心问题**（仅 3 个）：
1. **工具调用不系统**：
   - 工具定义分散（simple_datasource_qa.py, metadata_manager.py 等）
   - 没有统一的工具注册和发现机制
   - 缺少工具调用循环和错误处理
   - QuerySubTask 生成后没有自动调度执行

2. **上下文管理简单**：
   - 元数据直接传递给 LLM，没有过滤和优先级
   - 缺少基于 Category 的智能过滤
   - 没有 Token 预算管理
   - 对话历史没有压缩

3. **会话管理不完善**：
   - 使用 InMemorySaver，重启后丢失
   - 缺少会话持久化和恢复
   - 没有会话历史管理
   - 无法查看和重放历史会话

**改进目标**：
1. 建立系统化的工具调用机制（提升可扩展性和可维护性）
2. 优化上下文管理（减少 Token 消耗 50%，提升输出质量）
3. 完善会话管理（支持持久化、恢复、历史管理）

---

## Glossary

### 核心概念

- **Tool（工具）**: LLM 可以调用的外部功能（查询元数据、执行 VizQL、搜索字段等）
- **Tool Registry（工具注册表）**: 统一管理所有工具的注册、发现、调用
- **Context Provider（上下文提供器）**: 提供特定类型上下文的组件（元数据、历史记录等）
- **Token Budget（Token 预算）**: LLM 输入的最大 Token 数量限制
- **Checkpointer**: LangGraph 的检查点机制，用于状态持久化
- **Session（会话）**: 一次完整的对话，包含多轮交互

### LangChain/LangGraph 概念

- **Tool**: LangChain 的工具接口，标准化的函数调用
- **AgentExecutor**: LangChain 的 Agent 执行器，支持工具调用循环
- **Retriever**: LangChain 的检索器，用于获取相关上下文
- **VectorStore**: LangChain 的向量存储，用于语义搜索
- **Checkpointer**: LangGraph 的持久化机制
- **Store**: LangGraph 的跨会话存储

### Tableau 概念

- **VizQL**: Tableau 的查询语言
- **VDS**: VizQL Data Service，Tableau 的查询 API
- **Metadata**: 数据源元数据（字段、类型、关系等）
- **QuerySubTask**: 查询子任务，包含 Intent 和字段映射

---

## Requirements


### Requirement 1: 系统化工具调用与任务调度（Systematic Tool Calling & Task Scheduling）

**User Story:** 作为系统，我想要建立统一的工具调用机制和智能任务调度器，以便支持累积洞察分析、自动执行补充查询，并通过缓存解决上下文长度问题。

**背景**：
- 当前工具定义分散（simple_datasource_qa.py, metadata_manager.py, query_executor.py 等）
- QuerySubTask 生成后没有自动调度执行，需要手动调用
- **缺少查询结果缓存，无法支持累积洞察和补充查询**
- **重规划时需要重新执行所有查询，浪费时间和资源**
- 缺少统一的工具注册和发现机制
- 没有工具调用循环和错误处理

**改进方案**：
- 使用 LangChain Tool 接口统一所有工具
- 建立工具注册表（Tool Registry）
- **实现任务调度器（Task Scheduler）支持：**
  - 自动执行 QuerySubTask（并行+串行）
  - **查询结果缓存（1-2 小时 TTL）**
  - **支持累积洞察的补充查询**
  - **避免重复查询，解决上下文长度问题**
- 使用 AgentExecutor 支持工具调用循环

**关键设计点**：
1. **任务调度器不仅仅是组件调度**，更重要的是：
   - 配合累积洞察机制
   - 通过查询结果缓存解决上下文长度问题
   - 支持渐进式分析和补充查询

2. **累积洞察场景**：
   - AI 分析第一块数据，发现数据不足
   - 触发补充查询（不是用户不满意，是 AI 主动决策）
   - 任务调度器执行补充查询
   - 通过缓存避免重复查询之前的数据
   - 继续累积洞察分析

3. **查询结果缓存的重要性**：
   - 支持累积洞察的多轮分析
   - 避免重复查询，节省时间
   - 解决上下文长度问题（不需要把所有数据都放在上下文中）
   - 支持补充查询场景

#### Acceptance Criteria

1. WHEN 定义工具接口 THEN 系统 SHALL 使用 LangChain 的 Tool 基类，包含：
   - `name`: 工具名称
   - `description`: 工具描述（供 LLM 理解）
   - `args_schema`: 输入参数 Schema（Pydantic）
   - `_run()`: 同步执行方法
   - `_arun()`: 异步执行方法

2. WHEN 实现 Tableau 工具 THEN 系统 SHALL 提供以下工具：
   - `GetMetadataTool`: 获取数据源元数据（封装 MetadataManager）
   - `SearchFieldsTool`: 搜索字段（支持语义搜索和关键词搜索）
   - `ExecuteVizQLTool`: 执行 VizQL 查询（封装 QueryExecutor）
   - `ValidateVizQLTool`: 验证 VizQL 查询
   - `GetDimensionHierarchyTool`: 获取维度层级
   - `ExecuteSubtaskTool`: 执行 QuerySubTask（封装 QueryExecutor.execute_subtask）

3. WHEN 注册工具 THEN 系统 SHALL 建立工具注册表（ToolRegistry）：
   - 支持动态注册工具
   - 支持按名称查找工具
   - 支持列出所有可用工具
   - 支持工具分类（metadata, query, validation 等）

4. WHEN 实现任务调度器 THEN 系统 SHALL 自动执行 QuerySubTask：
   - 从 QueryPlanningResult 中提取所有 QuerySubTask
   - 按依赖关系排序（处理 depends_on）
   - 并行执行独立的子任务（使用 asyncio）
   - 串行执行有依赖的子任务
   - 收集所有结果并更新状态
   - **支持进度跟踪和实时反馈**

4.1. WHEN 实现查询结果缓存 THEN 系统 SHALL 缓存查询结果：
   - 使用 PersistentStore 存储查询结果
   - 缓存键基于查询内容的哈希（intents + question_text）
   - TTL 设置为 1-2 小时（支持累积洞察和补充查询）
   - 执行查询前先检查缓存
   - 缓存命中时直接返回结果，避免重复查询
   - 记录缓存命中率

4.2. WHEN 支持累积洞察的补充查询 THEN 系统 SHALL：
   - 在累积洞察分析过程中，AI 可以触发补充查询
   - 补充查询作为新的 QuerySubTask 添加到调度器
   - 调度器自动执行补充查询
   - 利用缓存避免重复查询之前的数据
   - 将补充查询结果提供给累积洞察分析
   - 记录补充查询的触发原因和结果

4.3. WHEN 解决上下文长度问题 THEN 系统 SHALL：
   - 不需要把所有查询结果都放在上下文中
   - 通过缓存存储查询结果
   - AI 可以通过 task_id 引用之前的查询结果
   - 只在需要时加载特定的查询结果
   - 大幅减少上下文长度，支持更多轮对话

5. WHEN 工具调用失败 THEN 系统 SHALL 返回结构化的错误信息：
   - `error_type`: 错误类型（validation, execution, timeout 等）
   - `error_message`: 错误消息
   - `suggestions`: 修正建议（可选）
   - `retry_count`: 重试次数

6. WHEN 使用 AgentExecutor THEN 系统 SHALL 支持工具调用循环：
   - 最多调用 5 次工具（防止无限循环）
   - 支持工具链式调用（一个工具的输出作为另一个工具的输入）
   - 记录所有工具调用（输入、输出、耗时）

7. WHEN 记录工具调用 THEN 系统 SHALL 使用 SQLiteTrackingCallback 记录：
   - 工具名称
   - 输入参数
   - 输出结果
   - 耗时
   - 成功/失败
   - 错误信息（如果失败）

8. WHEN 优化工具调用 THEN 系统 SHALL 缓存常用工具的结果：
   - 元数据缓存（1 小时）
   - 维度层级缓存（24 小时）
   - 查询结果缓存（可选，5 分钟）

---

### Requirement 2: 智能上下文管理（Intelligent Context Management）

**User Story:** 作为系统，我想要智能地选择和管理上下文，以便减少 Token 消耗并提高 AI 输出质量。

**背景**：
- 当前元数据直接传递给 LLM，没有过滤和优先级
- 一个数据源可能有 100+ 字段，导致 Token 消耗过高
- 缺少基于 Category 的智能过滤
- 对话历史没有压缩，超过 10 轮后 Token 消耗过高

**改进方案**：
- 实现上下文提供器（Context Provider）系统
- 基于 Category 过滤元数据
- 使用 Token 预算管理
- 压缩对话历史

#### Acceptance Criteria

1. WHEN 定义上下文提供器接口 THEN 系统 SHALL 包含以下方法：
   - `get_context(query, max_tokens)`: 获取上下文
   - `priority`: 上下文优先级（1-10，10 最高）
   - `estimate_tokens(context)`: 估算 Token 数量

2. WHEN 实现上下文提供器 THEN 系统 SHALL 提供以下提供器：
   - `MetadataContextProvider`: 元数据上下文（优先级：9）
     - 基于 Category 过滤字段
     - 只返回与查询相关的字段
   - `DimensionHierarchyContextProvider`: 维度层级上下文（优先级：8）
     - 只返回相关 Category 的层级
   - `ConversationHistoryContextProvider`: 对话历史上下文（优先级：7）
     - 保留最近 5 轮完整对话
     - 压缩早期对话为摘要
   - `ExamplesContextProvider`: 示例上下文（优先级：5）
     - 提供 VizQL 查询示例

3. WHEN 过滤元数据 THEN 系统 SHALL 基于 Category 智能过滤：
   - 从 Understanding 结果中提取涉及的 Category
   - 只保留相关 Category 的维度字段
   - 保留所有度量字段
   - 记录过滤前后的字段数量和 Token 数量

4. WHEN 计算 Token 数量 THEN 系统 SHALL 使用 tiktoken 库：
   - 准确计算每个上下文的 Token 数量
   - 支持不同模型的 Token 计算（gpt-4, gpt-3.5 等）
   - 提供 Token 预算管理（默认 8000 tokens）

5. WHEN 超出 Token 预算 THEN 系统 SHALL 按优先级裁剪：
   - 保留高优先级上下文（元数据、维度层级）
   - 裁剪低优先级上下文（示例、早期对话）
   - 记录裁剪的内容和原因

6. WHEN 压缩对话历史 THEN 系统 SHALL 使用 LLM 生成摘要：
   - 保留最近 5 轮完整对话
   - 将早期对话（5 轮以前）压缩为摘要
   - 摘要包含关键信息（问题、结果、决策）
   - 摘要长度不超过原内容的 30%

7. WHEN 记录上下文使用 THEN 系统 SHALL 记录以下信息：
   - 每个提供器的 Token 消耗
   - 裁剪的内容和原因
   - 过滤前后的字段数量
   - Token 预算使用情况

8. WHEN 评估效果 THEN 系统 SHALL 统计：
   - Token 消耗减少比例（目标：50%）
   - 输出质量变化（通过测试集评估）
   - 响应速度变化

---

### Requirement 3: 完善会话管理（Complete Session Management）

**User Story:** 作为用户，我想要恢复之前的会话并继续对话，以便提升使用体验。

**背景**：
- 当前使用 InMemorySaver，重启后会话丢失
- 缺少会话持久化和恢复功能
- 没有会话历史管理（列表、搜索、删除）
- 无法查看和重放历史会话

**改进方案**：
- 使用 LangGraph 的 SQLite Checkpointer 持久化会话
- 实现会话管理 API（CRUD 操作）
- 支持会话恢复和重放

#### Acceptance Criteria

1. WHEN 配置 Checkpointer THEN 系统 SHALL 使用 SQLite Checkpointer：
   - 存储路径：`data/checkpoints.db`
   - 自动创建数据库和表
   - 支持并发访问
   - 定期清理过期会话（30 天）

2. WHEN 创建会话 THEN 系统 SHALL 生成唯一的 session_id：
   - 使用 UUID 格式
   - 记录创建时间
   - 记录用户 ID
   - 记录数据源 LUID

3. WHEN 保存会话 THEN 系统 SHALL 持久化以下信息：
   - 完整的状态（VizQLState）
   - 对话历史（所有轮次）
   - 工具调用记录
   - 性能指标

4. WHEN 恢复会话 THEN 系统 SHALL 从 Checkpointer 加载：
   - 完整的状态
   - 对话历史
   - 继续对话（保持上下文）

5. WHEN 列出会话 THEN 系统 SHALL 返回用户的所有会话：
   - 会话 ID
   - 创建时间
   - 最后更新时间
   - 对话轮数
   - 摘要（第一个问题）
   - 状态（active, completed, error）

6. WHEN 搜索会话 THEN 系统 SHALL 支持以下条件：
   - 按时间范围搜索
   - 按关键词搜索（问题内容）
   - 按数据源搜索
   - 按状态搜索

7. WHEN 删除会话 THEN 系统 SHALL 删除所有相关数据：
   - Checkpointer 中的状态
   - Store 中的数据（如果有）
   - 工具调用记录

8. WHEN 导出会话 THEN 系统 SHALL 支持导出为 JSON：
   - 完整的对话历史
   - 所有状态变化
   - 工具调用记录
   - 性能指标

9. WHEN 重放会话 THEN 系统 SHALL 支持重新执行历史对话：
   - 按顺序重放每一轮
   - 记录重放结果
   - 对比原始结果和重放结果
   - 用于调试和测试

10. WHEN 实现会话管理 API THEN 系统 SHALL 提供以下端点：
    - `POST /api/sessions`: 创建会话
    - `GET /api/sessions`: 列出会话
    - `GET /api/sessions/{session_id}`: 获取会话详情
    - `DELETE /api/sessions/{session_id}`: 删除会话
    - `POST /api/sessions/{session_id}/restore`: 恢复会话
    - `GET /api/sessions/{session_id}/export`: 导出会话
    - `POST /api/sessions/{session_id}/replay`: 重放会话

---

## 实施优先级

### 🔴 第一阶段：核心功能（3-4 周）

**目标**：建立系统化的核心功能

1. **Requirement 1: 系统化工具调用与任务调度** ⭐⭐⭐⭐⭐
   - 周 1-2: 实现工具接口和注册表
   - 周 2-3: 实现任务调度器（并行+串行+依赖管理）
   - 周 3: **实现查询结果缓存（关键！）**
   - 周 4: 集成 AgentExecutor 和测试
   - 预期效果：
     - 自动调度执行，提升可维护性
     - **支持累积洞察和补充查询**
     - **通过缓存解决上下文长度问题**
     - **重规划时避免重复查询（150x 提升）**

2. **Requirement 2: 智能上下文管理** ⭐⭐⭐⭐⭐
   - 周 1-2: 实现上下文提供器系统
   - 周 2-3: 实现 Category 过滤和 Token 管理
   - 周 3-4: 实现对话历史压缩和测试
   - 预期效果：Token 消耗减少 50%

### 🟡 第二阶段：完善功能（2-3 周）

**目标**：完善用户体验

3. **Requirement 3: 完善会话管理** ⭐⭐⭐⭐
   - 周 1: 配置 SQLite Checkpointer
   - 周 2: 实现会话管理 API
   - 周 3: 实现会话恢复和重放
   - 预期效果：支持会话持久化和恢复

---

## 预期成果

### 量化指标

| 指标 | 当前 | 目标 | 提升 |
|------|------|------|------|
| Token 消耗 | 100% | 50% | -50% |
| 任务执行自动化 | 0% | 100% | +100% |
| **查询结果缓存** | ❌ | ✅ | **新功能** |
| **缓存命中时查询速度** | 5s | 0.1s | **50x** |
| **重规划时查询速度** | 15s | 0.1s | **150x** |
| 会话持久化 | ❌ | ✅ | 新功能 |
| 工具可扩展性 | 低 | 高 | +100% |

### 质量指标

- ✅ 统一的工具调用机制
- ✅ 自动化的任务调度
- ✅ **查询结果缓存（支持累积洞察）**
- ✅ **解决上下文长度问题**
- ✅ 智能的上下文管理
- ✅ 完善的会话管理
- ✅ 高可维护性
- ✅ 高可扩展性

### 累积洞察支持

- ✅ **支持渐进式分析（一口一口吃饭）**
- ✅ **支持补充查询（AI 主动决策）**
- ✅ **通过缓存避免重复查询**
- ✅ **解决上下文长度问题（不需要把所有数据都放在上下文中）**
- ✅ **支持多轮累积洞察分析**

---

## 技术栈

### 核心框架

- **LangChain 0.3.21**: 工具调用、上下文管理
- **LangGraph 0.3.21**: 工作流编排、状态管理、会话持久化
- **Pydantic 2.x**: 数据验证和序列化
- **FastAPI**: REST API
- **SQLite**: 持久化存储

### 新增组件

- **LangChain Tool**: 工具接口
- **LangChain AgentExecutor**: 工具调用循环
- **LangGraph SQLite Checkpointer**: 会话持久化
- **tiktoken**: Token 计数
- **asyncio**: 并行任务执行

---

## 不需要的功能（明确排除）

### ❌ 1. 意图识别系统
**原因**：已在 Understanding Agent 中由 LLM 实现
- 当前实现：LLM 识别 question_type, complexity, mentioned_dimensions 等
- 效果良好，无需改进

### ❌ 2. 工作集和编辑步骤管理
**原因**：当前只处理数据源查询，不涉及工作簿和看板编辑
- 当前范围：数据查询和分析
- 未来可能：如果扩展到工作簿编辑，再考虑

### ❌ 3. Prompt 系统改进
**原因**：当前 Prompt 系统已经很好
- 当前实现：4-section 结构化模板 + 自动 JSON Schema 注入
- 效果良好，无需改进

---

**文档版本**: v3.0 (Final)  
**创建时间**: 2025-11-20  
**作者**: Kiro AI Assistant  
**状态**: 待审核
