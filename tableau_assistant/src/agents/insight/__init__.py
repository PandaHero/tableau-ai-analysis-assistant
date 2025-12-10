"""
Insight Agent

LLM Agent that analyzes query results and generates insights.

Architecture:
- Calls AnalysisCoordinator for progressive analysis
- Generates final insight report
- Supports streaming output

Design Decision (per insight-design.md):
- Insight Agent is a workflow node that calls AnalysisCoordinator
- AnalysisCoordinator orchestrates the analysis flow (pure code)
- ChunkAnalyzer is the ONLY component that calls LLM
- All LLM prompts are defined in prompt.py

Requirements:
- R8.1: Progressive insight analysis
- R8.7: Streaming output support
"""

from .node import insight_node, insight_node_streaming, InsightAgent
from .prompt import (
    INSIGHT_SYSTEM_PROMPT,
    CHUNK_USER_TEMPLATE,
    FULL_ANALYSIS_USER_TEMPLATE,
)

__all__ = [
    "insight_node",
    "insight_node_streaming",
    "InsightAgent",
    # Prompts
    "INSIGHT_SYSTEM_PROMPT",
    "CHUNK_USER_TEMPLATE",
    "FULL_ANALYSIS_USER_TEMPLATE",
]
