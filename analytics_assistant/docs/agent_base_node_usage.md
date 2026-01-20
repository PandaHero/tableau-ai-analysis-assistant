# Agent Base Node 使用指南

## 概述

`agents/base/node.py` 提供了 Agent 层的基础工具函数，其中最重要的是 `get_llm()` 函数。

在系统重构后，`get_llm()` 现在通过 `ModelManager` 统一管理 LLM 实例，提供更强大的功能：
- 自动选择 temperature（基于 agent_name）
- 任务类型路由（自动选择最优模型）
- 显式指定模型
- JSON Mode 支持
- 参数覆盖

## 核心功能

### 1. 基本用法

```python
from analytics_assistant.src.agents.base import get_llm

# 使用默认配置
llm = get_llm()
```

### 2. 使用 agent_name 自动选择 temperature

每个 Agent 都有推荐的 temperature 配置：

```python
# 语义解析器（需要精确理解）
llm = get_llm(agent_name="semantic_parser")  # temperature=0.1

# 字段映射器（需要精确映射）
llm = get_llm(agent_name="field_mapper")  # temperature=0.1

# 维度层级（需要精确推断）
llm = get_llm(agent_name="dimension_hierarchy")  # temperature=0.1

# 洞察生成（需要创造性）
llm = get_llm(agent_name="insight")  # temperature=0.4

# 重新规划（需要判断）
llm = get_llm(agent_name="replanner")  # temperature=0.2
```

### 3. 显式指定 temperature（覆盖 agent_name）

```python
# 覆盖 agent_name 的默认 temperature
llm = get_llm(agent_name="semantic_parser", temperature=0.3)

# 或直接指定 temperature
llm = get_llm(temperature=0.5)
```

### 4. 使用任务类型路由（自动选择最优模型）

```python
from analytics_assistant.src.infra.ai import TaskType

# 自动选择适合语义解析的模型
llm = get_llm(task_type=TaskType.SEMANTIC_PARSING)

# 自动选择适合推理的模型（如 DeepSeek-R1）
llm = get_llm(task_type=TaskType.REASONING)

# 自动选择适合字段映射的模型
llm = get_llm(task_type=TaskType.FIELD_MAPPING)
```

### 5. 显式指定模型

```python
# 使用特定模型
llm = get_llm(model_id="deepseek-chat", temperature=0.7)

# 使用推理模型
llm = get_llm(model_id="deepseek-reasoner", temperature=0.7)
```

### 6. 启用 JSON Mode

```python
# 启用 JSON Mode（自动适配不同提供商）
llm = get_llm(
    agent_name="semantic_parser",
    enable_json_mode=True
)
```

### 7. 组合参数

```python
# 组合使用多个参数
llm = get_llm(
    agent_name="semantic_parser",
    task_type=TaskType.SEMANTIC_PARSING,
    enable_json_mode=True,
    temperature=0.3,  # 显式参数优先
    max_tokens=2048,
    streaming=True,
)
```

## Agent Temperature 配置

系统预定义了每个 Agent 的推荐 temperature：

```python
AGENT_TEMPERATURE_CONFIG = {
    "semantic_parser": 0.1,     # 需要精确理解用户意图
    "dimension_hierarchy": 0.1, # 需要精确推断层级关系
    "field_mapper": 0.1,        # 需要精确的字段映射
    "insight": 0.4,             # 需要创造性发现洞察
    "replanner": 0.2,           # 需要判断是否重规划
    "default": 0.2,
}
```

你可以通过 `get_agent_temperature()` 函数查询：

```python
from analytics_assistant.src.agents.base import get_agent_temperature

temp = get_agent_temperature("semantic_parser")  # 返回 0.1
```

## 参数优先级

当多个参数同时指定时，优先级如下：

1. **temperature**: 显式参数 > agent_name 配置 > ModelManager 默认值
2. **model_id**: 显式指定 > task_type 路由 > 默认模型

## 完整示例

### 示例 1：语义解析器节点

```python
from analytics_assistant.src.agents.base import get_llm, call_llm_with_tools
from analytics_assistant.src.infra.ai import TaskType

async def semantic_parser_node(state, config):
    # 使用任务类型路由 + agent_name temperature
    llm = get_llm(
        agent_name="semantic_parser",
        task_type=TaskType.SEMANTIC_PARSING,
        enable_json_mode=True,
    )
    
    messages = PROMPT.format_messages(question=state["question"])
    response = await call_llm_with_tools(llm, messages, tools=[])
    
    result = parse_json_response(response.content, SemanticQuery)
    return {"semantic_query": result}
```

### 示例 2：洞察生成节点（使用推理模型）

```python
async def insight_generator_node(state, config):
    # 使用推理模型（DeepSeek-R1）
    llm = get_llm(
        model_id="deepseek-reasoner",
        temperature=0.7,
    )
    
    messages = PROMPT.format_messages(data=state["data"])
    response = await call_llm_with_tools(llm, messages, tools=[])
    
    # 获取思考过程（R1 模型特性）
    thinking = response.additional_kwargs.get("thinking", "")
    answer = response.content
    
    return {"insight": answer, "thinking": thinking}
```

### 示例 3：字段映射节点

```python
async def field_mapper_node(state, config):
    # 使用 agent_name 自动选择 temperature
    llm = get_llm(
        agent_name="field_mapper",
        enable_json_mode=True,
    )
    
    messages = PROMPT.format_messages(
        question=state["question"],
        fields=state["fields"]
    )
    
    response = await call_llm_with_tools(llm, messages, tools=[])
    result = parse_json_response(response.content, FieldMapping)
    
    return {"field_mapping": result}
```

## 与旧版本的区别

### 旧版本（tableau_assistant）

```python
from tableau_assistant.src.infra.ai import get_llm

# 只能指定 temperature
llm = get_llm(temperature=0.1, enable_json_mode=True)
```

### 新版本（analytics_assistant）

```python
from analytics_assistant.src.agents.base import get_llm
from analytics_assistant.src.infra.ai import TaskType

# 支持更多功能
llm = get_llm(
    agent_name="semantic_parser",  # 自动选择 temperature
    task_type=TaskType.SEMANTIC_PARSING,  # 任务类型路由
    model_id="deepseek-chat",  # 显式指定模型
    enable_json_mode=True,
    max_tokens=2048,
)
```

## 最佳实践

1. **优先使用 agent_name**：让系统自动选择合适的 temperature
2. **使用 task_type 路由**：让系统自动选择最优模型
3. **显式指定 model_id**：仅在需要特定模型时使用
4. **启用 JSON Mode**：当需要结构化输出时
5. **覆盖参数**：仅在需要微调时使用

## 测试

运行单元测试：

```bash
cd analytics-assistant
python -m pytest tests/agents/base/test_node.py -v
```

所有 12 个测试应该通过：
- 4 个 `get_agent_temperature()` 测试
- 8 个 `get_llm()` 测试

## 相关文档

- [ModelManager 使用指南](./model_manager_usage.md)
- [YAML 配置指南](./yaml_config_guide.md)
- [推理模型指南](./reasoning_model_guide.md)
