# 系统级重构规范 - 总结

本文档提供系统级重构规范的快速概览和导航。

**项目名称**：`analytics-assistant`（通用 BI 分析助手平台）

---

## 📋 文档结构

### 核心文档

1. **`requirements.md`** - 需求文档（中文）
   - 15 个核心需求模块
   - 涵盖架构现代化、组件复用、语义理解优化等
   - 不需要向后兼容，允许破坏性变更

2. **`design.md`** - 主设计文档（中文）
   - 概述和架构概览
   - 实施计划概要
   - 附件索引
   - 新项目名称：`analytics-assistant`

3. **`tasks.md`** - 实施任务列表（已创建）
   - 7 个阶段的详细任务
   - 包含现有文件到目标模块的完整映射
   - 每个任务包含验收标准和测试要求
   - 所有路径使用 `analytics-assistant/` 前缀

### 附件文档（`attachments/`）

1. **`01-architecture-layers.md`** - 五层架构详细设计
2. **`02-framework-comparison.md`** - 框架选型对比
3. **`03-semantic-optimization.md`** - 语义理解优化详细设计
4. **`04-correctness-properties.md`** - 20 个正确性属性定义
5. **`05-implementation-plan.md`** - 7 阶段详细实施计划
6. **`06-risk-assessment.md`** - 6 大风险评估和回滚方案
7. **`07-directory-structure.md`** - 完整项目目录结构
8. **`08-dependencies.md`** - 依赖列表和配置示例
9. **`09-data-flow.md`** - 数据流和序列图
10. **`10-glossary.md`** - 术语表

### 已整合的分析内容

以下分析内容已整合到主设计文档（`design.md`）中：
- 中间件系统说明（LangChain 自带 vs 自定义）
- 重复代码和模块化问题分析
- 存储、缓存、索引、RAG 重复功能分析
- 重构优先级和时间表

---

## 🎯 核心目标

1. **使用 LangChain 和 LangGraph 框架**（必须）
2. **最大化复用现有代码**，特别是中间件部分
3. **采用模块化设计**，明确各模块接口规范
4. **重点优化语义理解模块**（准确性 + 降低 token 消耗 30%）
5. **分阶段实施**（7 个阶段）
6. **不需要向后兼容**，可以进行破坏性变更
7. **必须具备可回滚能力**

---

## 🏗️ 架构概览

### 五层架构

```
┌─────────────────────────────────────────────────────────┐
│ API 层（FastAPI）                                        │
│    - REST API 端点                                       │
│    - 流式输出支持（SSE）                                 │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ Orchestration 层（LangGraph）                            │
│    - 工作流编排（3 个 Agent 节点）                       │
│    - 中间件栈（8 个中间件）                              │
│    - 状态管理和检查点                                    │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ Agent 层（智能体）                                       │
│    - SemanticParser（子图）                              │
│    - Insight（子图）                                     │
│    - Replanner（单节点）                                 │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ Platform 层（平台适配）                                  │
│    - Tableau 适配器                                      │
│    - 实现 Core 层定义的接口                              │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ Core 层（核心抽象）                                      │
│    - 平台无关的接口和模型                                │
│    - 语义查询模型（SemanticQuery）                       │
│    - 不依赖任何其他层                                    │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ Infrastructure 层（基础设施 - 横向）                     │
│    - AI（LLM、Embedding、ModelManager）                  │
│    - RAG（检索器、向量存储）                             │
│    - Storage（缓存、数据库）                             │
│    - Config（配置管理）                                  │
│    - Observability（监控、日志）                         │
│    - 被所有层使用，不依赖业务层                          │
└─────────────────────────────────────────────────────────┘
```

**分层原则**：
- **Core 层**：最底层，不依赖任何其他层
- **Platform 层**：实现 Core 层接口，依赖 Core
- **Agent 层**：依赖 Platform + Core
- **Orchestration 层**：依赖 Agent + Platform + Core
- **API 层**：最上层，依赖所有业务层
- **Infrastructure 层**：横向层，被所有层使用

---

## 📊 中间件栈

### LangChain 框架自带（5个）

1. **TodoListMiddleware** - 任务队列管理
2. **SummarizationMiddleware** - 自动摘要对话历史
3. **ModelRetryMiddleware** - LLM 调用重试（指数退避）
4. **ToolRetryMiddleware** - 工具调用重试（指数退避）
5. **HumanInTheLoopMiddleware** - **人工确认（必选）**

