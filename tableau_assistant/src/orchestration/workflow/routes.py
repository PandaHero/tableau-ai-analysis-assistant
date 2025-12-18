# -*- coding: utf-8 -*-
"""
Workflow routing logic for Tableau Assistant

This module contains the routing functions used by the StateGraph
to determine the next node based on the current state.

Routing decisions:
1. After SemanticParser: intent.type == DATA_QUERY -> field_mapper or END
2. After Replanner: should_replan + replan_count -> semantic_parser or END

**Validates: Requirements 2.3, 2.4, 2.5, 17.4, 17.5, 17.6, 17.7**
"""

import logging
from typing import Dict, List, Literal, Optional, Union

# VizQLState must be imported at runtime because LangGraph's add_conditional_edges
# calls get_type_hints() to infer the output schema
from tableau_assistant.src.orchestration.workflow.state import VizQLState, ErrorRecord
from tableau_assistant.src.core.models import ReplanDecision

logger = logging.getLogger(__name__)


def route_after_semantic_parser(state: VizQLState) -> Literal["field_mapper", "end"]:
    """
    Route after SemanticParser node.
    
    Decision rules based on intent type from SemanticParseResult:
    - DATA_QUERY -> field_mapper (continue with data analysis)
    - CLARIFICATION -> end (return clarification question)
    - GENERAL -> end (return general response)
    - IRRELEVANT -> end (return rejection message)
    
    Args:
        state: Current workflow state
    
    Returns:
        Next node name: "field_mapper" or "end"
    """
    from tableau_assistant.src.core.models import IntentType
    
    question = state.get("question", "")[:50]  # Truncate for logging

    # New architecture: check semantic_parse_result.intent.type
    semantic_parse_result = state.get("semantic_parse_result")
    if semantic_parse_result is not None:
        # Handle both Pydantic object and dict
        if hasattr(semantic_parse_result, "intent"):
            intent = semantic_parse_result.intent
            intent_type = intent.type if hasattr(intent, "type") else intent.get("type")
        else:
            intent = semantic_parse_result.get("intent", {})
            intent_type = intent.get("type") if isinstance(intent, dict) else None
        
        if intent_type == IntentType.DATA_QUERY:
            logger.debug(f"Routing to field_mapper (DATA_QUERY): question='{question}...'")
            return "field_mapper"
        else:
            logger.info(f"Non-DATA_QUERY intent ({intent_type}), routing to END: '{question}...'")
            return "end"
    
    # Legacy: check is_analysis_question
    is_analysis_question = state.get("is_analysis_question", True)
    
    if is_analysis_question:
        logger.debug(f"Routing to field_mapper: question='{question}...'")
        return "field_mapper"
    
    logger.info(f"Non-analysis question detected, routing to END: '{question}...'")
    return "end"


def route_after_replanner(
    state: VizQLState,
    max_replan_rounds: int = 3
) -> Literal["semantic_parser", "end"]:
    """
    Smart replan routing logic.
    
    Decision rules (determined by Replanner Agent LLM):
    1. completeness_score >= 0.9 -> END (analysis complete)
    2. completeness_score < 0.9 and replan_count < max -> replan
       - Route to semantic_parser (parse new exploration question)
    3. replan_count >= max -> END (force end)
    
    Args:
        state: Current workflow state
        max_replan_rounds: Maximum number of replan rounds (default 3)
    
    Returns:
        Next node name: "semantic_parser" or "end"
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
        return "semantic_parser"
    
    logger.info(
        f"Analysis complete: completeness={completeness_score:.2f}, "
        f"rounds={replan_count}, routing to END"
    )
    return "end"



def calculate_completeness_score(
    state: VizQLState,
    replan_decision: ReplanDecision,
) -> float:
    """
    Calculate completeness score.
    
    Design principle:
    - LLM (Replanner Agent) is the best judge of "is the question fully answered"
      because it sees the original question, results, insights, and full context
    - Auxiliary checks only serve as a sanity check for extreme cases
    
    Formula: final_score = llm_score * 0.8 + auxiliary_score * 0.2
    
    Args:
        state: Current workflow state
        replan_decision: Replan decision from Replanner Agent
    
    Returns:
        Score between 0.0 and 1.0
    """
    # LLM-evaluated score is the primary indicator (80% weight)
    if hasattr(replan_decision, "completeness_score"):
        llm_score = replan_decision.completeness_score
    else:
        llm_score = getattr(replan_decision, "completeness_score", 0.5)
    
    # Auxiliary score: sanity check for extreme cases (20% weight)
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
