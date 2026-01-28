# -*- coding: utf-8 -*-
"""
Agent 基础工具模块

提供所有 Agent 节点共用的基础能力：
1. LLM 获取和配置（通过 ModelManager）
2. 流式结构化输出（统一方案）
3. Middleware 支持

公开 API：
- get_llm(): 获取 LLM 实例
- stream_llm_structured(): 流式+结构化输出 ⭐推荐

使用示例：

    from analytics_assistant.src.agents.base import (
        get_llm,
        stream_llm_structured,
    )
    
    # 获取 LLM
    llm = get_llm(agent_name="semantic_parser", enable_json_mode=True)
    
    # 流式结构化输出
    result = await stream_llm_structured(llm, messages, MyOutputModel)
    
    # 带 thinking（R1 模型）
    result, thinking = await stream_llm_structured(
        llm, messages, MyOutputModel, return_thinking=True
    )
    
    # 带工具调用
    result = await stream_llm_structured(
        llm, messages, MyOutputModel, tools=[search_tool]
    )
"""
import logging
import re
import json
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
    overload,
)

from pydantic import BaseModel
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.utils.json import parse_partial_json

from ...infra.ai import get_model_manager, TaskType
from ...infra.config import get_config

logger = logging.getLogger(__name__)

T = TypeVar('T', bound=BaseModel)


# ═══════════════════════════════════════════════════════════════════════════
# LLM 获取
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
    return temp_config.get(agent_name.lower(), temp_config.get("default", 0.2))


def get_llm(
    agent_name: Optional[str] = None,
    temperature: Optional[float] = None,
    enable_json_mode: bool = False,
    task_type: Optional[TaskType] = None,
    model_id: Optional[str] = None,
    **kwargs
) -> BaseChatModel:
    """
    获取 LLM 实例
    
    Args:
        agent_name: Agent 名称（用于自动选择 temperature）
        temperature: 温度参数（覆盖 agent_name 配置）
        enable_json_mode: 是否启用 JSON Mode
        task_type: 任务类型（用于智能路由）
        model_id: 模型 ID（显式指定模型）
    
    Returns:
        配置好的 LLM 实例
    """
    if temperature is not None:
        _temperature = temperature
    elif agent_name:
        _temperature = get_agent_temperature(agent_name)
    else:
        _temperature = None
    
    manager = get_model_manager()
    return manager.create_llm(
        model_id=model_id,
        task_type=task_type,
        temperature=_temperature,
        enable_json_mode=enable_json_mode,
        **kwargs
    )


# ═══════════════════════════════════════════════════════════════════════════
# 流式结构化输出（统一方案）⭐推荐
# ═══════════════════════════════════════════════════════════════════════════

def _parse_json_to_model(content: str, output_model: Type[T]) -> T:
    """
    内部 JSON 解析函数
    
    使用 LangChain 的 parse_partial_json 解析 JSON，然后用 Pydantic 验证。
    """
    cleaned = re.sub(r'```json\s*', '', content)
    cleaned = re.sub(r'```\s*', '', cleaned)
    cleaned = cleaned.strip()
    
    parsed = parse_partial_json(cleaned)
    if parsed is None:
        raise ValueError(f"Cannot parse JSON: {content[:200]}...")
    
    return output_model.model_validate(parsed)


# 类型重载：return_thinking=False 时返回 T
@overload
async def stream_llm_structured(
    llm: BaseChatModel,
    messages: List[BaseMessage],
    output_model: Type[T],
    *,
    config: Optional[Dict[str, Any]] = None,
    tools: Optional[List[Any]] = None,
    middleware: Optional[List[Any]] = None,
    state: Optional[Dict[str, Any]] = None,
    max_iterations: int = 5,
    on_token: Optional[Callable[[str], Awaitable[None]]] = None,
    on_partial: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    on_thinking: Optional[Callable[[str], Awaitable[None]]] = None,
    return_thinking: bool = False,
) -> T: ...

# 类型重载：return_thinking=True 时返回 tuple[T, str]
@overload
async def stream_llm_structured(
    llm: BaseChatModel,
    messages: List[BaseMessage],
    output_model: Type[T],
    *,
    config: Optional[Dict[str, Any]] = None,
    tools: Optional[List[Any]] = None,
    middleware: Optional[List[Any]] = None,
    state: Optional[Dict[str, Any]] = None,
    max_iterations: int = 5,
    on_token: Optional[Callable[[str], Awaitable[None]]] = None,
    on_partial: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    on_thinking: Optional[Callable[[str], Awaitable[None]]] = None,
    return_thinking: bool = True,
) -> tuple[T, str]: ...


