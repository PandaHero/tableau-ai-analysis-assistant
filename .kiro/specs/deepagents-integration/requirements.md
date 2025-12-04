# 需求文档：Agent 中间件集成

## 简介

本文档定义了 Tableau Assistant 的 Agent 中间件集成需求，基于 DeepAgents 框架和 LangChain 中间件系统，实现完整的 Agent 能力增强。

### 背景

当前系统存在以下问题：

1. **DeepAgents 未被有效使用**：虽然引入了 DeepAgents 框架，但中间件功能未在实际流程中生效
2. **Agent 架构不统一**：各节点（Understanding、Insight、Replanner）使用 BaseVizQLAgent 直接调用 LLM，未通过 DeepAgent 工具系统
3. **缺少关键能力**：
   - 无任务管理（TodoList）
   - 无对话总结（Summarization）
   - 无大文件处理（Filesystem）
   - 无参数修复（PatchToolCalls）
   - 无 Prompt 缓存（AnthropicPromptCaching）

### 目标

- 正确集成 DeepAgents 中间件系统
- 实现 LangChain 提供的 6 个核心中间件（排除 SubAgentMiddleware）
- 保持现有 StateGraph 工作流架构，所有节点通过工具系统交互
- 支持表计算识别（Understanding 阶段）
- 支持渐进式洞察分析（Insight 阶段）
- 支持语义字段映射（Planning 阶段）

### 技术选型

- **DeepAgents**：`create_deep_agent()` 函数，自动配置中间件
- **StateGraph**：LangGraph 状态图，用于精确的工作流控制（不使用 SubAgentMiddleware）
- **LangChain Middleware**：
  - `TodoListMiddleware` - 任务管理
  - `SummarizationMiddleware` - 对话总结
  - `FilesystemMiddleware` - 文件系统工具
  - `PatchToolCallsMiddleware` - 参数修复
  - `AnthropicPromptCachingMiddleware` - Claude Prompt 缓存
  - `HumanInTheLoopMiddleware` - 人工介入

### 架构决策

**为什么不使用 SubAgentMiddleware？**

1. **StateGraph 提供更精确的控制**：我们的工作流需要精确的节点执行顺序和条件路由
2. **避免动态子代理创建的复杂性**：子代理创建增加了系统复杂性和调试难度
3. **保持现有架构稳定**：现有的 StateGraph 节点流程已经过验证，无需改变

**中间件使用说明**

这些中间件来自 LangChain 和 DeepAgents 框架：
- `langchain.agents.middleware`：TodoListMiddleware、SummarizationMiddleware、HumanInTheLoopMiddleware、PatchToolCallsMiddleware
- `langchain_anthropic.middleware`：AnthropicPromptCachingMiddleware
- `deepagents`：FilesystemMiddleware

**中间件架构设计**：

中间件继承自 `AgentMiddleware` 基类，提供以下钩子函数：
- `before_agent_call` / `after_agent_call`：Agent 调用前后的钩子
- `before_llm_call` / `after_llm_call`：LLM 调用前后的钩子
- `tools`：中间件注入的工具列表
- `system_prompt`：中间件添加的系统提示词

**中间件使用方式**：

1. **通过 `create_deep_agent()` 配置**：DeepAgents 框架会自动配置内置中间件，并通过 `middleware=[]` 参数支持自定义中间件
2. **StateGraph 节点中使用**：在 StateGraph 的各个节点中，可以通过 DeepAgent 获得中间件能力。每个节点（如 Understanding、Planning、Insight 等）作为 StateGraph 的一部分运行，共享同一个 DeepAgent 的中间件配置

**本项目的架构**：
- 使用 `create_deep_agent()` 创建主 Agent，配置所有中间件
- 使用 StateGraph 管理工作流节点（Boost → Understanding → Planning → Execute → Insight → Replanner）
- 各节点通过工具系统与 DeepAgent 交互，自动获得中间件能力（如对话总结、大文件处理、参数修复等）

**HumanInTheLoop 中间件的主要用途**

HumanInTheLoopMiddleware 主要用于重规划阶段，当 Replanner Agent 生成多个后续分析问题时，暂停执行让用户选择要执行哪些问题。

## 术语表

