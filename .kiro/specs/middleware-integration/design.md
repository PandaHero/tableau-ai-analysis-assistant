# Design Document: Middleware Integration

## Overview

本设计文档描述了将 LangChain AgentMiddleware 机制集成到 Tableau Assistant 自定义节点函数中的技术方案。核心是实现一个生产级的 `MiddlewareRunner` 类，使已配置的 7 个 middleware 能够在自定义 StateGraph 节点中正确执行。

### 设计目标

1. **完全兼容 LangChain Middleware API** - 支持所有 6 个钩子点
2. **最小侵入性** - 现有节点函数只需添加 middleware 参数即可使用
3. **生产级质量** - 完善的错误处理、日志、类型安全
4. **高性能** - 避免不必要的对象创建和复制

## Architecture

### 工作流节点概览

项目包含 **6 个节点**，其中 4 个需要 Middleware 支持（涉及 LLM 调用）：

| 节点 | 类型 | 需要 Middleware | 说明 |
|------|------|----------------|------|
| **Understanding** | LLM Agent | ✅ | 问题分类 + 语义理解 |
| **FieldMapper** | RAG + LLM | ✅ | 语义字段映射 |
| **QueryBuilder** | 纯代码 | ❌ | VizQL 查询生成（无 LLM） |
| **Execute** | 纯代码 | ❌ | VizQL API 执行（无 LLM） |
| **Insight** | LLM Agent | ✅ | 数据洞察分析 |
| **Replanner** | LLM Agent | ✅ | 重规划决策 |

### 架构图

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                    Workflow Execution                                             │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                   │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐        │
│  │  Understanding  │───▶│   FieldMapper   │───▶│  QueryBuilder   │───▶│    Execute      │        │
│  │   (LLM Agent)   │    │   (RAG + LLM)   │    │   (Pure Code)   │    │   (Pure Code)   │        │
│  │   ✅ Middleware │    │   ✅ Middleware │    │   ❌ No MW      │    │   ❌ No MW      │        │
│  └─────────────────┘    └─────────────────┘    └─────────────────┘    └────────┬────────┘        │
│           ▲                                                                     │                 │
│           │                                                                     ▼                 │
│           │             ┌─────────────────┐    ┌─────────────────┐                               │
│           └─────────────│   Replanner     │◀───│     Insight     │                               │
│        (if replan)      │   (LLM Agent)   │    │   (LLM Agent)   │                               │
│                         │   ✅ Middleware │    │   ✅ Middleware │                               │
│                         └─────────────────┘    └─────────────────┘                               │
│                                  │                                                                │
│                                  ▼ (if done)                                                      │
│                                 END                                                               │
│                                                                                                   │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                   │
│  ┌────────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │                              MiddlewareRunner (共享)                                        │  │
│  │                                                                                             │  │
│  │  所有 LLM 节点共享同一个 Middleware 栈，通过 config 传递                                      │  │
│  │                                                                                             │  │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐                           │  │
│  │  │ TodoList    │ │ Summarize   │ │ ModelRetry  │ │ ToolRetry   │                           │  │
│  │  │ Middleware  │ │ Middleware  │ │ Middleware  │ │ Middleware  │                           │  │
│  │  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘                           │  │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐                                           │  │
│  │  │ Filesystem  │ │ PatchTool   │ │ HumanLoop   │                                           │  │
│  │  │ Middleware  │ │ Middleware  │ │ (Optional)  │                                           │  │
│  │  └─────────────┘ └─────────────┘ └─────────────┘                                           │  │
│  │                                                                                             │  │
│  │  Hook Execution Order:                                                                      │  │
│  │  1. before_agent  ──▶  2. before_model  ──▶  3. wrap_model_call                            │  │
│  │  4. after_model   ──▶  5. wrap_tool_call ──▶  6. after_agent                               │  │
│  └────────────────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                                   │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

## Components and Interfaces

### 1. MiddlewareRunner 类

