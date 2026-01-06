# Agent 优化需求文档

## 背景

当前 Tableau AI Analysis Assistant 的 Agent 架构基于 react-agent-refactor 实现，但存在以下核心问题需要优化：

### 问题 1: LLM 调用次数过多

一次完整查询可能触发 **5-13 次 LLM 调用**：

| 阶段 | LLM 调用 | 说明 |
|------|----------|------|
| SemanticParser Step1 | 1 次 | 语义理解 |
| SemanticParser Step2 | 1 次 (条件) | 计算推理 (非 SIMPLE 查询) |
| ReAct Error Handler | 1+ 次 (错误时) | 错误分析和重试决策 |
| Insight Profiler | 0 次 | 纯代码 |
| Insight Director | N 次 | 每次迭代 1 次 |
| Insight Analyzer | N 次 | 每次迭代 1 次 |
| Replanner | 1 次 | 重规划决策 |

**最坏情况**: Step1 + Step2 + (Director + Analyzer) × 5 + Replanner = **13 次 LLM 调用**

### 问题 2: 中间件需要优化

当前中间件实现存在冗余：
- OutputValidationMiddleware 与 Pydantic + `with_structured_output()` 功能重复
- PatchToolCallsMiddleware 在使用结构化输出时不需要
- 缺少对话历史摘要机制（长对话上下文问题）
- 缺少 LLM/Tool 重试机制（网络错误处理）

### 问题 3: Prompt 和 Schema 设计需要规范化

- 缺乏统一的 Prompt 设计模式
- Schema description 混入业务逻辑
- 缺少完整的设计指南文档

### 问题 4: 语义层设计需要深入思考

- 是否需要传递完整的 Tableau 数据模型给 LLM？
- 字段映射通过 RAG 实现，但需要优化策略
- 从 LLM 原理层面思考哪些可以工具化

## 目标

1. **减少 LLM 调用次数**: 目标 ≤ N+2 次/查询（N 为数据批次数）
2. **优化中间件架构**: 只保留必要的 4 个核心中间件
3. **规范 Prompt 和 Schema 设计**: 提供完整的设计指南
4. **优化语义层设计**: RAG + Candidate Fields 策略，不传递完整数据模型
5. **保持功能完整性**: 不丢失现有能力

## 需求

### 需求 1: 合并 SemanticParser Step1 + Step2

**用户故事**: 作为系统架构师，我希望减少语义解析阶段的 LLM 调用次数，以提高响应速度。

#### 验收标准

1. THE System SHALL 将 Step1 和 Step2 合并为单次 LLM 调用
2. WHEN 用户提出简单查询 (SIMPLE) THEN THE System SHALL 一次性输出完整的语义理解结果
3. WHEN 用户提出复杂查询 (LOD/TABLE_CALC) THEN THE System SHALL 在同一次调用中完成计算推理
4. THE System SHALL 保持现有的语义理解准确率
5. THE System SHALL 使用增强的 System Prompt 指导 LLM 分阶段思考

### 需求 2: 链式分析 + LangGraph Store 缓冲

**用户故事**: 作为系统架构师，我希望优化 Insight 分析阶段的 LLM 调用次数，同时保持洞察质量。

#### 验收标准

1. THE System SHALL 合并 Director 和 Analyzer 为单一的 ChainAnalyzer 角色
2. WHEN 分析数据批次时 THEN THE System SHALL 使用链式分析模式（每批数据分析后累积洞察）
3. WHEN Tableau 支持 SSE 时 THEN THE System SHALL 使用 SSE 流式返回数据
4. WHEN Tableau 不支持 SSE 时 THEN THE System SHALL 使用 LangGraph Store 作为缓冲层
5. THE System SHALL 将 LLM 调用次数从 2N 降到 N+1（N 为数据批次数）
6. THE System SHALL 在最后一轮生成完整洞察报告（流式输出）
7. THE System SHALL 保持全局视野，避免重复/冲突洞察

### 需求 3: 中间件简化

**用户故事**: 作为系统架构师，我希望简化中间件架构，只保留必要的核心中间件。

#### 验收标准

1. THE System SHALL 只保留 4 个核心中间件：
   - SummarizationMiddleware（对话历史摘要）
   - ModelRetryMiddleware（LLM 重试，指数退避）
   - ToolRetryMiddleware（工具重试，网络/API 错误）
   - FilesystemMiddleware（大文件缓存，已实现）
2. THE System SHALL 移除 OutputValidationMiddleware（Pydantic + `with_structured_output()` 已处理）
3. THE System SHALL 移除 PatchToolCallsMiddleware（结构化输出不需要）
4. THE System SHALL 实现 SummarizationMiddleware 压缩对话历史
5. THE System SHALL 实现 ModelRetryMiddleware 处理 LLM 调用失败
6. THE System SHALL 实现 ToolRetryMiddleware 处理工具调用失败（仅网络/API 错误，非业务逻辑错误）

