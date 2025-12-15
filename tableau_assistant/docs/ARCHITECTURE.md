# Tableau Assistant 架构文档

## 概述

Tableau Assistant 是一个基于 LangGraph 的智能数据分析助手，通过自然语言理解用户问题，自动生成 VizQL 查询并执行数据分析。

### 核心特性

- **自然语言查询**：将用户问题转换为 VizQL 查询
- **智能重规划**：自动评估分析完整性，生成后续探索问题
- **维度层级推断**：自动识别数据维度的层级关系
- **预热机制**：在看板打开时预加载数据模型
- **统一上下文管理**：通过 `WorkflowContext` 消除全局变量
- **企业级中间件栈**：8 层中间件提供重试、校验、转存等能力
- **渐进式洞察分析**：双 LLM 协作的 AI 宝宝吃饭模式

---

## 系统架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           Tableau Extension (Vue.js)                     │
└─────────────────────────────────────────────────────────────────────────┘
                                    │ HTTP/SSE
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           FastAPI Backend                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                   │
│  │  /api/chat   │  │ /api/preload │  │  /api/health │                   │
│  └──────────────┘  └──────────────┘  └──────────────┘                   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         Workflow Layer (LangGraph)                       │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                      Middleware Stack (8 层)                     │    │
│  │  TodoList → Summarization → ModelRetry → ToolRetry →            │    │
│  │  Filesystem → PatchToolCalls → OutputValidation → HITL          │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                      WorkflowExecutor                            │    │
│  │  - 创建 WorkflowContext                                          │    │
│  │  - 加载数据模型 (ensure_metadata_loaded)                          │    │
│  │  - 执行工作流 (run/stream)                                        │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                    │                                     │
│                                    ▼                                     │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                      StateGraph (6 Nodes)                        │    │
│  │                                                                  │    │
│  │  START → Understanding → FieldMapper → QueryBuilder              │    │
│  │                                            │                     │    │
│  │                                            ▼                     │    │
│  │          END ← Replanner ← Insight ← Execute                     │    │
│  │           ↑                                                      │    │
│  │           └──────── (replan loop) ────────┘                      │    │
│  └─────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         Services & Capabilities                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                   │
│  │PreloadService│  │ StoreManager │  │ VizQLClient  │                   │
│  └──────────────┘  └──────────────┘  └──────────────┘                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                   │
│  │  RAG Engine  │  │ LLM Manager  │  │ Embeddings   │                   │
│  └──────────────┘  └──────────────┘  └──────────────┘                   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         External Services                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                   │
│  │ Tableau API  │  │   LLM API    │  │   SQLite     │                   │
│  │ (Metadata,   │  │ (DeepSeek,   │  │ (Cache DB)   │                   │
│  │  VizQL)      │  │  Qwen, etc)  │  │              │                   │
│  └──────────────┘  └──────────────┘  └──────────────┘                   │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 目录结构

