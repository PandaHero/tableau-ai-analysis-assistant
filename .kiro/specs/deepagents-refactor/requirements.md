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

**用户故事**: 作为系统架构师，我希望将现有的 Agent 重构为 DeepAgents 的子代理系统，以便实现更好的上下文隔离和并行执行。

#### 验收标准

1. WHEN 定义子代理时 THEN 系统应将问题优化 Agent（boost-agent）定义为独立子代理
2. WHEN 定义子代理时 THEN 系统应将问题理解 Agent（understanding-agent）定义为独立子代理
3. WHEN 定义子代理时 THEN 系统应将查询规划 Agent（planning-agent）定义为独立子代理
4. WHEN 定义子代理时 THEN 系统应将洞察分析 Agent（insight-agent）定义为独立子代理
5. WHEN 定义子代理时 THEN 系统应将重规划 Agent（replanner-agent）定义为独立子代理
6. WHEN 主 Agent 需要执行复杂任务时 THEN 系统应使用 `task()` 工具委托给相应子代理
7. WHEN 子代理执行完成时 THEN 系统应返回结构化结果给主 Agent
8. WHEN 多个子任务独立时 THEN 系统应支持并行执行（通过 asyncio.gather）
9. WHEN Planning Agent 生成多个独立子查询时 THEN 系统应并行执行所有子查询
10. WHEN 查询执行时 THEN 系统应支持流水线并行（查询完成后立即开始分析，不等待其他查询）
11. WHEN 系统分析依赖关系时 THEN 系统应自动构建依赖图并按阶段并行执行
12. WHEN 配置子代理时 THEN 系统应支持为不同子代理配置不同的 LLM 模型
13. WHEN 配置 boost-agent 时 THEN 系统应支持使用轻量级模型（如 gpt-4o-mini）
14. WHEN 配置 planning-agent 时 THEN 系统应支持使用强大模型（如 claude-sonnet-4）

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

### 需求 10: API 设计

**用户故事**: 作为前端开发者，我希望有清晰的 API 接口，以便与后端系统集成。

#### 验收标准

1. WHEN 前端调用 `/api/chat` 端点时 THEN 系统应返回完整的分析结果
2. WHEN 前端调用 `/api/chat/stream` 端点时 THEN 系统应返回 SSE 流式事件
3. WHEN 前端传递 `boost_question=true` 参数时 THEN 系统应调用 Boost Agent 优化问题
4. WHEN 前端传递 `boost_question=false` 参数时 THEN 系统应跳过问题优化
5. WHEN 前端传递模型配置时 THEN 系统应正确应用配置到 DeepAgents
6. WHEN 系统返回结果时 THEN 系统应包含 executive_summary（执行摘要）
7. WHEN 系统返回结果时 THEN 系统应包含 key_findings（关键发现）
8. WHEN 系统返回结果时 THEN 系统应包含 insights（洞察列表）
9. WHEN 系统返回结果时 THEN 系统应包含 recommendations（建议）
10. WHEN 系统返回结果时 THEN 系统应包含 performance_metrics（性能指标）

### 需求 11: 测试和验证

**用户故事**: 作为 QA 工程师，我希望有完整的测试覆盖，以便验证重构后的系统功能正确。

#### 验收标准

1. WHEN 运行单元测试时 THEN 所有现有测试应通过
2. WHEN 运行集成测试时 THEN 系统应正确处理完整的查询流程
3. WHEN 测试子代理时 THEN 每个子代理应独立可测试
4. WHEN 测试中间件时 THEN 每个中间件应独立可测试
5. WHEN 测试工具时 THEN 每个 Tableau 工具应独立可测试
6. WHEN 运行性能测试时 THEN 重构后的系统应不慢于现有系统

### 需求 12: 渐进式洞察分析

**用户故事**: 作为数据分析师，我希望系统能够智能地分析大量查询结果，以便在不超过 Token 限制的情况下提取有价值的洞察。

#### 验收标准