### 需求 4: RAG + Candidate Fields 策略

**用户故事**: 作为系统架构师，我希望优化数据模型传递策略，减少 Token 消耗。

#### 验收标准

1. THE System SHALL NOT 传递完整的 DataModel 给 LLM
2. WHEN 进行字段映射时 THEN THE System SHALL 使用 RAG 检索候选字段
3. WHEN RAG confidence >= 0.9 时 THEN THE System SHALL 直接返回映射结果
4. WHEN RAG confidence < 0.9 时 THEN THE System SHALL 将候选字段传递给 LLM 进行选择
5. THE System SHALL 让 LLM 从候选字段中选择，而非生成字段名
6. THE System SHALL 保持现有的字段映射准确率

### 需求 5: Prompt 和 Schema 设计规范

**用户故事**: 作为开发者，我希望有完整的 Prompt 和 Schema 设计指南，以保证设计质量。

#### 验收标准

1. THE System SHALL 提供完整的 Prompt 设计模板（基于 Cursor、Windsurf、Devin AI 等 15+ 工具分析）
2. THE System SHALL 提供完整的 Schema 设计规范（职责分离原则）
3. THE System SHALL 在 Schema description 中只说明"是什么"（What），不说明"什么时候填"（When）和"怎么判断"（How）
4. THE System SHALL 在 Prompt 中说明决策规则、思考步骤、示例
5. THE System SHALL 使用 XML 标签分块组织复杂规则
6. THE System SHALL 提供正例和反例对比示例
7. THE System SHALL 包含自我纠错检查清单

### 需求 6: 保持 Observer 模式

**用户故事**: 作为系统架构师，我希望保持 Observer 模式，不使用 ReAct 模式。

#### 验收标准

1. THE System SHALL 保持现有的 Observer 错误处理模式
2. THE System SHALL NOT 使用 ReAct 模式（Thought → Action → Observation 循环）
3. THE System SHALL 在工具调用后使用 Observer 判断是否需要重试
4. THE System SHALL 保持现有的错误处理逻辑

### 需求 7: 大文件缓存中间件优化

**用户故事**: 作为开发者，我希望优化现有的大文件缓存中间件。

#### 验收标准

1. THE System SHALL 保留现有的 FilesystemMiddleware 功能
2. THE System SHALL 优化大文件检测逻辑
3. THE System SHALL 优化文件读写性能
4. THE System SHALL 支持配置缓存大小限制

## 非功能需求

### 性能需求

1. LLM 调用次数减少约 **50%**（从 2N+3 降到 N+2）
2. 响应时间减少 30%+（减少 LLM 调用）
3. Token 消耗减少 40%+（不传递完整数据模型）

### 质量需求

1. 查询准确率不低于当前水平
2. 洞察质量不低于当前水平（保持全局视野）
3. 字段映射准确率不低于当前水平

### 可维护性需求

1. 代码复杂度降低（移除冗余中间件）
2. Prompt 和 Schema 设计规范化
3. 文档完整（设计指南 + 实现文档）

## 风险与缓解

| 风险 | 缓解措施 |
|------|----------|
| 合并后 Prompt 过长 | 使用结构化 Prompt，分层组织 |
| 单次调用准确率下降 | 增强 System Prompt，添加更多示例 |
| 链式分析上下文过长 | 压缩历史洞察，只保留关键信息 |
| Tableau 版本不支持 SSE | 使用 LangGraph Store 作为缓冲层 |
| RAG 候选字段不准确 | LLM Fallback 机制，从候选字段中选择 |

## 实施优先级

| 需求 | 优先级 | 说明 |
|------|--------|------|
| 需求 3: 中间件简化 | P0 | 基础设施，影响所有后续需求 |
| 需求 5: Prompt 和 Schema 规范 | P0 | 设计指南，指导所有 Prompt 设计 |
| 需求 1: 合并 SemanticParser | P1 | 减少 1-2 次 LLM 调用 |
| 需求 4: RAG + Candidate Fields | P1 | 减少 Token 消耗 |
| 需求 2: 链式分析 | P1 | 减少 N 次 LLM 调用 |
| 需求 7: 大文件缓存优化 | P2 | 性能优化 |
| 需求 6: 保持 Observer | P2 | 架构决策，不影响功能 |

## 参考资料

- agent-simplification 设计文档
- react-agent-refactor 设计文档
- docs/appendix-prompt-schema-patterns.md
- Cursor、Windsurf、Devin AI、Claude Code 等 15+ AI 工具分析
