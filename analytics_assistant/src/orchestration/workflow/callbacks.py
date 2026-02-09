# -*- coding: utf-8 -*-
"""
SSE 回调机制

将后端工作流事件（token 流、思考过程、节点状态）转换为 SSE 事件，
通过 asyncio.Queue 传递给 StreamingResponse。

使用示例:
    event_queue = asyncio.Queue()
    callbacks = SSECallbacks(event_queue)

    # 注入到 RunnableConfig
    config = create_workflow_config(
        thread_id="xxx",
        context=ctx,
        on_token=callbacks.on_token,
        on_thinking=callbacks.on_thinking,
    )
"""

import asyncio
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# ========================================
# ProcessingStage 节点映射
# ========================================

# LLM 调用节点 → ProcessingStage
_LLM_NODE_MAPPING: Dict[str, str] = {
    "feature_extractor": "understanding",
    "semantic_understanding": "understanding",
    "error_corrector": "understanding",
    "field_mapper": "mapping",
    "field_semantic": "understanding",
}

# 用户可见节点（不调用 LLM，但需要展示进度）
_VISIBLE_NODE_MAPPING: Dict[str, str] = {
    "query_adapter": "building",
    "tableau_query": "executing",
    "feedback_learner": "generating",
}

# 合并映射
_ALL_NODE_MAPPING: Dict[str, str] = {**_LLM_NODE_MAPPING, **_VISIBLE_NODE_MAPPING}

# 阶段显示名称
_STAGE_NAMES_ZH: Dict[str, str] = {
    "understanding": "理解问题",
    "mapping": "字段映射",
    "building": "构建查询",
    "executing": "执行分析",
    "generating": "生成洞察",
}

_STAGE_NAMES_EN: Dict[str, str] = {
    "understanding": "Understanding",
    "mapping": "Mapping Fields",
    "building": "Building Query",
    "executing": "Executing Analysis",
    "generating": "Generating Insights",
}


def get_processing_stage(node_name: str) -> Optional[str]:
    """根据节点名称返回 ProcessingStage。

    只有涉及 LLM 调用或用户可见的节点才返回 stage，
    其他节点返回 None（不发送前端事件）。

    Args:
        node_name: LangGraph 节点名称

    Returns:
        ProcessingStage 字符串，或 None
    """
    return _ALL_NODE_MAPPING.get(node_name)


def get_stage_display_name(stage: str, language: str = "zh") -> str:
    """获取阶段的显示名称（支持中英文）。

    Args:
        stage: ProcessingStage
        language: 语言（"zh" 或 "en"）

    Returns:
        显示名称
    """
    if language == "en":
        return _STAGE_NAMES_EN.get(stage, stage)
    return _STAGE_NAMES_ZH.get(stage, stage)


class SSECallbacks:
    """SSE 回调函数集合。

    负责将后端事件转换为 SSE 事件字典，放入 asyncio.Queue。
    通过 RunnableConfig.configurable 注入到 LangGraph 节点。

    Attributes:
        event_queue: 事件队列
        _language: 显示语言
    """

    def __init__(
        self,
        event_queue: "asyncio.Queue[Optional[Dict]]",
        language: str = "zh",
    ):
        """初始化回调函数。

        Args:
            event_queue: 事件队列（用于发送 SSE 事件）
            language: 显示语言
        """
        self.event_queue = event_queue
        self._language = language

    async def on_token(self, token: str) -> None:
        """Token 回调：LLM 返回 token 时触发。

        Args:
            token: LLM 生成的 token
        """
        await self.event_queue.put({
            "type": "token",
            "content": token,
        })

    async def on_thinking(self, thinking: str) -> None:
        """Thinking 回调：R1 模型思考过程。

        Args:
            thinking: 思考内容
        """
        await self.event_queue.put({
            "type": "thinking_token",
            "content": thinking,
        })

    async def on_node_start(self, node_name: str) -> None:
        """节点开始回调。

        仅对有 ProcessingStage 映射的节点发送事件。

        Args:
            node_name: LangGraph 节点名称
        """
        stage = get_processing_stage(node_name)
        if stage:
            await self.event_queue.put({
                "type": "thinking",
                "stage": stage,
                "name": get_stage_display_name(stage, self._language),
                "status": "running",
            })

    async def on_node_end(self, node_name: str) -> None:
        """节点完成回调。

        仅对有 ProcessingStage 映射的节点发送事件。

        Args:
            node_name: LangGraph 节点名称
        """
        stage = get_processing_stage(node_name)
        if stage:
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
