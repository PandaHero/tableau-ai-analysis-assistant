# Tableau Assistant 系统化增强需求文档 (Final)

## 文档说明

本文档是基于深入理解累积洞察、重规划机制和任务调度器配合关系的最终统一版本，整合了所有之前版本的核心内容。

**核心理解**：
- ✅ **累积洞察**：多个 AI 并行分析一批查询结果，智能合成洞察（参考 BettaFish）
- ✅ **重规划**：循环迭代直到充分回答问题
- ✅ **任务调度器**：Query Builder + Query Executor + Data Processor + Date Utils + 查询结果缓存
- ✅ **任务 ID**：带轮次的唯一标识（r1_q0, r2_q0）避免重复
- ✅ **数据分块**：根据问题类型智能选择并行/串行策略
- ✅ **查询缓存**：1-2小时TTL，重规划时复用查询结果，解决上下文长度问题

**项目现状分析**：
- ✅ **Prompt 系统已经很好**：使用结构化的 4-section 模板
- ✅ **意图识别已实现**：在 Understanding Agent 中由 LLM 识别
- ✅ **基础架构完善**：LangGraph 工作流、Pydantic 模型、BaseAgent 架构
- ❌ **任务调度缺失**：QuerySubTask 生成后没有自动调度执行
- ❌ **累积洞察缺失**：没有多 AI 并行分析和智能合成机制
- ❌ **数据分块策略缺失**：不能根据问题类型智能分块
- ❌ **任务 ID 会重复**：重规划后可能出现 ID 冲突
- ❌ **查询结果缓存缺失**：重规划时需要重新执行所有查询
- ❌ **上下文管理简单**：缺少智能的上下文选择、优先级管理
- ❌ **会话管理不完善**：缺少持久化、恢复、历史管理

**核心改进方向**（4个主要需求）：
1. **任务调度器与查询执行增强**：自动调度 + 查询缓存 + 并行执行
2. **查询验证和错误修正**：提升查询成功率 20-30%
3. **智能上下文管理**：优化 Token 消耗 50%
4. **完善会话管理**：支持持久化和恢复

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

**改进目标**：
1. 建立系统化的工具调用和任务调度机制（提升可扩展性和可维护性）
2. 实现查询验证和错误修正循环（提升查询成功率 20-30%）
3. 优化上下文管理（减少 Token 消耗 50%，提升输出质量）
4. 完善会话管理（支持持久化、恢复、历史管理）

---

## Glossary

### 核心概念

- **Tool（工具）**: LLM 可以调用的外部功能（查询元数据、执行 VizQL、搜索字段等）
- **Tool Registry（工具注册表）**: 统一管理所有工具的注册、发现、调用
- **Task Scheduler（任务调度器）**: 自动执行 QuerySubTask，支持并行、串行、依赖管理
- **Query Result Cache（查询结果缓存）**: 缓存查询结果（1-2小时TTL），支持累积洞察和补充查询
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
- **PersistentStore**: 持久化存储，用于缓存查询结果

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
- **缺少查询结果缓存，重规划时需要重新执行所有查询**
- **浪费时间和资源，无法解决上下文长度问题**
- 缺少统一的工具注册和发现机制
- 没有工具调用循环和错误处理

**改进方案**：
- 使用 LangChain Tool 接口统一所有工具
- 建立工具注册表（Tool Registry）
- **实现任务调度器（Task Scheduler）支持：**
  - 自动执行 QuerySubTask（并行+串行）
  - **查询结果缓存（1-2 小时 TTL）**
  - **避免重复查询（重规划场景）**
  - **解决上下文长度问题**
- 使用 AgentExecutor 支持工具调用循环

**关键设计点**：

1. **累积洞察的正确理解**（参考 BettaFish）：
   ```
   Task Planner 生成一批任务：
   - r1_q0: 查询华东地区利润率
   - r1_q1: 查询华北地区利润率
   - r1_q2: 查询华南地区利润率
   - r1_q3: 查询全国平均利润率
   
   任务调度器并行执行 → 得到4个查询结果
   
   累积洞察分析（并行）：
   - AI宝宝1 分析 r1_q0 → 洞察：华东利润率 12%
   - AI宝宝2 分析 r1_q1 → 洞察：华北利润率 18%
   - AI宝宝3 分析 r1_q2 → 洞察：华南利润率 15%
   - AI宝宝4 分析 r1_q3 → 洞察：全国平均 15%
   
   Insight Coordinator 智能合成：
   - 识别关键发现：华东利润率最低
   - 对比分析：华东 < 华南 < 华北
   - 合成洞察："华东地区利润率最低（12%），低于全国平均 3 个百分点"
   ```

