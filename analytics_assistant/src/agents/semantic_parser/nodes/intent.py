# -*- coding: utf-8 -*-
"""意图路由节点"""
import logging
from typing import Any

from ..state import SemanticParserState
from ..components import IntentRouter, IntentType

logger = logging.getLogger(__name__)

_intent_router_instance: IntentRouter | None = None

def _get_intent_router() -> IntentRouter:
    """懒加载单例 IntentRouter，避免每次请求重复编译正则和加载配置。"""
    global _intent_router_instance
    if _intent_router_instance is None:
        _intent_router_instance = IntentRouter()
    return _intent_router_instance

async def intent_router_node(state: SemanticParserState) -> dict[str, Any]:
    """意图路由节点

    执行意图识别，判断问题类型。

    输入：
    - state["question"]: 用户问题

    输出：
    - intent_router_output: IntentRouterOutput 序列化后的 dict
    """
    question = state.get("question", "")
    logger.debug(f"intent_router_node: 问题='{question[:50]}'")

    if not question:
        logger.warning("intent_router_node: 问题为空")
        return {
            "intent_router_output": {
                "intent_type": IntentType.IRRELEVANT.value,
                "confidence": 1.0,
                "reason": "问题为空",
                "source": "L0_RULES",
            }
        }

    router = _get_intent_router()
    result = await router.route(question)

    logger.info(
        f"intent_router_node: intent={result.intent_type.value}, "
        f"confidence={result.confidence:.2f}, source={result.source}"
    )

    return {
        "intent_router_output": result.model_dump(),
    }
