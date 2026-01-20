# ModelManager 使用指南

## 概述

ModelManager 是统一的模型管理器，负责管理所有 LLM 和 Embedding 模型的配置、路由和调用。

## 快速开始

### 1. 获取 ModelManager 实例

```python
from src.infra.ai import get_model_manager

manager = get_model_manager()
```

### 2. 创建模型配置

```python
from src.infra.ai import ModelCreateRequest, ModelType, TaskType

# 创建 LLM 配置
request = ModelCreateRequest(
    name="Qwen3 本地",
    model_type=ModelType.LLM,
    provider="local",
    api_base="http://localhost:8000/v1",
    model_name="qwen3",
    api_key="EMPTY",
    openai_compatible=True,
    temperature=0.7,
    supports_streaming=True,
    supports_json_mode=True,
    suitable_tasks=[
        TaskType.SEMANTIC_PARSING,
        TaskType.FIELD_MAPPING,
        TaskType.DIMENSION_HIERARCHY,
    ],
    priority=10,
    is_default=True,
)

config = manager.create(request)
```

### 3. 创建 LLM 实例

```python
# 方式 1：使用默认配置
llm = manager.create_llm()

# 方式 2：使用任务类型路由（自动选择最优模型）
llm = manager.create_llm(task_type=TaskType.SEMANTIC_PARSING)

# 方式 3：使用推理模型（适合复杂分析任务）
llm = manager.create_llm(task_type=TaskType.REASONING)

# 方式 4：指定模型 ID
llm = manager.create_llm(model_id="local-qwen3")

# 方式 5：覆盖参数
llm = manager.create_llm(
    model_id="local-qwen3",
    temperature=0.8,
    max_tokens=8192,
    enable_json_mode=True,
    streaming=True
)
```

### 4. 使用 LLM

```python
# 非流式调用
response = llm.invoke("你好，请介绍一下自己")
print(response.content)

# 流式调用
for chunk in llm.stream("你好，请介绍一下自己"):
    print(chunk.content, end="", flush=True)

# 异步流式调用
async for chunk in llm.astream("你好，请介绍一下自己"):
    print(chunk.content, end="", flush=True)
```

## 环境变量配置

ModelManager 会自动从环境变量加载默认配置：

```bash
# .env

# 默认 LLM 配置
LLM_API_BASE=http://localhost:8000/v1
LLM_API_KEY=EMPTY
LLM_MODEL_NAME=qwen3

# 智谱 Embedding 配置
ZHIPUAI_API_KEY=your_zhipu_api_key
```

## 模型管理

### 列出模型

```python
# 列出所有 LLM 模型
llm_configs = manager.list(model_type=ModelType.LLM)

# 列出活跃模型
active_configs = manager.list(status=ModelStatus.ACTIVE)
```

### 更新模型

```python
from src.infra.ai import ModelUpdateRequest

update_request = ModelUpdateRequest(
    temperature=0.8,
    priority=10,
)
updated = manager.update("local-qwen3", update_request)
```

### 删除模型

```python
manager.delete("local-qwen3")
```

### 设置默认模型

```python
manager.set_default("local-qwen3")
```

## 智能路由

ModelManager 支持基于任务类型的智能路由，自动选择最适合的模型：

```python
# 自动路由到适合语义解析的模型
llm = manager.create_llm(task_type=TaskType.SEMANTIC_PARSING)

# 自动路由到适合洞察生成的模型
llm = manager.create_llm(task_type=TaskType.INSIGHT_GENERATION)
```

路由规则：
1. 筛选适合该任务的模型（`suitable_tasks` 包含该任务类型）
2. 按优先级排序（`priority` 越大越优先）
3. 选择优先级最高且已启用的模型
4. 如果没有可用模型，返回默认模型

## 特性支持

### JSON Mode

ModelManager 内置了 JSON Mode 适配器，能够根据不同的提供商自动适配 JSON Mode 参数。