```python
# tableau_assistant/src/agents/base/middleware_runner.py

from typing import Any, Callable, Awaitable, List, Dict, Optional, TypeVar
from dataclasses import dataclass, field
from langchain.agents.middleware.types import (
    AgentMiddleware,
    AgentState,
    ModelRequest,
    ModelResponse,
)
from langchain.tools.tool_node import ToolCallRequest
from langchain_core.messages import ToolMessage, BaseMessage
from langgraph.types import Command
from langgraph.runtime import Runtime

StateT = TypeVar('StateT', bound=Dict[str, Any])

@dataclass
class MiddlewareRunner:
    """
    生产级 Middleware 运行器，用于在自定义节点函数中执行 LangChain middleware。
    
    支持所有 6 个 AgentMiddleware 钩子：
    - before_agent / abefore_agent
    - before_model / abefore_model
    - wrap_model_call / awrap_model_call
    - after_model / aafter_model
    - wrap_tool_call / awrap_tool_call
    - after_agent / aafter_agent
    
    Example:
        ```python
        from tableau_assistant.src.agents.base.middleware_runner import MiddlewareRunner
        
        runner = MiddlewareRunner(middleware_stack)
        
        # 在节点函数中使用
        async def my_node(state, config):
            runtime = runner.build_runtime(config)
            
            # before_agent
            state = await runner.run_before_agent(state, runtime)
            
            # LLM 调用（带 middleware）
            response = await runner.call_model_with_middleware(
                model=llm,
                messages=messages,
                tools=tools,
                state=state,
                runtime=runtime,
            )
            
            # after_agent
            state = await runner.run_after_agent(state, runtime)
            
            return state
        ```
    """
    
    middleware: List[AgentMiddleware]
    fail_fast: bool = True
    
    # 按钩子类型分类的 middleware（初始化时计算）
    _mw_before_agent: List[AgentMiddleware] = field(default_factory=list, init=False)
    _mw_before_model: List[AgentMiddleware] = field(default_factory=list, init=False)
    _mw_after_model: List[AgentMiddleware] = field(default_factory=list, init=False)
    _mw_after_agent: List[AgentMiddleware] = field(default_factory=list, init=False)
    _mw_wrap_model_call: List[AgentMiddleware] = field(default_factory=list, init=False)
    _mw_wrap_tool_call: List[AgentMiddleware] = field(default_factory=list, init=False)
    
    def __post_init__(self):
        self._validate_middleware()
        self._classify_middleware()
    
    def _validate_middleware(self) -> None:
        """验证 middleware 列表"""
        ...
    
    def _classify_middleware(self) -> None:
        """按钩子类型分类 middleware"""
        ...
    
    # === Runtime 和 Request 构建 ===
    
    def build_runtime(
        self,
        config: Optional[Dict[str, Any]] = None,
        context: Any = None,
        store: Any = None,
        checkpointer: Any = None,
    ) -> Runtime:
        """构建 LangGraph Runtime 对象"""
        ...
    
    def build_model_request(
        self,
        model: BaseChatModel,         # 新增：LLM 实例
        messages: List[BaseMessage],
        tools: List[Any],
        state: Dict[str, Any],
        runtime: Runtime,
        system_prompt: Optional[str] = None,
    ) -> ModelRequest:
        """构建 ModelRequest 对象（使用 LangChain 的 ModelRequest）"""
        ...
    
    # === 钩子执行方法 ===
    
    async def run_before_agent(
        self,
        state: StateT,
        runtime: Runtime,
    ) -> StateT:
        """执行所有 before_agent 钩子"""
        ...
    
    async def run_before_model(
        self,
        state: StateT,
        runtime: Runtime,
    ) -> StateT:
        """执行所有 before_model 钩子"""
        ...
    
    async def run_after_model(
        self,
        state: StateT,
        runtime: Runtime,
    ) -> StateT:
        """执行所有 after_model 钩子"""
        ...
    
    async def run_after_agent(
        self,
        state: StateT,
        runtime: Runtime,
    ) -> StateT:
        """执行所有 after_agent 钩子"""
        ...
    
    # === 包装调用方法 ===
    
    async def wrap_model_call(
        self,
        request: ModelRequest,
        base_handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        """链式调用所有 wrap_model_call 钩子"""
        ...
    
    async def wrap_tool_call(
        self,
        request: ToolCallRequest,
        base_handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]],
    ) -> ToolMessage | Command:
        """链式调用所有 wrap_tool_call 钩子"""
        ...
    
    # === 高级 API ===
    
    async def call_model_with_middleware(
        self,
        model: Any,
        messages: List[BaseMessage],
        tools: List[Any],
        state: Dict[str, Any],
        runtime: Runtime,
        system_prompt: Optional[str] = None,
    ) -> ModelResponse:
        """
        完整的 LLM 调用流程，包含所有 middleware 钩子。
        
        执行顺序：
        1. before_model hooks
        2. wrap_model_call chain
        3. after_model hooks
        """
        ...
    
    async def call_tool_with_middleware(
        self,
        tool: Any,
        tool_call: Dict[str, Any],
        state: Dict[str, Any],
        runtime: Runtime,
    ) -> ToolMessage | Command:
        """
        完整的工具调用流程，包含所有 middleware 钩子。
        """
        ...
```

### 2. 集成到 call_llm_with_tools

```python
# tableau_assistant/src/agents/base/node.py (修改)

async def call_llm_with_tools(
    llm: BaseChatModel,
    messages: List[Dict[str, str]],
    tools: List[Any],
    max_iterations: int = 5,
    streaming: bool = True,
    # 新增参数
    middleware: List[AgentMiddleware] | None = None,
    state: Dict[str, Any] | None = None,
    config: Dict[str, Any] | None = None,
) -> str:
    """
    调用 LLM 并处理工具调用，支持 middleware。
    
    如果提供了 middleware 参数，将创建 MiddlewareRunner 并应用所有钩子。
    """
    if middleware:
        runner = MiddlewareRunner(middleware)
        runtime = runner.build_runtime(config)
        
        # 应用 before_model
        if state:
            state = await runner.run_before_model(state, runtime)
        
        # 构建 ModelRequest 并通过 wrap_model_call 链调用
        ...
    else:
        # 保持原有行为
        ...
```

### 3. 集成到节点函数

```python
# tableau_assistant/src/agents/understanding/node.py (修改示例)

async def understanding_node(
    state: Dict[str, Any],
    config: RunnableConfig | None = None
) -> Dict[str, Any]:
    """Understanding Agent 节点（带 middleware 支持）"""
    
    # 从 config 获取 middleware
    middleware = get_middleware_from_config(config)
    
    if middleware:
        runner = MiddlewareRunner(middleware)
        runtime = runner.build_runtime(config)
        
        # before_agent
        state = await runner.run_before_agent(state, runtime)
    
    # ... 原有逻辑 ...
    
    # 调用 LLM（带 middleware）
    response_content = await call_llm_with_tools(
        llm, messages, tools,
        middleware=middleware,
        state=state,
        config=config,
    )
    
    if middleware:
        # after_agent
        state = await runner.run_after_agent(state, runtime)
    
    return state
```

## Middleware 与钩子的执行流程

