# 附录 E：中间件集成详解

## 1. 现有中间件架构

### 1.1 当前中间件列表（8 个）

```python
# tableau_assistant/src/orchestration/workflow/factory.py

from langchain.agents.middleware import (
    TodoListMiddleware,        # LangChain 内置
    SummarizationMiddleware,   # LangChain 内置
    ModelRetryMiddleware,      # LangChain 内置
    ToolRetryMiddleware,       # LangChain 内置
    HumanInTheLoopMiddleware,  # LangChain 内置（可选）
)

from tableau_assistant.src.orchestration.middleware import (
    FilesystemMiddleware,       # 自定义
    PatchToolCallsMiddleware,   # 自定义（待移除）
    OutputValidationMiddleware, # 自定义（待移除）
)
```

### 1.2 优化后中间件列表（6 个）

```python
from langchain.agents.middleware import (
    TodoListMiddleware,        # LangChain 内置
    SummarizationMiddleware,   # LangChain 内置
    ModelRetryMiddleware,      # LangChain 内置
    ToolRetryMiddleware,       # LangChain 内置
    HumanInTheLoopMiddleware,  # LangChain 内置（可选）
)

from tableau_assistant.src.orchestration.middleware import (
    FilesystemMiddleware,       # 自定义
)

# 移除：
# - PatchToolCallsMiddleware（JSON 模式不需要）
# - OutputValidationMiddleware（JSON 模式 + Pydantic 已处理）
```

## 2. 中间件执行顺序

### 2.1 执行流程

```
┌─────────────────────────────────────────────────────────────────┐
│                    中间件执行流程                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Agent 开始:                                                    │
│  1. TodoListMiddleware.before_agent()                          │
│     └── 加载待处理任务                                          │
│                                                                 │
│  LLM 调用前:                                                    │
│  2. SummarizationMiddleware.wrap_model_call()                  │
│     └── 压缩对话历史（token 超阈值时）                          │
│  3. FilesystemMiddleware.wrap_model_call()                     │
│     └── 注入 files 系统提示                                    │
│                                                                 │
│  LLM 调用:                                                      │
│  4. ModelRetryMiddleware.wrap_model_call()                     │
│     └── LLM 调用失败时重试（指数退避）                         │
│                                                                 │
│  工具调用:                                                      │
│  5. ToolRetryMiddleware.wrap_tool_call()                       │
│     └── 工具调用失败时重试（网络/API 错误）                    │
│  6. FilesystemMiddleware.wrap_tool_call()                      │
│     └── 大结果保存到 files                                     │
│                                                                 │
│  Agent 结束:                                                    │
│  7. TodoListMiddleware.after_agent()                           │
│     └── 更新任务状态                                            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 洋葱模型

```
请求 → TodoList → Summarization → Filesystem → ModelRetry → LLM
                                                              ↓
响应 ← TodoList ← Summarization ← Filesystem ← ModelRetry ← LLM
```

## 3. 各中间件配置

### 3.1 SummarizationMiddleware

```python
# 配置参数（通过 .env 管理）
SummarizationMiddleware(
    model=summarization_model,
    trigger=("tokens", config["summarization_token_threshold"]),  # 默认 60K
    keep=("messages", config["messages_to_keep"]),  # 默认保留最近 N 条
)

# .env 配置
# SUMMARIZATION_TOKEN_THRESHOLD=60000
# MESSAGES_TO_KEEP=10
```

### 3.2 ModelRetryMiddleware

```python
# 配置参数
ModelRetryMiddleware(
    max_retries=config["model_max_retries"],  # 默认 3
    initial_delay=1.0,                         # 初始延迟 1 秒
    backoff_factor=2.0,                        # 指数退避：1s, 2s, 4s
    max_delay=60.0,                            # 最大延迟 60 秒
    jitter=True,                               # 添加随机抖动
)

# .env 配置
# MODEL_MAX_RETRIES=3
```

### 3.3 ToolRetryMiddleware

```python
# 配置参数
ToolRetryMiddleware(
    max_retries=config["tool_max_retries"],  # 默认 3
    initial_delay=1.0,
    backoff_factor=2.0,
    max_delay=60.0,
    jitter=True,
)

# .env 配置
# TOOL_MAX_RETRIES=3
```

### 3.4 FilesystemMiddleware

```python
# 配置参数
FilesystemMiddleware(
    tool_token_limit_before_evict=config["filesystem_token_limit"],  # 默认 20000
)

# .env 配置
# FILESYSTEM_TOKEN_LIMIT=20000
```

## 4. 移除中间件的原因

### 4.1 OutputValidationMiddleware

```
移除原因：
1. 当前使用 JSON 模式 + Pydantic 验证已足够
2. with_structured_output() 不支持流式输出
3. 项目使用 call_llm_with_tools + parse_json_response 模式

当前实现：
response = await call_llm_with_tools(
    llm=self.llm,
    prompt=prompt,
    tools=[],
    response_format={"type": "json_object"},  # JSON 模式
)
result = parse_json_response(response, SemanticQuery)  # Pydantic 验证
```

### 4.2 PatchToolCallsMiddleware

```
移除原因：
1. PatchToolCallsMiddleware 用于修复"悬空工具调用"
2. 悬空工具调用：有 tool_call 但无对应 tool_result
3. 使用 JSON 模式输出时，LLM 直接输出 JSON，不会产生工具调用消息
4. 因此不会有悬空工具调用问题
```

## 5. 迁移步骤

### 5.1 Phase 1: 移除冗余中间件

```python
# 修改 create_middleware_stack() 函数

def create_middleware_stack(...) -> List[AgentMiddleware]:
    middleware = []
    
    # 保留的中间件
    middleware.append(TodoListMiddleware())
    middleware.append(SummarizationMiddleware(...))
    middleware.append(ModelRetryMiddleware(...))
    middleware.append(ToolRetryMiddleware(...))
    middleware.append(FilesystemMiddleware(...))
    
    if interrupt_on:
        middleware.append(HumanInTheLoopMiddleware(...))
    
    # 移除：
    # middleware.append(PatchToolCallsMiddleware())
    # middleware.append(OutputValidationMiddleware(...))
    
    return middleware
```

### 5.2 Phase 2: 更新测试

```python
# 更新测试用例，移除对已删除中间件的引用

# 删除：
# from tableau_assistant.src.orchestration.middleware import (
#     PatchToolCallsMiddleware,
#     OutputValidationMiddleware,
# )
```

### 5.3 Phase 3: 清理代码

```bash
# 删除不再需要的文件
# tableau_assistant/src/orchestration/middleware/patch_tool_calls.py
# tableau_assistant/src/orchestration/middleware/output_validation.py
```

## 6. 监控指标

| 指标 | 说明 | 目标 |
|------|------|------|
| summarization_trigger_rate | 摘要触发率 | < 20% |
| model_retry_rate | LLM 重试率 | < 5% |
| tool_retry_rate | 工具重试率 | < 5% |
| filesystem_evict_rate | 文件驱逐率 | < 10% |