1. WHEN 查询返回大量数据（> 100 行）时 THEN 系统应使用渐进式分析策略
2. WHEN 使用渐进式分析时 THEN 系统应按优先级分块（异常值 → Top → 中间 → 尾部）
3. WHEN 分析每个数据块时 THEN 系统应提取洞察并累积到已有洞察中
4. WHEN 累积洞察时 THEN 系统应由 AI 决定如何合并和累积洞察
5. WHEN 分析过程中时 THEN 系统应流式输出每个新发现的洞察
6. WHEN AI 判断已获得足够洞察时 THEN 系统应早停并跳过剩余数据分析
7. WHEN 查询返回少量数据（< 100 行）时 THEN 系统应直接分析而不分块
8. WHEN 查询结果保存到文件时 THEN 系统应使用 FilesystemMiddleware 的 read_file 工具读取数据块
9. WHEN 分析数据块时 THEN 系统应由 AI 决定下一口吃什么（下一块数据的位置和大小）

### 需求 13: 智能重规划机制

**用户故事**: 作为数据分析师，我希望系统能够像人类分析师一样迭代分析，以便深入挖掘数据并找到根本原因。

#### 验收标准

1. WHEN Insight Agent 完成分析后 THEN 系统应调用 Replanner Agent 评估是否需要重规划
2. WHEN Replanner Agent 评估时 THEN 系统应基于所有轮次的累积洞察判断问题是否充分回答
3. WHEN Replanner Agent 评估时 THEN 系统应接收原始问题、累积洞察、当前轮次和最大轮次作为输入
4. WHEN 问题未充分回答时 THEN 系统应生成新问题以获取更多/不同维度的数据
5. WHEN 需要重规划时 THEN 系统应重新调用 Understanding Agent 理解新问题
6. WHEN 需要重规划时 THEN 系统应重新调用 Planning Agent 生成新的查询计划
7. WHEN 执行新查询时 THEN 系统应利用缓存避免重复查询已有数据
8. WHEN 重规划次数达到上限（默认 3 轮）时 THEN 系统应停止重规划并生成最终报告
9. WHEN 问题已充分回答时 THEN 系统应停止重规划并生成最终报告
10. WHEN 生成最终报告时 THEN 系统应整合所有轮次的洞察构建完整的分析结果

### 需求 14: 查询结果缓存

**用户故事**: 作为系统架构师，我希望系统能够缓存查询结果，以便在重规划时避免重复查询。

#### 验收标准

1. WHEN 执行查询时 THEN 系统应生成查询的唯一标识（query_key）
2. WHEN 执行查询时 THEN 系统应将查询结果和 query_key 缓存到 Store 的 /query_cache/ 命名空间
3. WHEN Planning Agent 生成查询计划时 THEN 系统应为每个子查询生成 query_key
4. WHEN 执行查询前时 THEN 系统应检查缓存中是否已有相同 query_key 的结果
5. WHEN 缓存命中时 THEN 系统应直接返回缓存结果而不执行查询
6. WHEN 缓存未命中时 THEN 系统应执行查询并缓存结果
7. WHEN 会话结束时 THEN 系统应清理该会话的查询缓存
8. WHEN 查询参数完全相同时 THEN 系统应生成相同的 query_key

### 需求 15: Question Boost Agent 集成

**用户故事**: 作为用户，我希望系统能够优化我的问题，以便获得更准确的分析结果。

#### 验收标准

1. WHEN 前端传递 `boost_question=true` 参数时 THEN 系统应调用 Boost Agent 优化问题
2. WHEN Boost Agent 优化问题时 THEN 系统应补充缺失信息（时间范围、维度、度量等）
3. WHEN Boost Agent 优化问题时 THEN 系统应使用元数据工具验证字段名
4. WHEN 问题优化完成后 THEN 系统应使用优化后的问题继续分析
5. WHEN 前端传递 `boost_question=false` 参数时 THEN 系统应跳过问题优化

### 需求 16: 语义字段映射

**用户故事**: 作为用户，我希望系统能够理解我使用的业务术语，以便自动映射到正确的技术字段名。

