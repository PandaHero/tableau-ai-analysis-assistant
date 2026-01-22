# Phase 1.3.5 分析总结

## 任务概述

分析老项目 (`tableau_assistant/`) 的缓存/持久化模式，定义新项目的缓存与持久化策略。

## 完成工作

### 1. 分析老项目缓存模式

**分析文件**：
- `tableau_assistant/src/infra/storage/data_model_cache.py` - DataModel 缓存
- `tableau_assistant/src/agents/dimension_hierarchy/cache_storage.py` - 维度层级缓存
- `tableau_assistant/src/platforms/tableau/auth.py` - 认证缓存

**关键发现**：

#### 1.1 DataModelCache（24小时 TTL）
```python
DEFAULT_TTL_MINUTES = 1440  # 24 小时
DATA_MODEL_NAMESPACE = ("data_model",)
```
- **用途**：缓存 Tableau 数据源的字段元数据
- **后端**：LangGraph SqliteStore
- **失效**：TTL 过期或手动失效
- **特点**：不含维度层级（hierarchy 由 DimensionHierarchyCacheStorage 管理）

#### 1.2 DimensionHierarchyCacheStorage（永久，field_hash 失效）
```python
PERMANENT_TTL_MINUTES = 10 * 365 * 24 * 60  # 10 年
NS_HIERARCHY_CACHE = "dimension_hierarchy_cache"
NS_DIMENSION_PATTERNS_METADATA = "dimension_patterns_metadata"
```
- **用途**：缓存 LLM 推断的维度层级结果
- **后端**：LangGraph SqliteStore
- **失效**：仅当 field_hash 变化时失效（字段元数据变化）
- **特点**：使用 `compute_field_hash_metadata_only()` 计算哈希

#### 1.3 认证缓存（10分钟 TTL，内存）
```python
_CTX_TTL_SEC: int = 600  # 10 分钟
_ctx_cache: Dict[str, Dict[str, Any]] = {}
_ctx_cached_at: Dict[str, float] = {}
```
- **用途**：缓存 Tableau API Token
- **后端**：内存（全局字典）
- **失效**：TTL 过期
- **特点**：支持多环境（按 domain 分别缓存）

---

### 2. 创建策略文档

**文档路径**：`analytics_assistant/docs/cache_persistence_strategy.md`

**内容概要**：
- 数据分类（临时缓存、永久存储、会话数据）
- 7 种数据类型的详细策略
- 配置映射
- VectorIndexManager 重构建议

**数据类型总结**：

| 数据类型 | 后端 | 命名空间 | TTL | 失效策略 |
|---------|------|---------|-----|---------|
| 数据模型缓存 | SQLite | `data_model` | 24h | TTL |
| 维度层级缓存 | SQLite | `dimension_hierarchy_cache` | 10年 | field_hash |
| RAG 模式元数据 | SQLite | `dimension_patterns_metadata` | 10年 | 手动 |
| 认证缓存 | Memory | - | 10min | TTL |
| Embedding 缓存 | SQLite | `embedding` | 1h | TTL |
| 会话管理 | SQLite | `session` | 7天 | TTL |
| 向量索引 | 文件系统 | - | - | metadata_hash |

---

### 3. 更新 YAML 配置

**文件路径**：`analytics_assistant/config/app.yaml`

**新增配置**：

#### 3.1 存储命名空间配置
```yaml
storage:
  namespaces:
    # 数据模型缓存（24小时）
    data_model:
      backend: sqlite
      connection_string: data/data_model.db
      ttl: 1440
    
    # 维度层级缓存（永久，field_hash 失效）
    dimension_hierarchy_cache:
      backend: sqlite
      connection_string: data/dimension_hierarchy.db
      ttl: 5256000
    
    # RAG 模式元数据（永久）
    dimension_patterns_metadata:
      backend: sqlite
      connection_string: data/dimension_patterns.db
      ttl: 5256000
    
    # 认证缓存（10分钟，内存）
    auth:
      backend: memory
      ttl: 10
    
    # Embedding 缓存（1小时）
    embedding:
      backend: sqlite
      connection_string: data/embedding.db
      ttl: 60
    
    # 会话管理（7天）
    session:
      backend: sqlite
      connection_string: data/session.db
      ttl: 10080
```