2. **重规划机制**（与累积洞察配合）：
   ```
   第1轮 → 累积洞察分析 → Replan Agent 判断
     ├─ 是否充分回答问题？
     ├─ 是 → 返回结果
     └─ 否 → 生成新问题 → 第2轮
   
   第2轮 → 重新执行 Understanding → Task Planner → 任务调度器
     → 累积洞察分析 → Replan Agent 判断
     → 循环直到充分回答
   ```

3. **查询结果缓存的重要性**：
   - **重规划场景**：第2轮可能需要第1轮的查询结果，通过缓存避免重复查询
   - **节省时间**：缓存命中时 0.1s vs 重新查询 5s（50x提升）
   - **解决上下文长度问题**：不需要把所有查询结果都放在上下文中，通过 task_id 引用
   - **支持多轮分析**：1-2小时TTL，支持用户在会话中多次引用历史数据

4. **任务调度器的职责**：
   - 自动执行 QuerySubTask（并行+串行+依赖管理）
   - 查询结果缓存（存储和检索）
   - 进度跟踪和实时反馈
   - 配合累积洞察机制：
     - **多任务场景**：为每个查询结果启动独立的洞察分析
     - **单任务分段场景**：为每个数据分块启动洞察分析（累积）

#### Acceptance Criteria

1. WHEN 定义工具接口 THEN 系统 SHALL 使用 LangChain 的 Tool 基类，包含：
   - `name`: 工具名称
   - `description`: 工具描述（供 LLM 理解）
   - `args_schema`: 输入参数 Schema（Pydantic）
   - `_run()`: 同步执行方法
   - `_arun()`: 异步执行方法

2. WHEN 实现 Tableau 工具 THEN 系统 SHALL 提供以下工具：
   - `GetMetadataTool`: 获取数据源元数据（封装 MetadataManager）
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

5. WHEN 实现查询结果缓存 THEN 系统 SHALL 缓存查询结果：
   - 使用 PersistentStore 存储查询结果
   - 缓存键基于查询内容的哈希（intents + question_text）
   - TTL 设置为 1-2 小时（支持重规划场景）
   - 执行查询前先检查缓存
   - 缓存命中时直接返回结果，避免重复查询
   - 记录缓存命中率

6. WHEN 解决上下文长度问题 THEN 系统 SHALL：
   - 不需要把所有查询结果都放在上下文中
   - 通过缓存存储查询结果
   - AI 可以通过 task_id 引用之前的查询结果
   - 只在需要时加载特定的查询结果
   - 大幅减少上下文长度，支持更多轮对话

7. WHEN 工具调用失败 THEN 系统 SHALL 返回结构化的错误信息：
   - `error_type`: 错误类型（validation, execution, timeout 等）
   - `error_message`: 错误消息
   - `suggestions`: 修正建议（可选）
   - `retry_count`: 重试次数

8. WHEN 使用 AgentExecutor THEN 系统 SHALL 支持工具调用循环：
   - 最多调用 5 次工具（防止无限循环）
   - 支持工具链式调用（一个工具的输出作为另一个工具的输入）
   - 记录所有工具调用（输入、输出、耗时）

9. WHEN 记录工具调用 THEN 系统 SHALL 使用 SQLiteTrackingCallback 记录：
   - 工具名称
   - 输入参数
   - 输出结果
   - 耗时
   - 成功/失败
   - 错误信息（如果失败）

10. WHEN 优化工具调用 THEN 系统 SHALL 缓存常用工具的结果：
    - 元数据缓存（1 小时）
    - 维度层级缓存（24 小时）
    - 查询结果缓存（1-2 小时）

---

### Requirement 2: 查询验证和错误修正循环（Query Validation & Error Correction）

