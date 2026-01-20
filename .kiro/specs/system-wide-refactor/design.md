# 设计文档：Analytics Assistant 系统级重构

## 概述

本设计文档详细说明了 Analytics Assistant 的系统级重构方案。该系统是基于 LangChain/LangGraph 的 AI 编排平台，通过多个专业化 Agent 实现自然语言数据分析。

**项目特性**：
- ✅ **允许破坏性重构**：项目未上线，不要求兼容旧接口/旧行为
- ✅ **可回滚能力**：通过 Git 分支策略和数据迁移脚本确保可回滚
- ✅ **分阶段实施**：7 个阶段，每个阶段独立可测试和回滚
- 📁 **新项目目录**：`analytics-assistant/`（不修改原始 `tableau_assistant/` 代码）

### 重构目标

1. **架构现代化**：建立清晰的五层架构，实现关注点分离
2. **代码复用最大化**：提取可复用组件和中间件，消除重复代码
3. **语义理解优化**：降低 token 消耗 30%，提升准确性
4. **模块化设计**：组件化 Agent，提升可测试性和可维护性
5. **性能优化**：减少延迟，提升缓存命中率
6. **可观测性增强**：完善日志、指标和追踪体系

### 设计原则

- **分层架构**：严格的依赖方向，下层不依赖上层
- **接口优先**：使用抽象基类定义清晰的契约
- **组件化**：小而专注的组件，单一职责
- **可测试性**：支持单元测试和集成测试
- **性能优先**：缓存、批处理、流式响应
- **可观测性**：全面的日志、指标和追踪
- **可回滚性**：每个阶段独立部署，支持快速回滚

## 架构设计

### 五层架构概览

```
┌─────────────────────────────────────────────────────────┐
│                    API 层 (FastAPI)                      │
│                  流式输出、错误处理                        │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│              Orchestration 层 (编排层)                   │
│   LangGraph 工作流、中间件、工具、状态管理                │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│                   Agent 层 (智能体层)                     │
│  SemanticParser、FieldMapper、DimensionHierarchy、        │
│  Insight、Replanner                                      │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│                Platform 层 (平台适配层)                   │
│  Tableau、Power BI 等平台特定实现                         │
│  实现 Core 层定义的接口                                   │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│                  Core 层 (核心领域层)                     │
│  领域模型、业务逻辑、平台无关接口                          │
│  不依赖任何其他层                                         │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│          Infrastructure 层 (基础设施层 - 横向)            │
│  AI (ModelManager)、RAG、Storage、Config、Observability  │
│  被所有层使用，不依赖业务层                                │
└─────────────────────────────────────────────────────────┘
```

**分层原则**（详见 [附件 1](./attachments/01-architecture-layers.md)）：
- **Core 层**：最底层，不依赖任何其他层，定义领域模型和接口
- **Platform 层**：实现 Core 层定义的接口，依赖 Core 层
- **Agent 层**：使用 Platform 层和 Core 层，依赖 Platform + Core
- **Orchestration 层**：编排 Agent 层，依赖 Agent + Platform + Core
- **API 层**：最上层，依赖 Orchestration + Agent + Platform + Core
- **Infrastructure 层**：横向层，被所有层使用，不依赖业务层

### 层次职责概要

详细的层次设计请参考：[附件 1：五层架构详细设计](./attachments/01-architecture-layers.md)

| 层次 | 职责 | 关键组件 | 依赖方向 |
|------|------|---------|---------|
| **Core 层** | 领域模型、业务逻辑、平台无关接口 | SemanticQuery, DataModel, IPlatformAdapter | 不依赖任何层 |
| **Platform 层** | 平台特定实现、API 调用、数据转换 | TableauAdapter, QueryBuilder | 依赖 Core |
| **Agent 层** | 专业化 AI Agent、任务处理 | SemanticParser, FieldMapper, Insight | 依赖 Platform + Core |
| **Orchestration 层** | 工作流编排、中间件、工具 | LangGraph Workflow, Middleware | 依赖 Agent + Platform + Core |
| **Infrastructure 层** | 横向基础设施服务 | ModelManager, RAG, Cache, Observability | 被所有层使用 |

## 框架选型

### LangChain/LangGraph 评估

**继续使用 LangChain/LangGraph 的理由**：