- **AgentMiddleware**: LangChain 中间件基类，用于增强 Agent 能力
- **TodoListMiddleware**: 提供 `write_todos` 工具，用于任务管理和进度跟踪
- **SummarizationMiddleware**: 当对话超过 token 限制时自动总结历史消息
- **FilesystemMiddleware**: 提供 ls、read_file、write_file、edit_file、glob、grep、execute 工具
- **PatchToolCallsMiddleware**: 自动修复工具调用参数错误
- **AnthropicPromptCachingMiddleware**: 为 Claude 模型启用 Prompt 缓存
- **HumanInTheLoopMiddleware**: 在特定工具调用前请求人工确认
- **StateGraph**: LangGraph 的状态图结构，用于精确的工作流控制
- **BackendProtocol**: 文件系统后端协议，支持 StateBackend（内存）和 StoreBackend（持久化）
- **SemanticMapper**: 语义映射组件，使用 RAG 将业务术语映射到技术字段名
- **Progressive Insight**: 渐进式洞察系统，处理大数据集的分块分析

## 需求

### 需求 1：DeepAgent 正确集成

**用户故事:** 作为开发者，我想要正确集成 DeepAgent，以便自动获得所有内置中间件能力。

#### 验收标准

1. WHEN 创建 DeepAgent 时 THEN 系统 SHALL 使用 `create_deep_agent()` 函数并传递正确的参数
2. WHEN 配置 DeepAgent 时 THEN 系统 SHALL 自动获得以下中间件：TodoListMiddleware、FilesystemMiddleware、SummarizationMiddleware、AnthropicPromptCachingMiddleware、PatchToolCallsMiddleware
3. WHEN 创建 DeepAgent 时 THEN 系统 SHALL 排除 SubAgentMiddleware，使用 StateGraph 进行工作流编排
4. WHEN 传递 `backend` 参数时 THEN FilesystemMiddleware SHALL 使用指定的后端存储
5. WHEN 传递 `store` 参数时 THEN 系统 SHALL 支持持久化存储
6. WHEN 传递 `interrupt_on` 参数时 THEN HumanInTheLoopMiddleware SHALL 在指定工具调用前请求确认
7. WHEN 选择语言模型时 THEN 系统 SHALL 调用现有的 `select_model()` 函数
8. WHEN 需要持久化存储时 THEN 系统 SHALL 使用现有的基于 SQLite 的 Store 实现

### 需求 2：StateGraph 工作流保持

**用户故事:** 作为系统架构师，我希望保持现有的 StateGraph 工作流控制，以便已建立的业务流程保持完整和可预测。

#### 验收标准

1. WHEN 系统初始化时 THEN 系统 SHALL 维持现有的 StateGraph 节点定义
2. WHEN 工作流执行时 THEN 系统 SHALL 按以下顺序处理节点：Boost → Understanding → Planning → Execute → Insight → Replanner
3. WHERE 不需要 boost 能力时 WHEN 工作流执行时 THEN 系统 SHALL 跳过 Boost 节点
4. WHEN Replanner 节点确定需要重规划时 THEN 系统 SHALL 将执行路由回 Planning 节点（跳过 Understanding，因为重规划需要从元数据中选择字段，此时真实的技术字段名已经知道）
5. WHEN 每个节点执行时 THEN 系统 SHALL 使用该节点现有的 Agent 实现
6. WHEN 每个节点执行时 THEN 系统 SHALL 应用 ModelConfig 中现有的温度配置

### 需求 3：TodoList 中间件集成

**用户故事:** 作为用户，我想要 Agent 能够管理复杂任务的进度，以便了解分析的执行状态。

#### 验收标准

1. WHEN Agent 处理复杂多步骤任务时 THEN 系统 SHALL 使用 `write_todos` 工具创建任务列表
2. WHEN 任务开始执行时 THEN 系统 SHALL 将任务状态标记为 `in_progress`
3. WHEN 任务完成时 THEN 系统 SHALL 将任务状态标记为 `completed`
4. WHEN 任务列表更新时 THEN 系统 SHALL 在状态中保存 `todos` 数组
5. WHEN 任务简单（少于 3 步）时 THEN 系统 SHALL 跳过 TodoList 直接执行

### 需求 4：Summarization 中间件集成

**用户故事:** 作为开发者，我想要自动总结长对话，以便避免 token 超限。

#### 验收标准

1. WHEN 对话 token 数超过配置阈值时 THEN SummarizationMiddleware SHALL 自动触发总结
2. WHEN 触发总结时 THEN 系统 SHALL 保留最近 N 条消息（可配置）
3. WHEN 总结完成时 THEN 系统 SHALL 用总结内容替换旧消息
4. WHEN 配置 `max_tokens_before_summary` 时 THEN 系统 SHALL 使用指定的 token 阈值
5. WHEN 配置 `messages_to_keep` 时 THEN 系统 SHALL 保留指定数量的最近消息
6. WHEN 总结对话时 THEN 系统 SHALL 仅总结对话交流并排除数据洞察内容（洞察存储在 VizQLState.insights）

