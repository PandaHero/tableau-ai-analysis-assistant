# 任务清单：BI 分析助手系统级重构

## 概述

本文档提供详细的实施任务清单，包含：
1. 现有文件到目标模块的映射关系
2. 每个阶段的具体文件迁移路径
3. 可执行的任务清单（按现有代码结构组织）

**重要说明**：
- ✅ **允许破坏性重构**：不受旧接口约束
- ✅ **可回滚能力**：每个阶段独立部署，Git Tag 标记
- ✅ **分阶段实施**：7 个阶段，每个阶段独立可测试
- 📁 **新项目目录**：`analytics-assistant/`（不修改原始 `tableau_assistant/` 代码）

---

## 文件映射表

### 现有目录结构 → 目标目录结构

| 现有路径 | 目标路径 | 迁移阶段 | 说明 |
|---------|---------|---------|------|
| **Infrastructure 层** | | | |
| `tableau_assistant/src/infra/ai/llm.py` | `analytics-assistant/src/infra/ai/model_manager.py` | 阶段 1 | 重构为 ModelManager 单例 |
| `tableau_assistant/src/infra/ai/embeddings.py` | `analytics-assistant/src/infra/ai/embeddings.py` | 阶段 1 | 保留，整合到 ModelManager |
| `tableau_assistant/src/infra/ai/json_mode_adapter.py` | `analytics-assistant/src/infra/ai/json_mode_adapter.py` | 阶段 1 | 保留，整合到 ModelManager |
| `tableau_assistant/src/infra/rag/retriever.py` | `analytics-assistant/src/infra/rag/retriever.py` | 阶段 1 | 重构为 UnifiedRetriever |
| `tableau_assistant/src/infra/rag/field_indexer.py` | `analytics-assistant/src/infra/rag/vector_index_manager.py` | 阶段 1 | 重命名并扩展功能 |
| `tableau_assistant/src/infra/rag/reranker.py` | `analytics-assistant/src/infra/rag/reranker.py` | 阶段 1 | 保留 |
| `tableau_assistant/src/infra/storage/langgraph_store.py` | `analytics-assistant/src/infra/storage/langgraph_store.py` | 阶段 1 | 保留 |
| `tableau_assistant/src/infra/storage/redis_cache.py` | 删除 | 阶段 1 | 移除，使用 LangGraph Store |
| `tableau_assistant/src/infra/storage/*.py` | `analytics-assistant/src/infra/storage/cache/*.py` | 阶段 1 | 重组为子目录结构 |
| `tableau_assistant/src/infra/storage/*.py` | `analytics-assistant/src/infra/storage/stores/*.py` | 阶段 1 | 重组为子目录结构 |
| `tableau_assistant/src/infra/config/settings.py` | `analytics-assistant/src/infra/config/settings.py` | 阶段 1 | 保留并扩展 |
| `tableau_assistant/src/infra/observability/logger.py` | `analytics-assistant/src/infra/observability/logger.py` | 阶段 1 | 保留并扩展 |
| **Core 层** | | | |
| `tableau_assistant/src/core/models/*.py` | `analytics-assistant/src/core/models/*.py` | 阶段 2 | 扩展领域模型 |
| `tableau_assistant/src/core/interfaces/*.py` | `analytics-assistant/src/core/interfaces/*.py` | 阶段 2 | 新增接口定义 |
| **Platform 层** | | | |
| `tableau_assistant/src/platforms/tableau/*.py` | `analytics-assistant/src/platform/tableau/*.py` | 阶段 2 | 重命名目录并重构 |
| **Agent 层** | | | |
| `tableau_assistant/src/agents/base/node.py` | `analytics-assistant/src/agents/base/node.py` | 阶段 3 | 保留工具函数 |
| `tableau_assistant/src/agents/base/middleware_runner.py` | `analytics-assistant/src/agents/base/middleware_runner.py` | 阶段 3 | 保留 |
| `tableau_assistant/src/agents/semantic_parser/models/*.py` | `analytics-assistant/src/agents/semantic_parser/schemas/*.py` | 阶段 3 | 重命名 models → schemas |
| `tableau_assistant/src/agents/field_mapper/models/*.py` | `analytics-assistant/src/agents/field_mapper/schemas/*.py` | 阶段 3 | 重命名 models → schemas |
| `tableau_assistant/src/agents/field_mapper/llm_selector.py` | 删除 | 阶段 3 | 移除，使用 ModelManager |
| `tableau_assistant/src/agents/field_mapper/rag/*.py` | 删除 | 阶段 3 | 移除，直接使用 infra/rag |
| `tableau_assistant/src/agents/dimension_hierarchy/models/*.py` | `analytics-assistant/src/agents/dimension_hierarchy/schemas/*.py` | 阶段 3 | 重命名 models → schemas |
| `tableau_assistant/src/agents/dimension_hierarchy/llm_inference.py` | 删除 | 阶段 3 | 移除，整合到 node.py |
| `tableau_assistant/src/agents/insight/models/*.py` | `analytics-assistant/src/agents/insight/schemas/*.py` | 阶段 3 | 重命名 models → schemas |
| `tableau_assistant/src/agents/replanner/models/*.py` | `analytics-assistant/src/agents/replanner/schemas/*.py` | 阶段 3 | 重命名 models → schemas |
| `tableau_assistant/src/agents/semantic_parser/*.py` | `analytics-assistant/src/agents/semantic_parser/*.py` | 阶段 4 | 重构优化 |
| **Orchestration 层** | | | |
| `tableau_assistant/src/orchestration/workflow/*.py` | `analytics-assistant/src/orchestration/workflow/*.py` | 阶段 5 | 保留并优化 |
| `tableau_assistant/src/orchestration/middleware/*.py` | `analytics-assistant/src/orchestration/middleware/*.py` | 阶段 5 | 保留并扩展 |
| `tableau_assistant/src/orchestration/tools/*.py` | 删除 | 阶段 5 | 移除，直接调用 Agent 节点 |

---


## 阶段 1：基础设施层重构（2 周）

### 目标
建立统一的基础设施服务，消除重复代码。

### 1.1 ModelManager 重构

**现有文件**：
- `tableau_assistant/src/infra/ai/llm.py` - 当前的 LLM 获取函数
- `tableau_assistant/src/infra/ai/embeddings.py` - Embedding 客户端
- `tableau_assistant/src/infra/ai/json_mode_adapter.py` - JSON Mode 适配器

