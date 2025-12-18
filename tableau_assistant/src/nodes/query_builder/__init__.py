"""
QueryBuilder Node - Pure code node (no LLM)

Converts MappedQuery (semantic with technical fields) to VizQLQuery.

Architecture (refactored):
- Uses platforms/tableau/query_builder.TableauQueryBuilder
- Implementation resolution and expression generation moved to platform layer

Requirements:
- R2.8: QueryBuilder Node entry point
"""

from .node import query_builder_node, QueryBuilderNode

__all__ = [
    "query_builder_node",
    "QueryBuilderNode",
]
