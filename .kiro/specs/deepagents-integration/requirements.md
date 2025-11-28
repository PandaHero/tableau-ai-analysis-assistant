# 需求文档

## 简介

本文档定义了将 DeepAgents 框架集成到现有 Tableau Assistant 系统的需求。目标是利用 DeepAgents 的 6 个内置中间件组件（Prompt 缓存、对话总结、文件系统、工具调用修复、任务管理和人工介入），同时保持现有架构和组件逻辑不变。

## 术语表

- **DeepAgents**: LangChain 官方的 Agent 框架，提供 7 个内置中间件组件
- **Middleware（中间件）**: 可插拔的功能扩展组件，用于增强 Agent 能力
- **StateGraph（状态图）**: LangGraph 的状态图结构，用于精确的工作流控制
- **TodoListMiddleware（任务列表中间件）**: 用于处理多个顺序任务的任务列表管理中间件
- **HumanInTheLoopMiddleware（人工介入中间件）**: 用于用户交互和审批的人工介入中间件（HITL）
- **Store（存储）**: LangGraph 基于 SQLite 的持久化存储机制
- **Runtime（运行时）**: LangGraph 运行时执行上下文
- **Agent（智能体）**: 使用 LLM 和工具处理用户请求的自主组件
- **Tool（工具）**: Agent 可以调用以执行特定操作的可调用函数
- **VizQL**: Tableau 的数据可视化查询语言
- **Replanner（重规划器）**: 负责生成后续分析问题的 Agent
- **Tableau Assistant（Tableau 助手）**: 本系统的名称，用于 EARS 模式中的系统主语

## 需求

### 需求 1: DeepAgents 框架集成

**用户故事**: 作为开发者，我希望集成 DeepAgents 框架，以便利用其内置中间件功能并减少自定义代码维护。

#### 验收标准

1. WHEN Tableau 助手初始化时 THEN Tableau 助手应使用 `create_deep_agent()` 函数创建主 Agent
2. WHEN 主 Agent 被创建时 THEN Tableau 助手应为该 Agent 配置 8 个自定义 Tableau 工具
3. WHERE 选定的模型是 Claude WHEN 主 Agent 被创建时 THEN Tableau 助手应启用 AnthropicPromptCachingMiddleware
4. WHEN 主 Agent 被创建时 THEN Tableau 助手应启用 SummarizationMiddleware
5. WHEN 主 Agent 被创建时 THEN Tableau 助手应启用 FilesystemMiddleware
6. WHEN 主 Agent 被创建时 THEN Tableau 助手应启用 PatchToolCallsMiddleware
7. WHEN 主 Agent 被创建时 THEN Tableau 助手应启用 TodoListMiddleware
8. WHEN 主 Agent 被创建时 THEN Tableau 助手应启用 HumanInTheLoopMiddleware
9. WHEN 主 Agent 被创建时 THEN Tableau 助手应从中间件配置中排除 SubAgentMiddleware
10. WHEN Tableau 助手选择语言模型时 THEN Tableau 助手应调用现有的 `select_model()` 函数
11. WHEN Tableau 助手需要持久化存储时 THEN Tableau 助手应使用现有的基于 SQLite 的 Store 实现

### 需求 2: StateGraph 工作流保持

**用户故事**: 作为系统架构师，我希望保持现有的 StateGraph 工作流控制，以便已建立的业务流程保持完整和可预测。

#### 验收标准

1. WHEN Tableau 助手初始化时 THEN Tableau 助手应维持现有的 StateGraph 节点定义
2. WHEN 工作流执行时 THEN Tableau 助手应按以下顺序处理节点：Boost → Understanding → Planning → Execute → Insight → Replanner
3. WHERE 不需要 boost 能力时 WHEN 工作流执行时 THEN Tableau 助手应跳过 Boost 节点
4. WHEN Replanner 节点确定需要重规划时 THEN Tableau 助手应将执行路由回 Understanding 节点
5. WHEN 每个节点执行时 THEN Tableau 助手应使用该节点现有的 Agent 实现
6. WHEN 每个节点执行时 THEN Tableau 助手应应用 ModelConfig 中现有的温度配置

### 需求 3: 组件工具封装

**用户故事**: 作为开发者，我希望将现有组件封装为 LangChain 工具，以便 DeepAgents 可以通过标准工具接口调用它们。

#### 验收标准

