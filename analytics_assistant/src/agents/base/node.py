# -*- coding: utf-8 -*-
"""
Agent 基础工具模块

提供所有 Agent 节点共用的基础能力：
1. LLM 获取和配置（通过 ModelManager）
2. LLM 调用（支持流式输出和工具调用）
3. Middleware 支持
4. JSON 解析（使用 Pydantic）

设计原则：
- 基于 LangChain/LangGraph 框架，不重复造轮子
- 使用 LangChain 原生 API（astream, astream_events）
- 通过 ModelManager 统一管理 LLM
- Middleware 支持扩展能力

使用示例：

    from analytics_assistant.src.agents.base import (
        get_llm,
        call_llm,
        call_llm_with_tools,
        parse_json_response,
    )
    
    # 在 Agent 节点中使用
    async def my_agent_node(state, config):
        # 获取 LLM
        llm = get_llm(agent_name="semantic_parser")
        
        # 简单调用（流式）
        response = await call_llm(llm, messages)
        
        # 带工具调用
        response = await call_llm_with_tools(llm, messages, tools)
        
        # 解析 JSON
        result = parse_json_response(response.content, MyOutputModel)
"""
import logging
from typing import (
    Any,
    AsyncIterator,
    Awaitable,
    Callable,
    Dict,
    List,
    Optional,
    Type,
    TypeVar,
    Union,
)

from pydantic import BaseModel, ValidationError
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

# 导入 ModelManager 和配置
from ...infra.ai import get_model_manager, TaskType
from ...infra.config import get_config

logger = logging.getLogger(__name__)

T = TypeVar('T', bound=BaseModel)


# ═══════════════════════════════════════════════════════════════════════════
# Agent Temperature 配置（从 YAML 读取）
# ═══════════════════════════════════════════════════════════════════════════

def _get_agent_temperature_config() -> Dict[str, float]:
    """从 YAML 配置读取 Agent temperature 配置"""
    config = get_config()
    agents_config = config.get("agents", {})
    return agents_config.get("temperature", {
        "semantic_parser": 0.1,
        "dimension_hierarchy": 0.1,
        "field_mapper": 0.1,
        "insight": 0.4,
        "replanner": 0.2,
        "default": 0.2,
    })


def get_agent_temperature(agent_name: str) -> float:
    """获取指定 Agent 的默认 temperature"""
    temp_config = _get_agent_temperature_config()
    return temp_config.get(
        agent_name.lower(),
        temp_config.get("default", 0.2)
    )


def _get_llm_config() -> Dict[str, Any]:
    """从 YAML 配置读取 LLM 调用配置"""
    config = get_config()
    agents_config = config.get("agents", {})
    return agents_config.get("llm", {
        "max_iterations": 5,
        "request_timeout": 120,
    })


def get_llm(
    agent_name: Optional[str] = None,
    temperature: Optional[float] = None,
    enable_json_mode: bool = False,
    task_type: Optional[TaskType] = None,
    model_id: Optional[str] = None,
    **kwargs
) -> BaseChatModel:
    """
    获取 LLM 实例（Agent 层封装）
    
    支持通过 agent_name 自动选择 temperature，底层调用 ModelManager。
    
    Args:
        agent_name: Agent 名称（用于自动选择 temperature）
        temperature: 温度参数（覆盖 agent_name 配置）
        enable_json_mode: 是否启用 JSON Mode
        task_type: 任务类型（用于智能路由）
        model_id: 模型 ID（显式指定模型）
        **kwargs: 传递给 ModelManager.create_llm() 的其他参数
    
    Returns:
        配置好的 LLM 实例
    
    Examples:
        # 使用 agent 对应的 temperature
        llm = get_llm(agent_name="semantic_parser")  # temperature=0.1
        
        # 启用 JSON Mode（模型原生支持）
        llm = get_llm(agent_name="semantic_parser", enable_json_mode=True)
        
        # 使用任务类型路由
        llm = get_llm(task_type=TaskType.SEMANTIC_PARSING)
    """
    # Temperature 优先级：显式参数 > agent_name 配置
    if temperature is not None:
        _temperature = temperature
    elif agent_name:
        _temperature = get_agent_temperature(agent_name)
    else:
        _temperature = None  # 使用 ModelManager 的默认值
    
    # 获取 ModelManager 实例
    manager = get_model_manager()
    
    # 调用 ModelManager.create_llm()
    return manager.create_llm(
        model_id=model_id,
        task_type=task_type,
        temperature=_temperature,
        enable_json_mode=enable_json_mode,
        **kwargs
    )


