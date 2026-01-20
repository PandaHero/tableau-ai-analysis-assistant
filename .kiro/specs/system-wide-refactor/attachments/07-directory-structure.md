# 附件 7：目录结构

本文档详细说明重构后的完整项目目录结构。

## 完整目录结构

```
analytics-assistant/
├── src/                          # 源代码根目录
│   ├── __init__.py
│   │
│   ├── api/                      # API 层
│   │   ├── __init__.py
│   │   ├── main.py               # FastAPI 应用入口
│   │   ├── chat.py               # 聊天端点（流式输出）
│   │   ├── cache.py              # 缓存端点
│   │   ├── models.py             # API 请求/响应模型
│   │   └── middleware/           # API 中间件
│   │       ├── __init__.py
│   │       ├── cors.py           # CORS 配置
│   │       ├── auth.py           # 认证中间件
│   │       └── error_handler.py  # 错误处理
│   │
│   ├── core/                     # Core 层（核心领域层）
│   │   ├── __init__.py
│   │   ├── models/               # 领域模型
│   │   │   ├── __init__.py
│   │   │   ├── enums.py          # 枚举类型（IntentType 等）
│   │   │   ├── query.py          # 查询模型（SemanticQuery）
│   │   │   ├── schema.py         # Schema 模型（DataModel, Field）
│   │   │   ├── result.py         # 结果模型（ExecuteResult）
│   │   │   ├── insight.py        # 洞察模型（Insight）
│   │   │   └── replan.py         # 重规划模型（ReplanDecision）
│   │   ├── interfaces/           # 接口定义
│   │   │   ├── __init__.py
│   │   │   ├── platform_adapter.py  # 平台适配器接口
│   │   │   └── data_loader.py    # 数据加载器接口
│   │   ├── exceptions.py         # 核心异常定义
│   │   └── validators.py         # 数据验证器
│   │
│   ├── platform/                 # Platform 层（平台适配层）
│   │   ├── __init__.py
│   │   ├── base.py               # 平台基类
│   │   └── tableau/              # Tableau 平台实现
│   │       ├── __init__.py
│   │       ├── adapter.py        # Tableau 适配器
│   │       ├── client.py         # Tableau API 客户端
│   │       ├── query_builder.py  # VizQL 查询构建器
│   │       ├── data_loader.py    # 数据模型加载器
│   │       └── models.py         # Tableau 特定模型
│   │
│   ├── agents/                   # Agent 层（智能体层）
│   │   ├── __init__.py
│   │   ├── base/                 # 基础组件
│   │   │   ├── __init__.py
│   │   │   ├── node.py           # Agent 节点基类
│   │   │   ├── prompt.py         # Prompt 基类
│   │   │   ├── components.py     # 可复用组件基类
│   │   │   ├── middleware_runner.py  # 中间件运行器
│   │   │   └── error_handler.py  # 错误处理器
│   │   │
│   │   ├── semantic_parser/      # 语义解析器 Agent
│   │   │   ├── __init__.py
│   │   │   ├── node.py           # 主节点（子图入口）
│   │   │   ├── subgraph.py       # LangGraph 子图定义
│   │   │   ├── state.py          # 子图状态
│   │   │   ├── schemas/          # 数据模型（重命名自 models/）
│   │   │   │   ├── __init__.py
│   │   │   │   ├── step1.py      # Step1 输出模型
│   │   │   │   ├── step2.py      # Step2 输出模型
│   │   │   │   └── pipeline.py   # Pipeline 模型
│   │   │   ├── nodes/            # 子图节点
│   │   │   │   ├── __init__.py
│   │   │   │   ├── intent_router.py  # 意图路由节点
│   │   │   │   ├── step1.py      # Step1 节点
│   │   │   │   ├── step2.py      # Step2 节点
│   │   │   │   ├── map_fields.py # 字段映射节点
│   │   │   │   ├── build_query.py    # 查询构建节点
│   │   │   │   ├── execute_query.py  # 查询执行节点
│   │   │   │   ├── react_error_handler.py  # ReAct 错误处理
│   │   │   │   └── exit.py       # 统一退出节点
│   │   │   ├── prompts/          # Prompt 模板
│   │   │   │   ├── __init__.py
│   │   │   │   ├── intent_router.py
│   │   │   │   ├── step1.py
│   │   │   │   ├── step2.py
│   │   │   │   └── react.py
│   │   │   └── components/       # 可复用组件
│   │   │       ├── __init__.py
│   │   │       ├── preprocess.py     # 预处理组件
│   │   │       ├── intent_classifier.py  # 意图分类器
│   │   │       ├── schema_linker.py  # Schema Linking
│   │   │       └── query_validator.py    # 查询验证器
│   │   │
│   │   ├── field_mapper/         # 字段映射器 Agent
│   │   │   ├── __init__.py
│   │   │   ├── node.py           # 主节点（直接使用 ModelManager 和 infra/rag）
│   │   │   ├── prompt.py         # Prompt 模板
│   │   │   └── schemas/          # 数据模型（重命名自 models/）
│   │   │       ├── __init__.py
│   │   │       └── mapping.py
│   │   │   # 注：删除 rag/ 子目录，直接使用 infra/rag
│   │   │   # 注：删除 llm_selector.py，直接使用 ModelManager
│   │   │
│   │   ├── dimension_hierarchy/  # 维度层级 Agent
│   │   │   ├── __init__.py
│   │   │   ├── node.py           # 主节点（整合 LLM 推断逻辑）
│   │   │   ├── inference.py      # 推断引擎
│   │   │   ├── prompt.py         # Prompt 模板
│   │   │   ├── cache_storage.py  # 缓存存储
│   │   │   ├── rag_retriever.py  # RAG 检索器
│   │   │   ├── seed_data.py      # 种子数据
│   │   │   └── schemas/          # 数据模型（重命名自 models/）
│   │   │       ├── __init__.py
│   │   │       └── hierarchy.py
│   │   │   # 注：删除 llm_inference.py，逻辑整合到 node.py
│   │   │
│   │   ├── insight/              # 洞察生成 Agent
│   │   │   ├── __init__.py
│   │   │   ├── node.py           # 主节点（子图入口）
│   │   │   ├── subgraph.py       # LangGraph 子图定义
│   │   │   ├── state.py          # 子图状态
│   │   │   ├── schemas/          # 数据模型（重命名自 models/）
│   │   │   │   ├── __init__.py
│   │   │   │   ├── profile.py    # 数据画像
│   │   │   │   └── insight.py    # 洞察模型
│   │   │   ├── nodes/            # 子图节点
│   │   │   │   ├── __init__.py
│   │   │   │   ├── profiler.py   # 数据画像节点
│   │   │   │   ├── director.py   # 导演节点
│   │   │   │   └── analyzer.py   # 分析器节点
│   │   │   ├── prompts/          # Prompt 模板
│   │   │   │   ├── __init__.py
│   │   │   │   ├── profiler.py
│   │   │   │   ├── director.py
│   │   │   │   └── analyzer.py
│   │   │   └── components/       # 可复用组件
│   │   │       ├── __init__.py
│   │   │       ├── statistical_analyzer.py
│   │   │       └── pattern_detector.py
│   │   │
│   │   └── replanner/            # 重规划 Agent
│   │       ├── __init__.py
│   │       ├── node.py           # 主节点
│   │       ├── prompt.py         # Prompt 模板
│   │       └── schemas/          # 数据模型（重命名自 models/）
│   │           ├── __init__.py
│   │           └── decision.py
│   │
│   ├── orchestration/            # Orchestration 层（编排层）
│   │   ├── __init__.py
│   │   ├── workflow/             # 工作流
│   │   │   ├── __init__.py
│   │   │   ├── main_workflow.py  # 主工作流图
│   │   │   ├── state.py          # 工作流状态定义
│   │   │   ├── nodes.py          # 工作流节点
│   │   │   └── routing.py        # 路由逻辑
│   │   └── middleware/           # 中间件系统
│   │       ├── __init__.py
│   │       ├── base.py           # 中间件基类（LangChain AgentMiddleware）
│   │       ├── filesystem.py     # 文件系统中间件（提供文件工具 + 大型结果缓存）
│   │       ├── patch_tool_calls.py   # 工具调用修复中间件（修复悬空 tool_calls）
│   │       ├── output_validation.py  # 输出验证中间件（最终质量闸门）
│   │       ├── backends/         # Filesystem 后端实现
│   │       │   ├── __init__.py
│   │       │   ├── protocol.py   # Backend 协议定义
│   │       │   ├── state.py      # StateBackend（存储到 LangGraph 状态）
│   │       │   └── utils.py      # 工具函数
│   │       ├── retry.py          # 重试中间件（可选）
│   │       └── summarization.py  # 对话摘要中间件（可选）
│   │   # 注：删除 tools/ 目录，直接调用 Agent 节点，避免重复抽象
│   │
│   ├── infra/                    # Infrastructure 层（基础设施层）
│   │   ├── __init__.py
│   │   │
│   │   ├── ai/                   # AI 模块
│   │   │   ├── __init__.py
│   │   │   ├── model_manager.py  # 模型管理器（统一管理多模型，单例模式）
│   │   │   ├── custom_llm.py     # 自定义 LLM 客户端（非 OpenAI 兼容）
│   │   │   ├── embeddings.py     # Embedding 客户端（ZhipuEmbedding, OpenAIEmbedding）
│   │   │   ├── json_mode_adapter.py  # JSON Mode 适配器（多提供商支持）
│   │   │   ├── prompt_manager.py # Prompt 管理器
│   │   │   └── token_counter.py  # Token 计数器
│   │   │
│   │   ├── rag/                  # RAG 模块
│   │   │   ├── __init__.py
│   │   │   ├── base.py           # 检索器基类
│   │   │   ├── vector_retriever.py   # 向量检索器
│   │   │   ├── keyword_retriever.py  # 关键词检索器（BM25）
│   │   │   ├── exact_retriever.py    # 精确匹配检索器
│   │   │   ├── hybrid_retriever.py   # 混合检索器
│   │   │   ├── vector_index_manager.py   # 统一向量索引管理器
│   │   │   ├── exact_index_manager.py    # 精确匹配索引管理器
│   │   │   ├── reranker.py       # 重排序器
│   │   │   └── chunker.py        # 文本分块器
│   │   │   # 注：Embedding 缓存移到 storage/managers/embedding_cache.py
│   │   │   # 注：向量存储移到 storage/vector/（faiss_store.py, chroma_store.py）
│   │   │
│   │   ├── storage/              # 存储模块
│   │   │   ├── __init__.py
│   │   │   ├── base.py           # 存储后端抽象接口（BaseStore）
│   │   │   ├── factory.py        # 存储工厂（根据配置创建存储实例）
│   │   │   │
│   │   │   ├── backends/         # 存储后端实现（封装 LangChain/LangGraph Store）
│   │   │   │   ├── __init__.py
│   │   │   │   ├── sqlite.py     # SQLite 后端（开发环境，封装 LangGraph SqliteStore）
│   │   │   │   ├── redis.py      # Redis 后端（生产环境，封装 LangChain RedisStore）
│   │   │   │   └── memory.py     # 内存后端（测试环境，封装 LangChain InMemoryStore）
│   │   │   │
│   │   │   ├── managers/         # 存储管理器（业务逻辑层）
│   │   │   │   ├── __init__.py
│   │   │   │   ├── cache_manager.py      # 缓存管理器基类
│   │   │   │   ├── data_model_cache.py   # 数据模型缓存（结构化数据 → SQLite/Redis）
│   │   │   │   ├── session_manager.py    # 会话管理器（结构化数据 → SQLite/Redis）
│   │   │   │   ├── golden_query_store.py # Golden Query 存储（结构化数据 → SQLite/Redis）
│   │   │   │   ├── embedding_cache.py    # Embedding 缓存（向量数据 → FAISS/Chroma）
│   │   │   │   └── file_store.py         # 文件存储（大型结果 → 文件系统）
│   │   │   │   # 注：file_store.py 被 FilesystemMiddleware 调用
│   │   │   │
│   │   │   └── vector/           # 向量存储（专用于 Embedding）
│   │   │       ├── __init__.py
│   │   │       ├── base.py       # 向量存储抽象接口
│   │   │       ├── faiss_store.py    # FAISS 向量存储（向量数据 → FAISS）
│   │   │       └── chroma_store.py   # Chroma 向量存储（向量数据 → Chroma）
│   │   │   # 注：不重复造轮子，封装 LangChain/LangGraph 自带的存储抽象
│   │   │   # 数据分类：
│   │   │   #   - 结构化数据（缓存、会话、配置）→ SQLite/Redis（backends/）
│   │   │   #   - 向量数据（Embeddings、字段索引）→ FAISS/Chroma（vector/）
│   │   │   #   - 大文件（查询结果）→ 文件系统（managers/file_store.py）
│   │   │
│   │   ├── config/               # 配置模块
│   │   │   ├── __init__.py
│   │   │   ├── settings.py       # 配置定义（Pydantic Settings）
│   │   │   ├── validator.py      # 配置验证器
│   │   │   ├── runtime.py        # 运行时配置
│   │   │   └── loader.py         # 配置加载器
│   │   │
│   │   ├── observability/        # 可观测性模块
│   │   │   ├── __init__.py
│   │   │   ├── logger.py         # 结构化日志（structlog）
│   │   │   ├── metrics.py        # Prometheus 指标
│   │   │   ├── tracing.py        # OpenTelemetry 追踪
│   │   │   ├── alerting.py       # 告警系统
│   │   │   └── dashboard.py      # 监控面板
│   │   │
│   │   ├── certs/                # 证书管理
│   │   │   ├── __init__.py
│   │   │   └── manager.py
│   │   │
│   │   ├── errors.py             # 基础设施错误定义
│   │   └── exceptions.py         # 基础设施异常
│   │
│   └── main.py                   # 应用入口（启动脚本）
│
├── tests/                        # 测试目录
│   ├── __init__.py
│   │
│   ├── unit/                     # 单元测试
│   │   ├── __init__.py
│   │   ├── agents/               # Agent 单元测试
│   │   │   ├── __init__.py
│   │   │   ├── test_semantic_parser.py
│   │   │   ├── test_field_mapper.py
│   │   │   ├── test_dimension_hierarchy.py
│   │   │   ├── test_insight.py
│   │   │   └── test_replanner.py
│   │   ├── core/                 # Core 层单元测试
│   │   │   ├── __init__.py
│   │   │   ├── test_models.py
│   │   │   └── test_validators.py
│   │   ├── infra/                # Infrastructure 单元测试
│   │   │   ├── __init__.py
│   │   │   ├── test_model_manager.py
│   │   │   ├── test_retriever.py
│   │   │   └── test_cache.py
│   │   └── orchestration/        # Orchestration 单元测试
│   │       ├── __init__.py
│   │       └── test_middleware.py
│   │
│   ├── property/                 # 属性测试（Property-Based Testing）
│   │   ├── __init__.py
│   │   ├── test_preprocess_properties.py     # 预处理属性测试
│   │   ├── test_cache_properties.py          # 缓存属性测试
│   │   ├── test_config_properties.py         # 配置属性测试
│   │   ├── test_serialization_properties.py  # 序列化属性测试
│   │   └── test_retrieval_properties.py      # 检索属性测试
│   │
│   ├── integration/              # 集成测试
│   │   ├── __init__.py
│   │   ├── test_workflow.py      # 工作流集成测试
│   │   ├── test_semantic_parser_subgraph.py  # 子图集成测试
│   │   ├── test_end_to_end.py    # 端到端测试
│   │   └── test_platform_integration.py      # 平台集成测试
│   │
│   ├── fixtures/                 # 测试夹具
│   │   ├── __init__.py
│   │   ├── data.py               # 测试数据
│   │   ├── mocks.py              # Mock 对象
│   │   └── factories.py          # 数据工厂
│   │
│   └── test_outputs/             # 测试输出文件
│       └── .gitkeep
│
├── data/                         # 数据目录
│   ├── indexes/                  # 索引文件
│   │   ├── dimension_patterns/   # 维度模式索引
│   │   └── field_mappings/       # 字段映射索引
│   └── langgraph_store.db        # LangGraph 持久化存储
│
├── docs/                         # 文档
│   ├── architecture.md           # 架构文档
│   ├── api.md                    # API 文档
│   ├── deployment.md             # 部署文档
│   ├── development.md            # 开发指南
│   └── testing.md                # 测试指南
│
├── scripts/                      # 脚本
│   ├── seed_data.py              # 种子数据生成
│   └── build_indexes.py          # 索引构建脚本
│
├── config/                       # 配置文件
│   ├── development.yaml          # 开发环境配置
│   ├── staging.yaml              # 预发布环境配置
│   └── production.yaml           # 生产环境配置
│
├── frontend/                     # 前端代码（Vue.js）
│   ├── src/
│   ├── public/
│   ├── package.json
│   └── vite.config.ts
│
├── .env.example                  # 环境变量示例
├── .gitignore                    # Git 忽略文件
├── requirements.txt              # Python 依赖（pip）
├── pyproject.toml                # 项目配置（Poetry）
├── pytest.ini                    # Pytest 配置
├── Dockerfile                    # Docker 镜像
├── docker-compose.yml            # Docker Compose 配置
├── start.py                      # 快速启动脚本
└── README.md                     # 项目说明
```

