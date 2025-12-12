# Tableau Assistant 架构文档

## 概述

Tableau Assistant 是一个基于 LangGraph 的智能数据分析助手，通过自然语言理解用户问题，自动生成 VizQL 查询并执行数据分析。

### 核心特性

- **自然语言查询**：将用户问题转换为 VizQL 查询
- **智能重规划**：自动评估分析完整性，生成后续探索问题
- **维度层级推断**：自动识别数据维度的层级关系
- **预热机制**：在看板打开时预加载数据模型，提升响应速度
- **统一上下文管理**：通过 `WorkflowContext` 消除全局变量

---

## 系统架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           Tableau Extension (Vue.js)                     │
│                                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                   │
│  │   App.vue    │  │  ChatView    │  │ TableauStore │                   │
│  └──────────────┘  └──────────────┘  └──────────────┘                   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ HTTP/SSE
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           FastAPI Backend                                │
│                                                                          │
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
│                                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                   │
│  │PreloadService│  │ StoreManager │  │ VizQLClient  │                   │
│  └──────────────┘  └──────────────┘  └──────────────┘                   │
│                                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                   │
│  │  RAG Engine  │  │ LLM Manager  │  │ Embeddings   │                   │
│  └──────────────┘  └──────────────┘  └──────────────┘                   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         External Services                                │
│                                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                   │
│  │ Tableau API  │  │   LLM API    │  │   SQLite     │                   │
│  │ (Metadata,   │  │ (Claude,     │  │ (Cache DB)   │                   │
│  │  VizQL)      │  │  DeepSeek)   │  │              │                   │
│  └──────────────┘  └──────────────┘  └──────────────┘                   │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 目录结构

```
tableau_assistant/
├── src/
│   ├── agents/                    # LLM Agent 节点
│   │   ├── understanding/         # 问题理解 Agent
│   │   ├── field_mapper/          # 字段映射 Agent
│   │   ├── insight/               # 数据洞察 Agent
│   │   ├── replanner/             # 重规划 Agent
│   │   └── dimension_hierarchy/   # 维度层级推断 Agent
│   │
│   ├── nodes/                     # 纯代码节点
│   │   ├── query_builder/         # VizQL 查询构建
│   │   └── execute/               # VizQL 查询执行
│   │
│   ├── workflow/                  # 工作流核心
│   │   ├── context.py             # WorkflowContext 上下文管理
│   │   ├── executor.py            # WorkflowExecutor 执行器
│   │   ├── factory.py             # 工作流工厂
│   │   └── routes.py              # 路由决策
│   │
│   ├── services/                  # 服务层
│   │   └── preload_service.py     # 预热服务
│   │
│   ├── api/                       # API 端点
│   │   ├── chat.py                # 对话 API
│   │   └── preload.py             # 预热 API
│   │
│   ├── models/                    # 数据模型
│   │   ├── metadata/              # 元数据模型
│   │   ├── workflow/              # 工作流状态
│   │   ├── semantic/              # 语义查询模型
│   │   ├── vizql/                 # VizQL 模型
│   │   └── insight/               # 洞察模型
│   │
│   ├── capabilities/              # 能力模块
│   │   ├── storage/               # 存储管理 (StoreManager)
│   │   ├── data_model/            # 数据模型管理
│   │   ├── rag/                   # RAG 检索
│   │   └── date_processing/       # 日期处理
│   │
│   ├── bi_platforms/              # BI 平台集成
│   │   └── tableau/               # Tableau 集成
│   │       ├── auth.py            # 认证管理
│   │       ├── metadata.py        # 元数据服务
│   │       └── vizql_client.py    # VizQL 客户端
│   │
│   ├── tools/                     # LangChain 工具
│   │   ├── metadata_tool.py       # 元数据查询工具
│   │   ├── data_model_tool.py     # 数据模型工具
│   │   └── date_tool.py           # 日期处理工具
│   │
│   ├── model_manager/             # 模型管理
│   │   ├── llm.py                 # LLM 选择器
│   │   ├── embeddings.py          # Embedding 模型
│   │   └── reranker.py            # 重排序模型
│   │
│   ├── middleware/                # 中间件
│   │   ├── filesystem.py          # 文件系统中间件
│   │   └── patch_tool_calls.py    # 工具调用修复
│   │
│   └── config/                    # 配置
│       ├── settings.py            # 应用配置
│       └── model_config.py        # 模型配置
│
├── tests/
│   ├── unit/                      # 单元测试
│   └── integration/               # 集成测试
│
└── docs/                          # 文档
    └── ARCHITECTURE.md            # 本文档
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
```

**关键方法**：
- `is_auth_valid()` - 检查认证是否有效
- `refresh_auth_if_needed()` - 自动刷新过期 token
- `ensure_metadata_loaded()` - 确保数据模型已加载

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

### 3. PreloadService（预热服务）

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

**缓存策略**：
- 维度层级缓存 TTL：24 小时
- 元数据缓存 TTL：1 小时
- 支持强制刷新和手动失效

### 4. StoreManager（存储管理）

基于 SQLite 的统一存储管理器，提供业务数据的持久化存储。

**支持的命名空间**：
- `metadata` - 元数据缓存（24小时 TTL）
- `dimension_hierarchy` - 维度层级缓存（24小时 TTL）
- `data_model` - 数据模型缓存（24小时 TTL）
- `user_preferences` - 用户偏好（永久）
- `question_history` - 问题历史（永久）

