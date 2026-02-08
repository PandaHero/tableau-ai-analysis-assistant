# ModelManager 配置文件

## 概述

ModelManager 支持通过 YAML 文件进行配置管理，提供更灵活和可维护的模型配置方式。

## 配置文件

- `models.yaml` - 实际使用的配置文件
- `models.example.yaml` - 配置文件模板（包含所有可用选项）

## 快速开始

### 1. 创建配置文件

```bash
# 复制示例配置文件
cp models.example.yaml models.yaml

# 编辑配置文件
vim models.yaml
```

### 2. 配置模型

```yaml
llm_models:
  - id: "deepseek-chat"
    name: "DeepSeek Chat V3.2"
    model_type: "llm"
    provider: "deepseek"
    api_base: "https://api.deepseek.com"
    model_name: "deepseek-chat"
    api_key: "your-api-key-here"
    openai_compatible: true
    temperature: 0.7
    suitable_tasks:
      - "semantic_parsing"
      - "insight_generation"
    priority: 10
    is_default: true
    status: "active"
```

### 3. 使用环境变量

配置文件支持环境变量展开：

```yaml
llm_models:
  - id: "deepseek-chat"
    api_key: "${DEEPSEEK_API_KEY}"  # 从环境变量读取
    api_base: "${API_BASE:-https://api.deepseek.com}"  # 带默认值
```

支持的格式：
- `${VAR_NAME}` - 读取环境变量，不存在则保持原样
- `${VAR_NAME:-default}` - 读取环境变量，不存在则使用默认值

### 4. 在代码中使用

```python
from src.infra.ai import get_model_manager

# ModelManager 会自动加载 YAML 配置
manager = get_model_manager()

# 使用配置的模型
llm = manager.create_llm(model_id="deepseek-chat")
response = llm.invoke("你好")
```

## 配置选项

### LLM 模型配置

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `id` | string | 是 | 模型唯一标识 |
| `name` | string | 是 | 模型显示名称 |
| `model_type` | string | 是 | 模型类型（`llm` 或 `embedding`） |
| `provider` | string | 是 | 提供商（`deepseek`, `openai`, `azure`, `local` 等） |
| `api_base` | string | 是 | API 基础 URL |
| `model_name` | string | 是 | 模型名称 |
| `api_key` | string | 是 | API 密钥 |
| `openai_compatible` | boolean | 否 | 是否 OpenAI 兼容（默认 `true`） |
| `temperature` | float | 否 | 温度参数（0.0-2.0） |
| `max_tokens` | integer | 否 | 最大 token 数 |
| `supports_streaming` | boolean | 否 | 是否支持流式输出（默认 `true`） |
| `supports_json_mode` | boolean | 否 | 是否支持 JSON Mode |
| `is_reasoning_model` | boolean | 否 | 是否是推理模型（默认 `false`） |
| `suitable_tasks` | array | 否 | 适合的任务类型列表 |
| `priority` | integer | 否 | 优先级（数字越大越优先，默认 0） |
| `is_default` | boolean | 否 | 是否为默认模型（默认 `false`） |
| `status` | string | 否 | 状态（`active` 或 `inactive`，默认 `active`） |
| `extra_body` | object | 否 | 额外参数（如 Azure 的 `api_version`） |

### 任务类型

可用的任务类型（`suitable_tasks`）：

- `semantic_parsing` - 语义解析
- `field_mapping` - 字段映射
- `field_semantic` - 字段语义推断
- `insight_generation` - 洞察生成
- `replanning` - 重新规划
- `reasoning` - 推理任务
- `embedding` - 向量化

### 全局配置

```yaml
global:
  default_timeout: 120  # 默认超时时间（秒）
  verify_ssl: true      # 是否验证 SSL 证书
  log_level: "INFO"     # 日志级别
  enable_persistence: false  # 是否启用持久化
```

## 示例配置

### DeepSeek 配置

