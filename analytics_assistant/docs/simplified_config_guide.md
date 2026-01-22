# 简化配置管理指南

## 设计原则

**一个配置文件管理所有配置** - `config/app.yaml`

不再有：
- ❌ `config/models.yaml`
- ❌ `config/storage.yaml`
- ❌ 每个模块的 `config_loader.py`

只有：
- ✅ `config/app.yaml` - 统一配置文件
- ✅ `src/infra/config/config_loader.py` - 统一配置管理器

## 配置文件结构

```yaml
# config/app.yaml - 统一配置文件

# AI 模型配置
ai:
  llm_models:
    - name: gpt-4
      provider: openai
      api_key: ${OPENAI_API_KEY}
  
  embedding_models:
    - name: text-embedding-3-small
      provider: openai
      api_key: ${OPENAI_API_KEY}

# 存储配置
storage:
  backend: ${STORAGE_BACKEND:-sqlite}
  connection_string: ${STORAGE_CONNECTION_STRING:-data/storage.db}
  ttl: 3600
  
  namespaces:
    cache:
      backend: redis
      connection_string: ${REDIS_URL:-redis://localhost:6379/0}

# RAG 配置（未来扩展）
rag:
  retrieval:
    top_k: 20

# 日志配置（未来扩展）
logging:
  level: ${LOG_LEVEL:-INFO}
```

## 使用方式

### 1. 获取配置

```python
from analytics_assistant.src.infra.config import get_config

# 获取全局配置实例
config = get_config()

# 获取 AI 配置
ai_config = config.get_ai_config()
llm_models = config.get_llm_models()
embedding_models = config.get_embedding_models()

# 获取存储配置
storage_config = config.get_storage_config()
backend = config.get_storage_backend()
```

### 2. 创建存储后端

```python
from analytics_assistant.src.infra.storage import StorageFactory

# 自动从 config/app.yaml 读取配置
store = StorageFactory.create_default_store("my_app")

# 使用命名空间特定配置
cache_store = StorageFactory.create_default_store("cache")
```

### 3. 加载 AI 模型配置

```python
from analytics_assistant.src.infra.config import get_config

config = get_config()
llm_models = config.get_llm_models()

for model in llm_models:
    print(f"Model: {model['name']}, Provider: {model['provider']}")
```

## 配置优先级

```
函数参数 > config/app.yaml（含环境变量展开） > 默认值
```

## 环境变量展开

在 `config/app.yaml` 中使用 `${VAR_NAME:-default}` 语法：

```yaml
storage:
  backend: ${STORAGE_BACKEND:-sqlite}  # 默认 sqlite
  connection_string: ${REDIS_URL:-redis://localhost:6379/0}
```

设置环境变量：
```bash
export STORAGE_BACKEND=redis
export REDIS_URL=redis://prod-redis:6379/0
```

## 目录结构

```
analytics_assistant/
├── config/
│   ├── app.yaml              # 统一配置文件（用户创建）
│   └── app.example.yaml      # 配置示例（提交到 Git）
└── src/
    └── infra/
        ├── config/
        │   └── config_loader.py  # 统一配置管理器（AppConfig）
        ├── ai/
        │   └── model_manager.py  # 直接使用 get_config()
        └── storage/
            └── factory.py        # 直接使用 get_config()
```

## 迁移指南

### 旧方式（复杂）

```python
# ❌ 每个模块有自己的配置加载器
from analytics_assistant.src.infra.ai.config_loader import ModelConfigLoader
from analytics_assistant.src.infra.storage.config_loader import StorageConfigLoader

ai_loader = ModelConfigLoader()
ai_config = ai_loader.load_llm_models()

storage_loader = StorageConfigLoader()
storage_config = storage_loader.load_storage_config()
```

### 新方式（简单）

```python
# ✅ 统一配置管理器
from analytics_assistant.src.infra.config import get_config

config = get_config()
ai_config = config.get_llm_models()
storage_config = config.get_storage_config()
```

## 配置文件管理

### 开发环境

```yaml
# config/app.yaml
storage:
  backend: sqlite
  connection_string: data/dev.db
```

### 生产环境

```yaml
# config/app.yaml
storage:
  backend: ${STORAGE_BACKEND:-redis}
  connection_string: ${REDIS_URL:-redis://prod-redis:6379/0}
```

### Git 管理

- ✅ 提交：`config/app.example.yaml`（示例配置）
- ❌ 不提交：`config/app.yaml`（实际配置，包含敏感信息）
- 在 `.gitignore` 中添加：`config/app.yaml`

## 优势

1. **简单**：只有一个配置文件
2. **统一**：所有模块使用相同的配置管理方式
3. **清晰**：配置集中在一个地方，易于查找和修改
4. **易维护**：不需要在多个文件之间切换
5. **易扩展**：添加新模块配置只需在 `app.yaml` 中添加新的 section

## 常见问题

### Q: 为什么不每个模块一个配置文件？

A: 
- 配置分散，难以管理
- 需要维护多个配置加载器
- 增加代码复杂度
- 团队成员需要知道多个配置文件的位置

### Q: 如何添加新模块的配置？

A:
1. 在 `config/app.yaml` 中添加新的 section
2. 在 `AppConfig` 中添加对应的 getter 方法
3. 模块直接使用 `get_config()` 获取配置

示例：
```python
# config/app.yaml
my_module:
  setting1: value1
  setting2: value2

# src/infra/config/config_loader.py
class AppConfig:
    def get_my_module_config(self):
        return self.config.get('my_module', {})

# 使用
from analytics_assistant.src.infra.config import get_config
config = get_config()
my_config = config.get_my_module_config()
```

## 总结

- **一个配置文件**：`config/app.yaml`
- **一个配置管理器**：`AppConfig`
- **统一使用方式**：`get_config()`
- **简单、清晰、易维护**