✅ **优势**：
- 成熟的 LLM 编排框架，社区活跃
- LangGraph 提供强大的状态管理和工作流编排
- 丰富的集成（OpenAI、Anthropic、向量数据库等）
- 支持流式输出和中间件
- 团队已有使用经验

⚠️ **劣势**：
- 抽象层次较高，某些场景灵活性不足
- RAG 功能不够强大，需要自研

**决策**：继续使用 LangChain/LangGraph，自研 RAG 基础设施

详细对比请参考：[附件 2：框架选型对比](./attachments/02-framework-comparison.md)

## 核心优化策略

### 存储架构设计

**设计原则**：
1. **不重复造轮子**：封装 LangChain/LangGraph 自带的存储抽象，不重新实现
2. **支持多后端**：SQLite（开发，默认）、Redis（生产，可选）、FAISS/Chroma（向量）
3. **明确数据分类**：结构化数据、向量数据、大文件分别存储
4. **简化部署**：项目未上线，不需要版本化存储和数据迁移
5. **移除直接依赖**：移除当前项目对 Redis 的直接依赖，通过配置可选启用

**存储分层架构**：
```
业务层（managers/）
  ↓
抽象层（base.py, factory.py）
  ↓
后端层（backends/）+ 向量层（vector/）
  ↓
LangChain/LangGraph 原生存储
```

**数据分类和存储策略**：

| 数据类型 | 存储位置 | 后端选择 | 说明 |
|---------|---------|---------|------|
| **结构化数据** | `backends/` | SQLite/Redis | 缓存、会话、配置等 |
| **向量数据** | `vector/` | FAISS/Chroma | Embeddings、字段索引 |
| **大文件** | `managers/file_store.py` | 文件系统 | 查询结果、大型数据 |

