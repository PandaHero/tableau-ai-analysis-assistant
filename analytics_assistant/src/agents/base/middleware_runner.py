# -*- coding: utf-8 -*-
"""
MiddlewareRunner - Middleware 运行器

用于在自定义 StateGraph 节点函数中执行 LangChain AgentMiddleware。

支持所有 6 个 AgentMiddleware 钩子：
- before_agent / abefore_agent
- before_model / abefore_model
- wrap_model_call / awrap_model_call
- after_model / aafter_model
- wrap_tool_call / awrap_tool_call
- after_agent / aafter_agent

使用示例：
    from analytics_assistant.src.agents.base.middleware_runner import MiddlewareRunner
    
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
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
from dataclasses import dataclass, field, replace
from typing import Any, Awaitable, Callable, Optional, TypeVar, Union

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)

StateT = TypeVar('StateT', bound=dict[str, Any])

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
            f"Middleware '{middleware_name}' 在钩子 '{hook_name}' 中失败: {original_error}"
        )

class MiddlewareChainError(MiddlewareError):
    """Middleware 链式调用错误"""
    pass

# ═══════════════════════════════════════════════════════════════════════════
# 类型定义
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class Runtime:
    """
    LangGraph Runtime 兼容类
    
    用于传递运行时上下文和配置。
    """
    context: Any = None
    store: Any = None
    config: dict[str, Any] = field(default_factory=dict)

@dataclass
class ModelRequest:
    """LLM 调用请求"""
    model: BaseChatModel
    messages: list[BaseMessage]
    system_message: Optional[BaseMessage] = None
    system_prompt: Optional[str] = None
    tool_choice: Any = None
    tools: Optional[list[Any]] = None
    response_format: Any = None
    state: Optional[dict[str, Any]] = None
    runtime: Any = None
    model_settings: Optional[dict[str, Any]] = None
    
    def override(self, **kwargs) -> 'ModelRequest':
        """创建修改后的副本"""
        return replace(self, **kwargs)

@dataclass
class ModelResponse:
    """LLM 调用响应"""
    result: list[AIMessage]
    structured_response: Any = None

@dataclass
class ToolCallRequest:
    """工具调用请求"""
    tool_call: dict[str, Any]
    tool: BaseTool
    state: dict[str, Any]
    runtime: Any
    
    def override(self, **kwargs) -> 'ToolCallRequest':
        """创建修改后的副本"""
        return replace(self, **kwargs)

@dataclass
class HookExecutionResult:
    """钩子执行结果"""
    success: bool
    middleware_name: str
    error: Optional[Exception] = None
    duration_ms: int = 0

# ═══════════════════════════════════════════════════════════════════════════
# MiddlewareRunner
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class MiddlewareRunner:
    """
    Middleware 运行器
    
    用于在自定义节点函数中执行 LangChain middleware。
    支持所有 6 个 AgentMiddleware 钩子。
    
    Attributes:
        middleware: Middleware 列表
        fail_fast: 是否在第一个错误时停止（默认 True）
    """
    
    middleware: list[Any]
    fail_fast: bool = True
    
    # 按钩子类型分类的 middleware（初始化时计算）
    _mw_before_agent: list[Any] = field(default_factory=list, init=False)
    _mw_before_model: list[Any] = field(default_factory=list, init=False)
    _mw_after_model: list[Any] = field(default_factory=list, init=False)
    _mw_after_agent: list[Any] = field(default_factory=list, init=False)
    _mw_wrap_model_call: list[Any] = field(default_factory=list, init=False)
    _mw_wrap_tool_call: list[Any] = field(default_factory=list, init=False)
    
    def __post_init__(self):
        """初始化后分类 middleware"""
        self._classify_middleware()
    
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
        """检查 middleware 是否实现了指定的钩子"""
        async_method = getattr(mw, async_name, None)
        if async_method is not None and self._is_overridden(mw, async_name):
            return True
        
        sync_method = getattr(mw, sync_name, None)
        if sync_method is not None and self._is_overridden(mw, sync_name):
            return True
        
        return False
    
    def _is_overridden(self, obj: Any, method_name: str) -> bool:
        """检查方法是否被子类覆盖"""
        method = getattr(obj, method_name, None)
        if method is None:
            return False
        
        if hasattr(method, '__func__'):
            method_class = method.__func__.__qualname__.rsplit('.', 1)[0]
        else:
            method_class = method.__qualname__.rsplit('.', 1)[0]
        
        obj_class_name = type(obj).__name__
        return method_class == obj_class_name
    
    @property
    def names(self) -> list[str]:
        """返回所有已注册 middleware 的名称列表"""
        return [type(mw).__name__ for mw in self.middleware]
    
    # ═══════════════════════════════════════════════════════════════════════
    # Runtime 和 Request 构建
    # ═══════════════════════════════════════════════════════════════════════
    
    def build_runtime(
        self,
        config: Optional[dict[str, Any]] = None,
        context: Any = None,
        store: Any = None,
    ) -> Runtime:
        """构建 Runtime 对象"""
        return Runtime(
            context=context,
            store=store,
            config=config or {},
        )
    
    def build_model_request(
        self,
        model: BaseChatModel,
        messages: list[BaseMessage],
        tools: Optional[list[Any]] = None,
        state: Optional[dict[str, Any]] = None,
        runtime: Optional[Runtime] = None,
        system_prompt: Optional[str] = None,
    ) -> ModelRequest:
        """构建 ModelRequest 对象"""
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
        result: list[AIMessage],
        structured_response: Any = None,
    ) -> ModelResponse:
        """构建 ModelResponse 对象"""
        return ModelResponse(
            result=result,
            structured_response=structured_response,
        )
    
    def build_tool_call_request(
        self,
        tool_call: dict[str, Any],
        tool: BaseTool,
        state: dict[str, Any],
        runtime: Runtime,
    ) -> ToolCallRequest:
        """构建 ToolCallRequest 对象"""
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
        """执行所有 before_agent 钩子"""
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
        """执行所有 after_agent 钩子"""
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
        """执行所有 before_model 钩子"""
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
        """执行所有 after_model 钩子"""
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
        middleware_list: list[Any],
        sync_hook_name: str,
        async_hook_name: str,
        state: StateT,
        **kwargs,
    ) -> StateT:
        """执行钩子列表"""
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
                    filtered_kwargs = self._filter_kwargs_for_hook(async_hook, kwargs)
                    result = await async_hook(state=current_state, **filtered_kwargs)
                elif sync_hook and self._is_overridden(mw, sync_hook_name):
                    filtered_kwargs = self._filter_kwargs_for_hook(sync_hook, kwargs)
                    if asyncio.iscoroutinefunction(sync_hook):
                        result = await sync_hook(state=current_state, **filtered_kwargs)
                    else:
                        result = sync_hook(state=current_state, **filtered_kwargs)
                
                # 合并状态更新
                if result and isinstance(result, dict):
                    current_state.update(result)
                
                elapsed = time.time() - start_time
                logger.debug(
                    f"Middleware '{mw_name}' 钩子 '{async_hook_name}' "
                    f"完成，耗时 {elapsed:.3f}s"
                )
                
            except Exception as e:
                elapsed = time.time() - start_time
                logger.error(
                    f"Middleware '{mw_name}' 钩子 '{async_hook_name}' "
                    f"失败，耗时 {elapsed:.3f}s: {e}",
                    exc_info=True,
                )
                
                if self.fail_fast:
                    raise MiddlewareError(mw_name, async_hook_name, e) from e
        
        return current_state
    
    def _filter_kwargs_for_hook(
        self,
        hook: Callable,
        kwargs: dict[str, Any],
    ) -> dict[str, Any]:
        """根据钩子函数的签名过滤 kwargs"""
        try:
            sig = inspect.signature(hook)
            params = sig.parameters
            
            # 检查是否接受 **kwargs
            has_var_keyword = any(
                p.kind == inspect.Parameter.VAR_KEYWORD
                for p in params.values()
            )
            
            if has_var_keyword:
                return kwargs
            
            # 只传递函数签名中定义的参数
            accepted_params = set(params.keys()) - {'self'}
            return {k: v for k, v in kwargs.items() if k in accepted_params}
            
        except (ValueError, TypeError):
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
                async_hook = getattr(mw, 'awrap_model_call', None)
                sync_hook = getattr(mw, 'wrap_model_call', None)
                
                if async_hook and self._is_overridden(mw, 'awrap_model_call'):
                    result = await async_hook(request, next_handler)
                elif sync_hook and self._is_overridden(mw, 'wrap_model_call'):
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
                    f"Middleware '{mw_name}' wrap_model_call "
                    f"完成，耗时 {elapsed:.3f}s"
                )
                
                return result
                
            except Exception as e:
                elapsed = time.time() - start_time
                logger.error(
                    f"Middleware '{mw_name}' wrap_model_call "
                    f"失败，耗时 {elapsed:.3f}s: {e}",
                    exc_info=True,
                )
                
                if self.fail_fast:
                    raise MiddlewareChainError(mw_name, 'wrap_model_call', e) from e
                raise
        
        return wrapper
    
    async def wrap_tool_call(
        self,
        request: ToolCallRequest,
        base_handler: Callable[[ToolCallRequest], Awaitable[ToolMessage]],
    ) -> ToolMessage:
        """链式调用所有 wrap_tool_call 钩子"""
        if not self._mw_wrap_tool_call:
            return await base_handler(request)
        
        handler = base_handler
        
        for mw in reversed(self._mw_wrap_tool_call):
            handler = self._create_tool_call_wrapper(mw, handler)
        
        return await handler(request)
    
    def _create_tool_call_wrapper(
        self,
        mw: Any,
        next_handler: Callable[[ToolCallRequest], Awaitable[ToolMessage]],
    ) -> Callable[[ToolCallRequest], Awaitable[ToolMessage]]:
        """创建单个 middleware 的工具调用包装函数"""
        mw_name = type(mw).__name__
        
        async def wrapper(request: ToolCallRequest) -> ToolMessage:
            start_time = time.time()
            
            try:
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
                    f"完成，耗时 {elapsed:.3f}s"
                )
                
                return result
                
            except Exception as e:
                elapsed = time.time() - start_time
                logger.error(
                    f"Middleware '{mw_name}' wrap_tool_call "
                    f"失败，耗时 {elapsed:.3f}s: {e}",
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
        messages: list[BaseMessage],
        tools: Optional[list[Any]] = None,
        state: Optional[dict[str, Any]] = None,
        runtime: Optional[Runtime] = None,
        system_prompt: Optional[str] = None,
    ) -> ModelResponse:
        """
        完整的 LLM 调用流程，包含所有 middleware 钩子
        
        执行顺序：
        1. before_model hooks
        2. wrap_model_call chain
        3. after_model hooks
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
                result=[response] if isinstance(response, AIMessage) else [response],
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
        tool_call: dict[str, Any],
        state: dict[str, Any],
        runtime: Runtime,
    ) -> ToolMessage:
        """完整的工具调用流程，包含所有 middleware 钩子"""
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
                result = f"错误: {str(e)}"
            
            return ToolMessage(content=str(result), tool_call_id=tool_id)
        
        return await self.wrap_tool_call(request, base_tool_handler)

# ═══════════════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════════════

def get_middleware_from_config(
    config: Optional[dict[str, Any]],
) -> Optional[list[Any]]:
    """从 config 中获取 middleware 栈"""
    if not config:
        return None
    
    configurable = config.get('configurable', {})
    middleware = configurable.get('middleware')
    
    if middleware:
        return middleware
    
    return config.get('middleware')

# ═══════════════════════════════════════════════════════════════════════════
# 导出
# ═══════════════════════════════════════════════════════════════════════════

__all__ = [
    # 主类
    'MiddlewareRunner',
    
    # 异常
    'MiddlewareError',
    'MiddlewareChainError',
    
    # 类型
    'ModelRequest',
    'ModelResponse',
    'ToolCallRequest',
    'Runtime',
    'HookExecutionResult',
    
    # 辅助函数
    'get_middleware_from_config',
]
