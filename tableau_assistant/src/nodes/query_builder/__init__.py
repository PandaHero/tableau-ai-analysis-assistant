"""
QueryBuilder Node - Pure code node (no LLM)

Converts MappedQuery (semantic with technical fields) to VizQLQuery.

Architecture:
- ImplementationResolver: Determines table calc vs LOD
- ExpressionGenerator: Generates VizQL expressions
- QueryAssembler: Assembles final VizQLQuery

Requirements:
- R2.8: QueryBuilder Node entry point
- R7.2.8-14: Implementation resolution and expression generation
"""

from .node import query_builder_node, QueryBuilderNode
from .implementation_resolver import ImplementationResolver
from .expression_generator import ExpressionGenerator

__all__ = [
    "query_builder_node",
    "QueryBuilderNode",
    "ImplementationResolver",
    "ExpressionGenerator",
]
