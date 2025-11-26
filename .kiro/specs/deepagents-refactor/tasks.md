# DeepAgents 重构实施任务列表

**版本**: v1.0
**最后更新**: 2025-01-15
**预计工期**: 4-6周

---

## 重要说明

### 核心原则
1. **100% 复用现有组件**：所有核心业务组件（QueryBuilder、QueryExecutor、DataProcessor等）100%保留
2. **保留现有 Prompt 系统**：使用 `tableau_assistant/prompts/` 的 4段式结构 + 自动 Schema 注入
3. **保留现有数据模型**：使用 `tableau_assistant/src/models/` 的 Pydantic 模型
4. **渐进式迁移**：先搭建框架，再逐步迁移功能

### 技术要求
1. **DeepAgents 框架**：使用 LangChain DeepAgents 作为主编排框架
2. **中间件系统**：利用内置中间件 + 3个自定义中间件
3. **子代理架构**：5个子代理（boost, understanding, planning, insight, replanner）
4. **工具封装**：8个工具封装现有组件
5. **数据处理**：使用 Pandas（而非 Polars）- 更好的生态兼容性

### 当前进度

**已完成**: 阶段1-3 基础架构和工具层（23个子任务）✅
- ✅ 项目结构搭建完成
- ✅ 8个工具全部实现（get_metadata, parse_date, build_vizql_query, execute_vizql_query, semantic_map_fields, process_query_result, detect_statistics, save_large_result）
- ✅ 3个中间件全部实现（TableauMetadataMiddleware, VizQLQueryMiddleware, ApplicationLevelCacheMiddleware）
- ✅ 子代理基类实现完成

**测试通过率**: 64/75 (85.3%)
- ✅ 中间件测试: 26/26 全部通过
- ✅ 工具测试: 38/49 通过
- 🔴 **需要紧急修复**: DataProcessor 使用 Polars，需迁移到 Pandas

**待完成**: 
- 🔴 **阶段9: Polars → Pandas 迁移（7个子任务）- 优先级最高**
  - DataProcessor 核心组件迁移
  - 5个数据处理器迁移（YoY, MoM, GrowthRate, Percentage, Custom）
  - 数据模型更新（QueryResult, ProcessingResult）
  - 单元测试更新
  - semantic_map_fields 导入修复
  - 生产级别代码审查
- ⏳ 阶段4-8, 10-11: 子代理、渐进式洞察、缓存、API层、测试

### 参考文档

**核心设计**：
- [设计文档](./design.md) - 技术架构、核心决策、数据流

**详细设计**：
- [子代理设计](./design-appendix/subagent-design.md)
- [中间件设计](./design-appendix/middleware-design.md)
- [工具设计](./design-appendix/tools-design.md)
- [数据模型设计](./design-appendix/data-models.md)
- [字段语义推断](./design-appendix/field-semantics.md) - 统一的字段语义推断系统
- [Task Planner与RAG集成](./design-appendix/task-planner-rag-integration.md) - 基于现有实现的集成方案
- [渐进式洞察系统](./design-appendix/progressive-insights.md) - Part 1-4，完整的渐进式分析设计
- [缓存系统](./design-appendix/caching-system.md) - Part 1-2，四层缓存架构
- [API设计](./design-appendix/api-design.md) - Part 1-3，REST API详细设计

---

## 阶段1：基础架构搭建 (P0)

- [ ] 1. 项目结构重组
  - [x] 1.1 创建 DeepAgents 目录结构



    - 创建 `src/deepagents/` 目录
    - 创建 `src/deepagents/subagents/` 目录
    - 创建 `src/deepagents/middleware/` 目录
    - 创建 `src/deepagents/tools/` 目录
    - 创建 `src/progressive_insight/` 目录
    - 创建 `src/semantic_mapping/` 目录
    - _Requirements: 1.1, 1.2, 1.3_
    - _预计时间: 0.5天_

  - [x] 1.2 安装和配置 DeepAgents


    - 安装 `langchain-deepagents` 包
    - 配置 CompositeBackend（SQLite）
    - 配置 PersistentStore
    - 测试基础功能
    - _Requirements: 1.1, 1.2_
    - _预计时间: 0.5天_


  - [x] 1.3 数据模型适配


    - 创建 `src/models/deepagent_state.py`（DeepAgentState）
    - 创建 `src/models/deepagent_context.py`（DeepAgentContext）
    - 验证与现有模型的兼容性
    - _Requirements: 1.3, 所有数据模型需求_
    - _预计时间: 1天_

---

## 阶段2：工具层实现 (P0)


- [x] 2. 核心工具封装（5个）
  - [x] 2.1 实现 get_metadata 工具
    - ✅ 封装 MetadataManager 组件
    - ✅ 定义工具 docstring
    - ✅ 使用 Store 缓存元数据（namespace: "metadata"）
    - ✅ 添加重试机制（@retry 装饰器）
    - ✅ 添加单元测试
    - _Requirements: 2.1, 2.2_
    - _参考: design-appendix/deepagents-features.md#2-store-高级用法_
    - _预计时间: 0.5天_
    - **状态**: ✅ 已完成 - 生产级别实现,包含完整错误处理和重试机制

  - [x] 2.2 实现 parse_date 工具
    - ✅ 封装 DateParser 组件
    - ✅ 定义工具 docstring
    - ✅ 添加单元测试
    - _Requirements: 2.3_
    - _预计时间: 0.5天_
    - **状态**: ✅ 已完成 - 生产级别实现,支持绝对和相对日期解析

  - [x] 2.3 实现 build_vizql_query 工具
    - ✅ 封装 QueryBuilder 组件
    - ✅ 定义工具 docstring
    - ✅ 添加单元测试
    - _Requirements: 2.4_
    - _预计时间: 0.5天_
    - **状态**: ✅ 已完成 - 生产级别实现,完整的VizQL查询构建

  - [x] 2.4 实现 execute_vizql_query 工具
    - ✅ 封装 QueryExecutor 组件
    - ✅ 定义工具 docstring
    - ✅ 添加重试机制（处理 TimeoutError、ConnectionError）
    - ✅ 添加降级策略（超时时返回部分结果）
    - ✅ 添加单元测试
    - _Requirements: 2.5_
    - _参考: design-appendix/deepagents-features.md#4-错误恢复机制_
    - _预计时间: 1天_
    - **状态**: ✅ 已完成 - 生产级别实现,包含重试和错误分类

  - [x] 2.5 实现 semantic_map_fields 工具（RAG+LLM）
    - ✅ 实现 Vector Store 管理（FAISS）
    - ✅ 实现 Field Indexer
    - ✅ 实现 Semantic Mapper（RAG+LLM）
    - ✅ 使用 Store 缓存映射结果（namespace: "semantic_mapping"）
    - ✅ 封装为工具
    - ⚠️ 单元测试存在依赖问题（langchain.schema已弃用）
    - _Requirements: 2.6, 8.1, 8.2_
    - _参考: design-appendix/deepagents-features.md#2-store-高级用法_
    - _预计时间: 2天_
    - **状态**: ⚠️ 需要修复 - 代码已实现但需要更新导入语句