**目标文件**：
- `analytics-assistant/src/infra/ai/model_manager.py` - 统一的模型管理器（单例）

**任务清单**：
- [x] 1.1.1 创建 ModelManager 类（单例模式）
  - [x] 支持多模型配置（LLM + Embedding）
  - [x] 支持多提供商（OpenAI、Azure、智谱、自定义）
  - [x] 智能路由（根据提供商选择客户端）
  - [x] 持久化配置（使用 CacheManager）
- [x] 1.1.2 整合 Embedding 客户端到 ModelManager
  - [x] 保留 `embeddings.py` 的实现
  - [x] 通过 ModelManager 统一管理
- [x] 1.1.3 整合 JSON Mode 适配器到 ModelManager
  - [x] 保留 `json_mode_adapter.py` 的实现
  - [x] 通过 ModelManager 统一调用
- [x] 1.1.4 更新 `agents/base/node.py` 的 `get_llm()` 函数
  - [x] 调用 ModelManager.get_llm()
  - [x] 保持 Agent 层的便捷接口
- [x] 1.1.5 单元测试（覆盖率 ≥ 80%）
  - [x] 测试多模型配置
  - [x] 测试智能路由
  - [x] 测试持久化

**迁移路径**：
```
1. 创建 model_manager.py（新文件）
2. 保留 llm.py、embeddings.py、json_mode_adapter.py
3. 更新 agents/base/node.py 调用 ModelManager
4. 测试通过后，标记 llm.py 为 deprecated
```

---

### 1.2 RAG 检索器重构

**现有文件**：
- `tableau_assistant/src/infra/rag/retriever.py` - 混合检索器
- `tableau_assistant/src/infra/rag/field_indexer.py` - 字段索引器
- `tableau_assistant/src/infra/rag/reranker.py` - 重排序器

**目标文件**：
- `analytics-assistant/src/infra/rag/retriever.py` - UnifiedRetriever（重构）
- `analytics-assistant/src/infra/rag/vector_index_manager.py` - 统一索引器（重命名）
- `analytics-assistant/src/infra/rag/reranker.py` - 保留

**任务清单**：
- [x] 1.2.1 重构 UnifiedRetriever
  - [x] 保留 EmbeddingRetriever、KeywordRetriever、HybridRetriever
  - [x] 优化 RRF 融合算法
  - [x] 添加精确匹配优先逻辑
- [x] 1.2.2 重命名 field_indexer.py → vector_index_manager.py
  - [x] 扩展为通用索引器（支持多种数据类型）
  - [x] 合并 FieldIndexer 和 FieldValueIndexer 功能
- [x] 1.2.3 整合 FieldValueIndexer 到 VectorIndexManager
  - [x] 合并重复功能
  - [x] 统一索引构建接口
- [x] 1.2.4 单元测试（覆盖率 ≥ 80%）
  - [x] 测试混合检索
  - [x] 测试 RRF 融合
  - [x] 测试精确匹配

**迁移路径**：
```
1. 重构 retriever.py（原地修改）
2. 重命名 field_indexer.py → vector_index_manager.py
3. 更新所有引用（agents/field_mapper、agents/dimension_hierarchy）
4. 测试通过后，删除旧的 FieldValueIndexer
```

---

### 1.3 存储和缓存统一

**现有文件**：
- `tableau_assistant/src/infra/storage/langgraph_store.py` - LangGraph SqliteStore
- `tableau_assistant/src/infra/storage/redis_cache.py` - Redis 缓存（待删除）
- `tableau_assistant/src/agents/dimension_hierarchy/cache_storage.py` - 维度层级缓存
- 多个分散的缓存和存储文件

**目标文件**：
- `analytics-assistant/src/infra/storage/base.py` - 存储后端抽象接口（BaseStore）
- `analytics-assistant/src/infra/storage/factory.py` - 存储工厂（根据配置创建实例）
- `analytics-assistant/src/infra/storage/backends/sqlite.py` - SQLite 后端（封装 LangGraph SqliteStore）
- `analytics-assistant/src/infra/storage/backends/redis.py` - Redis 后端（封装 LangChain RedisStore）
- `analytics-assistant/src/infra/storage/backends/memory.py` - 内存后端（封装 LangChain InMemoryStore）
- `analytics-assistant/src/infra/storage/managers/cache_manager.py` - 统一缓存管理器基类
- `analytics-assistant/src/infra/storage/managers/data_model_cache.py` - 数据模型缓存
- `analytics-assistant/src/infra/storage/managers/session_manager.py` - 会话管理器
- `analytics-assistant/src/infra/storage/managers/golden_query_store.py` - Golden Query 存储
- `analytics-assistant/src/infra/storage/managers/file_store.py` - 文件存储
- `analytics-assistant/src/infra/storage/vector/base.py` - 向量存储抽象接口
- `analytics-assistant/src/infra/storage/vector/faiss_store.py` - FAISS 向量存储
- `analytics-assistant/src/infra/storage/vector/chroma_store.py` - Chroma 向量存储

**任务清单**：
- [ ] 1.3.1 创建存储抽象层
  - [x] 创建 `base.py`（BaseStore 接口）
  - [x] 创建 `factory.py`（StorageFactory）
  - [x] 定义统一的存储接口（get, put, delete, list_keys）
- [ ] 1.3.2 实现存储后端（封装 LangChain/LangGraph Store）
  - [x] 实现 `backends/sqlite.py`（封装 LangGraph SqliteStore）
  - [x] 实现 `backends/redis.py`（封装 LangChain RedisStore）
  - [x] 实现 `backends/memory.py`（封装 LangChain InMemoryStore）
  - [x] 支持 TTL 和 namespace 隔离
- [ ] 1.3.3 实现向量存储（封装 LangChain VectorStore）
  - [x] 实现 `vector/base.py`（BaseVectorStore 接口）
  - [x] 实现 `vector/faiss_store.py`（封装 LangChain FAISS）
  - [x] 实现 `vector/chroma_store.py`（封装 LangChain Chroma）
  - [x] 支持 Embedding 缓存
- [ ] 1.3.4 创建 CacheManager（统一缓存管理器）
  - [x] 实现 `managers/cache_manager.py`（基类）
  - [x] 支持自动 Hash 计算
  - [x] 支持 TTL 配置
  - [x] 支持命名空间隔离