1. WHEN 将组件封装为工具时 THEN Tableau 助手应将 MetadataManager 封装为 `get_metadata` 工具
2. WHEN 将组件封装为工具时 THEN Tableau 助手应将 DateParser 封装为 `parse_date` 工具
3. WHEN 将组件封装为工具时 THEN Tableau 助手应将 QueryBuilder 封装为 `build_vizql_query` 工具
4. WHEN 将组件封装为工具时 THEN Tableau 助手应将 QueryExecutor 封装为 `execute_vizql_query` 工具
5. WHEN 将组件封装为工具时 THEN Tableau 助手应将 SemanticMapper 封装为 `semantic_map_fields` 工具
6. WHEN 将组件封装为工具时 THEN Tableau 助手应将 DataProcessor 封装为 `process_query_result` 工具
7. WHEN 将组件封装为工具时 THEN Tableau 助手应将 StatisticsDetector 封装为 `detect_statistics` 工具
8. WHEN 将组件封装为工具时 THEN Tableau 助手应利用 FilesystemMiddleware 提供 `save_large_result` 工具
9. WHEN 将组件封装为工具时 THEN Tableau 助手应保持每个组件现有的业务逻辑
10. WHEN 定义工具封装器时 THEN Tableau 助手应使用 `@tool` 装饰器
11. WHEN 定义工具封装器时 THEN Tableau 助手应提供描述工具目的、参数和返回值的完整文档字符串

### 需求 4: Prompt 缓存支持

**用户故事**: 作为系统管理员，我希望在使用 Claude 模型时利用 Prompt 缓存，以便显著降低 API 成本。

#### 验收标准

1. WHERE 选定的模型是 Claude WHEN Tableau 助手初始化时 THEN Tableau 助手应自动启用 AnthropicPromptCachingMiddleware
2. WHERE 选定的模型不是 Claude WHEN Tableau 助手需要缓存时 THEN Tableau 助手应使用 Store 进行业务数据缓存
3. WHEN Claude 的 Prompt 缓存命中时 THEN Tableau 助手应将 API 成本降低至少 90%
4. WHEN 配置语言模型时 THEN Tableau 助手应支持在不修改代码的情况下切换不同的 LLM 提供商
5. WHEN 配置缓存存储时 THEN Tableau 助手应使用 SQLite 作为存储后端

### 需求 5: 对话总结

**用户故事**: 作为用户，我希望系统在长会话期间自动总结对话历史，以便在不超过 token 限制的情况下保持对话上下文的连贯性。

#### 验收标准

1. WHEN 对话达到 10 轮消息时 THEN Tableau 助手应触发 SummarizationMiddleware
2. WHEN 触发总结时 THEN Tableau 助手应生成对话历史的自然语言摘要
3. WHEN 生成摘要时 THEN Tableau 助手应压缩历史消息同时保留摘要
4. WHEN 总结对话时 THEN Tableau 助手应保留 Insight Agent 生成的数据洞察
5. WHEN 总结对话时 THEN Tableau 助手应仅总结对话交流并排除数据洞察内容

### 需求 6: 重规划任务管理

**用户故事**: 作为用户，我希望系统在需要更深入分析时生成多个后续问题并让我选择要追求的问题，以便我可以控制分析方向，同时系统自动管理任务执行。

#### 验收标准

1. WHEN Replanner Agent 确定需要重规划时 THEN Tableau 助手应生成 2 到 5 个建议的后续问题
2. WHEN 生成建议问题时 THEN Tableau 助手应触发 HumanInTheLoopMiddleware 以暂停执行
3. WHEN 执行暂停时 THEN Tableau 助手应通过 API 向用户展示建议的问题
4. WHEN 展示问题时 THEN Tableau 助手应提供选项：执行所有问题、选择特定问题、修改问题或拒绝继续
5. WHEN 用户做出选择时 THEN Tableau 助手应将选定的问题作为任务添加到 TodoListMiddleware
6. WHEN 任务被添加到待办列表时 THEN Tableau 助手应自动管理任务队列执行顺序
7. WHEN 执行任务时 THEN Tableau 助手应通过完整的工作流序列处理每个问题
8. WHEN 所有任务完成时 THEN Tableau 助手应将所有生成的洞察聚合到统一的响应中
9. WHEN 用户拒绝继续时 THEN Tableau 助手应终止分析工作流
10. WHEN 重规划用户交互超过 5 分钟没有响应时 THEN Tableau 助手应自动执行所有建议的问题