- [x] 3. 辅助工具封装（3个）
  - [x] 3.1 实现 process_query_result 工具
    - ✅ 封装 DataProcessor 组件
    - ✅ 定义工具 docstring
    - ⚠️ 单元测试失败（缺少polars依赖）
    - _Requirements: 2.7_
    - _预计时间: 0.5天_
    - **状态**: ⚠️ 需要修复 - 代码已实现但缺少polars依赖

  - [x] 3.2 实现 detect_statistics 工具
    - ✅ 封装 StatisticsDetector 组件
    - ✅ 定义工具 docstring
    - ✅ 添加单元测试（9个测试全部通过）
    - _Requirements: 2.8_
    - _预计时间: 0.5天_
    - **状态**: ✅ 已完成 - 生产级别实现,完整的统计分析功能

  - [x] 3.3 实现 save_large_result 工具
    - ✅ 实现大结果保存逻辑
    - ✅ 定义工具 docstring
    - ✅ 添加单元测试（10个测试全部通过）
    - _Requirements: 2.9_
    - _预计时间: 0.5天_
    - **状态**: ✅ 已完成 - 生产级别实现,支持JSON/CSV和压缩

---

## 阶段3：中间件实现 (P0)

- [x] 4. 自定义中间件开发（3个）
  - [x] 4.1 实现 TableauMetadataMiddleware
    - ✅ 注入 get_metadata 工具
    - ✅ 不设置系统提示词（使用现有 Prompt 类）
    - ✅ 添加单元测试（6个测试全部通过）
    - _Requirements: 3.1_
    - _预计时间: 0.5天_
    - **状态**: ✅ 已完成 - 生产级别实现,完整的工具注入机制

  - [x] 4.2 实现 VizQLQueryMiddleware
    - ✅ 注入 execute_vizql_query 工具
    - ✅ 不设置系统提示词（使用现有 Prompt 类）
    - ✅ 添加单元测试（8个测试全部通过）
    - _Requirements: 3.2_
    - _预计时间: 0.5天_
    - **状态**: ✅ 已完成 - 生产级别实现,完整的查询执行工具

  - [x] 4.3 实现 ApplicationLevelCacheMiddleware
    - ✅ 实现 before_llm_call 钩子（检查缓存）
    - ✅ 实现 after_llm_call 钩子（保存缓存）
    - ✅ 实现缓存 key 生成逻辑
    - ✅ 配置 TTL（默认 1小时）
    - ✅ 添加单元测试（12个测试全部通过）
    - _Requirements: 3.3, 9.2_
    - _预计时间: 1天_
    - **状态**: ✅ 已完成 - 生产级别实现,完整的缓存管理和统计

---

## 阶段4：子代理实现 (P0)

- [ ] 5. 基础子代理实现（5个）
  - [x] 5.0 实现 BaseSubAgent 基类
    - ✅ 统一的执行流程
    - ✅ 自动的 Temperature 配置
    - ✅ 复用现有的 Prompt 类系统
    - ✅ 支持用户配置覆盖
    - ✅ 添加单元测试（11个测试全部通过）
    - _预计时间: 1天_
    - **状态**: ✅ 已完成 - 生产级别基类实现,为所有子代理提供统一接口

  - [ ] 5.1 实现 boost-agent
    - 配置 Agent（model, tools, max_tokens等）
    - 使用现有的 QuestionBoostPrompt
    - 使用 Store 检索历史问题（语义搜索）
    - 输出 QuestionBoost 模型
    - 添加错误处理和重试
    - 添加单元测试
    - _Requirements: 4.1_
    - _参考: design-appendix/deepagents-features.md#2-store-高级用法_
    - _预计时间: 1.5天_
    - **状态**: ⏳ 未开始 - 基类已就绪,可以开始实现

  - [ ] 5.2 实现 understanding-agent
    - 配置 Agent（model, tools, max_tokens等）
    - 使用现有的 UnderstandingPrompt
    - 输出 QuestionUnderstanding 模型
    - 添加问题拆分功能
    - 添加单元测试
    - _Requirements: 4.2_
    - _预计时间: 1天_
    - **状态**: ⏳ 未开始

  - [ ] 5.3 实现 planning-agent
    - 配置 Agent（model, tools, max_tokens等）
    - 使用现有的 TaskPlannerPrompt
    - 集成 semantic_map_fields 工具（RAG+LLM）
    - 输出 QueryPlan 模型
    - 添加单元测试
    - _Requirements: 4.3, 8.1, 8.2_
    - _预计时间: 1.5天_
    - **状态**: ⏳ 未开始

  - [ ] 5.4 实现 insight-agent
    - 配置 Agent（model, tools, max_tokens等）
    - 使用现有的 InsightPrompt
    - 集成渐进式分析逻辑
    - 使用 Store 存储异常知识库（namespace: "anomaly_knowledge"）
    - 实现降级策略（渐进式→全量→基础）
    - 输出 InsightCollection 模型
    - 添加错误处理
    - 添加单元测试
    - _Requirements: 4.4, 7.1, 7.2, 7.3_
    - _参考: design-appendix/deepagents-features.md#4-错误恢复机制_
    - _预计时间: 2.5天_
    - **状态**: ⏳ 未开始

  - [ ] 5.5 实现 replanner-agent
    - 配置 Agent（model, tools, max_tokens等）
    - 使用现有的 ReplannerPrompt
    - 输出 ReplanDecision 模型
    - 添加单元测试
    - _Requirements: 4.5, 6.1, 6.2_
    - _预计时间: 1天_
    - **状态**: ⏳ 未开始