- [-] 1.3.5 实现业务存储管理器
  - [x] **重要决策**：大部分业务存储管理器不需要实现，直接使用 `CacheManager` 即可
  - [x] **VectorIndexManager 重构**：
    - [x] **问题**：VectorIndexManager 与 BaseVectorStore 功能重复
    - [x] **解决方案**：删除 VectorIndexManager，创建 FieldVectorStore 封装 BaseVectorStore
    - [x] **实现**：
      - [x] 创建 `index_builder.py`（提取 IndexConfig 和 build_index_text）
      - [x] 创建 `field_vector_store.py`（封装 BaseVectorStore，提供字段检索接口）
      - [x] 更新 `retriever.py`（使用 FieldVectorStore 替代 VectorIndexManager）
      - [x] 更新 `__init__.py`（导出新模块）
      - [x] 删除 `vector_index_manager.py`
      - [x] 更新测试文件（test_retriever.py, test_field_vector_store.py）
    - [x] **参考**：见 `analytics_assistant/docs/cache_persistence_strategy.md`
  - [x] **缓存/持久化策略**：
    - [x] 分析老项目缓存模式（`tableau_assistant/`）
    - [x] 创建策略文档：`analytics_assistant/docs/cache_persistence_strategy.md`
    - [x] 更新 YAML 配置：`analytics_assistant/config/app.yaml`
    - [ ] 数据模型缓存：使用 `CacheManager("data_model", ttl=1440)`
    - [ ] 维度层级缓存：使用 `CacheManager("dimension_hierarchy_cache", ttl=null)`
    - [ ] RAG 模式元数据：使用 `CacheManager("dimension_patterns_metadata", ttl=null)`
    - [ ] Embedding 缓存：使用 `CacheManager("embedding", ttl=60)`
    - [ ] 会话管理：使用 `CacheManager("session", ttl=10080)`
  - [x] **不需要实现的管理器**（直接使用 CacheManager）：
    - ~~实现 `managers/data_model_cache.py`~~（使用 CacheManager）
    - ~~实现 `managers/golden_query_store.py`~~（使用 CacheManager）
    - ~~实现 `managers/embedding_cache.py`~~（使用 CacheManager）
    - ~~实现 `managers/file_store.py`~~（直接使用文件系统操作）
  - [ ]* **可选：SessionManager 实现**（直接使用 CacheManager + LangGraph Checkpointer）：
    - [ ]* 实现 `managers/session_manager.py`（会话管理，支持多轮对话）
      - [ ]* 创建会话（create_session）
      - [ ]* 获取会话（get_session）
      - [ ]* 更新会话（update_session）
      - [ ]* 清理过期会话（cleanup_expired_sessions，7天）
      - [ ]* 集成 LangGraph Checkpointer（SqliteSaver/RedisSaver）
- [x] 1.3.6 删除重复的 Embedding 缓存
  - [x] 删除 `infra/rag/embedding_cache.py`（与存储模块重复）- 文件不存在，无需删除
  - [x] 更新所有引用，使用 `managers/embedding_cache.py` - 无引用需要更新
- [x] 1.3.7 移除 Redis 直接依赖
  - [x] 移除项目中对 Redis 的直接依赖 - 项目中无 Redis 依赖
  - [x] 保留 Redis 后端实现（作为可选后端）- 不需要
  - [x] 更新配置，默认使用 SQLite - 已使用 SQLite
  - [x] 更新文档，说明如何启用 Redis - 不需要
- [-] 1.3.8 迁移维度层级缓存到 CacheManager
  - [-] 更新 `agents/dimension_hierarchy/cache_storage.py` - 新项目中尚未创建此 Agent
  - [-] 使用 CacheManager 替代直接调用 LangGraph Store - 待 Agent 迁移时实现
- [x] 1.3.9 单元测试（覆盖率 ≥ 80%）
  - [x] 测试 BaseStore 接口 - 使用 LangGraph SqliteStore
  - [x] 测试 SQLite/Redis/Memory 后端 - 测试 SQLite 单例
  - [x] 测试 FAISS/Chroma 向量存储 - 测试 FAISS 创建
  - [x] 测试 CacheManager 功能 - 测试基本操作、get_or_compute、stats
  - [x] 测试 Embedding 缓存 - 通过 CacheManager 实现
  - [x] 测试 TTL 功能 - CacheManager 支持 TTL
  - [x] 测试命名空间隔离 - 测试 namespace 隔离

**迁移路径**：
```
1. 创建存储抽象层（base.py, factory.py）
2. 实现存储后端（backends/）
3. 实现向量存储（vector/）
4. 创建 CacheManager（managers/cache_manager.py）
5. 实现业务存储管理器（managers/），包括 embedding_cache.py
6. 删除 RAG 模块的重复 embedding_cache.py
7. 删除 Redis 相关代码
8. 更新所有缓存调用（agents/dimension_hierarchy）
9. 单元测试
```

**数据分类说明**：
- **结构化数据**（缓存、会话、配置）→ SQLite/Redis（backends/）
- **向量数据**（Embeddings、字段索引）→ FAISS/Chroma（vector/）
- **大文件**（查询结果）→ 文件系统（managers/file_store.py）

**重要说明**：
- ❌ **不需要 vNext 版本化存储**：项目未上线，不需要灰度发布和版本隔离
- ❌ **不需要数据迁移**：项目未上线，不存在历史数据迁移问题
- ✅ **Embedding 缓存统一**：删除 `infra/rag/embedding_cache.py`，统一使用 `managers/embedding_cache.py`
- ✅ **FilesystemMiddleware 和 FileStore 关系**：FilesystemMiddleware 提供文件操作工具接口，FileStore 提供实际的文件存储实现

---

### 1.4 可观测性增强

**现有文件**：
- `tableau_assistant/src/infra/observability/logger.py` - 结构化日志

**目标文件**：
- `analytics-assistant/src/infra/observability/logger.py` - 扩展
- `analytics-assistant/src/infra/observability/metrics.py` - 新建（Prometheus）
- `analytics-assistant/src/infra/observability/tracing.py` - 新建（OpenTelemetry）

**任务清单**：
- [ ] 1.4.1 扩展结构化日志
  - [ ] 添加请求 ID 追踪
  - [ ] 添加性能日志
