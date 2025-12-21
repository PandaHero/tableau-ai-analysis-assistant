# Tableau Assistant 模块架构与功能汇总

> 本文档详细记录项目各模块的功能、设计模式，并结合业界最佳实践提出改进建议。
> 
> **深度分析版本** - 包含生产就绪度评估、主流项目对比、详细改进建议

---

## 目录

1. [项目架构概览](#1-项目架构概览)
2. [Agents 模块深度分析](#2-agents-模块深度分析)
3. [RAG 模块深度分析](#3-rag-模块深度分析)
4. [Orchestration 模块深度分析](#4-orchestration-模块深度分析)
5. [Platforms 模块](#5-platforms-模块)
6. [Infrastructure 模块](#6-infrastructure-模块)
7. [Core 模块](#7-core-模块)
8. [生产就绪度评估](#8-生产就绪度评估)
9. [业界对标与改进建议](#9-业界对标与改进建议)
10. [详细改进路线图](#10-详细改进路线图)

---

## 1. 项目架构概览

### 1.1 技术栈

| 层级 | 技术选型 | 说明 |
|------|----------|------|
| 工作流编排 | LangGraph StateGraph | 状态机驱动的多 Agent 协作 |
| LLM 框架 | LangChain | 统一的 LLM 抽象层 |
| 向量检索 | FAISS + BM25 | 混合检索（Hybrid RAG） |
| 持久化 | LangGraph SqliteStore | 会话状态 + 缓存 |
| API 框架 | FastAPI | 异步 REST API |
| 前端 | Vue 3 + TypeScript | 响应式 UI |

### 1.2 核心工作流（6 节点架构）

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Tableau Assistant Workflow                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────┐    ┌─────────────┐    ┌──────────────┐                │
│  │   Semantic   │───▶│   Field     │───▶│    Query     │                │
│  │   Parser     │    │   Mapper    │    │   Builder    │                │
│  │  (LLM Agent) │    │ (RAG + LLM) │    │  (Pure Code) │                │
│  └──────────────┘    └─────────────┘    └──────────────┘                │
│         │                                      │                         │
│         │ (non-DATA_QUERY)                     ▼                         │
│         │                            ┌──────────────┐                    │
│         ▼                            │   Execute    │                    │
│       [END]                          │  (VizQL API) │                    │
│                                      └──────────────┘                    │
│                                              │                           │
│                                              ▼                           │
│  ┌──────────────┐                   ┌──────────────┐                    │
│  │  Replanner   │◀──────────────────│   Insight    │                    │
│  │  (LLM Agent) │                   │  (LLM Agent) │                    │
│  └──────────────┘                   └──────────────┘                    │
│         │                                                                │
│         │ (should_replan=True)                                          │
│         └────────────────────────────▶ [SemanticParser]                 │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Agents 模块

### 2.1 模块结构

```
agents/
├── base/                    # Agent 基础设施
│   ├── node.py             # LLM 调用、工具处理、JSON 解析
│   ├── middleware_runner.py # LangChain Middleware 集成
│   └── prompt.py           # Prompt 模板基类
├── semantic_parser/         # 语义解析 Agent
│   ├── agent.py            # 主 Agent 逻辑
│   ├── node.py             # LangGraph 节点封装
│   ├── components/         # 组件化设计
│   │   ├── step1.py        # 语义理解 + 意图分类
│   │   ├── step2.py        # 计算推理 + 自验证
│   │   └── observer.py     # 一致性检查
│   └── prompts/            # Prompt 模板
├── field_mapper/            # 字段映射 Agent
├── insight/                 # 数据洞察 Agent
├── replanner/               # 重规划 Agent
└── dimension_hierarchy/     # 维度层级推断 Agent
```

### 2.2 Semantic Parser Agent（语义解析）

**设计模式**: LLM 组合架构（Step1 + Step2 + Observer）

| 组件 | 职责 | 对应认知阶段 |
|------|------|-------------|
| Step1 | 语义理解、问题重述、意图分类 | 直觉 (Intuition) |
| Step2 | 计算推理、自验证 | 推理 (Reasoning) |
| Observer | 一致性检查、冲突解决 | 元认知 (Metacognition) |

**意图分类**:
- `DATA_QUERY`: 数据查询（继续到 FieldMapper）
- `CLARIFICATION`: 需要澄清（返回澄清问题）
- `GENERAL`: 一般问题（直接回答）
- `IRRELEVANT`: 无关问题（拒绝）

**输出结构**:
```python
SemanticParseResult:
  - restated_question: str      # 完整独立的问题重述
  - intent: Intent              # 意图分类
  - semantic_query: SemanticQuery  # 平台无关的查询表示
  - clarification: ClarificationQuestion  # 澄清问题（可选）
  - general_response: str       # 一般回答（可选）
```

**亮点**:
- ✅ 三阶段认知架构，模拟人类思维过程
- ✅ 意图分类实现早期路由，避免无效计算
- ✅ Observer 提供自我纠错能力

**改进建议**:
- 🔧 参考 [Chain-of-Thought](https://arxiv.org/abs/2201.11903) 增强推理链
- 🔧 参考 [Self-Consistency](https://arxiv.org/abs/2203.11171) 多路径投票

---

### 2.3 Field Mapper Agent（字段映射）

**设计模式**: RAG + LLM 混合策略

```
┌─────────────────────────────────────────────────────────────────┐
│                    Field Mapper Pipeline                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  业务术语 ──▶ [Cache] ──▶ 命中? ──Yes──▶ 返回缓存结果            │
│                  │                                               │
│                  No                                              │
│                  ▼                                               │
│              [RAG 检索]                                          │
│                  │                                               │
│                  ▼                                               │
│          confidence ≥ 0.9? ──Yes──▶ 快速路径（无 LLM）           │
│                  │                                               │
│                  No                                              │
│                  ▼                                               │
│          [LLM 候选选择] ──▶ 返回最佳匹配                         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**核心组件**:
| 组件 | 职责 |
|------|------|
| FieldMapperNode | 主节点，协调缓存/RAG/LLM |
| LLMCandidateSelector | LLM 候选选择器 |
| SemanticMapper | 语义映射（RAG 检索） |
| KnowledgeAssembler | 元数据索引构建 |

**策略**:
1. **缓存优先**: LangGraph SqliteStore，24h TTL
2. **高置信度快速路径**: confidence ≥ 0.9 直接返回
3. **LLM 回退**: confidence < 0.9 时使用 LLM 从 top-k 候选中选择

**亮点**:
- ✅ 三级策略（缓存 → RAG → LLM）平衡速度和准确性
- ✅ 批量并发处理（Semaphore 控制并发数）
- ✅ 维度层级信息传递（category, level, granularity）

---

### 2.4 Insight Agent（数据洞察）

**设计模式**: 渐进式分析（Progressive Analysis）

**分析流程**:
1. **数据画像 (Data Profiling)**: 统计分布、异常检测
2. **语义分块 (Semantic Chunking)**: 基于数据特征分块
3. **LLM 分析**: 生成洞察
4. **洞察累积**: 合并多轮洞察

**输出结构**:
```python
InsightResult:
  - summary: str              # 总结
  - findings: List[Insight]   # 洞察列表
  - data_insight_profile: DataInsightProfile  # 数据画像
```

**亮点**:
- ✅ 流式输出支持（analyze_streaming）
- ✅ 维度层级感知分析
- ✅ 用户友好的错误消息转换

---

### 2.5 Replanner Agent（重规划）

**设计模式**: 类 Tableau Pulse 的多问题并行执行

**核心功能**:
1. 评估当前洞察的完成度（completeness_score）
2. 识别缺失的分析方面（missing_aspects）
3. 基于 dimension_hierarchy 生成探索问题
4. 为每个问题分配优先级

**输出结构**:
```python
ReplanDecision:
  - completeness_score: float      # 完成度 0-1
  - should_replan: bool            # 是否继续探索
  - missing_aspects: List[str]     # 缺失方面
  - exploration_questions: List[ExplorationQuestion]  # 探索问题
  - parallel_execution: bool       # 是否并行执行
```

**亮点**:
- ✅ 已回答问题去重（避免重复分析）
- ✅ 最大轮数限制（防止无限循环）
- ✅ 优先级排序（get_top_questions）

---

### 2.6 Dimension Hierarchy Agent（维度层级推断）

**功能**: 使用 LLM 推断字段的维度层级关系

**输出**:
```python
{
  "省份": {
    "category": "geography",
    "level": 1,
    "granularity": "province",
    "parent_dimension": null,
    "child_dimension": "城市"
  },
  "城市": {
    "category": "geography",
    "level": 2,
    "granularity": "city",
    "parent_dimension": "省份",
    "child_dimension": null
  }
}
```

**用途**:
- 指导 Replanner 生成下钻/上卷问题
- 帮助 Insight Agent 理解数据结构



---

## 3. RAG 模块

### 3.1 模块结构

```
infra/ai/rag/
├── models.py           # 数据模型（FieldChunk, RetrievalResult）
├── embeddings.py       # Embedding 提供者抽象
├── cache.py            # 向量缓存（CachedEmbeddingProvider）
├── field_indexer.py    # 字段索引器（FAISS）
├── retriever.py        # 检索器抽象层
│   ├── EmbeddingRetriever   # 向量检索
│   ├── KeywordRetriever     # BM25 关键词检索
│   └── HybridRetriever      # 混合检索（RRF 融合）
├── reranker.py         # 重排序器
│   ├── DefaultReranker      # 按分数排序
│   ├── RRFReranker          # RRF 融合
│   └── LLMReranker          # LLM 重排序
├── semantic_mapper.py  # 语义映射器（两阶段检索）
├── assembler.py        # 知识组装器
├── dimension_pattern.py # 维度模式 RAG
└── observability.py    # RAG 可观测性
```

### 3.2 核心组件

#### 3.2.1 Embedding 提供者

| 提供者 | 说明 |
|--------|------|
| ZhipuEmbedding | 智谱 AI Embedding |
| OpenAIEmbedding | OpenAI Embedding |
| CachedEmbeddingProvider | 带缓存的 Embedding 包装器 |

#### 3.2.2 检索器层次

```
┌─────────────────────────────────────────────────────────────────┐
│                      Retrieval Pipeline                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Query ──▶ [HybridRetriever] ──▶ [Reranker] ──▶ Results         │
│                  │                                               │
│                  ├── EmbeddingRetriever (FAISS)                 │
│                  │       └── 向量相似度检索                      │
│                  │                                               │
│                  └── KeywordRetriever (BM25)                    │
│                          └── jieba 分词 + rank_bm25             │
│                                                                  │
│  融合策略: RRF (Reciprocal Rank Fusion)                         │
│  公式: score = Σ(1/(k+rank))                                    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

#### 3.2.3 SemanticMapper（语义映射器）

**两阶段检索策略**:
1. **第一阶段**: 向量/混合检索 top-K 候选
2. **第二阶段**: LLMReranker 重排序

**置信度分层**:
| 置信度范围 | 处理策略 |
|-----------|---------|
| ≥ 0.9 | 高置信度快速路径，直接返回 |
| 0.5 - 0.9 | 走 Rerank，找最合适字段 |
| < 0.5 | 返回备选列表，触发 LLM Fallback |

#### 3.2.4 KnowledgeAssembler（知识组装器）

**分块策略**:
| 策略 | 说明 |
|------|------|
| BY_FIELD | 每个字段一个分块（默认） |
| BY_TABLE | 同一表的字段合并 |
| BY_CATEGORY | 同一类别的字段合并 |

**亮点**:
- ✅ 支持强制重建索引
- ✅ 索引持久化（save_index/load_index）
- ✅ 灵活的分块策略

### 3.3 RAG 可观测性

```python
RAGObserver:
  - RetrievalLogEntry: 检索日志
  - RerankLogEntry: 重排序日志
  - ErrorLogEntry: 错误日志
  - RAGMetrics: 性能指标
```



---

## 4. Orchestration 模块

### 4.1 模块结构

```
orchestration/
├── workflow/
│   ├── factory.py        # 工作流工厂（创建 StateGraph）
│   ├── state.py          # VizQLState 定义
│   ├── executor.py       # 工作流执行器
│   ├── context.py        # WorkflowContext（运行时上下文）
│   ├── routes.py         # 条件路由函数
│   ├── session_manager.py # 会话管理
│   └── printer.py        # 结果打印
├── middleware/
│   ├── filesystem.py     # 大结果自动保存
│   ├── patch_tool_calls.py # 修复悬空工具调用
│   ├── output_validation.py # LLM 输出验证
│   └── backends/         # 存储后端
└── tools/
    ├── data_model_tool.py  # 数据模型工具
    ├── metadata_tool.py    # 元数据工具
    └── schema_tool.py      # Schema 工具
```

### 4.2 VizQLState（工作流状态）

**状态字段分类**:

| 类别 | 字段 | 说明 |
|------|------|------|
| 对话历史 | messages, answered_questions | 支持 SummarizationMiddleware |
| 用户输入 | question | 原始问题 |
| 意图分类 | is_analysis_question, clarification | 路由控制 |
| 语义层 | semantic_query, mapped_query | Pydantic 对象 |
| 执行层 | vizql_query, query_result | VizQL 查询和结果 |
| 洞察层 | insights, all_insights | 累积洞察 |
| 重规划 | replan_decision, replan_count | 重规划控制 |
| 数据模型 | data_model, dimension_hierarchy | 元数据 |
| 控制流 | current_stage, execution_path | 执行追踪 |
| 错误处理 | errors, warnings | 错误记录 |

**自动累积字段**（使用 `Annotated[List, operator.add]`）:
- messages
- answered_questions
- insights
- all_insights
- errors
- warnings

### 4.3 WorkflowExecutor（工作流执行器）

**执行流程**:
```
1. 获取 Tableau 认证
2. 使用 DataModelCache 加载数据模型（缓存优先）
3. 创建 WorkflowContext
4. 构建初始 State
5. 执行工作流（ainvoke 或 astream_events）
```

**两种执行模式**:
- `run()`: 同步执行，返回 WorkflowResult
- `stream()`: 流式执行，返回 AsyncIterator[WorkflowEvent]

### 4.4 Middleware 栈

| 中间件 | 来源 | 功能 |
|--------|------|------|
| TodoListMiddleware | LangChain | 任务队列管理 |
| SummarizationMiddleware | LangChain | 对话历史摘要（超过 token 阈值时触发） |
| ModelRetryMiddleware | LangChain | LLM 重试（指数退避） |
| ToolRetryMiddleware | LangChain | 工具重试 |
| FilesystemMiddleware | 自定义 | 大结果自动保存到文件 |
| PatchToolCallsMiddleware | 自定义 | 修复悬空工具调用 |
| OutputValidationMiddleware | 自定义 | LLM 输出 JSON 验证 |
| HumanInTheLoopMiddleware | LangChain | 人工确认（可选） |



---

## 5. Platforms 模块

### 5.1 模块结构

```
platforms/
├── base.py              # 平台注册表（PlatformRegistry）
└── tableau/
    ├── adapter.py       # TableauAdapter（BasePlatformAdapter 实现）
    ├── auth.py          # Tableau 认证（JWT/PAT）
    ├── client.py        # Tableau REST API 客户端
    ├── vizql_client.py  # VizQL Data Service 客户端
    ├── query_builder.py # VizQL 查询构建器
    ├── field_mapper.py  # Tableau 字段映射
    ├── metadata.py      # 元数据处理
    └── models/          # Tableau 数据模型
```

### 5.2 平台适配器模式

```
┌─────────────────────────────────────────────────────────────────┐
│                    Platform Adapter Pattern                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  SemanticQuery ──▶ [PlatformAdapter] ──▶ QueryResult            │
│                          │                                       │
│                          ├── validate()                         │
│                          ├── build_query()                      │
│                          └── execute_query()                    │
│                                                                  │
│  实现:                                                           │
│  - TableauAdapter: VizQL Data Service                           │
│  - (未来) PowerBIAdapter: DAX Query                             │
│  - (未来) LookerAdapter: LookML                                 │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 5.3 VizQLClient

**功能**:
- Pydantic 模型验证
- 连接池（sync: requests.Session, async: aiohttp）
- 自动重试（tenacity 指数退避）
- 统一错误处理

**API 端点**:
| 方法 | 端点 | 说明 |
|------|------|------|
| query_datasource | /api/v1/vizql-data-service/query-datasource | 执行查询 |
| read_metadata | /api/v1/vizql-data-service/read-metadata | 读取元数据 |
| get_datasource_model | /api/v1/vizql-data-service/get-datasource-model | 获取数据模型 |

**错误类型**:
| 异常类 | HTTP 状态码 | 说明 |
|--------|------------|------|
| VizQLAuthError | 401/403 | 认证失败 |
| VizQLValidationError | 400 | 验证错误 |
| VizQLRateLimitError | 429 | 速率限制 |
| VizQLServerError | 5xx | 服务器错误 |
| VizQLTimeoutError | - | 超时 |
| VizQLNetworkError | - | 网络错误 |

---

## 6. Infrastructure 模块

### 6.1 模块结构

```
infra/
├── ai/
│   ├── llm.py           # LLM 管理（多提供商）
│   ├── embeddings.py    # Embedding 管理
│   ├── reranker.py      # 重排序器
│   └── rag/             # RAG 子模块
├── storage/
│   ├── langgraph_store.py  # LangGraph SqliteStore 单例
│   ├── data_model_cache.py # 数据模型缓存
│   └── data_model_loader.py # 数据模型加载器
├── config/
│   ├── settings.py      # Pydantic Settings
│   └── tableau_env.py   # 多 Tableau 环境配置
├── certs/
│   ├── manager.py       # 证书管理器
│   ├── fetcher.py       # 证书获取
│   ├── hot_reload.py    # 证书热重载
│   └── self_signed.py   # 自签名证书
├── monitoring/
│   └── callbacks.py     # LangChain 回调
├── utils/
│   └── conversation.py  # 对话工具
├── errors.py            # 错误定义
└── exceptions.py        # 异常类
```

### 6.2 LLM 管理

**支持的提供商**:
| 提供商 | 模型示例 |
|--------|---------|
| local | Ollama 本地模型 |
| openai | gpt-4, gpt-3.5-turbo |
| azure | Azure OpenAI |
| claude | claude-3-opus |
| deepseek | deepseek-chat |
| qwen | qwen-plus |
| zhipu | glm-4 |

### 6.3 存储管理

**LangGraph SqliteStore**:
- 全局单例（get_langgraph_store）
- 命名空间隔离
- TTL 支持
- 用于：数据模型缓存、字段映射缓存、维度层级缓存

---

## 7. Core 模块

### 7.1 模块结构

```
core/
├── interfaces/
│   ├── platform_adapter.py  # BasePlatformAdapter 接口
│   ├── field_mapper.py      # BaseFieldMapper 接口
│   └── query_builder.py     # BaseQueryBuilder 接口
└── models/
    ├── step1.py             # Step1Output
    ├── step2.py             # Step2Output
    ├── observer.py          # ObserverOutput
    ├── parse_result.py      # SemanticParseResult
    ├── query.py             # SemanticQuery
    ├── field_mapping.py     # MappedQuery
    ├── insight.py           # Insight, InsightResult
    ├── replan.py            # ReplanDecision
    ├── data_model.py        # DataModel, FieldMetadata
    ├── dimension_hierarchy.py # DimensionHierarchy
    ├── filters.py           # Filter 类型
    ├── computations.py      # Computation 类型
    └── enums.py             # 枚举定义
```

### 7.2 核心数据流

```
用户问题
    │
    ▼
┌─────────────────┐
│ SemanticParser  │ → SemanticParseResult
│   Step1Output   │     ├── restated_question
│   Step2Output   │     ├── intent
│   ObserverOutput│     └── SemanticQuery (平台无关)
└─────────────────┘
    │
    ▼
┌─────────────────┐
│  FieldMapper    │ → MappedQuery (业务术语 → 技术字段)
└─────────────────┘
    │
    ▼
┌─────────────────┐
│  QueryBuilder   │ → VizQLQuery (平台特定)
└─────────────────┘
    │
    ▼
┌─────────────────┐
│    Execute      │ → ExecuteResult
└─────────────────┘
    │
    ▼
┌─────────────────┐
│    Insight      │ → InsightResult
└─────────────────┘
    │
    ▼
┌─────────────────┐
│   Replanner     │ → ReplanDecision
└─────────────────┘
```

---

## 8. 业界对标与改进建议

### 8.1 对标项目分析

| 项目 | 特点 | 可借鉴之处 |
|------|------|-----------|
| **Vanna.ai** | Text-to-SQL，RAG 增强 | 训练数据管理、SQL 生成优化 |
| **LangChain SQL Agent** | 通用 SQL Agent | 工具设计、错误恢复 |
| **Dataherald** | 企业级 Text-to-SQL | 元数据管理、多数据源 |
| **SQLCoder** | 专用 SQL 模型 | 微调策略、Prompt 工程 |
| **Chat2DB** | 多数据库支持 | UI/UX、会话管理 |
| **Tableau Pulse** | 自动洞察 | 渐进式分析、异常检测 |

### 8.2 改进建议

#### 8.2.1 短期改进（1-2 周）

| 改进项 | 说明 | 参考 |
|--------|------|------|
| **Prometheus 指标** | 添加 workflow_duration, llm_latency, cache_hit_rate | Dataherald |
| **请求追踪** | X-Request-ID, trace_id 贯穿日志 | OpenTelemetry |
| **速率限制** | slowapi/fastapi-limiter | 通用实践 |
| **查询缓存** | 相同问题缓存结果 | Vanna.ai |

#### 8.2.2 中期改进（1-2 月）

| 改进项 | 说明 | 参考 |
|--------|------|------|
| **Schema Linking** | 增强字段映射准确性 | SQLCoder, RESDSQL |
| **Self-Correction** | 查询执行失败时自动修复 | LangChain SQL Agent |
| **Few-Shot Learning** | 动态选择相似示例 | Vanna.ai |
| **Query Decomposition** | 复杂问题分解 | DIN-SQL |

#### 8.2.3 长期改进（3-6 月）

| 改进项 | 说明 | 参考 |
|--------|------|------|
| **多数据源联邦** | 跨数据源查询 | Dataherald |
| **模型微调** | 领域特定微调 | SQLCoder |
| **协作分析** | 多用户协作 | Tableau Pulse |
| **自然语言反馈** | 用户反馈学习 | RLHF |

### 8.3 架构演进路线图

```
Phase 1: 稳定性增强
├── 添加可观测性（Prometheus + OpenTelemetry）
├── 完善错误处理和降级策略
└── 增加测试覆盖率

Phase 2: 准确性提升
├── Schema Linking 增强
├── Self-Correction 机制
├── Few-Shot 动态选择
└── Query Decomposition

Phase 3: 功能扩展
├── 多数据源支持
├── 协作分析功能
├── 自然语言反馈学习
└── 领域模型微调
```

---

## 9. 总结

### 9.1 架构亮点

1. **LLM 组合架构**: Step1 + Step2 + Observer 模拟人类认知
2. **RAG + LLM 混合**: 三级策略平衡速度和准确性
3. **LangGraph 工作流**: 清晰的节点职责和条件路由
4. **平台适配器模式**: 支持多平台扩展
5. **Middleware 栈**: 复用 LangChain + 自定义扩展

### 9.2 改进优先级

1. **立即执行**: 可观测性（Prometheus + 追踪）
2. **短期计划**: Schema Linking、Self-Correction
3. **中期计划**: Few-Shot、Query Decomposition
4. **长期规划**: 多数据源、协作分析

---

*文档生成时间: 2024-12-21*
*版本: 1.0*
