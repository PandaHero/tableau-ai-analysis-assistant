# 需求文档：Analytics Assistant 深度代码审查与功能分析

## 引言

本文档定义了对 Analytics Assistant 项目进行系统性深度代码审查的需求。该项目是一个基于 LangGraph 的智能 BI 分析助手，采用多 Agent 协作架构。审查目标是从整体架构到函数级别进行逐层深入分析，识别代码质量问题、性能瓶颈、安全隐患和编码规范违规，最终生成结构化的审查报告和优化路线图。

## 术语表

- **Code_Review_System**: 代码审查系统，负责逐模块分析代码并生成审查报告
- **Review_Report**: 审查报告文档，位于 `analytics_assistant/docs/deep_code_review.md`
- **Module_Section**: 审查报告中针对单个模块的独立章节
- **Finding**: 审查发现项，包含问题描述、严重程度、代码位置、优化建议
- **Severity_Level**: 问题严重程度，分为 Critical、High、Medium、Low 四级
- **Quality_Score**: 模块质量评分（0-100），基于多维度加权计算
- **Optimization_Roadmap**: 优化路线图，按优先级和工作量排列的改进计划

## 需求

### 需求 1：审查框架与评分标准

**用户故事：** 作为代码审查者，我希望有统一的审查框架和评分标准，以便对所有模块进行一致性评估。

#### 验收标准

1. THE Code_Review_System SHALL 在 Review_Report 开头定义包含功能完整性、代码质量、性能、错误处理、可维护性、安全性、测试覆盖七个维度的评分标准（每维度 0-100 分）
2. THE Code_Review_System SHALL 为每个 Module_Section 生成基于七个维度的 Quality_Score 汇总表
3. THE Code_Review_System SHALL 将每个 Finding 标记为 Critical、High、Medium、Low 四个 Severity_Level 之一
4. THE Code_Review_System SHALL 在 Review_Report 中使用统一的模板格式：模块概述、文件清单、类与函数分析、问题列表、优化建议

### 需求 2：Core 层深度审查

**用户故事：** 作为代码审查者，我希望深入审查 Core 层（interfaces.py、exceptions.py、schemas/）的所有组件，以确保核心接口和数据模型的设计质量。

#### 验收标准

1. WHEN 审查 `core/interfaces.py` THEN THE Code_Review_System SHALL 逐个分析每个抽象基类的方法签名、参数类型注解、返回值类型注解、抽象层次是否合理
2. WHEN 审查 `core/exceptions.py` THEN THE Code_Review_System SHALL 分析异常类的继承层次、异常消息是否包含上下文信息、是否覆盖所有错误场景
3. WHEN 审查 `core/schemas/` 目录 THEN THE Code_Review_System SHALL 逐文件分析每个 Pydantic 模型的字段定义、验证器（validator）、序列化配置、字段命名一致性
4. THE Code_Review_System SHALL 检查 Core 层是否存在对上层模块（agents、orchestration、platform）的反向依赖
5. THE Code_Review_System SHALL 检查 Core 层的数据模型是否存在字段重复定义或语义重叠

### 需求 3：Infra 配置与存储层深度审查

**用户故事：** 作为代码审查者，我希望深入审查 Infra 层的配置管理和存储模块，以确保基础设施的稳定性。

#### 验收标准

1. WHEN 审查 `infra/config/` THEN THE Code_Review_System SHALL 分析配置加载流程、单例模式实现、环境变量展开逻辑、配置缺失时的降级处理
2. WHEN 审查 `infra/storage/` THEN THE Code_Review_System SHALL 分析 KV 存储的读写实现、缓存淘汰策略、并发安全性、连接管理
3. THE Code_Review_System SHALL 检查配置模块是否存在硬编码的默认值未在 app.yaml 中声明的情况
4. THE Code_Review_System SHALL 检查存储模块是否存在未关闭的数据库连接或文件句柄

### 需求 4：Infra AI 与 RAG 层深度审查

**用户故事：** 作为代码审查者，我希望深入审查 AI 模型管理和 RAG 检索模块，以确保 AI 调用的可靠性和检索质量。

#### 验收标准

1. WHEN 审查 `infra/ai/` THEN THE Code_Review_System SHALL 分析 LLM 封装的模型注册、路由选择、重试机制、超时控制、流式输出处理
2. WHEN 审查 `infra/rag/` THEN THE Code_Review_System SHALL 分析索引创建与复用逻辑、检索策略实现（向量检索、混合检索）、重排序算法、文档分块策略
3. THE Code_Review_System SHALL 检查 AI 模块是否存在未处理的 API 调用异常或超时
4. THE Code_Review_System SHALL 检查 RAG 模块是否存在索引重复创建、未检查索引存在性的问题
5. WHEN 审查 `infra/seeds/` THEN THE Code_Review_System SHALL 分析种子数据的组织结构、加载性能、数据完整性

### 需求 5：Agent 基础设施与核心 Agent 深度审查

