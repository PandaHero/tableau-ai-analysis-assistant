# Tableau Assistant DeepAgents 重构需求文档

## 简介

本文档定义了将现有 Tableau Assistant 系统重构为基于 LangChain DeepAgents 框架的需求。DeepAgents 提供了开箱即用的长时程任务处理能力，包括规划、文件系统访问和子代理委托，可以显著简化当前架构并提升性能。

## 术语表

- **DeepAgents**: LangChain 官方的长时程任务 Agent 框架，基于 LangGraph 构建
- **Middleware**: 中间件，用于扩展 Agent 功能的可插拔组件
- **SubAgent**: 子代理，用于隔离执行复杂任务的独立 Agent
- **Backend**: 后端，控制文件存储和执行环境的可插拔组件
- **VizQL**: Tableau 的查询语言
- **Tableau Assistant**: 当前的多智能体 Tableau 数据分析系统
- **Runtime**: LangGraph 运行时上下文，包含 Store 和 Context
- **Store**: LangGraph 的持久化存储系统

## 需求

### 需求 1: 架构迁移

**用户故事**: 作为开发者，我希望将现有的多智能体架构迁移到 DeepAgents 框架，以便利用其内置功能并简化代码维护。

#### 验收标准

1. WHEN 系统启动时 THEN 系统应使用 `create_deep_agent()` 创建主 Agent
2. WHEN 创建主 Agent 时 THEN 系统应配置 Tableau 专用的自定义工具
3. WHEN 创建主 Agent 时 THEN 系统应配置自定义中间件以保留现有功能
4. WHEN 系统处理用户查询时 THEN 系统应使用 DeepAgents 的内置规划能力
5. WHEN 系统需要持久化数据时 THEN 系统应使用 DeepAgents 的 Backend 系统

### 需求 2: 子代理系统重构

**用户故事**: 作为系统架构师，我希望将现有的 7 个 Agent 重构为 DeepAgents 的子代理系统，以便实现更好的上下文隔离和并行执行。

#### 验收标准

1. WHEN 定义子代理时 THEN 系统应将问题理解 Agent 定义为独立子代理
2. WHEN 定义子代理时 THEN 系统应将查询规划 Agent 定义为独立子代理
3. WHEN 定义子代理时 THEN 系统应将洞察分析 Agent 定义为独立子代理
4. WHEN 定义子代理时 THEN 系统应将重规划 Agent 定义为独立子代理
5. WHEN 主 Agent 需要执行复杂任务时 THEN 系统应使用 `task()` 工具委托给相应子代理
6. WHEN 子代理执行完成时 THEN 系统应返回结构化结果给主 Agent
7. WHEN 多个子任务独立时 THEN 系统应并行执行多个子代理

### 需求 3: Tableau 工具集成

**用户故事**: 作为开发者，我希望将现有的 Tableau 工具集成到 DeepAgents 框架中，以便 Agent 可以访问 Tableau 数据源。

#### 验收标准

1. WHEN 创建 Agent 时 THEN 系统应注册 VizQL 查询工具
2. WHEN 创建 Agent 时 THEN 系统应注册元数据查询工具
3. WHEN 创建 Agent 时 THEN 系统应注册字段映射工具
4. WHEN 创建 Agent 时 THEN 系统应注册日期解析工具
5. WHEN Agent 调用 Tableau 工具时 THEN 系统应自动处理认证和错误重试
6. WHEN 工具返回大量数据时 THEN 系统应使用 DeepAgents 的文件系统自动保存结果

### 需求 4: 自定义中间件开发

**用户故事**: 作为开发者，我希望创建 Tableau 专用的中间件，以便扩展 DeepAgents 的功能以满足 Tableau 分析的特殊需求。

#### 验收标准

1. WHEN 系统初始化时 THEN 系统应创建 TableauMetadataMiddleware 中间件
2. WHEN TableauMetadataMiddleware 激活时 THEN 系统应自动注入元数据查询工具
3. WHEN TableauMetadataMiddleware 激活时 THEN 系统应在系统提示词中添加元数据使用指南
4. WHEN 系统初始化时 THEN 系统应创建 VizQLQueryMiddleware 中间件
5. WHEN VizQLQueryMiddleware 激活时 THEN 系统应自动注入 VizQL 查询工具
6. WHEN VizQLQueryMiddleware 激活时 THEN 系统应在系统提示词中添加查询语法指南
7. WHEN 系统初始化时 THEN 系统应创建 InsightGenerationMiddleware 中间件
8. WHEN InsightGenerationMiddleware 激活时 THEN 系统应自动处理大型查询结果的洞察生成

### 需求 5: 后端系统配置

**用户故事**: 作为系统管理员，我希望配置合适的后端系统，以便管理文件存储和跨会话持久化。

#### 验收标准

