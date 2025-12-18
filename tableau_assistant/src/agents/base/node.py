"""
Agent 基础工具模块

提供所有 Agent 节点共用的基础能力：
1. LLM 获取和配置
2. 工具调用处理（Tool Calls）
3. JSON 解析和清理
4. 流式输出支持

设计原则：
- 提供工具函数，不强制继承
- 每个 Agent 自己定义 Prompt 和处理逻辑
- 参考 semantic_parser/node.py 的实现模式

使用示例：

    from tableau_assistant.src.agents.base import (
        get_llm,
        get_agent_temperature,
        call_llm_with_tools,
        parse_json_response,
        stream_llm_call,
    )
    
    # 在 Agent 节点中使用
    async def my_agent_node(state, config):
        # 方式 1：使用 agent_name 自动选择 temperature
        llm = get_llm(agent_name="semantic_parser")  # temperature=0.1
        
        # 方式 2：直接指定 temperature
        llm = get_llm(temperature=0.1)
        
        tools = [my_tool_1, my_tool_2]
        messages = MY_PROMPT.format_messages(...)
        
        # 带工具调用
        response = await call_llm_with_tools(llm, messages, tools)
        result = parse_json_response(response, MyOutputModel)
        
        # 流式输出（无工具）
        response = await stream_llm_call(llm, messages)
        result = parse_json_response(response, MyOutputModel)
"""
import json
import logging
import re
from typing import Dict, Any, List, Optional, Type, TypeVar, AsyncIterator

from pydantic import BaseModel
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    HumanMessage,
    SystemMessage,
    AIMessage,
    ToolMessage,
)

logger = logging.getLogger(__name__)

T = TypeVar('T', bound=BaseModel)


# ═══════════════════════════════════════════════════════════════════════════
# LLM 获取（从 infra/ai 导入）
# ═══════════════════════════════════════════════════════════════════════════

from tableau_assistant.src.infra.ai import get_llm as _get_llm


# ═══════════════════════════════════════════════════════════════════════════
# Agent Temperature 配置（Agent 层配置，不放在 model_manager）
# ═══════════════════════════════════════════════════════════════════════════

AGENT_TEMPERATURE_CONFIG = {
    "semantic_parser": 0.1,     # 需要精确理解用户意图
    "dimension_hierarchy": 0.1, # 需要精确推断层级关系
    "field_mapper": 0.1,        # 需要精确的字段映射
    "insight": 0.4,             # 需要创造性发现洞察
    "replanner": 0.2,           # 需要判断是否重规划
    "default": 0.2,
}


def get_agent_temperature(agent_name: str) -> float:
    """获取指定 Agent 的默认 temperature"""
    return AGENT_TEMPERATURE_CONFIG.get(
        agent_name.lower(),
        AGENT_TEMPERATURE_CONFIG["default"]
    )


def get_llm(
    agent_name: Optional[str] = None,
    temperature: Optional[float] = None,
    **kwargs
) -> BaseChatModel:
    """
    获取 LLM 实例（Agent 层封装）
    
    这是 Agent 层的便捷函数，支持通过 agent_name 自动选择 temperature。
    底层调用 model_manager.get_llm。
    
    Args:
        agent_name: Agent 名称（可选，用于自动选择 temperature）
        temperature: 温度参数（可选，覆盖 agent_name 配置）
        **kwargs: 传递给 model_manager.get_llm 的其他参数
    
    Returns:
        配置好的 LLM 实例
    
    Examples:
        # 使用 agent 对应的 temperature
        llm = get_llm(agent_name="semantic_parser")  # temperature=0.1
        
        # 显式指定 temperature（覆盖 agent_name）
        llm = get_llm(agent_name="semantic_parser", temperature=0.3)
        
        # 直接指定 temperature
        llm = get_llm(temperature=0.1)
    """
    # Temperature 优先级：显式参数 > agent_name 配置
    if temperature is not None:
        _temperature = temperature
    elif agent_name:
        _temperature = get_agent_temperature(agent_name)
    else:
        _temperature = None  # 使用 model_manager 的默认值
    
    return _get_llm(temperature=_temperature, **kwargs)