---

## 阶段5：渐进式洞察系统 (P1)

- [ ] 6. 渐进式分析核心组件
  - [ ] 6.1 实现 Coordinator（决策器）
    - 实现 decide_strategy 方法（直接分析 vs 渐进式分析）
    - 实现数据规模检测（阈值：100行）
    - 实现复杂度评估
    - 实现Token预算估算
    - 添加单元测试
    - _Requirements: 7.1_
    - _参考: design-appendix/progressive-insights.md#2.1_
    - _预计时间: 0.5天_

  - [ ] 6.2 实现 DataProfiler（数据画像生成器）
    - 实现基本统计（行数、列数）
    - 实现数值字段分布分析（min/max/mean/median/std）
    - 实现异常值检测（Z-score方法，阈值3.0）
    - 实现分类字段分布分析
    - 实现数据质量评估（完整性、一致性、有效性）
    - 实现分块策略推荐
    - 添加单元测试
    - _Requirements: 7.1_
    - _参考: design-appendix/progressive-insights.md#2.2_
    - _预计时间: 1.5天_

  - [ ] 6.3 实现 SemanticChunker（智能分块器）
    - 实现异常值优先分块策略（anomaly_first）
    - 实现Top优先分块策略（top_first）
    - 实现混合分块策略（mixed）
    - 实现主要度量字段识别
    - 实现DataChunk数据模型
    - 添加单元测试
    - _Requirements: 7.1_
    - _参考: design-appendix/progressive-insights.md#2.3_
    - _预计时间: 1.5天_

  - [ ] 6.4 实现 PatternDetector（模式检测器）
    - 实现趋势检测（线性回归）
    - 实现周期性检测（自相关）
    - 实现相关性检测（Pearson相关系数）
    - 实现Pattern数据模型
    - 添加单元测试
    - _Requirements: 7.2_
    - _参考: design-appendix/progressive-insights-part2.md#2.5_
    - _预计时间: 1天_

  - [ ] 6.5 实现 AnomalyDetector（异常检测器）
    - 实现统计异常检测（Z-score > 3）
    - 实现业务异常检测（负值、未来日期等）
    - 实现Anomaly数据模型
    - 添加单元测试
    - _Requirements: 7.2_
    - _参考: design-appendix/progressive-insights-part2.md#2.6_
    - _预计时间: 1天_

  - [ ] 6.6 实现 ChunkAnalyzer（块分析器）
    - 集成PatternDetector和AnomalyDetector
    - 实现LLM输入准备（数据摘要、模式摘要、异常摘要）
    - 实现LLM洞察生成
    - 实现ChunkInsight数据模型
    - 添加单元测试
    - _Requirements: 7.2_
    - _参考: design-appendix/progressive-insights-part2.md#2.4_
    - _预计时间: 1.5天_

  - [ ] 6.7 实现 InsightAccumulator（洞察累积器）
    - 实现洞察累积逻辑
    - 实现早停条件检查（趋势稳定、洞察饱和、置信度达标）
    - 实现趋势历史记录
    - 实现洞察相似度计算
    - 实现AccumulatedInsights数据模型
    - 添加单元测试
    - _Requirements: 7.2_
    - _参考: design-appendix/progressive-insights-part3.md#2.7_
    - _预计时间: 1.5天_

  - [ ] 6.8 实现 QualityFilter（质量过滤器）
    - 实现置信度过滤（阈值0.5）
    - 实现重要性过滤（阈值0.3）
    - 实现证据检查
    - 实现描述模糊度检查
    - 添加单元测试
    - _Requirements: 7.2_
    - _参考: design-appendix/progressive-insights-part3.md#2.8_
    - _预计时间: 0.5天_

  - [ ] 6.9 实现 DedupMerger（去重合并器）
    - 实现洞察分组（按类型）
    - 实现相似度计算（SequenceMatcher）
    - 实现洞察合并（合并证据和数据点）
    - 添加单元测试
    - _Requirements: 7.2_
    - _参考: design-appendix/progressive-insights-part3.md#2.9_
    - _预计时间: 1天_

  - [ ] 6.10 实现 InsightSynthesizer（洞察合成器）
    - 集成QualityFilter和DedupMerger
    - 实现优先级排序
    - 实现关联分析
    - 实现最终洞察构建
    - 实现FinalInsight数据模型
    - 添加单元测试
    - _Requirements: 7.3_
    - _参考: design-appendix/progressive-insights-part3.md#2.10_
    - _预计时间: 1.5天_

  - [ ] 6.11 实现 SummaryGenerator（摘要生成器）
    - 实现LLM Prompt准备
    - 实现执行摘要生成
    - 实现ExecutiveSummary数据模型
    - 添加单元测试
    - _Requirements: 7.3_
    - _参考: design-appendix/progressive-insights-part4.md#2.11_
    - _预计时间: 0.5天_

  - [ ] 6.12 实现 RecommendGenerator（建议生成器）
    - 实现LLM Prompt准备
    - 实现建议生成（数据质量、业务行动、进一步分析）
    - 实现Recommendation数据模型
    - 添加单元测试
    - _Requirements: 7.3_
    - _参考: design-appendix/progressive-insights-part4.md#2.12_
    - _预计时间: 0.5天_

  - [ ] 6.13 实现 ProgressiveInsightSystem（主系统）
    - 集成所有组件
    - 实现直接分析流程
    - 实现渐进式分析流程
    - 实现并行处理优化（可选）
    - 实现缓存优化（可选）
    - 添加性能监控
    - 添加端到端测试
    - _Requirements: 7.1, 7.2, 7.3_
    - _参考: design-appendix/progressive-insights-part4.md#3_
    - _预计时间: 2天_