## 目录结构说明

### 1. src/ - 源代码根目录

所有源代码放在 src 目录下，遵循 Python 最佳实践。

### 2. 分层清晰

严格按照五层架构组织：
- **API 层** → **Orchestration 层** → **Agent 层** → **Platform 层** → **Core 层**
- **Infrastructure 层**（横向）

### 3. Agent 子目录

每个 Agent 都有完整的子目录结构：
- `schemas/` - 数据模型（重命名自 models/，避免与 Python models 概念冲突）
- `nodes/` - 子图节点（如果是子图）
- `prompts/` - Prompt 模板
- `components/` - 可复用组件

### 4. Infrastructure 横向

基础设施层提供横向服务，被所有层使用：
- `ai/` - AI 模型管理
- `rag/` - RAG 检索
- `storage/` - 存储服务
- `config/` - 配置管理
- `observability/` - 可观测性

### 5. 测试完整

包含三个层次的测试：
- `unit/` - 单元测试
- `property/` - 属性测试
- `integration/` - 集成测试

### 6. 配置分离

配置文件按环境分离：
- `development.yaml` - 开发环境
- `staging.yaml` - 预发布环境
- `production.yaml` - 生产环境

### 7. 数据隔离

数据文件（索引、数据库）独立存放在 data 目录。

