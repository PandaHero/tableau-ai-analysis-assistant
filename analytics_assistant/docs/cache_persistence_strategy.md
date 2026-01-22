# 缓存与持久化策略文档

## 概述

本文档定义了系统中所有数据的缓存与持久化策略，基于对老项目 (`tableau_assistant/`) 的分析。

## 数据分类

### 1. 临时缓存（Temporary Cache）
**特征**：短期有效，定期失效，可重新获取
**后端**：SQLite 或 Memory
**失效策略**：基于 TTL

### 2. 永久存储（Permanent Storage）
**特征**：长期保存，仅在数据变化时失效
**后端**：SQLite
**失效策略**：基于内容哈希（field_hash）

### 3. 会话数据（Session Data）
**特征**：中期有效，支持多轮对话
**后端**：SQLite
**失效策略**：基于 TTL（7天）

---

## 详细策略

### 1. 数据模型缓存（DataModel Cache）

**数据类型**：DataModel 元数据（字段定义、表结构等，不含维度层级）

**缓存策略**：
- **类型**：临时缓存
- **后端**：SQLite
- **命名空间**：`data_model`
- **TTL**：1440 分钟（24 小时）
- **失效条件**：
  - TTL 过期
  - 手动调用 `invalidate(datasource_luid)`

**参考实现**：`tableau_assistant/src/infra/storage/data_model_cache.py`

**关键代码**：
```python
DEFAULT_TTL_MINUTES = 1440  # 24 小时
DATA_MODEL_NAMESPACE = ("data_model",)
```

**使用场景**：
- 缓存 Tableau 数据源的字段元数据
- 减少 Tableau API 调用
- 每天自动刷新一次

---

### 2. 维度层级缓存（Dimension Hierarchy Cache）

**数据类型**：维度层级推断结果（category, level, granularity 等）

**缓存策略**：
- **类型**：永久存储
- **后端**：SQLite
- **命名空间**：`dimension_hierarchy_cache`
- **TTL**：5,256,000 分钟（10 年，实现"永久"）
- **失效条件**：
  - **仅当 field_hash 变化时失效**（字段名、caption、dataType 变化）
  - 不基于 TTL 失效
  - 手动调用 `delete_hierarchy_cache(cache_key)`

**参考实现**：`tableau_assistant/src/agents/dimension_hierarchy/cache_storage.py`

**关键代码**：
```python
PERMANENT_TTL_MINUTES = 10 * 365 * 24 * 60  # 10 年
NS_HIERARCHY_CACHE = "dimension_hierarchy_cache"

def compute_field_hash_metadata_only(dimension_fields: List[Any]) -> str:
    """计算字段列表的哈希值（仅用元数据，不含样例数据）"""
    # 使用 field_name, field_caption, data_type 计算 MD5
```

**使用场景**：
- 缓存 LLM 推断的维度层级结果
- 避免重复推断（成本高）
- 仅在字段元数据变化时重新推断

**架构说明**：
- DataModelCache 只缓存 DataModel 元数据（不含 hierarchy）
- DimensionHierarchyCacheStorage 管理 hierarchy（有 field_hash 机制）
- 每次读取 DataModel 时，从 DimensionHierarchyCacheStorage 获取最新 hierarchy
- 这样确保 hierarchy 的缓存失效严格遵循 field_hash 语义

---

### 3. RAG 模式元数据（RAG Pattern Metadata）

**数据类型**：维度层级 RAG 模式元数据（不含向量，向量存 FAISS）

**缓存策略**：
- **类型**：永久存储
- **后端**：SQLite
- **命名空间**：`dimension_patterns_metadata`
- **TTL**：5,256,000 分钟（10 年，实现"永久"）
- **失效条件**：
  - 手动调用 `delete_pattern_metadata(pattern_id)`
  - 手动调用 `clear_pattern_metadata()`（清空所有）

**参考实现**：`tableau_assistant/src/agents/dimension_hierarchy/cache_storage.py`

**关键代码**：
```python
NS_DIMENSION_PATTERNS_METADATA = "dimension_patterns_metadata"
```

**使用场景**：
- 存储 RAG 模式元数据（用于自学习）
- 向量存储在 FAISS 中（单独管理）
- 支持错误纠正（删除单个或全部）

---

### 4. 认证缓存（Authentication Cache）

**数据类型**：Tableau API Token

**缓存策略**：
- **类型**：临时缓存
- **后端**：Memory（内存）
- **命名空间**：无（使用全局字典）
- **TTL**：600 秒（10 分钟）
- **失效条件**：
  - TTL 过期
  - 手动调用 `get_tableau_auth(force_refresh=True)`

**参考实现**：`tableau_assistant/src/platforms/tableau/auth.py`

**关键代码**：
```python
_CTX_TTL_SEC: int = 600  # 10 分钟
_ctx_cache: Dict[str, Dict[str, Any]] = {}  # domain -> cache_data
_ctx_cached_at: Dict[str, float] = {}  # domain -> cached_at
```

**使用场景**：
- 缓存 Tableau 认证 token
- 避免频繁调用认证 API
- 支持多环境（按 domain 分别缓存）

---

### 5. Embedding 缓存（Embedding Cache）

**数据类型**：文本的 Embedding 向量

