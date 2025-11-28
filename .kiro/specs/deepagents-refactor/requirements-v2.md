# Tableau Assistant DeepAgents 重构需求文档 v2.0

**版本**: 2.0  
**日期**: 2025-01-15  
**状态**: 待评审

---

## 📋 文档说明

本文档是基于实际项目分析和讨论后的更新版本，修正了 v1.0 中的一些假设和过度设计。

**主要变化**：
1. 明确使用 DeepAgents 的 6 个 Middleware
2. 不使用 SubAgentMiddleware，改用 StateGraph 精确控制
3. 添加重规划场景的 TodoList 和 HITL 需求
4. 使用现有的模型选择和 Store 功能
5. 使用 SQLite 持久化，不引入 Redis

---

## 简介

本文档定义了将现有 Tableau Assistant 系统重构为基于 DeepAgents 框架的需求。重构目标是利用 DeepAgents 的内置功能（Prompt 缓存、对话总结、任务管理等），同时保持现有架构的精确流程控制。

---

## 术语表

- **DeepAgents**: LangChain 官方的 Agent 框架，提供内置 Middleware
- **Middleware**: 中间件，DeepAgents 提供 7 个内置 Middleware
- **StateGraph**: LangGraph 的状态图，用于精确控制 Agent 流程
- **TodoListMiddleware**: 任务列表管理中间件
- **HumanInTheLoopMiddleware**: 人工介入中间件
- **Store**: LangGraph 的 SQLite 持久化存储
- **VizQL**: Tableau 的查询语言
- **Runtime**: LangGraph 运行时上下文

---

## 需求

### 需求 1: DeepAgents 框架集成

**用户故事**: 作为开发者，我希望集成 DeepAgents 框架，以便利用其内置的 Middleware 功能，减少自定义代码。

#### 验收标准

1. WHEN 系统启动时 THEN 系统应使用 `create_deep_agent()` 创建主 Agent
2. WHEN 创建主 Agent 时 THEN 系统应配置 8 个自定义 Tableau 工具
3. WHEN 创建主 Agent 时 THEN 系统应启用 AnthropicPromptCachingMiddleware（使用 Claude 时）
4. WHEN 创建主 Agent 时 THEN 系统应启用 SummarizationMiddleware（长对话场景）
5. WHEN 创建主 Agent 时 THEN 系统应启用 FilesystemMiddleware（大结果集场景）
6. WHEN 创建主 Agent 时 THEN 系统应启用 PatchToolCallsMiddleware（自动修复工具调用）
7. WHEN 创建主 Agent 时 THEN 系统应启用 TodoListMiddleware（重规划场景）
8. WHEN 创建主 Agent 时 THEN 系统应启用 HumanInTheLoopMiddleware（重规划场景）
9. WHEN 创建主 Agent 时 THEN 系统应禁用 SubAgentMiddleware（使用 StateGraph 代替）
10. WHEN 系统使用现有模型选择功能时 THEN 系统应调用 `select_model()` 函数
11. WHEN 系统使用现有 Store 时 THEN 系统应使用 SQLite 持久化存储

### 需求 2: StateGraph 流程控制

**用户故事**: 作为系统架构师，我希望使用 StateGraph 精确控制 Agent 流程，以便保持固定的业务流程（Boost → Understanding → Planning → Execute → Insight → Replanner）。

#### 验收标准

1. WHEN 系统初始化时 THEN 系统应创建 StateGraph 定义流程
2. WHEN 定义流程时 THEN 系统应添加 Boost Agent 节点（可选）
3. WHEN 定义流程时 THEN 系统应添加 Understanding Agent 节点
4. WHEN 定义流程时 THEN 系统应添加 Planning Agent 节点
5. WHEN 定义流程时 THEN 系统应添加 Execute Query 节点
6. WHEN 定义流程时 THEN 系统应添加 Insight Agent 节点
7. WHEN 定义流程时 THEN 系统应添加 Replanner Agent 节点
8. WHEN 用户问题不需要优化时 THEN 系统应跳过 Boost Agent
9. WHEN Replanner 决定需要重规划时 THEN 系统应循环回到 Understanding Agent
10. WHEN Replanner 决定分析完成时 THEN 系统应结束流程
11. WHEN 各节点执行时 THEN 系统应使用现有的 Agent 温度配置（ModelConfig）

### 需求 3: Tableau 工具封装

**用户故事**: 作为开发者，我希望将现有的 Tableau 组件封装为 LangChain 工具，以便 DeepAgents 可以调用它们。

#### 验收标准