详细设计请参考：[附件 7：目录结构 - 存储架构详细说明](./attachments/07-directory-structure.md#存储架构详细说明)

### 语义理解优化（降低 token 消耗 30%）

**三层意图路由策略**：
1. **L0 规则引擎**（目标命中率 30%）：基于关键词和模式匹配
2. **L1 小模型**（目标命中率 50%）：轻量级分类模型
3. **L2 LLM 兜底**（剩余 20%）：复杂查询使用大模型

**Prompt 优化**：
- 动态 Schema 注入（仅相关字段）
- 分层 Prompt 设计（Step1 → Step2）
- 思维链压缩

**混合检索策略**：
- 精确匹配 > 向量检索 > 关键词检索
- 两阶段分数融合
- 候选数控制（≤20）

详细设计请参考：[附件 3：语义理解优化详细设计](./attachments/03-semantic-optimization.md)

## 测试策略

### Property-Based Testing（属性测试）

**20 个核心正确性属性**：

| 类别 | 属性数量 | 示例 |
|------|---------|------|
| 预处理 | 4 | 幂等性、可逆性、长度约束 |
| 意图路由 | 3 | 确定性、置信度范围、覆盖性 |
| Schema Linking | 4 | 精确匹配优先、同义词对称性 |
| 缓存 | 3 | 幂等性、一致性、过期时间 |
| 配置 | 3 | 验证完整性、默认值、环境隔离 |
| 序列化 | 3 | Round-trip、类型保持、向后兼容 |

详细属性定义请参考：[附件 4：正确性属性详细定义](./attachments/04-correctness-properties.md)

### 测试覆盖率目标

- **单元测试覆盖率**：≥ 80%
- **集成测试覆盖率**：≥ 60%
- **属性测试**：20 个核心属性全覆盖

## 实施计划

### 7 阶段实施路线图（约 17 周）

| 阶段 | 名称 | 工期 | 关键交付物 | 可回滚点 |
|------|------|------|-----------|---------|
| **阶段 1** | 基础设施层重构 | 2 周 | ModelManager, RAG, Cache | ✅ Git Tag v1.0 |
| **阶段 2** | Core 层和 Platform 层 | 2 周 | 领域模型、Tableau 适配器 | ✅ Git Tag v2.0 |
| **阶段 3** | Agent 组件化 | 3 周 | 可复用组件、中间件 | ✅ Git Tag v3.0 |
| **阶段 4** | 语义解析器优化 | 3 周 | 三层路由、Prompt 优化 | ✅ Git Tag v4.0 |
| **阶段 5** | Orchestration 层 | 2 周 | LangGraph 工作流 | ✅ Git Tag v5.0 |
| **阶段 6** | 测试和优化 | 3 周 | 单元测试、属性测试 | ✅ Git Tag v6.0 |
| **阶段 7** | 文档和验收 | 2 周 | 技术文档、用户文档、系统验收 | ✅ Git Tag v7.0 |

详细实施计划请参考：[附件 5：分阶段实施计划](./attachments/05-implementation-plan.md)

### 回滚策略

**Git 分支策略**：
```
main (生产)
  ↑
develop (开发)
  ↑
feature/phase-1 → merge → tag v1.0
feature/phase-2 → merge → tag v2.0
...
```

**回滚步骤**：
1. 识别问题阶段（通过监控和日志）
2. 执行 `git revert` 或 `git checkout <previous-tag>`
3. 回滚配置文件到上一版本
4. 重新部署
5. 验证系统功能

**配置回滚**：
- 每个阶段提供配置快照
- 配置文件版本控制（Git）
- 环境变量备份

## 风险评估

### 6 大技术风险

| 风险 | 影响 | 概率 | 缓解策略 | 回滚方案 |
|------|------|------|---------|---------|
| LangGraph 性能瓶颈 | 高 | 中 | 性能测试、优化、降级方案 | 回滚到上一版本 |
| RAG 检索准确性 | 高 | 中 | A/B 测试、人工评估 | 使用旧检索逻辑 |
| 数据迁移失败 | 高 | 低 | 备份、回滚脚本 | 恢复备份 |
| Token 消耗超预期 | 中 | 中 | 监控、告警、成本控制 | 调整路由策略 |
| 测试覆盖不足 | 中 | 中 | 强制覆盖率检查、Code Review | N/A |
| 团队学习曲线 | 低 | 高 | 培训、文档、结对编程 | N/A |

详细风险评估请参考：[附件 6：风险评估报告](./attachments/06-risk-assessment.md)

## 性能基准

| 指标 | 基线 | 目标 | 测量方法 |
|------|------|------|---------|
| 语义解析延迟（P90） | 5.0s | 3.0s | 性能测试 |
| Token 消耗 | 1000 tokens | 700 tokens | LLM API 统计 |
| 缓存命中率 | 40% | 60% | LangGraph SqliteStore 统计 |
| 并发处理能力 | 50 req/s | 100 req/s | 压力测试 |
| 错误率 | 5% | 2% | 监控统计 |

## 重复代码和模块化问题

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
| **存储后端** | Redis 依赖 | 🔴 高 | 与 SqliteStore 重复 | 移除，统一使用 SqliteStore |
| **缓存** | 7+ 个缓存类 | 🔴 高 | 重复逻辑（Hash、TTL、序列化） | 创建统一 CacheManager |
| **索引** | `FieldValueIndexer` | 🔴 高 | 与 FieldIndexer 重复 | 合并为 VectorIndexManager |
| **RAG** | 多个检索器 | 🟡 中 | 职责不清，层级混乱 | 明确检索器层级 |
| **模块化** | Agent 层基础设施代码 | 🔴 高 | 违反分层原则 | 移动到 Infra 层 |
| **中间件** | `PatchToolCallsMiddleware` | 🟡 中 | 可能不再需要 | 阶段 1 后测试 |
| **中间件** | `OutputValidationMiddleware` | 🟡 中 | 可能不再需要 | 阶段 1 后测试 |

### 具体问题分析

#### 1. 存储后端重复

**问题**：
- Redis 与 LangGraph SqliteStore 功能重复
- FAISS 文件存储分散
- 缺乏统一的存储抽象

**解决方案**：
- 创建 `StorageBackend` 接口
- 统一使用 SqliteStore
- 将 FAISS 索引序列化后存入 SqliteStore

#### 2. 缓存层级混乱

**发现的缓存类**：
1. `DataModelCache` - 数据模型元数据
2. `FieldIndexCache` - 字段索引
3. `GoldenQueryStore` - Golden Query
4. `CachedEmbeddingProvider` - Embedding 向量
5. `SchemaLinkingQueryCache` - Schema Linking 查询
6. `DimensionHierarchyCacheStorage` - 维度层级
7. `CachedMapping` - 字段映射

**问题**：每个缓存类都重新实现了相同的逻辑（Hash 计算、TTL 管理、序列化）

**解决方案**：
- 创建统一的 `CacheManager` 基类
- 所有缓存类继承 `CacheManager`
- 统一 TTL 策略和失效机制

#### 3. 索引功能重复

**问题**：
- `FieldIndexer` 和 `FieldValueIndexer` 功能重复
- 都在构建 FAISS 索引
- 持久化策略不一致

**解决方案**：
- 合并为统一的 `VectorIndexManager`
- 统一 Embedding 缓存策略
- 统一持久化策略

#### 4. 模块化问题

**问题**：
- Agent 层包含基础设施代码（缓存、索引、检索）
- 基础设施层依赖 Agent 层（违反分层原则）
- 没有清晰的分层边界

**解决方案**：
- 移动 Agent 层的基础设施代码到 Infra 层
- 清理依赖关系
- 明确分层边界

### 重构优先级和时间表

| 优先级 | 任务 | 预期收益 | 时间 |
|-------|------|---------|------|
| 🔴 高 | 统一存储层（移除 Redis） | 减少 30% 存储代码 | 2-3 周 |
| 🔴 高 | 统一缓存管理器 | 减少 40% 缓存代码 | 2-3 周 |
| 🟡 中 | 统一索引管理器 | 减少 35% 索引代码 | 3-4 周 |
| 🟡 中 | 统一检索器层级 | 减少 25% 检索代码 | 2-3 周 |
| 🟡 中 | 模块化重组 | 清晰分层边界 | 1-2 周 |

**总计**：11-16 周（约 3-4 个月）

### 预期收益

- **代码减少**：35-40% 存储/缓存/索引/RAG 相关代码
- **部署简化**：移除 Redis 依赖
- **可维护性**：统一接口和抽象，清晰分层边界
- **性能**：统一缓存策略，提高缓存命中率

### 中间件系统说明

**LangChain 框架自带中间件**（5个）：
- `TodoListMiddleware` - 任务队列管理
- `SummarizationMiddleware` - 自动摘要对话历史
- `ModelRetryMiddleware` - LLM 调用自动重试
- `ToolRetryMiddleware` - 工具调用自动重试
- `HumanInTheLoopMiddleware` - **人工确认（必选）**

**自定义中间件**（3个）：
- `FilesystemMiddleware` - 大型结果自动保存到文件
- `PatchToolCallsMiddleware` - 修复悬空的 tool_calls（重构后可能不需要）
- `OutputValidationMiddleware` - 输出格式校验（重构后可能不需要）

**注意**：大部分中间件是框架自带，不是自研。重构后将评估自定义中间件的必要性。

### 多轮会话管理

**实现方案**：

系统使用 **LangGraph 的 Checkpointer** 和 **SessionManager** 实现多轮会话管理。

#### 1. 会话存储架构

```python
# infra/storage/managers/session_manager.py
class SessionManager:
    """会话管理器 - 管理多轮对话的会话状态"""
    
    def __init__(self, store: BaseStore):
        self.store = store
        self.namespace = "sessions"
    
    async def create_session(self, user_id: str, workspace_id: str) -> str:
        """创建新会话"""
        session_id = generate_session_id()
        session = {
            "session_id": session_id,
            "user_id": user_id,
            "workspace_id": workspace_id,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
            "message_count": 0,
            "metadata": {}
        }
        await self.store.put(f"{self.namespace}/{session_id}", session)
        return session_id
    
    async def get_session(self, session_id: str) -> Dict:
        """获取会话信息"""
        return await self.store.get(f"{self.namespace}/{session_id}")
    
    async def update_session(self, session_id: str, updates: Dict):
        """更新会话信息"""
        session = await self.get_session(session_id)
        session.update(updates)
        session["updated_at"] = datetime.now()
        await self.store.put(f"{self.namespace}/{session_id}", session)
```

#### 2. LangGraph Checkpointer 集成

LangGraph 使用 **Checkpointer** 自动保存和恢复工作流状态：

```python
# orchestration/workflow/factory.py
from langgraph.checkpoint.sqlite import SqliteSaver

def create_workflow_with_checkpointer():
    """创建带检查点的工作流"""
    # 使用 SQLite 作为检查点存储
    checkpointer = SqliteSaver.from_conn_string("checkpoints.db")
    
    # 创建工作流
    workflow = create_workflow()
    
    # 编译时传入 checkpointer
    app = workflow.compile(checkpointer=checkpointer)
    
    return app
```

#### 3. 会话上下文管理

**对话历史存储**：
- 使用 LangGraph 的 `MessagesState` 自动管理消息历史
- 使用 `SummarizationMiddleware` 自动压缩长对话（超过 60K tokens）
- 保留最近 10 条消息的完整内容

**会话恢复**：
```python
# API 层调用
async def continue_conversation(session_id: str, user_message: str):
    """继续现有会话"""
    # 1. 获取会话信息
    session = await session_manager.get_session(session_id)
    
    # 2. 使用 session_id 作为 thread_id 恢复状态
    config = {
        "configurable": {
            "thread_id": session_id,
            "checkpoint_ns": session["workspace_id"]
        }
    }
    
    # 3. 调用工作流（自动加载历史状态）
    result = await app.ainvoke(
        {"messages": [HumanMessage(content=user_message)]},
        config=config
    )
    
    # 4. 更新会话统计
    await session_manager.update_session(session_id, {
        "message_count": session["message_count"] + 1
    })
    
    return result
```

#### 4. 会话状态持久化

**存储内容**：
- **会话元数据**：session_id, user_id, workspace_id, created_at, updated_at
- **对话历史**：完整的消息列表（由 LangGraph Checkpointer 管理）
- **工作流状态**：当前节点、变量、中间结果（由 LangGraph Checkpointer 管理）
- **上下文信息**：数据模型、字段映射、查询历史

**存储后端**：
- **开发环境**：SQLite（`checkpoints.db` + `sessions.db`）
- **生产环境**：Redis（可选，通过配置切换）

#### 5. 会话生命周期管理

**会话创建**：
```python
POST /api/sessions
{
    "user_id": "user123",
    "workspace_id": "workspace456"
}
→ 返回 session_id
```

**会话继续**：
```python
POST /api/chat
{
    "session_id": "session789",
    "message": "过去7天的销售额趋势"
}
→ 自动加载历史状态，继续对话
```

**会话清理**：
- 自动清理：超过 7 天未活跃的会话
- 手动清理：用户主动结束会话
- 保留策略：重要会话可标记为"保留"

#### 6. 多轮对话示例

**第一轮**：
```
用户: "过去7天的销售额趋势"
系统: [生成趋势图] "这是过去7天的销售额趋势..."
```

**第二轮**（基于上下文）：
```
用户: "按区域分组"
系统: [理解上下文：销售额 + 过去7天 + 按区域分组]
     [生成分组趋势图] "这是各区域的销售额趋势..."
```

**第三轮**（继续细化）：
```
用户: "只看华东区"
系统: [理解上下文：销售额 + 过去7天 + 华东区]
     [生成华东区趋势图] "这是华东区的销售额趋势..."
```

**关键特性**：
- ✅ **自动上下文理解**：无需重复指定时间范围、指标等
- ✅ **状态持久化**：会话可跨请求恢复
- ✅ **对话压缩**：长对话自动摘要，节省 token
- ✅ **灵活存储**：支持 SQLite（开发）和 Redis（生产）

### HumanInTheLoopMiddleware 配置（必选）

**重要**：HumanInTheLoopMiddleware 是**必选**的，不是可选的。

**介入场景**：
- **探索任务规划**（`write_todos`）：当 Replanner Agent 生成探索问题时，需要用户审核和确认

**为什么只在探索任务介入**：
- 探索问题会影响后续的查询方向，需要用户确认是否继续探索
- 其他操作（数据查询、可视化生成等）是系统的核心功能，不需要人工介入
- 保持流畅的用户体验，避免过多的确认步骤

**配置示例**：
```python
# .env
INTERRUPT_ON=write_todos

# 或者在代码中配置
HumanInTheLoopMiddleware(
    interrupt_on={
        "write_todos": True
    }
)
```

**工作流程**：
1. Replanner Agent 调用 `write_todos` 工具生成探索问题
2. HumanInTheLoopMiddleware 拦截调用
3. 系统暂停，向用户展示探索问题列表
4. 用户审核：
   - 批准 → 继续执行探索问题
   - 拒绝 → 结束当前会话
   - 修改 → 用户可以调整探索问题

### 中间件和存储模块的协作

**FilesystemMiddleware 和 FileStore 的关系**：
- **FilesystemMiddleware**（`orchestration/middleware/filesystem.py`）：
  - 职责：为 Agent 提供文件操作工具接口（ls, read_file, write_file, edit_file, glob, grep）
  - 层次：Orchestration 层
  - 作用：让 Agent 能够通过工具调用来操作文件系统
  
- **FileStore**（`infra/storage/managers/file_store.py`）：
  - 职责：实际的文件存储实现（读写文件、管理文件生命周期）
  - 层次：Infrastructure 层
  - 作用：提供底层的文件存储能力

- **协作方式**：
  - FilesystemMiddleware 调用 FileStore 来实现文件操作
  - FilesystemMiddleware 负责工具接口和参数验证
  - FileStore 负责实际的文件 I/O 操作
  - 这种分层设计实现了关注点分离：工具接口层（Orchestration）和存储实现层（Infrastructure）

**Embedding 缓存的统一**：
- ❌ **删除**：`infra/rag/embedding_cache.py`（RAG 模块的重复实现）
- ✅ **保留**：`infra/storage/managers/embedding_cache.py`（统一的 Embedding 缓存）
- **原因**：避免重复实现，统一缓存管理策略
- **影响**：所有需要 Embedding 缓存的模块（RAG、FieldMapper、DimensionHierarchy）都使用统一的缓存接口

---

## 附件索引

详细设计文档已拆分到附件目录，便于阅读和维护：

1. [五层架构详细设计](./attachments/01-architecture-layers.md) - Core、Platform、Agent、Orchestration、Infrastructure 层详细设计
2. [框架选型对比](./attachments/02-framework-comparison.md) - LangChain/LangGraph vs 其他框架对比
3. [语义理解优化详细设计](./attachments/03-semantic-optimization.md) - 三层路由、Prompt 优化、混合检索
4. [正确性属性详细定义](./attachments/04-correctness-properties.md) - 20 个 Property-Based Testing 属性
5. [分阶段实施计划](./attachments/05-implementation-plan.md) - 7 阶段详细任务分解
6. [风险评估报告](./attachments/06-risk-assessment.md) - 风险识别、缓解策略、回滚方案
7. [目录结构](./attachments/07-directory-structure.md) - 完整的项目目录结构
8. [依赖和配置](./attachments/08-dependencies.md) - 依赖列表、配置示例
9. [数据流和序列图](./attachments/09-data-flow.md) - 系统数据流和交互序列图
10. [术语表](./attachments/10-glossary.md) - 技术术语和概念定义
11. [多轮会话管理](./attachments/11-session-management.md) - 会话管理详细实现方案
12. [ModelManager 设计](./attachments/12-model-manager-design.md) - 统一模型管理器详细设计

## 总结

本设计文档提供了 Tableau AI 分析助手系统级重构的完整方案：

✅ **清晰的五层架构**：关注点分离，依赖方向明确（Core 不依赖任何层，Platform 实现 Core 接口）  
✅ **组件化设计**：可复用、可测试、易维护  
✅ **语义理解优化**：三层路由 + Prompt 优化 + 混合检索，降低 token 消耗 30%  
✅ **完善的测试策略**：单元测试 + 属性测试，覆盖率 ≥ 80%  
✅ **分阶段实施**：7 个阶段，每个阶段独立可测试和回滚  
✅ **风险可控**：识别 6 大风险，提供缓解策略和回滚方案  
✅ **可观测性**：日志、指标、追踪、告警全覆盖  

**关键特性**：
- 🚀 **允许破坏性重构**：不受旧接口约束，实现最优架构
- 🔄 **可回滚能力**：Git 分支策略 + 数据迁移脚本 + 每阶段独立部署
- 📊 **性能提升**：延迟降低 40%，token 消耗降低 30%，缓存命中率提升 50%
- 📁 **文件映射清晰**：详见 [tasks.md](./tasks.md)，包含现有文件到目标模块的完整映射

该设计为系统重构提供了清晰的路线图，确保在提升代码质量和性能的同时，保持系统稳定性和可回滚性。
