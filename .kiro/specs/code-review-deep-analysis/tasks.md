# 实施计划：Analytics Assistant 深度代码审查与功能分析

## 概述

按照自底向上的分层策略，逐模块深入审查代码，最终生成结构化审查报告 `analytics_assistant/docs/deep_code_review.md`。每个任务读取指定模块的所有文件，进行函数/类级别分析，将审查发现写入报告文档。

## 任务

- [x] 1. 初始化审查报告框架
  - 创建 `analytics_assistant/docs/deep_code_review.md` 文件
  - 写入报告标题、目录结构、审查框架说明（评分标准、严重程度定义、审查维度）
  - 写入执行摘要占位章节（后续汇总时填充）
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 15.1, 15.2_

- [x] 2. Phase 1: Core 层深度审查
  - [x] 2.1 审查 `core/interfaces.py` 和 `core/exceptions.py`
    - 读取两个文件的完整代码
    - 逐个分析每个抽象基类：方法签名、参数类型注解、返回值类型注解、抽象层次
    - 逐个分析每个异常类：继承层次、异常消息完整性、使用场景
    - 检查是否存在对上层模块的反向依赖
    - 将分析结果写入报告的 Core 模块章节
    - _Requirements: 2.1, 2.2, 2.4_

  - [x] 2.2 审查 `core/schemas/` 全部 7 个数据模型文件
    - 读取 schemas/ 下所有文件：computations.py, data_model.py, enums.py, execute_result.py, field_candidate.py, fields.py, filters.py, validation.py
    - 逐文件分析每个 Pydantic 模型：字段定义、验证器、序列化配置、字段命名一致性
    - 检查是否存在字段重复定义或语义重叠
    - 将分析结果追加到报告的 Core 模块章节
    - 生成 Core 模块质量评分表
    - _Requirements: 2.3, 2.5_

- [x] 3. Phase 1: Infra 配置与存储层深度审查
  - [x] 3.1 审查 `infra/config/config_loader.py`
    - 读取配置加载器完整代码
    - 分析配置加载流程、单例模式实现、环境变量展开逻辑、配置缺失时的降级处理
    - 检查是否存在硬编码的默认值未在 app.yaml 中声明
    - 将分析结果写入报告的 Infra/Config 模块章节
    - _Requirements: 3.1, 3.3_

  - [x] 3.2 审查 `infra/storage/` 全部 5 个文件
    - 读取 storage/ 下所有文件：cache.py, kv_store.py, repository.py, store_factory.py, vector_store.py
    - 分析 KV 存储的读写实现、缓存淘汰策略、并发安全性、连接管理
    - 检查是否存在未关闭的数据库连接或文件句柄
    - 将分析结果写入报告的 Infra/Storage 模块章节
    - 生成 Infra/Config 和 Infra/Storage 模块质量评分表
    - _Requirements: 3.2, 3.4_

- [x] 4. Checkpoint - Phase 1 完成
  - 确认 Phase 1 的所有模块审查结果已写入报告
  - 确认 Core、Infra/Config、Infra/Storage 三个模块都有质量评分表
  - Ensure all findings are recorded, ask the user if questions arise.

- [x] 5. Phase 2: Infra AI 模块深度审查
  - [x] 5.1 审查 `infra/ai/` 全部 7 个文件
    - 读取 ai/ 下所有文件：custom_llm.py, model_factory.py, model_manager.py, model_persistence.py, model_registry.py, model_router.py, models.py
    - 分析模型注册机制、路由选择逻辑、重试机制、超时控制、流式输出处理
    - 检查是否存在未处理的 API 调用异常或超时
    - 将分析结果写入报告的 Infra/AI 模块章节
    - 生成 Infra/AI 模块质量评分表
    - _Requirements: 4.1, 4.3_

