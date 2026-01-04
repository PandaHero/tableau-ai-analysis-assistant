# -*- coding: utf-8 -*-
"""
Workflow routing logic for Tableau Assistant

This module contains the routing functions used by the StateGraph
to determine the next node based on the current state.

Refactored Architecture (3 Agent Nodes):
- SemanticParser (Subgraph): Step1 → Step2 → QueryPipeline
- Insight (Subgraph): Profiler → Director ⟷ Analyst
- Replanner (single node): Decides continue/end, generates parallel questions

Routing decisions:
1. After SemanticParser: intent.type == DATA_QUERY -> insight or END
2. After Replanner: should_replan + replan_count -> semantic_parser or END
   - Multiple questions: Use Send() API for parallel execution
   - Single question: Serial execution

Parallel Execution:
- When Replanner generates N>1 questions, route_after_replanner returns List[Send]
- LangGraph automatically handles parallel branch execution and state merging
- accumulated_insights uses merge_insights reducer for automatic deduplication
"""

import logging
from typing import Dict, List, Literal, Optional, Union

from langgraph.types import Send

# VizQLState must be imported at runtime because LangGraph's add_conditional_edges
# calls get_type_hints() to infer the output schema
from tableau_assistant.src.orchestration.workflow.state import VizQLState
from tableau_assistant.src.agents.replanner.models import ReplanDecision

logger = logging.getLogger(__name__)


def route_after_semantic_parser(state: VizQLState) -> Literal["insight", "end"]:
    """
    Route after SemanticParser Subgraph.
    
    Decision rules based on intent type:
    - DATA_QUERY with successful query_result -> insight (continue with analysis)
    - CLARIFICATION -> end (return clarification question)
    - GENERAL -> end (return general response)
    - IRRELEVANT -> end (return rejection message)
    - Query execution failed -> end (return error to user)
    
    Note: Error handling is now done within SemanticParser Subgraph via ReAct.
    If we reach this routing function, either:
    1. Query succeeded -> route to insight
    2. ReAct decided to ABORT/CLARIFY -> route to end
    
    Args:
        state: Current workflow state
    
    Returns:
        Next node name: "insight" or "end"
    """
    from tableau_assistant.src.core.models import IntentType
    
    question = state.get("question", "")[:50]  # Truncate for logging

    # Check intent_type (flattened field from SemanticParseResult)
    intent_type = state.get("intent_type")
    
    if intent_type is not None:
        if intent_type == IntentType.DATA_QUERY:
            # Check if query execution succeeded
            query_result = state.get("query_result")
            if query_result is not None:
                # Check for success
                is_success = False
                if hasattr(query_result, 'is_success'):
                    is_success = query_result.is_success()
                elif hasattr(query_result, 'error'):
                    is_success = not bool(query_result.error)
                elif isinstance(query_result, dict):
                    is_success = not bool(query_result.get('error'))
                else:
                    # Assume success if we have a result
                    is_success = True
                
                if is_success:
                    logger.debug(f"Routing to insight (DATA_QUERY success): question='{question}...'")
                    return "insight"
                else:
                    logger.info(f"Query failed, routing to END: '{question}...'")
                    return "end"
            else:
                # No query result - might be clarification or abort from ReAct
                logger.info(f"No query result, routing to END: '{question}...'")
                return "end"
        else:
            logger.info(f"Non-DATA_QUERY intent ({intent_type}), routing to END: '{question}...'")
            return "end"
    
    # Fallback: check is_analysis_question
    is_analysis_question = state.get("is_analysis_question", True)
    
    if is_analysis_question and state.get("query_result") is not None:
        logger.debug(f"Routing to insight (fallback): question='{question}...'")
        return "insight"
    
    logger.info(f"Non-analysis question or no result, routing to END: '{question}...'")
    return "end"


def route_after_replanner(
    state: VizQLState,
    max_replan_rounds: int = 3
) -> Union[Literal["semantic_parser", "end"], List[Send]]:
    """
    Smart replan routing logic with parallel execution support.
    
    Decision rules (determined by Replanner Agent LLM):
    1. completeness_score >= 0.9 or should_replan=False -> END (analysis complete)
    2. should_replan=True and replan_count < max:
       - N=1 question: Return "semantic_parser" (serial execution)
       - N>1 questions: Return List[Send] (parallel execution via Send() API)
    3. replan_count >= max -> END (force end)
    
    Parallel Execution:
    - When multiple exploration questions are generated, use Send() API
    - Each Send() creates a parallel branch with its own question
    - LangGraph automatically merges states using merge_insights reducer
    
    Args:
        state: Current workflow state
        max_replan_rounds: Maximum number of replan rounds (default 3)
    
    Returns:
        - "semantic_parser": Serial execution for single question
        - "end": Analysis complete or max rounds reached
        - List[Send]: Parallel execution for multiple questions
    """
    replan_decision = state.get("replan_decision")
    replan_count = state.get("replan_count", 0)
    parallel_questions = state.get("parallel_questions", [])

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
    if should_replan and exploration_questions:
        num_questions = len(exploration_questions)
        
        # Extract question texts for logging and Send()
        question_texts = []
        for q in exploration_questions:
            if hasattr(q, "question"):
                question_texts.append(q.question)
            elif isinstance(q, dict):
                question_texts.append(q.get("question", str(q)))
            else:
                question_texts.append(str(q))
        
        if num_questions == 1:
            # Single question: serial execution
            logger.info(
                f"Replanning (serial): round {replan_count + 1}/{max_replan_rounds}, "
                f"completeness={completeness_score:.2f}, "
                f"question='{question_texts[0][:50]}...'"
            )
            return "semantic_parser"
        else:
            # Multiple questions: parallel execution via Send() API
            logger.info(
                f"Replanning (parallel): round {replan_count + 1}/{max_replan_rounds}, "
                f"completeness={completeness_score:.2f}, "
                f"dispatching {num_questions} parallel branches"
            )
            
            # Create Send() for each question
            sends = []
            for i, question_text in enumerate(question_texts):
                # Each Send() creates a parallel branch with updated question
                sends.append(
                    Send(
                        "semantic_parser",
                        {
                            "question": question_text,
                            "replan_count": replan_count + 1,
                            # Clear previous results for fresh analysis
                            "semantic_query": None,
                            "mapped_query": None,
                            "vizql_query": None,
                            "query_result": None,
                            "enhanced_profile": None,
                            "insights": [],
                        }
                    )
                )
                logger.debug(f"  Branch {i+1}: '{question_text[:50]}...'")
            
            return sends
    
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
    
    errors = state.get("errors", [])
    insights = state.get("insights", [])
    accumulated_insights = state.get("accumulated_insights", [])
    
    # Use accumulated_insights if available (from parallel execution)
    all_insights = accumulated_insights if accumulated_insights else insights
    
    # Check 1: No query result at all is a critical failure
    query_result = state.get("query_result")
    if not query_result:
        auxiliary_score = 0.0
    else:
        # Check 2: High error ratio indicates problems
        if errors:
            auxiliary_score = min(auxiliary_score, 0.5)
        
        # Check 3: No insights means analysis is incomplete
        if not all_insights:
            auxiliary_score = min(auxiliary_score, 0.5)
    
    # Final score: LLM is primary (80%), auxiliary is sanity check (20%)
    final_score = llm_score * 0.8 + auxiliary_score * 0.2
    
    return min(1.0, max(0.0, final_score))