```yaml
llm_models:
  # DeepSeek Chat（非思考模式）
  - id: "deepseek-chat"
    name: "DeepSeek Chat V3.2"
    model_type: "llm"
    provider: "deepseek"
    api_base: "https://api.deepseek.com"
    model_name: "deepseek-chat"
    api_key: "${DEEPSEEK_API_KEY}"
    openai_compatible: true
    temperature: 0.7
    supports_json_mode: true
    suitable_tasks:
      - "semantic_parsing"
      - "insight_generation"
    priority: 10
    is_default: true
    status: "active"
  
  # DeepSeek Reasoner（思考模式）
  - id: "deepseek-reasoner"
    name: "DeepSeek Reasoner V3.2"
    model_type: "llm"
    provider: "deepseek"
    api_base: "https://api.deepseek.com"
    model_name: "deepseek-reasoner"
    api_key: "${DEEPSEEK_API_KEY}"
    openai_compatible: true
    is_reasoning_model: true
    suitable_tasks:
      - "reasoning"
    priority: 15
    status: "active"
```

### Azure OpenAI 配置

```yaml
llm_models:
  - id: "azure-gpt4"
    name: "Azure GPT-4"
    model_type: "llm"
    provider: "azure"
    api_base: "${AZURE_OPENAI_ENDPOINT}"
    model_name: "${AZURE_OPENAI_DEPLOYMENT_NAME}"
    api_key: "${AZURE_OPENAI_API_KEY}"
    openai_compatible: false
    extra_body:
      api_version: "2024-02-15-preview"
    suitable_tasks:
      - "semantic_parsing"
    priority: 8
    status: "active"
```

### 本地模型配置

```yaml
llm_models:
  - id: "qwen3-local"
    name: "Qwen3 本地"
    model_type: "llm"
    provider: "local"
    api_base: "http://localhost:8000/v1"
    model_name: "qwen3"
    api_key: "EMPTY"
    openai_compatible: true
    suitable_tasks:
      - "semantic_parsing"
    priority: 5
    status: "active"
```

## 配置优先级

ModelManager 按以下优先级加载配置：

1. **YAML 配置文件** - `config/models.yaml`
2. **环境变量** - `LLM_API_BASE`, `LLM_API_KEY` 等
3. **代码中动态创建** - `manager.create(request)`

如果 YAML 文件不存在，ModelManager 会回退到环境变量配置。

## 最佳实践

1. **使用环境变量存储敏感信息**
   ```yaml
   api_key: "${DEEPSEEK_API_KEY}"  # 不要硬编码 API key
   ```

2. **为不同环境创建不同的配置文件**
   ```
   config/
   ├── models.yaml           # 当前环境
   ├── models.dev.yaml       # 开发环境
   ├── models.staging.yaml   # 预发布环境
   └── models.prod.yaml      # 生产环境
   ```

3. **设置合理的优先级**
   - 高质量模型：priority = 10-15
   - 中等质量模型：priority = 5-9
   - 备用模型：priority = 1-4

4. **使用任务类型路由**
   ```yaml
   suitable_tasks:
     - "semantic_parsing"  # 明确指定适合的任务
     - "insight_generation"
   ```

5. **禁用不使用的模型**
   ```yaml
   status: "inactive"  # 保留配置但不启用
   ```

## 故障排查

### 配置文件未加载

检查文件路径是否正确：
```python
# 默认路径：analytics-assistant/config/models.yaml
```

### 环境变量未展开

确保环境变量已设置：
```bash
export DEEPSEEK_API_KEY="your-api-key"
```

### 模型未找到

检查模型 ID 是否正确：
```python
# 列出所有模型
configs = manager.list()
for config in configs:
    print(config.id)
```

## 参考

- [ModelManager 使用指南](../../docs/model_manager_usage.md)
- [DeepSeek API 文档](https://platform.deepseek.com/api-docs/)
- [OpenAI API 文档](https://platform.openai.com/docs/api-reference)