---

## 阶段6：主 Agent 编排 (P0)

- [ ] 7. 主 Agent 实现
  - [ ] 7.1 创建 AgentFactory
    - 实现 create_deep_agent 函数
    - 配置所有中间件
    - 配置所有子代理
    - 配置所有工具
    - 配置 Backend（CompositeBackend + PersistentStore）
    - 配置 Context（DeepAgentContext）
    - _Requirements: 1.1, 1.2_
    - _参考: design-appendix/deepagents-features.md#3-context-传递机制_
    - _预计时间: 1.5天_

  - [ ] 7.2 实现主流程编排
    - 实现用户输入处理
    - 实现子代理调用流程（使用 Runtime 传递 Context）
    - 实现查询执行流程
    - 实现重规划循环（带错误恢复）
    - 实现最终报告生成
    - 添加性能监控（PerformanceTrackingCallback）
    - _Requirements: 所有需求_
    - _参考: design-appendix/deepagents-features.md#5-性能监控和追踪_
    - _预计时间: 2.5天_

  - [ ] 7.3 实现并行查询执行
    - 分析查询依赖关系
    - 实现并行执行策略
    - 实现流水线执行策略
    - _Requirements: 5.1, 5.2_
    - _预计时间: 1天_

---

## 阶段7：缓存系统优化 (P1)

- [ ] 8. 四层缓存架构
  - [ ] 8.1 配置 L1 Prompt Caching（Anthropic）
    - 配置 AnthropicPromptCachingMiddleware
    - 优化Prompt结构（固定内容在前）
    - 监控缓存使用情况（cache_read_input_tokens）
    - 验证成本节省效果（50-90%）
    - _Requirements: 9.1_
    - _参考: design-appendix/caching-system.md#2_
    - _预计时间: 0.5天_

  - [ ] 8.2 实现 L2 Application Cache（SQLite）
    - 实现ApplicationCache类
    - 实现缓存Key生成（model + messages + temperature）
    - 实现TTL检查（默认1小时）
    - 实现CachedLLMWrapper
    - 集成到ApplicationLevelCacheMiddleware
    - 监控缓存命中率（目标40-60%）
    - 添加单元测试
    - _Requirements: 9.2_
    - _参考: design-appendix/caching-system.md#3_
    - _预计时间: 1.5天_

  - [ ] 8.3 实现 L3 Query Result Cache（SQLite）
    - 实现QueryResultCache类
    - 实现查询缓存Key生成（datasource_luid + vizql_query）
    - 实现TTL配置（会话期间有效）
    - 实现CachedExecuteVizQLQuery工具
    - 集成到execute_vizql_query工具
    - 监控缓存命中率（目标20-40%）
    - 添加单元测试
    - _Requirements: 9.3_
    - _参考: design-appendix/caching-system.md#4_
    - _预计时间: 1.5天_

  - [ ]* 8.4 实现 L4 Semantic Cache（FAISS，可选）
    - 实现SemanticCache类
    - 实现查询向量生成（Embedding模型）
    - 实现向量相似度检索（FAISS）
    - 配置相似度阈值（默认0.95）
    - 实现缓存映射管理
    - 监控缓存命中率（目标5-15%）
    - 添加单元测试
    - _Requirements: 9.4_
    - _参考: design-appendix/caching-system-part2.md#5_
    - _预计时间: 2天_

  - [ ] 8.5 实现缓存管理功能
    - 实现TTL缓存策略
    - 实现LRU缓存策略
    - 实现CacheInvalidator（主动失效）
    - 实现CacheWarmer（缓存预热）
    - 添加单元测试
    - _Requirements: 9.1, 9.2, 9.3, 9.4_
    - _参考: design-appendix/caching-system-part2.md#6_
    - _预计时间: 1天_

  - [ ] 8.6 实现缓存监控系统
    - 实现CacheMetrics数据模型
    - 实现CacheMonitor（指标收集）
    - 实现CacheReporter（日志和报告）
    - 集成到主系统
    - 添加性能仪表板
    - _Requirements: 13.2_
    - _参考: design-appendix/caching-system-part2.md#7_
    - _预计时间: 1天_

  - [ ] 8.7 实现CachedDeepAgent（完整集成）
    - 集成所有四层缓存
    - 实现统一的缓存接口
    - 实现缓存性能监控
    - 添加端到端测试
    - 验证整体缓存效果
    - _Requirements: 9.1, 9.2, 9.3, 9.4_
    - _参考: design-appendix/caching-system-part2.md#8_
    - _预计时间: 1.5天_

---

## 阶段8：API 层实现 (P0)

- [ ] 9. 数据模型定义
  - [ ] 9.1 实现请求模型
    - 实现ChatRequest模型（question, datasource_luid, boost_question, thread_id, model_config）
    - 添加字段验证和示例
    - 添加单元测试
    - _Requirements: 10.1_
    - _参考: design-appendix/api-design.md#2.1_
    - _预计时间: 0.5天_

  - [ ] 9.2 实现响应模型
    - 实现Insight模型
    - 实现Recommendation模型
    - 实现PerformanceMetrics模型
    - 实现ChatResponse模型
    - 添加字段验证和示例
    - 添加单元测试
    - _Requirements: 10.1_
    - _参考: design-appendix/api-design.md#2.2_
    - _预计时间: 0.5天_

  - [ ] 9.3 实现错误响应模型
    - 实现ErrorResponse模型
    - 定义HTTP状态码映射
    - 添加单元测试
    - _Requirements: 11.3_
    - _参考: design-appendix/api-design-part3.md#4.1_
    - _预计时间: 0.5天_