### 需求 5：Filesystem 中间件集成

**用户故事:** 作为开发者，我想要 Agent 能够处理大文件和查询结果，以便支持大数据分析。

#### 验收标准

1. WHEN 工具输出超过 token 限制时 THEN FilesystemMiddleware SHALL 将结果写入虚拟文件系统
2. WHEN 结果被写入文件系统时 THEN 系统 SHALL 返回文件路径和前 10 行预览
3. WHEN Agent 需要读取大文件时 THEN 系统 SHALL 支持分页读取（offset + limit）
4. WHEN 配置 `tool_token_limit_before_evict` 时 THEN 系统 SHALL 使用指定的阈值
5. WHEN 使用 StateBackend 时 THEN 文件 SHALL 存储在 Agent 状态中（临时）
6. WHEN 使用 StoreBackend 时 THEN 文件 SHALL 存储在持久化存储中
7. WHEN 用户会话终止时 THEN 系统 SHALL 删除与该会话关联的临时文件

### 需求 6：PatchToolCalls 中间件集成

**用户故事:** 作为开发者，我想要自动修复工具调用参数错误，以便提高系统鲁棒性。

#### 验收标准

1. WHEN 工具调用参数类型错误时 THEN PatchToolCallsMiddleware SHALL 尝试自动修复
2. WHEN 参数缺失时 THEN 系统 SHALL 尝试从上下文推断或应用默认值
3. WHEN 参数名称拼写错误时 THEN 系统 SHALL 自动纠正参数名称
4. WHEN 修复失败时 THEN 系统 SHALL 返回清晰的错误信息
5. WHEN 修复成功时 THEN 系统 SHALL 使用修复后的参数重新调用工具
6. WHEN 工具调用被自动修复时 THEN 系统 SHALL 记录修复详情到日志

### 需求 7：AnthropicPromptCaching 中间件集成

**用户故事:** 作为开发者，我想要为 Claude 模型启用 Prompt 缓存，以便降低成本和延迟。

#### 验收标准

1. WHEN 使用 Claude 模型时 THEN AnthropicPromptCachingMiddleware SHALL 自动启用
2. WHEN 使用非 Claude 模型时 THEN 系统 SHALL 忽略此中间件（不报错）并使用 SQLite Store 进行业务数据缓存
3. WHEN 配置 `unsupported_model_behavior="ignore"` 时 THEN 系统 SHALL 静默忽略不支持的模型
4. WHEN 配置语言模型时 THEN 系统 SHALL 支持在不修改代码的情况下切换不同的 LLM 提供商

### 需求 8：HumanInTheLoop 中间件集成（重规划用户交互）

**用户故事:** 作为用户，我想要在重规划时选择要执行的后续分析问题，以便控制分析方向。

#### 验收标准

1. WHEN Replanner Agent 生成后续分析问题时 THEN 系统 SHALL 触发 HumanInTheLoopMiddleware 暂停执行
2. WHEN 暂停时 THEN 系统 SHALL 向用户展示生成的后续问题列表
3. WHEN 用户选择问题后 THEN 系统 SHALL 将选中的问题添加到执行队列
4. WHEN 用户拒绝继续时 THEN 系统 SHALL 终止重规划循环并返回当前结果
5. WHEN 用户超时未响应时 THEN 系统 SHALL 根据配置自动执行所有建议问题或终止

### 需求 9：Understanding Agent 表计算识别

**用户故事:** 作为用户，我想要系统自动识别表计算需求，以便支持累计、排名、移动平均等高级分析。

#### 模型配置要求

- **模型**: 使用与主 Agent 相同的模型（通过 model_config 配置）
- **温度**: 0.1（低温度确保一致性）
- **输出格式**: 结构化输出，使用 Pydantic 模型验证
- **Prompt 设计**: 基于关键词识别 + 上下文推断的混合方法

#### 验收标准

1. WHEN 用户问题包含"累计"、"running total"、"累积"关键词时 THEN Understanding Agent SHALL 识别为 RUNNING_TOTAL
2. WHEN 用户问题包含"排名"、"rank"、"排序"关键词时 THEN Understanding Agent SHALL 识别为 RANK
3. WHEN 用户问题包含"移动平均"、"moving average"、"滑动平均"关键词时 THEN Understanding Agent SHALL 识别为 MOVING_CALCULATION
4. WHEN 用户问题包含"占比"、"percent of total"、"百分比"关键词时 THEN Understanding Agent SHALL 识别为 PERCENT_OF_TOTAL
5. WHEN 识别到表计算需求时 THEN 系统 SHALL 在 QuestionUnderstanding 中设置 `table_calc_type` 字段
6. WHEN 识别到表计算需求时 THEN 系统 SHALL 推断 `table_calc_dimensions` 字段
7. WHEN Understanding Agent 输出结果时 THEN 系统 SHALL 使用结构化输出格式验证