- [x] 6. Phase 2: Infra RAG 模块深度审查
  - [x] 6.1 审查 `infra/rag/` 核心文件（service.py, retrieval_service.py, retriever.py, index_manager.py）
    - 读取 RAG 服务核心文件
    - 分析索引创建与复用逻辑、检索策略实现（向量检索、混合检索）
    - 检查是否存在索引重复创建、未检查索引存在性的问题
    - _Requirements: 4.2, 4.4_

  - [x] 6.2 审查 `infra/rag/` 辅助文件（embedding_service.py, reranker.py, similarity.py, models.py, exceptions.py, schemas/, prompts/）
    - 读取 RAG 辅助文件
    - 分析重排序算法、向量存储、相似度计算、异常定义
    - 将全部 RAG 分析结果写入报告的 Infra/RAG 模块章节
    - 生成 Infra/RAG 模块质量评分表
    - _Requirements: 4.2_

- [x] 7. Phase 2: Infra Seeds 模块审查
  - [x] 7.1 审查 `infra/seeds/` 全部文件
    - 读取 seeds/ 下所有文件：computation.py, dimension.py, measure.py, keywords/, patterns/
    - 分析数据组织结构、数据加载性能、数据完整性
    - 将分析结果写入报告的 Infra/Seeds 模块章节
    - 生成 Infra/Seeds 模块质量评分表
    - _Requirements: 4.5_

- [x] 8. Checkpoint - Phase 2 完成
  - 确认 Phase 2 的所有模块审查结果已写入报告
  - 确认 Infra/AI、Infra/RAG、Infra/Seeds 三个模块都有质量评分表
  - Ensure all findings are recorded, ask the user if questions arise.

- [x] 9. Phase 3: Agent 基础设施审查
  - [x] 9.1 审查 `agents/base/` 全部文件
    - 读取 base/ 下所有文件：node.py, middleware_runner.py, context.py, middleware/
    - 分析 Node 基类的生命周期管理、中间件运行器的执行链、上下文传递机制
    - 将分析结果写入报告的 Agents/Base 模块章节
    - 生成 Agents/Base 模块质量评分表
    - _Requirements: 5.1_

- [x] 10. Phase 3: Semantic Parser Agent 深度审查（P0 核心流程）
  - [x] 10.1 审查 `semantic_parser/graph.py` 和 `semantic_parser/state.py`
    - 读取图定义和状态定义
    - 分析 11 阶段流程的节点定义、状态转换条件、条件边
    - 分析 State 中的字段定义、类型注解、默认值
    - _Requirements: 5.2, 5.3_

  - [x] 10.2 审查 `semantic_parser/components/` 前 8 个组件
    - 读取：dynamic_schema_builder.py, error_corrector.py, feature_cache.py, feature_extractor.py, feedback_learner.py, few_shot_manager.py, field_retriever.py, field_value_cache.py
    - 逐个分析每个组件类的职责、方法实现、错误处理、性能
    - _Requirements: 5.2_

  - [x] 10.3 审查 `semantic_parser/components/` 后 8 个组件
    - 读取：filter_validator.py, history_manager.py, intent_router.py, output_validator.py, query_cache.py, rule_prefilter.py, semantic_cache.py, semantic_understanding.py
    - 逐个分析每个组件类的职责、方法实现、错误处理、性能
    - _Requirements: 5.2_

  - [x] 10.4 审查 `semantic_parser/prompts/` 和 `semantic_parser/schemas/`
    - 读取 prompts/ 下 4 个文件和 schemas/ 下 10 个文件
    - 分析 Prompt 模板设计、数据模型定义
    - 将全部 Semantic Parser 分析结果写入报告
    - 生成 Semantic Parser 模块质量评分表
    - _Requirements: 5.2, 5.3_

- [x] 11. Phase 3: Field Mapper Agent 深度审查（P0 核心流程）
  - [x] 11.1 审查 `field_mapper/` 全部文件
    - 读取 field_mapper/ 下所有文件：node.py, prompts/prompt.py, schemas/config.py, schemas/mapping.py
    - 分析两阶段 RAG 检索实现、相似度计算逻辑、候选字段排序算法、缓存策略
    - 将分析结果写入报告的 Field Mapper 模块章节
    - 生成 Field Mapper 模块质量评分表
    - _Requirements: 5.4_

- [x] 12. Phase 3: Field Semantic Agent 深度审查
  - [x] 12.1 审查 `field_semantic/` 全部文件
    - 读取 field_semantic/ 下所有文件：inference.py, utils.py, components/（4 个 Mixin）, prompts/prompt.py, schemas/output.py
    - 分析种子匹配逻辑、LLM 批量推断的批次划分、结果合并策略
    - 将分析结果写入报告的 Field Semantic 模块章节
    - 生成 Field Semantic 模块质量评分表
    - _Requirements: 5.5_

