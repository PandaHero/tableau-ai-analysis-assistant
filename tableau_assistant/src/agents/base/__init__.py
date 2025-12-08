"""
Agent 基础模块

提供所有 Agent 节点共用的基础能力：
1. node.py - LLM 调用、工具处理、JSON 解析
2. prompt.py - Prompt 模板基类
"""
from .node import (
    # LLM 获取
    get_llm,
    get_agent_temperature,
    AGENT_TEMPERATURE_CONFIG,
    
    # 工具调用
    call_llm_with_tools,
    convert_messages,
    
    # 流式输出
    stream_llm_call,
    invoke_llm,
    
    # JSON 解析
    clean_json_output,
    parse_json_response,
)

from .prompt import (
    # Prompt 基类
    BasePrompt,
    StructuredPrompt,
    DataAnalysisPrompt,
    VizQLPrompt,
)

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
    
    # Prompt 基类
    "BasePrompt",
    "StructuredPrompt",
    "DataAnalysisPrompt",
    "VizQLPrompt",
]
