# YAML 配置管理指南

## 概述

ModelManager 现在支持通过 YAML 文件进行配置管理，提供了更灵活、可维护的模型配置方式。

## ✅ 已完成的功能

### 1. YAML 配置加载
- ✅ 自动从 `config/models.yaml` 加载配置
- ✅ 支持环境变量展开（`${VAR_NAME}` 和 `${VAR_NAME:-default}`）
- ✅ 配置优先级：YAML > 环境变量 > 代码动态创建
- ✅ 自动回退到示例配置文件

### 2. DeepSeek API 集成
- ✅ DeepSeek Chat（非思考模式）
- ✅ DeepSeek Reasoner（思考模式，推理模型）
- ✅ JSON Mode 支持
- ✅ 流式输出支持
- ✅ 任务类型路由

### 3. 配置管理
- ✅ LLM 模型配置
- ✅ Embedding 模型配置
- ✅ 全局配置
- ✅ 多环境支持

## 快速开始

### 1. 配置文件位置

```
analytics-assistant/
└── config/
    ├── models.yaml              # 实际配置文件
    ├── models.example.yaml      # 配置模板
    └── README.md                # 配置文档
```

### 2. 基本配置

```yaml
llm_models:
  - id: "deepseek-chat"
    name: "DeepSeek Chat V3.2"
    model_type: "llm"
    provider: "deepseek"
    api_base: "https://api.deepseek.com"
    model_name: "deepseek-chat"
    api_key: "${DEEPSEEK_API_KEY}"  # 从环境变量读取
    openai_compatible: true
    temperature: 0.7
    supports_streaming: true
    supports_json_mode: true
    suitable_tasks:
      - "semantic_parsing"
      - "insight_generation"
    priority: 10
    is_default: true
    status: "active"
```

### 3. 在代码中使用

```python
from src.infra.ai import get_model_manager, TaskType

# ModelManager 会自动加载 YAML 配置
manager = get_model_manager()

# 方式 1: 使用模型 ID
llm = manager.create_llm(model_id="deepseek-chat")
response = llm.invoke("你好")

# 方式 2: 使用任务类型路由
llm = manager.create_llm(task_type=TaskType.SEMANTIC_PARSING)
response = llm.invoke("分析销售数据")

# 方式 3: 使用推理模型
llm = manager.create_llm(model_id="deepseek-reasoner")
response = llm.invoke("为什么天空是蓝色的？")

# 方式 4: 启用 JSON Mode
llm = manager.create_llm(
    model_id="deepseek-chat",
    enable_json_mode=True
)
response = llm.invoke("返回一个 JSON 对象")

# 方式 5: 启用流式输出
llm = manager.create_llm(
    model_id="deepseek-chat",
    streaming=True
)
for chunk in llm.stream("讲个故事"):
    print(chunk.content, end="", flush=True)
```

## 环境变量支持

### 支持的格式

1. **简单引用**：`${VAR_NAME}`
   - 读取环境变量
   - 如果不存在，保持原样

2. **带默认值**：`${VAR_NAME:-default}`
   - 读取环境变量
   - 如果不存在，使用默认值

### 示例

```yaml
llm_models:
  - id: "deepseek-chat"
    api_key: "${DEEPSEEK_API_KEY}"  # 必须设置环境变量
    api_base: "${API_BASE:-https://api.deepseek.com}"  # 有默认值
    model_name: "${MODEL_NAME:-deepseek-chat}"  # 有默认值
```

```bash
# 设置环境变量
export DEEPSEEK_API_KEY="sk-xxx"
export API_BASE="https://api.deepseek.com"
```

## 配置选项详解

### LLM 模型配置

| 字段 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `id` | string | 是 | - | 模型唯一标识 |
| `name` | string | 是 | - | 模型显示名称 |
| `model_type` | string | 是 | - | `llm` 或 `embedding` |
| `provider` | string | 是 | - | `deepseek`, `openai`, `azure`, `local` 等 |
| `api_base` | string | 是 | - | API 基础 URL |
| `model_name` | string | 是 | - | 模型名称 |
| `api_key` | string | 是 | - | API 密钥 |
| `openai_compatible` | boolean | 否 | `true` | 是否 OpenAI 兼容 |
| `temperature` | float | 否 | `null` | 温度参数（0.0-2.0） |
| `max_tokens` | integer | 否 | `null` | 最大 token 数 |
| `supports_streaming` | boolean | 否 | `true` | 是否支持流式输出 |
| `supports_json_mode` | boolean | 否 | `null` | 是否支持 JSON Mode |
| `is_reasoning_model` | boolean | 否 | `false` | 是否是推理模型 |
| `suitable_tasks` | array | 否 | `[]` | 适合的任务类型 |
| `priority` | integer | 否 | `0` | 优先级（越大越优先） |
| `is_default` | boolean | 否 | `false` | 是否为默认模型 |
| `status` | string | 否 | `active` | `active` 或 `inactive` |
| `extra_body` | object | 否 | `{}` | 额外参数 |