- [ ] 1.4.2 实现 Prometheus 指标
  - [ ] LLM 调用次数、延迟、成功率
  - [ ] 缓存命中率
  - [ ] 工作流执行时间
- [ ] 1.4.3 实现 OpenTelemetry 追踪
  - [ ] 分布式追踪
  - [ ] Span 标记
- [ ] 1.4.4 集成测试
  - [ ] 验证指标采集
  - [ ] 验证追踪链路

**迁移路径**：
```
1. 扩展 logger.py（原地修改）
2. 创建 metrics.py（新文件）
3. 创建 tracing.py（新文件）
4. 在关键路径添加指标和追踪
```

---

### 阶段 1 验证标准

- ✅ 单元测试覆盖率 ≥ 80%
- ✅ 集成测试通过
- ✅ 性能测试：检索延迟 < 300ms
- ✅ ModelManager 支持多模型配置
- ✅ UnifiedRetriever 支持混合检索
- ✅ CacheManager 支持 Redis 迁移
- ✅ 可观测性指标正常采集

### 阶段 1 回滚方案

- Git Tag: `v1.0-infra`
- 回滚命令: `git checkout v1.0-infra`
- 配置回滚：恢复配置文件到上一版本

---


## 阶段 2：Core 层和 Platform 层（2 周）

### 目标
建立领域模型和平台适配器，实现关注点分离。

### 2.1 Core 层领域模型

**现有文件**：
- `tableau_assistant/src/core/models/*.py` - 现有领域模型

**目标文件**：
- `analytics-assistant/src/core/models/query.py` - SemanticQuery 模型
- `analytics-assistant/src/core/models/schema.py` - DataModel, Field 模型
- `analytics-assistant/src/core/models/result.py` - ExecuteResult 模型
- `analytics-assistant/src/core/models/insight.py` - Insight 模型
- `analytics-assistant/src/core/models/replan.py` - ReplanDecision 模型
- `analytics-assistant/src/core/interfaces/platform_adapter.py` - 平台适配器接口（新建）
- `analytics-assistant/src/core/interfaces/data_loader.py` - 数据加载器接口（新建）

**任务清单**：
- [x] 2.1.1 扩展 SemanticQuery 模型
  - [x] 添加验证逻辑（Pydantic field_validator）
  - [x] 添加序列化方法（Pydantic model_dump）
- [x] 2.1.2 扩展 DataModel 和 Field 模型
  - [x] 创建 DimensionField、MeasureField、SortSpec
  - [x] 创建 Computation 联合类型（LOD + TableCalc）
  - [x] 创建 Filter 联合类型
- [x] 2.1.3 创建 BasePlatformAdapter 接口
  - [x] 定义 execute_query() 方法
  - [x] 定义 build_query() 方法
  - [x] 定义 validate_query() 方法
- [x] 2.1.4 创建 BaseQueryBuilder 和 BaseFieldMapper 接口
  - [x] 定义 build() 方法
  - [x] 定义 validate() 方法
  - [x] 定义 map() 和 map_single_field() 方法
- [-] 2.1.5 单元测试（覆盖率 ≥ 80%）
  - [-] 测试模型验证 - 待后续补充
  - [-] 测试序列化 - 待后续补充

**迁移路径**：
```
1. 扩展现有模型（原地修改）
2. 创建接口文件（新文件）
3. 更新所有引用
```

---

### 2.2 Platform 层 Tableau 适配器

**现有文件**：
- `tableau_assistant/src/platforms/tableau/*.py` - Tableau 平台实现

**目标文件**：
- `analytics-assistant/src/platform/tableau/adapter.py` - TableauAdapter（实现 IPlatformAdapter）
- `analytics-assistant/src/platform/tableau/client.py` - Tableau API 客户端
- `analytics-assistant/src/platform/tableau/query_builder.py` - VizQL 查询构建器
- `analytics-assistant/src/platform/tableau/data_loader.py` - 数据模型加载器

**任务清单**：
- [x] 2.2.1 重命名目录 platforms → platform
  - [x] 创建 analytics_assistant/src/platform/ 目录结构
  - [x] 更新所有导入路径
- [x] 2.2.2 创建 TableauAdapter（实现 BasePlatformAdapter）
  - [x] 实现 execute_query()
  - [x] 实现 build_query()
  - [x] 实现 validate_query()
- [x] 2.2.3 重构 QueryBuilder
  - [x] 分离 VizQL 构建逻辑
  - [x] 添加查询验证
- [-] 2.2.4 重构 DataLoader
  - [-] 实现 IDataLoader 接口 - 待 VizQL Client 迁移时实现
  - [-] 添加数据验证 - 待 VizQL Client 迁移时实现
- [-] 2.2.5 集成测试（与 Tableau API）
  - [-] 测试数据模型加载 - 待 VizQL Client 迁移时实现
  - [-] 测试查询执行 - 待 VizQL Client 迁移时实现

**迁移路径**：
```
1. 重命名目录 platforms → platform
2. 创建 adapter.py（实现接口）
3. 重构 query_builder.py 和 data_loader.py
4. 更新所有引用（agents/semantic_parser）
```

---

### 阶段 2 验证标准

- ✅ 单元测试覆盖率 ≥ 80%
- ✅ Tableau API 集成测试通过
- ✅ 数据模型加载成功
- ✅ 接口定义清晰，易于扩展

### 阶段 2 回滚方案

- Git Tag: `v2.0-core-platform`
- 回滚命令: `git checkout v2.0-core-platform`
- 配置回滚：恢复配置文件到上一版本

---

## 阶段 3：Agent 组件化（3 周）

### 目标
将现有 Agent 重构为组件化架构，提升可复用性。

### 3.1 Base 组件

**现有文件**：
- `tableau_assistant/src/agents/base/node.py` - Agent 基础工具
- `tableau_assistant/src/agents/base/middleware_runner.py` - 中间件运行器

**目标文件**：
- `analytics-assistant/src/agents/base/node.py` - 保留工具函数
- `analytics-assistant/src/agents/base/middleware_runner.py` - 暂时保留，阶段 5 迁移到 orchestration/middleware/

**任务清单**：
- [x] 3.1.1 保留 node.py 的工具函数
  - [x] get_llm()
  - [x] call_llm_with_tools()
  - [x] parse_json_response()