```python
# 启用 JSON Mode
llm = manager.create_llm(
    model_id="local-qwen3",
    enable_json_mode=True
)

response = llm.invoke("返回一个包含姓名和年龄的 JSON 对象")
# 输出：{"name": "张三", "age": 25}
```

**支持的提供商**：
- **DeepSeek, OpenAI, Azure, Local, Qwen, Kimi**: 通过 `model_kwargs.response_format` 传递
- **Custom**: 通过 `extra_body.response_format` 传递
- **Anthropic**: 不支持原生 JSON Mode（依赖 Prompt 约束）

**自动适配**：
```python
# DeepSeek 模型
llm = manager.create_llm(
    model_id="deepseek-chat",
    enable_json_mode=True
)
# 自动使用 model_kwargs.response_format

# Custom 模型
llm = manager.create_llm(
    model_id="custom-model",
    enable_json_mode=True
)
# 自动使用 extra_body.response_format
```

### 流式输出

```python
# 启用流式输出
llm = manager.create_llm(
    model_id="local-qwen3",
    streaming=True
)

for chunk in llm.stream("你好"):
    print(chunk.content, end="", flush=True)
```

### 参数覆盖

```python
# 运行时覆盖配置参数
llm = manager.create_llm(
    model_id="local-qwen3",
    temperature=0.9,  # 覆盖配置中的默认值
    max_tokens=8192,
    top_p=0.95
)
```

## 推理模型支持

ModelManager 完整支持推理模型（如 DeepSeek-R1），这些模型具有深度思考能力。

### 配置推理模型

```python
# 注册 DeepSeek-R1
request = ModelCreateRequest(
    name="DeepSeek-R1",
    model_type=ModelType.LLM,
    provider="deepseek",
    api_base="http://localhost:8001/v1",
    model_name="deepseek-reasoner",
    api_key="your-api-key",
    openai_compatible=True,
    is_reasoning_model=True,  # 标记为推理模型
    suitable_tasks=[
        TaskType.REASONING,
        TaskType.INSIGHT_GENERATION,
    ],
    priority=10,
)
config = manager.create(request)
```

### 使用推理模型

```python
# 使用任务类型路由
llm = manager.create_llm(task_type=TaskType.REASONING)

# 调用模型
response = llm.invoke("分析销售额下降的原因")

# 获取最终答案
print("答案:", response.content)

# 获取思考过程（推理模型特有）
thinking = response.additional_kwargs.get('thinking', '')
print("思考过程:", thinking)
```

详细使用指南请参考：[推理模型使用指南](./reasoning_model_guide.md)

## Embedding 模型支持

ModelManager 统一管理 Embedding 模型，支持多种提供商。

### 配置 Embedding 模型

```python
# 方式 1：OpenAI Embeddings
request = ModelCreateRequest(
    name="OpenAI Embedding",
    model_type=ModelType.EMBEDDING,
    provider="openai",
    api_base="https://api.openai.com/v1",
    model_name="text-embedding-3-small",
    api_key="your-openai-key",
    suitable_tasks=[TaskType.EMBEDDING],
    priority=5,
)
config = manager.create(request)

# 方式 2：智谱 AI Embeddings
request = ModelCreateRequest(
    name="Zhipu Embedding",
    model_type=ModelType.EMBEDDING,
    provider="zhipu",
    api_base="https://open.bigmodel.cn/api/paas/v4",
    model_name="embedding-2",
    api_key="your-zhipu-key",
    suitable_tasks=[TaskType.EMBEDDING],
    priority=10,
    is_default=True,  # 设为默认 Embedding
)
config = manager.create(request)

# 方式 3：Azure OpenAI Embeddings
request = ModelCreateRequest(
    name="Azure Embedding",
    model_type=ModelType.EMBEDDING,
    provider="azure",
    api_base="https://your-instance.openai.azure.com",
    model_name="text-embedding-ada-002",
    api_key="your-azure-key",
    suitable_tasks=[TaskType.EMBEDDING],
    priority=5,
    extra_body={"api_version": "2024-02-15-preview"},
)
config = manager.create(request)

# 方式 4：本地 Embedding 模型
request = ModelCreateRequest(
    name="Local BGE Embedding",
    model_type=ModelType.EMBEDDING,
    provider="local",
    api_base="http://localhost:8000/v1",
    model_name="bge-large-zh-v1.5",
    api_key="EMPTY",
    suitable_tasks=[TaskType.EMBEDDING],
    priority=5,
)
config = manager.create(request)
```