# ═══════════════════════════════════════════════════════════════════════════
# 工具调用处理
# ═══════════════════════════════════════════════════════════════════════════

def convert_messages(messages: List[Dict[str, str]]) -> List:
    """
    将字典格式的消息转换为 LangChain 消息对象
    
    Args:
        messages: [{"role": "system", "content": "..."}, ...]
    
    Returns:
        LangChain 消息对象列表
    """
    langchain_messages = []
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        
        if role == "system":
            langchain_messages.append(SystemMessage(content=content))
        elif role == "user":
            langchain_messages.append(HumanMessage(content=content))
        elif role == "assistant":
            langchain_messages.append(AIMessage(content=content))
    
    return langchain_messages


async def _call_llm_with_tools_and_middleware(
    llm: BaseChatModel,
    messages: List[Dict[str, str]],
    tools: List[Any],
    max_iterations: int,
    streaming: bool,
    middleware: List[Any],
    state: Dict[str, Any],
    config: Optional[Dict[str, Any]],
) -> str:
    """
    带 middleware 支持的 LLM 调用（内部函数）
    
    执行顺序：
    1. before_model hooks
    2. wrap_model_call chain (包含实际 LLM 调用)
    3. after_model hooks
    4. 如果有 tool_calls，执行 wrap_tool_call chain
    5. 循环直到没有 tool_calls 或达到 max_iterations
    """
    from tableau_assistant.src.agents.base.middleware_runner import (
        MiddlewareRunner,
        ModelRequest,
        ModelResponse,
    )
    
    # 创建 MiddlewareRunner
    runner = MiddlewareRunner(middleware)
    runtime = runner.build_runtime(config)
    
    # 转换消息格式
    langchain_messages = convert_messages(messages)
    
    # 构建工具映射
    tool_map = {tool.name: tool for tool in tools}
    
    # 迭代处理
    for iteration in range(max_iterations):
        logger.debug(f"LLM iteration {iteration + 1}/{max_iterations} (with middleware)")
        
        # 1. before_model hooks
        state = await runner.run_before_model(state, runtime)
        
        # 2. wrap_model_call chain
        async def base_model_handler(request: ModelRequest) -> ModelResponse:
            """实际的 LLM 调用"""
            _llm = request.model
            _msgs = request.messages
            
            # 绑定工具
            if request.tools:
                _llm = _llm.bind_tools(request.tools)
            
            # 调用 LLM
            if streaming:
                response = await _stream_llm_call_internal(_llm, _msgs)
            else:
                response = await _llm.ainvoke(_msgs)
            
            return runner.build_model_response(
                result=[response] if isinstance(response, AIMessage) else [response],
            )
        
        # 构建 ModelRequest
        request = runner.build_model_request(
            model=llm,
            messages=langchain_messages,
            tools=tools,
            state=state,
            runtime=runtime,
        )
        
        # 通过 wrap_model_call 链调用
        model_response = await runner.wrap_model_call(request, base_model_handler)
        
        # 3. after_model hooks
        state = await runner.run_after_model(
            state, runtime,
            response=model_response,
            request=request,
        )
        
        # 获取 LLM 响应
        if not model_response.result:
            return ""
        
        response = model_response.result[0]
        langchain_messages.append(response)
        
        # 检查是否有工具调用
        if not response.tool_calls:
            logger.debug("No tool calls, returning response (with middleware)")
            return response.content
        
        # 4. 处理工具调用（通过 wrap_tool_call 链）
        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_id = tool_call["id"]
            
            logger.info(f"Tool call: {tool_name}({tool_args})")
            
            tool = tool_map.get(tool_name)
            if tool is None:
                tool_result = f"Error: Tool '{tool_name}' not found"
                logger.warning(tool_result)
            else:
                # 通过 wrap_tool_call 链调用工具
                tool_message = await runner.call_tool_with_middleware(
                    tool=tool,
                    tool_call=tool_call,
                    state=state,
                    runtime=runtime,
                )
                tool_result = tool_message.content if hasattr(tool_message, 'content') else str(tool_message)
            
            # 添加工具结果消息
            langchain_messages.append(
                ToolMessage(content=str(tool_result), tool_call_id=tool_id)
            )
    
    # 达到最大迭代次数
    logger.warning(f"Max iterations ({max_iterations}) reached (with middleware)")
    
    for msg in reversed(langchain_messages):
        if hasattr(msg, 'content') and msg.content:
            return msg.content
    
    return ""