**用户故事：** 作为代码审查者，我希望深入审查 Agent 基础设施和核心 Agent（SemanticParser、FieldMapper、FieldSemantic），以确保核心业务流程的正确性。

#### 验收标准

1. WHEN 审查 `agents/base/` THEN THE Code_Review_System SHALL 分析 Node 基类的生命周期管理、中间件运行器的执行链、上下文传递机制
2. WHEN 审查 `agents/semantic_parser/` THEN THE Code_Review_System SHALL 逐个分析 graph.py 中定义的每个节点函数、state.py 中的状态字段、components/ 下的每个业务组件类和方法
3. WHEN 审查 `agents/semantic_parser/` THEN THE Code_Review_System SHALL 分析 11 阶段流程中每个阶段的输入输出、状态转换条件、错误恢复路径
4. WHEN 审查 `agents/field_mapper/` THEN THE Code_Review_System SHALL 分析两阶段 RAG 检索的实现、相似度计算逻辑、候选字段排序算法
5. WHEN 审查 `agents/field_semantic/` THEN THE Code_Review_System SHALL 分析种子匹配逻辑、LLM 批量推断的批次划分、结果合并策略

### 需求 6：辅助 Agent 深度审查

**用户故事：** 作为代码审查者，我希望审查辅助 Agent（Insight、Replanner），以确保辅助功能的实现质量。

#### 验收标准

1. WHEN 审查 `agents/insight/` THEN THE Code_Review_System SHALL 分析洞察生成的 Prompt 设计、数据分析逻辑、输出格式化
2. WHEN 审查 `agents/replanner/` THEN THE Code_Review_System SHALL 分析重规划触发条件、错误分类逻辑、重试策略、状态回滚机制
3. THE Code_Review_System SHALL 检查辅助 Agent 是否正确复用 agents/base/ 提供的基础设施

### 需求 7：Orchestration 与 API 层深度审查

**用户故事：** 作为代码审查者，我希望深入审查工作流编排和 API 层，以确保端到端流程的正确性和 API 接口的安全性。

#### 验收标准

1. WHEN 审查 `orchestration/workflow/` THEN THE Code_Review_System SHALL 分析 WorkflowContext 的生命周期管理、工作流执行器的调度逻辑、回调机制的实现
2. WHEN 审查 `api/main.py` THEN THE Code_Review_System SHALL 分析 FastAPI 应用配置、中间件注册、CORS 设置、异常处理器
3. WHEN 审查 `api/routers/` THEN THE Code_Review_System SHALL 逐个分析每个路由的请求验证、响应格式、错误处理、认证检查
4. WHEN 审查 `api/models/` THEN THE Code_Review_System SHALL 分析请求模型和响应模型的字段验证规则
5. THE Code_Review_System SHALL 检查 API 层是否存在未验证的用户输入、缺失的认证检查、不安全的 CORS 配置

### 需求 8：Platform 层深度审查

**用户故事：** 作为代码审查者，我希望深入审查 Platform 层的 Tableau 适配器实现，以确保与外部系统集成的安全性和可靠性。

#### 验收标准

1. WHEN 审查 `platform/base.py` THEN THE Code_Review_System SHALL 分析平台注册表的设计、工厂方法的实现、接口抽象的完整性
2. WHEN 审查 `platform/tableau/` THEN THE Code_Review_System SHALL 逐文件分析认证流程、API 客户端实现、查询构建器、数据转换逻辑
3. THE Code_Review_System SHALL 检查 Tableau 适配器是否存在 SQL 注入风险、令牌泄露风险、SSL 验证绕过
4. THE Code_Review_System SHALL 评估添加新平台适配器（如 Power BI）的扩展难度，识别需要修改的接口

### 需求 9：编码规范符合性检查

**用户故事：** 作为代码审查者，我希望检查所有代码是否符合项目编码规范（coding-standards.md），以确保代码一致性。

#### 验收标准

1. THE Code_Review_System SHALL 扫描所有 Python 文件，识别函数内部的延迟导入（违反规则 7.2）
2. THE Code_Review_System SHALL 扫描所有 Python 文件，识别硬编码的阈值、超时、策略参数（违反规则 2.1、2.2）
3. THE Code_Review_System SHALL 检查所有 Prompt 定义是否位于 `prompts/` 目录下（违反规则 3.3）
4. THE Code_Review_System SHALL 检查所有 Pydantic 模型是否位于 `schemas/` 目录下（违反规则 4.1）
5. THE Code_Review_System SHALL 扫描所有异常捕获，识别裸异常捕获（无日志、无上下文，违反规则 14.2）
6. THE Code_Review_System SHALL 扫描所有 async 函数，识别阻塞调用（如 `time.sleep`、`requests.get`，违反规则 16.3）
7. THE Code_Review_System SHALL 扫描所有类型注解，识别小写泛型用法（如 `list[str]`，违反规则 17.4）
8. THE Code_Review_System SHALL 检查模块间导入方向是否符合依赖方向图（违反规则 12A.2）
9. THE Code_Review_System SHALL 识别逐个调用外部 API 的代码（违反规则 23.2）
10. THE Code_Review_System SHALL 识别未检查索引存在性就创建 RAG 索引的代码（违反规则 23.3）