#### 3.2 向量存储配置
```yaml
vector_storage:
  backend: chroma  # faiss/chroma
  embedding_dimension: 1024
  index_dir: data/indexes
  
  faiss:
    index_type: flat
    use_gpu: false
  
  chroma:
    persist_directory: data/chroma
    collection_prefix: analytics_assistant
```

#### 3.3 RAG 配置
```yaml
rag:
  retrieval:
    top_k: 20
    score_threshold: 0.7
    retriever_type: hybrid
    embedding_weight: 0.7
    keyword_weight: 0.3
    use_rrf: true
    rrf_k: 60
  
  reranking:
    enabled: true
    reranker_type: llm
    rerank_top_k: 30
```

---

### 4. 识别架构问题

#### 4.1 VectorIndexManager 与 BaseVectorStore 重复

**问题**：
- `VectorIndexManager` 和 `BaseVectorStore` 功能重复
- 两者都管理向量索引、提供搜索、支持持久化

**影响范围**：
- `analytics_assistant/src/infra/rag/vector_index_manager.py`
- `analytics_assistant/src/infra/rag/retriever.py`
- `analytics_assistant/src/infra/storage/vector/base.py`
- `analytics_assistant/src/infra/storage/vector/faiss_store.py`
- `analytics_assistant/src/infra/storage/vector/chroma_store.py`

**建议方案**：
1. **删除 VectorIndexManager**（推荐）
   - 将业务逻辑（如 `build_index_text`）移到 Retriever
   - 直接使用 BaseVectorStore（FAISS/Chroma）
   - 优点：消除重复，架构更清晰
   - 缺点：需要重构 Retriever

2. **保留 VectorIndexManager 作为薄包装**
   - 保持现有接口，改动最小
   - 缺点：仍有部分重复

**重构步骤**（方案 1）：
1. 将 `build_index_text()` 移到 Retriever 或独立工具类
2. 更新 Retriever 依赖：
   ```python
   # 旧代码
   retriever = EmbeddingRetriever(vector_index_manager)
   
   # 新代码
   retriever = EmbeddingRetriever(vector_store)
   ```
3. 删除 `vector_index_manager.py`
4. 更新所有引用

---

### 5. 简化业务存储管理器

**决策**：大部分业务存储管理器不需要实现，直接使用 `CacheManager` 即可

**不需要实现的管理器**：
- ~~`managers/data_model_cache.py`~~ → 使用 `CacheManager("data_model", ttl=1440)`
- ~~`managers/golden_query_store.py`~~ → 使用 `CacheManager("golden_query")`
- ~~`managers/embedding_cache.py`~~ → 使用 `CacheManager("embedding", ttl=60)`
- ~~`managers/file_store.py`~~ → 直接使用文件系统操作

**可能需要实现的管理器**：
- `managers/session_manager.py`（会话管理，支持多轮对话）
  - 创建会话（create_session）
  - 获取会话（get_session）
  - 更新会话（update_session）
  - 清理过期会话（cleanup_expired_sessions）
  - 集成 LangGraph Checkpointer（SqliteSaver/RedisSaver）

**使用示例**：
```python
from analytics_assistant.src.infra.storage.managers import CacheManager

# 数据模型缓存
data_model_cache = CacheManager("data_model")
data_model = await data_model_cache.get_or_compute(
    key=datasource_luid,
    compute_fn=lambda: load_data_model(datasource_luid)
)

# 维度层级缓存（永久）
hierarchy_cache = CacheManager("dimension_hierarchy_cache")
hierarchy = await hierarchy_cache.get(cache_key)

# Embedding 缓存
embedding_cache = CacheManager("embedding")
vector = await embedding_cache.get_or_compute(
    key=text,
    compute_fn=lambda: embedding_provider.embed_query(text)
)
```

---

## 关键原则

### 1. 配置集中化
- 所有配置集中在 `analytics_assistant/config/app.yaml`
- 不分散在各个模块
- 支持环境变量展开：`${VAR_NAME:-default}`
- 支持命名空间隔离

