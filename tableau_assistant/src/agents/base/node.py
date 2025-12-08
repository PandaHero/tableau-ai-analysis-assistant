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
- 参考 understanding/node.py 的实现模式

使用示例：

    from tableau_assistant.src.agents.base import (
        get_llm,
        call_llm_with_tools,
        parse_json_response,
        stream_llm_call,
    )
    
    # 在 Agent 节点中使用
    async def my_agent_node(state, config):
        llm = get_llm(agent_name="my_agent")
        tools = [my_tool_1, my_tool_2]
        
        messages = MY_PROMPT.format_messages(...)
        
        # 方式 1：带工具调用
        response = await call_llm_with_tools(llm, messages, tools)
        result = parse_json_response(response, MyOutputModel)
        
        # 方式 2：流式输出（无工具）
        response = await stream_llm_call(llm, messages)
        result = parse_json_response(response, MyOutputModel)
"""
import json
import logging
import re
from typing import Dict, Any, List, Optional, Type, TypeVar

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
# Agent Temperature 配置
# ═══════════════════════════════════════════════════════════════════════════

AGENT_TEMPERATURE_CONFIG = {
    "understanding": 0.1,       # 需要精确理解用户意图
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


# ═══════════════════════════════════════════════════════════════════════════
# LLM 获取
# ═══════════════════════════════════════════════════════════════════════════

def get_llm(
    temperature: Optional[float] = None,
    model_name: Optional[str] = None,
    provider: Optional[str] = None,
    agent_name: Optional[str] = None,
) -> BaseChatModel:
    """
    获取 LLM 实例
    
    Args:
        temperature: 温度参数（可选）
        model_name: 模型名称（可选，默认从环境变量读取）
        provider: 提供商（可选，默认从环境变量读取）
        agent_name: Agent 名称（用于获取默认 temperature）
    
    Returns:
        配置好的 LLM 实例
    
    Example:
        # 使用默认配置
        llm = get_llm()
        
        # 指定 Agent 名称（自动获取对应 temperature）
        llm = get_llm(agent_name="dimension_hierarchy")
        
        # 完全自定义
        llm = get_llm(temperature=0.3, model_name="gpt-4o")
    """
    import os
    from tableau_assistant.src.model_manager.llm import select_model
    
    _provider = provider or os.environ.get("LLM_MODEL_PROVIDER", "local")
    _model_name = (
        model_name 
        or os.environ.get("TOOLING_LLM_MODEL") 
        or os.environ.get("LLM_MODEL_NAME", "qwen2.5-72b")
    )
    
    # 确定 temperature
    if temperature is not None:
        _temperature = temperature
    elif agent_name:
        _temperature = get_agent_temperature(agent_name)
    else:
        _temperature = float(os.environ.get("LLM_TEMPERATURE", "0.2"))
    
    return select_model(
        provider=_provider, 
        model_name=_model_name, 
        temperature=_temperature
    )


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


async def call_llm_with_tools(
    llm: BaseChatModel,
    messages: List[Dict[str, str]],
    tools: List[Any],
    max_iterations: int = 5,
) -> str:
    """
    调用 LLM 并处理工具调用
    
    这是 Agent 节点的核心函数，处理 LLM 与工具的交互循环。
    
    Args:
        llm: LLM 实例
        messages: 消息列表 [{"role": "system", "content": "..."}, ...]
        tools: 可用工具列表（@tool 装饰的函数）
        max_iterations: 最大迭代次数（防止无限循环）
    
    Returns:
        LLM 最终响应内容（字符串）
    
    Example:
        llm = get_llm(agent_name="understanding")
        tools = [get_metadata, parse_date]
        messages = MY_PROMPT.format_messages(question="各省份销售额")
        
        response = await call_llm_with_tools(llm, messages, tools)
        result = parse_json_response(response, SemanticQuery)
    """
    # 绑定工具到 LLM
    llm_with_tools = llm.bind_tools(tools)
    
    # 转换消息格式
    langchain_messages = convert_messages(messages)
    
    # 构建工具映射（用于快速查找）
    tool_map = {tool.name: tool for tool in tools}
    
    # 迭代处理工具调用
    for iteration in range(max_iterations):
        logger.debug(f"LLM iteration {iteration + 1}/{max_iterations}")
        
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


# ═══════════════════════════════════════════════════════════════════════════
# 流式输出
# ═══════════════════════════════════════════════════════════════════════════

async def stream_llm_call(
    llm: BaseChatModel,
    messages: List[Dict[str, str]],
    print_output: bool = True,
) -> str:
    """
    流式调用 LLM（无工具）
    
    适用于不需要工具调用的场景，如维度层级推断。
    
    Args:
        llm: LLM 实例
        messages: 消息列表
        print_output: 是否打印流式输出
    
    Returns:
        完整的响应内容
    
    Example:
        llm = get_llm(agent_name="dimension_hierarchy")
        messages = DIMENSION_HIERARCHY_PROMPT.format_messages(dimensions=dims_str)
        
        response = await stream_llm_call(llm, messages)
        result = parse_json_response(response, DimensionHierarchyResult)
    """
    langchain_messages = convert_messages(messages)
    
    collected_content = []
    token_count = 0
    
    if print_output:
        print("  🔄 [流式输出] ", end="", flush=True)
    
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
    
    if print_output:
        print(f" ✓ ({token_count} tokens)")
    
    full_content = "".join(collected_content)
    if not full_content.strip():
        raise ValueError("LLM 返回空内容")
    
    return full_content


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
    "convert_messages",
    
    # 流式输出
    "stream_llm_call",
    "invoke_llm",
    
    # JSON 解析
    "clean_json_output",
    "parse_json_response",
]
