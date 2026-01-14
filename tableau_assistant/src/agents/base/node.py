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
# Tool Calls 解析（Requirements 0.8）
# ═══════════════════════════════════════════════════════════════════════════

from dataclasses import dataclass as dc_dataclass
from typing import Optional as OptionalType


@dc_dataclass
class ParsedToolCall:
    """解析后的 tool_call 数据类
    
    Attributes:
        name: 工具名称
        args: 解析后的参数字典
        id: tool_call ID
        parse_error: 解析错误信息（如果解析失败）
    """
    name: str
    args: dict
    id: str
    parse_error: OptionalType[str] = None


def _parse_tool_calls(
    tool_calls: list[dict],
    config: OptionalType[dict] = None,
) -> list[ParsedToolCall]:
    """解析 tool_calls 的 args（从字符串到字典）
    
    实现三层防护：
    1. 直接 JSON 解析
    2. json_repair 修复
    3. 记录错误并返回空 args
    
    Args:
        tool_calls: 原始 tool_calls 列表，每个元素包含 name, args (str), id
        config: RunnableConfig，用于获取 metrics
    
    Returns:
        解析后的 ParsedToolCall 列表
    
    Requirements: 0.8 - 流式 tool_calls 解析错误显式处理
    """
    import json as json_module
    
    # 获取 metrics（如果可用）
    metrics = None
    if config:
        configurable = config.get("configurable", {})
        metrics = configurable.get("metrics")
    
    parsed_tool_calls = []
    for tc in tool_calls:
        if not (tc.get("name") and tc.get("id")):
            continue
        
        raw_args = tc.get("args", "")
        args = {}
        parse_error = None
        
        if not raw_args:
            # 空参数，直接使用空字典
            pass
        else:
            # 第一层：尝试直接 JSON 解析
            try:
                args = json_module.loads(raw_args)
            except json_module.JSONDecodeError as e:
                # 记录警告日志
                truncated_args = raw_args[:200] + "..." if len(raw_args) > 200 else raw_args
                logger.warning(
                    f"Tool call args parse failed for '{tc['name']}': {e}, "
                    f"raw args (truncated): {truncated_args}"
                )
                if metrics:
                    metrics.tool_args_parse_failure_count += 1
                
                # 第二层：尝试 json_repair 修复
                try:
                    from json_repair import repair_json
                    repaired = repair_json(raw_args)
                    args = json_module.loads(repaired)
                    logger.info(f"Tool call args repaired successfully for '{tc['name']}'")
                    if metrics:
                        metrics.tool_args_repair_success_count += 1
                except Exception as repair_error:
                    # 第三层：修复失败，记录错误
                    logger.warning(
                        f"Tool call args repair failed for '{tc['name']}': {repair_error}, "
                        f"raw args (truncated): {truncated_args}"
                    )
                    parse_error = f"JSON parse failed: {str(e)[:100]}"
                    args = {}
        
        parsed_tool_calls.append(ParsedToolCall(
            name=tc["name"],
            args=args,
            id=tc["id"],
            parse_error=parse_error,
        ))
    
    return parsed_tool_calls


# ═══════════════════════════════════════════════════════════════════════════
# LLM 空响应异常（Requirements 0.9）
# ═══════════════════════════════════════════════════════════════════════════

class LLMEmptyResponseError(Exception):
    """LLM 返回空响应时抛出的异常
    
    包含请求上下文信息，便于问题定位。
    
    Attributes:
        model: 模型名称或实例
        message_count: 请求消息数量
        iteration: 当前迭代次数（如果在工具调用循环中）
    
    Requirements: 0.9 - LLM 空响应显式处理
    """
    
    def __init__(
        self,
        model: Any,
        message_count: int,
        iteration: OptionalType[int] = None,
    ):
        self.model = model
        self.message_count = message_count
        self.iteration = iteration
        
        # 构建错误消息
        model_name = getattr(model, "model_name", str(model))
        msg = f"LLM returned empty response for model '{model_name}', messages={message_count}"
        if iteration is not None:
            msg += f", iteration={iteration}"
        
        super().__init__(msg)