**User Story:** 作为系统，我想要在查询执行前后进行验证和错误修正，以便提高查询成功率并减少用户等待时间。

**背景**：
- 当前查询执行失败时，直接返回错误给用户
- 缺少自动验证和修正机制
- 没有智能重试策略
- 用户需要手动修正错误并重新提问

**改进方案**：
- 查询执行前验证（字段存在性、聚合函数合法性）
- 查询执行失败后自动修正
- 智能重试机制（最多3次）
- 使用 LLM 分析错误并生成修正方案

#### Acceptance Criteria

1. WHEN 生成查询计划后 THEN 系统 SHALL 验证所有字段是否存在于元数据中

2. WHEN 验证发现字段不存在 THEN 系统 SHALL：
   - 在元数据中搜索相似字段（基于字段名相似度）
   - 使用 LLM 推断用户意图，选择最合适的字段
   - 自动修正字段名

3. WHEN 验证发现聚合函数不合法 THEN 系统 SHALL：
   - 检查聚合函数是否适用于字段类型
   - 使用 LLM 分析并修正聚合函数
   - 提供修正建议

4. WHEN 查询执行失败 THEN 系统 SHALL：
   - 捕获错误信息（VDS 返回的错误）
   - 使用 LLM 分析错误原因
   - 生成修正方案
   - 自动执行修正后的查询

5. WHEN 执行修正后的查询 THEN 系统 SHALL 最多重试 3 次：
   - 第1次：自动修正并重试
   - 第2次：使用备选方案重试
   - 第3次：简化查询重试
   - 超过3次：返回详细错误信息给用户

6. WHEN 重试次数超限 THEN 系统 SHALL 返回详细信息：
   - 原始错误信息
   - 已尝试的修正方案
   - 建议用户如何修改问题
   - 相关的元数据信息

7. WHEN 修正成功 THEN 系统 SHALL 记录修正信息：
   - 修正前的查询计划
   - 修正后的查询计划
   - 修正原因
   - 用于学习和优化

8. WHEN 分析错误模式 THEN 系统 SHALL 统计：
   - 常见错误类型（字段不存在、聚合函数错误、语法错误等）
   - 修正成功率
   - 平均重试次数
   - 用于优化验证和修正策略

---

### Requirement 3: 智能上下文管理（Intelligent Context Management）

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

### Requirement 4: 完善会话管理（Complete Session Management）

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

### 🔴 第一阶段：核心功能（4-5 周）

**目标**：建立系统化的核心功能

1. **Requirement 1: 系统化工具调用与任务调度** ⭐⭐⭐⭐⭐
   - 周 1-2: 实现工具接口和注册表
   - 周 2-3: 实现任务调度器（并行+串行+依赖管理）
   - 周 3: **实现查询结果缓存（关键！）**
   - 周 4: 集成 AgentExecutor 和测试
   - 预期效果：
     - 自动调度执行，提升可维护性
     - **通过缓存解决上下文长度问题**
     - **重规划时避免重复查询（150x 提升）**

2. **Requirement 2: 查询验证和错误修正循环** ⭐⭐⭐⭐⭐
   - 周 1: 实现查询前验证（字段、聚合函数）
   - 周 2: 实现错误捕获和分析
   - 周 3: 实现 LLM 驱动的自动修正
   - 周 4: 实现智能重试机制和测试
   - 预期效果：查询成功率提升 20-30%

3. **Requirement 3: 智能上下文管理** ⭐⭐⭐⭐⭐
   - 周 1-2: 实现上下文提供器系统
   - 周 2-3: 实现 Category 过滤和 Token 管理
   - 周 3-4: 实现对话历史压缩和测试
   - 预期效果：Token 消耗减少 50%

### 🟡 第二阶段：完善功能（2-3 周）

**目标**：完善用户体验

4. **Requirement 4: 完善会话管理** ⭐⭐⭐⭐
   - 周 1: 配置 SQLite Checkpointer
   - 周 2: 实现会话管理 API
   - 周 3: 实现会话恢复和重放
   - 预期效果：支持会话持久化和恢复

---

## 预期成果

### 量化指标