---

## 与现有项目的映射

| 现有路径 | 重构后路径 | 说明 |
|---------|-----------|------|
| `tableau_assistant/src/` | `analytics-assistant/src/` | 源代码根目录 |
| `tableau_assistant/src/api/` | `analytics-assistant/src/api/` | API 层 |
| `tableau_assistant/src/core/` | `analytics-assistant/src/core/` | Core 层 |
| `tableau_assistant/src/platforms/` | `analytics-assistant/src/platform/` | Platform 层 |
| `tableau_assistant/src/agents/` | `analytics-assistant/src/agents/` | Agent 层 |
| `tableau_assistant/src/orchestration/` | `analytics-assistant/src/orchestration/` | Orchestration 层 |
| `tableau_assistant/src/infra/` | `analytics-assistant/src/infra/` | Infrastructure 层 |
| `tableau_assistant/tests/` | `analytics-assistant/tests/` | 测试目录 |
| `tableau_assistant/data/` | `analytics-assistant/data/` | 数据目录 |

---

## 文件命名规范

### Python 文件

- 模块文件：`snake_case.py`（如 `model_manager.py`）
- 类文件：与类名对应（如 `ModelManager` → `model_manager.py`）
- 测试文件：`test_*.py`（如 `test_model_manager.py`）

### 配置文件