# ═══════════════════════════════════════════════════════════════════════════
# LLM 获取（从 infra/ai 导入）
# ═══════════════════════════════════════════════════════════════════════════

from tableau_assistant.src.infra.ai import get_llm as _get_llm
from tableau_assistant.src.infra.config import settings


# ═══════════════════════════════════════════════════════════════════════════
# LLM 超时配置
# ═══════════════════════════════════════════════════════════════════════════

def get_llm_timeout() -> int:
    """获取 LLM 请求超时时间（秒），从配置读取"""
    return settings.llm_request_timeout


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
    enable_json_mode: bool = False,
    **kwargs
) -> BaseChatModel:
    """
    获取 LLM 实例（Agent 层封装）
    
    这是 Agent 层的便捷函数，支持通过 agent_name 自动选择 temperature。
    底层调用 model_manager.get_llm。
    
    Args:
        agent_name: Agent 名称（可选，用于自动选择 temperature）
        temperature: 温度参数（可选，覆盖 agent_name 配置）
        enable_json_mode: 是否启用 JSON Mode（Requirements 0.7）
        **kwargs: 传递给 model_manager.get_llm 的其他参数
    
    Returns:
        配置好的 LLM 实例
    
    Examples:
        # 使用 agent 对应的 temperature
        llm = get_llm(agent_name="semantic_parser")  # temperature=0.1
        
        # 启用 JSON Mode（Requirements 0.7）
        llm = get_llm(agent_name="semantic_parser", enable_json_mode=True)
        
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
    
    return _get_llm(temperature=_temperature, enable_json_mode=enable_json_mode, **kwargs)


# ═══════════════════════════════════════════════════════════════════════════
# 工具调用处理
# ═══════════════════════════════════════════════════════════════════════════

def convert_messages(messages: List) -> List:
    """
    将字典格式的消息转换为 LangChain 消息对象
    
    支持两种输入格式：
    1. 字典格式: [{"role": "system", "content": "..."}, ...]
    2. LangChain 消息对象: [HumanMessage(...), AIMessage(...), ...]
    
    Args:
        messages: 消息列表（字典或 LangChain 消息对象）
    
    Returns:
        LangChain 消息对象列表
    """
    from langchain_core.messages import BaseMessage
    
    langchain_messages = []
    for msg in messages:
        # 如果已经是 LangChain 消息对象，直接添加
        if isinstance(msg, BaseMessage):
            langchain_messages.append(msg)
            continue
        
        # 字典格式转换
        if isinstance(msg, dict):
            role = msg.get("role", "")
            content = msg.get("content", "")
            
            if role == "system":
                langchain_messages.append(SystemMessage(content=content))
            elif role == "user":
                langchain_messages.append(HumanMessage(content=content))
            elif role == "assistant":
                langchain_messages.append(AIMessage(content=content))
            elif role == "tool":
                # 处理工具消息
                tool_call_id = msg.get("tool_call_id", "")
                langchain_messages.append(ToolMessage(content=content, tool_call_id=tool_call_id))
            else:
                # 未知角色，默认作为 HumanMessage
                logger.warning(f"Unknown message role: {role}, treating as HumanMessage")
                langchain_messages.append(HumanMessage(content=content))
        else:
            logger.warning(f"Unknown message type: {type(msg)}, skipping")
    
    return langchain_messages


def _maybe_record_json_mode_fallback(llm: Any, config: Optional[Dict[str, Any]]) -> None:
    """如当前 LLM 处于 JSON Mode 降级状态，则累加 metrics.json_mode_fallback_count。

    设计点：
    - infra 层仅打标（见 model_manager.py），不直接依赖 workflow/state
    - Agent 调用侧能拿到 RunnableConfig，从而能安全地更新贯通 metrics
    """
    if not config:
        return
    configurable = config.get("configurable", {})
    metrics = configurable.get("metrics")
    if metrics is None:
        return
    if getattr(llm, "_json_mode_fallback", False):
        metrics.json_mode_fallback_count += 1
        provider = getattr(llm, "_json_mode_fallback_provider", None) or getattr(llm, "_provider", None)
        if provider and hasattr(metrics, "json_mode_fallback_by_provider"):
            metrics.json_mode_fallback_by_provider[provider] = (
                metrics.json_mode_fallback_by_provider.get(provider, 0) + 1
            )




async def _call_llm_with_tools_and_middleware(
    llm: BaseChatModel,
    messages: List[Dict[str, str]],
    tools: List[Any],
    max_iterations: int,
    streaming: bool,
    middleware: List[Any],
    state: Dict[str, Any],
    config: Optional[Dict[str, Any]],
) -> AIMessage:
    """
    带 middleware 支持的 LLM 调用（内部函数）
    
    执行顺序：
    1. before_model hooks
    2. wrap_model_call chain (包含实际 LLM 调用)
    3. after_model hooks
    4. 如果有 tool_calls，执行 wrap_tool_call chain
    5. 循环直到没有 tool_calls 或达到 max_iterations
    
    Returns:
        AIMessage: 完整的 LLM 响应消息
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
    tool_map = {tool.name: tool for tool in tools} if tools else {}

    # JSON Mode 降级计数（Requirements 0.7）
    # middleware 场景下 model 可能被 wrap_model_call 替换/包装；这里按“每个实际 model 实例”计 1 次，避免工具迭代重复累加。
    recorded_model_ids = set()
    
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

            # JSON Mode 降级计数（Requirements 0.7）
            _model_id = id(_llm)
            if _model_id not in recorded_model_ids:
                _maybe_record_json_mode_fallback(_llm, config)
                recorded_model_ids.add(_model_id)
            
            # 绑定工具（如果有的话）

            if request.tools:
                _llm = _llm.bind_tools(request.tools)
            
            # 调用 LLM
            # 传递 config 以便 LangGraph 的 callbacks 能捕获流式事件
            if streaming:
                response = await _stream_llm_call_internal(_llm, _msgs, config=config)
            else:
                response = await _llm.ainvoke(_msgs, config=config)
            
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
        
        # 获取 LLM 响应 - Requirements 0.9
        if not model_response.result:
            # 获取 metrics（如果可用）
            metrics = None
            if config:
                configurable = config.get("configurable", {})
                metrics = configurable.get("metrics")
            
            # 记录指标
            if metrics:
                metrics.llm_empty_response_count += 1
            
            # 记录错误日志
            model_name = getattr(llm, "model_name", str(llm))
            logger.error(
                f"LLM returned empty response, model={model_name}, "
                f"messages={len(langchain_messages)}, iteration={iteration + 1}"
            )
            
            # 抛出明确异常
            raise LLMEmptyResponseError(
                model=llm,
                message_count=len(langchain_messages),
                iteration=iteration + 1,
            )
        
        response = model_response.result[0]
        langchain_messages.append(response)
        
        # 检查是否有工具调用
        if not response.tool_calls:
            logger.debug("No tool calls, returning response (with middleware)")
            return response
        
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
        if isinstance(msg, AIMessage):
            return msg
    
    return AIMessage(content="")