- [x] 13. Phase 3: 辅助 Agent 审查
  - [x] 13.1 审查 `insight/` 全部文件
    - 读取 insight/ 下所有文件：graph.py, components/（3 文件）, prompts/, schemas/
    - 分析洞察生成的 Prompt 设计、数据分析逻辑、输出格式化
    - 将分析结果写入报告的 Insight 模块章节
    - 生成 Insight 模块质量评分表
    - _Requirements: 6.1_

  - [x] 13.2 审查 `replanner/` 全部文件
    - 读取 replanner/ 下所有文件：graph.py, prompts/, schemas/
    - 分析重规划触发条件、错误分类逻辑、重试策略、状态回滚机制
    - 检查是否正确复用 agents/base/ 基础设施
    - 将分析结果写入报告的 Replanner 模块章节
    - 生成 Replanner 模块质量评分表
    - _Requirements: 6.2, 6.3_

- [x] 14. Checkpoint - Phase 3 完成
  - 确认 Phase 3 的所有 Agent 模块审查结果已写入报告
  - 确认 6 个 Agent 模块都有质量评分表
  - Ensure all findings are recorded, ask the user if questions arise.

- [x] 15. Phase 4: Orchestration 模块深度审查
  - [x] 15.1 审查 `orchestration/workflow/` 全部文件
    - 读取 workflow/ 下所有文件：context.py, executor.py, callbacks.py
    - 分析 WorkflowContext 的生命周期管理、工作流执行器的调度逻辑、回调机制
    - 将分析结果写入报告的 Orchestration 模块章节
    - 生成 Orchestration 模块质量评分表
    - _Requirements: 7.1_

- [x] 16. Phase 4: Platform 模块深度审查
  - [x] 16.1 审查 `platform/base.py` 和 `platform/tableau/` 全部文件
    - 读取 platform/ 下所有文件：base.py, tableau/（adapter.py, auth.py, client.py, data_loader.py, query_builder.py, ssl_utils.py）
    - 分析平台注册表设计、认证流程、API 客户端实现、查询构建器、数据转换逻辑
    - 检查 SQL/VizQL 注入风险、令牌泄露风险、SSL 验证绕过
    - 评估添加新平台适配器的扩展难度
    - 将分析结果写入报告的 Platform 模块章节
    - 生成 Platform 模块质量评分表
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

- [x] 17. Phase 4: API 层深度审查
  - [x] 17.1 审查 `api/` 全部文件
    - 读取 api/ 下所有文件：main.py, dependencies.py, middleware.py, models/（5 文件）, routers/（5 文件）, utils/sse.py
    - 分析 FastAPI 应用配置、中间件注册、CORS 设置、异常处理器
    - 逐个分析每个路由的请求验证、响应格式、错误处理、认证检查
    - 分析请求模型和响应模型的字段验证规则
    - 检查未验证的用户输入、缺失的认证检查、不安全的 CORS 配置
    - 将分析结果写入报告的 API 模块章节
    - 生成 API 模块质量评分表
    - _Requirements: 7.2, 7.3, 7.4, 7.5_

- [x] 18. Checkpoint - Phase 4 完成
  - 确认 Phase 4 的所有模块审查结果已写入报告
  - 确认 Orchestration、Platform、API 三个模块都有质量评分表
  - Ensure all findings are recorded, ask the user if questions arise.

