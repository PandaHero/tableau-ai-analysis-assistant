"""SemanticParser Agent - Semantic understanding and query generation.

This module provides the SemanticParser agent which:
1. Understands user questions (Step 1)
2. Performs computation reasoning (Step 2)
3. Generates and executes VizQL queries (Pipeline)
4. Handles errors with ReAct pattern (via LangGraph node routing loop)

Main exports:
- semantic_parser_node: LangGraph node function for main graph integration
- create_semantic_parser_subgraph: Factory function to create the subgraph
"""

from .node import semantic_parser_node
from .subgraph import create_semantic_parser_subgraph

__all__ = [
    "semantic_parser_node",
    "create_semantic_parser_subgraph",
]