#### 验收标准

1. WHEN Understanding Agent 完成后 THEN 系统应调用 semantic_map_fields 工具进行字段映射
2. WHEN 调用 semantic_map_fields 时 THEN 系统应传入业务术语列表、问题上下文和元数据
3. WHEN 系统初始化时 THEN 系统应从 Tableau 元数据构建字段向量索引
4. WHEN 构建向量索引时 THEN 系统应为每个字段生成包含字段名、描述、示例值的富文本向量
5. WHEN 用户使用业务术语时 THEN 系统应使用向量检索找到 Top-K（如 K=5）候选字段
6. WHEN 找到候选字段后 THEN 系统应使用 LLM 理解问题上下文选择最佳匹配
7. WHEN LLM 选择字段时 THEN 系统应考虑字段类型（维度 vs 度量）
8. WHEN LLM 选择字段时 THEN 系统应考虑字段的业务含义
9. WHEN LLM 选择字段时 THEN 系统应考虑问题中的其他字段
10. WHEN 字段映射时 THEN 系统应处理同义词（如"收入"="营收"="销售额"）
11. WHEN 字段映射时 THEN 系统应支持多语言（如"Sales"="销售额"）
12. WHEN 字段映射时 THEN 系统应支持模糊匹配（如"销售" → "销售额"）
13. WHEN 映射置信度高（> 0.8）时 THEN 系统应直接使用该字段
14. WHEN 映射置信度中等（0.5-0.8）时 THEN 系统应返回最佳匹配并记录警告
15. WHEN 映射置信度低（< 0.5）时 THEN 系统应返回多个候选字段并请求用户确认
16. WHEN 字段映射完成时 THEN 系统应返回 FieldMappingResult（包含映射、置信度、候选字段、推理过程）
17. WHEN Planning Agent 执行时 THEN 系统应使用 FieldMappingResult 生成 Intent 模型
18. WHEN 生成 Intent 时 THEN 系统应将 mapping_confidence 和 mapping_alternatives 添加到 Intent 模型
19. WHEN 用户确认字段映射时 THEN 系统应将映射关系保存到 Store 用于学习
20. WHEN 下次遇到相同术语时 THEN 系统应优先使用历史映射并提升置信度

### 需求 17: 数据处理层迁移

**用户故事**: 作为开发者，我希望将数据处理层从 Polars 迁移到 Pandas，以便团队更熟悉和生态系统更成熟。

#### 验收标准

1. WHEN 系统处理数据时 THEN 系统应使用 Pandas DataFrame 而不是 Polars DataFrame
2. WHEN 迁移 DataProcessor 时 THEN 系统应更新所有数据处理方法使用 Pandas API
3. WHEN 迁移 Processors 时 THEN 系统应更新所有数据处理器（AggregationProcessor、FilterProcessor 等）
4. WHEN 迁移 QueryResult 模型时 THEN 系统应更新数据类型定义
5. WHEN 迁移完成后 THEN 所有数据处理功能应保持不变
6. WHEN 迁移完成后 THEN 所有现有测试应通过
7. WHEN 迁移完成后 THEN 系统性能应不低于迁移前
8. WHEN 迁移完成后 THEN 系统应移除所有 Polars 依赖

### 需求 18: 渐进式洞察系统架构

**用户故事**: 作为系统架构师，我希望渐进式洞察系统有清晰的分层架构，以便实现模块化和可维护性。

#### 验收标准