# ═══════════════════════════════════════════════════════════════════════════
# LLM 调用（流式输出）
# ═══════════════════════════════════════════════════════════════════════════

async def call_llm(
    llm: BaseChatModel,
    messages: List[BaseMessage],
    config: Optional[Dict[str, Any]] = None,
    middleware: Optional[List[Any]] = None,
    state: Optional[Dict[str, Any]] = None,
) -> AIMessage:
    """
    调用 LLM（流式输出，无工具）
    
    使用 LangChain 原生 astream() 实现 token 级别流式输出。
    通过传递 config，LangGraph 的 astream_events 能捕获 token 事件。
    
    Args:
        llm: LLM 实例
        messages: LangChain 消息列表
        config: LangGraph RunnableConfig（用于流式事件捕获）
        middleware: 可选的 middleware 列表
        state: 可选的当前状态（用于 middleware）
    
    Returns:
        AIMessage: 完整的 LLM 响应
    
    Example:
        llm = get_llm(agent_name="semantic_parser")
        messages = [SystemMessage(content="..."), HumanMessage(content="...")]
        response = await call_llm(llm, messages)
        print(response.content)
    """
    # 如果有 middleware，使用 MiddlewareRunner
    if middleware:
        from .middleware_runner import MiddlewareRunner
        
        runner = MiddlewareRunner(middleware)
        runtime = runner.build_runtime(config)
        
        # before_model
        current_state = dict(state) if state else {}
        current_state = await runner.run_before_model(current_state, runtime)
        
        # 构建请求
        request = runner.build_model_request(
            model=llm,
            messages=messages,
            state=current_state,
            runtime=runtime,
        )
        
        # wrap_model_call
        async def base_handler(req):
            return runner.build_model_response(
                result=[await _stream_llm_internal(req.model, req.messages, config)]
            )
        
        response = await runner.wrap_model_call(request, base_handler)
        
        # after_model
        await runner.run_after_model(
            current_state, runtime,
            response=response,
            request=request,
        )
        
        return response.result[0] if response.result else AIMessage(content="")
    
    # 无 middleware，直接调用
    return await _stream_llm_internal(llm, messages, config)


async def _stream_llm_internal(
    llm: BaseChatModel,
    messages: List[BaseMessage],
    config: Optional[Dict[str, Any]] = None,
) -> AIMessage:
    """
    内部流式调用 LLM
    
    使用 astream 进行流式调用，收集所有 chunk 后合并为完整的 AIMessage。
    """
    collected_content = []
    additional_kwargs = {}
    
    # 使用 astream 进行流式调用
    # 传递 config 使 LangGraph 的 callbacks 能捕获流式事件
    async for chunk in llm.astream(messages, config=config):
        # 收集 content
        if hasattr(chunk, "content") and chunk.content:
            collected_content.append(chunk.content)
        
        # 收集 additional_kwargs（如 R1 模型的思考过程）
        if hasattr(chunk, "additional_kwargs") and chunk.additional_kwargs:
            additional_kwargs.update(chunk.additional_kwargs)
    
    # 确定最终 content
    full_content = "".join(collected_content)
    
    # R1 模型：使用解析后的答案
    if "answer" in additional_kwargs:
        final_content = additional_kwargs["answer"]
    else:
        final_content = full_content
    
    return AIMessage(
        content=final_content,
        additional_kwargs=additional_kwargs,
    )


