# 中间件层设计

## 概述

本文档描述中间件层的详细设计，包括自主实现的 FilesystemMiddleware 和 PatchToolCallsMiddleware。

对应项目结构：`src/middleware/`

---

## 中间件分类

| 中间件 | 来源 | 功能 | 提供的工具 |
|--------|------|------|-----------|
| `TodoListMiddleware` | LangChain | 任务队列管理 | `write_todos`, `read_todos` |
| `SummarizationMiddleware` | LangChain | 对话历史自动总结 | 无（自动触发） |
| `ModelRetryMiddleware` | LangChain | LLM 调用失败自动重试 | 无（自动触发） |
| `ToolRetryMiddleware` | LangChain | 工具调用失败自动重试 | 无（自动触发） |
| `HumanInTheLoopMiddleware` | LangChain | 人工确认（可选） | 无（自动触发） |
| `FilesystemMiddleware` | **自主实现** | 大结果自动转存 | `read_file`, `write_file` |
| `PatchToolCallsMiddleware` | **自主实现** | 修复悬空工具调用 | 无（自动触发） |

---

## 中间件 vs 工具 的区别

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    中间件 vs 工具 对比                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  中间件（Middleware）                                                        │
│  ├─ 定义: Agent 执行过程中自动生效的能力增强                                 │
│  ├─ 调用方式: 自动触发，无需 Agent 显式调用                                  │
│  ├─ 分类:                                                                    │
│  │   ├─ 提供工具的中间件: TodoListMiddleware → write_todos                  │
│  │   └─ 自动触发的中间件: SummarizationMiddleware, ModelRetryMiddleware     │
│  └─ 示例: token 超限时自动总结、LLM 调用失败自动重试                         │
│                                                                              │
│  工具（Tool）                                                                │
│  ├─ 定义: Agent 可以显式调用的功能单元                                       │
│  ├─ 调用方式: Agent 通过 tool_calls 显式调用                                 │
│  ├─ 来源:                                                                    │
│  │   ├─ 业务工具: 我们实现的工具（get_metadata, get_schema_module）         │
│  │   └─ 中间件工具: 中间件注入的工具（write_todos, read_file）              │
│  └─ 示例: LLM 决定调用 get_schema_module 获取 Schema 规则                   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 1. FilesystemMiddleware

### 职责

- 大结果自动转存到文件
- 提供文件读写工具

### 实现

```python
# tableau_assistant/src/middleware/filesystem.py

class FilesystemMiddleware:
    """
    文件系统中间件
    
    功能：
    1. 检测工具返回结果的 token 数量
    2. 超过阈值时自动保存到文件
    3. 提供 read_file 和 write_file 工具
    """
    
    def __init__(self, tool_token_limit_before_evict: int = 20000):
        self.token_limit = tool_token_limit_before_evict
        self.temp_dir = Path(tempfile.gettempdir()) / "tableau_assistant"
        self.temp_dir.mkdir(exist_ok=True)
    
    def get_tools(self) -> List[BaseTool]:
        """返回中间件提供的工具"""
        return [self.read_file, self.write_file]
    
    @tool
    def read_file(self, file_path: str) -> str:
        """
        读取文件内容
        
        Args:
            file_path: 文件路径
        
        Returns:
            文件内容
        """
        path = Path(file_path)
        if not path.exists():
            return f"<error>文件不存在: {file_path}</error>"
        return path.read_text(encoding="utf-8")
    
    @tool
    def write_file(self, file_path: str, content: str) -> str:
        """
        写入文件内容
        
        Args:
            file_path: 文件路径
            content: 文件内容
        
        Returns:
            写入结果
        """
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return f"已写入文件: {file_path}"
    
    def process_tool_result(self, result: Any) -> Any:
        """
        处理工具返回结果
        
        如果结果超过 token 限制，保存到文件并返回文件路径
        """
        result_str = str(result)
        token_count = self._estimate_tokens(result_str)
        
        if token_count > self.token_limit:
            # 保存到临时文件
            file_path = self._save_to_temp_file(result_str)
            return f"结果已保存到文件: {file_path}\n使用 read_file 工具读取内容。"
        
        return result
    
    def _estimate_tokens(self, text: str) -> int:
        """估算 token 数量（简单估算：字符数 / 4）"""
        return len(text) // 4
    
    def _save_to_temp_file(self, content: str) -> str:
        """保存到临时文件"""
        file_name = f"result_{uuid.uuid4().hex[:8]}.txt"
        file_path = self.temp_dir / file_name
        file_path.write_text(content, encoding="utf-8")
        return str(file_path)
```