### 需求 10：性能瓶颈识别

**用户故事：** 作为代码审查者，我希望识别代码中的性能瓶颈，并提供具体的优化建议。

#### 验收标准

1. THE Code_Review_System SHALL 识别串行执行的独立异步操作，建议使用 `asyncio.gather` 并发执行
2. THE Code_Review_System SHALL 识别未使用缓存的重复计算或重复 API 调用
3. THE Code_Review_System SHALL 识别未限制并发度的批量异步操作，建议使用 `asyncio.Semaphore`
4. THE Code_Review_System SHALL 识别低效的数据结构使用（如在列表中进行查找操作，应使用字典或集合）
5. THE Code_Review_System SHALL 识别大对象的不必要深拷贝
6. WHEN 发现性能问题 THEN THE Code_Review_System SHALL 在 Review_Report 中提供优化前后的代码对比示例

### 需求 11：安全性分析

**用户故事：** 作为代码审查者，我希望识别代码中的安全漏洞和安全隐患。

#### 验收标准

1. THE Code_Review_System SHALL 扫描所有文件，识别硬编码的 API Key、密码、Token
2. THE Code_Review_System SHALL 检查所有查询构建逻辑，识别 SQL 注入或 VizQL 注入风险
3. THE Code_Review_System SHALL 检查所有 API 端点，识别缺失的输入验证
4. THE Code_Review_System SHALL 检查日志输出，识别可能泄露敏感信息的日志语句
5. THE Code_Review_System SHALL 检查 SSL 配置，识别禁用 SSL 验证的代码

### 需求 12：跨模块架构分析

**用户故事：** 作为代码审查者，我希望从全局视角分析模块间的架构关系，识别系统级问题。

#### 验收标准

1. THE Code_Review_System SHALL 绘制模块间的实际依赖关系图，与编码规范中定义的依赖方向图进行对比
2. THE Code_Review_System SHALL 识别循环依赖链，列出涉及的具体文件和导入语句
3. THE Code_Review_System SHALL 识别职责重叠的模块或类，建议合并或重新划分
4. THE Code_Review_System SHALL 识别跨模块重复实现的功能，建议提取到公共模块
5. THE Code_Review_System SHALL 评估系统的整体可扩展性，识别添加新 Agent 或新平台的阻塞点

### 需求 13：可维护性评估

**用户故事：** 作为代码审查者，我希望评估代码的可维护性，识别难以维护的代码段。

#### 验收标准

1. THE Code_Review_System SHALL 标记超过 50 行的函数和超过 500 行的类
2. THE Code_Review_System SHALL 标记圈复杂度超过 10 的函数
3. THE Code_Review_System SHALL 标记嵌套层次超过 4 层的代码块
4. THE Code_Review_System SHALL 标记参数超过 5 个的函数
5. THE Code_Review_System SHALL 标记缺失 Docstring 的公开函数和公开类
6. THE Code_Review_System SHALL 标记使用魔法数字（未定义为常量的数字字面量）的代码

### 需求 14：测试覆盖分析

**用户故事：** 作为代码审查者，我希望评估现有测试的覆盖情况和质量。

#### 验收标准

1. THE Code_Review_System SHALL 列出每个模块对应的测试文件，识别缺失测试文件的模块
2. THE Code_Review_System SHALL 识别缺失单元测试的核心公开函数
3. THE Code_Review_System SHALL 识别测试中的过度 Mock（Mock 了不应该 Mock 的内部逻辑）
4. THE Code_Review_System SHALL 评估属性测试（Hypothesis）的使用情况，识别适合添加属性测试的函数
5. THE Code_Review_System SHALL 识别缺失的集成测试场景

### 需求 15：审查报告与优化路线图

**用户故事：** 作为代码审查者，我希望生成结构化的审查报告和可执行的优化路线图。

#### 验收标准

1. THE Code_Review_System SHALL 将完整审查报告写入 `analytics_assistant/docs/deep_code_review.md`
2. WHEN 生成报告 THEN THE Code_Review_System SHALL 按模块组织章节，每个模块包含：概述、文件清单、质量评分表、问题列表（按严重程度排序）、优化建议
3. WHEN 生成报告 THEN THE Code_Review_System SHALL 在报告末尾生成优化路线图，按 P0-P3 优先级排列改进任务
4. WHEN 生成报告 THEN THE Code_Review_System SHALL 在报告开头生成执行摘要，包含总体质量评分、关键发现数量、Top 10 高优先级问题
5. THE Code_Review_System SHALL 为优化路线图中的每个任务标注预估工作量（小时或人天）
