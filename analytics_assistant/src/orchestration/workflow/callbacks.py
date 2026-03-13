# -*- coding: utf-8 -*-
"""工作流到 SSE 事件的回调适配层。"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# LLM 调用节点 -> ProcessingStage。
_LLM_NODE_MAPPING: dict[str, str] = {
    "feature_extractor": "understanding",
    "global_understanding_stage": "understanding",
    "semantic_understanding": "understanding",
    "insight_agent": "generating",
    "replanner_agent": "replanning",
    "field_mapper": "mapping",
    "field_semantic": "understanding",
}

# 用户可见节点，不一定调用 LLM，但需要展示进度。
_VISIBLE_NODE_MAPPING: dict[str, str] = {
    "authentication": "preparing",
    "data_preparation": "preparing",
    "query_adapter": "building",
    "tableau_query": "executing",
    "feedback_learner": "generating",
    "insight_agent": "generating",
    "replanner_agent": "replanning",
    "rule_prefilter": "understanding",
    "global_understanding_stage": "understanding",
    "filter_validator": "building",
    "output_validator": "building",
    "error_corrector": "understanding",
}

_ALL_NODE_MAPPING: dict[str, str] = {**_LLM_NODE_MAPPING, **_VISIBLE_NODE_MAPPING}

_STAGE_NAMES_ZH: dict[str, str] = {
    "preparing": "准备数据",
    "understanding": "理解问题",
    "mapping": "字段映射",
    "building": "构建查询",
    "executing": "执行分析",
    "generating": "生成洞察",
    "replanning": "重新规划",
}

_STAGE_NAMES_EN: dict[str, str] = {
    "preparing": "Preparing Data",
    "understanding": "Understanding",
    "mapping": "Mapping Fields",
    "building": "Building Query",
    "executing": "Executing Analysis",
    "generating": "Generating Insights",
    "replanning": "Replanning",
}


def get_processing_stage(node_name: str) -> Optional[str]:
    """根据节点名返回稳定的 ProcessingStage。"""
    return _ALL_NODE_MAPPING.get(node_name)


def get_stage_display_name(stage: str, language: str = "zh") -> str:
    """获取阶段展示名，支持中英文。"""
    if language == "en":
        return _STAGE_NAMES_EN.get(stage, stage)
    return _STAGE_NAMES_ZH.get(stage, stage)


class SSECallbacks:
    """把工作流回调写入事件队列。"""

    def __init__(
        self,
        event_queue: "asyncio.Queue[Optional[dict]]",
        language: str = "zh",
    ):
        self.event_queue = event_queue
        self._language = language

    async def on_token(self, token: str) -> None:
        """转发普通答案 token。"""
        await self.event_queue.put({
            "type": "token",
            "content": token,
        })

    async def on_thinking(self, thinking: str) -> None:
        """转发 reasoning token。"""
        await self.event_queue.put({
            "type": "thinking_token",
            "content": thinking,
        })

    async def on_node_start(self, node_name: str) -> None:
        """节点开始时发出阶段 running 事件。"""
        stage = get_processing_stage(node_name)
        if stage is None:
            return
        await self.event_queue.put({
            "type": "thinking",
            "stage": stage,
            "name": get_stage_display_name(stage, self._language),
            "status": "running",
        })

    async def on_node_end(self, node_name: str) -> None:
        """节点结束时发出阶段 completed 事件。"""
        stage = get_processing_stage(node_name)
        if stage is None:
            return
        await self.event_queue.put({
            "type": "thinking",
            "stage": stage,
            "name": get_stage_display_name(stage, self._language),
            "status": "completed",
        })


__all__ = [
    "SSECallbacks",
    "get_processing_stage",
    "get_stage_display_name",
]