- YAML 配置：`environment.yaml`（如 `development.yaml`）
- 环境变量：`.env`、`.env.example`
- 项目配置：`pyproject.toml`、`pytest.ini`

### 文档文件

- Markdown 文档：`kebab-case.md`（如 `architecture-layers.md`）
- README：`README.md`

---

### 3. 重复代码重构说明

根据重复代码分析，以下组件已被重构或移除：

**已移除的重复代码**：
- ❌ `agents/field_mapper/llm_selector.py` - 移除，逻辑整合到 `node.py` 中
- ❌ `agents/field_mapper/rag/` - 移除，直接使用 `infra/rag`
- ❌ `agents/dimension_hierarchy/llm_inference.py` - 移除，整合到 `node.py` 中
- ❌ `orchestration/tools/` - 移除，直接调用 Agent 节点，避免重复抽象
- ❌ Redis 缓存依赖 - 移除，统一使用 LangGraph SqliteStore

**统一的基础设施组件**：
- ✅ `infra/storage/base.py` - 统一存储后端接口
- ✅ `infra/storage/managers/cache_manager.py` - 统一缓存管理器基类
- ✅ `infra/rag/vector_index_manager.py` - 统一向量索引管理器（合并 FieldIndexer 和 FieldValueIndexer）
- ✅ `infra/rag/exact_index_manager.py` - 精确匹配索引管理器
- ✅ `infra/storage/managers/embedding_cache.py` - 统一 Embedding 缓存（移除 RAG 模块的重复实现）