async def stream_llm_structured(
    llm: BaseChatModel,
    messages: List[BaseMessage],
    output_model: Type[T],
    *,
    config: Optional[Dict[str, Any]] = None,
    tools: Optional[List[Any]] = None,
    middleware: Optional[List[Any]] = None,
    state: Optional[Dict[str, Any]] = None,
    max_iterations: int = 5,
    on_token: Optional[Callable[[str], Awaitable[None]]] = None,
    on_partial: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    on_thinking: Optional[Callable[[str], Awaitable[None]]] = None,
    return_thinking: bool = False,
) -> Union[T, tuple[T, str]]:
    """
    流式调用 LLM 并返回结构化输出（统一方案）⭐推荐
    
    同时提供：
    1. Token 级别流式输出（通过 on_token 回调）
    2. 部分 JSON 对象流式输出（通过 on_partial 回调）
    3. 完整的 Pydantic 对象返回
    4. 工具调用支持（可选）
    5. Middleware 支持（可选）
    6. Thinking 输出（R1 模型，可选）
    
    Args:
        llm: LLM 实例（建议启用 json_mode）
        messages: LangChain 消息列表
        output_model: 目标 Pydantic 模型类
        config: LangGraph RunnableConfig
        tools: 可用工具列表
        middleware: middleware 列表
        state: 当前状态（用于 middleware）
        max_iterations: 最大工具调用迭代次数
        on_token: Token 回调（用于 UI 展示）
        on_partial: 部分 JSON 回调（用于渐进式 UI 更新）
        on_thinking: Thinking 回调（R1 模型思考过程）
        return_thinking: 是否返回 thinking（默认 False）
    
    Returns:
        - return_thinking=False: 返回 Pydantic 模型实例
        - return_thinking=True: 返回 (Pydantic 模型实例, thinking 字符串)
    
    Example:
        # 基础用法
        result = await stream_llm_structured(llm, messages, Step1Output)
        
        # 带流式回调
        result = await stream_llm_structured(
            llm, messages, Step1Output,
            on_token=handle_token,
        )
        
        # 带 thinking（R1 模型）
        result, thinking = await stream_llm_structured(
            llm, messages, Step1Output,
            return_thinking=True,
        )
        
        # 带工具调用
        result = await stream_llm_structured(
            llm, messages, Step1Output,
            tools=[search_tool],
        )
    """
    if middleware:
        return await _stream_structured_with_middleware(
            llm, messages, output_model, config, tools,
            middleware, state, max_iterations, on_token, on_partial, on_thinking, return_thinking
        )
    if tools:
        return await _stream_structured_with_tools(
            llm, messages, output_model, config, tools,
            max_iterations, on_token, on_partial, on_thinking, return_thinking
        )
    return await _stream_structured_internal(
        llm, messages, output_model, config, on_token, on_partial, on_thinking, return_thinking
    )


