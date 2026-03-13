# -*- coding: utf-8 -*-
"""错误修正节点。"""

import logging
from typing import Any

from analytics_assistant.src.agents.base.node import get_llm

from ..components import ErrorCorrector
from ..schemas.output import SemanticOutput
from ..state import SemanticParserState

logger = logging.getLogger(__name__)


async def error_corrector_node(state: SemanticParserState) -> dict[str, Any]:
    """根据执行错误反馈修正语义结果。"""
    question = state.get("question", "")
    semantic_output_raw = state.get("semantic_output")
    pipeline_error = state.get("pipeline_error")
    error_history = state.get("error_history", [])

    if not pipeline_error:
        logger.warning("error_corrector_node: 没有错误需要修正")
        return {}

    if not semantic_output_raw:
        logger.warning("error_corrector_node: 缺少 semantic_output")
        return {"correction_abort_reason": "missing_semantic_output"}

    semantic_output = SemanticOutput.model_validate(semantic_output_raw)
    corrector = ErrorCorrector(
        llm=get_llm(agent_name="semantic_parser", enable_json_mode=True)
    )
    corrector.restore_history(error_history)

    context: dict[str, Any] = {}
    field_candidates_raw = state.get("field_candidates", [])
    if field_candidates_raw:
        context["available_fields"] = [
            candidate.get("field_name") or candidate.get("name", "")
            if isinstance(candidate, dict) else str(candidate)
            for candidate in field_candidates_raw
        ]
    if error_history:
        context["error_history"] = error_history

    result = await corrector.correct(
        question=question,
        previous_output=semantic_output,
        error_info=pipeline_error.get("message", ""),
        error_type=pipeline_error.get("error_type", "unknown"),
        context=context or None,
    )

    new_error_history = [item.model_dump() for item in corrector.error_history]
    new_retry_count = corrector.retry_count

    if not result.should_continue:
        logger.info(
            "error_corrector_node: 修正终止, reason=%s",
            result.abort_reason,
        )
        return {
            "error_history": new_error_history,
            "retry_count": new_retry_count,
            "correction_abort_reason": result.abort_reason,
            "thinking": result.thinking,
        }

    logger.info("error_corrector_node: 修正完成, retry_count=%s", new_retry_count)
    return {
        "semantic_output": (
            result.corrected_output.model_dump()
            if result.corrected_output else semantic_output_raw
        ),
        "error_history": new_error_history,
        "retry_count": new_retry_count,
        "pipeline_error": None,
        "thinking": result.thinking,
    }