### 需求 10：Boost Agent 元数据使用

**用户故事:** 作为用户，我想要问题优化时参考数据源元数据，以便获得更精确的问题增强。

#### 验收标准

1. WHEN Boost Agent 执行时 THEN 系统 SHALL 默认使用元数据（`use_metadata=True`）
2. WHEN 元数据包含维度层级时 THEN Boost Agent SHALL 参考层级关系优化问题
3. WHEN 元数据包含 sample values 时 THEN Boost Agent SHALL 参考样本值补充缺失信息
4. WHEN 元数据不可用时 THEN Boost Agent SHALL 降级为不使用元数据模式

### 需求 11：Insight Agent 渐进式分析

**用户故事:** 作为用户，我想要系统能够渐进式分析大数据，以便获得高质量洞察。

#### 验收标准

1. WHEN 查询结果超过 100 行时 THEN Insight Agent SHALL 使用渐进式分析
2. WHEN 渐进式分析时 THEN 系统 SHALL 按优先级分块：URGENT(异常) → HIGH(top) → MEDIUM(mid) → LOW(low) → DEFERRED(tail)
3. WHEN 分析每个数据块时 THEN 系统 SHALL 累积洞察并决定下一步
4. WHEN 洞察质量足够时 THEN 系统 SHALL 支持早停机制
5. WHEN 发现异常时 THEN 系统 SHALL 优先分析异常数据块
6. WHEN 分析完成时 THEN 系统 SHALL 合成最终洞察

### 需求 12：Replanner Agent 智能重规划

**用户故事:** 作为用户，我想要系统能够智能重规划，以便在分析不完整时自动补充查询。

#### 重规划类型

| 类型 | 触发条件 | 生成的新问题 |
|------|---------|-------------|
| 补充缺失信息 | 原问题部分未回答 | 针对缺失部分的补充问题 |
| 深入分析异常 | 发现数据异常 | 针对异常的深入分析问题 |
| 洞察不足 | 分析过于表面 | 更深入的分析问题 |

#### 智能终止策略

- completeness_score >= 0.9 → 直接结束（已足够好）
- replan_count >= max_rounds → 强制结束（硬限制）
- completeness_score < 0.7 → 继续重规划（明显不足）
- 0.7 <= score < 0.9 → 由 Replanner 决定

#### 验收标准

1. WHEN should_replan=True 且 replan_count < max_rounds 时 THEN 系统 SHALL 从 Replanner 路由回 Planning 节点（跳过 Understanding）
2. WHEN 重规划时 THEN 系统 SHALL 跳过 Understanding 节点，因为重规划需要从元数据中选择字段，此时真实的技术字段名已经知道
3. WHEN completeness_score >= 0.9 时 THEN 系统 SHALL 直接结束重规划循环
4. WHEN replan_count >= max_rounds 时 THEN 系统 SHALL 强制结束并记录终止原因
5. WHEN completeness_score < 0.7 且 should_replan=True 时 THEN 系统 SHALL 继续重规划
6. WHEN 重规划循环终止时 THEN 系统 SHALL 记录终止原因和当前完成度到 replan_history
7. WHEN 生成重规划问题时 THEN Replanner SHALL 基于已有洞察生成补充问题，而不是重复原问题

### 需求 13：工具层统一封装

**用户故事:** 作为开发者，我想要将所有业务组件封装为 LangChain 工具，以便在 DeepAgent 中统一管理。

**已完成：**
- ✅ get_metadata 工具 (`capabilities/metadata/tool.py`)
- ✅ semantic_map_fields 工具 (`capabilities/semantic_mapping/tool.py`)
- ✅ parse_date 工具 (`capabilities/date_processing/tool.py`)

#### 验收标准

1. ✅ WHEN 封装工具时 THEN 系统 SHALL 使用 `@tool` 装饰器或 `StructuredTool.from_function()`
2. ✅ WHEN 定义工具时 THEN 系统 SHALL 提供完整的 docstring 和参数说明
3. WHEN 工具返回结果时 THEN 系统 SHALL 使用 Pydantic 模型验证输出
4. WHEN 创建 DeepAgent 时 THEN 系统 SHALL 传递所有业务工具列表（需要创建工具注册表）
5. WHEN 封装 QueryBuilder 时 THEN 系统 SHALL 创建 `build_vizql_query` 工具
6. WHEN 封装 QueryExecutor 时 THEN 系统 SHALL 创建 `execute_vizql_query` 工具
7. WHEN 封装 DataProcessor 时 THEN 系统 SHALL 创建 `process_query_result` 工具
8. WHEN 封装 StatisticsDetector 时 THEN 系统 SHALL 创建 `detect_statistics` 工具
9. WHEN 封装大文件保存时 THEN 系统 SHALL 利用 FilesystemMiddleware 提供 `save_large_result` 工具
10. WHEN 封装工具时 THEN 系统 SHALL 保持每个组件现有的业务逻辑