---

## 2. PatchToolCallsMiddleware

### 职责

- 修复悬空的工具调用
- 确保工具调用链完整

### 实现

```python
# tableau_assistant/src/middleware/patch_tool_calls.py

class PatchToolCallsMiddleware:
    """
    修复悬空工具调用中间件
    
    问题场景：
    - LLM 生成了 tool_call，但没有对应的 tool_result
    - 可能导致后续处理出错
    
    解决方案：
    - 检测悬空的 tool_call
    - 自动补充空的 tool_result
    """
    
    def process_messages(self, messages: List[Message]) -> List[Message]:
        """
        处理消息列表，修复悬空的工具调用
        """
        result = []
        pending_tool_calls = {}
        
        for msg in messages:
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                # 记录待处理的工具调用
                for tc in msg.tool_calls:
                    pending_tool_calls[tc['id']] = tc
            
            if isinstance(msg, ToolMessage):
                # 移除已处理的工具调用
                if msg.tool_call_id in pending_tool_calls:
                    del pending_tool_calls[msg.tool_call_id]
            
            result.append(msg)
        
        # 为悬空的工具调用补充空结果
        for tc_id, tc in pending_tool_calls.items():
            result.append(ToolMessage(
                content="<error>工具调用未完成</error>",
                tool_call_id=tc_id
            ))
        
        return result
```

---

## 3. LangChain 内置中间件配置

### TodoListMiddleware

```python
from langchain.agents.middleware import TodoListMiddleware

# 配置
todo_middleware = TodoListMiddleware()

# 提供的工具
# - write_todos(todos: List[str]): 写入待办事项
# - read_todos(): 读取待办事项
```

### SummarizationMiddleware

```python
from langchain.agents.middleware import SummarizationMiddleware

# 配置
summarization_middleware = SummarizationMiddleware(
    model="gpt-4",
    trigger=("tokens", 100000),  # token 超过 100000 时触发
    keep=("messages", 10),       # 保留最近 10 条消息
)

# 自动触发，无需显式调用
```

### ModelRetryMiddleware

```python
from langchain.agents.middleware import ModelRetryMiddleware

# 配置
model_retry_middleware = ModelRetryMiddleware(
    max_retries=3,
    retry_on=[
        "rate_limit_exceeded",
        "server_error",
        "timeout",
    ]
)

# 自动触发，无需显式调用
```

### ToolRetryMiddleware

```python
from langchain.agents.middleware import ToolRetryMiddleware

# 配置
tool_retry_middleware = ToolRetryMiddleware(
    max_retries=3,
    retry_on=[
        "connection_error",
        "timeout",
    ]
)

# 自动触发，无需显式调用
```

### HumanInTheLoopMiddleware

```python
from langchain.agents.middleware import HumanInTheLoopMiddleware

# 配置（可选）
human_middleware = HumanInTheLoopMiddleware(
    interrupt_on=["write_todos"],  # 在调用 write_todos 时暂停
)

# 与 Replanner 的协作流程：
# 1. Replanner 调用 write_todos
# 2. HumanInTheLoopMiddleware 自动暂停
# 3. 用户审查问题（选择/修改/拒绝）
# 4. 继续执行或结束
```

---

## 中间件栈配置

```python
def create_middleware_stack(config: Dict[str, Any]) -> List[Middleware]:
    """创建中间件栈"""
    middleware = [
        # LangChain 内置
        TodoListMiddleware(),
        SummarizationMiddleware(
            model=config.get("model_name", "gpt-4"),
            trigger=("tokens", config.get("summarization_token_threshold", 100000)),
            keep=("messages", config.get("messages_to_keep", 10)),
        ),
        ModelRetryMiddleware(max_retries=config.get("model_max_retries", 3)),
        ToolRetryMiddleware(max_retries=config.get("tool_max_retries", 3)),
        
        # 自主实现
        FilesystemMiddleware(
            tool_token_limit_before_evict=config.get("filesystem_token_limit", 20000),
        ),
        PatchToolCallsMiddleware(),
    ]
    
    # 可选：人工确认
    if config.get("interrupt_on"):
        middleware.append(HumanInTheLoopMiddleware(
            interrupt_on=config["interrupt_on"]
        ))
    
    return middleware
```