- [x] 3.1.2 ~~创建 BaseComponent 抽象类~~ - 不需要实现
  - [x] **决策**：Agent 节点保持函数式风格，不强制继承
  - [x] **原因**：与老项目模式一致，更简洁
- [x] 3.1.3 ~~创建通用错误处理器~~ - 不需要实现
  - [x] **决策**：使用 LangGraph 的 ModelRetryMiddleware
  - [x] **原因**：不重复造轮子，业务异常定义在 core/exceptions.py
- [x] 3.1.4 单元测试（覆盖率 ≥ 80%）

**迁移路径**：
```
1. 保留 node.py 和 middleware_runner.py
2. 创建 components.py（新文件）
3. 创建 error_handler.py（新文件）
```

---

### 3.2 FieldMapper 组件化

**现有文件**：
- `tableau_assistant/src/agents/field_mapper/node.py` - FieldMapper 节点
- `tableau_assistant/src/agents/field_mapper/llm_selector.py` - LLM 选择器（待删除）
- `tableau_assistant/src/agents/field_mapper/rag/*.py` - RAG 检索（待删除）
- `tableau_assistant/src/agents/field_mapper/models/*.py` - 数据模型

**目标文件**：
- `analytics-assistant/src/agents/field_mapper/node.py` - 重构为组件化
- `analytics-assistant/src/agents/field_mapper/schemas/*.py` - 数据模型（重命名）

**任务清单**：
- [x] 3.2.1 删除 llm_selector.py
  - [x] 使用 ModelManager 替代（通过 agents/base 的 get_llm）
  - [x] 更新 node.py 的调用（_llm_select 方法直接使用 get_llm）
- [x] 3.2.2 删除 rag/ 子目录
  - [x] 直接使用 infra/rag 模块（预留接口，TODO 集成）
  - [x] 更新 node.py 的导入
- [x] 3.2.3 重命名 models/ → schemas/
  - [x] 创建 schemas/ 目录
  - [x] 更新所有导入路径
- [x] 3.2.4 重构 node.py 为组件化架构
  - [x] 保持函数式风格（不强制继承 BaseComponent）
  - [x] 分离 RAG 检索逻辑（使用 infra/rag 接口）
  - [x] 直接使用 ModelManager（通过 agents/base）
- [ ] 3.2.5 单元测试（覆盖率 ≥ 80%）
  - [ ] 测试字段映射
  - [ ] 测试 RAG 检索

**迁移路径**：
```
1. 删除 llm_selector.py 和 rag/ 子目录
2. 重命名 models/ → schemas/
3. 重构 node.py（原地修改）
4. 更新所有引用
```

---

### 3.3 DimensionHierarchy 组件化

**现有文件**：
- `tableau_assistant/src/agents/dimension_hierarchy/node.py` - 维度层级节点
- `tableau_assistant/src/agents/dimension_hierarchy/cache_storage.py` - 缓存存储
- `tableau_assistant/src/agents/dimension_hierarchy/inference.py` - 推断引擎
- `tableau_assistant/src/agents/dimension_hierarchy/llm_inference.py` - LLM 推断（待删除）
- `tableau_assistant/src/agents/dimension_hierarchy/models/*.py` - 数据模型

**目标文件**：
- `analytics-assistant/src/agents/dimension_hierarchy/node.py` - 重构为组件化（整合 LLM 推断逻辑）
- `analytics-assistant/src/agents/dimension_hierarchy/cache_storage.py` - 使用 CacheManager
- `analytics-assistant/src/agents/dimension_hierarchy/inference.py` - 保留
- `analytics-assistant/src/agents/dimension_hierarchy/schemas/*.py` - 数据模型（重命名）

**任务清单**：
- [ ] 3.3.1 删除 llm_inference.py
  - [ ] 将 LLM 推断逻辑整合到 node.py
  - [ ] 使用 ModelManager 和 base 工具函数
- [ ] 3.3.2 重命名 models/ → schemas/
  - [ ] 重命名目录
  - [ ] 更新所有导入路径
- [ ] 3.3.3 更新 cache_storage.py 使用 CacheManager
  - [ ] 替换直接调用 LangGraph Store
  - [ ] 使用统一的缓存接口
- [ ] 3.3.4 重构 node.py 为组件化架构
  - [ ] 继承 BaseComponent
  - [ ] 整合 LLM 推断逻辑
  - [ ] 分离推断逻辑
- [ ] 3.3.5 单元测试（覆盖率 ≥ 80%）
  - [ ] 测试维度层级推断
  - [ ] 测试缓存功能

**迁移路径**：
```
1. 删除 llm_inference.py，逻辑整合到 node.py
2. 重命名 models/ → schemas/
3. 更新 cache_storage.py（原地修改）
4. 重构 node.py（原地修改）
5. 测试缓存迁移
```

---

### 3.4 Insight 和 Replanner 组件化

**现有文件**：
- `tableau_assistant/src/agents/insight/*.py` - Insight Agent（子图）
- `tableau_assistant/src/agents/insight/models/*.py` - 数据模型
- `tableau_assistant/src/agents/replanner/*.py` - Replanner Agent
- `tableau_assistant/src/agents/replanner/models/*.py` - 数据模型

**目标文件**：
- `analytics-assistant/src/agents/insight/*.py` - 保留子图架构
- `analytics-assistant/src/agents/insight/schemas/*.py` - 数据模型（重命名）
- `analytics-assistant/src/agents/replanner/*.py` - 保留
- `analytics-assistant/src/agents/replanner/schemas/*.py` - 数据模型（重命名）

**任务清单**：
- [ ] 3.4.1 Insight Agent 组件化
  - [ ] 重命名 models/ → schemas/
  - [ ] 重构 Profiler、Director、Analyzer 为组件
  - [ ] 保持子图架构
- [ ] 3.4.2 Replanner Agent 组件化
  - [ ] 重命名 models/ → schemas/
  - [ ] 重构为组件化架构
  - [ ] 保持单节点设计
- [ ] 3.4.3 SemanticParser Agent 组件化
  - [ ] 重命名 models/ → schemas/
  - [ ] 更新所有导入路径
- [ ] 3.4.4 集成测试
  - [ ] 测试 Insight 子图
  - [ ] 测试 Replanner 决策

**迁移路径**：
```
1. 重命名所有 Agent 的 models/ → schemas/
2. 重构 Insight 组件（原地修改）
3. 重构 Replanner 组件（原地修改）
4. 集成测试
```