### 自定义中间件（3个）

1. **FilesystemMiddleware** - 大型结果自动保存到文件
2. **PatchToolCallsMiddleware** - 修复悬空的 tool_calls（重构后可能移除）
3. **OutputValidationMiddleware** - 输出格式校验（重构后可能移除）

### HumanInTheLoopMiddleware（必选）

**重要**：HumanInTheLoopMiddleware 是**必选**的，不是可选的。

**介入场景**：
- **探索任务规划**（`write_todos`）：当 Replanner Agent 生成探索问题时，需要用户审核和确认

**为什么只在探索任务介入**：
- 探索问题会影响后续的查询方向，需要用户确认是否继续探索
- 其他操作（数据查询、可视化生成等）是系统的核心功能，不需要人工介入
- 保持流畅的用户体验，避免过多的确认步骤

**配置示例**：
```bash
# .env
INTERRUPT_ON=write_todos
```

---

## 🔄 多轮会话管理

### 实现方案

系统使用 **LangGraph Checkpointer** 和 **SessionManager** 实现多轮会话：

**核心组件**：
1. **SessionManager**（`infra/storage/managers/session_manager.py`）
   - 管理会话元数据（session_id, user_id, workspace_id）
   - 会话创建、查询、更新、清理

2. **LangGraph Checkpointer**（`SqliteSaver` / `RedisSaver`）
   - 自动保存工作流状态
   - 自动管理对话历史
   - 支持会话恢复

3. **SummarizationMiddleware**
   - 自动压缩长对话（超过 60K tokens）
   - 保留最近 10 条消息

**会话生命周期**：
```
创建会话 → 多轮对话 → 自动保存状态 → 会话恢复 → 自动清理（7天）
```

**多轮对话示例**：
```
第1轮: "过去7天的销售额趋势" → [生成趋势图]
第2轮: "按区域分组" → [理解上下文：销售额+过去7天+按区域]
第3轮: "只看华东区" → [理解上下文：销售额+过去7天+华东区]
```

**关键特性**：
- ✅ 自动上下文理解（无需重复指定参数）
- ✅ 状态持久化（跨请求恢复）
- ✅ 对话压缩（节省 token）
- ✅ 灵活存储（SQLite/Redis）

---

## 🔍 重复代码和模块化问题

### 问题概述

经过全面代码审查，发现以下重复和模块化问题：

**统计数据**：
- **存储后端**: 4 个（LangGraph SqliteStore, Redis, FAISS, 内存）
- **缓存类**: 7+ 个，重复实现相同逻辑
- **索引器**: 3+ 个，功能重叠
- **检索器**: 5+ 个，职责不清
- **重复代码估计**: 40-50%

### 需要重构的重复代码

| 类别 | 文件/组件 | 优先级 | 问题 | 建议 |
|------|----------|--------|------|------|
| **LLM 管理** | `agents/field_mapper/llm_selector.py` | 🔴 高 | 简单封装，无额外价值 | 移除，使用 base 工具函数 |
| **Agent RAG** | `agents/field_mapper/rag/` | 🔴 高 | 与 infra/rag 重复 | 移除，直接使用 infra/rag |
| **LLM 推断** | `agents/dimension_hierarchy/llm_inference.py` | 🔴 高 | 简单封装，可整合 | 移除，整合到 node.py |
| **工具层** | `orchestration/tools/` | 🔴 高 | 与 Agent 节点重复 | 移除，直接调用 Agent 节点 |
| **存储后端** | Redis 依赖 | 🔴 高 | 与 SqliteStore 重复 | 移除，统一使用 SqliteStore |
| **缓存** | 7+ 个缓存类 | 🔴 高 | 重复逻辑（Hash、TTL、序列化） | 创建统一 CacheManager |
| **索引** | `FieldValueIndexer` | 🔴 高 | 与 FieldIndexer 重复 | 合并为 VectorIndexManager |
| **RAG** | 多个检索器 | 🟡 中 | 职责不清，层级混乱 | 明确检索器层级 |
| **模块化** | Agent 层基础设施代码 | 🔴 高 | 违反分层原则 | 移动到 Infra 层 |
| **中间件** | `PatchToolCallsMiddleware` | 🟡 中 | 可能不再需要 | 阶段 1 后测试 |
| **中间件** | `OutputValidationMiddleware` | 🟡 中 | 可能不再需要 | 阶段 1 后测试 |
| **命名** | `models/` 目录 | 🟡 中 | 与 Python models 冲突 | 重命名为 `schemas/` |