**重构后的缓存类**（继承 CacheManager）：
- `managers/data_model_cache.py` - 数据模型缓存
- `managers/embedding_cache.py` - Embedding 缓存（统一管理，移除 RAG 模块的重复实现）
- `managers/session_manager.py` - 会话管理
- `managers/golden_query_store.py` - Golden Query 存储
- `managers/file_store.py` - 文件存储

**重构后的存储类**：
- `managers/golden_query_store.py` - Golden Query 存储
- `managers/session_manager.py` - 会话管理
- `managers/file_store.py` - 文件存储

**命名规范优化**：
- ✅ `models/` → `schemas/` - 避免与 Python models 概念冲突
- ✅ `storage/` 子目录化 - 创建 `backends/`、`managers/` 和 `vector/` 子目录，提升组织清晰度

**重构后的检索器层级**：
```
业务检索器（Agent 层）
  ↓
混合检索器（Infra 层）
  ↓
基础检索器（Infra 层）
  ↓
索引管理器（Infra 层）
```

---

## 存储架构详细说明

### 设计原则

1. **不重复造轮子**：封装 LangChain/LangGraph 自带的存储抽象，不重新实现
2. **支持多后端**：SQLite（开发）、Redis（生产）、FAISS/Chroma（向量）
3. **明确数据分类**：结构化数据、向量数据、大文件分别存储
4. **简化部署**：项目未上线，不需要版本化存储和数据迁移

