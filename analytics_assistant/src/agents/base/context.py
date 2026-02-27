# -*- coding: utf-8 -*-
"""
Agent 上下文获取辅助函数

从 LangGraph RunnableConfig 中提取工作流上下文对象。
返回类型为 WorkflowContextProtocol，Agent 节点无需依赖 orchestration 模块。

使用示例:
    from analytics_assistant.src.agents.base.context import (
        get_context,
        get_context_or_raise,
    )

    async def my_node(state, config):
        ctx = get_context_or_raise(config)
        datasource = ctx.datasource_luid
"""

from typing import Any, Optional

from analytics_assistant.src.core.interfaces import WorkflowContextProtocol

def get_context(
    config: Optional[dict[str, Any]],
) -> Optional[WorkflowContextProtocol]:
    """从 RunnableConfig 获取工作流上下文。

    Args:
        config: LangGraph RunnableConfig 配置字典

    Returns:
        WorkflowContextProtocol 实例，如果不存在则返回 None
    """
    if config is None:
        return None
    configurable = config.get("configurable", {})
    return configurable.get("workflow_context")

def get_context_or_raise(
    config: Optional[dict[str, Any]],
) -> WorkflowContextProtocol:
    """从 RunnableConfig 获取工作流上下文，不存在则抛出异常。

    Args:
        config: LangGraph RunnableConfig 配置字典

    Returns:
        WorkflowContextProtocol 实例

    Raises:
        ValueError: 如果 config 为 None 或不包含 workflow_context
    """
    if config is None:
        raise ValueError("config is None, cannot get WorkflowContext")

    ctx = get_context(config)
    if ctx is None:
        raise ValueError(
            "WorkflowContext not found in config. "
            "Make sure to use create_workflow_config() to create the config."
        )
    return ctx

__all__ = [
    "get_context",
    "get_context_or_raise",
]