async def call_llm_with_tools(
    llm: BaseChatModel,
    messages: List[Dict[str, str]],
    tools: List[Any],
    max_iterations: int = 5,
    streaming: bool = True,
    # Middleware 支持参数
    middleware: Optional[List[Any]] = None,
    state: Optional[Dict[str, Any]] = None,
    config: Optional[Dict[str, Any]] = None,
) -> str:
    """
    调用 LLM 并处理工具调用
    
    这是 Agent 节点的核心函数，处理 LLM 与工具的交互循环。
    默认使用流式调用，以便 LangGraph 的 astream_events 能捕获 token 事件。
    
    支持 middleware 参数，当提供时会创建 MiddlewareRunner 并应用所有钩子。
    
    Args:
        llm: LLM 实例
        messages: 消息列表 [{"role": "system", "content": "..."}, ...]
        tools: 可用工具列表（@tool 装饰的函数）
        max_iterations: 最大迭代次数（防止无限循环）
        streaming: 是否使用流式调用（默认 True，支持 token 级别流式输出）
        middleware: 可选的 middleware 列表（AgentMiddleware 实例）
        state: 可选的当前状态（用于 middleware）
        config: 可选的 LangGraph RunnableConfig（用于 middleware）
    
    Returns:
        LLM 最终响应内容（字符串）
    
    Example:
        llm = get_llm(temperature=0.1)  # 或 get_llm(agent_name="semantic_parser")
        tools = [get_metadata, calculate_date_range]
        messages = MY_PROMPT.format_messages(question="各省份销售额")
        
        # 不带 middleware
        response = await call_llm_with_tools(llm, messages, tools)
        result = parse_json_response(response, SemanticQuery)
        
        # 带 middleware
        response = await call_llm_with_tools(
            llm, messages, tools,
            middleware=middleware_stack,
            state=state,
            config=config,
        )
    """
    # 如果提供了 middleware，使用 MiddlewareRunner
    if middleware:
        return await _call_llm_with_tools_and_middleware(
            llm=llm,
            messages=messages,
            tools=tools,
            max_iterations=max_iterations,
            streaming=streaming,
            middleware=middleware,
            state=state or {},
            config=config,
        )
    
    # 绑定工具到 LLM
    llm_with_tools = llm.bind_tools(tools)
    
    # 转换消息格式
    langchain_messages = convert_messages(messages)
    
    # 构建工具映射（用于快速查找）
    tool_map = {tool.name: tool for tool in tools}
    
    # 迭代处理工具调用
    for iteration in range(max_iterations):
        logger.debug(f"LLM iteration {iteration + 1}/{max_iterations}")
        
        if streaming:
            # 流式调用 - 支持 token 级别输出
            response = await _stream_llm_call_internal(llm_with_tools, langchain_messages)
        else:
            # 非流式调用
            response = await llm_with_tools.ainvoke(langchain_messages)
        
        langchain_messages.append(response)
        
        # 检查是否有工具调用
        if not response.tool_calls:
            # 没有工具调用，返回最终响应
            logger.debug("No tool calls, returning response")
            return response.content
        
        # 处理工具调用
        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_id = tool_call["id"]
            
            logger.info(f"Tool call: {tool_name}({tool_args})")
            
            # 查找并执行工具
            tool = tool_map.get(tool_name)
            if tool is None:
                tool_result = f"Error: Tool '{tool_name}' not found"
                logger.warning(tool_result)
            else:
                try:
                    # 异步工具
                    if hasattr(tool, 'ainvoke'):
                        tool_result = await tool.ainvoke(tool_args)
                    else:
                        tool_result = tool.invoke(tool_args)
                except Exception as e:
                    logger.error(f"Tool {tool_name} failed: {e}")
                    tool_result = f"Error: {str(e)}"
            
            # 添加工具结果消息
            langchain_messages.append(
                ToolMessage(content=str(tool_result), tool_call_id=tool_id)
            )
    
    # 达到最大迭代次数
    logger.warning(f"Max iterations ({max_iterations}) reached")
    
    # 返回最后一条消息的内容
    for msg in reversed(langchain_messages):
        if hasattr(msg, 'content') and msg.content:
            return msg.content
    
    return ""