### 完整执行流程图

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│                              Agent Node 执行流程（带 Middleware）                                │
├─────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────────────────────┐   │
│  │ PHASE 1: Agent 启动                                                                      │   │
│  │                                                                                          │   │
│  │  before_agent hooks (按顺序执行):                                                        │   │
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐                       │   │
│  │  │ PatchToolCalls   │→│ TodoList         │→│ Filesystem       │→ ... → state updated   │   │
│  │  │ Middleware       │  │ Middleware       │  │ Middleware       │                       │   │
│  │  │ (修复悬空调用)    │  │ (初始化任务队列)  │  │ (初始化文件系统)  │                       │   │
│  │  └──────────────────┘  └──────────────────┘  └──────────────────┘                       │   │
│  └─────────────────────────────────────────────────────────────────────────────────────────┘   │
│                                              ↓                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────────────────────┐   │
│  │ PHASE 2: LLM 调用循环 (可能多次迭代)                                                      │   │
│  │                                                                                          │   │
│  │  ┌─────────────────────────────────────────────────────────────────────────────────┐    │   │
│  │  │ 2.1 before_model hooks (每次 LLM 调用前):                                        │    │   │
│  │  │  ┌──────────────────┐  ┌──────────────────┐                                     │    │   │
│  │  │  │ Summarization    │→│ PatchToolCalls   │→ ... → messages 可能被总结/修复       │    │   │
│  │  │  │ Middleware       │  │ Middleware       │                                     │    │   │
│  │  │  │ (检查token,总结) │  │ (修复消息历史)    │                                     │    │   │
│  │  │  └──────────────────┘  └──────────────────┘                                     │    │   │
│  │  └─────────────────────────────────────────────────────────────────────────────────┘    │   │
│  │                                              ↓                                           │   │
│  │  ┌─────────────────────────────────────────────────────────────────────────────────┐    │   │
│  │  │ 2.2 wrap_model_call chain (洋葱模型):                                            │    │   │
│  │  │                                                                                  │    │   │
│  │  │  ┌─────────────────────────────────────────────────────────────────────────┐    │    │   │
│  │  │  │ ModelRetry (最外层)                                                      │    │    │   │
│  │  │  │  ┌─────────────────────────────────────────────────────────────────┐    │    │    │   │
│  │  │  │  │ Filesystem (修改 system_prompt)                                  │    │    │    │   │
│  │  │  │  │  ┌─────────────────────────────────────────────────────────┐    │    │    │    │   │
│  │  │  │  │  │ PatchToolCalls (修复 messages)                          │    │    │    │    │   │
│  │  │  │  │  │  ┌─────────────────────────────────────────────────┐    │    │    │    │    │   │
│  │  │  │  │  │  │           实际 LLM 调用                          │    │    │    │    │    │   │
│  │  │  │  │  │  │           llm.ainvoke(messages)                 │    │    │    │    │    │   │
│  │  │  │  │  │  └─────────────────────────────────────────────────┘    │    │    │    │    │   │
│  │  │  │  │  │  ← 如果失败，ModelRetry 会重试整个链                      │    │    │    │    │   │
│  │  │  │  │  └─────────────────────────────────────────────────────────┘    │    │    │    │   │
│  │  │  │  └─────────────────────────────────────────────────────────────────┘    │    │    │   │
│  │  │  └─────────────────────────────────────────────────────────────────────────┘    │    │   │
│  │  │                                                                                  │    │   │
│  │  │  执行顺序: ModelRetry.enter → Filesystem.enter → PatchToolCalls.enter →         │    │   │
│  │  │            LLM调用 → PatchToolCalls.exit → Filesystem.exit → ModelRetry.exit    │    │   │
│  │  └─────────────────────────────────────────────────────────────────────────────────┘    │   │
│  │                                              ↓                                           │   │
│  │  ┌─────────────────────────────────────────────────────────────────────────────────┐    │   │
│  │  │ 2.3 after_model hooks (每次 LLM 调用后):                                         │    │   │
│  │  │  目前项目中的 middleware 没有实现 after_model，但接口支持                          │    │   │
│  │  └─────────────────────────────────────────────────────────────────────────────────┘    │   │
│  │                                              ↓                                           │   │
│  │  ┌─────────────────────────────────────────────────────────────────────────────────┐    │   │
│  │  │ 2.4 如果 LLM 返回 tool_calls，执行工具调用:                                       │    │   │
│  │  │                                                                                  │    │   │
│  │  │  for each tool_call:                                                             │    │   │
│  │  │    wrap_tool_call chain (洋葱模型):                                              │    │   │
│  │  │    ┌─────────────────────────────────────────────────────────────────────────┐  │    │   │
│  │  │    │ ToolRetry (最外层)                                                       │  │    │   │
│  │  │    │  ┌─────────────────────────────────────────────────────────────────┐    │  │    │   │
│  │  │    │  │ HumanInTheLoop (检查是否需要人工确认)                             │    │  │    │   │
│  │  │    │  │  ┌─────────────────────────────────────────────────────────┐    │    │  │    │   │
│  │  │    │  │  │ Filesystem (大结果自动转存)                              │    │    │  │    │   │
│  │  │    │  │  │  ┌─────────────────────────────────────────────────┐    │    │    │  │    │   │
│  │  │    │  │  │  │         实际工具调用                             │    │    │    │  │    │   │
│  │  │    │  │  │  │         tool.invoke(args)                       │    │    │    │  │    │   │
│  │  │    │  │  │  └─────────────────────────────────────────────────┘    │    │    │  │    │   │
│  │  │    │  │  └─────────────────────────────────────────────────────────┘    │    │  │    │   │
│  │  │    │  └─────────────────────────────────────────────────────────────────┘    │  │    │   │
│  │  │    └─────────────────────────────────────────────────────────────────────────┘  │    │   │
│  │  │                                                                                  │    │   │
│  │  │  执行顺序: ToolRetry.enter → HumanInTheLoop.enter → Filesystem.enter →          │    │   │
│  │  │            工具调用 → Filesystem.exit → HumanInTheLoop.exit → ToolRetry.exit    │    │   │
│  │  └─────────────────────────────────────────────────────────────────────────────────┘    │   │
│  │                                              ↓                                           │   │
│  │  如果还有 tool_calls，回到 2.1 继续循环                                                  │   │
│  └─────────────────────────────────────────────────────────────────────────────────────────┘   │
│                                              ↓                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────────────────────┐   │
│  │ PHASE 3: Agent 结束                                                                      │   │
│  │                                                                                          │   │
│  │  after_agent hooks (按顺序执行):                                                         │   │
│  │  目前项目中的 middleware 没有实现 after_agent，但接口支持                                 │   │
│  └─────────────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 各 Middleware 的钩子使用情况