| 指标 | 当前 | 目标 | 提升 |
|------|------|------|------|
| **查询成功率** | ~70% | ~90% | **+20-30%** |
| Token 消耗 | 100% | 50% | -50% |
| 任务执行自动化 | 0% | 100% | +100% |
| **查询结果缓存** | ❌ | ✅ | **新功能** |
| **缓存命中时查询速度** | 5s | 0.1s | **50x** |
| **重规划时查询速度** | 15s | 0.1s | **150x** |
| **自动错误修正** | ❌ | ✅ | **新功能** |
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

- ✅ **多 AI 并行分析一批查询结果**
- ✅ **Insight Coordinator 智能合成洞察**
- ✅ **通过缓存避免重复查询（重规划场景）**
- ✅ **解决上下文长度问题（不需要把所有数据都放在上下文中）**
- ✅ **支持多轮重规划分析**

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
- **LangGraph PersistentStore**: 查询结果缓存
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

**文档版本**: Final  
**创建时间**: 2025-11-20  
**作者**: Kiro AI Assistant  
**状态**: 待审核


---

### Requirement 5: 增强数据处理器（Enhanced Data Processor）

**User Story:** 作为数据分析师，我想要使用更强大的数据处理和分析功能，以便进行深入的统计分析、时间序列预测和机器学习分析。

**背景**：
- 当前数据处理器只支持基础的同比、环比、占比计算
- 使用 Polars 库，但数据科学生态不如 pandas 丰富
- 缺少派生指标计算、数据画像、统计分析等高级功能
- 无法进行时间序列预测和机器学习分析
- 参考主流 AI 数据分析项目（PandasAI、LangChain Data Analysis、AutoML）

**改进方案**：
- 从 Polars 迁移到 pandas + numpy + scipy + scikit-learn 生态
- 添加派生指标计算（移动平均、累计、排名、RFM等）
- 添加数据画像功能（统计描述、分布分析、相关性分析）
- 添加统计分析（假设检验、回归分析、置信区间）
- 添加时间序列分析和预测（ARIMA、Prophet、异常检测）
- 添加机器学习分析（聚类、分类、异常检测、特征工程）
- 添加智能分析建议（自动推荐合适的分析方法）

#### Acceptance Criteria

**基础数据处理（保留现有功能）**

1. WHEN 执行同比分析 THEN 系统 SHALL 使用 pandas 计算同比增长率

2. WHEN 执行环比分析 THEN 系统 SHALL 使用 pandas 计算环比增长率

3. WHEN 执行占比分析 THEN 系统 SHALL 使用 pandas 计算各项占比

4. WHEN 执行自定义公式 THEN 系统 SHALL 使用 pandas 表达式引擎计算结果

**派生指标计算**

5. WHEN 计算移动平均 THEN 系统 SHALL 支持：
   - 简单移动平均（SMA）
   - 指数移动平均（EMA）
   - 加权移动平均（WMA）
   - 支持按分组计算

6. WHEN 计算累计指标 THEN 系统 SHALL 支持：
   - 累计求和（cumsum）
   - 累计乘积（cumprod）
   - 累计最大值/最小值
   - 支持按分组和排序计算

7. WHEN 计算排名指标 THEN 系统 SHALL 支持：
   - RANK（标准排名）
   - DENSE_RANK（密集排名）
   - ROW_NUMBER（行号）
   - 支持按分组和多字段排序

8. WHEN 计算窗口函数 THEN 系统 SHALL 支持：
   - LEAD（向前取值）
   - LAG（向后取值）
   - FIRST_VALUE（首值）
   - LAST_VALUE（末值）

9. WHEN 计算 RFM 指标 THEN 系统 SHALL 自动计算：
   - Recency（最近购买时间）
   - Frequency（购买频率）
   - Monetary（购买金额）
   - RFM 分数和分群

**数据画像**

10. WHEN 生成数据画像 THEN 系统 SHALL 自动分析：
    - 数据基本信息（行数、列数、内存占用）
    - 数值字段统计（均值、中位数、标准差、分位数）
    - 分类字段统计（唯一值数量、频数分布）
    - 时间字段统计（时间跨度、采样频率）
    - 缺失值分析
    - 异常值检测

