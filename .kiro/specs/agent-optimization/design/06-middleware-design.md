# 中间件设计

## 1. 设计目标

简化中间件架构，只保留必要的核心中间件，使用 LangChain 内置中间件。

## 2. 中间件架构

### 2.1 核心中间件（4 个）

| 中间件 | 来源 | 职责 |
|--------|------|------|
| SummarizationMiddleware | LangChain 内置 | 对话历史压缩（已实现） |
| ModelRetryMiddleware | LangChain 内置 | LLM 调用重试（已实现） |
| ToolRetryMiddleware | LangChain 内置 | 工具调用重试（已实现） |
| FilesystemMiddleware | 自定义（已实现） | 大文件缓存 |

### 2.2 移除的中间件

| 中间件 | 移除原因 |
|--------|---------|
| OutputValidationMiddleware | 使用 JSON 模式 + Pydantic 验证已足够 |
| PatchToolCallsMiddleware | 使用 JSON 模式输出时不需要（修复悬空工具调用）|

### 2.3 中间件执行顺序

```
┌─────────────────────────────────────────────────────────────────┐
│                    中间件执行顺序                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  LLM 调用前:                                                    │
│  1. SummarizationMiddleware.wrap_model_call()                  │
│     └── 压缩对话历史（LangChain 内置，已配置）                  │
│  2. FilesystemMiddleware.before_model()                        │
│     └── 注入 files 系统提示                                    │
│                                                                 │
│  LLM 调用:                                                      │
│  3. ModelRetryMiddleware.wrap_model_call()                     │
│     └── LLM 调用失败时重试（LangChain 内置，指数退避）          │
│                                                                 │
│  工具调用:                                                      │
│  4. ToolRetryMiddleware.wrap_tool_call()                       │
│     └── 工具调用失败时重试（LangChain 内置，网络/API 错误）     │
│  5. FilesystemMiddleware.after_tool()                          │
│     └── 大结果保存到 files                                     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## 3. 现有实现（无需修改）

### 3.1 SummarizationMiddleware（LangChain 内置）

项目已在 `factory.py` 中配置：

```python
from langchain.agents.middleware import SummarizationMiddleware

# 已配置在 create_middleware_stack()
middleware.append(SummarizationMiddleware(
    model=summarization_model,
    trigger=("tokens", config["summarization_token_threshold"]),  # 默认 60K
    keep=("messages", config["messages_to_keep"]),  # 默认保留最近 N 条
))
```

**配置参数**（通过 `.env` 管理）：
- `summarization_token_threshold`: 触发摘要的 token 阈值（默认 60K）
- `messages_to_keep`: 保留的最近消息数

### 3.2 ModelRetryMiddleware（LangChain 内置）

```python
from langchain.agents.middleware import ModelRetryMiddleware

# 已配置在 create_middleware_stack()
middleware.append(ModelRetryMiddleware(
    max_retries=config["model_max_retries"],  # 默认 3
    initial_delay=1.0,
    backoff_factor=2.0,  # 指数退避：1s, 2s, 4s
    max_delay=60.0,
    jitter=True,
))
```

### 3.3 ToolRetryMiddleware（LangChain 内置）

```python
from langchain.agents.middleware import ToolRetryMiddleware

# 已配置在 create_middleware_stack()
middleware.append(ToolRetryMiddleware(
    max_retries=config["tool_max_retries"],  # 默认 3
    initial_delay=1.0,
    backoff_factor=2.0,
    max_delay=60.0,
    jitter=True,
))
```

## 4. FilesystemMiddleware（已实现）

### 4.1 现有功能

参考 `tableau_assistant/src/orchestration/middleware/filesystem.py`：

```python
class FilesystemMiddleware(AgentMiddleware):
    """文件系统中间件
    
    功能：
    1. 大工具结果自动保存到文件系统
    2. 提供文件读写工具（ls, read_file, write_file, edit_file, glob, grep）
    3. 注入文件系统系统提示
    """
    
    # 已实现的功能
    - wrap_model_call: 注入文件系统系统提示
    - wrap_tool_call: 大结果自动保存到文件
    - 提供文件操作工具
