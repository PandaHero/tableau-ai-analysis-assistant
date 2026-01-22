# -*- coding: utf-8 -*-
"""
Agent 基础模块

提供所有 Agent 节点共用的基础能力：
1. LLM 获取和配置（通过 ModelManager）
2. LLM 调用（支持流式输出和工具调用）
3. Middleware 支持
4. JSON 解析

使用示例：
    from analytics_assistant.src.agents.base import (
        get_llm,
        call_llm,
        call_llm_with_tools,
        parse_json_response,
        TaskType,
    )
    
    # 获取 LLM
    llm = get_llm(agent_name="semantic_parser")
    
    # 调用 LLM（流式）
    response = await call_llm(llm, messages)
    
    # 带工具调用
    response = await call_llm_with_tools(llm, messages, tools)
    
    # 解析 JSON
    result = parse_json_response(response.content, MyOutputModel)
"""

from .node import (
    # LLM 获取
    get_llm,
    get_agent_temperature,
    
    # LLM 调用
    call_llm,
    stream_llm,
    call_llm_with_tools,
    
    # JSON 解析
    parse_json_response,
    JSONParseError,
)

from .middleware_runner import (
    # 主类
    MiddlewareRunner,
    
    # 异常
    MiddlewareError,
    MiddlewareChainError,
    
    # 类型
    ModelRequest,
    ModelResponse,
    ToolCallRequest,
    Runtime,
    
    # 辅助函数
    get_middleware_from_config,
)

# 从 infra/ai 导入 TaskType，方便 Agent 层使用
from ...infra.ai import TaskType

__all__ = [
    # LLM 获取
    "get_llm",
    "get_agent_temperature",
    
    # LLM 调用
    "call_llm",
    "stream_llm",
    "call_llm_with_tools",
    
    # JSON 解析
    "parse_json_response",
    "JSONParseError",
    
    # Middleware
    "MiddlewareRunner",
    "MiddlewareError",
    "MiddlewareChainError",
    "ModelRequest",
    "ModelResponse",
    "ToolCallRequest",
    "Runtime",
    "get_middleware_from_config",
    
    # 任务类型
    "TaskType",
]
