# -*- coding: utf-8 -*-
"""
Director Node - InsightAgent Subgraph Phase 2

Implements director_node(state: InsightState) -> Dict for the InsightAgent Subgraph.

Responsibilities:
- Read enhanced_profile, chunks, and accumulated insights from state
- Call AnalysisDirector.decide() to determine next action
- Process DirectorOutputWithAccumulation to update insights and final_summary
- Update state with director_decision and control fields

Architecture:
- This is a LangGraph node function, not a class
- Uses AnalysisDirector component for decision making
- Director LLM handles insight accumulation (KEEP/MERGE/REPLACE/DISCARD)
- Director LLM generates final_summary when stopping

Requirements:
- Task 3.6: Implement Director Node
- R8.2: Strategy selection and decision making
"""

import logging
from typing import Dict, Any, Optional

from tableau_assistant.src.agents.insight.state import InsightState
from tableau_assistant.src.agents.insight.components.director import AnalysisDirector
from tableau_assistant.src.agents.insight.models import (
    Insight,
    PriorityChunk,
    EnhancedDataProfile,
)
from tableau_assistant.src.agents.insight.models.director import (
    DirectorAction,
    DirectorDecision,
    DirectorOutputWithAccumulation,
)

logger = logging.getLogger(__name__)

# Default max iterations
DEFAULT_MAX_ITERATIONS = 5


