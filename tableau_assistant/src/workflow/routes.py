"""
Workflow routing logic for Tableau Assistant

This module contains the routing functions used by the StateGraph
to determine the next node based on the current state.

Routing decisions:
1. After Understanding: is_analysis_question → field_mapper or END
2. After Replanner: should_replan + replan_count → understanding or END

**Validates: Requirements 2.3, 2.4, 2.5, 17.4, 17.5, 17.6, 17.7**
"""

import logging
from typing import Dict, Any, Literal

logger = logging.getLogger(__name__)


def route_after_understanding(state: Dict[str, Any]) -> Literal["field_mapper", "end"]:
    """
    Route after Understanding node.
    
    Decision rules:
    1. If is_analysis_question=True → return "field_mapper"
    2. Otherwise → return "end" (non-analysis question, end directly)
    
    **Property 3: 非分析类问题路由**
    *For any* Understanding 输出中 is_analysis_question=False，
    工作流应直接路由到 END 并返回友好提示
    **Validates: Requirements 2.3**
    
    Args:
        state: Current workflow state
    
    Returns:
        Next node name: "field_mapper" or "end"
    """
    is_analysis_question = state.get("is_analysis_question", True)
    question = state.get("question", "")[:50]  # Truncate for logging
    
    if is_analysis_question:
        logger.debug(f"Routing to field_mapper: question='{question}...'")
        return "field_mapper"
    
    logger.info(f"Non-analysis question detected, routing to END: '{question}...'")
    return "end"


def route_after_replanner(
    state: Dict[str, Any],
    max_replan_rounds: int = 3
) -> Literal["understanding", "end"]:
    """
    Smart replan routing logic.
    
    Decision rules (determined by Replanner Agent LLM):
    1. completeness_score >= 0.9 → END (analysis complete)
    2. completeness_score < 0.9 and replan_count < max → replan
       - Route to understanding (re-understand new question)
    3. replan_count >= max → END (force end)
    
    Routing rules:
    - should_replan=True and replan_count < max → understanding
    - should_replan=False or replan_count >= max → END
    
    **Property 4: 智能重规划路由正确性**
    *For any* Replanner 输出，当 should_replan=True 且 replan_count < max 时
    应路由到 Understanding，否则应路由到 END
    **Validates: Requirements 2.4, 2.5, 17.4, 17.5, 17.6, 17.7**
    
    Note: Planning node has been removed. When replanning, go directly
    back to Understanding node to re-understand the new question.
    
    Args:
        state: Current workflow state
        max_replan_rounds: Maximum number of replan rounds (default 3)
    
    Returns:
        Next node name: "understanding" or "end"
    """
    replan_decision = state.get("replan_decision")
    replan_count = state.get("replan_count", 0)
    
    # Extract decision details - handle both Pydantic object and dict
    if replan_decision is None:
        should_replan = False
        completeness_score = 1.0
        exploration_questions = []
    elif hasattr(replan_decision, "should_replan"):
        # Pydantic object
        should_replan = replan_decision.should_replan
        completeness_score = replan_decision.completeness_score
        exploration_questions = replan_decision.exploration_questions or []
    else:
        # Dict fallback
        should_replan = replan_decision.get("should_replan", False)
        completeness_score = replan_decision.get("completeness_score", 1.0)
        exploration_questions = replan_decision.get("exploration_questions", [])
    
    # Check if max replan rounds reached
    if replan_count >= max_replan_rounds:
        logger.info(
            f"Max replan rounds reached ({replan_count}/{max_replan_rounds}), "
            f"routing to END (completeness={completeness_score:.2f})"
        )
        return "end"
    
    # Route based on Replanner's smart decision
    if should_replan:
        # Get exploration questions for logging
        if exploration_questions:
            first_q = exploration_questions[0]
            if hasattr(first_q, "question"):
                next_question = first_q.question
            elif isinstance(first_q, dict):
                next_question = first_q.get("question", "N/A")
            else:
                next_question = str(first_q)
        else:
            next_question = "N/A"
        
        logger.info(
            f"Replanning: round {replan_count + 1}/{max_replan_rounds}, "
            f"completeness={completeness_score:.2f}, "
            f"next_question='{next_question[:50]}...'"
        )
        return "understanding"
    
    logger.info(
        f"Analysis complete: completeness={completeness_score:.2f}, "
        f"rounds={replan_count}, routing to END"
    )
    return "end"


def calculate_completeness_score(
    state: Dict[str, Any],
    replan_decision: Dict[str, Any]
) -> float:
    """
    Calculate completeness score.
    
    Design principle:
    - LLM (Replanner Agent) is the best judge of "is the question fully answered"
      because it sees the original question, results, insights, and full context
    - Auxiliary checks only serve as a sanity check for extreme cases
      (e.g., LLM says 0.9 but there's no data at all)
    
    Formula: final_score = llm_score * 0.8 + auxiliary_score * 0.2
    
    The auxiliary_score is 1.0 in normal cases, only drops when:
    - No query results at all (critical failure)
    - High error ratio (> 50% of results are errors)
    - No insights generated (analysis incomplete)
    
    Args:
        state: Current workflow state
        replan_decision: Replan decision from Replanner Agent
    
    Returns:
        Score between 0.0 and 1.0
    """
    # LLM-evaluated score is the primary indicator (80% weight)
    llm_score = replan_decision.get("completeness_score", 0.5)
    
    # Auxiliary score: sanity check for extreme cases (20% weight)
    # Starts at 1.0, only reduced when something is clearly wrong
    auxiliary_score = 1.0
    
    subtask_results = state.get("subtask_results", [])
    errors = state.get("errors", [])
    insights = state.get("insights", [])
    
    # Check 1: No results at all is a critical failure
    if not subtask_results:
        auxiliary_score = 0.0
    else:
        # Check 2: High error ratio (> 50%) indicates problems
        error_ratio = len(errors) / len(subtask_results) if subtask_results else 0
        if error_ratio > 0.5:
            auxiliary_score = min(auxiliary_score, 0.5)
        
        # Check 3: No insights means analysis is incomplete
        if not insights:
            auxiliary_score = min(auxiliary_score, 0.5)
    
    # Final score: LLM is primary (80%), auxiliary is sanity check (20%)
    final_score = llm_score * 0.8 + auxiliary_score * 0.2
    
    return min(1.0, max(0.0, final_score))