| Middleware | before_agent | before_model | wrap_model_call | after_model | wrap_tool_call | after_agent |
|------------|--------------|--------------|-----------------|-------------|----------------|-------------|
| **SummarizationMiddleware** | - | ✅ 检查token数，触发总结 | - | - | - | - |
| **ModelRetryMiddleware** | - | - | ✅ 失败时重试 | - | - | - |
| **ToolRetryMiddleware** | - | - | - | - | ✅ 失败时重试 | - |
| **TodoListMiddleware** | - | - | - | - | - | - |
| **HumanInTheLoopMiddleware** | - | - | - | - | ✅ 暂停等待确认 | - |
| **FilesystemMiddleware** | - | - | ✅ 添加系统提示 | - | ✅ 大结果转存 | - |
| **PatchToolCallsMiddleware** | ✅ 修复悬空调用 | - | ✅ 修复消息 | - | - | - |
| **OutputValidationMiddleware** | - | - | - | ✅ 校验输出格式 | - | ✅ 校验最终状态 |

### OutputValidationMiddleware（新增）

用于在 `after_model` 和 `after_agent` 钩子中校验 LLM 输出，确保输出符合预期的 Pydantic Schema。

```python
# tableau_assistant/src/middleware/output_validation.py

from typing import Type, Optional, Dict, Any
from pydantic import BaseModel, ValidationError
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelResponse, AgentState
from langgraph.runtime import Runtime
import logging
import json

logger = logging.getLogger(__name__)


class OutputValidationMiddleware(AgentMiddleware):
    """
    输出校验中间件
    
    在 after_model 钩子中校验 LLM 输出是否符合预期的 Pydantic Schema。
    在 after_agent 钩子中校验最终状态是否包含必需字段。
    
    Features:
    - JSON 格式校验
    - Pydantic Schema 校验
    - 错误记录和报告
    - 可配置的校验策略（strict/lenient）
    """
    
    def __init__(
        self,
        expected_schema: Optional[Type[BaseModel]] = None,
        required_state_fields: Optional[list[str]] = None,
        strict: bool = False,
    ):
        """
        Args:
            expected_schema: 期望的输出 Pydantic 模型（用于 after_model）
            required_state_fields: 必需的状态字段列表（用于 after_agent）
            strict: 严格模式，校验失败时抛出异常；否则只记录警告
        """
        self.expected_schema = expected_schema
        self.required_state_fields = required_state_fields or []
        self.strict = strict
    
    async def aafter_model(
        self,
        response: ModelResponse,
        request: "ModelRequest",
        state: AgentState,
        runtime: Runtime,
    ) -> Optional[Dict[str, Any]]:
        """
        校验 LLM 输出
        
        检查：
        1. 输出是否为有效 JSON
        2. JSON 是否符合 expected_schema
        """
        if not self.expected_schema:
            return None
        
        if not response.result:
            logger.warning("OutputValidation: Empty response from LLM")
            return self._handle_error("Empty response", state)
        
        content = response.result[0].content
        
        # Step 1: 提取 JSON
        try:
            # 尝试从 markdown code block 中提取
            json_str = self._extract_json(content)
            parsed = json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.warning(f"OutputValidation: Invalid JSON - {e}")
            return self._handle_error(f"Invalid JSON: {e}", state)
        
        # Step 2: Pydantic 校验
        try:
            validated = self.expected_schema.model_validate(parsed)
            logger.debug(f"OutputValidation: Schema validation passed for {self.expected_schema.__name__}")
            return {"validated_output": validated}
        except ValidationError as e:
            logger.warning(f"OutputValidation: Schema validation failed - {e}")
            return self._handle_error(f"Schema validation failed: {e}", state)
    
    async def aafter_agent(
        self,
        state: AgentState,
        runtime: Runtime,
    ) -> Optional[Dict[str, Any]]:
        """
        校验最终状态
        
        检查：
        1. 必需字段是否存在
        2. 必需字段是否为 None
        """
        if not self.required_state_fields:
            return None
        
        missing_fields = []
        for field in self.required_state_fields:
            if field not in state or state.get(field) is None:
                missing_fields.append(field)
        
        if missing_fields:
            error_msg = f"Missing required fields: {missing_fields}"
            logger.warning(f"OutputValidation: {error_msg}")
            return self._handle_error(error_msg, state)
        
        logger.debug("OutputValidation: All required state fields present")
        return None
    
    def _extract_json(self, content: str) -> str:
        """从内容中提取 JSON 字符串"""
        # 尝试从 ```json ... ``` 中提取
        import re
        match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
        if match:
            return match.group(1)
        
        # 尝试找到 { ... } 或 [ ... ]
        start_brace = content.find('{')
        start_bracket = content.find('[')
        
        if start_brace == -1 and start_bracket == -1:
            return content  # 返回原内容，让 json.loads 报错
        
        if start_brace == -1:
            start = start_bracket
        elif start_bracket == -1:
            start = start_brace
        else:
            start = min(start_brace, start_bracket)
        
        # 找到对应的结束符
        if content[start] == '{':
            end = content.rfind('}')
        else:
            end = content.rfind(']')
        
        if end == -1:
            return content[start:]
        
        return content[start:end+1]
    
    def _handle_error(self, error_msg: str, state: AgentState) -> Dict[str, Any]:
        """处理校验错误"""
        if self.strict:
            raise ValueError(f"OutputValidation failed: {error_msg}")
        
        # 非严格模式：记录错误到 state
        return {
            "validation_errors": state.get("validation_errors", []) + [{
                "middleware": "OutputValidationMiddleware",
                "error": error_msg,
            }]
        }
```

#### 使用示例

```python
# 在 workflow factory 中配置
middleware_stack = [
    SummarizationMiddleware(...),
    ModelRetryMiddleware(...),
    OutputValidationMiddleware(
        expected_schema=SemanticQuery,  # Understanding Agent 的输出
        required_state_fields=["semantic_query", "is_analysis_question"],
        strict=False,  # 非严格模式，只记录警告
    ),
    # ... 其他 middleware
]

# 不同节点可以使用不同的 expected_schema
understanding_validation = OutputValidationMiddleware(expected_schema=SemanticQuery)
insight_validation = OutputValidationMiddleware(expected_schema=InsightResult)
replanner_validation = OutputValidationMiddleware(expected_schema=ReplanDecision)
```

### 洋葱模型详解

wrap_model_call 和 wrap_tool_call 使用"洋葱模型"（Onion Model）：