### 存储分层架构

```
┌─────────────────────────────────────────────────────────┐
│              业务层（managers/）                          │
│  - CacheManager（缓存管理器基类）                         │
│  - DataModelCache（数据模型缓存）                         │
│  - SessionManager（会话管理）                             │
│  - GoldenQueryStore（Golden Query 存储）                  │
│  - FileStore（文件存储）                                  │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│              抽象层（base.py, factory.py）                │
│  - BaseStore（存储后端接口）                              │
│  - StorageFactory（根据配置创建实例）                     │
└─────────────────────────────────────────────────────────┘
                          ↓
┌──────────────────────────┬──────────────────────────────┐
│   后端层（backends/）     │    向量层（vector/）          │
│  - SqliteStore 封装       │  - FAISS 封装                 │
│  - RedisStore 封装        │  - Chroma 封装                │
│  - InMemoryStore 封装     │                               │
└──────────────────────────┴──────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│         LangChain/LangGraph 原生存储                      │
│  - SqliteStore（LangGraph）                               │
│  - RedisStore（LangChain）                                │
│  - InMemoryStore（LangChain）                             │
│  - FAISS（LangChain VectorStore）                         │
│  - Chroma（LangChain VectorStore）                        │
└─────────────────────────────────────────────────────────┘
```

### 数据分类和存储策略

| 数据类型 | 存储位置 | 后端选择 | 说明 |
|---------|---------|---------|------|
| **结构化数据** | `backends/` | SQLite/Redis | 缓存、会话、配置等 |
| **向量数据** | `vector/` | FAISS/Chroma | Embeddings、字段索引 |
| **大文件** | `managers/file_store.py` | 文件系统 | 查询结果、大型数据 |

#### 1. 结构化数据（backends/）

**存储内容**：
- 数据模型元数据（DataModelCache）
- 用户会话数据（SessionManager）
- Golden Query（GoldenQueryStore）
- 配置和设置

**后端选择**：
- **开发环境**：SQLite（`backends/sqlite.py`）- **默认**
  - 封装 `LangGraph SqliteStore`
  - 无需额外依赖
  - 支持 TTL 和 namespace
- **生产环境**：Redis（`backends/redis.py`）- **可选**
  - 封装 `LangChain RedisStore`
  - 高性能、分布式
  - 支持 TTL 和 namespace
  - 通过配置启用