11. WHEN 分析字段分布 THEN 系统 SHALL 提供：
    - 直方图统计数据
    - 正态性检验（Shapiro-Wilk、Kolmogorov-Smirnov）
    - 偏度和峰度
    - 分位数分析

12. WHEN 分析相关性 THEN 系统 SHALL 计算：
    - Pearson 相关系数矩阵
    - Spearman 秩相关系数矩阵
    - 协方差矩阵
    - 识别高相关性字段对（|r| > 0.7）

13. WHEN 检测异常值 THEN 系统 SHALL 支持：
    - IQR 方法（四分位距）
    - Z-score 方法（标准分数）
    - 可配置的阈值
    - 返回异常值标记和统计

**统计分析**

14. WHEN 执行假设检验 THEN 系统 SHALL 支持：
    - t检验（单样本、双样本、配对）
    - 卡方检验（独立性检验、拟合优度检验）
    - 方差分析（ANOVA）
    - 非参数检验（Mann-Whitney U、Kruskal-Wallis）
    - 返回检验统计量、p值、结论

15. WHEN 执行回归分析 THEN 系统 SHALL 支持：
    - 线性回归（OLS）
    - 多元回归
    - 逻辑回归
    - 岭回归（Ridge）、Lasso回归
    - 返回系数、R²、p值、残差分析

16. WHEN 计算置信区间 THEN 系统 SHALL 支持：
    - 均值置信区间
    - 比例置信区间
    - 预测区间
    - 可配置置信水平（默认95%）

**时间序列分析**

17. WHEN 分解时间序列 THEN 系统 SHALL 提取：
    - 趋势（Trend）
    - 季节性（Seasonality）
    - 残差（Residual）
    - 支持加法模型和乘法模型

18. WHEN 检验平稳性 THEN 系统 SHALL 执行：
    - ADF检验（Augmented Dickey-Fuller）
    - KPSS检验
    - 返回检验统计量、p值、是否平稳

19. WHEN 使用 ARIMA 预测 THEN 系统 SHALL：
    - 支持自动参数选择（auto_arima）
    - 支持季节性 ARIMA（SARIMA）
    - 返回预测值、置信区间、评估指标（MAE、RMSE）
    - 可配置预测期数

20. WHEN 使用 Prophet 预测 THEN 系统 SHALL：
    - 自动检测趋势和季节性
    - 支持节假日效应（可选）
    - 返回预测值、置信区间、组件分解
    - 可配置预测期数

21. WHEN 检测时间序列异常 THEN 系统 SHALL 支持：
    - 基于统计的异常检测（3-sigma规则）
    - 基于预测的异常检测（预测误差）
    - 季节性异常检测
    - 返回异常点位置和异常分数

**机器学习分析**

22. WHEN 执行聚类分析 THEN 系统 SHALL 支持：
    - K-Means聚类（支持自动选择最优K值）
    - DBSCAN密度聚类
    - 层次聚类（Hierarchical）
    - 返回聚类标签、聚类中心、评估指标（轮廓系数）

23. WHEN 执行分类分析 THEN 系统 SHALL 支持：
    - 决策树（Decision Tree）
    - 随机森林（Random Forest）
    - 梯度提升（XGBoost、LightGBM）
    - 返回预测结果、特征重要性、评估指标（准确率、F1-score）

24. WHEN 执行异常检测 THEN 系统 SHALL 支持：
    - Isolation Forest
    - One-Class SVM
    - Local Outlier Factor（LOF）
    - 返回异常标记和异常分数

25. WHEN 执行特征工程 THEN 系统 SHALL 支持：
    - 特征选择（SelectKBest、RFE）
    - 特征重要性排序
    - 主成分分析（PCA）
    - 特征标准化/归一化

**智能分析建议**

26. WHEN 接收到数据和问题 THEN 系统 SHALL 自动推荐：
    - 识别数据类型（数值型、分类型、时间型）
    - 评估数据质量（缺失值、异常值、分布）
    - 推荐合适的分析方法（优先级排序）
    - 说明推荐原因和预期洞察

27. WHEN 完成分析 THEN 系统 SHALL 提供：
    - 结构化的分析结果
    - 可视化建议（图表类型、配置）
    - 自然语言解释（用LLM生成）
    - 进一步分析建议