### 任务类型

可用的任务类型（`suitable_tasks`）：

- `semantic_parsing` - 语义解析
- `field_mapping` - 字段映射
- `dimension_hierarchy` - 维度层级
- `insight_generation` - 洞察生成
- `replanning` - 重新规划
- `reasoning` - 推理任务（需要深度思考）
- `embedding` - 向量化

## 多环境配置

### 目录结构

```
config/
├── models.yaml              # 当前环境（gitignore）
├── models.example.yaml      # 配置模板
├── models.dev.yaml          # 开发环境
├── models.staging.yaml      # 预发布环境
└── models.prod.yaml         # 生产环境
```

### 切换环境

```python
from src.infra.ai.config_loader import load_models_from_yaml

# 加载不同环境的配置
dev_config = load_models_from_yaml("config/models.dev.yaml")
prod_config = load_models_from_yaml("config/models.prod.yaml")
```

## 配置示例

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
    max_tokens: 4096
    supports_streaming: true
    supports_json_mode: true
    suitable_tasks:
      - "semantic_parsing"
      - "field_mapping"
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
    temperature: 0.7
    max_tokens: 8192
    supports_streaming: true
    is_reasoning_model: true
    suitable_tasks:
      - "reasoning"
      - "insight_generation"
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
      - "insight_generation"
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
    temperature: 0.7
    suitable_tasks:
      - "semantic_parsing"
      - "field_mapping"
    priority: 5
    status: "active"
```

## 最佳实践

### 1. 安全性

❌ **不要硬编码 API Key**
```yaml
api_key: "sk-xxx"  # 不安全！
```

✅ **使用环境变量**
```yaml
api_key: "${DEEPSEEK_API_KEY}"  # 安全！
```

### 2. 优先级设置

```yaml
# 高质量模型（优先使用）
priority: 15

# 中等质量模型
priority: 10

# 备用模型
priority: 5
```

### 3. 任务路由

```yaml
# 明确指定适合的任务
suitable_tasks:
  - "semantic_parsing"
  - "insight_generation"
```

### 4. 状态管理

```yaml
# 启用模型
status: "active"

# 禁用但保留配置
status: "inactive"
```

### 5. 推理模型标记

```yaml
# DeepSeek Reasoner 是推理模型
is_reasoning_model: true

# DeepSeek Chat 不是推理模型
is_reasoning_model: false
```

## 故障排查

### 问题 1: 配置文件未加载

**症状**：ModelManager 没有加载 YAML 配置

**解决方案**：
1. 检查文件路径：`analytics-assistant/config/models.yaml`
2. 检查文件权限
3. 查看日志输出

### 问题 2: 环境变量未展开

**症状**：API key 显示为 `${DEEPSEEK_API_KEY}`

**解决方案**：
```bash
# 设置环境变量
export DEEPSEEK_API_KEY="your-api-key"

# 验证
echo $DEEPSEEK_API_KEY
```

### 问题 3: 模型未找到

**症状**：`ValueError: Model xxx not found`

**解决方案**：
```python
# 列出所有模型
manager = get_model_manager()
configs = manager.list()
for config in configs:
    print(f"ID: {config.id}, Name: {config.name}")
```

### 问题 4: API 调用失败

**症状**：`API call failed`

**解决方案**：
1. 检查 API key 是否正确
2. 检查网络连接
3. 检查 API base URL
4. 查看详细错误信息

## 测试

### 运行测试

```bash
# 测试 YAML 配置加载
python analytics-assistant/tests/manual/test_yaml_config.py

# 测试 DeepSeek API 调用
python analytics-assistant/tests/manual/test_deepseek_simple.py
```

### 验证配置

```python
from src.infra.ai import get_model_manager

manager = get_model_manager()

# 列出所有配置
configs = manager.list()
print(f"总计: {len(configs)} 个模型")

# 检查默认模型
default_llm = manager.get_default(ModelType.LLM)
print(f"默认 LLM: {default_llm.name if default_llm else 'None'}")

# 测试 API 调用
llm = manager.create_llm(model_id="deepseek-chat")
response = llm.invoke("你好")
print(f"响应: {response.content}")
```

## 参考

- [ModelManager 使用指南](./model_manager_usage.md)
- [配置文件 README](../config/README.md)
- [DeepSeek API 文档](https://platform.deepseek.com/api-docs/)