### 重构优先级和时间表

| 优先级 | 任务 | 预期收益 | 时间 |
|-------|------|---------|------|
| 🔴 高 | 统一存储层（移除 Redis） | 减少 30% 存储代码 | 2-3 周 |
| 🔴 高 | 统一缓存管理器 + 子目录化 | 减少 40% 缓存代码 | 2-3 周 |
| 🔴 高 | 删除重复 Agent 代码 | 减少 15% Agent 代码 | 1-2 周 |
| 🔴 高 | 删除 orchestration/tools/ | 减少 5% 编排代码 | 1 周 |
| 🔴 高 | models/ → schemas/ 重命名 | 避免命名冲突 | 1 周 |
| 🟡 中 | 统一索引管理器 | 减少 35% 索引代码 | 3-4 周 |
| 🟡 中 | 统一检索器层级 | 减少 25% 检索代码 | 2-3 周 |
| 🟡 中 | 模块化重组 | 清晰分层边界 | 1-2 周 |

**总计**：13-20 周（约 3-5 个月）

**详细分析**：请查看 `design.md` 的"重复代码和模块化问题"章节

---

## 📅 实施计划

### 7 阶段实施路线图（约 17 周）

### 阶段 1：基础设施层重构（2-3 周）

- 统一 LLM 和 Embedding 管理（ModelManager）
- 实现混合检索器（UnifiedRetriever）
- 优化存储架构（统一存储抽象，支持多后端）
- 实现向量存储（FAISS/Chroma）
- **存储后端策略**：
  - 移除当前项目对 Redis 的直接依赖
  - 创建统一存储抽象层，支持 SQLite（开发）和 Redis（生产可选）
  - 开发环境默认使用 SQLite，无需额外依赖
  - 生产环境可选择 Redis 后端（通过配置切换）

**存储架构重点**：
- 封装 LangChain/LangGraph 自带的存储抽象（不重复造轮子）
- 支持多后端：SQLite（开发，默认）、Redis（生产，可选）、FAISS/Chroma（向量）
- 明确数据分类：结构化数据 → SQLite/Redis，向量数据 → FAISS/Chroma，大文件 → 文件系统

### 阶段 2：Core 层和 Platform 层（2-3 周）

- 定义平台无关的接口（IPlatformAdapter）
- 实现 Tableau 适配器
- 迁移现有代码到新架构

### 阶段 3：Agent 层重构（3-4 周）

- 重构 Agent 基础组件
- 移除重复代码（llm_selector.py）
- 组件化 Agent 实现
- 统一 Agent 接口

### 阶段 4：语义解析器优化（3-4 周）

- 实现三层意图路由（规则引擎 + 小模型 + LLM）
- 优化 Prompt 设计
- 实现混合检索策略
- 降低 token 消耗 30%

### 阶段 5：Orchestration 层（2-3 周）

- 实现 LangGraph 工作流
- 配置中间件栈
- 实现状态管理和检查点

### 阶段 6：测试和优化（2-3 周）

- 单元测试和集成测试（覆盖率 ≥ 80%）
- 属性测试（20 个核心属性）
- 性能优化和压力测试

### 阶段 7：文档和验收（1-2 周）

- 完善技术文档
- 用户文档和培训材料
- 系统验收测试

**总计：** 17 周（约 4 个月）

---

## 🎯 关键指标

### 性能目标

- 平均响应时间：< 3 秒（P95 < 5 秒）
- Token 消耗：降低 30%
- 缓存命中率：> 60%
- 系统可用性：> 99.5%

### 质量目标

- 意图识别准确率：> 95%
- 字段映射准确率：> 90%
- 查询成功率：> 95%
- 单元测试覆盖率：> 80%

---

## 📚 快速导航

### 我想了解...

- **架构设计** → `attachments/01-architecture-layers.md`
- **框架选型** → `attachments/02-framework-comparison.md`
- **语义优化** → `attachments/03-semantic-optimization.md`
- **正确性属性** → `attachments/04-correctness-properties.md`
- **实施计划** → `attachments/05-implementation-plan.md`
- **风险评估** → `attachments/06-risk-assessment.md`
- **目录结构** → `attachments/07-directory-structure.md`
- **依赖管理** → `attachments/08-dependencies.md`
- **数据流** → `attachments/09-data-flow.md`
- **术语表** → `attachments/10-glossary.md`
- **多轮会话** → `attachments/11-session-management.md`
- **ModelManager 设计** → `attachments/12-model-manager-design.md`