```
tableau_assistant/
├── src/
│   ├── agents/                    # LLM Agent 节点
│   │   ├── base/                  # 基础工具（LLM调用、Middleware Runner）
│   │   ├── understanding/         # 问题理解 Agent
│   │   ├── field_mapper/          # 字段映射 Agent (RAG+LLM)
│   │   ├── insight/               # 数据洞察 Agent
│   │   ├── replanner/             # 重规划 Agent
│   │   └── dimension_hierarchy/   # 维度层级推断 Agent
│   │
│   ├── nodes/                     # 纯代码节点
│   │   ├── query_builder/         # VizQL 查询构建
│   │   └── execute/               # VizQL 查询执行
│   │
│   ├── components/                # 功能组件
│   │   └── insight/               # 渐进式洞察分析
│   │       ├── coordinator.py     # 分析协调器（AI 宝宝吃饭主循环）
│   │       ├── profiler.py        # 数据画像
│   │       ├── statistical_analyzer.py  # Phase 1 统计/ML 分析
│   │       ├── anomaly_detector.py      # 异常检测
│   │       ├── chunker.py         # 智能分块
│   │       ├── analyzer.py        # Phase 2 双 LLM 分析
│   │       ├── accumulator.py     # 洞察累积
│   │       └── synthesizer.py     # 洞察合成
│   │
│   ├── workflow/                  # 工作流核心
│   │   ├── context.py             # WorkflowContext 上下文管理
│   │   ├── executor.py            # WorkflowExecutor 执行器
│   │   ├── factory.py             # 工作流工厂（含中间件配置）
│   │   └── routes.py              # 路由决策
│   │
│   ├── middleware/                # 自定义中间件
│   │   ├── filesystem.py          # 大结果自动转存
│   │   ├── output_validation.py   # LLM 输出校验
│   │   ├── patch_tool_calls.py    # 工具调用修复
│   │   └── backends/              # 中间件后端（State Backend）
│   │
│   ├── capabilities/              # 能力模块
│   │   ├── rag/                   # RAG 语义映射
│   │   │   ├── semantic_mapper.py # 两阶段检索
│   │   │   ├── field_indexer.py   # 字段索引
│   │   │   ├── retriever.py       # 向量+BM25 检索
│   │   │   ├── reranker.py        # LLM 重排序
│   │   │   └── assembler.py       # 知识组装
│   │   ├── storage/               # StoreManager 持久化
│   │   ├── date_processing/       # 日期处理
│   │   └── data_model/            # 数据模型管理
│   │
│   ├── services/                  # 服务层
│   │   └── preload_service.py     # 预热服务
│   │
│   ├── bi_platforms/              # BI 平台集成
│   │   └── tableau/
│   │       ├── auth.py            # JWT/PAT 认证
│   │       ├── metadata.py        # 元数据服务
│   │       └── vizql_client.py    # VizQL 客户端
│   │
│   ├── model_manager/             # 模型管理
│   │   ├── llm.py                 # LLM 选择器
│   │   ├── embeddings.py          # Embedding 模型
│   │   └── reranker.py            # 重排序器选择器
│   │
│   ├── models/                    # Pydantic 数据模型
│   │   ├── semantic/              # SemanticQuery
│   │   ├── vizql/                 # VizQLQuery
│   │   ├── field_mapper/          # MappedQuery
│   │   ├── insight/               # Insight 模型
│   │   ├── replanner/             # ReplanDecision
│   │   ├── metadata/              # Metadata 模型
│   │   ├── workflow/              # VizQLState
│   │   └── api/                   # API 模型
│   │
│   ├── tools/                     # LangChain 工具
│   ├── api/                       # FastAPI 端点
│   └── config/                    # 配置
│
├── cert_manager/                  # SSL 证书管理
├── tests/                         # 测试
└── docs/                          # 文档
```

---

## 核心组件

### 1. WorkflowContext（上下文管理）

`WorkflowContext` 是统一的依赖容器，通过 `RunnableConfig` 传递给所有节点和工具。

```python
class WorkflowContext(BaseModel):
    auth: TableauAuthContext          # Tableau 认证
    store: StoreManager               # 持久化存储
    datasource_luid: str              # 数据源 LUID
    metadata: Optional[Metadata]      # 完整数据模型
    max_replan_rounds: int = 3        # 最大重规划轮数
    user_id: Optional[str] = None     # 用户 ID
    metadata_load_status: Optional[MetadataLoadStatus]  # 加载状态
```

**关键方法**：
- `is_auth_valid()` - 检查认证是否有效
- `refresh_auth_if_needed()` - 自动刷新过期 token
- `ensure_metadata_loaded()` - 确保数据模型已加载（含维度层级推断）

**使用方式**：
```python
# 在 WorkflowExecutor 中创建
ctx = WorkflowContext(auth=auth_ctx, store=store, datasource_luid="ds_123")
ctx = await ctx.ensure_metadata_loaded()
config = create_workflow_config(thread_id, ctx)

# 在节点中获取
async def my_node(state, config):
    ctx = get_context_or_raise(config)
    metadata = ctx.metadata
    middleware = get_middleware_from_config(config)
```

### 2. WorkflowExecutor（执行器）

封装工作流执行逻辑，提供简洁的对外接口。