async def _stream_llm_call_internal(
    llm: BaseChatModel,
    messages: List,
) -> AIMessage:
    """
    内部流式调用 LLM，返回完整的 AIMessage
    
    使用 astream_events 而不是 ainvoke，这样 LangGraph 的外层 astream_events 
    能够捕获到 on_chat_model_stream 事件，实现 token 级别的流式输出。
    
    关键：LangGraph 的事件传播机制会将内部 LLM 调用的事件冒泡到外层，
    所以在节点内部使用 astream_events 调用 LLM，外层的 workflow.astream_events
    就能捕获到 token 事件。
    
    Args:
        llm: 已绑定工具的 LLM 实例
        messages: LangChain 消息列表
    
    Returns:
        完整的 AIMessage（包含 content 和 tool_calls）
    """
    collected_content = []
    tool_calls = []
    
    # 使用 astream_events 以便事件能被 LangGraph 捕获
    async for event in llm.astream_events(messages, version="v2"):
        event_type = event.get("event")
        
        if event_type == "on_chat_model_stream":
            chunk = event.get("data", {}).get("chunk")
            if chunk:
                # 收集 content
                if hasattr(chunk, "content") and chunk.content:
                    collected_content.append(chunk.content)
                
                # 收集 tool_calls（流式累积）
                if hasattr(chunk, "tool_call_chunks") and chunk.tool_call_chunks:
                    for tc_chunk in chunk.tool_call_chunks:
                        tc_index = tc_chunk.get("index", 0)
                        while len(tool_calls) <= tc_index:
                            tool_calls.append({"name": "", "args": "", "id": ""})
                        
                        if tc_chunk.get("name"):
                            tool_calls[tc_index]["name"] = tc_chunk["name"]
                        if tc_chunk.get("id"):
                            tool_calls[tc_index]["id"] = tc_chunk["id"]
                        if tc_chunk.get("args"):
                            tool_calls[tc_index]["args"] += tc_chunk["args"]
    
    # 解析 tool_calls 的 args（从字符串到字典）
    import json as json_module
    parsed_tool_calls = []
    for tc in tool_calls:
        if tc["name"] and tc["id"]:
            try:
                args = json_module.loads(tc["args"]) if tc["args"] else {}
            except json_module.JSONDecodeError:
                args = {}
            parsed_tool_calls.append({
                "name": tc["name"],
                "args": args,
                "id": tc["id"],
            })
    
    return AIMessage(
        content="".join(collected_content),
        tool_calls=parsed_tool_calls
    )