```

### 4.2 优化建议

```python
# 可配置的大文件阈值（已支持）
class FilesystemMiddleware(AgentMiddleware):
    def __init__(
        self,
        *,
        backend: BACKEND_TYPES | None = None,
        system_prompt: str | None = None,
        custom_tool_descriptions: dict[str, str] | None = None,
        tool_token_limit_before_evict: int | None = 20000,  # 可配置
    ):
        ...
```

## 5. 中间件简化（本次优化）

### 5.1 移除 OutputValidationMiddleware

**原因**：
- 当前使用 JSON 模式 + Pydantic 验证已足够
- `with_structured_output()` 不支持流式输出，项目使用 `call_llm_with_tools` 模式
- JSON 模式输出 + `parse_json_response()` 已经处理验证

**当前实现**：
```python
# 当前使用 JSON 模式（支持流式）
response = await call_llm_with_tools(
    llm=self.llm,
    prompt=prompt,
    tools=[],  # 无工具调用
    response_format={"type": "json_object"},  # JSON 模式
)
result = parse_json_response(response, SemanticQuery)  # Pydantic 验证
```

### 5.2 移除 PatchToolCallsMiddleware

**原因**：
- PatchToolCallsMiddleware 用于修复"悬空工具调用"（有 tool_call 但无对应 tool_result）
- 使用 JSON 模式输出时，LLM 直接输出 JSON，不会产生工具调用消息
- 因此不会有悬空工具调用问题

**注意**：如果某些场景仍需要工具调用模式，可保留作为可选。

## 6. 中间件集成（现有代码）

### 6.1 当前中间件列表

```python
# tableau_assistant/src/orchestration/workflow/factory.py

def create_middleware_stack(...) -> List[AgentMiddleware]:
    middleware = []
    
    # 1. TodoListMiddleware - 任务队列管理
    middleware.append(TodoListMiddleware())
    
    # 2. SummarizationMiddleware - 对话历史压缩（LangChain 内置）
    middleware.append(SummarizationMiddleware(
        model=summarization_model,
        trigger=("tokens", config["summarization_token_threshold"]),
        keep=("messages", config["messages_to_keep"]),
    ))
    
    # 3. ModelRetryMiddleware - LLM 调用重试（LangChain 内置）
    middleware.append(ModelRetryMiddleware(
        max_retries=config["model_max_retries"],
        initial_delay=1.0,
        backoff_factor=2.0,
        max_delay=60.0,
        jitter=True,
    ))
    
    # 4. ToolRetryMiddleware - 工具调用重试（LangChain 内置）
    middleware.append(ToolRetryMiddleware(
        max_retries=config["tool_max_retries"],
        initial_delay=1.0,
        backoff_factor=2.0,
        max_delay=60.0,
        jitter=True,
    ))
    
    # 5. FilesystemMiddleware - 大文件缓存（自定义）
    middleware.append(FilesystemMiddleware(
        tool_token_limit_before_evict=config["filesystem_token_limit"],
    ))
    
    # 6. PatchToolCallsMiddleware - 修复悬空工具调用（待移除）
    middleware.append(PatchToolCallsMiddleware())
    
    # 7. HumanInTheLoopMiddleware - 人工确认（可选）
    if interrupt_on:
        middleware.append(HumanInTheLoopMiddleware(interrupt_on=interrupt_on))
    
    # 8. OutputValidationMiddleware - 输出验证（待移除）
    middleware.append(OutputValidationMiddleware(strict=False, retry_on_failure=True))
    
    return middleware