1. WHEN 实现渐进式洞察系统时 THEN 系统应包含 Coordinator（主持人）组件
2. WHEN Coordinator 评估数据时 THEN 系统应决定使用直接分析还是渐进式分析策略
3. WHEN 实现准备层时 THEN 系统应包含 Data Profiler（数据画像）组件
4. WHEN 实现准备层时 THEN 系统应包含 Semantic Chunker（语义分块器）组件
5. WHEN 实现准备层时 THEN 系统应包含 Adaptive Optimizer（自适应优化器）组件
6. WHEN 实现分析层时 THEN 系统应包含 Chunk Analyzer（块分析器）组件
7. WHEN 实现分析层时 THEN 系统应包含 Pattern Detector（模式检测器）组件
8. WHEN 实现分析层时 THEN 系统应包含 Anomaly Detector（异常检测器）组件
9. WHEN 实现累积层时 THEN 系统应包含 Insight Accumulator（洞察累积器）组件
10. WHEN 实现累积层时 THEN 系统应包含 Quality Filter（质量过滤器）组件
11. WHEN 实现累积层时 THEN 系统应包含 Dedup & Merge（去重合并）组件
12. WHEN 实现合成层时 THEN 系统应包含 Insight Synthesizer（洞察合成器）组件
13. WHEN 实现合成层时 THEN 系统应包含 Summary Generator（摘要生成器）组件
14. WHEN 实现合成层时 THEN 系统应包含 Recommend Generator（建议生成器）组件
15. WHEN 各层组件交互时 THEN 系统应遵循准备层 → 分析层 → 累积层 → 合成层的流程

### 需求 19: 持久化存储扩展

**用户故事**: 作为系统架构师，我希望扩展持久化存储以支持新功能，以便保存累积洞察和查询缓存。

#### 验收标准

