# -*- coding: utf-8 -*-
"""
Agent 基础模块

提供所有 Agent 节点共用的基础能力：
1. LLM 获取和配置（通过 ModelManager）
2. 流式结构化输出（统一方案，支持 tools + middleware）

公开 API（仅 2 个函数）：
- get_llm(): 获取 LLM 实例
- stream_llm_structured(): 流式+结构化输出 ⭐推荐

使用示例：
    from analytics_assistant.src.agents.base import (
        get_llm,
        stream_llm_structured,
        TaskType,
    )
    
    # 获取 LLM
    llm = get_llm(agent_name="semantic_parser", enable_json_mode=True)
    
    # 流式结构化输出（推荐）
    result = await stream_llm_structured(llm, messages, MyOutputModel)
    
    # 带 thinking（R1 模型）
    result, thinking = await stream_llm_structured(
        llm, messages, MyOutputModel,
        return_thinking=True,
    )
    
    # 带工具 + middleware
    result = await stream_llm_structured(
        llm, messages, MyOutputModel,
        tools=[search_tool],
        middleware=[my_middleware],
        state=current_state,
    )
"""

from .node import (
    # LLM 获取
    get_llm,
    get_agent_temperature,
    
    # 流式输出
    stream_llm,
    
    # 流式结构化输出（统一方案）⭐推荐
    stream_llm_structured,
)

from .context import (
    get_context,
    get_context_or_raise,
)

from ...infra.ai import TaskType

__all__ = [
    # LLM 获取
    "get_llm",
    "get_agent_temperature",
    
    # 流式输出
    "stream_llm",
    
    # 流式结构化输出（统一方案）
    "stream_llm_structured",
    
    # 上下文获取
    "get_context",
    "get_context_or_raise",
    
    # 任务类型
    "TaskType",
]
