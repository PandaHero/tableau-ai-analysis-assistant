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
- 实现 LangChain 提供的 7 个核心中间件
- 统一 Agent 架构，所有节点通过工具系统交互
- 支持表计算识别（Understanding 阶段）
- 支持渐进式洞察分析（Insight 阶段）

### 技术选型

- **DeepAgents**：`create_deep_agent()` 函数，自动配置中间件
- **LangChain Middleware**：
  - `TodoListMiddleware` - 任务管理
  - `SummarizationMiddleware` - 对话总结
  - `FilesystemMiddleware` - 文件系统工具
  - `PatchToolCallsMiddleware` - 参数修复
  - `AnthropicPromptCachingMiddleware` - Claude Prompt 缓存
  - `HumanInTheLoopMiddleware` - 人工介入
  - `SubAgentMiddleware` - 子代理

## 术语表

- **AgentMiddleware**: LangChain 中间件基类，用于增强 Agent 能力
- **TodoListMiddleware**: 提供 `write_todos` 工具，用于任务管理和进度跟踪
- **SummarizationMiddleware**: 当对话超过 token 限制时自动总结历史消息
- **FilesystemMiddleware**: 提供 ls、read_file、write_file、edit_file、glob、grep、execute 工具
- **PatchToolCallsMiddleware**: 自动修复工具调用参数错误
- **AnthropicPromptCachingMiddleware**: 为 Claude 模型启用 Prompt 缓存
- **HumanInTheLoopMiddleware**: 在特定工具调用前请求人工确认
- **SubAgentMiddleware**: 提供 `task` 工具，用于启动子代理处理复杂任务
- **BackendProtocol**: 文件系统后端协议，支持 StateBackend（内存）和 StoreBackend（持久化）

## 需求

### 需求 1：DeepAgent 正确集成

**用户故事:** 作为开发者，我想要正确集成 DeepAgent，以便自动获得所有内置中间件能力。

#### 验收标准

1. WHEN 创建 DeepAgent 时 THEN 系统 SHALL 使用 `create_deep_agent()` 函数并传递正确的参数
2. WHEN 配置 DeepAgent 时 THEN 系统 SHALL 自动获得以下中间件：TodoListMiddleware、FilesystemMiddleware、SubAgentMiddleware、SummarizationMiddleware、AnthropicPromptCachingMiddleware、PatchToolCallsMiddleware
3. WHEN 传递 `subagents=[]` 时 THEN SubAgentMiddleware SHALL 仍然启用但不提供自定义子代理
4. WHEN 传递 `backend` 参数时 THEN FilesystemMiddleware SHALL 使用指定的后端存储
5. WHEN 传递 `store` 参数时 THEN 系统 SHALL 支持持久化存储
6. WHEN 传递 `interrupt_on` 参数时 THEN HumanInTheLoopMiddleware SHALL 在指定工具调用前请求确认

### 需求 2：TodoList 中间件集成

**用户故事:** 作为用户，我想要 Agent 能够管理复杂任务的进度，以便了解分析的执行状态。

#### 验收标准

1. WHEN Agent 处理复杂多步骤任务时 THEN 系统 SHALL 使用 `write_todos` 工具创建任务列表
2. WHEN 任务开始执行时 THEN 系统 SHALL 将任务状态标记为 `in_progress`
3. WHEN 任务完成时 THEN 系统 SHALL 将任务状态标记为 `completed`
4. WHEN 任务列表更新时 THEN 系统 SHALL 在状态中保存 `todos` 数组
5. WHEN 任务简单（少于 3 步）时 THEN 系统 SHALL 跳过 TodoList 直接执行

### 需求 3：Summarization 中间件集成

**用户故事:** 作为开发者，我想要自动总结长对话，以便避免 token 超限。

#### 验收标准

1. WHEN 对话 token 数超过配置阈值时 THEN SummarizationMiddleware SHALL 自动触发总结
2. WHEN 触发总结时 THEN 系统 SHALL 保留最近 N 条消息（可配置）
3. WHEN 总结完成时 THEN 系统 SHALL 用总结内容替换旧消息
4. WHEN 配置 `max_tokens_before_summary` 时 THEN 系统 SHALL 使用指定的 token 阈值
5. WHEN 配置 `messages_to_keep` 时 THEN 系统 SHALL 保留指定数量的最近消息