async def stream_llm(
    llm: BaseChatModel,
    messages: List[BaseMessage],
    config: Optional[Dict[str, Any]] = None,
) -> AsyncIterator[str]:
    """
    流式调用 LLM，返回 async generator
    
    适用于需要逐 token 处理的场景，如 SSE/WebSocket 推送。
    
    Args:
        llm: LLM 实例
        messages: LangChain 消息列表
        config: LangGraph RunnableConfig
    
    Yields:
        每个生成的 token
    
    Example:
        async for token in stream_llm(llm, messages):
            await websocket.send(token)
    """
    async for chunk in llm.astream(messages, config=config):
        if hasattr(chunk, "content") and chunk.content:
            yield chunk.content


# ═══════════════════════════════════════════════════════════════════════════
# LLM 调用（带工具）
# ═══════════════════════════════════════════════════════════════════════════

async def call_llm_with_tools(
    llm: BaseChatModel,
    messages: List[BaseMessage],
    tools: List[Any],
    max_iterations: int = 5,
    config: Optional[Dict[str, Any]] = None,
    middleware: Optional[List[Any]] = None,
    state: Optional[Dict[str, Any]] = None,
) -> AIMessage:
    """
    调用 LLM 并处理工具调用
    
    使用 LangChain 原生 bind_tools() 和 astream() 实现。
    支持多轮工具调用，直到 LLM 返回最终响应。
    
    Args:
        llm: LLM 实例
        messages: LangChain 消息列表
        tools: 可用工具列表（@tool 装饰的函数）
        max_iterations: 最大迭代次数（防止无限循环）
        config: LangGraph RunnableConfig
        middleware: 可选的 middleware 列表
        state: 可选的当前状态（用于 middleware）
    
    Returns:
        AIMessage: 完整的 LLM 响应
    
    Example:
        from langchain_core.tools import tool
        
        @tool
        def search(query: str) -> str:
            '''搜索工具'''
            return f"搜索结果: {query}"
        
        response = await call_llm_with_tools(llm, messages, tools=[search])
    """
    # 如果有 middleware，使用 MiddlewareRunner
    if middleware:
        from .middleware_runner import MiddlewareRunner
        
        runner = MiddlewareRunner(middleware)
        runtime = runner.build_runtime(config)
        current_state = dict(state) if state else {}
        
        return await _call_with_tools_and_middleware(
            llm, messages, tools, max_iterations,
            config, runner, runtime, current_state
        )
    
    # 无 middleware，直接调用
    return await _call_with_tools_internal(
        llm, messages, tools, max_iterations, config
    )


async def _call_with_tools_internal(
    llm: BaseChatModel,
    messages: List[BaseMessage],
    tools: List[Any],
    max_iterations: int,
    config: Optional[Dict[str, Any]],
) -> AIMessage:
    """内部工具调用实现"""
    # 绑定工具
    llm_with_tools = llm.bind_tools(tools) if tools else llm
    
    # 构建工具映射
    tool_map = {tool.name: tool for tool in tools} if tools else {}
    
    # 复制消息列表
    current_messages = list(messages)
    
    for iteration in range(max_iterations):
        logger.debug(f"LLM 迭代 {iteration + 1}/{max_iterations}")
        
        # 流式调用
        response = await _stream_llm_with_tools_internal(
            llm_with_tools, current_messages, config
        )
        
        current_messages.append(response)
        
        # 检查是否有工具调用
        if not response.tool_calls:
            logger.debug("无工具调用，返回响应")
            return response
        
        # 处理工具调用
        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_id = tool_call["id"]
            
            logger.info(f"工具调用: {tool_name}({tool_args})")
            
            tool = tool_map.get(tool_name)
            if tool is None:
                tool_result = f"错误: 工具 '{tool_name}' 不存在"
                logger.warning(tool_result)
            else:
                try:
                    # 异步工具
                    if hasattr(tool, 'ainvoke'):
                        tool_result = await tool.ainvoke(tool_args)
                    else:
                        tool_result = tool.invoke(tool_args)
                except Exception as e:
                    logger.error(f"工具 {tool_name} 执行失败: {e}")
                    tool_result = f"错误: {str(e)}"
            
            # 添加工具结果
            current_messages.append(
                ToolMessage(content=str(tool_result), tool_call_id=tool_id)
            )
    
    # 达到最大迭代次数
    logger.warning(f"达到最大迭代次数 ({max_iterations})")
    
    # 返回最后一条 AIMessage
    for msg in reversed(current_messages):
        if isinstance(msg, AIMessage):
            return msg
    
    return AIMessage(content="")