async def _stream_structured_internal(
    llm: BaseChatModel,
    messages: List[BaseMessage],
    output_model: Type[T],
    config: Optional[Dict[str, Any]],
    on_token: Optional[Callable[[str], Awaitable[None]]],
    on_partial: Optional[Callable[[Dict[str, Any]], Awaitable[None]]],
    on_thinking: Optional[Callable[[str], Awaitable[None]]],
    return_thinking: bool,
) -> Union[T, tuple[T, str]]:
    """内部：基础流式结构化输出
    
    使用 json_mode 时，LLM 只知道要输出 JSON，但不知道具体格式。
    因此需要在 prompt 中注入 JSON Schema，告诉 LLM 期望的输出结构。
    
    这是 LangChain json_mode 的标准用法，参考：
    https://python.langchain.com/docs/how_to/structured_output/
    "Note that if using JSON mode then you must include instructions for 
    formatting the output into the desired schema into the model call."
    """
    # 构建 schema 指令，追加到最后一条消息
    schema = output_model.model_json_schema()
    schema_instruction = f"""

请严格按照以下 JSON Schema 格式输出，不要添加任何其他内容：
```json
{json.dumps(schema, ensure_ascii=False, indent=2)}
```"""
    
    # 复制消息列表，在最后一条 HumanMessage 后追加 schema 指令
    augmented_messages = list(messages)
    if augmented_messages:
        from langchain_core.messages import HumanMessage
        # 找到最后一条 HumanMessage 并追加 schema
        for i in range(len(augmented_messages) - 1, -1, -1):
            if isinstance(augmented_messages[i], HumanMessage):
                original = augmented_messages[i]
                augmented_messages[i] = HumanMessage(
                    content=str(original.content) + schema_instruction
                )
                break
    
    collected_content: List[str] = []
    additional_kwargs: Dict[str, Any] = {}
    prev_partial: Optional[Dict[str, Any]] = None
    
    async for chunk in llm.astream(augmented_messages, config=config):
        if hasattr(chunk, "content") and chunk.content:
            token = chunk.content
            collected_content.append(token)
            if on_token:
                await on_token(token)
            if on_partial:
                full_content = "".join(collected_content)
                try:
                    partial = parse_partial_json(full_content)
                    if partial is not None and partial != prev_partial:
                        await on_partial(partial)
                        prev_partial = partial
                except Exception:
                    pass
        if hasattr(chunk, "additional_kwargs") and chunk.additional_kwargs:
            if on_thinking and "thinking" in chunk.additional_kwargs:
                await on_thinking(chunk.additional_kwargs["thinking"])
            additional_kwargs.update(chunk.additional_kwargs)
    
    full_content = "".join(collected_content)
    final_content = additional_kwargs.get("answer", full_content)
    parsed = _parse_json_to_model(final_content, output_model)
    
    if return_thinking:
        return parsed, additional_kwargs.get("thinking", "")
    return parsed


async def _stream_structured_with_tools(
    llm: BaseChatModel,
    messages: List[BaseMessage],
    output_model: Type[T],
    config: Optional[Dict[str, Any]],
    tools: List[Any],
    max_iterations: int,
    on_token: Optional[Callable[[str], Awaitable[None]]],
    on_partial: Optional[Callable[[Dict[str, Any]], Awaitable[None]]],
    on_thinking: Optional[Callable[[str], Awaitable[None]]],
    return_thinking: bool,
) -> Union[T, tuple[T, str]]:
    """内部：带工具调用的流式结构化输出"""
    llm_with_tools = llm.bind_tools(tools)
    current_messages = list(messages)
    collected_thinking: List[str] = []
    
    for iteration in range(max_iterations):
        collected_content: List[str] = []
        tool_calls: List[Dict[str, Any]] = []
        additional_kwargs: Dict[str, Any] = {}
        prev_partial: Optional[Dict[str, Any]] = None
        
        async for chunk in llm_with_tools.astream(current_messages, config=config):
            if hasattr(chunk, "content") and chunk.content:
                token = chunk.content
                collected_content.append(token)
                if on_token:
                    await on_token(token)
                if on_partial:
                    full_content = "".join(collected_content)
                    try:
                        partial = parse_partial_json(full_content)
                        if partial is not None and partial != prev_partial:
                            await on_partial(partial)
                            prev_partial = partial
                    except Exception:
                        pass
            
            if hasattr(chunk, "tool_call_chunks") and chunk.tool_call_chunks:
                for tc_chunk in chunk.tool_call_chunks:
                    idx = tc_chunk.get("index", 0)
                    while len(tool_calls) <= idx:
                        tool_calls.append({"name": "", "args": "", "id": ""})
                    if tc_chunk.get("name"):
                        tool_calls[idx]["name"] = tc_chunk["name"]
                    if tc_chunk.get("args"):
                        tool_calls[idx]["args"] += tc_chunk["args"]
                    if tc_chunk.get("id"):
                        tool_calls[idx]["id"] = tc_chunk["id"]
            
            if hasattr(chunk, "additional_kwargs") and chunk.additional_kwargs:
                if on_thinking and "thinking" in chunk.additional_kwargs:
                    await on_thinking(chunk.additional_kwargs["thinking"])
                    collected_thinking.append(chunk.additional_kwargs["thinking"])
                additional_kwargs.update(chunk.additional_kwargs)
        
        # 检查是否有工具调用
        valid_tool_calls = [tc for tc in tool_calls if tc.get("name") and tc.get("id")]
        
        if not valid_tool_calls:
            # 没有工具调用，解析最终结果
            full_content = "".join(collected_content)
            final_content = additional_kwargs.get("answer", full_content)
            parsed = _parse_json_to_model(final_content, output_model)
            
            if return_thinking:
                thinking = additional_kwargs.get("thinking", "".join(collected_thinking))
                return parsed, thinking
            return parsed
        
        # 执行工具调用
        ai_message = AIMessage(
            content="".join(collected_content),
            tool_calls=[
                {
                    "name": tc["name"],
                    "args": json.loads(tc["args"]) if tc["args"] else {},
                    "id": tc["id"],
                }
                for tc in valid_tool_calls
            ]
        )
        current_messages.append(ai_message)
        
        # 查找并执行工具
        tools_by_name = {t.name: t for t in tools}
        for tc in valid_tool_calls:
            tool = tools_by_name.get(tc["name"])
            if tool:
                try:
                    args = json.loads(tc["args"]) if tc["args"] else {}
                    result = await tool.ainvoke(args)
                    current_messages.append(
                        ToolMessage(content=str(result), tool_call_id=tc["id"])
                    )
                except Exception as e:
                    logger.warning(f"Tool {tc['name']} failed: {e}")
                    current_messages.append(
                        ToolMessage(content=f"Error: {e}", tool_call_id=tc["id"])
                    )
            else:
                current_messages.append(
                    ToolMessage(content=f"Unknown tool: {tc['name']}", tool_call_id=tc["id"])
                )
    
    raise RuntimeError(f"Max iterations ({max_iterations}) reached without final response")


