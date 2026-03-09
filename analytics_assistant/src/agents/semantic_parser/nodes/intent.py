# -*- coding: utf-8 -*-
"""意图路由节点"""
import logging
from typing import Any

from ..state import SemanticParserState
from ..components import IntentRouter, IntentType

logger = logging.getLogger(__name__)

async def intent_router_node(state: SemanticParserState) -> dict[str, Any]:
    """意图路由节点

    执行意图识别，判断问题类型。

    输入：
    - state["question"]: 用户问题

    输出：
    - intent_router_output: IntentRouterOutput 序列化后的 dict
    """
    logger.info("=" * 60)
    logger.info("[intent_router_node] 开始执行")
    question = state.get("question", "")
    logger.info(f"[intent_router_node] 问题: {question}")

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

    logger.info("[intent_router_node] 创建 IntentRouter...")
    router = IntentRouter()
    logger.info("[intent_router_node] 调用 router.route()...")
    result = await router.route(question)

    logger.info(
        f"intent_router_node: intent={result.intent_type.value}, "
        f"confidence={result.confidence:.2f}"
    )
    logger.info("[intent_router_node] 执行完成")
    logger.info("=" * 60)

    return {
        "intent_router_output": result.model_dump(),
    }