- [ ] 10. FastAPI 端点实现
  - [ ] 10.1 实现 POST /api/v1/chat（同步查询）
    - 实现请求验证
    - 实现数据源权限检查
    - 实现AgentFactory调用
    - 实现thread_id生成/使用
    - 实现响应构建
    - 添加错误处理（400/403/500）
    - 添加单元测试
    - _Requirements: 10.1_
    - _参考: design-appendix/api-design-part2.md#3.1_
    - _预计时间: 1.5天_

  - [ ] 10.2 实现 POST /api/v1/chat/stream（流式查询）
    - 实现SSE事件生成器
    - 监听 `on_chat_model_stream` 事件（Token流）
    - 监听 `on_chain_start/end` 事件（Agent进度）
    - 监听 `on_tool_start/end` 事件（工具调用）
    - 实现format_sse_event函数
    - 配置StreamingResponse头部
    - 添加错误处理
    - 添加单元测试
    - _Requirements: 10.2, 12.1, 12.2_
    - _参考: design-appendix/api-design-part2.md#3.2_
    - _预计时间: 2.5天_

  - [ ] 10.3 实现 GET /api/v1/health（健康检查）
    - 实现HealthResponse模型
    - 检查数据库连接
    - 检查LLM服务
    - 检查Tableau服务
    - 判断整体状态（healthy/degraded）
    - 添加单元测试
    - _Requirements: 10.3_
    - _参考: design-appendix/api-design-part2.md#3.3_
    - _预计时间: 0.5天_

  - [ ] 10.4 实现 GET /api/v1/datasources（数据源列表）
    - 实现DataSource模型
    - 实现DataSourceListResponse模型
    - 从Tableau获取数据源列表
    - 实现分页（limit/offset）
    - 添加权限过滤
    - 添加单元测试
    - _Requirements: 10.4_
    - _参考: design-appendix/api-design-part2.md#3.4_
    - _预计时间: 1天_

  - [ ] 10.5 实现 GET /api/v1/datasources/{luid}/metadata（元数据）
    - 实现FieldMetadata模型
    - 实现DataSourceMetadata模型
    - 实现权限检查
    - 从Tableau获取元数据
    - 添加单元测试
    - _Requirements: 10.5_
    - _参考: design-appendix/api-design-part2.md#3.5_
    - _预计时间: 0.5天_

  - [ ] 10.6 实现 GET /api/v1/threads/{thread_id}/history（会话历史）
    - 实现Message模型
    - 实现ThreadHistoryResponse模型
    - 实现thread所有权验证
    - 从Store获取历史消息
    - 添加单元测试
    - _Requirements: 10.6_
    - _参考: design-appendix/api-design-part2.md#3.6_
    - _预计时间: 0.5天_

- [ ] 11. 错误处理和中间件
  - [ ] 11.1 实现错误处理中间件
    - 实现请求ID生成
    - 实现ValueError处理（400）
    - 实现PermissionError处理（403）
    - 实现通用异常处理（500）
    - 实现HTTPException处理器
    - 添加错误日志
    - 添加单元测试
    - _Requirements: 11.3_
    - _参考: design-appendix/api-design-part3.md#4.3_
    - _预计时间: 1天_

- [ ] 12. 认证和授权
  - [ ] 12.1 实现JWT认证
    - 实现User模型
    - 实现create_access_token函数
    - 实现get_current_user依赖
    - 实现POST /api/v1/auth/login端点
    - 配置JWT密钥和过期时间
    - 添加单元测试
    - _Requirements: 11.1_
    - _参考: design-appendix/api-design-part3.md#5.2_
    - _预计时间: 1.5天_

  - [ ] 12.2 实现权限检查
    - 实现require_role装饰器
    - 实现has_datasource_access函数
    - 实现is_thread_owner函数
    - 添加单元测试
    - _Requirements: 11.2_
    - _参考: design-appendix/api-design-part3.md#5.3_
    - _预计时间: 1天_

- [ ] 13. 限流和配额
  - [ ] 13.1 实现限流系统
    - 集成slowapi库
    - 配置限流规则（100/hour普通用户，1000/hour高级用户）
    - 实现动态限流（根据用户角色）
    - 实现RateLimitExceeded处理
    - 添加单元测试
    - _Requirements: 11.4_
    - _参考: design-appendix/api-design-part3.md#6.1_
    - _预计时间: 1天_

  - [ ] 13.2 实现配额管理
    - 实现QuotaManager类
    - 实现check_quota方法
    - 实现consume_quota方法
    - 实现配额限制获取
    - 集成到chat端点
    - 添加单元测试
    - _Requirements: 11.4_
    - _参考: design-appendix/api-design-part3.md#6.2_
    - _预计时间: 1天_

- [ ] 14. API文档和客户端
  - [ ] 14.1 配置OpenAPI文档
    - 自定义OpenAPI schema
    - 配置安全方案（BearerAuth）
    - 添加API描述和示例
    - 验证Swagger UI和ReDoc
    - _Requirements: 10.7_
    - _参考: design-appendix/api-design-part3.md#7.1_
    - _预计时间: 0.5天_

  - [ ]* 14.2 实现Python客户端SDK（可选）
    - 实现DeepAgentClient类
    - 实现chat方法（同步）
    - 实现chat_stream方法（流式）
    - 添加使用示例
    - 添加单元测试
    - _Requirements: 10.8_
    - _参考: design-appendix/api-design-part3.md#8.1_
    - _预计时间: 1.5天_