1. WHEN 封装工具时 THEN 系统应将 MetadataManager 封装为 `get_metadata` 工具
2. WHEN 封装工具时 THEN 系统应将 DateParser 封装为 `parse_date` 工具
3. WHEN 封装工具时 THEN 系统应将 QueryBuilder 封装为 `build_vizql_query` 工具
4. WHEN 封装工具时 THEN 系统应将 QueryExecutor 封装为 `execute_vizql_query` 工具
5. WHEN 封装工具时 THEN 系统应将 SemanticMapper 封装为 `semantic_map_fields` 工具
6. WHEN 封装工具时 THEN 系统应将 DataProcessor 封装为 `process_query_result` 工具
7. WHEN 封装工具时 THEN 系统应将 StatisticsDetector 封装为 `detect_statistics` 工具
8. WHEN 封装工具时 THEN 系统应使用 FilesystemMiddleware 提供 `save_large_result` 工具
9. WHEN 封装工具时 THEN 系统应保持现有组件的业务逻辑不变
10. WHEN 封装工具时 THEN 系统应使用 `@tool` 装饰器定义工具
11. WHEN 定义工具时 THEN 系统应提供清晰的文档字符串和参数说明

### 需求 4: Prompt 缓存支持

**用户故事**: 作为系统管理员，我希望利用 Prompt 缓存降低 API 成本，特别是在使用 Claude 时。

#### 验收标准

1. WHEN 系统使用 Claude 模型时 THEN 系统应自动启用 AnthropicPromptCachingMiddleware
2. WHEN 系统使用其他模型时 THEN 系统应使用现有的 Store 缓存业务数据
3. WHEN Prompt 缓存命中时 THEN 系统应降低 90% 的 API 成本（Claude）
4. WHEN 系统配置模型时 THEN 系统应支持灵活切换不同 LLM 提供商
5. WHEN 系统配置模型时 THEN 系统应使用现有的 `select_model()` 函数

### 需求 5: 对话总结功能

**用户故事**: 作为用户，我希望系统在长对话时自动总结历史，以便保持对话连贯性并避免上下文溢出。

#### 验收标准

1. WHEN 对话轮数达到 10 轮时 THEN 系统应触发 SummarizationMiddleware
2. WHEN 触发总结时 THEN 系统应生成对话历史的自然语言总结
3. WHEN 生成总结后 THEN 系统应压缩历史消息，保留关键信息
4. WHEN 总结完成后 THEN 系统应继续对话，使用压缩后的历史
5. WHEN 总结时 THEN 系统应保留 Insight Agent 生成的数据洞察（不被总结覆盖）

### 需求 6: 重规划任务管理

**用户故事**: 作为用户，我希望系统在发现需要深入分析时，能够生成多个问题并让我选择，然后自动管理这些任务的执行。

#### 验收标准

1. WHEN Replanner Agent 决定需要重规划时 THEN 系统应生成 2-5 个建议问题
2. WHEN 生成建议问题后 THEN 系统应触发 HumanInTheLoopMiddleware 暂停
3. WHEN 系统暂停时 THEN 系统应通过 API 展示建议问题给用户
4. WHEN 展示问题时 THEN 系统应提供选项：执行全部、选择部分、修改问题、不继续
5. WHEN 用户选择后 THEN 系统应将选中的问题添加到 TodoListMiddleware
6. WHEN 任务添加后 THEN 系统应自动管理任务队列（优先级、状态）
7. WHEN 执行任务时 THEN 系统应依次执行每个问题（Understanding → ... → Insight）
8. WHEN 所有任务完成后 THEN 系统应汇总所有洞察返回给用户
9. WHEN 用户选择不继续时 THEN 系统应结束分析流程
10. WHEN 重规划超时（5分钟）时 THEN 系统应自动执行所有建议问题

### 需求 7: 文件系统支持

**用户故事**: 作为开发者，我希望系统能够自动处理大结果集，将其保存到文件系统而不是内存中。

#### 验收标准

1. WHEN 查询结果超过 10MB 时 THEN 系统应使用 FilesystemMiddleware 保存结果
2. WHEN 保存结果时 THEN 系统应生成唯一的文件 ID
3. WHEN 保存完成后 THEN 系统应返回文件路径给 Agent
4. WHEN Agent 需要访问大结果时 THEN 系统应从文件系统加载
5. WHEN 会话结束时 THEN 系统应清理临时文件
6. WHEN 文件系统配置时 THEN 系统应使用 `data/agent_files` 作为基础路径

### 需求 8: 工具调用修复

**用户故事**: 作为开发者，我希望系统能够自动修复常见的工具调用错误，以便提升查询成功率。

#### 验收标准

1. WHEN Agent 调用工具时参数类型错误 THEN 系统应自动转换类型
2. WHEN Agent 调用工具时缺少必需参数 THEN 系统应使用默认值或提示 Agent
3. WHEN Agent 调用工具时参数名拼写错误 THEN 系统应自动纠正
4. WHEN 工具调用修复后 THEN 系统应记录修复日志
5. WHEN 工具调用无法修复时 THEN 系统应返回清晰的错误信息给 Agent

### 需求 9: 数据洞察保留