**缓存策略**：
- **类型**：临时缓存
- **后端**：SQLite
- **命名空间**：`embedding`
- **TTL**：3600 分钟（1 小时）
- **失效条件**：
  - TTL 过期
  - 手动清除

**参考实现**：待实现（阶段 1.3.5）

**使用场景**：
- 缓存 Embedding API 调用结果
- 减少 Embedding API 调用成本
- 提升检索性能

---

### 6. 会话管理（Session Management）

**数据类型**：多轮对话会话状态

**缓存策略**：
- **类型**：会话数据
- **后端**：SQLite
- **命名空间**：`session`
- **TTL**：604,800 分钟（7 天）
- **失效条件**：
  - TTL 过期
  - 手动调用 `cleanup_expired_sessions()`

**参考实现**：待实现（阶段 1.3.5）

**使用场景**：
- 存储多轮对话上下文
- 支持会话恢复
- 集成 LangGraph Checkpointer

---

### 7. 向量索引（Vector Index）

**数据类型**：FAISS 向量索引 + 字段分块元数据

**缓存策略**：
- **类型**：永久存储（文件系统）
- **后端**：文件系统（FAISS 索引文件 + JSON 元数据）
- **路径**：`data/indexes/{datasource_luid}_faiss.index`
- **失效条件**：
  - 字段元数据变化（metadata_hash 不匹配）
  - 手动删除索引文件

**参考实现**：`analytics_assistant/src/infra/rag/vector_index_manager.py`

**关键方法**：
```python
def save_index(self, filename: Optional[str] = None) -> bool:
    """保存索引到磁盘（FAISS + 元数据）"""

def load_index(self, filename: Optional[str] = None) -> bool:
    """从磁盘加载索引（FAISS + 元数据）"""
```

**使用场景**：
- 持久化 FAISS 向量索引
- 避免每次启动重建索引
- 支持增量更新

---

## 配置映射

所有缓存/持久化配置都在 `analytics_assistant/config/app.yaml` 中定义：

```yaml
storage:
  # 默认后端
  backend: sqlite
  connection_string: data/storage.db
  ttl: 3600
  
  # 命名空间特定配置
  namespaces:
    # 数据模型缓存（24小时）
    data_model:
      backend: sqlite
      connection_string: data/data_model.db
      ttl: 1440  # 24 小时（分钟）
    
    # 维度层级缓存（永久，field_hash 失效）
    dimension_hierarchy_cache:
      backend: sqlite
      connection_string: data/dimension_hierarchy.db
      ttl: 5256000  # 10 年（分钟）
    
    # RAG 模式元数据（永久）
    dimension_patterns_metadata:
      backend: sqlite
      connection_string: data/dimension_patterns.db
      ttl: 5256000  # 10 年（分钟）
    
    # 认证缓存（10分钟，内存）
    auth:
      backend: memory
      ttl: 10  # 10 分钟（分钟）
    
    # Embedding 缓存（1小时）
    embedding:
      backend: sqlite
      connection_string: data/embedding.db
      ttl: 60  # 1 小时（分钟）
    
    # 会话管理（7天）
    session:
      backend: sqlite
      connection_string: data/session.db
      ttl: 10080  # 7 天（分钟）
```

---

## VectorIndexManager 重构建议

### 问题

`VectorIndexManager` 与 `BaseVectorStore` 功能重复：
- 两者都管理向量索引
- 两者都提供搜索功能
- 两者都支持持久化

### 建议方案

**方案 1：删除 VectorIndexManager，使用 BaseVectorStore**
- 优点：消除重复，架构更清晰
- 缺点：需要重构 Retriever

**方案 2：保留 VectorIndexManager 作为薄包装**
- 优点：保持现有接口，改动最小
- 缺点：仍有部分重复

**推荐**：方案 1（删除 VectorIndexManager）

### 重构步骤

1. 将 `VectorIndexManager` 的业务逻辑（如 `build_index_text`）移到 `Retriever`
2. 直接使用 `BaseVectorStore`（FAISS/Chroma）进行向量存储
3. 更新 `Retriever` 的依赖：
   ```python
   # 旧代码
   retriever = EmbeddingRetriever(vector_index_manager)
   
   # 新代码
   retriever = EmbeddingRetriever(vector_store)
   ```

---

## 总结

| 数据类型 | 后端 | 命名空间 | TTL | 失效策略 |
|---------|------|---------|-----|---------|
| 数据模型缓存 | SQLite | `data_model` | 24h | TTL |
| 维度层级缓存 | SQLite | `dimension_hierarchy_cache` | 10年 | field_hash |
| RAG 模式元数据 | SQLite | `dimension_patterns_metadata` | 10年 | 手动 |
| 认证缓存 | Memory | - | 10min | TTL |
| Embedding 缓存 | SQLite | `embedding` | 1h | TTL |
| 会话管理 | SQLite | `session` | 7天 | TTL |
| 向量索引 | 文件系统 | - | - | metadata_hash |

**关键原则**：
1. **临时数据用 TTL**：认证、Embedding、数据模型
2. **永久数据用哈希**：维度层级、RAG 模式
3. **会话数据用中期 TTL**：7天
4. **向量索引用文件系统**：FAISS 持久化

**配置原则**：
- 所有配置集中在 `app.yaml`
- 不分散在各个模块
- 支持环境变量展开
- 支持命名空间隔离