async def call_llm_with_tools(
    llm: BaseChatModel,
    messages: List[Dict[str, str]],
    tools: List[Any],
    max_iterations: int = 5,
    streaming: bool = True,
    timeout: Optional[int] = None,
    # Middleware 支持参数
    middleware: Optional[List[Any]] = None,
    state: Optional[Dict[str, Any]] = None,
    config: Optional[Dict[str, Any]] = None,
) -> AIMessage:
    """
    调用 LLM 并处理工具调用，返回完整的 AIMessage
    
    这是 Agent 节点的核心函数，处理 LLM 与工具的交互循环。
    默认使用流式调用，以便 LangGraph 的 astream_events 能捕获 token 事件。
    
    返回完整的 AIMessage，包含：
    - content: 响应内容
    - additional_kwargs: 额外信息（如 R1 模型的思考过程 "thinking"）
    - tool_calls: 工具调用信息
    
    Args:
        llm: LLM 实例
        messages: 消息列表 [{"role": "system", "content": "..."}, ...]
        tools: 可用工具列表（@tool 装饰的函数）
        max_iterations: 最大迭代次数（防止无限循环）
        streaming: 是否使用流式调用（默认 True，支持 token 级别流式输出）
        timeout: 请求超时时间（秒），默认从配置读取 llm_request_timeout
        middleware: 可选的 middleware 列表（AgentMiddleware 实例）
        state: 可选的当前状态（用于 middleware）
        config: 可选的 LangGraph RunnableConfig（用于 middleware）
    
    Returns:
        AIMessage: 完整的 LLM 响应消息
        - response.content: 响应内容（字符串）
        - response.additional_kwargs.get("thinking"): R1 模型的思考过程
    
    Example:
        llm = get_llm(agent_name="semantic_parser")
        messages = MY_PROMPT.format_messages(question="各省份销售额")
        
        response = await call_llm_with_tools(llm, messages, tools=[])
        
        # 获取响应内容
        content = response.content
        result = parse_json_response(content, SemanticQuery)
        
        # 获取思考过程（R1 模型）
        thinking = response.additional_kwargs.get("thinking", "")
    """
    import asyncio
    
    # 获取超时配置
    request_timeout = timeout if timeout is not None else get_llm_timeout()
    
    # 如果提供了 middleware，使用 MiddlewareRunner
    if middleware:
        return await asyncio.wait_for(
            _call_llm_with_tools_and_middleware(
                llm=llm,
                messages=messages,
                tools=tools,
                max_iterations=max_iterations,
                streaming=streaming,
                middleware=middleware,
                state=state or {},
                config=config,
            ),
            timeout=request_timeout
        )
    
    # 绑定工具到 LLM（如果有工具的话）
    llm_with_tools = llm.bind_tools(tools) if tools else llm
    
    # 转换消息格式
    langchain_messages = convert_messages(messages)
    
    # 构建工具映射（用于快速查找）
    tool_map = {tool.name: tool for tool in tools} if tools else {}

    # JSON Mode 降级计数（Requirements 0.7）
    # 这里按“每次 call_llm_with_tools 调用”计 1 次，避免工具迭代导致重复累加。
    _maybe_record_json_mode_fallback(llm, config)
    
    # 迭代处理工具调用
    for iteration in range(max_iterations):
        logger.debug(f"LLM iteration {iteration + 1}/{max_iterations}")

        if streaming:
            # 流式调用 - 支持 token 级别输出
            # 传递 config 以便 LangGraph 的 callbacks 能捕获流式事件
            response = await asyncio.wait_for(
                _stream_llm_call_internal(llm_with_tools, langchain_messages, config=config),
                timeout=request_timeout
            )
        else:
            # 非流式调用
            response = await asyncio.wait_for(
                llm_with_tools.ainvoke(langchain_messages, config=config),
                timeout=request_timeout
            )


        
        langchain_messages.append(response)
        
        # 检查是否有工具调用
        if not response.tool_calls:
            # 没有工具调用，返回最终响应
            logger.debug("No tool calls, returning response")
            return response
        
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
    
    # 返回最后一条 AIMessage
    for msg in reversed(langchain_messages):
        if isinstance(msg, AIMessage):
            return msg
    
    return AIMessage(content="")