```python
executor = WorkflowExecutor(
    datasource_luid="ds_123",
    max_replan_rounds=3,
)

# 同步执行
result = await executor.run("各地区销售额是多少")

# 流式执行
async for event in executor.stream("各地区销售额是多少"):
    if event.type == EventType.TOKEN:
        print(event.content, end="")
```

### 3. 中间件栈

工作流使用 8 层中间件（按顺序执行）：

| 中间件 | 功能 | 来源 |
|--------|------|------|
| TodoListMiddleware | 任务队列管理 | LangChain |
| SummarizationMiddleware | 对话历史自动总结（防止上下文溢出） | LangChain |
| ModelRetryMiddleware | LLM 调用指数退避重试 | LangChain |
| ToolRetryMiddleware | 工具调用重试 | LangChain |
| FilesystemMiddleware | 大结果自动转存到文件 | 自定义 |
| PatchToolCallsMiddleware | 修复悬空工具调用 | 自定义 |
| OutputValidationMiddleware | LLM 输出 JSON/Schema 校验 | 自定义 |
| HumanInTheLoopMiddleware | 人工确认（可选） | LangChain |

**中间件配置**：
```python
def create_middleware_stack(config: Dict) -> List[AgentMiddleware]:
    middleware = []
    
    # 1. TodoListMiddleware
    middleware.append(TodoListMiddleware())
    
    # 2. SummarizationMiddleware
    middleware.append(SummarizationMiddleware(
        model=chat_model,
        trigger=("tokens", config["summarization_token_threshold"]),
        keep=("messages", config["messages_to_keep"]),
    ))
    
    # 3. ModelRetryMiddleware（指数退避）
    middleware.append(ModelRetryMiddleware(
        max_retries=config["model_max_retries"],
        initial_delay=1.0,
        backoff_factor=2.0,
        jitter=True,
    ))
    
    # 4. ToolRetryMiddleware
    middleware.append(ToolRetryMiddleware(...))
    
    # 5. FilesystemMiddleware
    middleware.append(FilesystemMiddleware(
        tool_token_limit_before_evict=config["filesystem_token_limit"],
    ))
    
    # 6. PatchToolCallsMiddleware
    middleware.append(PatchToolCallsMiddleware())
    
    # 7. OutputValidationMiddleware
    middleware.append(OutputValidationMiddleware(
        strict=False,
        retry_on_failure=True,
    ))
    
    # 8. HumanInTheLoopMiddleware（可选）
    if config.get("interrupt_on"):
        middleware.append(HumanInTheLoopMiddleware(...))
    
    return middleware
```

### 4. 渐进式洞察分析（AI 宝宝吃饭）

两阶段分析架构：

**Phase 1: 统计/ML 分析（无 LLM）**
```python
class StatisticalAnalyzer:
    def analyze(self, data, profile) -> DataInsightProfile:
        # 分布检测
        distribution_type = self._detect_distribution(values)
        
        # 帕累托分析
        pareto_ratio = self._calculate_pareto_ratio(values)
        
        # 异常检测
        anomaly_indices = self._detect_anomalies(values)
        
        # 聚类分析
        clusters = self._perform_clustering(data)
        
        # 推荐分块策略
        strategy = self._recommend_chunking_strategy(profile)
        
        return DataInsightProfile(...)
```

**Phase 2: 双 LLM 协作**
```python
class AnalysisCoordinator:
    async def _progressive_analysis_two_phase(self, data, context, profile, insight_profile):
        # 1. 使用 Phase 1 推荐的分块策略
        chunks = self.chunker.chunk_by_strategy(data, insight_profile.recommended_chunking_strategy)
        
        while remaining_chunks:
            # 2. 分析师 LLM：分析当前数据块
            new_insights = await self.analyzer.analyze_chunk_with_analyst(
                chunk=next_chunk,
                insight_profile=insight_profile,
                existing_insights=accumulated_insights,
            )
            
            # 3. 主持人 LLM：决定下一步
            next_decision, quality = await self.analyzer.decide_next_with_coordinator(
                accumulated_insights=accumulated_insights,
                remaining_chunks=remaining_chunks,
            )
            
            # 4. 早停判断
            if not next_decision.should_continue:
                break
        
        # 5. 合成最终结果
        return self.synthesizer.synthesize(accumulated_insights)
```