---

## 阶段9：代码质量修复和迁移 (P0)

- [ ] 9.5 从 Polars 迁移到 Pandas（生产级别要求）
  - [ ] 9.5.1 迁移 DataProcessor 核心组件
    - **背景**: 当前 DataProcessor 使用 Polars，需要统一迁移到 Pandas
    - 更新 `data_processor/base.py`:
      - 将 `import polars as pl` 改为 `import pandas as pd`
      - 将所有 `pl.DataFrame` 改为 `pd.DataFrame`
      - 更新类型注解和文档字符串
    - 更新 `data_processor/processor.py`:
      - 将所有 `pl.DataFrame` 改为 `pd.DataFrame`
      - 更新数据验证逻辑：
        - `df.is_empty()` → `df.empty`
        - `df.null_count()` → `df.isnull().sum()`
        - `df.is_infinite()` → `np.isinf(df).any()`
        - `df.shape` 保持不变
        - `df.columns` 保持不变
      - 更新 Polars 特定的数据类型检查：
        - `pl.Float32, pl.Float64` → `np.float32, np.float64` 或使用 `pd.api.types.is_float_dtype()`
        - `pl.Int8, pl.Int16, pl.Int32, pl.Int64` → 使用 `pd.api.types.is_integer_dtype()`
    - _Requirements: 2.7_
    - _预计时间: 0.5天_
    - **优先级**: 🔴 P0 - 技术栈统一

  - [ ] 9.5.2 迁移所有数据处理器
    - 更新 `processors/yoy_processor.py`: Polars → Pandas
    - 更新 `processors/mom_processor.py`: Polars → Pandas
    - 更新 `processors/growth_rate_processor.py`: Polars → Pandas
    - 更新 `processors/percentage_processor.py`: Polars → Pandas
    - 更新 `processors/custom_processor.py`: Polars → Pandas
    - 关键 API 差异：
      - 数据选择: `df.select()` → `df[columns]` 或 `df.loc[]`
      - 数据过滤: `df.filter()` → `df[condition]` 或 `df.query()`
      - 分组聚合: `df.groupby().agg()` 语法类似但有细微差异
      - 列操作: `df.with_columns()` → `df.assign()` 或直接赋值
      - 排序: `df.sort()` → `df.sort_values()`
      - 连接: `df.join()` → `df.merge()` 或 `df.join()`
    - _Requirements: 2.7_
    - _预计时间: 1天_
    - **优先级**: 🔴 P0 - 核心功能

  - [ ] 9.5.3 更新数据模型
    - 更新 `models/query_result.py`:
      - QueryResult 的 data 字段类型从 `pl.DataFrame` 改为 `pd.DataFrame`
      - ProcessingResult 的 data 字段类型从 `pl.DataFrame` 改为 `pd.DataFrame`
      - 更新 `from_executor_result` 方法以创建 Pandas DataFrame
      - 更新序列化/反序列化逻辑（如果有）
    - 确保与其他组件的兼容性
    - _Requirements: 2.7_
    - _预计时间: 0.3天_
    - **优先级**: 🔴 P0 - 数据模型

  - [ ] 9.5.4 更新单元测试
    - 更新所有 DataProcessor 相关的单元测试
    - 将测试数据从 Polars DataFrame 改为 Pandas DataFrame
    - 更新断言以适配 Pandas API
    - 验证所有测试通过
    - _Requirements: 2.7_
    - _预计时间: 0.5天_
    - **优先级**: 🔴 P0 - 测试覆盖

  - [ ] 9.5.5 更新依赖和文档
    - 从 requirements.txt 移除 polars（如果存在）
    - 确保 pandas 和 numpy 在 requirements.txt 中
    - 更新 `process_query_result` 工具的文档（已经正确使用 "Pandas"）
    - 更新 DataProcessor 的 README 或文档
    - _Requirements: 2.7_
    - _预计时间: 0.2天_
    - **优先级**: 🟡 P1 - 文档更新

  - [ ] 9.5.6 修复其他代码问题
    - 修复 semantic_map_fields 导入问题:
      - 将 `from langchain.schema import Document` 改为 `from langchain_core.documents import Document`
      - 更新 semantic_mapper.py 中的所有相关导入
    - 验证所有单元测试通过（目标: 75/75）
    - _Requirements: 2.6, 8.1, 8.2_
    - _预计时间: 0.2天_
    - **优先级**: 🔴 P0 - 使用已弃用的API

  - [ ] 9.5.7 生产级别代码审查
    - 审查所有迁移后的代码
    - 确保没有 mock 数据或简化实现
    - 确保所有错误处理都是生产级别
    - 确保所有日志记录完整
    - 性能测试：对比 Polars 和 Pandas 的性能差异
    - 运行完整测试套件并确保通过
    - _预计时间: 0.5天_
    - **优先级**: 🟡 P1 - 质量保证
    - **注意**: 必须是生产级别代码，不能有简化或mock数据

---

## 阶段10：集成测试和优化 (P0)

- [ ] 10. 端到端测试
  - [ ] 10.1 编写端到端测试用例
    - 测试简单问题流程
    - 测试复杂问题流程
    - 测试多轮对话流程
    - 测试重规划机制
    - 测试流式输出（astream_events）
    - _Requirements: 所有需求_
    - _参考: design-appendix/deepagents-features.md#1-流式输出_
    - _预计时间: 2.5天_

  - [ ] 10.2 性能测试
    - 测试分析时间
    - 测试首次反馈时间
    - 测试 Token 使用量
    - 测试缓存命中率
    - 使用 PerformanceTrackingCallback 收集指标
    - 分析性能瓶颈
    - _Requirements: 13.1, 13.2, 13.3_
    - _参考: design-appendix/deepagents-features.md#5-性能监控和追踪_
    - _预计时间: 1.5天_

  - [ ] 10.3 错误恢复测试
    - 测试 LLM 错误恢复（重试机制）
    - 测试查询错误恢复（降级策略）
    - 测试网络错误恢复（超时处理）
    - 测试错误传播机制
    - _Requirements: 11.3_
    - _参考: design-appendix/deepagents-features.md#4-错误恢复机制_
    - _预计时间: 1.5天_