### 需求 14：语义字段映射与任务规划集成

**用户故事:** 作为用户，我希望系统能够智能地将我使用的业务术语映射到实际的数据字段，以便我可以使用自然语言而不需要知道精确的字段名称。

#### 验收标准

1. WHEN Understanding 阶段提取业务术语时 THEN 系统 SHALL 将 mentioned_dimensions、mentioned_measures 和 mentioned_date_fields 传递给 Planning 阶段
2. WHEN Planning 阶段接收到业务术语时 THEN 系统 SHALL 为每个业务术语调用 semantic_map_fields 工具进行字段映射
3. WHEN semantic_map_fields 工具执行时 THEN 系统 SHALL 使用 FAISS 向量检索获取 Top-5 候选字段
4. WHEN 候选字段数量大于 1 且相似度差异小于 0.2 时 THEN 系统 SHALL 使用 LLM 进行语义判断选择最佳匹配
5. WHEN 字段映射完成时 THEN 系统 SHALL 使用映射后的技术字段名（而非业务术语）生成 VizQL 查询规格
6. WHEN 字段映射置信度低于 0.7 时 THEN 系统 SHALL 在响应中包含映射不确定性警告
7. WHEN 字段映射失败（无匹配字段）时 THEN 系统 SHALL 返回清晰的错误消息并建议可能的字段名
8. WHEN 相同业务术语在同一会话中再次出现时 THEN 系统 SHALL 使用 Store 缓存的映射结果（TTL: 1小时）
9. WHEN 数据源元数据更新时 THEN 系统 SHALL 重建该数据源的字段向量索引

### 需求 15：性能优化

**用户故事:** 作为系统管理员，我希望 DeepAgents 集成能够提高系统性能，以便用户体验更快的响应时间和更低的运营成本。

#### 验收标准

1. WHEN 比较集成前后的性能时 THEN 系统 SHALL 将平均查询响应时间减少至少 30%
2. WHERE 使用 Claude 模型时 WHEN 测量缓存性能时 THEN 系统 SHALL 实现至少 60% 的 Prompt 缓存命中率
3. WHEN 分析长对话（超过 10 轮）时 THEN 系统 SHALL 在至少 80% 的符合条件的对话中触发总结

### 需求 16：系统兼容性

**用户故事:** 作为系统集成商，我希望 DeepAgents 集成能够保持与现有基础设施的兼容性，以便部署只需要对环境进行最小的更改。

#### 验收标准

1. WHEN 部署系统时 THEN 系统 SHALL 在 Python 3.9 或更高版本上运行
2. WHEN 配置语言模型时 THEN 系统 SHALL 支持所有当前支持的 LLM 提供商，包括 Claude、DeepSeek、Qwen 和 OpenAI 兼容端点
3. WHEN 前端应用程序发出 API 请求时 THEN 系统 SHALL 保持与现有 API 契约的向后兼容性

### 需求 17：代码可维护性

**用户故事:** 作为开发者，我希望 DeepAgents 集成能够降低代码复杂性，以便系统更易于维护和扩展。

#### 验收标准

1. WHEN 比较集成前后的代码库时 THEN 系统 SHALL 将总代码行数减少至少 20%
2. WHEN 比较集成前后的代码库时 THEN 系统 SHALL 将自定义中间件代码减少至少 30%
3. WHEN 测量测试覆盖率时 THEN 系统 SHALL 保持至少 80% 的测试覆盖率

## 约束条件

1. **排除 SubAgentMiddleware**: 系统不应使用 SubAgentMiddleware；工作流控制应使用 StateGraph 实现
2. **存储技术**: 系统不应引入 Redis；所有缓存和存储应使用 SQLite
3. **代码复用**: 系统应利用现有功能而不是重新实现等效特性
4. **API 稳定性**: 系统应保持 API 兼容性；前端应用程序不应需要修改
5. **业务逻辑保持**: 系统应保持现有组件业务逻辑不变
6. **渐进式洞察与对话总结职责分离**: 渐进式洞察系统处理查询结果数据（存储在 VizQLState.insights），SummarizationMiddleware 处理对话历史（Messages）；两者独立运行，互不干扰