async def stream_llm_with_tools(
    llm: BaseChatModel,
    messages: List[Dict[str, str]],
    tools: List[Any],
    max_iterations: int = 5,
) -> AsyncIterator[Dict[str, Any]]:
    """
    流式调用 LLM 并处理工具调用（Token 级别流式输出）
    
    与 call_llm_with_tools 功能相同，但支持 token 级别的流式输出。
    
    Args:
        llm: LLM 实例
        messages: 消息列表
        tools: 可用工具列表
        max_iterations: 最大迭代次数
    
    Yields:
        事件字典，格式：
        - {"type": "token", "content": "..."} - token 输出
        - {"type": "tool_call", "name": "...", "args": {...}} - 工具调用
        - {"type": "tool_result", "name": "...", "result": "..."} - 工具结果
        - {"type": "complete", "content": "..."} - 完成，包含完整响应
    
    Example:
        async for event in stream_llm_with_tools(llm, messages, tools):
            if event["type"] == "token":
                print(event["content"], end="", flush=True)
            elif event["type"] == "complete":
                result = parse_json_response(event["content"], SemanticQuery)
    """
    llm_with_tools = llm.bind_tools(tools)
    langchain_messages = convert_messages(messages)
    tool_map = {tool.name: tool for tool in tools}
    
    for iteration in range(max_iterations):
        logger.debug(f"LLM streaming iteration {iteration + 1}/{max_iterations}")
        
        # 流式调用 LLM
        collected_content = []
        tool_calls = []
        
        async for event in llm_with_tools.astream_events(langchain_messages, version="v2"):
            event_type = event.get("event")
            
            # Token 流式输出
            if event_type == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk:
                    # 收集 content
                    if hasattr(chunk, "content") and chunk.content:
                        collected_content.append(chunk.content)
                        yield {"type": "token", "content": chunk.content}
                    
                    # 收集 tool_calls（流式累积）
                    if hasattr(chunk, "tool_call_chunks") and chunk.tool_call_chunks:
                        for tc_chunk in chunk.tool_call_chunks:
                            # 找到或创建对应的 tool_call
                            tc_index = tc_chunk.get("index", 0)
                            while len(tool_calls) <= tc_index:
                                tool_calls.append({"name": "", "args": "", "id": ""})
                            
                            if tc_chunk.get("name"):
                                tool_calls[tc_index]["name"] = tc_chunk["name"]
                            if tc_chunk.get("id"):
                                tool_calls[tc_index]["id"] = tc_chunk["id"]
                            if tc_chunk.get("args"):
                                tool_calls[tc_index]["args"] += tc_chunk["args"]
        
        full_content = "".join(collected_content)
        
        # 构建 AIMessage 并添加到历史
        import json as json_module
        parsed_tool_calls = []
        for tc in tool_calls:
            if tc["name"] and tc["id"]:
                try:
                    args = json_module.loads(tc["args"]) if tc["args"] else {}
                except json_module.JSONDecodeError:
                    args = {}
                parsed_tool_calls.append({
                    "name": tc["name"],
                    "args": args,
                    "id": tc["id"],
                })
        
        ai_message = AIMessage(content=full_content, tool_calls=parsed_tool_calls)
        langchain_messages.append(ai_message)
        
        # 没有工具调用，完成
        if not parsed_tool_calls:
            logger.debug("No tool calls, streaming complete")
            yield {"type": "complete", "content": full_content}
            return
        
        # 处理工具调用
        for tool_call in parsed_tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_id = tool_call["id"]
            
            yield {"type": "tool_call", "name": tool_name, "args": tool_args}
            logger.info(f"Tool call: {tool_name}({tool_args})")
            
            tool = tool_map.get(tool_name)
            if tool is None:
                tool_result = f"Error: Tool '{tool_name}' not found"
                logger.warning(tool_result)
            else:
                try:
                    if hasattr(tool, 'ainvoke'):
                        tool_result = await tool.ainvoke(tool_args)
                    else:
                        tool_result = tool.invoke(tool_args)
                except Exception as e:
                    logger.error(f"Tool {tool_name} failed: {e}")
                    tool_result = f"Error: {str(e)}"
            
            yield {"type": "tool_result", "name": tool_name, "result": str(tool_result)[:200]}
            langchain_messages.append(
                ToolMessage(content=str(tool_result), tool_call_id=tool_id)
            )
    
    # 达到最大迭代次数
    logger.warning(f"Max iterations ({max_iterations}) reached")
    for msg in reversed(langchain_messages):
        if hasattr(msg, 'content') and msg.content:
            yield {"type": "complete", "content": msg.content}
            return
    
    yield {"type": "complete", "content": ""}


# ═══════════════════════════════════════════════════════════════════════════
# 流式输出
# ═══════════════════════════════════════════════════════════════════════════

# 流式输出回调类型
from typing import Callable, Union, AsyncIterator
from typing_extensions import Protocol


class StreamCallback(Protocol):
    """流式输出回调协议"""
    def __call__(self, token: str) -> None: ...


class AsyncStreamCallback(Protocol):
    """异步流式输出回调协议"""
    async def __call__(self, token: str) -> None: ...


StreamCallbackType = Union[StreamCallback, AsyncStreamCallback, None]