```

### 6.2 优化后中间件列表

```python
def create_middleware_stack(...) -> List[AgentMiddleware]:
    middleware = []
    
    # 1. TodoListMiddleware - 任务队列管理
    middleware.append(TodoListMiddleware())
    
    # 2. SummarizationMiddleware - 对话历史压缩（LangChain 内置）
    middleware.append(SummarizationMiddleware(
        model=summarization_model,
        trigger=("tokens", config["summarization_token_threshold"]),
        keep=("messages", config["messages_to_keep"]),
    ))
    
    # 3. ModelRetryMiddleware - LLM 调用重试（LangChain 内置）
    middleware.append(ModelRetryMiddleware(
        max_retries=config["model_max_retries"],
        initial_delay=1.0,
        backoff_factor=2.0,
        max_delay=60.0,
        jitter=True,
    ))
    
    # 4. ToolRetryMiddleware - 工具调用重试（LangChain 内置）
    middleware.append(ToolRetryMiddleware(
        max_retries=config["tool_max_retries"],
        initial_delay=1.0,
        backoff_factor=2.0,
        max_delay=60.0,
        jitter=True,
    ))
    
    # 5. FilesystemMiddleware - 大文件缓存（自定义）
    middleware.append(FilesystemMiddleware(
        tool_token_limit_before_evict=config["filesystem_token_limit"],
    ))
    
    # 6. HumanInTheLoopMiddleware - 人工确认（可选）
    if interrupt_on:
        middleware.append(HumanInTheLoopMiddleware(interrupt_on=interrupt_on))
    
    # 移除：PatchToolCallsMiddleware（JSON 模式不需要）
    # 移除：OutputValidationMiddleware（JSON 模式 + Pydantic 已处理）
    
    return middleware
```

## 7. 关于 with_structured_output 的说明

### 7.1 为什么不使用 with_structured_output

```
with_structured_output() 的限制：
1. 不支持流式输出（streaming）
2. 对某些模型不可靠（如 DeepSeek R1）
3. 项目需要流式输出以提升用户体验
```

### 7.2 当前使用的模式

```python
# 当前使用 JSON 模式 + parse_json_response（支持流式）
response = await call_llm_with_tools(
    llm=self.llm,
    prompt=prompt,
    tools=[],
    response_format={"type": "json_object"},  # JSON 模式
)
result = parse_json_response(response, SemanticQuery)  # Pydantic 验证
```

### 7.3 为什么移除 PatchToolCallsMiddleware

```
PatchToolCallsMiddleware 解决的问题：
- 修复"悬空工具调用"（有 tool_call 但无对应 tool_result）
- 这种情况发生在 LLM 输出工具调用消息，但工具执行失败或被中断时

使用 JSON 模式后：
1. LLM 直接输出 JSON 数据
2. 不会产生工具调用消息
3. 因此不会有悬空工具调用问题
```

## 8. 性能对比

### 8.1 中间件数量

| 场景 | 当前 | 优化后 | 减少 |
|------|------|--------|------|
| 中间件数量 | 8 | 6 | 25% |

### 8.2 移除的中间件

| 中间件 | 移除原因 |
|--------|---------|
| OutputValidationMiddleware | JSON 模式 + Pydantic 已处理 |
| PatchToolCallsMiddleware | JSON 模式不会产生悬空工具调用 |

## 9. 迁移策略

### Phase 1: 移除冗余中间件
1. 移除 OutputValidationMiddleware
2. 移除 PatchToolCallsMiddleware
3. 更新 `create_middleware_stack()` 函数
4. 更新测试用例

### Phase 2: 验证现有中间件
1. 验证 SummarizationMiddleware 配置正确
2. 验证 ModelRetryMiddleware 配置正确
3. 验证 ToolRetryMiddleware 配置正确
4. 验证 FilesystemMiddleware 功能正常

### Phase 3: 配置优化
1. 根据模型上下文长度调整 summarization_token_threshold
2. 根据网络环境调整重试参数
3. 根据数据量调整 filesystem_token_limit