```
请求进入 →  [MW1.enter] → [MW2.enter] → [MW3.enter] → 实际调用 → [MW3.exit] → [MW2.exit] → [MW1.exit] → 响应返回

代码实现：
async def wrap_model_call(request, base_handler):
    # MW1 是最外层
    handler = base_handler
    for mw in reversed(middleware_list):  # 从后往前包装
        prev_handler = handler
        handler = lambda req, h=prev_handler, m=mw: m.awrap_model_call(req, h)
    return await handler(request)
```

### 重试机制示例

```
ModelRetryMiddleware 的 wrap_model_call:

async def awrap_model_call(self, request, handler):
    for attempt in range(self.max_retries + 1):
        try:
            return await handler(request)  # 调用内层 middleware 链
        except Exception as e:
            if attempt == self.max_retries:
                raise
            delay = self.initial_delay * (self.backoff_factor ** attempt)
            await asyncio.sleep(delay + random.uniform(0, delay * 0.1))  # jitter
```

## Data Models

### ModelRequest

注意：我们使用 LangChain 提供的 `ModelRequest` 类，不需要自己定义。

```python
# LangChain 的 ModelRequest 签名（来自 langchain.agents.middleware.types）
@dataclass
class ModelRequest:
    """LLM 调用请求"""
    model: BaseChatModel              # LLM 实例（必需）
    messages: List[AnyMessage]        # 消息列表（必需）
    system_message: SystemMessage | None = None
    system_prompt: str | None = None  # 系统提示
    tool_choice: Any | None = None
    tools: List[BaseTool | dict] | None = None  # 工具列表
    response_format: ResponseFormat | None = None
    state: AgentState | None = None   # 当前状态
    runtime: Runtime | None = None    # 运行时上下文
    model_settings: dict[str, Any] | None = None
    
    def override(self, **kwargs) -> 'ModelRequest':
        """创建修改后的副本"""
        return dataclass.replace(self, **kwargs)
```

### ModelResponse

```python
@dataclass
class ModelResponse:
    """LLM 调用响应"""
    result: List[AIMessage]
    structured_response: Any = None
```

### ToolCallRequest

```python
@dataclass
class ToolCallRequest:
    """工具调用请求"""
    tool_call: Dict[str, Any]  # {"name": "...", "args": {...}, "id": "..."}
    tool: BaseTool
    state: Dict[str, Any]
    runtime: Runtime
    
    def override(self, **kwargs) -> 'ToolCallRequest':
        """创建修改后的副本"""
        return dataclass.replace(self, **kwargs)
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*



### Property Reflection

经过分析，以下属性可以合并或简化：

1. **钩子执行顺序属性** (2.1, 2.3, 3.1, 3.3) - 可以合并为一个通用的"钩子按顺序执行"属性
2. **状态合并属性** (2.2, 2.4, 3.2, 3.4) - 可以合并为一个通用的"状态正确合并"属性
3. **链式调用属性** (4.1, 5.1) - 可以合并为一个通用的"wrap 钩子链式组合"属性
4. **Runtime/Request 构建属性** (6.1-6.4, 7.1-7.7) - 可以合并为"对象构建完整性"属性
5. **错误处理属性** (2.5, 10.3, 10.4) - 可以合并为"错误处理行为"属性

### Correctness Properties

**Property 1: Middleware 验证和分类**
*For any* middleware 列表，MiddlewareRunner 应正确验证每个元素是 AgentMiddleware 实例，并按钩子类型分类到对应的内部列表
**Validates: Requirements 1.1, 1.2, 1.4**

**Property 2: 钩子按顺序执行**
*For any* 实现了特定钩子的 middleware 列表，调用对应的 run_* 方法时，钩子应按 middleware 在列表中的顺序依次执行
**Validates: Requirements 2.1, 2.3, 3.1, 3.3**

**Property 3: 状态更新正确合并**
*For any* 初始状态和钩子返回的状态更新，最终状态应包含所有更新，后面的更新覆盖前面的同名字段
**Validates: Requirements 2.2, 2.4, 3.2, 3.4**

**Property 4: wrap 钩子链式组合**
*For any* 实现了 wrap_model_call 或 wrap_tool_call 的 middleware 列表，钩子应按"洋葱模型"链式组合（第一个 middleware 在最外层）
**Validates: Requirements 4.1, 5.1**

**Property 5: wrap 钩子支持重试**
*For any* wrap 钩子，middleware 应能够多次调用 handler 实现重试逻辑，每次调用都是独立的
**Validates: Requirements 4.2, 5.2**

**Property 6: wrap 钩子支持短路**
*For any* wrap 钩子，middleware 应能够跳过调用 handler 直接返回结果，后续 middleware 不被调用
**Validates: Requirements 4.3**

**Property 7: wrap 钩子支持修改请求/响应**
*For any* wrap 钩子，middleware 对 request 或 response 的修改应正确传递给下一个 middleware 或最终结果
**Validates: Requirements 4.4, 5.3**

**Property 8: 异步钩子优先**
*For any* 异步调用，MiddlewareRunner 应优先使用 async 版本的钩子（abefore_model, awrap_model_call 等）
**Validates: Requirements 4.5, 5.4**

**Property 9: Runtime 和 Request 构建完整性**
*For any* 输入参数，构建的 Runtime 和 ModelRequest 对象应包含所有必需字段且值正确
**Validates: Requirements 6.1, 6.2, 6.3, 6.4, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7**

**Property 10: 错误处理行为**
*For any* 抛出异常的 middleware，当 fail_fast=True 时应立即停止并抛出异常，当 fail_fast=False 时应记录错误并继续执行后续 middleware
**Validates: Requirements 2.5, 10.1, 10.3, 10.4**

**Property 11: call_llm_with_tools 集成**
*For any* 带 middleware 参数的 call_llm_with_tools 调用，应按正确顺序执行所有钩子（before_model → wrap_model_call → [tool calls with wrap_tool_call] → after_model）
**Validates: Requirements 8.1, 8.3, 8.4**

**Property 12: 向后兼容**
*For any* 不带 middleware 参数的 call_llm_with_tools 调用，行为应与修改前完全一致
**Validates: Requirements 8.2**

## 对话历史管理

### 问题背景

当前系统的每个节点函数只使用当前问题，不包含历史对话。这导致：
1. LLM 无法理解上下文（如"跟去年比"中的"去年"需要参考之前的问题）
2. SummarizationMiddleware 无法工作（没有 messages 可以总结）

### 解决方案：结构化摘要消息（方案 C）

历史消息采用**结构化摘要格式**，包含关键信息但不过于冗长：

#### 1. 消息格式设计

```python
# 每轮对话结束后，Insight Agent 生成结构化摘要消息
AIMessage(content=f"""
【分析完成】
原始问题：{question}
分析维度：{', '.join(dimensions)}
分析指标：{', '.join(measures)}
时间范围：{time_range}
查询结果摘要：{query_result_summary}

回答：{insight_summary}
""")
```

**示例：**

```
【分析完成】
原始问题：今年的销售额是多少？
分析维度：无
分析指标：销售额
时间范围：2024年
查询结果摘要：2024年销售额 = 150万元