### 5. PreloadService（预热服务）

在 Tableau 看板打开时触发，后台异步执行维度层级推断。

```python
service = get_preload_service()

# 启动预热
task_id, status = await service.start_preload("ds_123")

# 查询状态
status_info = service.get_status(task_id)

# 获取结果
result = service.get_result("ds_123")
```

### 6. StoreManager（存储管理）

基于 SQLite 的统一存储管理器：

**支持的命名空间**：
- `metadata` - 元数据缓存（24小时 TTL）
- `dimension_hierarchy` - 维度层级缓存（24小时 TTL）
- `data_model` - 数据模型缓存（24小时 TTL）
- `field_mapping` - 字段映射缓存（24小时 TTL）
- `user_preferences` - 用户偏好（永久）

---

## 工作流节点

### 节点流程图

```
START
  │
  ▼
┌─────────────────┐
│  Understanding  │  LLM Agent
│  问题理解        │  - 问题分类
│                 │  - 语义解析
└────────┬────────┘
         │
         ▼ (is_analysis_question?)
         │
    ┌────┴────┐
    │  Yes    │  No → END
    ▼         │
┌─────────────────┐
│  FieldMapper    │  RAG + LLM
│  字段映射        │  - 两阶段检索
│                 │  - LLM Fallback
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  QueryBuilder   │  Pure Code
│  查询构建        │  - 生成 VizQL
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│    Execute      │  Pure Code
│    查询执行      │  - 调用 VizQL API
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│    Insight      │  双 LLM 协作
│    数据洞察      │  - Phase 1 统计
│                 │  - Phase 2 LLM
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Replanner     │  LLM Agent
│   重规划        │  - 完成度评估
│                 │  - 探索问题生成
└────────┬────────┘
         │
         ▼ (should_replan?)
         │
    ┌────┴────┐
    │  Yes    │  No → END
    └────┬────┘
         │
         ▼
    (回到 Understanding)
```

### 节点详情

| 节点 | 类型 | 输入 | 输出 | 说明 |
|------|------|------|------|------|
| Understanding | LLM Agent | question | SemanticQuery | 问题分类和语义理解 |
| FieldMapper | RAG + LLM | SemanticQuery | MappedQuery | 业务术语映射到技术字段 |
| QueryBuilder | Pure Code | MappedQuery | VizQLQuery | 生成 VizQL 查询 |
| Execute | Pure Code | VizQLQuery | ExecuteResult | 执行查询并返回结果 |
| Insight | 双 LLM | ExecuteResult | Insight[] | 渐进式洞察分析 |
| Replanner | LLM Agent | Insight[] | ReplanDecision | 评估完整性，决定是否继续 |

---

## 数据模型

### VizQLState（工作流状态）

```python
class VizQLState(TypedDict):
    # 用户输入
    question: str
    messages: List[BaseMessage]
    
    # 问题分类
    is_analysis_question: bool
    
    # 语义层
    semantic_query: Optional[SemanticQuery]
    mapped_query: Optional[MappedQuery]
    vizql_query: Optional[VizQLQuery]
    query_result: Optional[ExecuteResult]
    
    # 洞察
    insights: List[Insight]
    all_insights: List[Insight]
    data_insight_profile: Optional[DataInsightProfile]
    
    # 重规划
    replan_decision: Optional[ReplanDecision]
    replan_count: int
    replan_history: List[Dict]
    answered_questions: List[str]
    
    # 数据模型（工作流启动时加载）
    metadata: Optional[Metadata]
    dimension_hierarchy: Optional[Dict]
    current_dimensions: List[str]
```

### Metadata（元数据模型）

```python
class Metadata(BaseModel):
    datasource_luid: str
    datasource_name: str
    datasource_description: Optional[str]
    fields: List[FieldMetadata]
    field_count: int
    dimension_hierarchy: Optional[Dict]  # 维度层级
    data_model: Optional[DataModel]      # 逻辑表关系
```

