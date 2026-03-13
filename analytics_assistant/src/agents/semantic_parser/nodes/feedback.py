# -*- coding: utf-8 -*-
"""反馈学习节点。"""

import logging
from typing import Any, Optional

from langgraph.types import RunnableConfig

from analytics_assistant.src.orchestration.retrieval_memory import (
    FeedbackLearningService,
)

from ..query_contract import inspect_query_contract
from ..schemas.output import SemanticOutput
from ..state import SemanticParserState

logger = logging.getLogger(__name__)

_feedback_learning_service: Optional[FeedbackLearningService] = None


def _get_feedback_learning_service() -> FeedbackLearningService:
    """惰性创建反馈学习服务，避免重复构造外部依赖。"""
    global _feedback_learning_service
    if _feedback_learning_service is None:
        _feedback_learning_service = FeedbackLearningService()
    return _feedback_learning_service


def _build_semantic_guard_result(state: SemanticParserState) -> dict[str, Any]:
    """将 validation/filter validation 收敛成稳定的 semantic_guard 结果。"""
    validation_result = dict(state.get("validation_result") or {})
    filter_validation_result = dict(state.get("filter_validation_result") or {})
    confirmed_filters = list(state.get("confirmed_filters") or [])
    validation_errors = list(validation_result.get("errors") or [])
    query_contract_state = inspect_query_contract(state.get("semantic_query"))

    filter_needs_confirmation = bool(
        filter_validation_result.get("needs_confirmation", False)
    )
    filter_has_unresolvable = bool(
        filter_validation_result.get("has_unresolvable_filters", False)
    )
    verified = (
        bool(validation_result.get("is_valid", True))
        and not bool(validation_result.get("needs_clarification", False))
        and not filter_needs_confirmation
        and not filter_has_unresolvable
    )
    compiler_ready = bool(state.get("semantic_output")) and bool(
        query_contract_state["compiler_ready"]
    )

    return {
        "verified": verified,
        "validation_mode": "deterministic",
        "corrected": bool(validation_result.get("corrected_output"))
        or bool(confirmed_filters),
        "compiler_ready": compiler_ready,
        "allowed_to_execute": verified and compiler_ready,
        "query_contract_mode": query_contract_state["query_contract_mode"],
        "query_contract_source": query_contract_state["query_contract_source"],
        "error_count": len(validation_errors),
        "filter_confirmation_count": len(confirmed_filters),
        "needs_clarification": bool(
            validation_result.get("needs_clarification", False)
        ),
        "needs_value_confirmation": filter_needs_confirmation,
        "has_unresolvable_filters": filter_has_unresolvable,
        "errors": validation_errors,
    }


async def feedback_learner_node(
    state: SemanticParserState,
    config: Optional[RunnableConfig] = None,
) -> dict[str, Any]:
    """在语义解析成功后持久化缓存、审计与检索 trace。"""
    semantic_output_raw = state.get("semantic_output")
    semantic_query = state.get("semantic_query")
    optimization_metrics = dict(state.get("optimization_metrics") or {})

    if not semantic_output_raw:
        logger.warning("feedback_learner_node: 缺少 semantic_output")
        return {
            "parse_result": {
                "success": False,
                "error": {"message": "缺少 semantic_output"},
            }
        }

    semantic_output = SemanticOutput.model_validate(semantic_output_raw)
    feedback_service = _get_feedback_learning_service()
    feedback_result = await feedback_service.persist_success(
        state=state,
        config=config,
        semantic_output=semantic_output,
        semantic_query=semantic_query,
        optimization_metrics=optimization_metrics,
    )

    logger.info("feedback_learner_node: 完成, query_id=%s", semantic_output.query_id)
    return {
        "parse_result": {
            "success": True,
            "query_id": semantic_output.query_id,
            "semantic_output": semantic_output_raw,
            "semantic_guard": _build_semantic_guard_result(state),
            "validation_result": state.get("validation_result"),
            "filter_validation_result": state.get("filter_validation_result"),
            "analysis_plan": state.get("analysis_plan"),
            "global_understanding": state.get("global_understanding"),
            "query": semantic_query,
            "is_degraded": bool(state.get("is_degraded", False)),
            "optimization_metrics": optimization_metrics,
            "query_cache_hit": bool(state.get("cache_hit", False)),
            "candidate_fields_ref": state.get("candidate_fields_ref"),
            "candidate_values_ref": state.get("candidate_values_ref"),
            "fewshot_examples_ref": state.get("fewshot_examples_ref"),
            "retrieval_trace_ref": feedback_result.get("retrieval_trace_ref"),
            "memory_write_refs": list(feedback_result.get("memory_write_refs") or []),
        }
    }