### 2. 缓存策略分类
- **临时数据用 TTL**：认证、Embedding、数据模型
- **永久数据用哈希**：维度层级、RAG 模式
- **会话数据用中期 TTL**：7天
- **向量索引用文件系统**：FAISS 持久化

### 3. 架构简化
- 消除重复抽象（VectorIndexManager vs BaseVectorStore）
- 直接使用 CacheManager，避免过度封装
- 保持接口清晰，易于维护

---

## 下一步工作

### 1. VectorIndexManager 重构（优先级：高）✅ 已完成
- [x] 决定重构方案（方案 1：删除 VectorIndexManager，使用 FieldVectorStore）
- [x] 创建 `index_builder.py`（提取 IndexConfig 和 build_index_text）
- [x] 创建 `field_vector_store.py`（封装 BaseVectorStore，提供字段检索接口）
- [x] 更新 Retriever 依赖（使用 FieldVectorStore）
- [x] 删除 `vector_index_manager.py`
- [x] 更新所有引用
- [x] 更新测试文件（test_retriever.py, test_field_vector_store.py）
- [x] 测试验证（46 个测试全部通过）

**重构详情**：
- **新文件**：
  - `analytics_assistant/src/infra/rag/index_builder.py` - IndexConfig 和 build_index_text
  - `analytics_assistant/src/infra/rag/field_vector_store.py` - FieldVectorStore 类
  - `analytics_assistant/tests/infra/rag/test_field_vector_store.py` - 新测试文件
- **修改文件**：
  - `analytics_assistant/src/infra/rag/retriever.py` - 使用 FieldVectorStore
  - `analytics_assistant/src/infra/rag/__init__.py` - 更新导出
  - `analytics_assistant/tests/infra/rag/test_retriever.py` - 更新测试
- **删除文件**：
  - `analytics_assistant/src/infra/rag/vector_index_manager.py`
  - `analytics_assistant/tests/infra/rag/test_vector_index_manager.py`

### 2. SessionManager 实现（优先级：中）
- [ ] 实现 `managers/session_manager.py`
- [ ] 集成 LangGraph Checkpointer
- [ ] 支持多轮对话
- [ ] 测试验证

**注意**：根据之前讨论，不创建单独的 SessionManager，直接使用 CacheManager + LangGraph Checkpointer

### 3. 配置验证（优先级：低）
- [ ] 验证所有命名空间配置
- [ ] 测试 TTL 功能
- [ ] 测试环境变量展开
- [ ] 文档更新

---

## 参考文档

- **策略文档**：`analytics_assistant/docs/cache_persistence_strategy.md`
- **配置文件**：`analytics_assistant/config/app.yaml`
- **老项目参考**：
  - `tableau_assistant/src/infra/storage/data_model_cache.py`
  - `tableau_assistant/src/agents/dimension_hierarchy/cache_storage.py`
  - `tableau_assistant/src/platforms/tableau/auth.py`

---

## 总结

本阶段完成了缓存/持久化策略的全面分析和文档化：

1. ✅ 分析老项目缓存模式
2. ✅ 创建详细策略文档
3. ✅ 更新 YAML 配置
4. ✅ 识别架构问题（VectorIndexManager 重复）
5. ✅ 简化业务存储管理器设计
6. ✅ **VectorIndexManager 重构完成**

**关键成果**：
- 明确了 7 种数据类型的缓存/持久化策略
- 所有配置集中在 `app.yaml`
- **VectorIndexManager 重构完成**：
  - 删除了 VectorIndexManager
  - 创建了 FieldVectorStore（封装 BaseVectorStore）
  - 提取了 IndexConfig 和 build_index_text 到 index_builder.py
  - 更新了 Retriever 使用 FieldVectorStore
  - 所有测试通过（46 个测试）
- 简化了业务存储管理器设计（直接使用 CacheManager）

**待办事项**：
- SessionManager 实现（可选，可直接使用 CacheManager + LangGraph Checkpointer）
- 配置验证和测试