### 我想查看...

- **需求文档** → `requirements.md`
- **设计文档** → `design.md`
- **任务清单** → `tasks.md`

---

## 🚀 下一步行动

1. ✅ **已完成：** 需求文档、设计文档、附件文档
2. ✅ **已完成：** 中间件分类修正、数据流图表优化
3. ✅ **已完成：** 重复代码分析
4. ✅ **已完成：** 存储/RAG 重复分析
5. ✅ **已完成：** 根据 GPT-5.2 审查意见更新文档
   - 删除向后兼容和灰度发布要求
   - 统一分层架构描述
   - 创建详细的任务清单和文件映射（`tasks.md`）
   - 简化实施计划
6. 🔄 **待执行：** Review 更新后的文档
7. 🔄 **待执行：** 开始阶段 1 - 基础设施层重构

---

## 📝 最新更新（2026-01-20）

### 多轮会话和人工中间件明确（第五次更新）

**新增的内容**：
- ✅ 明确 HumanInTheLoopMiddleware 为**必选**（不是可选）
- ✅ 定义具体的人工介入场景（数据修改、敏感查询、高风险操作、任务规划）
- ✅ 提供详细的配置示例（环境变量和代码配置）
- ✅ 明确多轮会话实现方案（SessionManager + LangGraph Checkpointer）
- ✅ 创建新附件：`attachments/11-session-management.md`（多轮会话详细设计）

**更新的文件**：
- ✅ `design.md` - 添加多轮会话管理章节，更新 HumanInTheLoopMiddleware 说明
- ✅ `SUMMARY.md` - 添加多轮会话管理概览，更新中间件说明
- ✅ `attachments/01-architecture-layers.md` - 更新 HumanInTheLoopMiddleware 配置
- ✅ `tasks.md` - 添加 SessionManager 实现任务，更新 HumanInTheLoopMiddleware 配置任务
- ✅ `attachments/11-session-management.md` - 新建，详细说明多轮会话实现

**关键改进**：
1. **HumanInTheLoopMiddleware 必选**：仅在探索任务（write_todos）时需要人工确认
2. **明确介入场景**：探索任务规划（用户审核探索问题）
3. **多轮会话实现**：SessionManager + LangGraph Checkpointer + SummarizationMiddleware
4. **会话管理功能**：创建、查询、更新、恢复、清理（7天）
5. **对话压缩**：自动压缩长对话（超过 60K tokens），节省 70-80% token
6. **灵活存储**：SQLite（开发）+ Redis（生产可选）

**多轮会话架构**：
```
SessionManager（会话元数据）
  ↓
LangGraph Checkpointer（状态持久化）
  ↓
SummarizationMiddleware（对话压缩）
  ↓
自动上下文理解 + 跨请求恢复
```

### 存储架构重新设计（第四次更新 - 移除 vNext 和数据迁移）

**优化的内容**：
- ✅ 移除 vNext 版本化存储（项目未上线，不需要灰度发布）
- ✅ 移除数据迁移相关任务和说明（项目未上线，无历史数据）
- ✅ 删除 `infra/rag/embedding_cache.py`（与存储模块重复）
- ✅ 统一使用 `infra/storage/managers/embedding_cache.py`
- ✅ 澄清 FilesystemMiddleware 和 FileStore 的关系

**更新的文件**：
- ✅ `attachments/07-directory-structure.md` - 移除 vNext，添加 Embedding 缓存说明
- ✅ `tasks.md` - 更新存储任务，移除 vNext 和数据迁移
- ✅ `design.md` - 添加中间件和存储协作说明
- ✅ `SUMMARY.md` - 同步最新变更

**关键改进**：
1. **简化部署**：项目未上线，不需要版本化存储和数据迁移
2. **消除重复**：删除 RAG 模块的 embedding_cache.py，统一使用存储模块
3. **明确关系**：FilesystemMiddleware（工具接口）调用 FileStore（存储实现）
4. **分层清晰**：工具接口层（Orchestration）和存储实现层（Infrastructure）分离