- [x] 19. Phase 5: 编码规范符合性全局扫描
  - [x] 19.1 扫描延迟导入、硬编码配置、Prompt/Schema 位置
    - 使用 grep 搜索所有 Python 文件中函数内部的 import 语句
    - 搜索硬编码的阈值、超时等数字字面量
    - 检查 Prompt 定义是否都在 prompts/ 目录下
    - 检查 Pydantic 模型是否都在 schemas/ 目录下
    - 将违规项写入报告的编码规范检查章节
    - _Requirements: 9.1, 9.2, 9.3, 9.4_

  - [x] 19.2 扫描异常处理、异步阻塞、类型注解、依赖方向
    - 搜索裸异常捕获（except 块无日志无 raise）
    - 搜索 async 函数中的阻塞调用（time.sleep, requests.get 等）
    - 搜索小写泛型用法（list[, dict[, tuple[, set[）
    - 分析模块间导入方向，检查违反依赖方向图的导入
    - 搜索逐个调用外部 API 的模式
    - 检查 RAG 索引创建是否先检查存在性
    - 将违规项追加到报告的编码规范检查章节
    - _Requirements: 9.5, 9.6, 9.7, 9.8, 9.9, 9.10_

- [x] 20. Phase 5: 跨模块架构分析
  - [x] 20.1 依赖关系分析与架构评估
    - 绘制模块间的实际依赖关系图（Mermaid 格式）
    - 与编码规范中定义的依赖方向图对比，识别违规
    - 识别循环依赖链
    - 识别职责重叠的模块或类
    - 识别跨模块重复实现的功能
    - 评估系统整体可扩展性
    - 将分析结果写入报告的跨模块架构分析章节
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5_

- [x] 21. Phase 5: 性能与安全汇总分析
  - [x] 21.1 性能瓶颈汇总
    - 汇总各模块审查中发现的性能问题
    - 补充全局性能分析：串行异步操作、缺失缓存、未限制并发、低效数据结构
    - 为每个性能问题提供优化前后的代码对比示例
    - 将分析结果写入报告的性能瓶颈汇总章节
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_

  - [x] 21.2 安全性汇总
    - 汇总各模块审查中发现的安全问题
    - 补充全局安全扫描：硬编码密钥、注入风险、输入验证、日志泄露、SSL 配置
    - 将分析结果写入报告的安全性汇总章节
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_

- [x] 22. Phase 5: 可维护性与测试覆盖分析
  - [x] 22.1 可维护性指标汇总
    - 汇总各模块中超过 50 行的函数、超过 500 行的类
    - 汇总圈复杂度超过 10 的函数
    - 汇总嵌套超过 4 层的代码、参数超过 5 个的函数
    - 汇总缺失 Docstring 的公开函数和类
    - 汇总魔法数字使用
    - 将分析结果写入报告的可维护性评估章节
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6_

  - [x] 22.2 测试覆盖分析
    - 对比源代码目录和测试目录，列出每个模块的测试文件
    - 识别缺失测试文件的模块
    - 识别缺失单元测试的核心公开函数
    - 评估属性测试（Hypothesis）的使用情况
    - 识别缺失的集成测试场景
    - 将分析结果写入报告的测试覆盖分析章节
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5_

- [x] 23. Phase 5: 生成执行摘要与优化路线图
  - [x] 23.1 填充执行摘要
    - 计算总体质量评分（所有模块加权平均）
    - 统计关键发现数量（按 Critical/High/Medium/Low 分类）
    - 列出 Top 10 高优先级问题
    - 填充报告开头的执行摘要章节
    - _Requirements: 15.4_

  - [x] 23.2 生成优化路线图
    - 按 P0-P3 优先级整理所有优化建议
    - P0: SemanticParser 和 FieldMapper 相关问题
    - P1: RAG、Config、Storage 相关问题
    - P2: Insight、Replanner 相关问题
    - P3: API 层和平台集成相关问题
    - 为每个优化任务标注预估工作量（小时或人天）
    - 将优化路线图写入报告末尾
    - _Requirements: 15.3, 15.5_

- [x] 24. 最终 Checkpoint - 审查报告完成
  - 确认 `analytics_assistant/docs/deep_code_review.md` 包含所有模块的审查结果
  - 确认执行摘要已填充
  - 确认优化路线图已生成
  - 确认所有 Finding 都有严重程度标记
  - 确认所有模块都有质量评分表
  - Ensure the report is complete, ask the user if questions arise.

## 说明

- 所有任务的输出是**审查发现和优化建议**，写入 `analytics_assistant/docs/deep_code_review.md`
- 任务不涉及修改项目源代码
- 每个 Phase 结束后有 Checkpoint，确保审查结果完整
- Semantic Parser 和 Field Mapper 作为 P0 核心流程，审查最为深入
- 审查报告使用中文编写