---

## API 端点

### 对话 API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/chat/stream` | POST | 流式查询（SSE） |
| `/api/boost-question` | POST | 问题优化 |
| `/api/health` | GET | 健康检查 |

### 预热 API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/preload/dimension-hierarchy` | POST | 启动预热 |
| `/api/preload/status/{task_id}` | GET | 查询任务状态 |
| `/api/preload/invalidate` | POST | 使缓存失效 |
| `/api/preload/cache-status/{datasource_luid}` | GET | 查询缓存状态 |

---

## 配置说明

### 环境变量

```bash
# Tableau 配置
TABLEAU_DOMAIN=your-tableau-server.com
TABLEAU_SITE=your-site
TABLEAU_JWT_SECRET=your-jwt-secret
DATASOURCE_LUID=your-datasource-luid

# LLM 配置
LLM_MODEL_PROVIDER=deepseek  # local, openai, deepseek, zhipu, qwen
TOOLING_LLM_MODEL=deepseek-chat

# 中间件配置
SUMMARIZATION_TOKEN_THRESHOLD=20000
MESSAGES_TO_KEEP=10
MODEL_MAX_RETRIES=3
TOOL_MAX_RETRIES=3
FILESYSTEM_TOKEN_LIMIT=20000

# 缓存配置
METADATA_CACHE_TTL=86400
DIMENSION_HIERARCHY_CACHE_TTL=86400

# 工作流配置
MAX_REPLAN_ROUNDS=3
```

---

## 缓存策略

| 数据类型 | TTL | 存储位置 | 失效触发 |
|----------|-----|----------|----------|
| 认证 Token | ~2小时 | 内存 | 自动检测过期 |
| 元数据 | 24小时 | SQLite | TTL 过期 |
| 维度层级 | 24小时 | SQLite | TTL 过期 / 手动失效 |
| 字段映射 | 24小时 | SQLite | TTL 过期 |

---

## 测试

```bash
# 单元测试
pytest tableau_assistant/tests/unit/ -v

# 集成测试
pytest tableau_assistant/tests/integration/ -v

# 特定测试
pytest tableau_assistant/tests/integration/test_e2e_simple_aggregation.py -v
pytest tableau_assistant/tests/integration/test_context_flow.py -v
```

---

## 开发指南

### 添加新节点

1. 在 `src/agents/` 或 `src/nodes/` 创建节点目录
2. 实现节点函数：
```python
async def my_node(state: VizQLState, config: RunnableConfig) -> Dict:
    # 获取上下文和中间件
    ctx = get_context_or_raise(config)
    middleware = get_middleware_from_config(config)
    
    # 实现逻辑
    result = await call_llm_with_tools(llm, messages, tools, middleware=middleware)
    
    return {"output_field": result}
```
3. 在 `workflow/factory.py` 中注册节点

### 添加新中间件

1. 在 `src/middleware/` 创建中间件文件
2. 继承 `AgentMiddleware` 基类
3. 实现钩子方法：
```python
class MyMiddleware(AgentMiddleware):
    async def aafter_model(self, response, request, state, runtime):
        # 在 LLM 调用后执行
        return {"my_field": processed_result}
    
    async def aafter_agent(self, state, runtime):
        # 在 Agent 完成后执行
        return None
```
4. 在 `workflow/factory.py` 的 `create_middleware_stack()` 中添加

### 添加新工具

1. 在 `src/tools/` 创建工具文件
2. 使用 `@tool` 装饰器定义工具
3. 通过 `get_context(config)` 获取上下文

---

## 版本历史

### v2.2.0 (2024-12)
- 添加 OutputValidationMiddleware
- 完善中间件栈集成
- 优化渐进式洞察分析

### v2.1.0 (2024-12)
- 重构上下文管理，引入 WorkflowContext
- 添加预热服务 PreloadService
- 移除全局变量

### v2.0.0 (2024-11)
- 6 节点工作流架构
- RAG + LLM 混合字段映射
- 渐进式洞察分析

---

**最后更新**: 2024-12-14
