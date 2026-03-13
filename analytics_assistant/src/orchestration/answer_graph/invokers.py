# -*- coding: utf-8 -*-
"""Answer 阶段的共享 LLM 调用入口。"""

from __future__ import annotations

from typing import Any


async def invoke_insight_agent(**kwargs: Any) -> Any:
    """延迟加载 Insight Agent，避免可选依赖在导入阶段产生副作用。"""
    from analytics_assistant.src.agents.insight.graph import run_insight_agent

    return await run_insight_agent(**kwargs)


async def invoke_replanner_agent(**kwargs: Any) -> Any:
    """延迟加载 Replanner Agent，避免可选依赖在导入阶段产生副作用。"""
    from analytics_assistant.src.agents.replanner.graph import run_replanner_agent

    return await run_replanner_agent(**kwargs)