async def _stream_llm_with_tools_internal(
    llm: BaseChatModel,
    messages: List[BaseMessage],
    config: Optional[Dict[str, Any]],
) -> AIMessage:
    """内部流式调用（带工具）"""
    collected_content = []
    tool_calls = []
    additional_kwargs = {}
    
    async for chunk in llm.astream(messages, config=config):
        # 收集 content
        if hasattr(chunk, "content") and chunk.content:
            collected_content.append(chunk.content)
        
        # 收集 additional_kwargs
        if hasattr(chunk, "additional_kwargs") and chunk.additional_kwargs:
            additional_kwargs.update(chunk.additional_kwargs)
        
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
    
    # 解析 tool_calls 的 args
    import json
    parsed_tool_calls = []
    for tc in tool_calls:
        if not (tc.get("name") and tc.get("id")):
            continue
        
        args = {}
        if tc.get("args"):
            try:
                args = json.loads(tc["args"])
            except json.JSONDecodeError as e:
                logger.warning(f"工具参数解析失败: {e}")
        
        parsed_tool_calls.append({
            "name": tc["name"],
            "args": args,
            "id": tc["id"],
        })
    
    # 确定最终 content
    full_content = "".join(collected_content)
    if "answer" in additional_kwargs:
        final_content = additional_kwargs["answer"]
    else:
        final_content = full_content
    
    return AIMessage(
        content=final_content,
        tool_calls=parsed_tool_calls,
        additional_kwargs=additional_kwargs,
    )


async def _call_with_tools_and_middleware(
    llm: BaseChatModel,
    messages: List[BaseMessage],
    tools: List[Any],
    max_iterations: int,
    config: Optional[Dict[str, Any]],
    runner: Any,  # MiddlewareRunner
    runtime: Any,  # Runtime
    state: Dict[str, Any],
) -> AIMessage:
    """带 middleware 的工具调用实现"""
    # 绑定工具
    llm_with_tools = llm.bind_tools(tools) if tools else llm
    
    # 构建工具映射
    tool_map = {tool.name: tool for tool in tools} if tools else {}
    
    # 复制消息列表
    current_messages = list(messages)
    current_state = state
    
    for iteration in range(max_iterations):
        logger.debug(f"LLM 迭代 {iteration + 1}/{max_iterations} (with middleware)")
        
        # before_model
        current_state = await runner.run_before_model(current_state, runtime)
        
        # 构建请求
        request = runner.build_model_request(
            model=llm_with_tools,
            messages=current_messages,
            tools=tools,
            state=current_state,
            runtime=runtime,
        )
        
        # wrap_model_call
        async def base_handler(req):
            return runner.build_model_response(
                result=[await _stream_llm_with_tools_internal(
                    req.model, req.messages, config
                )]
            )
        
        model_response = await runner.wrap_model_call(request, base_handler)
        
        # after_model
        current_state = await runner.run_after_model(
            current_state, runtime,
            response=model_response,
            request=request,
        )
        
        # 获取响应
        if not model_response.result:
            raise ValueError("LLM 返回空响应")
        
        response = model_response.result[0]
        current_messages.append(response)
        
        # 检查是否有工具调用
        if not response.tool_calls:
            logger.debug("无工具调用，返回响应 (with middleware)")
            return response
        
        # 处理工具调用（通过 middleware）
        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_id = tool_call["id"]
            
            logger.info(f"工具调用: {tool_name}({tool_args})")
            
            tool = tool_map.get(tool_name)
            if tool is None:
                tool_result = f"错误: 工具 '{tool_name}' 不存在"
                logger.warning(tool_result)
            else:
                # 通过 middleware 调用工具
                tool_message = await runner.call_tool_with_middleware(
                    tool=tool,
                    tool_call=tool_call,
                    state=current_state,
                    runtime=runtime,
                )
                tool_result = tool_message.content if hasattr(tool_message, 'content') else str(tool_message)
            
            current_messages.append(
                ToolMessage(content=str(tool_result), tool_call_id=tool_id)
            )
    
    # 达到最大迭代次数
    logger.warning(f"达到最大迭代次数 ({max_iterations}) (with middleware)")
    
    for msg in reversed(current_messages):
        if isinstance(msg, AIMessage):
            return msg
    
    return AIMessage(content="")


