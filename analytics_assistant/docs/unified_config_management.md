# 统一配置管理

## 概述

项目采用统一的 YAML 配置管理方式，所有模块（AI、Storage、RAG 等）都使用相同的配置加载模式。

## 设计原则

### ✅ 推荐方式

1. **所有配置都在 YAML 中定义**
   - 便于版本控制
   - 便于团队协作
   - 配置集中管理

2. **在 YAML 中引用环境变量**
   ```yaml
   storage:
     backend: ${STORAGE_BACKEND:-sqlite}
     connection_string: ${REDIS_URL:-redis://localhost:6379/0}
   ```

3. **使用默认值**
   ```yaml
   storage:
     backend: sqlite  # 开发环境默认值
     connection_string: data/storage.db
   ```

### ❌ 不推荐方式

1. **直接读取环境变量**
   ```python
   # ❌ 不要这样做
   backend = os.getenv("STORAGE_BACKEND", "sqlite")
   ```

2. **混合使用 YAML 和环境变量**
   - 配置来源混乱
   - 难以追踪配置值
   - 增加调试难度

## 配置优先级

```
函数参数 > YAML 配置（含环境变量展开） > 默认值
```

**说明**：
- 函数参数：代码中显式传递的参数（最高优先级）
- YAML 配置：配置文件中的值，支持 `${VAR_NAME:-default}` 语法
- 默认值：代码中的硬编码默认值（最低优先级）

## 统一配置加载器

### BaseConfigLoader

所有配置加载器都继承自 `BaseConfigLoader`：

```python
from analytics_assistant.src.infra.config.config_loader import BaseConfigLoader

class MyConfigLoader(BaseConfigLoader):
    def __init__(self):
        super().__init__(
            config_path="config/my_config.yaml",
            fallback_path="config/my_config.example.yaml"
        )
    
    def load_my_config(self):
        config = self.load()
        return config.get('my_section', {})
```

### 现有配置加载器

1. **ModelConfigLoader** (`analytics_assistant/src/infra/ai/config_loader.py`)
   - 加载 AI 模型配置
   - 配置文件：`config/models.yaml`

2. **StorageConfigLoader** (`analytics_assistant/src/infra/storage/config_loader.py`)
   - 加载存储配置
   - 配置文件：`config/storage.yaml`

## 环境变量展开

### 语法

支持两种格式：

1. **`${VAR_NAME}`**
   - 读取环境变量
   - 不存在则保持原样（字符串 `${VAR_NAME}`）

2. **`${VAR_NAME:-default}`**（推荐）
   - 读取环境变量
   - 不存在则使用默认值

### 示例

```yaml
# config/storage.yaml
storage:
  # 开发环境：使用默认值
  backend: sqlite
  connection_string: data/storage.db
  
  # 生产环境：使用环境变量
  # backend: ${STORAGE_BACKEND:-redis}
  # connection_string: ${REDIS_URL:-redis://prod-redis:6379/0}
  
  # 混合使用
  ttl: ${STORAGE_TTL:-3600}  # 默认 1 小时
```

## 配置文件结构

### 目录结构

```
analytics_assistant/
├── config/
│   ├── models.yaml          # AI 模型配置（用户创建）
│   ├── models.example.yaml  # AI 模型配置示例
│   ├── storage.yaml         # 存储配置（用户创建）
│   └── storage.example.yaml # 存储配置示例
└── src/
    └── infra/
        ├── config/
        │   └── config_loader.py  # 统一配置加载器基类
        ├── ai/
        │   └── config_loader.py  # AI 配置加载器
        └── storage/
            └── config_loader.py  # 存储配置加载器
```

### 配置文件命名规范

- `*.example.yaml`: 示例配置文件（提交到 Git）
- `*.yaml`: 实际配置文件（不提交到 Git，在 `.gitignore` 中）

## 使用示例

### 1. AI 模型配置

