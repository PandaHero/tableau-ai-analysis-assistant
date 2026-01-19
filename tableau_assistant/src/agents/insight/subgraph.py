# -*- coding: utf-8 -*-
"""InsightAgent Subgraph - LangGraph Subgraph implementation.

This module creates a LangGraph StateGraph that implements the InsightAgent
as a Subgraph. The Subgraph can be used as a node in the main workflow.

Architecture (LangGraph Node Routing Loop):
    START → profiler → director → (conditional) → analyzer | END
    analyzer → director (loop)

Flow:
1. Profiler: Generate enhanced data profile and create chunks
2. Director: Decide what to analyze next (chunk/dimension/anomaly)
3. Analyzer: Execute analysis based on director's decision
4. Loop: Director reviews analyst output and decides next action
5. End: When director decides to stop (question answered or max iterations)

Key Design:
- Progressive insight accumulation with historical insight processing
- Director LLM orchestrates the analysis loop
- Analyst LLM analyzes data and suggests insight actions
- No separate Synthesizer - Director generates final summary when stopping
"""

import logging
from typing import Any, Dict, Literal, Optional

from langgraph.graph import StateGraph, START, END
from langgraph.types import RunnableConfig

from tableau_assistant.src.agents.insight.state import InsightState
from tableau_assistant.src.agents.insight.nodes import profiler_node, director_node, analyzer_node
from tableau_assistant.src.agents.insight.models.director import DirectorAction


logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Routing Functions
# ═══════════════════════════════════════════════════════════════════════════

def route_after_profiler(state: InsightState) -> Literal["director", "__end__"]:
    """Route after Profiler node.
    
    Routing logic:
    - If profiler failed (error_message set): END
    - If no chunks generated: END
    - Otherwise: director
    """
    error_message = state.get("error_message")
    if error_message:
        logger.info(f"Route after profiler: END (error: {error_message})")
        return "__end__"
    
    chunks = state.get("chunks")
    if not chunks:
        logger.info("Route after profiler: END (no chunks)")
        return "__end__"
    
    logger.info("Route after profiler: director")
    return "director"


def route_after_director(state: InsightState) -> Literal["analyzer", "__end__"]:
    """Route after Director node.
    
    Routing logic:
    - If director failed (error_message set): END
    - If should_continue=False: END (analysis complete)
    - If action=STOP: END
    - Otherwise: analyzer
    """
    error_message = state.get("error_message")
    if error_message:
        logger.info(f"Route after director: END (error: {error_message})")
        return "__end__"
    
    should_continue = state.get("should_continue")
    if should_continue is False:
        logger.info("Route after director: END (should_continue=False)")
        return "__end__"
    
    current_action = state.get("current_action")
    if current_action == DirectorAction.STOP:
        logger.info("Route after director: END (action=STOP)")
        return "__end__"
    
    logger.info(f"Route after director: analyzer (action={current_action})")
    return "analyzer"


def route_after_analyzer(state: InsightState) -> Literal["director"]:
    """Route after Analyzer node.
    
    Always routes back to director for next decision.
    The director will decide whether to continue or stop.
    """
    logger.info("Route after analyzer: director")
    return "director"


# ═══════════════════════════════════════════════════════════════════════════
# Subgraph Factory
# ═══════════════════════════════════════════════════════════════════════════

def create_insight_subgraph() -> StateGraph:
    """Create the InsightAgent Subgraph.
    
    Architecture (LangGraph Node Routing Loop):
        START → profiler → director → (conditional) → analyzer | END
        analyzer → director (loop)
    
    Nodes:
    - profiler: Generate enhanced data profile and create chunks
    - director: Decide what to analyze next, manage insight accumulation
    - analyzer: Execute analysis based on director's decision
    
    Flow:
    1. Profiler generates Tableau Pulse-style profile and chunks
    2. Director decides first analysis target
    3. Analyzer executes analysis with historical insight processing
    4. Director reviews output, updates insights, decides next action
    5. Loop continues until director decides to stop
    6. Director generates final summary when stopping
    
    Returns:
        StateGraph for InsightAgent (not compiled)
    """
    # Create graph with InsightState
    graph = StateGraph(InsightState)
    
    # Add nodes
    graph.add_node("profiler", profiler_node)
    graph.add_node("director", director_node)
    graph.add_node("analyzer", analyzer_node)
    
    # Add edges
    # START → profiler
    graph.add_edge(START, "profiler")
    
    # profiler → (conditional) → director | END
    graph.add_conditional_edges(
        "profiler",
        route_after_profiler,
        {
            "director": "director",
            "__end__": END,
        },
    )
    
    # director → (conditional) → analyzer | END
    graph.add_conditional_edges(
        "director",
        route_after_director,
        {
            "analyzer": "analyzer",
            "__end__": END,
        },
    )
    
    # analyzer → director (always loop back)
    graph.add_edge("analyzer", "director")
    
    logger.info("InsightAgent Subgraph created with profiler → director ↔ analyzer loop")
    
    return graph


__all__ = [
    "create_insight_subgraph",
    "route_after_profiler",
    "route_after_director",
    "route_after_analyzer",
]