**实现方式**：
```python
# backends/sqlite.py
from langgraph.store.sqlite import SqliteStore

class SqliteBackend(BaseStore):
    def __init__(self, db_path: str):
        self._store = SqliteStore(db_path)
    
    async def put(self, namespace: Tuple, key: str, value: Dict):
        await self._store.aput(namespace, key, value)
```

#### 2. 向量数据（vector/）

**存储内容**：
- 字段 Embeddings（用于字段映射）
- 字段值 Embeddings（用于维度层级）
- 文档 Embeddings（用于 RAG 检索）

**后端选择**：
- **FAISS**（`vector/faiss_store.py`）
  - 封装 `LangChain FAISS VectorStore`
  - 本地存储，快速检索
  - 适合中小规模数据
- **Chroma**（`vector/chroma_store.py`）
  - 封装 `LangChain Chroma VectorStore`
  - 支持持久化和分布式
  - 适合大规模数据

**实现方式**：
```python
# vector/faiss_store.py
from langchain.vectorstores import FAISS

class FAISSVectorStore(BaseVectorStore):
    def __init__(self, embedding_function):
        self._store = FAISS(embedding_function=embedding_function)
    
    async def add_embeddings(self, texts: List[str], embeddings: List[List[float]]):
        await self._store.aadd_embeddings(texts, embeddings)
```

#### 3. 大文件（managers/file_store.py）

**存储内容**：
- 大型查询结果（> 1MB）
- 导出的数据文件
- 临时文件

**实现方式**：
- 直接使用文件系统
- 支持分页读取（offset/limit）
- 自动清理过期文件

### 存储工厂（factory.py）

**职责**：根据配置创建存储实例

**实现方式**：
```python
# factory.py
class StorageFactory:
    @staticmethod
    def create_backend(config: StorageConfig) -> BaseStore:
        if config.backend == "sqlite":
            return SqliteBackend(config.db_path)
        elif config.backend == "redis":
            return RedisBackend(config.redis_url)
        elif config.backend == "memory":
            return MemoryBackend()
        else:
            raise ValueError(f"Unknown backend: {config.backend}")
    
    @staticmethod
    def create_vector_store(config: VectorConfig) -> BaseVectorStore:
        if config.vector_db == "faiss":
            return FAISSVectorStore(config.embedding_function)
        elif config.vector_db == "chroma":
            return ChromaVectorStore(config.embedding_function)
        else:
            raise ValueError(f"Unknown vector DB: {config.vector_db}")
```

### 缓存管理器基类（managers/cache_manager.py）

**职责**：统一的缓存管理接口

**功能**：
- 自动 Hash 计算
- TTL 管理
- 序列化/反序列化
- 命名空间隔离

**实现方式**：
```python
# managers/cache_manager.py
class CacheManager:
    def __init__(self, backend: BaseStore, namespace: Tuple[str, ...]):
        self.backend = backend
        self.namespace = namespace
    
    async def get(self, key: str) -> Optional[Dict]:
        return await self.backend.get(self.namespace, key)
    
    async def put(self, key: str, value: Dict, ttl: Optional[int] = None):
        await self.backend.put(self.namespace, key, value, ttl=ttl)
    
    def compute_hash(self, *args) -> str:
        # 统一的 Hash 计算逻辑
        return hashlib.sha256(str(args).encode()).hexdigest()
```

### 配置示例

**开发环境**（`config/development.yaml`）：
```yaml
storage:
  backend: sqlite
  db_path: data/langgraph_store.db
  ttl_minutes: 1440  # 24 小时

vector:
  vector_db: faiss
  index_path: data/indexes/
```

**生产环境**（`config/production.yaml`）：
```yaml
storage:
  backend: redis
  redis_url: redis://localhost:6379/0
  ttl_minutes: 1440  # 24 小时

vector:
  vector_db: chroma
  chroma_url: http://localhost:8000
```

### 关键优势

✅ **不重复造轮子**：封装 LangChain/LangGraph 自带的存储，不重新实现  
✅ **支持多后端**：SQLite（开发）、Redis（生产）、FAISS/Chroma（向量）  
✅ **明确数据分类**：结构化数据、向量数据、大文件分别存储  
✅ **统一接口**：`CacheManager` 提供统一的缓存管理接口  
✅ **易于扩展**：通过 `StorageFactory` 轻松添加新后端  
✅ **简化部署**：开发环境使用 SQLite，无需额外依赖  