# ═══════════════════════════════════════════════════════════════════════════
# JSON 解析
# ═══════════════════════════════════════════════════════════════════════════

class JSONParseError(Exception):
    """JSON 解析错误"""
    
    def __init__(self, message: str, content_preview: str):
        self.message = message
        self.content_preview = content_preview
        super().__init__(f"{message} | preview={content_preview[:100]}...")


def parse_json_response(
    content: str,
    output_model: Type[T],
) -> T:
    """
    解析 JSON 响应
    
    使用 Pydantic 的 model_validate_json() 直接解析。
    不做 JSON 修复，依赖模型的 json_mode 参数保证输出格式。
    
    Args:
        content: LLM 响应内容
        output_model: 目标 Pydantic 模型类
    
    Returns:
        解析后的模型实例
    
    Raises:
        JSONParseError: JSON 解析失败
        ValidationError: Pydantic 校验失败
    
    Example:
        response = await call_llm(llm, messages)
        result = parse_json_response(response.content, MyOutputModel)
    """
    import re
    
    # 清理 markdown 代码块
    cleaned = re.sub(r'```json\s*', '', content)
    cleaned = re.sub(r'```\s*', '', cleaned)
    cleaned = cleaned.strip()
    
    # 提取 JSON（找第一个 { 和匹配的 }）
    start = cleaned.find('{')
    if start != -1:
        depth = 0
        end = -1
        in_string = False
        escape = False
        
        for i, char in enumerate(cleaned[start:], start):
            if escape:
                escape = False
                continue
            if char == '\\':
                escape = True
                continue
            if char == '"' and not escape:
                in_string = not in_string
                continue
            if in_string:
                continue
            if char == '{':
                depth += 1
            elif char == '}':
                depth -= 1
                if depth == 0:
                    end = i
                    break
        
        if end != -1:
            cleaned = cleaned[start:end+1]
    
    # 使用 Pydantic 解析
    try:
        return output_model.model_validate_json(cleaned)
    except ValidationError:
        raise
    except Exception as e:
        raise JSONParseError(
            message=f"JSON 解析失败: {str(e)}",
            content_preview=content[:200],
        )


# ═══════════════════════════════════════════════════════════════════════════
# 导出
# ═══════════════════════════════════════════════════════════════════════════

__all__ = [
    # LLM 获取
    "get_llm",
    "get_agent_temperature",
    "TaskType",
    
    # LLM 调用
    "call_llm",
    "stream_llm",
    "call_llm_with_tools",
    
    # JSON 解析
    "parse_json_response",
    "JSONParseError",
]
