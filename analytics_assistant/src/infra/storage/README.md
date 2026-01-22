# 存储后端重构说明

## 概述

本存储模块封装了 LangChain/LangGraph 的存储实现，提供统一的 KV 存储接口。

## 设计原则

### 1. 封装而非重新实现

- **SQLite 后端**：封装 `langgraph.store.sqlite.SqliteStore`
- **内存后端**：封装 `langgraph.store.memory.InMemoryStore`
- **Redis 后端**：使用 `redis-py` 客户端（保持与 LangGraph Store 的接口一致性）

### 2. 命名空间隔离

所有后端使用 LangGraph Store 的 namespace tuple 格式：`(namespace,)`

```python
# 示例
namespace = "my_app"
namespace_tuple = (namespace,)  # LangGraph Store 格式
```

### 3. TTL 支持

- **SQLite**：支持 TTL（LangGraph 使用分钟作为单位）
- **Redis**：原生支持 TTL（秒）
- **内存**：不支持 TTL（LangGraph InMemoryStore 限制）

### 4. 环境变量配置

支持通过环境变量切换后端：

```bash
# 开发环境（默认）
export STORAGE_BACKEND=sqlite
export STORAGE_CONNECTION_STRING=data/storage.db

# 生产环境
export STORAGE_BACKEND=redis
export STORAGE_CONNECTION_STRING=redis://prod-redis:6379/0
export STORAGE_TTL=3600
```

## 使用示例

### 基本用法

```python
from analytics_assistant.src.infra.storage import StorageFactory, StoreConfig

# 方式 1：使用配置对象
config = StoreConfig(
    backend="sqlite",
    namespace="my_app",
    connection_string="data/storage.db",
    ttl=3600  # 1 小时
)
store = StorageFactory.create_store(config)

# 方式 2：使用默认配置（从 YAML 或环境变量读取）
store = StorageFactory.create_default_store("my_app")

# 方式 3：从环境变量和 YAML 配置读取
store = StorageFactory.create_from_env("my_app")

# 使用存储
store.put("key1", {"data": "value"})
value = store.get("key1")
store.delete("key1")
```

### 配置方式

#### 1. YAML 配置文件（推荐）

创建 `config/storage.yaml`：

```yaml
storage:
  # 默认后端
  backend: sqlite
  connection_string: data/storage.db
  ttl: 3600  # 1 小时
  
  # 命名空间特定配置
  namespaces:
    cache:
      backend: redis
      connection_string: redis://localhost:6379/0
      ttl: 3600
    
    session:
      backend: redis
      connection_string: redis://localhost:6379/0
      ttl: 604800  # 7 天
```

使用：

```python
# 使用默认配置
store = StorageFactory.create_default_store("my_app")

# 使用命名空间特定配置
cache_store = StorageFactory.create_default_store("cache")
session_store = StorageFactory.create_default_store("session")
```

#### 2. 环境变量配置

```bash
# 设置环境变量
export STORAGE_BACKEND=redis
export STORAGE_CONNECTION_STRING=redis://localhost:6379/0
export STORAGE_TTL=3600
```

使用：

```python
store = StorageFactory.create_from_env("my_app")
```

#### 3. 环境变量展开（YAML 中）

```yaml
storage:
  backend: ${STORAGE_BACKEND:-sqlite}
  connection_string: ${STORAGE_CONNECTION_STRING:-data/storage.db}
  ttl: ${STORAGE_TTL:-3600}
```

#### 4. 配置优先级

```
函数参数 > 环境变量 > YAML 配置 > 默认值
```

示例：

```python
# 1. 最高优先级：函数参数
store = StorageFactory.create_default_store(
    "my_app",
    backend="redis",  # 覆盖所有其他配置
    connection_string="redis://prod:6379/0"
)

# 2. 环境变量优先于 YAML
# export STORAGE_BACKEND=redis
# config/storage.yaml: backend: sqlite
# 结果：使用 redis

# 3. YAML 优先于默认值
# config/storage.yaml: backend: redis
# 结果：使用 redis（而不是默认的 sqlite）
```

### 后端切换

```python
# 开发环境：SQLite
dev_store = StorageFactory.create_default_store(
    "my_app",
    backend="sqlite",
    connection_string="data/dev.db"
)

# 生产环境：Redis
prod_store = StorageFactory.create_default_store(
    "my_app",
    backend="redis",
    connection_string="redis://prod-redis:6379/0"
)

# 测试环境：内存
test_store = StorageFactory.create_default_store(
    "my_app",
    backend="memory"
)
```

### 命名空间隔离

```python
# 不同业务使用不同命名空间
cache_store = StorageFactory.create_default_store("cache")
session_store = StorageFactory.create_default_store("session")
model_store = StorageFactory.create_default_store("model")

# 数据互不干扰
cache_store.put("key1", "cache_value")
session_store.put("key1", "session_value")

assert cache_store.get("key1") == "cache_value"
assert session_store.get("key1") == "session_value"
```