### 使用 Embedding 模型

```python
from src.infra.ai import get_embeddings

# 方式 1：使用默认 Embedding
embeddings = get_embeddings()

# 方式 2：指定模型 ID
embeddings = get_embeddings(model_id="zhipu-embedding-2")

# 向量化文档
vectors = embeddings.embed_documents(["文本1", "文本2", "文本3"])
print(f"生成了 {len(vectors)} 个向量，每个向量维度: {len(vectors[0])}")

# 向量化查询
query_vector = embeddings.embed_query("查询文本")
print(f"查询向量维度: {len(query_vector)}")
```

### 环境变量自动加载

ModelManager 会自动从环境变量加载 Embedding 配置：

```bash
# .env

# 智谱 Embedding（优先）
ZHIPUAI_API_KEY=your_zhipu_api_key

# 或使用 OpenAI Embedding
LLM_API_KEY=your_openai_key
```

如果设置了 `ZHIPUAI_API_KEY`，ModelManager 会自动创建智谱 Embedding 配置并设为默认。

### Embedding 最佳实践

1. **选择合适的模型**：
   - 中文场景：智谱 embedding-2（1024 维）或本地 BGE 模型
   - 英文场景：OpenAI text-embedding-3-small（1536 维）
   - 多语言：OpenAI text-embedding-3-large（3072 维）

2. **使用缓存**：Embedding 计算成本高，建议启用缓存
   ```python
   # 缓存会在后续任务中实现（任务 1.3）
   ```

3. **批量处理**：一次性向量化多个文档，提升效率
   ```python
   # 批量向量化
   texts = ["文本1", "文本2", "文本3", ...]
   vectors = embeddings.embed_documents(texts)
   ```

4. **维度选择**：根据场景选择合适的维度
   - 小规模数据（< 10K）：使用高维向量（1536+）
   - 大规模数据（> 100K）：使用低维向量（768-1024）

## 最佳实践

1. **使用任务类型路由**：让 ModelManager 自动选择最优模型
2. **配置合理的优先级**：确保高质量模型优先被选择
3. **设置默认模型**：确保在没有匹配模型时有降级方案
4. **使用环境变量**：便于在不同环境中切换配置
5. **启用流式输出**：提升用户体验，实时显示生成内容

## 故障排查

### 问题：找不到模型

```python
# 错误
llm = manager.create_llm(model_id="non-existent-model")
# ValueError: Model non-existent-model not found

# 解决方案：检查模型是否已注册
configs = manager.list()
print([c.id for c in configs])
```

### 问题：没有可用的模型

```python
# 错误
llm = manager.create_llm()
# ValueError: No LLM model available

# 解决方案：创建默认模型或从环境变量加载
# 确保设置了 LLM_API_BASE 和 LLM_API_KEY
```

### 问题：任务路由失败

```python
# 错误
llm = manager.create_llm(task_type=TaskType.SEMANTIC_PARSING)
# 返回默认模型而不是期望的模型

# 解决方案：检查模型的 suitable_tasks 配置
config = manager.get("local-qwen3")
print(config.suitable_tasks)
```

## 下一步

- 查看 [ModelManager 设计文档](../../../.kiro/specs/system-wide-refactor/attachments/12-model-manager-design.md)
- 查看 [单元测试](../tests/infra/ai/test_model_manager.py) 了解更多使用示例
- 实现 Embedding 模型支持（任务 1.1.2）
- 实现 JSON Mode 适配器集成（任务 1.1.3）
