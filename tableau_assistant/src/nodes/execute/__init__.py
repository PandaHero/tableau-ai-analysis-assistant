"""
Execute Node - Pure code node (no LLM)

Executes VizQL queries against VizQL Data Service API.

Architecture:
- Receives VizQLQuery from QueryBuilder
- Calls VizQL Data Service /query-datasource API
- Returns ExecuteResult with data

Requirements:
- R7.1: Execute VizQL API call
- R7.2: Parse API response
- R7.3: Error handling
- R7.4: Large result handling (via FilesystemMiddleware)
"""

from .node import execute_node, ExecuteNode

__all__ = [
    "execute_node",
    "ExecuteNode",
]