回答：2024年销售额为150万元。
```

#### 2. 在 VizQLState 中添加 messages 字段

```python
from langchain_core.messages import BaseMessage

class VizQLState(TypedDict):
    # ... 现有字段 ...
    
    # 对话历史（LangChain 消息列表，自动累积）
    messages: Annotated[List[BaseMessage], operator.add]
    
    # 已回答的问题列表（用于 Replanner 去重）
    answered_questions: Annotated[List[str], operator.add]
```

#### 3. 节点函数使用历史消息

```python
async def insight_node(state, config):
    # ... 分析逻辑 ...
    
    # 生成结构化摘要消息
    summary_message = AIMessage(content=f"""
【分析完成】
原始问题：{state.get("question")}
分析维度：{', '.join(d.name for d in semantic_query.dimensions)}
分析指标：{', '.join(m.name for m in semantic_query.measures)}
时间范围：{time_range}
查询结果摘要：{format_query_result(query_result)}

回答：{insight_result.summary}
""")
    
    return {
        "messages": [
            HumanMessage(content=state.get("question")),
            summary_message,
        ],
        "answered_questions": [state.get("question")],  # 记录已回答的问题
        "insights": insights,
        ...
    }
```

### Replanner 去重逻辑（LLM Prompt 约束方案）

Replanner 生成探索问题时，通过 **Prompt 约束** 让 LLM 自己避免生成重复问题，而不是用代码做文本相似度计算。

#### 设计原理

1. **LLM 能看到完整上下文**：`messages` 包含所有历史问答，`answered_questions` 列出已回答问题
2. **LLM 理解语义相似**：LLM 能理解 "各省份销售额" ≈ "按省份看销售额"
3. **更简单更智能**：不需要写文本相似度代码，LLM 自己判断

#### Replanner Prompt 设计（遵循 PROMPT_AND_MODEL_GUIDE.md 规范）

```python
# tableau_assistant/src/agents/replanner/prompt.py

class ReplannerPrompt(VizQLPrompt):
    """Replanner Agent Prompt - 决定是否继续探索分析"""
    
    def get_role(self) -> str:
        return """Data analysis replanning expert who decides whether to continue exploration.

Expertise:
- Insight evaluation and prioritization
- Dimension hierarchy navigation
- Exploration question generation
- Duplicate detection and avoidance"""
    
    def get_task(self) -> str:
        return """Analyze current insights and decide whether to continue exploration.

Process: Review insights → Check answered questions → Generate NEW questions → Decide replan"""
    
    def get_specific_domain_knowledge(self) -> str:
        return """**Think step by step:**

Step 1: Review current insights
- What patterns or anomalies were found?
- Which findings are worth exploring further?

Step 2: Check what has been answered (CRITICAL for deduplication)
- Review the answered_questions list
- Review the current_dimensions list
- DO NOT generate questions that overlap with these

Step 3: Generate exploration questions
- Consider dimension hierarchy for drill-down
- Prioritize high-value exploration directions
- MUST be different from answered questions

Step 4: Decide whether to continue
- Are there valuable unexplored directions?
- Has the analysis reached sufficient depth?"""
    
    def get_constraints(self) -> str:
        return """MUST: check answered_questions before generating, avoid semantic duplicates, respect dimension hierarchy
MUST NOT: generate questions similar to answered ones, drill into already-analyzed dimensions, exceed max replan rounds"""
    
    def get_user_template(self) -> str:
        return """Current analysis context:

## Conversation History
{messages}

## Already Answered Questions (DO NOT REPEAT)
{answered_questions}

## Already Analyzed Dimensions (DO NOT DRILL AGAIN)
{current_dimensions}

## Current Insights
{insights}

## Dimension Hierarchy (for drill-down reference)
{dimension_hierarchy}

## Task
Based on the above, decide whether to continue exploration and generate NEW questions."""
    
    def get_output_model(self) -> Type[BaseModel]:
        return ReplanDecision
```

#### ReplanDecision 数据模型（遵循 XML 格式规范）

```python
# tableau_assistant/src/models/replanner/replan_decision.py