## 与原始项目的对比

### 原始实现（tableau_assistant）

```python
# 直接使用 LangGraph Store
from langgraph.store.sqlite import SqliteStore
from tableau_assistant.src.infra.storage import get_langgraph_store

store = get_langgraph_store()  # 全局单例
store.put(("namespace",), "key", value)
```

### 新实现（analytics_assistant）

```python
# 封装后的统一接口
from analytics_assistant.src.infra.storage import StorageFactory

store = StorageFactory.create_default_store("namespace")
store.put("key", value)  # 更简洁的接口
```

## 关键差异

### 1. 接口简化

- **原始**：`store.put((namespace,), key, value)`
- **新版**：`store.put(key, value)`（namespace 在初始化时指定）

### 2. 后端切换

- **原始**：硬编码 SQLite，切换困难
- **新版**：环境变量配置，轻松切换

### 3. TTL 处理

- **原始**：直接使用 LangGraph 的分钟单位
- **新版**：统一使用秒单位，内部自动转换

### 4. 错误处理

- **原始**：TTL 不支持时会抛出异常
- **新版**：优雅降级，自动回退到无 TTL 模式

## 迁移指南

### 从原始项目迁移

```python
# 原始代码
from tableau_assistant.src.infra.storage import get_langgraph_store

store = get_langgraph_store()
store.put(("cache",), "key1", {"data": "value"}, ttl=1440)  # 1440 分钟

# 迁移后
from analytics_assistant.src.infra.storage import StorageFactory

store = StorageFactory.create_default_store("cache")
store.put("key1", {"data": "value"}, ttl=86400)  # 86400 秒 = 1440 分钟
```

### 维度层级缓存迁移

```python
# 原始代码（cache_storage.py）
from tableau_assistant.src.infra.storage import get_langgraph_store

class DimensionHierarchyCacheStorage:
    def __init__(self, store=None):
        self._store = store or get_langgraph_store()
    
    def put_hierarchy_cache(self, cache_key, field_hash, hierarchy_data):
        self._store.put(
            (NS_HIERARCHY_CACHE,),
            cache_key,
            data,
            ttl=PERMANENT_TTL_MINUTES
        )

# 迁移后（使用 CacheManager）
from analytics_assistant.src.infra.storage import StorageFactory

class DimensionHierarchyCacheStorage:
    def __init__(self, store=None):
        self._store = store or StorageFactory.create_default_store(
            NS_HIERARCHY_CACHE
        )
    
    def put_hierarchy_cache(self, cache_key, field_hash, hierarchy_data):
        # TTL 转换：分钟 -> 秒
        ttl_seconds = PERMANENT_TTL_MINUTES * 60
        self._store.put(cache_key, data, ttl=ttl_seconds)
```

## 注意事项

### 1. TTL 单位转换

- LangGraph Store：分钟
- 新接口：秒
- 自动转换：`ttl_minutes = ttl_seconds // 60`

### 2. InMemoryStore 限制

- 不支持 TTL
- 不持久化
- 仅用于测试

### 3. Redis 连接

- 需要安装：`pip install redis`
- 连接格式：`redis://host:port/db`
- 支持密码：`redis://:password@host:port/db`

### 4. 命名空间命名

- 使用小写字母和下划线
- 避免特殊字符
- 示例：`cache`, `session`, `model_cache`

## 环境配置示例

### 开发环境（.env.dev）

```bash
STORAGE_BACKEND=sqlite
STORAGE_CONNECTION_STRING=data/dev.db
STORAGE_TTL=3600
```

### 生产环境（.env.prod）

```bash
STORAGE_BACKEND=redis
STORAGE_CONNECTION_STRING=redis://prod-redis:6379/0
STORAGE_TTL=86400
```

### 测试环境（.env.test）

```bash
STORAGE_BACKEND=memory
```

## 性能对比

| 后端 | 读取延迟 | 写入延迟 | 持久化 | TTL 支持 | 适用场景 |
|------|---------|---------|--------|---------|---------|
| SQLite | ~1ms | ~2ms | ✅ | ✅ | 开发、单机部署 |
| Redis | ~0.5ms | ~0.5ms | ✅ | ✅ | 生产、分布式 |
| Memory | ~0.01ms | ~0.01ms | ❌ | ❌ | 测试、临时数据 |

## 下一步

1. **实现 CacheManager**：统一缓存管理器基类
2. **实现业务存储管理器**：
   - `data_model_cache.py`
   - `session_manager.py`
   - `golden_query_store.py`
   - `embedding_cache.py`
   - `file_store.py`
3. **迁移现有缓存**：更新 `agents/dimension_hierarchy/cache_storage.py`
4. **单元测试**：覆盖率 ≥ 80%
