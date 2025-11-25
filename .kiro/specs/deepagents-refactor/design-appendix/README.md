# 设计文档附录索引

本目录包含 DeepAgents 重构设计文档的详细附录。

## 📚 已完成的附录

### ✅ 1. [子代理设计详解](./subagent-design.md)
详细描述 5 个子代理的设计：
- Boost Agent - 问题优化
- Understanding Agent - 问题理解
- Planning Agent - 查询规划
- Insight Agent - 洞察分析（含渐进式分析）
- Replanner Agent - 重规划决策

**内容包括**：配置、输入输出、Prompt 设计、协作流程

### ✅ 2. [中间件设计详解](./middleware-design.md)
详细描述 3 个自定义中间件的设计：
- TableauMetadataMiddleware - 元数据注入
- VizQLQueryMiddleware - 查询语法指南
- ApplicationLevelCacheMiddleware - 应用层缓存

**内容包括**：实现代码、系统提示词、缓存策略、开发指南

---

## 📝 已完成的附录（续）

### ✅ 3. [工具设计详解](./tools-design.md)
详细描述 **8 个 Tableau 工具** 的设计：

**核心工具（5个）**：
- get_metadata - 元数据查询
- semantic_map_fields - 语义字段映射（RAG+LLM）
- parse_date - 日期解析
- build_vizql_query - 查询构建
- execute_vizql_query - 查询执行

**辅助工具（3个）**：
- process_query_result - 数据处理
- detect_statistics - 统计检测
- save_large_result - 大结果保存

**内容包括**：工具定义、内部实现（100%复用现有组件）、协作流程、开发指南

### ✅ 4. [数据模型设计详解](./data-models.md)
详细描述所有数据模型定义：
- State 模型（DeepAgentState、SubAgentState）
- Context 模型（DeepAgentContext、SessionContext）
- Question 模型（QuestionUnderstanding、QuestionBoost）
- Query 模型（QueryPlan、QuerySpec、QueryResult）
- Insight 模型（Insight、InsightCollection、ContributionItem）
- Result 模型（FinalReport、AnalysisRound、ReplanDecision）
- Cache 模型（CacheEntry、CacheStats）
- Error 模型（DeepAgentError、PerformanceMetrics）

**内容包括**：完整的 Pydantic 模型定义、模型关系图

### ✅ 5. [DeepAgents 特性详解](./deepagents-features.md)
详细描述如何充分利用 DeepAgents 框架的高级特性：
- 流式输出（astream_events）- Token 级流式输出、SSE 集成
- Store 高级用法 - 命名空间、语义搜索、TTL 管理
- Context 传递机制 - 避免上下文污染、确保线程安全
- 错误恢复机制 - 重试、降级、错误传播
- 性能监控和追踪 - Callbacks、实时监控

**内容包括**：完整的代码示例、最佳实践、性能优化建议

### ✅ 6. [剩余主题概要](./remaining-topics.md)
包含以下主题的概要说明：
- 渐进式洞察系统（架构分层、工作流程）
- 语义字段映射（RAG+LLM混合模型架构、映射流程）
- 缓存系统设计（四层架构、缓存策略）
- API 设计（端点、请求响应格式、SSE 事件）

**说明**：这些是概要性说明，详细实现在代码中体现

---

## 📖 使用指南

### 阅读顺序建议

**快速了解**：
1. 先阅读 [主文档](../design.md)
2. 了解整体架构和核心决策

**深入学习**：
1. [子代理设计详解](./subagent-design.md) - 了解 Agent 如何协作
2. [中间件设计详解](./middleware-design.md) - 了解如何扩展功能
3. 其他附录 - 根据需要深入了解特定模块

**开发实施**：
1. 参考 [数据模型设计](./data-models.md) - 定义数据结构
2. 参考 [API 设计](./api-design.md) - 实现接口
3. 参考具体模块的附录 - 实现功能

---

## 🔄 文档更新计划

**已完成的附录**：
- ✅ 子代理设计详解
- ✅ 中间件设计详解
- ✅ 工具设计详解（8个工具）
- ✅ 数据模型设计详解（8大类模型）
- ✅ 剩余主题概要（渐进式洞察、语义映射、缓存、API）

**说明**：
- 所有核心设计文档已完成
- 详细实现将在任务执行阶段完成
- 现有的 Prompt 类系统（`tableau_assistant/prompts/`）继续使用，不需要重复定义

---

## 📞 反馈和贡献

如果您在阅读文档时有任何疑问或建议，请：
1. 在相关文档中添加注释
2. 提出具体的改进建议
3. 补充缺失的内容

---

**文档版本**: v1.0  
**最后更新**: 2025-01-15  
**维护者**: DeepAgents 重构团队