async def stream_llm_call(
    llm: BaseChatModel,
    messages: List[Dict[str, str]],
    print_output: bool = True,
    on_token: StreamCallbackType = None,
) -> str:
    """
    流式调用 LLM（无工具）
    
    适用于不需要工具调用的场景，如维度层级推断。
    支持回调函数实时接收 token。
    
    Args:
        llm: LLM 实例
        messages: 消息列表
        print_output: 是否打印流式输出到控制台
        on_token: 可选的回调函数，每个 token 生成时调用
                  支持同步或异步回调: (token: str) -> None
    
    Returns:
        完整的响应内容
    
    Example:
        # 基础用法
        response = await stream_llm_call(llm, messages)
        
        # 带回调
        tokens = []
        response = await stream_llm_call(
            llm, messages, 
            on_token=lambda t: tokens.append(t)
        )
        
        # 异步回调（如 WebSocket 推送）
        async def send_to_ws(token):
            await websocket.send(token)
        response = await stream_llm_call(llm, messages, on_token=send_to_ws)
    """
    langchain_messages = convert_messages(messages)
    
    collected_content = []
    token_count = 0
    
    if print_output:
        print("  🔄 [流式输出] ", end="", flush=True)
    
    import asyncio
    
    async for event in llm.astream_events(langchain_messages, version="v2"):
        event_type = event.get("event")
        if event_type == "on_chat_model_stream":
            chunk = event.get("data", {}).get("chunk")
            if chunk and hasattr(chunk, "content"):
                token = chunk.content
                if token:
                    if print_output:
                        print(token, end="", flush=True)
                    collected_content.append(token)
                    token_count += 1
                    
                    # 调用回调
                    if on_token:
                        if asyncio.iscoroutinefunction(on_token):
                            await on_token(token)
                        else:
                            on_token(token)
    
    if print_output:
        print(f" ✓ ({token_count} tokens)")
    
    full_content = "".join(collected_content)
    if not full_content.strip():
        raise ValueError("LLM 返回空内容")
    
    return full_content


async def stream_llm_call_generator(
    llm: BaseChatModel,
    messages: List[Dict[str, str]],
) -> AsyncIterator[str]:
    """
    流式调用 LLM，返回 async generator
    
    适用于需要逐 token 处理的场景，如 SSE/WebSocket 推送。
    
    Args:
        llm: LLM 实例
        messages: 消息列表
    
    Yields:
        每个生成的 token
    
    Example:
        async for token in stream_llm_call_generator(llm, messages):
            await websocket.send(token)
            
        # 或收集完整响应
        tokens = [token async for token in stream_llm_call_generator(llm, messages)]
        full_response = "".join(tokens)
    """
    langchain_messages = convert_messages(messages)
    
    async for event in llm.astream_events(langchain_messages, version="v2"):
        event_type = event.get("event")
        if event_type == "on_chat_model_stream":
            chunk = event.get("data", {}).get("chunk")
            if chunk and hasattr(chunk, "content"):
                token = chunk.content
                if token:
                    yield token


# 带批次标识的流式 token
from dataclasses import dataclass


@dataclass
class StreamToken:
    """
    带批次标识的流式 token
    
    用于并行流式输出场景，区分不同批次的输出。
    """
    batch_id: int           # 批次 ID（从 0 开始）
    token: str              # token 内容
    is_complete: bool = False  # 该批次是否完成


# 带批次标识的回调类型
class BatchStreamCallback(Protocol):
    """带批次标识的流式输出回调协议"""
    def __call__(self, batch_id: int, token: str) -> None: ...


class AsyncBatchStreamCallback(Protocol):
    """异步带批次标识的流式输出回调协议"""
    async def __call__(self, batch_id: int, token: str) -> None: ...


BatchStreamCallbackType = Union[BatchStreamCallback, AsyncBatchStreamCallback, None]


