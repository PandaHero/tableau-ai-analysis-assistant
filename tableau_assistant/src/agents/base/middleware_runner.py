"""
MiddlewareRunner - 生产级 Middleware 运行器

用于在自定义 StateGraph 节点函数中执行 LangChain AgentMiddleware。

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

Requirements:
- R1: MiddlewareRunner 核心实现
- R2-R5: 钩子执行
- R6-R7: Runtime 和 Request 构建
- R10: 错误处理和日志
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
from dataclasses import dataclass, field
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    List,
    Optional,
    TypeVar,
    Union,
)

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)

StateT = TypeVar('StateT', bound=Dict[str, Any])


# ═══════════════════════════════════════════════════════════════════════════
# 异常类
# ═══════════════════════════════════════════════════════════════════════════

class MiddlewareError(Exception):
    """Middleware 执行错误基类"""
    
    def __init__(
        self,
        middleware_name: str,
        hook_name: str,
        original_error: Exception,
    ):
        self.middleware_name = middleware_name
        self.hook_name = hook_name
        self.original_error = original_error
        super().__init__(
            f"Middleware '{middleware_name}' failed in hook '{hook_name}': {original_error}"
        )


class MiddlewareValidationError(MiddlewareError):
    """Middleware 验证错误"""
    pass


class MiddlewareChainError(MiddlewareError):
    """Middleware 链式调用错误"""
    pass


# ═══════════════════════════════════════════════════════════════════════════
# 类型定义（兼容 LangChain）
# ═══════════════════════════════════════════════════════════════════════════

# 尝试从 LangChain 导入类型，如果不存在则定义本地版本
try:
    from langchain.agents.middleware.types import (
        AgentMiddleware,
        ModelRequest,
        ModelResponse,
    )
    from langchain.tools.tool_node import ToolCallRequest
    from langgraph.types import Command
    
    LANGCHAIN_MIDDLEWARE_AVAILABLE = True
    
except ImportError:
    # LangChain middleware 模块不可用，定义本地类型
    LANGCHAIN_MIDDLEWARE_AVAILABLE = False
    
    class AgentMiddleware:
        """AgentMiddleware 基类（本地定义）"""
        pass
    
    @dataclass
    class ModelRequest:
        """LLM 调用请求"""
        model: BaseChatModel
        messages: List[BaseMessage]
        system_message: Optional[BaseMessage] = None
        system_prompt: Optional[str] = None
        tool_choice: Any = None
        tools: Optional[List[Any]] = None
        response_format: Any = None
        state: Optional[Dict[str, Any]] = None
        runtime: Any = None
        model_settings: Optional[Dict[str, Any]] = None
        
        def override(self, **kwargs) -> 'ModelRequest':
            """创建修改后的副本"""
            from dataclasses import replace
            return replace(self, **kwargs)
    
    @dataclass
    class ModelResponse:
        """LLM 调用响应"""
        result: List[AIMessage]
        structured_response: Any = None
    
    @dataclass
    class ToolCallRequest:
        """工具调用请求"""
        tool_call: Dict[str, Any]
        tool: BaseTool
        state: Dict[str, Any]
        runtime: Any
        
        def override(self, **kwargs) -> 'ToolCallRequest':
            """创建修改后的副本"""
            from dataclasses import replace
            return replace(self, **kwargs)
    
    class Command:
        """LangGraph Command"""
        pass


# Runtime 类型 - 始终使用本地定义以确保兼容性
# LangGraph 的 Runtime 签名是: (*, context, store, stream_writer, previous)
# 我们需要额外的 config 字段来传递配置
@dataclass
class Runtime:
    """
    LangGraph Runtime 兼容类
    
    LangGraph 原生 Runtime 签名: (*, context, store, stream_writer, previous)
    我们扩展它以支持 config 字段用于传递 RunnableConfig
    """
    context: Any = None
    store: Any = None
    config: Dict[str, Any] = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════════════
# MiddlewareRunner
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class MiddlewareRunner:
    """
    生产级 Middleware 运行器
    
    用于在自定义节点函数中执行 LangChain middleware。
    支持所有 6 个 AgentMiddleware 钩子。
    
    Attributes:
        middleware: Middleware 列表
        fail_fast: 是否在第一个错误时停止（默认 True）
    """
    
    middleware: List[Any]  # List[AgentMiddleware]
    fail_fast: bool = True
    
    # 按钩子类型分类的 middleware（初始化时计算）
    _mw_before_agent: List[Any] = field(default_factory=list, init=False)
    _mw_before_model: List[Any] = field(default_factory=list, init=False)
    _mw_after_model: List[Any] = field(default_factory=list, init=False)
    _mw_after_agent: List[Any] = field(default_factory=list, init=False)
    _mw_wrap_model_call: List[Any] = field(default_factory=list, init=False)
    _mw_wrap_tool_call: List[Any] = field(default_factory=list, init=False)
    
    def __post_init__(self):
        """初始化后验证和分类 middleware"""
        self._validate_middleware()
        self._classify_middleware()
    
    # ═══════════════════════════════════════════════════════════════════════
    # 验证和分类
    # ═══════════════════════════════════════════════════════════════════════
    
    def _validate_middleware(self) -> None:
        """
        验证 middleware 列表
        
        Raises:
            ValueError: 如果 middleware 无效或有重复
        """
        if not self.middleware:
            return
        
        # 检查重复实例（使用 id 比较）
        seen_ids = set()
        for mw in self.middleware:
            mw_id = id(mw)
            if mw_id in seen_ids:
                raise ValueError(
                    f"Duplicate middleware instance detected: {type(mw).__name__}. "
                    "Please remove duplicate instances from the middleware list."
                )
            seen_ids.add(mw_id)
        
        # 验证类型（如果 LangChain middleware 可用）
        if LANGCHAIN_MIDDLEWARE_AVAILABLE:
            for mw in self.middleware:
                if not isinstance(mw, AgentMiddleware):
                    raise ValueError(
                        f"Invalid middleware type: {type(mw).__name__}. "
                        f"Expected AgentMiddleware instance."
                    )
    
    def _classify_middleware(self) -> None:
        """按钩子类型分类 middleware"""
        self._mw_before_agent = []
        self._mw_before_model = []
        self._mw_after_model = []
        self._mw_after_agent = []
        self._mw_wrap_model_call = []
        self._mw_wrap_tool_call = []
        
        for mw in self.middleware:
            # before_agent / abefore_agent
            if self._has_hook(mw, 'before_agent', 'abefore_agent'):
                self._mw_before_agent.append(mw)
            
            # before_model / abefore_model
            if self._has_hook(mw, 'before_model', 'abefore_model'):
                self._mw_before_model.append(mw)
            
            # after_model / aafter_model
            if self._has_hook(mw, 'after_model', 'aafter_model'):
                self._mw_after_model.append(mw)
            
            # after_agent / aafter_agent
            if self._has_hook(mw, 'after_agent', 'aafter_agent'):
                self._mw_after_agent.append(mw)
            
            # wrap_model_call / awrap_model_call
            if self._has_hook(mw, 'wrap_model_call', 'awrap_model_call'):
                self._mw_wrap_model_call.append(mw)
            
            # wrap_tool_call / awrap_tool_call
            if self._has_hook(mw, 'wrap_tool_call', 'awrap_tool_call'):
                self._mw_wrap_tool_call.append(mw)
    
    def _has_hook(self, mw: Any, sync_name: str, async_name: str) -> bool:
        """
        检查 middleware 是否实现了指定的钩子
        
        通过检查方法是否被覆盖（不是基类的默认实现）来判断
        """
        # 检查异步版本
        async_method = getattr(mw, async_name, None)
        if async_method is not None:
            # 检查是否是覆盖的方法（不是基类的）
            if self._is_overridden(mw, async_name):
                return True
        
        # 检查同步版本
        sync_method = getattr(mw, sync_name, None)
        if sync_method is not None:
            if self._is_overridden(mw, sync_name):
                return True
        
        return False
    
    def _is_overridden(self, obj: Any, method_name: str) -> bool:
        """检查方法是否被子类覆盖"""
        method = getattr(obj, method_name, None)
        if method is None:
            return False
        
        # 获取方法所属的类
        if hasattr(method, '__func__'):
            method_class = method.__func__.__qualname__.rsplit('.', 1)[0]
        else:
            method_class = method.__qualname__.rsplit('.', 1)[0]
        
        # 如果方法定义在 AgentMiddleware 基类中，则未被覆盖
        obj_class_name = type(obj).__name__
        return method_class == obj_class_name
    
    @property
    def names(self) -> List[str]:
        """返回所有已注册 middleware 的名称列表"""
        return [type(mw).__name__ for mw in self.middleware]
    
    def get_merged_state_schema(self) -> Dict[str, Any]:
        """
        收集并合并所有 middleware 的 state_schema
        
        遍历所有 middleware，收集它们定义的 state_schema，
        并合并为统一的 schema 字典。
        
        Returns:
            合并后的 state schema 字典，格式为:
            {
                "middleware_name": {
                    "schema": TypedDict 类,
                    "fields": ["field1", "field2", ...],
                }
            }
        
        Example:
            >>> runner = MiddlewareRunner([FilesystemMiddleware()])
            >>> schemas = runner.get_merged_state_schema()
            >>> print(schemas)
            {
                "FilesystemMiddleware": {
                    "schema": FilesystemState,
                    "fields": ["files"],
                }
            }
        
        **Validates: Requirements 11.1, 11.2**
        """
        merged_schemas: Dict[str, Any] = {}
        
        for mw in self.middleware:
            mw_name = type(mw).__name__
            
            # 检查 middleware 是否定义了 state_schema
            state_schema = getattr(mw, 'state_schema', None)
            
            if state_schema is not None:
                # 提取 schema 的字段信息
                fields = []
                
                # TypedDict 的字段存储在 __annotations__ 中
                if hasattr(state_schema, '__annotations__'):
                    fields = list(state_schema.__annotations__.keys())
                
                merged_schemas[mw_name] = {
                    "schema": state_schema,
                    "fields": fields,
                }
                
                logger.debug(
                    f"Collected state_schema from '{mw_name}': "
                    f"fields={fields}"
                )
        
        return merged_schemas
    
    def get_all_state_fields(self) -> List[str]:
        """
        获取所有 middleware 定义的状态字段名列表
        
        Returns:
            所有 middleware 状态字段的扁平列表（去重）
        
        **Validates: Requirements 11.1**
        """
        all_fields = set()
        
        for mw in self.middleware:
            state_schema = getattr(mw, 'state_schema', None)
            if state_schema is not None and hasattr(state_schema, '__annotations__'):
                all_fields.update(state_schema.__annotations__.keys())
        
        return list(all_fields)
    
    def merge_middleware_state_updates(
        self,
        current_state: StateT,
        updates: Dict[str, Any],
    ) -> StateT:
        """
        合并 middleware 状态更新，正确处理带 reducer 的字段
        
        对于普通字段，直接覆盖；
        对于带 Annotated[..., reducer] 的字段（如 FilesystemMiddleware 的 files），
        使用对应的 reducer 函数进行合并。
        
        Args:
            current_state: 当前状态
            updates: 状态更新字典
        
        Returns:
            合并后的状态
        
        **Validates: Requirements 11.2, 11.3**
        """
        from typing import get_type_hints, get_origin, get_args
        
        result = dict(current_state)
        
        for key, value in updates.items():
            if key not in result:
                # 新字段，直接添加
                result[key] = value
                continue
            
            # 检查是否有 reducer
            reducer = self._get_field_reducer(key)
            
            if reducer is not None:
                # 使用 reducer 合并
                try:
                    result[key] = reducer(result.get(key), value)
                    logger.debug(f"Merged field '{key}' using reducer")
                except Exception as e:
                    logger.warning(
                        f"Failed to use reducer for field '{key}': {e}. "
                        "Falling back to direct assignment."
                    )
                    result[key] = value
            else:
                # 直接覆盖
                result[key] = value
        
        return result
    
    def _get_field_reducer(self, field_name: str) -> Optional[Callable]:
        """
        获取字段的 reducer 函数
        
        遍历所有 middleware 的 state_schema，查找字段的 Annotated 类型，
        提取其中的 reducer 函数。
        
        Args:
            field_name: 字段名
        
        Returns:
            reducer 函数，如果没有则返回 None
        """
        from typing import get_type_hints, get_origin, get_args, Annotated
        
        for mw in self.middleware:
            state_schema = getattr(mw, 'state_schema', None)
            if state_schema is None:
                continue
            
            # 获取类型提示
            try:
                hints = get_type_hints(state_schema, include_extras=True)
            except Exception:
                continue
            
            if field_name not in hints:
                continue
            
            field_type = hints[field_name]
            
            # 检查是否是 Annotated 类型
            if get_origin(field_type) is Annotated:
                args = get_args(field_type)
                # Annotated[Type, metadata1, metadata2, ...]
                # reducer 通常是第二个参数（metadata）
                for arg in args[1:]:
                    if callable(arg):
                        return arg
        
        return None

    
    # ═══════════════════════════════════════════════════════════════════════
    # Runtime 和 Request 构建
    # ═══════════════════════════════════════════════════════════════════════
    
    def build_runtime(
        self,
        config: Optional[Dict[str, Any]] = None,
        context: Any = None,
        store: Any = None,
    ) -> Runtime:
        """
        构建 Runtime 对象
        
        Args:
            config: LangGraph RunnableConfig
            context: 用户自定义上下文
            store: 跨线程持久化存储
        
        Returns:
            Runtime 对象
        """
        return Runtime(
            context=context,
            store=store,
            config=config or {},
        )
    
    def build_model_request(
        self,
        model: BaseChatModel,
        messages: List[BaseMessage],
        tools: Optional[List[Any]] = None,
        state: Optional[Dict[str, Any]] = None,
        runtime: Optional[Runtime] = None,
        system_prompt: Optional[str] = None,
    ) -> ModelRequest:
        """
        构建 ModelRequest 对象
        
        Args:
            model: LLM 实例
            messages: 消息列表
            tools: 可用工具列表
            state: 当前 Agent 状态
            runtime: 运行时上下文
            system_prompt: 系统提示
        
        Returns:
            ModelRequest 对象
        """
        return ModelRequest(
            model=model,
            messages=messages,
            tools=tools,
            state=state,
            runtime=runtime,
            system_prompt=system_prompt,
        )
    
    def build_model_response(
        self,
        result: List[AIMessage],
        structured_response: Any = None,
    ) -> ModelResponse:
        """
        构建 ModelResponse 对象
        
        Args:
            result: AIMessage 列表
            structured_response: 可选的结构化响应
        
        Returns:
            ModelResponse 对象
        """
        return ModelResponse(
            result=result,
            structured_response=structured_response,
        )
    
    def build_tool_call_request(
        self,
        tool_call: Dict[str, Any],
        tool: BaseTool,
        state: Dict[str, Any],
        runtime: Runtime,
    ) -> ToolCallRequest:
        """
        构建 ToolCallRequest 对象
        
        Args:
            tool_call: 工具调用信息 {"name": "...", "args": {...}, "id": "..."}
            tool: 工具实例
            state: 当前状态
            runtime: 运行时上下文
        
        Returns:
            ToolCallRequest 对象
        """
        return ToolCallRequest(
            tool_call=tool_call,
            tool=tool,
            state=state,
            runtime=runtime,
        )
    
    # ═══════════════════════════════════════════════════════════════════════
    # 钩子执行方法
    # ═══════════════════════════════════════════════════════════════════════
    
    async def run_before_agent(
        self,
        state: StateT,
        runtime: Runtime,
    ) -> StateT:
        """
        执行所有 before_agent 钩子
        
        Args:
            state: 当前状态
            runtime: 运行时上下文
        
        Returns:
            更新后的状态
        """
        return await self._run_hooks(
            self._mw_before_agent,
            'before_agent',
            'abefore_agent',
            state,
            runtime=runtime,
        )
    
    async def run_after_agent(
        self,
        state: StateT,
        runtime: Runtime,
    ) -> StateT:
        """
        执行所有 after_agent 钩子
        
        Args:
            state: 当前状态
            runtime: 运行时上下文
        
        Returns:
            更新后的状态
        """
        return await self._run_hooks(
            self._mw_after_agent,
            'after_agent',
            'aafter_agent',
            state,
            runtime=runtime,
        )
    
    async def run_before_model(
        self,
        state: StateT,
        runtime: Runtime,
        request: Optional[ModelRequest] = None,
    ) -> StateT:
        """
        执行所有 before_model 钩子
        
        Args:
            state: 当前状态
            runtime: 运行时上下文
            request: 可选的 ModelRequest
        
        Returns:
            更新后的状态
        """
        return await self._run_hooks(
            self._mw_before_model,
            'before_model',
            'abefore_model',
            state,
            runtime=runtime,
            request=request,
        )
    
    async def run_after_model(
        self,
        state: StateT,
        runtime: Runtime,
        response: Optional[ModelResponse] = None,
        request: Optional[ModelRequest] = None,
    ) -> StateT:
        """
        执行所有 after_model 钩子
        
        Args:
            state: 当前状态
            runtime: 运行时上下文
            response: LLM 响应
            request: 原始请求
        
        Returns:
            更新后的状态
        """
        return await self._run_hooks(
            self._mw_after_model,
            'after_model',
            'aafter_model',
            state,
            runtime=runtime,
            response=response,
            request=request,
        )
    
    async def _run_hooks(
        self,
        middleware_list: List[Any],
        sync_hook_name: str,
        async_hook_name: str,
        state: StateT,
        **kwargs,
    ) -> StateT:
        """
        执行钩子列表
        
        Args:
            middleware_list: 要执行的 middleware 列表
            sync_hook_name: 同步钩子名称
            async_hook_name: 异步钩子名称
            state: 当前状态
            **kwargs: 传递给钩子的额外参数
        
        Returns:
            更新后的状态
        """
        current_state = dict(state)
        
        for mw in middleware_list:
            mw_name = type(mw).__name__
            start_time = time.time()
            
            try:
                # 优先使用异步版本
                async_hook = getattr(mw, async_hook_name, None)
                sync_hook = getattr(mw, sync_hook_name, None)
                
                result = None
                
                if async_hook and self._is_overridden(mw, async_hook_name):
                    # 获取钩子函数的参数签名，只传递它接受的参数
                    filtered_kwargs = self._filter_kwargs_for_hook(async_hook, kwargs)
                    # 调用异步钩子
                    result = await async_hook(state=current_state, **filtered_kwargs)
                elif sync_hook and self._is_overridden(mw, sync_hook_name):
                    # 获取钩子函数的参数签名，只传递它接受的参数
                    filtered_kwargs = self._filter_kwargs_for_hook(sync_hook, kwargs)
                    # 调用同步钩子
                    if asyncio.iscoroutinefunction(sync_hook):
                        result = await sync_hook(state=current_state, **filtered_kwargs)
                    else:
                        result = sync_hook(state=current_state, **filtered_kwargs)
                
                # 合并状态更新（使用 reducer 处理特殊字段）
                if result and isinstance(result, dict):
                    current_state = self.merge_middleware_state_updates(
                        current_state, result
                    )
                
                elapsed = time.time() - start_time
                logger.debug(
                    f"Middleware '{mw_name}' hook '{async_hook_name}' "
                    f"completed in {elapsed:.3f}s"
                )
                
            except Exception as e:
                elapsed = time.time() - start_time
                logger.error(
                    f"Middleware '{mw_name}' hook '{async_hook_name}' "
                    f"failed after {elapsed:.3f}s: {e}",
                    exc_info=True,
                )
                
                if self.fail_fast:
                    raise MiddlewareError(mw_name, async_hook_name, e) from e
                # 否则继续执行后续 middleware
        
        return current_state
    
    def _filter_kwargs_for_hook(
        self,
        hook: Callable,
        kwargs: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        根据钩子函数的签名过滤 kwargs
        
        只传递钩子函数实际接受的参数，避免 TypeError。
        
        Args:
            hook: 钩子函数
            kwargs: 要传递的参数字典
        
        Returns:
            过滤后的参数字典
        """
        try:
            sig = inspect.signature(hook)
            params = sig.parameters
            
            # 检查是否接受 **kwargs
            has_var_keyword = any(
                p.kind == inspect.Parameter.VAR_KEYWORD
                for p in params.values()
            )
            
            if has_var_keyword:
                # 如果接受 **kwargs，传递所有参数
                return kwargs
            
            # 只传递函数签名中定义的参数
            accepted_params = set(params.keys()) - {'self'}
            return {k: v for k, v in kwargs.items() if k in accepted_params}
            
        except (ValueError, TypeError):
            # 如果无法获取签名，返回原始 kwargs
            return kwargs

    
    # ═══════════════════════════════════════════════════════════════════════
    # Wrap 钩子链
    # ═══════════════════════════════════════════════════════════════════════
    
    async def wrap_model_call(
        self,
        request: ModelRequest,
        base_handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        """
        链式调用所有 wrap_model_call 钩子
        
        使用洋葱模型：第一个 middleware 在最外层
        
        Args:
            request: ModelRequest 对象
            base_handler: 实际的 LLM 调用函数
        
        Returns:
            ModelResponse 对象
        """
        if not self._mw_wrap_model_call:
            return await base_handler(request)
        
        # 构建链式调用
        handler = base_handler
        
        # 从后往前包装（最后一个 middleware 最接近实际调用）
        for mw in reversed(self._mw_wrap_model_call):
            handler = self._create_model_call_wrapper(mw, handler)
        
        return await handler(request)
    
    def _create_model_call_wrapper(
        self,
        mw: Any,
        next_handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> Callable[[ModelRequest], Awaitable[ModelResponse]]:
        """创建单个 middleware 的包装函数"""
        mw_name = type(mw).__name__
        
        async def wrapper(request: ModelRequest) -> ModelResponse:
            start_time = time.time()
            
            try:
                # 优先使用异步版本
                async_hook = getattr(mw, 'awrap_model_call', None)
                sync_hook = getattr(mw, 'wrap_model_call', None)
                
                if async_hook and self._is_overridden(mw, 'awrap_model_call'):
                    result = await async_hook(request, next_handler)
                elif sync_hook and self._is_overridden(mw, 'wrap_model_call'):
                    if asyncio.iscoroutinefunction(sync_hook):
                        result = await sync_hook(request, next_handler)
                    else:
                        # 同步钩子需要特殊处理
                        result = sync_hook(request, next_handler)
                        if asyncio.iscoroutine(result):
                            result = await result
                else:
                    # 没有实现钩子，直接调用下一个
                    result = await next_handler(request)
                
                elapsed = time.time() - start_time
                logger.debug(
                    f"Middleware '{mw_name}' wrap_model_call "
                    f"completed in {elapsed:.3f}s"
                )
                
                return result
                
            except Exception as e:
                elapsed = time.time() - start_time
                logger.error(
                    f"Middleware '{mw_name}' wrap_model_call "
                    f"failed after {elapsed:.3f}s: {e}",
                    exc_info=True,
                )
                
                if self.fail_fast:
                    raise MiddlewareChainError(mw_name, 'wrap_model_call', e) from e
                raise
        
        return wrapper
    
    async def wrap_tool_call(
        self,
        request: ToolCallRequest,
        base_handler: Callable[[ToolCallRequest], Awaitable[Union[ToolMessage, Command]]],
    ) -> Union[ToolMessage, Command]:
        """
        链式调用所有 wrap_tool_call 钩子
        
        使用洋葱模型：第一个 middleware 在最外层
        
        Args:
            request: ToolCallRequest 对象
            base_handler: 实际的工具调用函数
        
        Returns:
            ToolMessage 或 Command
        """
        if not self._mw_wrap_tool_call:
            return await base_handler(request)
        
        # 构建链式调用
        handler = base_handler
        
        # 从后往前包装
        for mw in reversed(self._mw_wrap_tool_call):
            handler = self._create_tool_call_wrapper(mw, handler)
        
        return await handler(request)
    
    def _create_tool_call_wrapper(
        self,
        mw: Any,
        next_handler: Callable[[ToolCallRequest], Awaitable[Union[ToolMessage, Command]]],
    ) -> Callable[[ToolCallRequest], Awaitable[Union[ToolMessage, Command]]]:
        """创建单个 middleware 的工具调用包装函数"""
        mw_name = type(mw).__name__
        
        async def wrapper(request: ToolCallRequest) -> Union[ToolMessage, Command]:
            start_time = time.time()
            
            try:
                # 优先使用异步版本
                async_hook = getattr(mw, 'awrap_tool_call', None)
                sync_hook = getattr(mw, 'wrap_tool_call', None)
                
                if async_hook and self._is_overridden(mw, 'awrap_tool_call'):
                    result = await async_hook(request, next_handler)
                elif sync_hook and self._is_overridden(mw, 'wrap_tool_call'):
                    if asyncio.iscoroutinefunction(sync_hook):
                        result = await sync_hook(request, next_handler)
                    else:
                        result = sync_hook(request, next_handler)
                        if asyncio.iscoroutine(result):
                            result = await result
                else:
                    result = await next_handler(request)
                
                elapsed = time.time() - start_time
                logger.debug(
                    f"Middleware '{mw_name}' wrap_tool_call "
                    f"completed in {elapsed:.3f}s"
                )
                
                return result
                
            except Exception as e:
                elapsed = time.time() - start_time
                logger.error(
                    f"Middleware '{mw_name}' wrap_tool_call "
                    f"failed after {elapsed:.3f}s: {e}",
                    exc_info=True,
                )
                
                if self.fail_fast:
                    raise MiddlewareChainError(mw_name, 'wrap_tool_call', e) from e
                raise
        
        return wrapper
    
    # ═══════════════════════════════════════════════════════════════════════
    # 高级 API
    # ═══════════════════════════════════════════════════════════════════════
    
    async def call_model_with_middleware(
        self,
        model: BaseChatModel,
        messages: List[BaseMessage],
        tools: Optional[List[Any]] = None,
        state: Optional[Dict[str, Any]] = None,
        runtime: Optional[Runtime] = None,
        system_prompt: Optional[str] = None,
    ) -> ModelResponse:
        """
        完整的 LLM 调用流程，包含所有 middleware 钩子
        
        执行顺序：
        1. before_model hooks
        2. wrap_model_call chain
        3. after_model hooks
        
        Args:
            model: LLM 实例
            messages: 消息列表
            tools: 可用工具列表
            state: 当前状态
            runtime: 运行时上下文
            system_prompt: 系统提示
        
        Returns:
            ModelResponse 对象
        """
        current_state = dict(state) if state else {}
        runtime = runtime or self.build_runtime()
        
        # 构建 ModelRequest
        request = self.build_model_request(
            model=model,
            messages=messages,
            tools=tools,
            state=current_state,
            runtime=runtime,
            system_prompt=system_prompt,
        )
        
        # 1. before_model hooks
        current_state = await self.run_before_model(
            current_state,
            runtime,
            request=request,
        )
        
        # 更新 request 中的 state
        request = request.override(state=current_state)
        
        # 2. wrap_model_call chain
        async def base_model_handler(req: ModelRequest) -> ModelResponse:
            """实际的 LLM 调用"""
            llm = req.model
            msgs = req.messages
            
            # 绑定工具（如果有）
            if req.tools:
                llm = llm.bind_tools(req.tools)
            
            # 调用 LLM
            response = await llm.ainvoke(msgs)
            
            return self.build_model_response(
                result=[response] if isinstance(response, AIMessage) else response,
            )
        
        response = await self.wrap_model_call(request, base_model_handler)
        
        # 3. after_model hooks
        current_state = await self.run_after_model(
            current_state,
            runtime,
            response=response,
            request=request,
        )
        
        return response
    
    async def call_tool_with_middleware(
        self,
        tool: BaseTool,
        tool_call: Dict[str, Any],
        state: Dict[str, Any],
        runtime: Runtime,
    ) -> Union[ToolMessage, Command]:
        """
        完整的工具调用流程，包含所有 middleware 钩子
        
        Args:
            tool: 工具实例
            tool_call: 工具调用信息
            state: 当前状态
            runtime: 运行时上下文
        
        Returns:
            ToolMessage 或 Command
        """
        request = self.build_tool_call_request(
            tool_call=tool_call,
            tool=tool,
            state=state,
            runtime=runtime,
        )
        
        async def base_tool_handler(req: ToolCallRequest) -> ToolMessage:
            """实际的工具调用"""
            tool_instance = req.tool
            args = req.tool_call.get('args', {})
            tool_id = req.tool_call.get('id', '')
            
            try:
                if hasattr(tool_instance, 'ainvoke'):
                    result = await tool_instance.ainvoke(args)
                else:
                    result = tool_instance.invoke(args)
            except Exception as e:
                result = f"Error: {str(e)}"
            
            return ToolMessage(content=str(result), tool_call_id=tool_id)
        
        return await self.wrap_tool_call(request, base_tool_handler)


# ═══════════════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════════════

def get_middleware_from_config(
    config: Optional[Dict[str, Any]],
) -> Optional[List[Any]]:
    """
    从 config 中获取 middleware 栈
    
    Args:
        config: LangGraph RunnableConfig
    
    Returns:
        Middleware 列表，如果不存在则返回 None
    """
    if not config:
        return None
    
    # 尝试从 configurable 中获取
    configurable = config.get('configurable', {})
    middleware = configurable.get('middleware')
    
    if middleware:
        return middleware
    
    # 尝试直接从 config 获取
    return config.get('middleware')


# ═══════════════════════════════════════════════════════════════════════════
# 导出
# ═══════════════════════════════════════════════════════════════════════════

__all__ = [
    # 主类
    'MiddlewareRunner',
    
    # 异常
    'MiddlewareError',
    'MiddlewareValidationError',
    'MiddlewareChainError',
    
    # 类型
    'ModelRequest',
    'ModelResponse',
    'ToolCallRequest',
    'Runtime',
    
    # 辅助函数
    'get_middleware_from_config',
    
    # 常量
    'LANGCHAIN_MIDDLEWARE_AVAILABLE',
]