**存储架构分层**：
```
业务层（managers/）
  ↓ CacheManager, DataModelCache, SessionManager, EmbeddingCache, FileStore
抽象层（base.py, factory.py）
  ↓ BaseStore, StorageFactory
后端层（backends/）+ 向量层（vector/）
  ↓ SqliteBackend, RedisBackend, MemoryBackend, FAISSVectorStore, ChromaVectorStore
LangChain/LangGraph 原生存储
  ↓ SqliteStore, RedisStore, InMemoryStore, FAISS, Chroma
```

**数据分类策略**：
- **结构化数据**（缓存、会话、配置）→ SQLite/Redis（backends/）
- **向量数据**（Embeddings、字段索引）→ FAISS/Chroma（vector/）
- **大文件**（查询结果）→ 文件系统（managers/file_store.py）

### 目录结构优化（第二次更新）

**优化的内容**：
- ✅ 删除 `orchestration/tools/` - 与 Agent 节点功能重复，直接调用 Agent 节点
- ✅ 删除 `agents/field_mapper/rag/` - 直接使用 `infra/rag`，避免重复
- ✅ 删除 `agents/field_mapper/llm_selector.py` - 简单封装，直接使用 ModelManager
- ✅ 删除 `agents/dimension_hierarchy/llm_inference.py` - 整合到 `node.py`
- ✅ `models/` → `schemas/` - 所有 Agent 的 models 目录重命名为 schemas，避免与 Python models 概念冲突
- ✅ `storage/` 子目录化 - 创建 `cache/` 和 `stores/` 子目录，提升组织清晰度

**更新的文件**：
- ✅ `attachments/07-directory-structure.md` - 应用优化后的完整目录结构
- ✅ `tasks.md` - 更新文件映射表，反映所有优化
- ✅ `SUMMARY.md` - 同步最新的目录结构变更和重构优先级

**关键改进**：
1. **代码减少 15-20%**：通过删除重复代码和不必要的抽象层
2. **命名规范统一**：`schemas/` 替代 `models/`，避免命名冲突
3. **组织更清晰**：`storage/` 子目录化（`cache/` 和 `stores/`）
4. **依赖更简单**：直接使用 `infra/rag` 和 ModelManager，减少中间层
5. **架构更纯粹**：移除 `orchestration/tools/`，直接调用 Agent 节点

### 文档整合和清理（第一次更新）

**整合的内容**：
- ✅ 将 `CORRECTIONS.md` 的中间件系统说明整合到 `design.md`
- ✅ 将 `DUPLICATE_CODE_ANALYSIS.md` 的重复代码分析整合到 `design.md`
- ✅ 将 `STORAGE_RAG_DUPLICATION_ANALYSIS.md` 的存储/RAG 分析整合到 `design.md`
- ✅ 删除重复文档，保持文档结构简洁

**文档结构优化**：
- 核心文档：`requirements.md`、`design.md`、`tasks.md`、`SUMMARY.md`
- 附件文档：10 个专题附件（`attachments/` 目录）
- 所有关键分析内容已整合到主设计文档中

### 根据 GPT-5.2 审查意见的更新

**更新的文件**：
- ✅ `requirements.md` - 删除需求 5 的向后兼容，删除需求 15 的灰度发布
- ✅ `attachments/06-risk-assessment.md` - 删除 R3 灰度发布风险
- ✅ `attachments/01-architecture-layers.md` - 添加清晰的分层原则和依赖规则
- ✅ `design.md` - 更新架构概览，明确依赖方向，整合重复代码分析
- ✅ `attachments/05-implementation-plan.md` - 简化实施计划，聚焦核心重构任务
- ✅ `tasks.md` - 新建，包含详细的文件映射和迁移路径（7 个阶段）

**关键改进**：
1. **分层架构更清晰**：Core 层不依赖任何层，Platform 层实现 Core 接口
2. **文件映射更具体**：每个现有文件都有明确的目标路径和迁移阶段
3. **任务清单更可执行**：按现有代码结构组织，每个任务都有具体的文件路径
4. **实施计划更聚焦**：7 个阶段，专注于代码重构、测试和文档
5. **文档结构更简洁**：整合重复文档，避免信息分散
6. **消除重复代码**：统一存储、缓存、索引、检索组件，减少 35-40% 代码

---

## 📞 联系方式

如有问题或建议，请联系项目负责人。

**最后更新：** 2026-01-20