```python
store = get_store_manager()

# 元数据操作
store.put_metadata("ds_123", metadata_obj)
metadata = store.get_metadata("ds_123")

# 维度层级操作
store.put_dimension_hierarchy("ds_123", hierarchy_dict)
hierarchy = store.get_dimension_hierarchy("ds_123")
```

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
│  字段映射        │  - 业务术语 → 技术字段
│                 │  - 语义匹配
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  QueryBuilder   │  Pure Code
│  查询构建        │  - 生成 VizQL 查询
│                 │  - 参数验证
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│    Execute      │  Pure Code
│    查询执行      │  - 调用 VizQL API
│                 │  - 结果解析
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│    Insight      │  LLM Agent
│    数据洞察      │  - 分析数据
│                 │  - 生成洞察
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Replanner     │  LLM Agent
│   重规划        │  - 评估完整性
│                 │  - 生成后续问题
└────────┬────────┘
         │
         ▼ (should_replan?)
         │
    ┌────┴────┐
    │  Yes    │  No → END
    │         │
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
| Insight | LLM Agent | ExecuteResult | Insight[] | 分析数据生成洞察 |
| Replanner | LLM Agent | Insight[] | ReplanDecision | 评估完整性，决定是否继续 |

---

## 数据模型

### VizQLState（工作流状态）

```python
class VizQLState(TypedDict):
    # 用户输入
    question: str
    
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
    
    # 重规划
    replan_decision: Optional[ReplanDecision]
    replan_count: int
    
    # 数据模型（工作流启动时加载）
    metadata: Optional[Dict]
    dimension_hierarchy: Optional[Dict]
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
| `/api/chat` | POST | 同步查询（暂未实现） |
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

## 中间件栈

工作流使用以下中间件（按顺序）：

1. **TodoListMiddleware** - 任务队列管理
2. **SummarizationMiddleware** - 自动摘要对话历史
3. **ModelRetryMiddleware** - LLM 调用重试（指数退避）
4. **ToolRetryMiddleware** - 工具调用重试
5. **FilesystemMiddleware** - 大结果自动保存
6. **PatchToolCallsMiddleware** - 修复悬空工具调用
7. **HumanInTheLoopMiddleware** - 人工确认（可选）

---

## 认证机制

### TableauAuthContext

```python
class TableauAuthContext(BaseModel):
    api_key: str              # API Token
    site: str                 # Tableau Site
    domain: str               # Tableau Domain
    auth_method: str          # "jwt" 或 "pat"
    expires_at: datetime      # 过期时间
    
    def is_expired(self, buffer_seconds: int = 60) -> bool:
        """检查是否即将过期"""
```

### 认证流程

1. 工作流启动时获取一次 Tableau token
2. 通过 `RunnableConfig["configurable"]["workflow_context"]` 传递
3. Token 过期时自动刷新（`refresh_auth_if_needed()`）

---

## 缓存策略

| 数据类型 | TTL | 存储位置 | 失效触发 |
|----------|-----|----------|----------|
| 认证 Token | ~2小时 | 内存 | 自动检测过期 |
| 元数据 | 24小时 | SQLite | TTL 过期 |
| 维度层级 | 24小时 | SQLite | TTL 过期 / 手动失效 |
| 数据模型 | 24小时 | SQLite | TTL 过期 |

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
LLM_MODEL_PROVIDER=anthropic  # anthropic, deepseek, qwen
LLM_MODEL_NAME=claude-3-5-sonnet-20241022
TOOLING_LLM_MODEL=claude-3-5-haiku-20241022

# 缓存配置
METADATA_CACHE_TTL=86400
DIMENSION_HIERARCHY_CACHE_TTL=86400

# 工作流配置
MAX_REPLAN_ROUNDS=3
SUMMARIZATION_TOKEN_THRESHOLD=60000
```

---

## 测试

### 运行测试

```bash
# 单元测试
pytest tableau_assistant/tests/unit/ -v

# 集成测试（需要真实环境）
pytest tableau_assistant/tests/integration/ -v

# 特定测试
pytest tableau_assistant/tests/integration/test_preload_service.py -v
pytest tableau_assistant/tests/integration/test_context_flow.py -v
```

### 测试覆盖

- **单元测试**：WorkflowContext、Config 辅助函数
- **集成测试**：预热服务、上下文流程、完整工作流

---

## 开发指南

### 添加新节点

1. 在 `src/agents/` 或 `src/nodes/` 创建节点目录
2. 实现节点函数：`async def my_node(state: VizQLState, config: RunnableConfig) -> Dict`
3. 在 `workflow/factory.py` 中注册节点
4. 更新 `VizQLState` 添加新字段（如需要）

### 添加新工具

1. 在 `src/tools/` 创建工具文件
2. 使用 `@tool` 装饰器定义工具
3. 通过 `get_context(config)` 获取上下文
4. 在 `tools/__init__.py` 中导出

### 添加新 API

1. 在 `src/api/` 创建路由文件
2. 定义 Pydantic 请求/响应模型
3. 在 `main.py` 中注册路由

---

## 版本历史

### v2.0 (2024-12)

- 重构上下文管理，引入 `WorkflowContext`
- 添加预热服务 `PreloadService`
- 移除全局变量和向后兼容代码
- 统一数据模型管理

### v1.0 (2024-11)

- 初始版本
- 6 节点工作流架构
- 基础 VizQL 查询功能
