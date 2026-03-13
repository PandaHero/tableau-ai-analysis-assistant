# -*- coding: utf-8 -*-
"""Strict analysis-plan normalization node."""

import logging
import time
from typing import Any

from ..node_utils import merge_metrics
from ..schemas.planner import GlobalUnderstandingOutput, parse_analysis_plan
from ..state import SemanticParserState

logger = logging.getLogger(__name__)


def _require_global_understanding(
    raw_global_understanding: Any,
) -> GlobalUnderstandingOutput:
    if not raw_global_understanding:
        raise ValueError("analysis_planner requires global_understanding")
    return GlobalUnderstandingOutput.model_validate(raw_global_understanding)


async def analysis_planner_node(state: SemanticParserState) -> dict[str, object]:
    """Normalize an already-structured plan without any rule fallback."""

    start_time = time.time()
    raw_global_understanding = state.get("global_understanding")
    global_understanding = _require_global_understanding(raw_global_understanding)

    plan = parse_analysis_plan(
        raw_analysis_plan=state.get("analysis_plan"),
        raw_global_understanding=raw_global_understanding,
    )
    if plan is None:
        raise ValueError(
            "analysis_planner requires analysis_plan or "
            "global_understanding.analysis_plan"
        )

    if global_understanding.analysis_plan is None:
        global_understanding = global_understanding.model_copy(
            update={"analysis_plan": plan}
        )

    elapsed_ms = (time.time() - start_time) * 1000
    logger.info(
        "analysis_planner_node: mode=%s, needs_planning=%s, sub_questions=%s, elapsed=%.1fms",
        plan.plan_mode.value,
        plan.needs_planning,
        len(plan.sub_questions),
        elapsed_ms,
    )

    return {
        "analysis_plan": plan.model_dump(),
        "global_understanding": global_understanding.model_dump(),
        "optimization_metrics": merge_metrics(
            state,
            analysis_planner_ms=elapsed_ms,
            analysis_planner_mode=plan.plan_mode.value,
            analysis_planner_triggered=plan.needs_planning,
        ),
    }


__all__ = ["analysis_planner_node"]