1. WHEN 系统启动时 THEN 系统应使用 CompositeBackend 混合后端
2. WHEN 使用 CompositeBackend 时 THEN 系统应将临时文件路由到 StateBackend
3. WHEN 使用 CompositeBackend 时 THEN 系统应将元数据路由到 StoreBackend 持久化存储
4. WHEN 使用 CompositeBackend 时 THEN 系统应将维度层级路由到 StoreBackend 持久化存储
5. WHEN 使用 CompositeBackend 时 THEN 系统应将用户偏好路由到 StoreBackend 持久化存储
6. WHEN 查询结果过大时 THEN 系统应自动保存到文件系统并返回文件路径

### 需求 6: 流式输出支持

**用户故事**: 作为前端开发者，我希望保持现有的流式输出功能，以便用户可以实时看到分析进度。

#### 验收标准

1. WHEN 用户发起查询时 THEN 系统应使用 `astream_events()` 提供流式输出
2. WHEN Agent 生成 token 时 THEN 系统应通过 SSE 实时推送给前端
3. WHEN 子代理执行时 THEN 系统应推送子代理的进度事件
4. WHEN 工具调用时 THEN 系统应推送工具调用的开始和结束事件
5. WHEN 发生错误时 THEN 系统应推送错误事件并提供详细信息

### 需求 7: 人工审批集成

**用户故事**: 作为系统管理员，我希望对敏感操作添加人工审批，以便控制系统的自主行为。

#### 验收标准

1. WHEN 配置 Agent 时 THEN 系统应支持 `interrupt_on` 配置
2. WHEN Agent 尝试执行敏感查询时 THEN 系统应暂停并等待人工审批
3. WHEN 人工审批通过时 THEN 系统应继续执行查询
4. WHEN 人工审批拒绝时 THEN 系统应取消查询并返回拒绝原因
5. WHEN 人工审批编辑时 THEN 系统应使用修改后的参数执行查询

### 需求 8: 性能优化

**用户故事**: 作为系统架构师，我希望利用 DeepAgents 的优化功能，以便降低成本并提升响应速度。

#### 验收标准

1. WHEN 系统处理长上下文时 THEN 系统应使用 SummarizationMiddleware 自动总结
2. WHEN 使用 Anthropic 模型时 THEN 系统应使用 AnthropicPromptCachingMiddleware 缓存提示词
3. WHEN 工具返回大量数据时 THEN 系统应自动保存到文件系统以节省上下文
4. WHEN 多个子任务独立时 THEN 系统应并行执行以减少总时间
5. WHEN 上下文超过 170k tokens 时 THEN 系统应自动触发总结机制

### 需求 9: 错误处理和重试

**用户故事**: 作为开发者，我希望系统能够优雅地处理错误并自动重试，以便提高系统的可靠性。

#### 验收标准

1. WHEN LLM 调用失败时 THEN 系统应自动重试最多 3 次
2. WHEN VizQL 查询失败时 THEN 系统应分析错误并尝试修复查询
3. WHEN 子代理执行失败时 THEN 系统应记录错误并尝试替代方案
4. WHEN 所有重试失败时 THEN 系统应返回详细的错误信息
5. WHEN 发生错误时 THEN 系统应使用 PatchToolCallsMiddleware 修复悬空工具调用

### 需求 10: 向后兼容性

**用户故事**: 作为产品经理，我希望重构后的系统保持与现有 API 的兼容性，以便不影响现有的前端集成。

#### 验收标准

1. WHEN 前端调用 `/api/chat` 端点时 THEN 系统应返回与现有格式兼容的响应
2. WHEN 前端调用 `/api/chat/stream` 端点时 THEN 系统应返回与现有格式兼容的 SSE 事件
3. WHEN 前端传递模型配置时 THEN 系统应正确应用配置到 DeepAgents
4. WHEN 前端请求问题优化时 THEN 系统应使用相应的子代理处理
5. WHEN 系统返回结果时 THEN 系统应包含所有现有的字段（executive_summary, key_findings 等）

### 需求 11: 测试和验证

**用户故事**: 作为 QA 工程师，我希望有完整的测试覆盖，以便验证重构后的系统功能正确。

#### 验收标准

1. WHEN 运行单元测试时 THEN 所有现有测试应通过
2. WHEN 运行集成测试时 THEN 系统应正确处理完整的查询流程
3. WHEN 测试子代理时 THEN 每个子代理应独立可测试
4. WHEN 测试中间件时 THEN 每个中间件应独立可测试
5. WHEN 测试工具时 THEN 每个 Tableau 工具应独立可测试
6. WHEN 运行性能测试时 THEN 重构后的系统应不慢于现有系统

### 需求 12: 文档和示例

**用户故事**: 作为新加入的开发者，我希望有清晰的文档和示例，以便快速理解新架构。

#### 验收标准

1. WHEN 查看文档时 THEN 系统应提供 DeepAgents 架构概述
2. WHEN 查看文档时 THEN 系统应提供子代理定义示例
3. WHEN 查看文档时 THEN 系统应提供自定义中间件开发指南
4. WHEN 查看文档时 THEN 系统应提供工具集成示例
5. WHEN 查看文档时 THEN 系统应提供完整的 API 使用示例
6. WHEN 查看文档时 THEN 系统应提供迁移指南（从旧架构到新架构）