- [ ] 11. 性能优化
  - [ ] 11.1 优化并行查询执行
    - 分析瓶颈
    - 优化执行策略
    - 验证性能提升
    - _Requirements: 13.1_
    - _预计时间: 1天_

  - [ ] 11.2 优化缓存策略
    - 分析缓存命中率
    - 调优 TTL
    - 优化缓存 key 生成
    - _Requirements: 13.2_
    - _预计时间: 1天_

  - [ ] 11.3 优化 Prompt 长度
    - 分析 Token 使用
    - 精简提示词
    - 验证效果
    - _Requirements: 13.3_
    - _预计时间: 1天_

---

## 阶段10：代码质量修复和优化 (P0)

- [ ] 11.5 修复现有代码问题（生产级别要求）
  - [ ] 11.5.1 **迁移 DataProcessor 从 Polars 到 Pandas**
    - 更新 `data_processor/base.py`: 将 `import polars as pl` 改为 `import pandas as pd`
    - 更新 `data_processor/processor.py`: 所有 `pl.DataFrame` 改为 `pd.DataFrame`
    - 更新所有处理器（YoY, MoM, GrowthRate, Percentage, Custom）:
      - 将 Polars API 改为 Pandas API
      - `df.is_empty()` → `df.empty`
      - `df.null_count()` → `df.isna().sum()`
      - `df.is_infinite()` → `np.isinf(df)`
      - 列操作语法调整
    - 更新 `QueryResult` 和 `ProcessingResult` 模型中的数据类型
    - 更新所有相关的单元测试
    - 移除 polars 依赖，确保 pandas 已安装
    - 验证所有测试通过
    - _Requirements: 2.7_
    - _预计时间: 1.5天_
    - **优先级**: 🔴 P0 - 架构决策，必须使用 Pandas
    - **原因**: Pandas 生态更成熟，与现有数据科学工具链兼容性更好

  - [ ] 11.5.2 修复 process_query_result 工具文档
    - 确认工具文档说明使用 Pandas（在完成 11.5.1 后）
    - 更新所有示例代码
    - 验证单元测试通过
    - _Requirements: 2.7_
    - _预计时间: 0.2天_
    - **优先级**: 🔴 P0 - 依赖于 11.5.1

  - [ ] 11.5.3 修复 semantic_map_fields 导入问题
    - 将 `from langchain.schema import Document` 改为 `from langchain_core.documents import Document`
    - 更新 semantic_mapper.py 中的所有相关导入
    - 验证单元测试通过
    - _Requirements: 2.6, 8.1, 8.2_
    - _预计时间: 0.2天_
    - **优先级**: 🔴 P0 - 使用已弃用的API

  - [ ] 11.5.4 代码质量审查
    - 审查所有已实现的工具和中间件
    - 确保没有 mock 数据或简化实现
    - 确保所有错误处理都是生产级别
    - 确保所有日志记录完整
    - 运行完整测试套件并确保通过
    - _预计时间: 0.5天_
    - **优先级**: 🟡 P1 - 质量保证

---

## 阶段11：文档和部署 (P1)

- [ ] 12. 文档完善
  - [ ] 12.1 完善 API 文档
    - 编写 API 使用指南
    - 生成 OpenAPI 文档
    - 添加示例代码
    - _预计时间: 1天_

  - [ ] 12.2 编写部署指南
    - 编写环境配置指南
    - 编写部署步骤
    - 编写故障排查指南
    - _预计时间: 1天_

  - [ ] 12.3 编写用户使用手册
    - 编写功能介绍
    - 编写使用示例
    - 录制演示视频
    - _预计时间: 1天_

- [ ] 13. 部署准备
  - [ ] 13.1 配置生产环境
    - 配置环境变量
    - 配置数据库
    - 配置缓存
    - _预计时间: 0.5天_

  - [ ] 13.2 配置监控和日志
    - 配置性能监控
    - 配置错误日志
    - 配置告警
    - _预计时间: 1天_

  - [ ] 13.3 准备回滚方案
    - 备份现有系统
    - 准备回滚脚本
    - 测试回滚流程
    - _预计时间: 0.5天_

---

## 任务优先级说明

- **P0（必须完成）**：核心功能，必须在第一阶段完成
- **P1（推荐完成）**：重要功能，优先完成
- **P2（可选完成）**：增强功能，时间允许时完成
- **标记 * 的任务**：可选任务，不影响核心功能

---

## 预计时间线

| 阶段 | 任务 | 预计时间 | 变化 |
|------|------|---------|------|
| 阶段1 | 基础架构搭建 | 2天 | - |
| 阶段2 | 工具层实现 | 5.5天 | +0.5天（增加重试和降级） |
| 阶段3 | 中间件实现 | 2天 | - |
| 阶段4 | 子代理实现 | 7天 | +0.5天（增加 Store 集成） |
| 阶段5 | 渐进式洞察系统 | 14天 | +8天（详细设计补充） |
| 阶段6 | 主 Agent 编排 | 5天 | +1天（增加监控和 Context） |
| 阶段7 | 缓存系统优化 | 9天 | +6天（详细设计补充） |
| 阶段8 | API 层实现 | 13天 | +8.5天（详细设计补充） |
| 阶段9 | 集成测试和优化 | 7.5天 | +1.5天（增加特性测试） |
| 阶段10 | 代码质量修复和优化 | 2.4天 | +2.4天（Polars→Pandas迁移） |
| 阶段11 | 文档和部署 | 4天 | - |
| **总计** | | **71.4天（约10.5周）** | **+28.4天** |