### 需求 4：Filesystem 中间件集成

**用户故事:** 作为开发者，我想要 Agent 能够处理大文件和查询结果，以便支持大数据分析。

#### 验收标准

1. WHEN 工具输出超过 token 限制时 THEN FilesystemMiddleware SHALL 将结果写入虚拟文件系统
2. WHEN 结果被写入文件系统时 THEN 系统 SHALL 返回文件路径和前 10 行预览
3. WHEN Agent 需要读取大文件时 THEN 系统 SHALL 支持分页读取（offset + limit）
4. WHEN 配置 `tool_token_limit_before_evict` 时 THEN 系统 SHALL 使用指定的阈值
5. WHEN 使用 StateBackend 时 THEN 文件 SHALL 存储在 Agent 状态中（临时）
6. WHEN 使用 StoreBackend 时 THEN 文件 SHALL 存储在持久化存储中

### 需求 5：PatchToolCalls 中间件集成

**用户故事:** 作为开发者，我想要自动修复工具调用参数错误，以便提高系统鲁棒性。

#### 验收标准

1. WHEN 工具调用参数类型错误时 THEN PatchToolCallsMiddleware SHALL 尝试自动修复
2. WHEN 参数缺失时 THEN 系统 SHALL 尝试从上下文推断
3. WHEN 修复失败时 THEN 系统 SHALL 返回清晰的错误信息
4. WHEN 修复成功时 THEN 系统 SHALL 使用修复后的参数重新调用工具

### 需求 6：AnthropicPromptCaching 中间件集成

**用户故事:** 作为开发者，我想要为 Claude 模型启用 Prompt 缓存，以便降低成本和延迟。

#### 验收标准

1. WHEN 使用 Claude 模型时 THEN AnthropicPromptCachingMiddleware SHALL 自动启用
2. WHEN 使用非 Claude 模型时 THEN 系统 SHALL 忽略此中间件（不报错）
3. WHEN 配置 `unsupported_model_behavior="ignore"` 时 THEN 系统 SHALL 静默忽略不支持的模型

### 需求 7：HumanInTheLoop 中间件集成

**用户故事:** 作为用户，我想要在关键操作前确认，以便控制 Agent 行为。

#### 验收标准

1. WHEN 配置 `interrupt_on` 参数时 THEN 系统 SHALL 在指定工具调用前暂停
2. WHEN 暂停时 THEN 系统 SHALL 返回中断状态等待用户确认
3. WHEN 用户确认后 THEN 系统 SHALL 继续执行工具调用
4. WHEN 用户拒绝时 THEN 系统 SHALL 跳过该工具调用

### 需求 8：SubAgent 中间件集成

**用户故事:** 作为开发者，我想要支持子代理处理复杂任务，以便实现任务分解和并行处理。

#### 验收标准

1. WHEN 配置 `subagents` 列表时 THEN SubAgentMiddleware SHALL 提供 `task` 工具
2. WHEN 调用 `task` 工具时 THEN 系统 SHALL 启动指定类型的子代理
3. WHEN 子代理完成时 THEN 系统 SHALL 返回子代理的最终结果
4. WHEN 配置 `general_purpose_agent=True` 时 THEN 系统 SHALL 提供通用子代理
5. WHEN 多个子代理任务独立时 THEN 系统 SHALL 支持并行执行

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
2. WHEN 重规划时 THEN 系统 SHALL 跳过 Understanding 节点，因为元数据和字段映射已完成
3. WHEN completeness_score >= 0.9 时 THEN 系统 SHALL 直接结束重规划循环
4. WHEN replan_count >= max_rounds 时 THEN 系统 SHALL 强制结束并记录终止原因
5. WHEN completeness_score < 0.7 且 should_replan=True 时 THEN 系统 SHALL 继续重规划
6. WHEN 重规划循环终止时 THEN 系统 SHALL 记录终止原因和当前完成度到 replan_history
7. WHEN 生成重规划问题时 THEN Replanner SHALL 基于已有洞察生成补充问题，而不是重复原问题

### 需求 13：工具层统一封装（部分已完成）

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

