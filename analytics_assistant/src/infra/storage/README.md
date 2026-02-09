# 存储模块

## 概述

基于 LangGraph BaseStore 框架的统一存储层，所有后端共享相同 API，切换只需修改 `app.yaml`。

## 架构

```
app.yaml (storage.backend: sqlite/memory/postgres/redis)
    │
    ▼
StoreFactory → 创建 BaseStore 实例（单例）
    │
    ├── CacheManager    (缓存封装: 同步+异步, TTL 秒→分钟转换, get_or_compute)
    ├── get_kv_store()  (全局单例, Agent 层直接使用 BaseStore API)
    └── BaseRepository  (CRUD 抽象: 同步+异步, 用于 API 层数据)
```

## 模块说明

| 文件 | 职责 |
|------|------|
| `store_factory.py` | 根据配置创建 BaseStore 实例，支持 sqlite/memory/postgres/redis |
| `kv_store.py` | 全局 BaseStore 单例，通过 StoreFactory 创建 |
| `cache.py` | CacheManager - 命名空间绑定、TTL 转换、统计、同步+异步 API |
| `repository.py` | BaseRepository - CRUD 抽象，用于 API 层（会话/设置/反馈） |
| `vector_store.py` | 向量存储（FAISS/Chroma），依赖 infra.ai |

## 支持的后端

| 后端 | 类 | TTL | 持久化 | 安装 |
|------|-----|-----|--------|------|
| sqlite | `SqliteStore` | ✅ | ✅ | 内置 |
| memory | `InMemoryStore` | ❌ | ❌ | 内置 |
| postgres | `AsyncPostgresStore` | ✅ | ✅ | `pip install langgraph-checkpoint-postgres` |
| redis | `RedisStore` | ✅ | ✅ | `pip install langgraph-checkpoint-redis` |

## 使用示例

### CacheManager（Agent 层缓存）

```python
from analytics_assistant.src.infra.storage import CacheManager

cache = CacheManager("embeddings", default_ttl=3600)

# 同步
cache.set("key1", {"data": "value"})
value = cache.get("key1")
result = cache.get_or_compute("key", compute_fn=lambda: expensive(), ttl=3600)

# 异步
await cache.aset("key1", {"data": "value"})
value = await cache.aget("key1")
result = await cache.aget_or_compute("key", compute_fn=async_fn, ttl=3600)
```

### BaseRepository（API 层 CRUD）

```python
from analytics_assistant.src.infra.storage import BaseRepository

repo = BaseRepository("sessions")

# 异步 CRUD
await repo.asave("session-1", {"title": "对话", "user": "admin"})
item = await repo.afind_by_id("session-1")
items = await repo.afind_all(filter_dict={"user": "admin"})
await repo.aremove("session-1")
```

### 直接使用 BaseStore

```python
from analytics_assistant.src.infra.storage import get_kv_store

store = get_kv_store()
store.put(("cache",), "key1", {"data": "value"})
item = store.get(("cache",), "key1")
```

## 配置

在 `analytics_assistant/config/app.yaml` 的 `storage` 节配置：

```yaml
storage:
  backend: sqlite
  connection_string: analytics_assistant/data/storage.db
  ttl: 1440  # 默认 TTL（分钟）
  namespaces:
    auth:
      backend: memory
      ttl: 10
    session:
      backend: sqlite
      connection_string: analytics_assistant/data/session.db
      ttl: 10080
```

## 后端切换

只需修改 `app.yaml`，代码无需任何改动：

```yaml
# 开发环境
storage:
  backend: sqlite
  connection_string: analytics_assistant/data/storage.db

# 生产环境
storage:
  backend: postgres
  connection_string: postgresql://user:pass@host/db
```