**性能和质量**

28. WHEN 处理大数据集 THEN 系统 SHALL：
    - 支持分块处理（chunk processing）
    - 使用向量化操作（避免循环）
    - 提供进度反馈
    - 处理时间不超过原Polars实现的2倍

29. WHEN 执行复杂分析 THEN 系统 SHALL：
    - 验证输入数据的有效性
    - 处理缺失值和异常值
    - 提供详细的错误信息
    - 记录分析参数和结果

30. WHEN 使用机器学习模型 THEN 系统 SHALL：
    - 自动划分训练集和测试集
    - 执行交叉验证
    - 返回模型评估指标
    - 支持模型持久化（可选）

---

## 实施优先级（更新）

### Phase 1: 核心功能（2周）
1. **任务调度器**
   - 实现任务调度器
   - 实现查询结果缓存
   - 集成到工作流

2. **查询验证和修正**
   - 实现查询验证器
   - 实现错误修正器
   - 集成重试机制

### Phase 2: 上下文优化（2周）
3. **上下文管理**
   - 实现上下文提供器系统
   - 实现 Token 预算管理
   - 实现对话历史压缩

### Phase 3: 会话管理（1周）
4. **会话管理**
   - 配置 SQLite Checkpointer
   - 实现会话管理 API
   - 数据迁移

### Phase 4: 数据处理器增强（3-4周）【新增】
5. **基础迁移**（1周）
   - 从 Polars 迁移到 pandas
   - 保持现有功能不变
   - 更新测试用例

6. **派生指标和数据画像**（1周）
   - 实现派生指标计算器
   - 实现数据画像处理器
   - 添加单元测试

7. **统计和时间序列分析**（1周）
   - 实现统计分析处理器
   - 实现时间序列处理器
   - 集成 ARIMA 和 Prophet

8. **机器学习和智能建议**（1周）
   - 实现机器学习处理器
   - 实现智能分析建议
   - 端到端测试

---

## 预期成果（更新）

### 功能成果
- ✅ **统一的工具调用机制**
- ✅ **智能任务调度器**（支持并行、串行、依赖管理）
- ✅ **查询结果缓存**（1-2小时TTL，解决上下文长度问题）
- ✅ **查询验证和错误修正**（提升成功率20-30%）
- ✅ **智能上下文管理**（减少Token消耗50%）
- ✅ **完善的会话管理**（支持持久化、恢复、历史）
- ✅ **支持多轮重规划分析**
- ✅ **强大的数据处理能力**（派生指标、统计分析、时间序列、机器学习）【新增】
- ✅ **智能分析建议**（自动推荐合适的分析方法）【新增】

### 性能成果
- 查询成功率：70% → 90%（+20-30%）
- Token 消耗：100% → 50%（-50%）
- 缓存命中时查询速度：5s → 0.1s（50x）
- 重规划时查询速度：15s → 0.1s（150x）
- 并发任务执行：串行 → 3并发（3x）
- 数据处理性能：保持在Polars实现的2倍以内【新增】

### 技术成果
- 清晰的架构设计
- 完善的错误处理
- 全面的测试覆盖
- 详细的文档
- 可扩展的设计
- 丰富的数据科学生态集成【新增】

---

## 技术栈（更新）

### 核心框架
- **LangChain**: LLM 应用框架
- **LangGraph**: 多智能体工作流
- **Pydantic**: 数据验证

### 数据处理【更新】
- **pandas**: 数据处理和分析（替代Polars）
- **numpy**: 数值计算
- **scipy**: 科学计算和统计分析
- **statsmodels**: 统计模型和时间序列分析
- **prophet**: Facebook时间序列预测
- **pmdarima**: 自动ARIMA参数选择
- **scikit-learn**: 机器学习算法
- **xgboost**: 梯度提升
- **lightgbm**: 轻量级梯度提升

### 存储
- **SQLite**: 本地数据库
- **PersistentStore**: 查询结果缓存
- **InMemorySaver**: 会话状态管理

### 工具
- **asyncio**: 并行任务执行
- **tiktoken**: Token 计算
- **difflib**: 字符串相似度

---