async def stream_llm_call_with_batch_id(
    llm: BaseChatModel,
    messages: List[Dict[str, str]],
    batch_id: int,
    on_token: BatchStreamCallbackType = None,
) -> str:
    """
    带批次标识的流式调用 LLM
    
    用于并行流式输出场景，每个 token 都带有批次 ID。
    
    Args:
        llm: LLM 实例
        messages: 消息列表
        batch_id: 批次 ID
        on_token: 回调函数 (batch_id: int, token: str) -> None
    
    Returns:
        完整的响应内容
    """
    import asyncio
    
    langchain_messages = convert_messages(messages)
    collected_content = []
    
    async for event in llm.astream_events(langchain_messages, version="v2"):
        event_type = event.get("event")
        if event_type == "on_chat_model_stream":
            chunk = event.get("data", {}).get("chunk")
            if chunk and hasattr(chunk, "content"):
                token = chunk.content
                if token:
                    collected_content.append(token)
                    if on_token:
                        if asyncio.iscoroutinefunction(on_token):
                            await on_token(batch_id, token)
                        else:
                            on_token(batch_id, token)
    
    return "".join(collected_content)


async def invoke_llm(
    llm: BaseChatModel,
    messages: List[Dict[str, str]],
) -> str:
    """
    简单调用 LLM（无工具、无流式）
    
    Args:
        llm: LLM 实例
        messages: 消息列表
    
    Returns:
        响应内容
    """
    langchain_messages = convert_messages(messages)
    response = await llm.ainvoke(langchain_messages)
    return response.content


# ═══════════════════════════════════════════════════════════════════════════
# JSON 解析
# ═══════════════════════════════════════════════════════════════════════════

def clean_json_output(content: str) -> str:
    """
    清理 LLM 输出的 JSON
    
    处理常见问题：
    - Markdown 代码块
    - 额外的空白
    - 尾随逗号
    
    Args:
        content: LLM 输出内容
    
    Returns:
        清理后的 JSON 字符串
    """
    # Step 1: 移除 markdown 代码块
    content = re.sub(r'```json\s*', '', content)
    content = re.sub(r'```\s*', '', content)
    
    # Step 2: 提取 JSON（找第一个 { 和最后一个 }）
    start = content.find('{')
    end = content.rfind('}')
    if start != -1 and end != -1 and end > start:
        content = content[start:end+1]
    
    # Step 3: 尝试直接解析
    try:
        json.loads(content)
        return content.strip()
    except json.JSONDecodeError:
        pass
    
    # Step 4: 尝试使用 json-repair 库
    try:
        from json_repair import repair_json
        repaired = repair_json(content)
        json.loads(repaired)
        logger.debug("JSON 修复成功")
        return repaired
    except ImportError:
        logger.debug("json-repair 库未安装，使用基础修复")
    except Exception as e:
        logger.debug(f"json-repair 修复失败: {e}")
    
    # Step 5: 基础修复
    # 移除尾随逗号
    content = re.sub(r',(\s*[}\]])', r'\1', content)
    # 修复引号
    content = content.replace('"', '"').replace('"', '"')
    content = content.replace(''', "'").replace(''', "'")
    
    return content.strip()


def parse_json_response(
    content: str, 
    output_model: Type[T],
) -> T:
    """
    解析 LLM 响应为 Pydantic 模型
    
    Args:
        content: LLM 响应内容
        output_model: 目标 Pydantic 模型类
    
    Returns:
        解析后的模型实例
    
    Raises:
        ValueError: 解析失败
    
    Example:
        response = await stream_llm_call(llm, messages)
        result = parse_json_response(response, DimensionHierarchyResult)
    """
    cleaned = clean_json_output(content)
    
    try:
        return output_model.model_validate_json(cleaned)
    except Exception as e:
        logger.error(f"JSON 解析失败: {e}")
        logger.error(f"内容: {cleaned[:500]}...")
        raise ValueError(f"无法解析 LLM 响应: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# 导出
# ═══════════════════════════════════════════════════════════════════════════

__all__ = [
    # LLM 获取
    "get_llm",
    "get_agent_temperature",
    "AGENT_TEMPERATURE_CONFIG",
    
    # 工具调用
    "call_llm_with_tools",
    "stream_llm_with_tools",
    "convert_messages",
    
    # 流式输出
    "stream_llm_call",
    "stream_llm_call_generator",
    "stream_llm_call_with_batch_id",
    "StreamToken",
    "invoke_llm",
    
    # JSON 解析
    "clean_json_output",
    "parse_json_response",
]