### 需求 7: 大结果集文件系统支持

**用户故事**: 作为开发者，我希望系统通过将大结果集保存到文件系统来自动处理它们，以便内存限制不会限制查询结果大小。

#### 验收标准

1. WHEN 查询结果超过 10 兆字节时 THEN Tableau 助手应使用 FilesystemMiddleware 将结果保存到磁盘
2. WHEN 将结果保存到磁盘时 THEN Tableau 助手应为结果生成唯一的文件标识符
3. WHEN 结果保存到磁盘时 THEN Tableau 助手应将文件路径返回给请求组件
4. WHEN Agent 需要访问大结果时 THEN Tableau 助手应使用文件标识符从文件系统加载结果
5. WHEN 用户会话终止时 THEN Tableau 助手应删除与该会话关联的临时文件
6. WHEN 配置文件系统存储时 THEN Tableau 助手应使用 `data/agent_files` 作为基础目录路径

### 需求 8: 工具调用错误恢复

**用户故事**: 作为开发者，我希望系统自动修复工具调用错误，以便在无需手动干预的情况下提高 Agent 操作的成功率。

#### 验收标准

1. WHEN Agent 使用不正确的参数类型调用工具时 THEN Tableau 助手应自动将参数转换为正确的类型
2. WHEN Agent 调用工具时缺少必需参数时 THEN Tableau 助手应为缺少的参数应用默认值
3. WHEN Agent 使用拼写错误的参数名称调用工具时 THEN Tableau 助手应自动更正参数名称
4. WHEN 工具调用被自动修复时 THEN Tableau 助手应记录更正详情以便调试
5. WHEN 工具调用无法自动修复时 THEN Tableau 助手应返回描述问题的清晰错误消息

### 需求 9: 性能优化

**用户故事**: 作为系统管理员，我希望 DeepAgents 集成能够提高系统性能，以便用户体验更快的响应时间和更低的运营成本。

#### 验收标准

1. WHEN 比较集成前后的性能时 THEN Tableau 助手应将平均查询响应时间减少至少 30%
2. WHERE 使用 Claude 模型时 WHEN 测量缓存性能时 THEN Tableau 助手应实现至少 60% 的 Prompt 缓存命中率
3. WHEN 分析长对话（超过 10 轮）时 THEN Tableau 助手应在至少 80% 的符合条件的对话中触发总结
4. WHEN Replanner 生成后续问题时 THEN 用户应在至少 70% 的重规划交互中选择至少一个问题

### 需求 10: 系统兼容性

**用户故事**: 作为系统集成商，我希望 DeepAgents 集成能够保持与现有基础设施的兼容性，以便部署只需要对环境进行最小的更改。

#### 验收标准

1. WHEN 部署 Tableau 助手时 THEN Tableau 助手应在 Python 3.9 或更高版本上运行
2. WHEN 配置语言模型时 THEN Tableau 助手应支持所有当前支持的 LLM 提供商，包括 Claude、DeepSeek、Qwen 和 OpenAI 兼容端点
3. WHEN 前端应用程序发出 API 请求时 THEN Tableau 助手应保持与现有 API 契约的向后兼容性

### 需求 11: 代码可维护性

**用户故事**: 作为开发者，我希望 DeepAgents 集成能够降低代码复杂性，以便系统更易于维护和扩展。

#### 验收标准

1. WHEN 比较集成前后的代码库时 THEN Tableau 助手应将总代码行数减少至少 20%
2. WHEN 比较集成前后的代码库时 THEN Tableau 助手应将自定义中间件代码减少至少 30%
3. WHEN 测量测试覆盖率时 THEN Tableau 助手应保持至少 80% 的测试覆盖率

## 约束条件

1. **排除 SubAgentMiddleware**: Tableau 助手不应使用 SubAgentMiddleware；工作流控制应使用 StateGraph 实现
2. **存储技术**: Tableau 助手不应引入 Redis；所有缓存和存储应使用 SQLite
3. **代码复用**: Tableau 助手应利用现有功能而不是重新实现等效特性
4. **API 稳定性**: Tableau 助手应保持 API 兼容性；前端应用程序不应需要修改
5. **业务逻辑保持**: Tableau 助手应保持现有组件业务逻辑不变