**用户故事**: 作为用户，我希望系统保留 Insight Agent 生成的数据洞察，即使在对话总结时也不丢失。

#### 验收标准

1. WHEN Insight Agent 生成洞察时 THEN 系统应使用结构化格式（Pydantic 模型）
2. WHEN 生成洞察时 THEN 系统应包含洞察类型（对比、趋势、排名、组成）
3. WHEN 生成洞察时 THEN 系统应包含关键发现和可操作建议
4. WHEN 生成洞察时 THEN 系统应包含置信度评分
5. WHEN SummarizationMiddleware 触发时 THEN 系统应保留所有结构化洞察
6. WHEN 对话总结时 THEN 系统应只总结对话历史，不总结数据洞察
7. WHEN 返回结果时 THEN 系统应同时返回对话总结和数据洞察

### 需求 10: 现有功能保留

**用户故事**: 作为开发者，我希望保留所有现有的功能和配置，避免重复造轮子。

#### 验收标准

1. WHEN 系统选择模型时 THEN 系统应使用现有的 `select_model()` 函数
2. WHEN 系统配置 Agent 温度时 THEN 系统应使用现有的 `ModelConfig` 类
3. WHEN 系统缓存数据时 THEN 系统应使用现有的 Store（SQLite）
4. WHEN 系统管理元数据时 THEN 系统应使用现有的 MetadataManager
5. WHEN 系统执行查询时 THEN 系统应使用现有的 QueryExecutor
6. WHEN 系统构建查询时 THEN 系统应使用现有的 QueryBuilder
7. WHEN 系统处理数据时 THEN 系统应使用现有的 DataProcessor
8. WHEN 系统映射字段时 THEN 系统应使用现有的 SemanticMapper
9. WHEN 系统解析日期时 THEN 系统应使用现有的 DateParser
10. WHEN 系统检测统计时 THEN 系统应使用现有的 StatisticsDetector
11. WHEN 系统使用所有现有组件时 THEN 系统应保持其业务逻辑不变

### 需求 11: 流式输出支持

**用户故事**: 作为前端开发者，我希望保持现有的流式输出功能，以便用户可以实时看到分析进度。

#### 验收标准

1. WHEN 用户发起查询时 THEN 系统应使用 `astream_events()` 提供流式输出
2. WHEN Agent 生成 token 时 THEN 系统应通过 SSE 实时推送给前端
3. WHEN 节点切换时 THEN 系统应推送节点状态事件
4. WHEN 工具调用时 THEN 系统应推送工具调用事件
5. WHEN 重规划暂停时 THEN 系统应推送暂停事件和建议问题
6. WHEN 用户选择后 THEN 系统应推送恢复事件
7. WHEN 任务执行时 THEN 系统应推送任务进度事件

---

## 非功能需求

### 性能需求

1. 查询响应时间应减少 30%（相比当前系统）
2. Prompt 缓存命中率应 ≥ 60%（使用 Claude 时）
3. 对话总结触发率应 ≥ 80%（长对话场景）
4. 重规划用户选择率应 ≥ 70%

### 兼容性需求

1. 系统应支持 Python 3.9+
2. 系统应支持 DeepAgents 0.1.0+
3. 系统应支持 LangGraph 1.0.4+
4. 系统应支持现有的所有 LLM 提供商（local/openai/azure）

### 可维护性需求

1. 代码行数应减少 20%（相比当前系统）
2. 自定义代码应减少 30%（利用 DeepAgents 内置功能）
3. 测试覆盖率应 ≥ 80%

---

## 约束条件

1. **不使用 SubAgentMiddleware** - 使用 StateGraph 精确控制流程
2. **不引入 Redis** - 使用 SQLite 持久化
3. **不重复造轮子** - 使用现有的模型选择、Store、组件
4. **保持 API 兼容** - 前端不需要修改
5. **保持业务逻辑** - 所有现有组件的业务逻辑不变

---

## 依赖关系

### 新增依赖
- `deepagents>=0.1.0`
- `langchain-anthropic>=1.1.0`（可选，使用 Claude 时）
- `langgraph-store>=1.0.0`

### 现有依赖（保留）
- `langchain>=1.1.0`
- `langgraph>=1.0.4`
- `langchain-openai>=1.1.0`
- `langchain-community>=0.4.1`
- 所有其他现有依赖

---

## 风险和缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| DeepAgents 学习曲线 | 中 | 先完成简单 Agent，逐步熟悉 |
| 重规划 UI 复杂度 | 中 | 设计简洁的用户交互界面 |
| Prompt 缓存效果 | 低 | 只在使用 Claude 时启用 |
| 功能回归 | 高 | 详细测试，保持现有组件不变 |

---

**版本历史**:
- v1.0 (2025-01-10): 初始版本
- v2.0 (2025-01-15): 基于实际分析更新，明确使用 6 个 Middleware，不使用 SubAgent，添加重规划需求