class ReplanDecision(BaseModel):
    """
    Replanner decision output.
    
    <what>Decision on whether to continue exploration and what questions to explore next</what>
    
    <decision_tree>
    START
      │
      ├─► Review answered_questions and current_dimensions
      │   │
      │   └─► For each potential question:
      │       ├─ Similar to answered_questions? → SKIP
      │       ├─ Dimension in current_dimensions? → SKIP
      │       └─ New and valuable? → INCLUDE
      │
      ├─► exploration_questions = filtered list
      │
      └─► should_replan = len(exploration_questions) > 0 AND has_value
      
    END
    </decision_tree>
    
    <examples>
    Example 1 - Continue exploration:
    Input: answered=["今年各地区销售额"], current_dims=["地区"], insights=[华东最高]
    Output: {
        "should_replan": true,
        "exploration_questions": ["按省份下钻华东地区", "按产品类别分析"],
        "next_question": "按省份下钻华东地区",
        "reason": "华东地区销售额最高，值得深入分析省份分布"
    }
    
    Example 2 - Stop (duplicate detected):
    Input: answered=["各省份销售额", "按省份下钻华东"], current_dims=["地区", "省份"]
    Output: {
        "should_replan": false,
        "exploration_questions": [],
        "reason": "省份维度已分析，无新的探索方向"
    }
    </examples>
    
    <anti_patterns>
    ❌ Generating "按省份分析" when "各省份销售额" already answered
    ❌ Generating "按地区下钻" when "地区" in current_dimensions
    ❌ Generating semantically similar questions (e.g., "各省份销售额" vs "按省份看销售额")
    </anti_patterns>
    """
    model_config = ConfigDict(extra="forbid")
    
    should_replan: bool = Field(
        description="""Whether to continue exploration.

<what>Decision to continue or stop exploration</what>
<when>Always required</when>
<how>True if there are valuable unexplored directions, False otherwise</how>

<decision_rule>
IF exploration_questions is empty THEN false
IF all valuable directions already explored THEN false
IF max_replan_rounds reached THEN false
ELSE true
</decision_rule>"""
    )
    
    exploration_questions: List[str] = Field(
        default_factory=list,
        description="""List of NEW exploration questions.

<what>Questions for further exploration</what>
<when>When should_replan=true</when>
<how>List of question strings, each must be NEW (not in answered_questions)</how>

<dependency>
- field: answered_questions (from state)
- condition: each question must NOT be similar to any answered question
- reason: Avoid redundant analysis
</dependency>

<anti_patterns>
❌ Including questions similar to answered_questions
❌ Including questions targeting dimensions in current_dimensions
❌ Including vague or non-actionable questions
</anti_patterns>"""
    )
    
    next_question: Optional[str] = Field(
        default=None,
        description="""The next question to analyze.

<what>Selected question from exploration_questions</what>
<when>When should_replan=true</when>
<how>Pick the highest priority question from exploration_questions</how>

<dependency>
- field: should_replan
- condition: should_replan == true
- reason: Only needed when continuing exploration
</dependency>"""
    )
    
    reason: str = Field(
        description="""Explanation for the decision.

<what>Why this decision was made</what>
<when>Always required</when>
<how>Brief explanation of the reasoning</how>"""
    )
```

#### 简化后的 Replanner 节点

```python
async def replanner_node(state, config):
    """Replanner 节点 - LLM 自己处理去重"""
    
    # 准备上下文（LLM 会看到这些信息并自己避免重复）
    messages = state.get("messages", [])
    answered_questions = state.get("answered_questions", [])
    current_dimensions = state.get("current_dimensions", [])
    insights = state.get("insights", [])
    dimension_hierarchy = state.get("dimension_hierarchy", {})
    
    # 调用 LLM（Prompt 中已包含去重约束）
    prompt = REPLANNER_PROMPT
    llm = get_llm(agent_name="replanner")
    
    response = await call_llm_with_tools(
        llm,
        prompt.format_messages(
            messages=format_messages(messages),
            answered_questions=answered_questions,
            current_dimensions=current_dimensions,
            insights=format_insights(insights),
            dimension_hierarchy=dimension_hierarchy,
        ),
        tools=[],
        middleware=get_middleware_from_config(config),
        state=state,
        config=config,
    )
    
    # 解析 LLM 输出（LLM 已经做了去重）
    replan_decision = parse_json_response(response, ReplanDecision)
    
    return {
        "replan_decision": replan_decision,
        "replanner_complete": True,
    }
```

#### 3. 多轮对话执行流程（含去重）

```
第一轮: "今年各地区销售额是多少？"
┌─────────────────────────────────────────────────────────────────────────────┐
│ messages = []                                                                │
│ answered_questions = []                                                      │
│ current_dimensions = []                                                      │
│                                                                              │
│ → Understanding → FieldMapper → QueryBuilder → Execute → Insight             │
│                                                                              │
│ Insight 输出:                                                                 │
│   messages = [Human("今年各地区销售额..."), AI("【分析完成】...华东150万...")]  │
│   answered_questions = ["今年各地区销售额是多少？"]                            │
│   current_dimensions = ["地区"]                                               │
│                                                                              │
│ → Replanner                                                                   │
│   生成探索问题: ["按省份下钻华东地区", "按产品类别分析", "按月份趋势"]           │
│   去重检查: 全部通过（没有重复）                                               │
│   should_replan = True                                                        │
│   下一个问题: "按省份下钻华东地区"                                             │
└─────────────────────────────────────────────────────────────────────────────┘

第二轮: "按省份下钻华东地区"（Replanner 生成）
┌─────────────────────────────────────────────────────────────────────────────┐
│ messages = [之前的对话...]                                                    │
│ answered_questions = ["今年各地区销售额是多少？"]                              │
│ current_dimensions = ["地区"]                                                 │
│                                                                              │
│ → Understanding (看到历史上下文，知道是下钻华东)                               │
│ → ... → Insight                                                               │
│                                                                              │
│ Insight 输出:                                                                 │
│   answered_questions += ["按省份下钻华东地区"]                                 │
│   current_dimensions += ["省份"]  # 新增已分析维度                            │
│                                                                              │
│ → Replanner                                                                   │
│   生成探索问题: ["按省份下钻华东地区", "按产品类别分析", "按城市下钻"]          │
│   去重检查:                                                                   │
│     - "按省份下钻华东地区" → 已在 answered_questions 中 → 过滤                 │
│     - "按产品类别分析" → 通过                                                  │
│     - "按城市下钻" → 通过                                                      │
│   filtered_questions = ["按产品类别分析", "按城市下钻"]                        │
│   should_replan = True                                                        │
└─────────────────────────────────────────────────────────────────────────────┘