**说明**：
1. 增加的时间主要来自详细设计文档的补充：
   - 渐进式洞察系统：从6天增加到14天（+8天）
   - 缓存系统：从3天增加到9天（+6天）
   - API层：从4.5天增加到13天（+8.5天）
   - **Polars→Pandas迁移：新增2.4天**
2. 这些增加的时间反映了更详细和完整的实现要求
3. 总工期从7周增加到10.5周，更符合实际开发需求
4. **架构决策**：使用 Pandas 而非 Polars，因为 Pandas 生态更成熟，与现有工具链兼容性更好

---

## 风险和缓解措施

### 风险1：DeepAgents 框架学习曲线
- **缓解**：先完成简单的 Agent，逐步熟悉框架
- **缓解**：参考官方文档和示例代码

### 风险2：现有组件兼容性问题
- **缓解**：100% 复用现有组件，只封装为工具
- **缓解**：保持现有接口不变

### 风险3：性能不达标
- **缓解**：实施四层缓存架构
- **缓解**：实施并行查询执行
- **缓解**：实施渐进式分析

### 风险4：测试覆盖不足
- **缓解**：每个组件都添加单元测试
- **缓解**：编写完整的端到端测试

---

**文档版本**: v1.0  
**最后更新**: 2025-01-15


---

## 🔴 紧急修复任务 (P0 - 必须立即完成)

### 代码质量和技术栈统一

- [x] FIX-1. 将 DataProcessor 从 Polars 迁移到 Pandas（生产级别要求）
  - [x] FIX-1.1 更新 DataProcessor 基类
    - 文件：`tableau_assistant/src/components/data_processor/base.py`
    - 将 `import polars as pl` 改为 `import pandas as pd`
    - 将所有 `pl.DataFrame` 改为 `pd.DataFrame`
    - 更新 Polars 特有方法为 Pandas 等价方法：
      - `df.is_empty()` → `df.empty`
      - `pl.col("column")` → `df["column"]` 或 `df.column`
      - 其他 Polars API → Pandas API
    - _预计时间: 0.3天_
    - **优先级**: 🔴 P0 - 阻塞性问题

  - [x] FIX-1.2 更新所有 DataProcessor 实现类
    - 检查并更新所有继承 ProcessorBase 的类
    - 确保所有数据处理逻辑使用 Pandas DataFrame
    - 更新所有测试用例
    - _预计时间: 0.2天_
    - **优先级**: 🔴 P0 - 阻塞性问题

  - [x] FIX-1.3 更新 process_query_result 工具文档
    - 文件：`tableau_assistant/src/deepagents/tools/process_query_result.py`
    - 确保文档说明正确：使用 Pandas 而不是 Polars
    - 验证工具功能正常
    - 运行单元测试确保通过
    - _Requirements: 2.7_
    - _预计时间: 0.1天_
    - **优先级**: 🔴 P0 - 文档与实现一致性

- [x] FIX-2. 修复 semantic_map_fields 导入问题（生产级别要求）
  - [x] FIX-2.1 更新 langchain 导入
    - 文件：`tableau_assistant/src/semantic_mapping/semantic_mapper.py`
    - 将 `from langchain.schema import Document` 改为 `from langchain_core.documents import Document`
    - 检查是否有其他已弃用的 langchain 导入
    - _预计时间: 0.1天_
    - **优先级**: 🔴 P0 - 使用已弃用的API

  - [x] FIX-2.2 验证修复
    - 运行 semantic_map_fields 相关的所有单元测试
    - 确保所有测试通过
    - _Requirements: 2.6, 8.1, 8.2_
    - _预计时间: 0.1天_
    - **优先级**: 🔴 P0 - 验证修复

- [ ] FIX-3. 代码质量全面审查（生产级别要求）
  - [ ] FIX-3.1 审查所有已实现的工具
    - 检查 8 个工具的实现质量
    - 确保没有 mock 数据或简化实现
    - 确保所有错误处理都是生产级别
    - 确保所有日志记录完整和有意义
    - 确保所有类型注解完整
    - _预计时间: 0.3天_
    - **优先级**: 🟡 P1 - 质量保证

  - [ ] FIX-3.2 审查所有已实现的中间件
    - 检查 3 个中间件的实现质量
    - 确保没有 mock 数据或简化实现
    - 确保所有错误处理都是生产级别
    - 确保所有日志记录完整和有意义
    - _预计时间: 0.2天_
    - **优先级**: 🟡 P1 - 质量保证

  - [ ] FIX-3.3 运行完整测试套件
    - 运行所有单元测试
    - 目标：100% 测试通过率
    - 修复所有失败的测试
    - 生成测试覆盖率报告
    - _预计时间: 0.2天_
    - **优先级**: 🟡 P1 - 质量验证

---

## 📋 生产级别代码质量标准（所有未来任务必须遵守）

### 强制要求
1. **禁止 Mock 数据**：所有实现必须使用真实的组件和数据流
2. **完整错误处理**：所有可能的异常都必须被捕获和处理
3. **详细日志记录**：关键操作必须有 INFO 级别日志，错误必须有 ERROR 级别日志
4. **完整类型注解**：所有函数参数和返回值必须有类型注解
5. **生产级别文档**：所有工具和类必须有详细的 docstring，包含参数说明、返回值说明和使用示例
6. **单元测试覆盖**：所有新功能必须有对应的单元测试
7. **性能考虑**：必须考虑性能优化，避免不必要的计算和内存占用

### 代码审查检查清单
- [ ] 是否有 mock 数据或简化实现？
- [ ] 是否有完整的错误处理？
- [ ] 是否有详细的日志记录？
- [ ] 是否有完整的类型注解？
- [ ] 是否有详细的文档说明？
- [ ] 是否有单元测试？
- [ ] 是否考虑了性能优化？

---