---

### 阶段 3 验证标准

- ✅ 单元测试覆盖率 ≥ 80%
- ✅ 集成测试通过
- ✅ 性能无退化
- ✅ 组件可复用

### 阶段 3 回滚方案

- Git Tag: `v3.0-agent-components`
- 回滚命令: `git checkout v3.0-agent-components`
- 配置回滚：恢复配置文件到上一版本

---


## 阶段 4：语义解析器优化（3 周）

### 目标
实现三层意图路由、Prompt 优化、混合检索，降低 token 消耗 30%。

### 4.1 三层意图路由

**现有文件**：
- `tableau_assistant/src/agents/semantic_parser/nodes/intent_router.py` - 意图路由节点

**目标文件**：
- `analytics-assistant/src/agents/semantic_parser/components/intent_classifier.py` - 三层路由（新建）
- `analytics-assistant/src/agents/semantic_parser/nodes/intent_router.py` - 调用三层路由

**任务清单**：
- [ ] 4.1.1 实现 L0 规则引擎
  - [ ] 关键词匹配（"总计"、"排名"、"趋势"）
  - [ ] 模式匹配（正则表达式）
  - [ ] 目标命中率 ≥ 30%
- [ ] 4.1.2 训练 L1 小模型（DistilBERT）
  - [ ] 准备训练数据（标注意图）
  - [ ] 训练分类模型
  - [ ] 目标命中率 ≥ 50%
- [ ] 4.1.3 实现 L2 LLM 兜底
  - [ ] 使用 ModelManager 获取 LLM
  - [ ] Prompt 设计
  - [ ] 处理剩余 20% 复杂查询
- [ ] 4.1.4 集成三层路由逻辑
  - [ ] L0 → L1 → L2 级联
  - [ ] 置信度阈值配置
- [ ] 4.1.5 单元测试和 A/B 测试
  - [ ] 测试命中率
  - [ ] 测试 token 消耗
  - [ ] A/B 对比旧路由

**迁移路径**：
```
1. 创建 intent_classifier.py（新文件）
2. 实现 L0、L1、L2 路由
3. 更新 intent_router.py 调用三层路由
4. A/B 测试验证效果
```

---

### 4.2 Prompt 优化

**现有文件**：
- `tableau_assistant/src/agents/semantic_parser/prompts/*.py` - Prompt 模板

**目标文件**：
- `analytics-assistant/src/agents/semantic_parser/prompts/step1.py` - 优化 Step1 Prompt
- `analytics-assistant/src/agents/semantic_parser/prompts/step2.py` - 优化 Step2 Prompt

**任务清单**：
- [ ] 4.2.1 实现动态 Schema 过滤
  - [ ] 根据意图类型过滤字段
  - [ ] 仅注入相关字段（≤20 个）
  - [ ] 减少 Prompt 长度 50%
- [ ] 4.2.2 设计分层 Prompt（Step1 + Step2）
  - [ ] Step1：意图理解 + 粗粒度字段选择
  - [ ] Step2：精细化查询构建
  - [ ] 避免一次性生成完整查询
- [ ] 4.2.3 实现思维链压缩
  - [ ] 简化推理步骤
  - [ ] 减少冗余描述
- [ ] 4.2.4 A/B 测试
  - [ ] 对比旧 Prompt
  - [ ] 测量 token 消耗
  - [ ] 测量准确率

**迁移路径**：
```
1. 优化 step1.py 和 step2.py（原地修改）
2. 实现动态 Schema 过滤
3. A/B 测试验证效果
```

---

### 4.3 混合检索优化

**现有文件**：
- `tableau_assistant/src/agents/semantic_parser/components/schema_linker.py` - Schema Linking

**目标文件**：
- `analytics-assistant/src/agents/semantic_parser/components/schema_linker.py` - 优化混合检索

**任务清单**：
- [ ] 4.3.1 实现精确匹配优先
  - [ ] 字段名完全匹配 → 直接返回
  - [ ] 别名匹配 → 直接返回
  - [ ] 跳过向量检索（节省时间）
- [ ] 4.3.2 优化向量检索
  - [ ] 使用 UnifiedRetriever
  - [ ] 调整 top_k 参数（≤20）
- [ ] 4.3.3 优化关键词检索
  - [ ] 使用 BM25
  - [ ] 中文分词优化（jieba）
- [ ] 4.3.4 优化 RRF 融合
  - [ ] 调整权重参数
  - [ ] 两阶段分数融合
- [ ] 4.3.5 性能测试
  - [ ] 测量检索延迟
  - [ ] 测量准确率

**迁移路径**：
```
1. 优化 schema_linker.py（原地修改）
2. 集成 UnifiedRetriever
3. 性能测试验证效果
```

---

### 4.4 集成和验证

**任务清单**：
- [ ] 4.4.1 集成所有优化
  - [ ] 三层路由 + Prompt 优化 + 混合检索
  - [ ] 端到端测试
- [ ] 4.4.2 性能测试
  - [ ] 测量 token 消耗（目标降低 30%）
  - [ ] 测量延迟（目标 < 3s）
  - [ ] 测量准确率（目标提升 10%）
- [ ] 4.4.3 A/B 测试
  - [ ] 对比旧版本
  - [ ] 收集用户反馈
- [ ] 4.4.4 文档更新
  - [ ] 更新设计文档
  - [ ] 更新 API 文档

**迁移路径**：
```
1. 集成所有优化
2. 端到端测试
3. A/B 测试验证
4. 文档更新
```

---

### 阶段 4 验证标准

- ✅ L0 命中率 ≥ 30%
- ✅ L1 命中率 ≥ 50%
- ✅ Token 消耗降低 ≥ 30%
- ✅ 准确率提升 ≥ 10%
- ✅ 延迟 < 3s

### 阶段 4 回滚方案

- Git Tag: `v4.0-semantic-optimization`
- 回滚命令: `git checkout v4.0-semantic-optimization`
- 模型文件：备份小模型权重文件

---

## 阶段 5：Orchestration 层（2 周）

### 目标
使用 LangGraph 重构主工作流，实现中间件系统。

### 5.1 LangGraph 工作流

**现有文件**：
- `tableau_assistant/src/orchestration/workflow/factory.py` - 工作流工厂
- `tableau_assistant/src/orchestration/workflow/state.py` - 工作流状态
- `tableau_assistant/src/orchestration/workflow/routes.py` - 路由逻辑