async def _stream_structured_with_middleware(
    llm: BaseChatModel,
    messages: List[BaseMessage],
    output_model: Type[T],
    config: Optional[Dict[str, Any]],
    tools: Optional[List[Any]],
    middleware: List[Any],
    state: Optional[Dict[str, Any]],
    max_iterations: int,
    on_token: Optional[Callable[[str], Awaitable[None]]],
    on_partial: Optional[Callable[[Dict[str, Any]], Awaitable[None]]],
    on_thinking: Optional[Callable[[str], Awaitable[None]]],
    return_thinking: bool,
) -> Union[T, tuple[T, str]]:
    """内部：带 Middleware 的流式结构化输出"""
    current_messages = list(messages)
    current_state = dict(state) if state else {}
    
    # 执行 pre-process middleware
    for mw in middleware:
        if hasattr(mw, "pre_process"):
            result = await mw.pre_process(current_messages, current_state)
            if result:
                current_messages, current_state = result
    
    # 调用 LLM（可能带工具）
    if tools:
        result = await _stream_structured_with_tools(
            llm, current_messages, output_model, config, tools,
            max_iterations, on_token, on_partial, on_thinking, return_thinking
        )
    else:
        result = await _stream_structured_internal(
            llm, current_messages, output_model, config,
            on_token, on_partial, on_thinking, return_thinking
        )
    
    # 提取 parsed 结果
    if return_thinking:
        parsed, thinking = result
    else:
        parsed = result
        thinking = ""
    
    # 执行 post-process middleware
    for mw in middleware:
        if hasattr(mw, "post_process"):
            post_result = await mw.post_process(parsed, current_state)
            if post_result is not None:
                parsed = post_result
    
    if return_thinking:
        return parsed, thinking
    return parsed


# ═══════════════════════════════════════════════════════════════════════════
# 简单流式输出（用于不需要结构化的场景）
# ═══════════════════════════════════════════════════════════════════════════

async def stream_llm(
    llm: BaseChatModel,
    messages: List[BaseMessage],
    config: Optional[Dict[str, Any]] = None,
) -> AsyncIterator[str]:
    """
    简单流式输出（仅返回 token 流）
    
    用于不需要结构化输出的场景，如维度层级推断。
    如果需要结构化输出，请使用 stream_llm_structured()。
    
    Args:
        llm: LLM 实例
        messages: LangChain 消息列表
        config: LangGraph RunnableConfig
    
    Yields:
        LLM 生成的 token
    """
    async for chunk in llm.astream(messages, config=config):
        if hasattr(chunk, "content") and chunk.content:
            yield chunk.content


# ═══════════════════════════════════════════════════════════════════════════
# 导出
# ═══════════════════════════════════════════════════════════════════════════

__all__ = [
    "get_llm",
    "get_agent_temperature",
    "TaskType",
    "stream_llm",
    "stream_llm_structured",
]