async def director_node(state: InsightState, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Director node for InsightAgent Subgraph.
    
    Phase 2 of insight analysis:
    1. Read profile, chunks, and current insights from state
    2. Process analyst output if available (new insights + historical actions)
    3. Call AnalysisDirector.decide() to get DirectorOutputWithAccumulation
    4. Update state with accumulated insights, decision, and final_summary
    
    Args:
        state: InsightState containing enhanced_profile, chunks, insights
        config: LangGraph RunnableConfig (for middleware)
        
    Returns:
        Dict with:
        - director_decision: DirectorDecision
        - current_action: DirectorAction
        - current_target: Dict (chunk_id, dimension, anomaly_indices)
        - should_continue: bool
        - iteration_count: int
        - insights: List[Insight] (accumulated insights from Director)
        - final_summary: Optional[str] (when stopping)
        - error_message: Optional[str]
    """
    logger.info("Director node started")
    
    try:
        # 1. Extract required data from state
        enhanced_profile = state.get("enhanced_profile")
        chunks = state.get("chunks") or []
        analyzed_chunk_ids = state.get("analyzed_chunk_ids") or []
        iteration_count = state.get("iteration_count") or 0
        max_iterations = state.get("max_iterations") or DEFAULT_MAX_ITERATIONS
        
        # Get accumulated insights from state
        accumulated_insights = state.get("insights") or []
        
        # Get analyst output from state (if available, from analyzer_node)
        analyst_output = state.get("analyst_output")
        analyst_new_insights = None
        analyst_historical_actions = None
        data_coverage = state.get("data_coverage") or 0.0
        
        if analyst_output:
            analyst_new_insights = analyst_output.get("new_insights")
            # Format historical actions for director prompt
            raw_actions = analyst_output.get("historical_actions") or []
            if raw_actions:
                analyst_historical_actions = _format_historical_actions(raw_actions)
            data_coverage = analyst_output.get("data_coverage", data_coverage)
        
        # Get user question from context
        context = state.get("context") or {}
        user_question = context.get("question", "")
        if not user_question:
            # Try to get from restated_question
            user_question = state.get("restated_question") or ""
        
        # 2. Validate required data
        if enhanced_profile is None:
            logger.error("No enhanced_profile in state")
            return _create_error_response("No enhanced_profile available")
        
        if not chunks:
            logger.warning("No chunks available, stopping analysis")
            return _create_stop_response(
                reason="No data chunks available for analysis",
                iteration_count=iteration_count,
                current_insights=accumulated_insights,
            )
        
        # 3. Check iteration limit
        if iteration_count >= max_iterations:
            logger.info(f"Max iterations ({max_iterations}) reached, stopping")
            return _create_stop_response(
                reason=f"Maximum iterations ({max_iterations}) reached",
                iteration_count=iteration_count,
                current_insights=accumulated_insights,
                final_summary=_generate_iteration_limit_summary(accumulated_insights),
            )
        
        # 4. Create director and make decision
        director = AnalysisDirector(max_iterations=max_iterations)
        
        output: DirectorOutputWithAccumulation = await director.decide(
            user_question=user_question,
            enhanced_profile=enhanced_profile,
            available_chunks=chunks,
            analyzed_chunk_ids=analyzed_chunk_ids,
            current_insights=accumulated_insights,
            iteration_count=iteration_count,
            analyst_new_insights=analyst_new_insights,
            analyst_historical_actions=analyst_historical_actions,
            data_coverage=data_coverage,
            state=state,
            config=config,
        )
        
        logger.info(
            f"Director decision: action={output.decision.action}, "
            f"should_continue={output.decision.should_continue}, "
            f"accumulated_insights={len(output.accumulated_insights)}"
        )
        
        # 5. Build response with accumulated insights from Director
        return _build_decision_response(output, iteration_count + 1)
        
    except Exception as e:
        logger.error(f"Director node failed: {e}", exc_info=True)
        return _create_error_response(f"Director failed: {str(e)}")


def _build_decision_response(
    output: DirectorOutputWithAccumulation,
    iteration_count: int,
) -> Dict[str, Any]:
    """Build response dict from DirectorOutputWithAccumulation."""
    decision = output.decision
    
    # Build current_target based on action
    current_target = None
    if decision.action == DirectorAction.ANALYZE_CHUNK:
        current_target = {"chunk_id": decision.target_chunk_id}
    elif decision.action == DirectorAction.ANALYZE_DIMENSION:
        current_target = {
            "dimension": decision.target_dimension,
            "dimension_value": decision.target_dimension_value,
        }
    elif decision.action == DirectorAction.ANALYZE_ANOMALY:
        current_target = {"anomaly_indices": decision.target_anomaly_indices}
    
    response = {
        "director_decision": decision,
        "current_action": decision.action,
        "current_target": current_target,
        "should_continue": decision.should_continue,
        "iteration_count": iteration_count,
        # Key: Update insights from Director's accumulated_insights
        "insights": output.accumulated_insights,
        # Key: Update final_summary from Director
        "final_summary": output.final_summary,
        "error_message": None,
    }
    
    return response


def _create_stop_response(
    reason: str,
    iteration_count: int,
    current_insights: list = None,
    final_summary: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a stop response."""
    from tableau_assistant.src.agents.insight.models import InsightQuality
    
    decision = DirectorDecision(
        action=DirectorAction.STOP,
        should_continue=False,
        reason=reason,
        quality_assessment=InsightQuality(
            completeness=0.5,
            confidence=0.5,
            need_more_data=False,
            question_answered=False,
        ),
    )
    
    return {
        "director_decision": decision,
        "current_action": DirectorAction.STOP,
        "current_target": None,
        "should_continue": False,
        "iteration_count": iteration_count,
        "insights": current_insights or [],
        "final_summary": final_summary,
        "error_message": None,
    }


def _create_error_response(error_message: str) -> Dict[str, Any]:
    """Create an error response."""
    return {
        "director_decision": None,
        "current_action": None,
        "current_target": None,
        "should_continue": False,
        "iteration_count": 0,
        "insights": [],
        "final_summary": None,
        "error_message": error_message,
    }


def _generate_iteration_limit_summary(insights: list) -> str:
    """Generate summary when iteration limit is reached."""
    if not insights:
        return "Analysis reached maximum iterations without generating insights."
    
    insight_count = len(insights)
    return f"Analysis completed with {insight_count} insights after reaching iteration limit."


def _format_historical_actions(actions: list) -> str:
    """Format historical actions for director prompt."""
    if not actions:
        return "（无历史处理建议）"
    
    lines = []
    for action in actions:
        idx = action.get("historical_index", 0)
        action_type = action.get("action", "KEEP")
        reason = action.get("reason", "")
        lines.append(f"[{idx}] {action_type}: {reason}")
    
    return "\n".join(lines)


__all__ = ["director_node"]