1. WHEN 配置 StoreBackend 时 THEN 系统应支持 /metadata/* 命名空间
2. WHEN 配置 StoreBackend 时 THEN 系统应支持 /hierarchies/* 命名空间
3. WHEN 配置 StoreBackend 时 THEN 系统应支持 /preferences/* 命名空间
4. WHEN 配置 StoreBackend 时 THEN 系统应支持 /insights/* 命名空间用于存储累积洞察
5. WHEN 配置 StoreBackend 时 THEN 系统应支持 /query_cache/* 命名空间用于存储查询缓存
6. WHEN 保存累积洞察时 THEN 系统应将洞察按会话和轮次组织存储
7. WHEN 保存查询缓存时 THEN 系统应使用 query_key 作为索引

### 需求 20: 性能指标和监控

**用户故事**: 作为系统管理员，我希望监控系统性能指标，以便验证重构后的性能提升。

#### 验收标准

1. WHEN 系统处理查询时 THEN 系统应记录分析时间指标
2. WHEN 系统处理查询时 THEN 系统应记录 Token 使用量指标
3. WHEN 系统处理查询时 THEN 系统应记录首次反馈时间指标
4. WHEN 系统使用渐进式分析时 THEN 系统应记录分析的数据块数量
5. WHEN 系统使用早停机制时 THEN 系统应记录跳过的数据量
6. WHEN 系统使用查询缓存时 THEN 系统应记录缓存命中率
7. WHEN 系统完成分析后 THEN 系统应提供性能摘要报告
8. WHEN 对比新旧系统时 THEN 分析时间应提升至少 3 倍
9. WHEN 对比新旧系统时 THEN Token 使用应减少至少 50%
10. WHEN 对比新旧系统时 THEN 首次反馈时间应提升至少 10 倍

### 需求 21: 上下文管理

**用户故事**: 作为系统架构师，我希望系统能够智能管理上下文，以便在长时程任务中保持性能和准确性。

#### 验收标准

1. WHEN 系统处理查询时 THEN 系统应使用 LangGraph 的 State 管理上下文
2. WHEN 系统初始化时 THEN 系统应根据模型名称加载对应的上下文配置（context_window, summarization_threshold）
3. WHEN 对话历史超过模型的 summarization_threshold 时 THEN 系统应使用 SummarizationMiddleware 自动总结历史消息
4. WHEN 使用 Claude 模型时 THEN 系统应使用 AnthropicPromptCachingMiddleware 缓存系统提示词（节省 50-90% 成本）
5. WHEN 使用其他模型时 THEN 系统应使用 PersistentStore 实现应用层缓存（缓存 LLM 响应）
6. WHEN 系统需要缓存查询结果时 THEN 系统应使用 PersistentStore（SQLite）进行持久化缓存
7. WHEN 系统需要缓存 LLM 响应时 THEN 系统应使用 PersistentStore 的 llm_cache 命名空间
8. WHEN 缓存 LLM 响应时 THEN 系统应使用系统提示词 + 用户输入的 hash 作为缓存 key
9. WHEN 缓存 LLM 响应时 THEN 系统应设置合理的 TTL（默认 1 小时）
10. WHEN 需要语义缓存时 THEN 系统应使用向量相似度匹配历史查询（可选功能）
7. WHEN 查询结果过大时 THEN 系统应使用 FilesystemMiddleware 保存到文件而不是放入上下文
8. WHEN 子代理执行时 THEN 系统应为每个子代理创建独立的上下文
9. WHEN 子代理完成时 THEN 系统应只将结构化结果返回主 Agent 而不是完整上下文
10. WHEN 多轮分析时 THEN 系统应累积每轮的洞察而不是保留所有原始数据
11. WHEN 系统提示词包含元数据时 THEN 系统应利用 Prompt Caching 避免重复传输
12. WHEN 会话结束时 THEN 系统应清理临时上下文和文件

### 需求 22: 多用户并发支持

**用户故事**: 作为系统管理员，我希望系统能够支持多用户同时发起数据分析，以便服务多个用户。

#### 验收标准

1. WHEN 多个用户同时发起查询时 THEN 系统应为每个用户创建独立的会话
2. WHEN 创建会话时 THEN 系统应使用 UUID + 时间戳 + 用户ID 生成唯一的 thread_id
3. WHEN 生成 thread_id 时 THEN 系统应确保全局唯一性（使用 UUID 或雪花算法）
4. WHEN 创建 thread_id 时 THEN 系统应将会话信息保存到 Redis 用于验证
5. WHEN 用户查询时 THEN 系统应验证 thread_id 的有效性
6. WHEN 用户查询时 THEN 系统应使用 thread_id 隔离不同用户的上下文
7. WHEN 用户查询时 THEN 系统应使用 thread_id 隔离不同用户的查询缓存
8. WHEN 用户查询时 THEN 系统应使用 thread_id 隔离不同用户的累积洞察
9. WHEN 用户查询时 THEN 系统应使用 thread_id 隔离不同用户的临时文件
10. WHEN 系统使用 StoreBackend 时 THEN 系统应支持按 thread_id 查询和存储数据
11. WHEN 系统使用 StateBackend 时 THEN 系统应支持按 thread_id 隔离临时文件
12. WHEN 会话超时（默认 1 小时）时 THEN 系统应自动清理该会话的所有资源
13. WHEN API 返回时 THEN 系统应在响应头中包含 X-Thread-ID

### 需求 23: 应用层缓存中间件

**用户故事**: 作为系统架构师，我希望为所有模型实现应用层缓存，以便节省成本和提升性能。

#### 验收标准

1. WHEN 系统初始化时 THEN 系统应创建 ApplicationLevelCacheMiddleware
2. WHEN LLM 调用前时 THEN 系统应生成缓存 key（hash(system_prompt + user_input)）
3. WHEN 缓存 key 生成后时 THEN 系统应检查 PersistentStore 中是否存在缓存
4. WHEN 缓存命中时 THEN 系统应直接返回缓存结果而不调用 LLM
5. WHEN 缓存未命中时 THEN 系统应调用 LLM 并将响应保存到缓存
6. WHEN 保存缓存时 THEN 系统应使用命名空间 ("llm_cache", model_name)
7. WHEN 保存缓存时 THEN 系统应设置 TTL 为 1 小时
8. WHEN 缓存过期时 THEN 系统应自动清理过期数据
9. WHEN 使用 Claude 模型时 THEN 系统应同时使用 AnthropicPromptCachingMiddleware 和 ApplicationLevelCacheMiddleware
10. WHEN 使用其他模型时 THEN 系统应只使用 ApplicationLevelCacheMiddleware

### 需求 24: 语义字段映射的向量存储

**用户故事**: 作为系统架构师，我希望有高效的向量存储系统，以便快速检索候选字段。

#### 验收标准

1. WHEN 系统初始化时 THEN 系统应使用 FAISS 作为向量数据库（MVP 阶段）
2. WHEN 构建向量索引时 THEN 系统应使用 bce-embedding-base-v1（如果有 GPU）或 text-embedding-3-large（如果没有 GPU）作为 Embedding 模型
3. WHEN 构建向量索引时 THEN 系统应只存储 Tableau 元数据（字段信息），不存储数据表的所有数据
3. WHEN 构建向量索引时 THEN 系统应为每个数据源单独构建索引
4. WHEN 向量索引构建完成时 THEN 系统应将索引持久化到磁盘
5. WHEN 系统启动时 THEN 系统应加载已有的向量索引而不是重新构建
6. WHEN 元数据更新时 THEN 系统应支持增量更新向量索引
7. WHEN 检索候选字段时 THEN 系统应使用余弦相似度或点积相似度
8. WHEN 检索候选字段时 THEN 系统应支持设置相似度阈值过滤低质量候选
9. WHEN 向量索引过大时 THEN 系统应支持分片和分布式检索

### 需求 25: 历史查询检索（可选）

**用户故事**: 作为用户，我希望系统能够记住我的历史查询，以便快速获取相似问题的答案和推荐相关问题。

#### 验收标准

1. WHEN 用户完成查询时 THEN 系统应将查询问题和结果向量化并存储到向量数据库
2. WHEN 用户提出新问题时 THEN 系统应在历史查询中搜索相似问题
3. WHEN 找到相似问题（相似度 > 0.95）时 THEN 系统应直接返回缓存结果而不执行查询
4. WHEN 用户输入问题时 THEN 系统应推荐相关的历史问题
5. WHEN 存储历史查询时 THEN 系统应使用命名空间 ("query_history", user_id)
6. WHEN 历史查询过多时 THEN 系统应只保留最近 30 天的查询
7. WHEN 历史查询过多时 THEN 系统应定期清理低频查询

### 需求 26: 洞察检索（可选）

**用户故事**: 作为用户，我希望系统能够构建知识库，以便快速找到相关的历史洞察和分析。

#### 验收标准

1. WHEN 系统生成洞察时 THEN 系统应将洞察内容向量化并存储到向量数据库
2. WHEN 用户提出问题时 THEN 系统应在历史洞察中搜索相关洞察
3. WHEN 找到相关洞察时 THEN 系统应在结果中展示相关洞察作为参考
4. WHEN 用户查看分析结果时 THEN 系统应推荐相关的历史分析
5. WHEN 存储洞察时 THEN 系统应使用命名空间 ("insights_history", datasource_luid)
6. WHEN 洞察过多时 THEN 系统应只保留最近 90 天的洞察
7. WHEN 洞察过多时 THEN 系统应定期清理低质量洞察

### 需求 27: 文档和示例

**用户故事**: 作为新加入的开发者，我希望有清晰的文档和示例，以便快速理解新架构。

#### 验收标准

1. WHEN 查看文档时 THEN 系统应提供 DeepAgents 架构概述
2. WHEN 查看文档时 THEN 系统应提供子代理定义示例
3. WHEN 查看文档时 THEN 系统应提供自定义中间件开发指南
4. WHEN 查看文档时 THEN 系统应提供工具集成示例
5. WHEN 查看文档时 THEN 系统应提供完整的 API 使用示例
6. WHEN 查看文档时 THEN 系统应提供迁移指南（从旧架构到新架构）
7. WHEN 查看文档时 THEN 系统应提供渐进式洞察分析的详细说明
8. WHEN 查看文档时 THEN 系统应提供重规划机制的详细说明
9. WHEN 查看文档时 THEN 系统应提供渐进式洞察系统的分层架构说明
10. WHEN 查看文档时 THEN 系统应提供语义字段映射的实现指南
11. WHEN 查看文档时 THEN 系统应提供上下文管理的最佳实践
12. WHEN 查看文档时 THEN 系统应提供多用户并发的配置指南