**目标文件**：
- `analytics-assistant/src/orchestration/workflow/main_workflow.py` - 主工作流图（新建）
- `analytics-assistant/src/orchestration/workflow/state.py` - 保留并扩展
- `analytics-assistant/src/orchestration/workflow/routes.py` - 保留并优化

**任务清单**：
- [ ] 5.1.1 创建主工作流图
  - [ ] 定义节点（SemanticParser、Insight、Replanner）
  - [ ] 定义边（条件路由）
  - [ ] 支持并行执行（Send() API）
- [ ] 5.1.2 扩展工作流状态
  - [ ] 添加 metrics 字段
  - [ ] 添加 parallel_questions 字段
  - [ ] 添加 session_id 字段（支持多轮会话）
- [ ] 5.1.3 优化路由逻辑
  - [ ] route_after_semantic_parser
  - [ ] route_after_replanner（支持并行）
- [ ] 5.1.4 集成 LangGraph Checkpointer
  - [ ] 配置 SqliteSaver（开发环境）
  - [ ] 配置 RedisSaver（生产环境，可选）
  - [ ] 实现会话恢复逻辑
- [ ] 5.1.5 集成测试
  - [ ] 测试工作流执行
  - [ ] 测试并行执行
  - [ ] 测试会话恢复（多轮对话）
  - [ ] 测试对话压缩（SummarizationMiddleware）

**迁移路径**：
```
1. 创建 main_workflow.py（新文件）
2. 扩展 state.py（原地修改，添加 session_id）
3. 优化 routes.py（原地修改）
4. 更新 factory.py 调用新工作流
5. 集成 Checkpointer
6. 测试多轮会话
```

---

### 5.2 中间件系统

**现有文件**：
- `tableau_assistant/src/orchestration/middleware/*.py` - 现有中间件
- `tableau_assistant/src/orchestration/tools/*.py` - LangChain 工具（待删除）

**目标文件**：
- `src/orchestration/middleware/filesystem.py` - 保留
- `src/orchestration/middleware/patch_tool_calls.py` - 保留
- `src/orchestration/middleware/output_validation.py` - 保留
- `src/orchestration/middleware/retry.py` - 新建（可选）
- `src/orchestration/middleware/summarization.py` - 新建（可选）

**任务清单**：
- [ ] 5.2.1 删除 tools/ 目录
  - [ ] 移除 query_executor.py、data_profiler.py、field_lookup.py
  - [ ] 直接调用 Agent 节点，避免重复抽象
  - [ ] 更新工作流中的调用
- [ ] 5.2.2 保留现有中间件
  - [ ] FilesystemMiddleware
  - [ ] PatchToolCallsMiddleware
  - [ ] OutputValidationMiddleware
- [ ] 5.2.3 集成 LangChain 中间件
  - [ ] TodoListMiddleware
  - [ ] SummarizationMiddleware
  - [ ] ModelRetryMiddleware
  - [ ] ToolRetryMiddleware
  - [ ] **HumanInTheLoopMiddleware（必选）**
    - [ ] 配置介入场景（仅 write_todos）
    - [ ] 支持环境变量配置（INTERRUPT_ON=write_todos）
    - [ ] 实现用户审核探索问题的流程
    - [ ] 添加审计日志
- [ ] 5.2.4 配置中间件栈
  - [ ] 在 factory.py 中配置
  - [ ] 支持动态启用/禁用
- [ ] 5.2.5 集成测试
  - [ ] 测试中间件功能
  - [ ] 测试中间件顺序

**迁移路径**：
```
1. 删除 tools/ 目录
2. 保留现有中间件
3. 集成 LangChain 中间件
4. 配置中间件栈
5. 集成测试
```

---

### 阶段 5 验证标准

- ✅ 工作流集成测试通过
- ✅ 中间件功能验证通过
- ✅ 端到端测试通过
- ✅ 并行执行正常

### 阶段 5 回滚方案

- Git Tag: `v5.0-orchestration`
- 回滚命令: `git checkout v5.0-orchestration`
- 配置回滚：恢复 LangGraph checkpoint 配置

---


## 阶段 6：测试和优化（3 周）

### 目标
完善测试体系，优化性能，确保质量。

### 6.1 单元测试

**任务清单**：
- [ ] 6.1.1 补充 Infrastructure 层单元测试
  - [ ] ModelManager 测试
  - [ ] UnifiedRetriever 测试
  - [ ] CacheManager 测试
  - [ ] 覆盖率 ≥ 80%
- [ ] 6.1.2 补充 Core 层单元测试
  - [ ] 领域模型测试
  - [ ] 验证器测试
  - [ ] 覆盖率 ≥ 80%
- [ ] 6.1.3 补充 Platform 层单元测试
  - [ ] TableauAdapter 测试
  - [ ] QueryBuilder 测试
  - [ ] 覆盖率 ≥ 80%
- [ ] 6.1.4 补充 Agent 层单元测试
  - [ ] SemanticParser 测试
  - [ ] FieldMapper 测试
  - [ ] DimensionHierarchy 测试
  - [ ] Insight 测试
  - [ ] Replanner 测试
  - [ ] 覆盖率 ≥ 80%
- [ ] 6.1.5 补充 Orchestration 层单元测试
  - [ ] 工作流测试
  - [ ] 中间件测试
  - [ ] 覆盖率 ≥ 80%
- [ ] 6.1.6 修复测试失败
  - [ ] 分析失败原因
  - [ ] 修复代码或测试
- [ ] 6.1.7 Code Review
  - [ ] 代码质量检查
  - [ ] 最佳实践检查

---

### 6.2 属性测试（Property-Based Testing）

**任务清单**：
- [ ] 6.2.1 预处理属性测试（4 个属性）
  - [ ] P1.1 幂等性：f(f(x)) = f(x)
  - [ ] P1.2 可逆性：decode(encode(x)) = x
  - [ ] P1.3 长度约束：len(output) ≤ max_length
  - [ ] P1.4 字符集约束：output ⊆ valid_charset
- [ ] 6.2.2 意图路由属性测试（3 个属性）
  - [ ] P2.1 确定性：route(x) = route(x)
  - [ ] P2.2 置信度范围：0 ≤ confidence ≤ 1
  - [ ] P2.3 覆盖性：∀x, ∃route