第三轮: "按产品类别分析"
┌─────────────────────────────────────────────────────────────────────────────┐
│ current_dimensions = ["地区", "省份"]                                         │
│                                                                              │
│ → ... → Replanner                                                             │
│   生成探索问题: ["按省份下钻", "按产品子类别下钻"]                              │
│   去重检查:                                                                   │
│     - "按省份下钻" → "省份" 已在 current_dimensions 中 → 过滤                  │
│     - "按产品子类别下钻" → 通过                                                │
│   ...                                                                         │
└─────────────────────────────────────────────────────────────────────────────┘
```
│   - "今年" = 2024年（从上下文推断）                                            │
│   - "去年" = 2023年                                                           │
│   - 已知 2024 年数据，只需查询 2023 年                                         │
│                                                                              │
│   返回: messages = [Human("跟去年比..."), AI("需要查询2023年数据...")]         │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 设计补充：潜在问题的解决方案

### 问题 A & D：消息来源标记

为了区分用户问题和系统生成的探索问题，在消息中添加 metadata 标记来源：

```python
from langchain_core.messages import HumanMessage, AIMessage

# 用户原始问题（workflow 入口处标记）
HumanMessage(
    content="今年各地区销售额是多少？",
    additional_kwargs={"source": "user"}
)

# Replanner 生成的探索问题
HumanMessage(
    content="按省份下钻华东地区",
    additional_kwargs={
        "source": "replanner",
        "parent_question": "今年各地区销售额是多少？"
    }
)

# Insight 生成的回答
AIMessage(
    content="【分析完成】...",
    additional_kwargs={"source": "insight"}
)
```

**消息来源类型**：
- `user`：用户输入的问题
- `replanner`：Replanner 生成的探索问题
- `insight`：Insight Agent 生成的分析结果

### 问题 E：answered_questions 长度限制

为避免 answered_questions 过长导致 Replanner Prompt 超过 token 限制，限制其长度：

```python
MAX_ANSWERED_QUESTIONS = 20

def trim_answered_questions(questions: List[str]) -> List[str]:
    """保留最近 N 个问题，避免列表过长"""
    if len(questions) > MAX_ANSWERED_QUESTIONS:
        return questions[-MAX_ANSWERED_QUESTIONS:]
    return questions
```

在 Insight 节点返回时调用此函数。

### 问题 F：校验失败触发重试

OutputValidationMiddleware 校验失败时，默认抛出异常触发 ModelRetryMiddleware 重试：

```python
class OutputValidationMiddleware(AgentMiddleware):
    def __init__(
        self,
        expected_schema: Optional[Type[BaseModel]] = None,
        required_state_fields: Optional[list[str]] = None,
        strict: bool = False,
        retry_on_failure: bool = True,  # 新增：校验失败时是否触发重试
    ):
        self.retry_on_failure = retry_on_failure
        # ...
    
    async def aafter_model(self, response, request, state, runtime):
        # 校验失败时
        if validation_failed:
            if self.retry_on_failure:
                raise OutputValidationError(f"Validation failed: {error_msg}")
            else:
                return self._handle_error(error_msg, state)
```

### 问题 G：串行执行说明

当前设计只支持**串行执行**探索问题：

```
Replanner 生成: ["问题A", "问题B", "问题C"]
执行顺序:
  第 N 轮: 执行 "问题A"
  第 N+1 轮: 执行 "问题B"
  第 N+2 轮: 执行 "问题C"
```

**原因**：
1. 避免并行执行时的状态冲突
2. 简化实现复杂度
3. 保证分析结果的顺序性

**未来优化**：可以考虑支持并行执行，但需要：
- 验证 LangGraph 的并行状态合并机制
- 处理并行执行时的 messages 合并顺序
- 处理并行执行时的 answered_questions 去重

## Error Handling

### 错误处理策略

1. **fail_fast=True（默认）**
   - 第一个 middleware 抛出异常时立即停止
   - 异常向上传播，由调用方处理
   - 适用于开发和调试阶段

2. **fail_fast=False（优雅降级）**
   - 记录错误但继续执行后续 middleware
   - 收集所有错误，最后返回部分结果
   - 适用于生产环境，确保服务可用性

### 异常类型

```python
class MiddlewareError(Exception):
    """Middleware 执行错误基类"""
    def __init__(self, middleware_name: str, hook_name: str, original_error: Exception):
        self.middleware_name = middleware_name
        self.hook_name = hook_name
        self.original_error = original_error
        super().__init__(f"Middleware '{middleware_name}' failed in hook '{hook_name}': {original_error}")

class MiddlewareValidationError(MiddlewareError):
    """Middleware 验证错误"""
    pass

class MiddlewareChainError(MiddlewareError):
    """Middleware 链式调用错误"""
    pass
```

## Testing Strategy

### 单元测试

使用 pytest 和 pytest-asyncio 进行单元测试。

### 属性测试

使用 Hypothesis 进行属性测试，验证 correctness properties。

```python
# 测试框架配置
import pytest
from hypothesis import given, strategies as st, settings

# 每个属性测试运行 100 次
@settings(max_examples=100)

# 示例：Property 2 - 钩子按顺序执行
@given(st.lists(st.sampled_from([mock_mw_1, mock_mw_2, mock_mw_3]), min_size=1, max_size=5))
async def test_hooks_execute_in_order(middleware_list):
    """
    **Feature: middleware-integration, Property 2: 钩子按顺序执行**
    **Validates: Requirements 2.1, 2.3, 3.1, 3.3**
    """
    runner = MiddlewareRunner(middleware_list)
    execution_order = []
    
    # 执行钩子
    await runner.run_before_agent(state, runtime)
    
    # 验证执行顺序
    assert execution_order == [mw.name for mw in middleware_list if has_before_agent(mw)]
```

### 集成测试

测试 MiddlewareRunner 与实际 LangChain middleware 的集成：

```python
async def test_summarization_middleware_integration():
    """测试 SummarizationMiddleware 集成"""
    middleware = [SummarizationMiddleware(model=mock_model, trigger=("tokens", 100))]
    runner = MiddlewareRunner(middleware)
    
    # 创建超过 token 阈值的消息
    state = {"messages": [HumanMessage(content="x" * 1000)]}
    
    # 执行 before_model
    new_state = await runner.run_before_model(state, runtime)
    
    # 验证消息被总结
    assert len(new_state["messages"]) < len(state["messages"])
```