async def _stream_llm_call_internal(
    llm: BaseChatModel,
    messages: List,
    config: Optional[Dict[str, Any]] = None,
) -> AIMessage:
    """
    内部流式调用 LLM，返回完整的 AIMessage
    
    使用 astream 进行流式调用，收集所有 chunk 后合并为完整的 AIMessage。
    通过传递 config 参数，LangGraph 的 astream_events 能捕获 token 事件。
    
    对于 R1 模型：
    - 流式输出包含思考过程和最终答案
    - 最后一个 chunk 的 additional_kwargs 包含解析后的 thinking 和 raw_content
    - 返回的 content 应该是最终答案（不含思考过程）
    
    Args:
        llm: LLM 实例（可能已绑定工具）
        messages: LangChain 消息列表
        config: LangGraph RunnableConfig（包含 callbacks，用于流式事件捕获）
    
    Returns:
        完整的 AIMessage（包含 content、tool_calls 和 additional_kwargs）
    """
    collected_content = []
    tool_calls = []
    additional_kwargs = {}
    
    # 使用 astream 进行流式调用
    # 关键：传递 config 参数，使 LangGraph 的 callbacks 能捕获流式事件
    async for chunk in llm.astream(messages, config=config):
        # 收集 content（同时 LangGraph 会捕获这些 chunk 作为事件）
        if hasattr(chunk, "content") and chunk.content:
            collected_content.append(chunk.content)
        
        # 收集 additional_kwargs（R1 模型的思考过程在最后一个 chunk）
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
    
    # 解析 tool_calls 的 args（从字符串到字典）- Requirements 0.8
    parsed_tool_call_objs = _parse_tool_calls(tool_calls, config)
    parsed_tool_calls = [
        {
            "name": tc.name,
            "args": tc.args,
            "id": tc.id,
            **({"parse_error": tc.parse_error} if tc.parse_error else {}),
        }
        for tc in parsed_tool_call_objs
    ]
    
    # 确定最终的 content
    # 对于 R1 模型，additional_kwargs 中有 answer 字段，直接使用
    # 对于其他模型，使用收集的 content
    full_content = "".join(collected_content)
    
    if "answer" in additional_kwargs:
        # R1 模型：使用解析后的答案
        final_content = additional_kwargs["answer"]
    else:
        final_content = full_content
    
    return AIMessage(
        content=final_content,
        tool_calls=parsed_tool_calls,
        additional_kwargs=additional_kwargs,
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
        
        # 构建 AIMessage 并添加到历史 - Requirements 0.8
        # 注意：stream_llm_with_tools 没有 config 参数，无法传递 metrics
        parsed_tool_call_objs = _parse_tool_calls(tool_calls, config=None)
        parsed_tool_calls = [
            {
                "name": tc.name,
                "args": tc.args,
                "id": tc.id,
                **({"parse_error": tc.parse_error} if tc.parse_error else {}),
            }
            for tc in parsed_tool_call_objs
        ]
        
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

class JSONParseError(Exception):
    """JSON 解析错误 - 结构化异常
    
    用于提供详细的错误信息，便于调试和日志记录。
    """
    
    def __init__(
        self,
        message: str,
        content_preview: str,
        error_type: str,
        error_position: int | None = None,
        original_error: Exception | None = None,
    ):
        self.message = message
        self.content_preview = content_preview
        self.error_type = error_type
        self.error_position = error_position
        self.original_error = original_error
        super().__init__(message)
    
    def __str__(self) -> str:
        parts = [self.message]
        if self.error_position is not None:
            parts.append(f"position={self.error_position}")
        parts.append(f"preview={self.content_preview[:100]}...")
        return " | ".join(parts)


def clean_json_output(content: str) -> str:
    """清理 LLM 输出的 JSON（不做 json_repair）。

    说明：
    - 该函数只做“提取/清洗”，不做修复尝试。
    - 修复（包括 json_repair 与基础修复）统一在 parse_json_response() 中完成，
      以保证 direct vs repair 指标口径清晰（Requirements 0.7）。

    处理常见问题：
    - Markdown 代码块
    - 额外的空白
    - 尾随字符（trailing characters）
    - 多个 JSON 对象
    """

    # Step 1: 移除 markdown 代码块
    content = re.sub(r'```json\s*', '', content)
    content = re.sub(r'```\s*', '', content)
    
    # Step 2: 提取 JSON（找第一个 { 和匹配的 }）
    # 使用括号匹配而不是简单的 rfind，处理嵌套情况
    start = content.find('{')
    if start != -1:
        depth = 0
        end = -1
        in_string = False
        escape = False
        
        for i, char in enumerate(content[start:], start):
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
            content = content[start:end+1]
    
    # Step 3: 尝试直接解析
    try:
        json.loads(content)
        return content.strip()
    except json.JSONDecodeError:
        pass
    
    return content.strip()



def parse_json_response(
    content: str, 
    output_model: Type[T],
    repair_enabled: bool = True,
    metrics: Optional[Any] = None,
    provider: Optional[str] = None,
) -> T:

    """解析 JSON 响应 - 三层防护（修正版）
    
    三层防护逻辑（Requirements 0.7）：
    1. 第一层：直接 json.loads() 解析（捕获 json.JSONDecodeError）
    2. 第二层：json_repair 修复（捕获修复后的 json.JSONDecodeError）
    3. 第三层：Pydantic 校验（捕获 ValidationError）
    
    关键修正（GPT-5.2 审查）：
    - Pydantic v2 的 model_validate_json() 对无效 JSON 抛出 ValidationError（不是 JSONDecodeError）
    - 因此必须先用 json.loads() 验证 JSON 格式，再用 Pydantic 校验 schema
    - 这样才能正确区分"JSON 格式错误"和"schema 不匹配"
    
    Args:
        content: LLM 响应内容
        output_model: 目标 Pydantic 模型类
        repair_enabled: 是否启用 json_repair（默认 True）
        metrics: 可选的 SemanticParserMetrics 实例（用于记录指标）
    
    Returns:
        解析后的模型实例
    
    Raises:
        JSONParseError: JSON 解析失败（格式错误，包括 json_repair 失败）
        ValidationError: Pydantic 校验失败（JSON 格式正确但 schema 不匹配）
    
    Example:
        response = await stream_llm_call(llm, messages)
        result = parse_json_response(response, DimensionHierarchyResult)
    """
    from pydantic import ValidationError
    
    original_content = content
    first_json_error_pos: int | None = None  # 记录第一次 JSON 解析错误的位置
    
    # 第一层：清理并尝试直接 json.loads() 解析
    cleaned = clean_json_output(content)
    
    try:
        # 先用 json.loads() 验证 JSON 格式
        data = json.loads(cleaned)
        # JSON 格式正确，再用 Pydantic 校验 schema
        result = output_model.model_validate(data)
        logger.debug("JSON direct parse succeeded")
        # 记录指标（Requirements 0.7）
        if metrics is not None and hasattr(metrics, 'json_direct_parse_success_count'):
            metrics.json_direct_parse_success_count += 1
            if provider and hasattr(metrics, "json_direct_parse_success_by_provider"):
                metrics.json_direct_parse_success_by_provider[provider] = (
                    metrics.json_direct_parse_success_by_provider.get(provider, 0) + 1
                )

        return result
    except json.JSONDecodeError as e:
        # JSON 格式错误 - 记录位置信息，继续尝试 json_repair
        first_json_error_pos = e.pos
        logger.debug(f"Direct JSON parse failed at position {e.pos}: {e.msg}")
    except ValidationError:
        # JSON 格式正确但 schema 不匹配 - 直接抛出，不需要 json_repair
        logger.warning(f"Pydantic validation failed for {output_model.__name__}")
        # 记录指标（Requirements 0.7）
        if metrics is not None and hasattr(metrics, 'pydantic_validation_failure_count'):
            metrics.pydantic_validation_failure_count += 1
            if provider and hasattr(metrics, "pydantic_validation_failure_by_provider"):
                metrics.pydantic_validation_failure_by_provider[provider] = (
                    metrics.pydantic_validation_failure_by_provider.get(provider, 0) + 1
                )

        raise
    
    # 第二层：尝试修复（Requirements 0.7）
    # 先做轻量 deterministic 修复，再尝试 json_repair（如安装）
    if repair_enabled:
        def _record_repair_attempt(attempt_type: str) -> None:
            if metrics is None:
                return
            if hasattr(metrics, "json_repair_attempt_type_attempt_counts"):
                metrics.json_repair_attempt_type_attempt_counts[attempt_type] = (
                    metrics.json_repair_attempt_type_attempt_counts.get(attempt_type, 0) + 1
                )

        def _record_repair_success(attempt_type: str) -> None:
            if metrics is None:
                return
            if hasattr(metrics, "json_repair_attempt_type_success_counts"):
                metrics.json_repair_attempt_type_success_counts[attempt_type] = (
                    metrics.json_repair_attempt_type_success_counts.get(attempt_type, 0) + 1
                )

        def _record_repair_success_rollup() -> None:
            if metrics is None or not hasattr(metrics, "json_repair_success_count"):
                return
            metrics.json_repair_success_count += 1
            if provider and hasattr(metrics, "json_repair_success_by_provider"):
                metrics.json_repair_success_by_provider[provider] = (
                    metrics.json_repair_success_by_provider.get(provider, 0) + 1
                )

        def _try_parse(repaired_str: str) -> T:
            data = json.loads(repaired_str)
            return output_model.model_validate(data)

        # 2.1 基础修复：移除尾随逗号
        try:
            _record_repair_attempt("remove_trailing_commas")
            repaired = re.sub(r",(\s*[}\]])", r"\1", cleaned)
            result = _try_parse(repaired)
            logger.info("JSON repaired and parsed successfully (remove_trailing_commas)")
            _record_repair_success_rollup()
            _record_repair_success("remove_trailing_commas")
            return result
        except (json.JSONDecodeError, ValidationError):
            pass
        except Exception as e:
            logger.debug(f"Repair attempt remove_trailing_commas failed: {e}")

        # 2.2 json_repair 库（如果存在）
        try:
            from json_repair import repair_json

            _record_repair_attempt("json_repair_lib")
            repaired = repair_json(original_content)
            result = _try_parse(repaired)

            logger.info("JSON repaired and parsed successfully (json_repair_lib)")
            _record_repair_success_rollup()
            _record_repair_success("json_repair_lib")
            return result

        except json.JSONDecodeError as repair_json_error:
            logger.warning(
                f"JSON repair failed (still invalid JSON): {repair_json_error}, "
                f"original content (truncated): {original_content[:500]}"
            )
        except ImportError:
            logger.debug("json-repair library not installed, skipping repair")
        except ValidationError:
            logger.warning(f"JSON repaired but Pydantic validation failed for {output_model.__name__}")
            if metrics is not None and hasattr(metrics, 'pydantic_validation_failure_count'):
                metrics.pydantic_validation_failure_count += 1
                if provider and hasattr(metrics, "pydantic_validation_failure_by_provider"):
                    metrics.pydantic_validation_failure_by_provider[provider] = (
                        metrics.pydantic_validation_failure_by_provider.get(provider, 0) + 1
                    )

            raise
        except Exception as repair_error:
            logger.warning(
                f"JSON repair failed (unexpected error): {repair_error}, "
                f"original content (truncated): {original_content[:500]}"
            )

    
    # 第三层：解析失败，抛出结构化错误
    # 记录指标（Requirements 0.7）
    if metrics is not None and hasattr(metrics, 'json_parse_failure_count'):
        metrics.json_parse_failure_count += 1
        if provider and hasattr(metrics, "json_parse_failure_by_provider"):
            metrics.json_parse_failure_by_provider[provider] = (
                metrics.json_parse_failure_by_provider.get(provider, 0) + 1
            )

    
    raise JSONParseError(
        message="Failed to parse JSON response after all attempts",
        content_preview=original_content[:200],
        error_type="json_parse",
        error_position=first_json_error_pos,  # 包含错误位置（Requirements 0.7）
    )


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
    "JSONParseError",
]