- [ ] 6.2.3 Schema Linking 属性测试（4 个属性）
  - [ ] P3.1 精确匹配优先：exact_match → score = 1.0
  - [ ] P3.2 同义词对称性：synonym(a, b) → synonym(b, a)
  - [ ] P3.3 分数单调性：score(exact) ≥ score(fuzzy)
  - [ ] P3.4 候选数约束：len(candidates) ≤ top_k
- [ ] 6.2.4 缓存属性测试（3 个属性）
  - [ ] P4.1 幂等性：get(put(k, v)) = v
  - [ ] P4.2 一致性：put(k, v1); put(k, v2); get(k) = v2
  - [ ] P4.3 过期时间：get(k, ttl) after ttl → None
- [ ] 6.2.5 配置属性测试（3 个属性）
  - [ ] P5.1 验证完整性：validate(config) → all_required_fields_present
  - [ ] P5.2 默认值：get(key, default) = default if key not in config
  - [ ] P5.3 环境隔离：config(dev) ≠ config(prod)
- [ ] 6.2.6 序列化属性测试（3 个属性）
  - [ ] P6.1 Round-trip：deserialize(serialize(x)) = x
  - [ ] P6.2 类型保持：type(deserialize(serialize(x))) = type(x)
  - [ ] P6.3 向后兼容：deserialize(old_format) works
- [ ] 6.2.7 运行属性测试
  - [ ] 每个属性 ≥ 100 用例
  - [ ] 修复发现的问题

---

### 6.3 性能优化

**任务清单**：
- [ ] 6.3.1 性能测试
  - [ ] 压力测试（100 req/s）
  - [ ] 延迟测试（P90 < 3s）
  - [ ] Token 消耗测试（< 700 tokens）
  - [ ] 缓存命中率测试（≥ 60%）
- [ ] 6.3.2 识别性能瓶颈
  - [ ] 使用 profiler 分析
  - [ ] 识别慢查询
  - [ ] 识别高 token 消耗点
- [ ] 6.3.3 优化关键路径
  - [ ] 优化 LLM 调用
  - [ ] 优化 RAG 检索
  - [ ] 优化缓存策略
- [ ] 6.3.4 验证性能指标
  - [ ] 延迟降低 40%
  - [ ] Token 消耗降低 30%
  - [ ] 缓存命中率提升 50%

---

### 阶段 6 验证标准

- ✅ 单元测试覆盖率 ≥ 80%
- ✅ 属性测试全部通过
- ✅ 性能指标达标（延迟 < 3s, token < 700）
- ✅ Code Review 完成

### 阶段 6 回滚方案

- Git Tag: `v6.0-testing`
- 回滚命令: `git checkout v6.0-testing`
- 配置回滚：恢复配置文件到上一版本

---

## 阶段 7：文档和验收（1-2 周）

### 目标
完善技术文档，进行系统验收测试。

### 7.1 技术文档

**任务清单**：
- [ ] 7.1.1 更新架构文档
  - [ ] 五层架构说明
  - [ ] 组件交互图
  - [ ] 依赖关系图
- [ ] 7.1.2 更新 API 文档
  - [ ] 端点说明
  - [ ] 请求/响应示例
  - [ ] 错误码说明
- [ ] 7.1.3 更新开发指南
  - [ ] 代码规范
  - [ ] 测试指南
  - [ ] 贡献指南

---

### 7.2 用户文档

**任务清单**：
- [ ] 7.2.1 用户手册
  - [ ] 功能说明
  - [ ] 使用示例
  - [ ] 常见问题
- [ ] 7.2.2 培训材料
  - [ ] 架构培训
  - [ ] 功能培训
  - [ ] 最佳实践

---

### 7.3 系统验收

**任务清单**：
- [ ] 7.3.1 功能验收测试
  - [ ] 核心功能测试
  - [ ] 边界条件测试
  - [ ] 错误处理测试
- [ ] 7.3.2 性能验收测试
  - [ ] 延迟测试（P90 < 3s）
  - [ ] 吞吐量测试（> 100 req/s）
  - [ ] 缓存命中率测试（> 60%）
- [ ] 7.3.3 安全验收测试
  - [ ] 认证授权测试
  - [ ] 数据加密测试
  - [ ] 漏洞扫描

---

### 阶段 7 验证标准

- ✅ 所有文档更新完成
- ✅ 功能验收测试通过
- ✅ 性能指标达标
- ✅ 安全测试通过

### 阶段 7 回滚方案

- Git Tag: `v7.0-final`
- 回滚命令: `git checkout v7.0-final`
- 配置回滚：恢复配置文件到上一版本

---

## 总体时间线

```
Week 1-2:   阶段 1 - 基础设施层重构
Week 3-4:   阶段 2 - Core 和 Platform 层
Week 5-7:   阶段 3 - Agent 组件化
Week 8-10:  阶段 4 - 语义解析器优化
Week 11-12: 阶段 5 - Orchestration 层
Week 13-15: 阶段 6 - 测试和优化
Week 16-17: 阶段 7 - 部署和监控
```

**总工期**：17 周（约 4 个月）

---

## 质量门禁

每个阶段完成后必须通过以下检查：

- ✅ 单元测试覆盖率 ≥ 80%
- ✅ 集成测试全部通过
- ✅ Code Review 完成
- ✅ 性能测试通过
- ✅ 文档更新完成

---

## 风险管理

### 关键风险

1. **阶段 4 延期**：语义解析器优化复杂度高
   - 缓解：提前进行技术预研
   - 应急：简化优化范围

2. **测试覆盖不足**：时间紧张导致测试不充分
   - 缓解：强制覆盖率检查
   - 应急：延长阶段 6 时间

3. **性能不达标**：优化效果不如预期
   - 缓解：每个阶段进行性能测试
   - 应急：回滚到上一版本

---

## 总结

本任务清单提供了详细的实施路径：

✅ **文件映射清晰**：现有文件 → 目标文件  
✅ **迁移路径明确**：每个文件的迁移步骤  
✅ **任务可执行**：按现有代码结构组织  
✅ **验证标准明确**：每个阶段的验证标准  
✅ **回滚方案完整**：Git Tag + 数据迁移  

通过这个任务清单，开发团队可以按部就班地完成系统级重构，确保质量和进度可控。

