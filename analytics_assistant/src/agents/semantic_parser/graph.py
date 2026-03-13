# -*- coding: utf-8 -*-
"""Semantic parser LangGraph definition."""

from __future__ import annotations

import logging
from typing import Any, Optional

from langgraph.graph import END, StateGraph

from .nodes import (
    error_corrector_node,
    feedback_learner_node,
    filter_validator_node,
    intent_router_node,
    output_validator_node,
    parallel_retrieval_node,
    prepare_prompt_node,
    query_adapter_node,
    query_cache_node,
    semantic_understanding_node,
    unified_feature_and_understanding_node,
)
from .routes import (
    route_after_correction,
    route_after_query,
    route_by_cache,
    route_by_intent,
)
from .state import SemanticParserState

logger = logging.getLogger(__name__)

_compiled_graph_singleton: Optional[Any] = None


def create_semantic_parser_graph() -> StateGraph:
    """Create the semantic parser graph using the refactored node layout."""
    graph = StateGraph(SemanticParserState)

    graph.add_node("intent_router", intent_router_node)
    graph.add_node("query_cache", query_cache_node)
    graph.add_node(
        "unified_feature_understanding",
        unified_feature_and_understanding_node,
    )
    graph.add_node("parallel_retrieval", parallel_retrieval_node)
    graph.add_node("prepare_prompt", prepare_prompt_node)
    graph.add_node("semantic_understanding", semantic_understanding_node)
    graph.add_node("output_validator", output_validator_node)
    graph.add_node("filter_validator", filter_validator_node)
    graph.add_node("query_adapter", query_adapter_node)
    graph.add_node("error_corrector", error_corrector_node)
    graph.add_node("feedback_learner", feedback_learner_node)

    graph.set_entry_point("intent_router")

    graph.add_conditional_edges(
        "intent_router",
        route_by_intent,
        {
            "data_query": "query_cache",
            "general": END,
            "irrelevant": END,
            "clarification": END,
        },
    )
    graph.add_conditional_edges(
        "query_cache",
        route_by_cache,
        {
            "cache_hit": "feedback_learner",
            "cache_miss": "unified_feature_understanding",
        },
    )

    graph.add_edge("unified_feature_understanding", "parallel_retrieval")
    graph.add_edge("parallel_retrieval", "prepare_prompt")
    graph.add_edge("prepare_prompt", "semantic_understanding")
    graph.add_edge("semantic_understanding", "output_validator")
    graph.add_edge("output_validator", "filter_validator")
    graph.add_edge("filter_validator", "query_adapter")

    graph.add_conditional_edges(
        "query_adapter",
        route_after_query,
        {
            "success": "feedback_learner",
            "error": "error_corrector",
        },
    )
    graph.add_conditional_edges(
        "error_corrector",
        route_after_correction,
        {
            "retry": "output_validator",
            "abort": END,
        },
    )

    graph.add_edge("feedback_learner", END)
    return graph


def compile_semantic_parser_graph(checkpointer: Optional[Any] = None) -> Any:
    """Compile and cache the semantic parser graph."""
    global _compiled_graph_singleton

    if checkpointer is not None:
        return create_semantic_parser_graph().compile(checkpointer=checkpointer)

    if _compiled_graph_singleton is None:
        _compiled_graph_singleton = create_semantic_parser_graph().compile()
        logger.info("semantic_parser graph 已编译并缓存为进程级单例")

    return _compiled_graph_singleton


__all__ = [
    "intent_router_node",
    "query_cache_node",
    "semantic_understanding_node",
    "output_validator_node",
    "filter_validator_node",
    "query_adapter_node",
    "error_corrector_node",
    "feedback_learner_node",
    "unified_feature_and_understanding_node",
    "prepare_prompt_node",
    "parallel_retrieval_node",
    "route_by_intent",
    "route_by_cache",
    "route_after_query",
    "route_after_correction",
    "create_semantic_parser_graph",
    "compile_semantic_parser_graph",
]
