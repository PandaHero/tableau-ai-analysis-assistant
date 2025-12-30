# -*- coding: utf-8 -*-
"""
InsightAgent Node Functions

LangGraph node functions for InsightAgent Subgraph.
These are state orchestration functions that call business logic components.

Architecture:
- Node functions handle State read/write and error handling
- Business logic is in components/ (EnhancedDataProfiler, SemanticChunker, etc.)
- This separation allows independent testing of business logic

Nodes:
- profiler_node: Phase 1 - Data profiling and chunking
- director_node: Phase 2 - Analysis decision making
- analyzer_node: Phase 3 - Chunk analysis with historical insight processing
"""

from .profiler_node import profiler_node
from .director_node import director_node
from .analyzer_node import analyzer_node

__all__ = ["profiler_node", "director_node", "analyzer_node"]