---

## 关键组件说明

### 1. 中间件系统（orchestration/middleware/）

中间件系统基于 **LangChain AgentMiddleware** 实现，提供可复用的横切关注点处理。

**LangChain 框架自带中间件**（5个）：
- **TodoListMiddleware**：任务队列管理
- **SummarizationMiddleware**：自动摘要对话历史（长对话压缩）
- **ModelRetryMiddleware**：LLM 调用自动重试（指数退避）
- **ToolRetryMiddleware**：工具调用自动重试（指数退避）
- **HumanInTheLoopMiddleware**：人工确认（可选）

**自定义中间件**（基于 deepagents 设计）：
- **FilesystemMiddleware**：
  - 提供文件系统工具（ls, read_file, write_file, edit_file, glob, grep）
  - 自动将大型工具结果保存到文件系统（避免 context 溢出）
  - 支持分页读取（offset/limit）
  - 基于 deepagents 设计
  - **注意**：FilesystemMiddleware 提供文件操作工具接口，实际的文件存储实现由 `infra/storage/managers/file_store.py` 提供

**重构后评估的中间件**：
- **PatchToolCallsMiddleware**：修复悬空工具调用（LangGraph 可能已内置处理）
- **OutputValidationMiddleware**：输出验证（格式校验已在组件级完成）

### 2. ModelManager（infra/ai/model_manager.py）

统一的模型管理器，提供：

- **多模型支持**：管理多个 LLM 和 Embedding 模型
- **多提供商**：OpenAI、Azure、智谱、自定义端点
- **智能路由**：
  - Azure OpenAI → AzureChatOpenAI
  - 非 OpenAI 兼容 → CustomLLMChat
  - OpenAI 兼容 → ChatOpenAI
- **持久化**：配置存储在 LangGraph SqliteStore
- **健康检查**：定期检查模型可用性
- **使用统计**：记录请求次数、成功率、延迟

### 3. 统一存储层（infra/storage/）

**StorageBackend 接口**：
- 提供统一的存储抽象
- 支持多种后端（SqliteStore, Redis, Memory）
- 便于测试和替换实现

**CacheManager 基类**：
- 统一的缓存管理接口
- 自动处理 Hash 计算、TTL 管理、序列化
- 所有缓存类继承此基类

**主要存储后端**：
- **LangGraph SqliteStore**：主要持久化后端
- 移除 Redis 依赖，简化部署

### 4. 统一索引和检索（infra/rag/）

**VectorIndexManager**：
- 合并 FieldIndexer 和 FieldValueIndexer
- 统一 Embedding 缓存策略
- 统一持久化策略

**检索器层级**：
- **基础检索器**：VectorRetriever, KeywordRetriever, ExactRetriever
- **混合检索器**：HybridRetriever（融合多路召回）
- **业务检索器**：DimensionRAGRetriever, SchemaLinkingRetriever（Agent 层）

---

## 总结

这个目录结构：

✅ **清晰的分层**：五层架构一目了然  
✅ **模块化设计**：每个模块职责明确  
✅ **消除重复代码**：统一存储、缓存、索引、检索组件  
✅ **易于导航**：按功能组织，便于查找  
✅ **可扩展性**：易于添加新的 Agent 或模块  
✅ **测试友好**：测试目录与源代码目录对应  
✅ **部署简化**：移除 Redis 依赖，统一使用 SqliteStore  
✅ **命名规范**：`schemas/` 替代 `models/`，避免命名冲突  
✅ **组织优化**：`storage/` 子目录化（`cache/` 和 `stores/`），提升清晰度  

**关键优化**：
- 删除 `orchestration/tools/` - 与 Agent 节点功能重复
- 删除 `agents/field_mapper/rag/` - 直接使用 `infra/rag`
- 删除 `agents/field_mapper/llm_selector.py` - 简单封装，无额外价值
- 删除 `agents/dimension_hierarchy/llm_inference.py` - 整合到 `node.py`
- `models/` → `schemas/` - 避免与 Python models 概念冲突
- `storage/` 子目录化 - 创建 `cache/` 和 `stores/` 子目录

通过这个结构，开发者可以快速理解系统架构，找到需要修改的代码，并添加新功能。重构后的代码减少了 15-20% 的重复代码，提升了可维护性和性能。