```yaml
# config/models.yaml
llm_models:
  - name: gpt-4
    provider: openai
    api_key: ${OPENAI_API_KEY}
    temperature: 0.7

embedding_models:
  - name: text-embedding-3-small
    provider: openai
    api_key: ${OPENAI_API_KEY}
```

```python
from analytics_assistant.src.infra.ai.config_loader import ModelConfigLoader

loader = ModelConfigLoader()
llm_models = loader.load_llm_models()
```

### 2. 存储配置

```yaml
# config/storage.yaml
storage:
  backend: ${STORAGE_BACKEND:-sqlite}
  connection_string: ${STORAGE_CONNECTION_STRING:-data/storage.db}
  ttl: ${STORAGE_TTL:-3600}
  
  namespaces:
    cache:
      backend: redis
      connection_string: ${REDIS_URL:-redis://localhost:6379/0}
```

```python
from analytics_assistant.src.infra.storage.factory import StorageFactory

# 使用默认配置
store = StorageFactory.create_default_store("my_app")

# 使用命名空间特定配置
cache_store = StorageFactory.create_default_store("cache")
```

## 环境配置最佳实践

### 开发环境

```yaml
# config/storage.yaml
storage:
  backend: sqlite
  connection_string: data/dev.db
  ttl: 3600
```

### 生产环境

```yaml
# config/storage.yaml
storage:
  backend: ${STORAGE_BACKEND:-redis}
  connection_string: ${REDIS_URL:-redis://prod-redis:6379/0}
  ttl: ${STORAGE_TTL:-86400}
```

设置环境变量：
```bash
export STORAGE_BACKEND=redis
export REDIS_URL=redis://prod-redis:6379/0
export STORAGE_TTL=86400
```

### 测试环境

```yaml
# config/storage.yaml
storage:
  backend: memory
  ttl: 600
```

## 迁移指南

### 从环境变量迁移到 YAML

**旧方式**（不推荐）：
```python
backend = os.getenv("STORAGE_BACKEND", "sqlite")
connection_string = os.getenv("STORAGE_CONNECTION_STRING", "data/storage.db")
```

**新方式**（推荐）：
```yaml
# config/storage.yaml
storage:
  backend: ${STORAGE_BACKEND:-sqlite}
  connection_string: ${STORAGE_CONNECTION_STRING:-data/storage.db}
```

```python
from analytics_assistant.src.infra.storage.factory import StorageFactory

store = StorageFactory.create_default_store("my_app")
```

## 常见问题

### Q: 为什么不直接读取环境变量？

A: 
1. **配置分散**：环境变量散落在代码各处，难以管理
2. **难以追踪**：不知道哪些环境变量被使用
3. **版本控制**：无法通过 Git 追踪配置变化
4. **团队协作**：团队成员需要手动设置环境变量

### Q: 什么时候使用环境变量？

A: 
- 敏感信息（API Key、密码等）
- 环境特定配置（生产/开发/测试）
- 但都应该在 YAML 中通过 `${VAR_NAME:-default}` 引用

### Q: 如何在不同环境使用不同配置？

A:
1. **方式一**：使用环境变量展开
   ```yaml
   storage:
     backend: ${STORAGE_BACKEND:-sqlite}
   ```

2. **方式二**：使用不同的配置文件
   ```bash
   # 开发环境
   cp config/storage.dev.yaml config/storage.yaml
   
   # 生产环境
   cp config/storage.prod.yaml config/storage.yaml
   ```

### Q: 配置文件应该提交到 Git 吗？

A:
- ✅ 提交：`*.example.yaml`（示例配置）
- ❌ 不提交：`*.yaml`（实际配置，包含敏感信息）
- 在 `.gitignore` 中添加：`config/*.yaml`

## 总结

1. **统一使用 YAML 配置**：所有配置都在 YAML 中定义
2. **环境变量展开**：在 YAML 中使用 `${VAR_NAME:-default}` 引用环境变量
3. **配置优先级**：函数参数 > YAML > 默认值
4. **不直接读取环境变量**：避免配置来源混乱
5. **版本控制**：提交 `*.example.yaml`，不提交 `*.yaml`
