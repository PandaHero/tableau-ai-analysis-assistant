"""
Insight Agent

LLM Agent that analyzes query results and generates insights.

Architecture (per design.md):
- Director LLM: orchestrates progressive analysis, decides what to analyze next, manages insight accumulation
- Analyst LLM: analyzes single data chunk, generates structured insights, suggests historical insight actions

Directory structure:
- prompts/ - Prompt template classes
- models/ - All data models (including LLM output models)
- components/ - Business logic components
- nodes/ - LangGraph node functions
- subgraph.py - LangGraph Subgraph factory

IMPORTANT - Circular Import Prevention:
- Do NOT import subgraph.py or node.py at package level
- These modules import state.py which imports orchestration/workflow/state.py
- orchestration/workflow/state.py imports Insight from this package
- Importing subgraph/node here would create a circular import

When you need to use subgraph or node, import directly:
    from tableau_assistant.src.agents.insight.subgraph import create_insight_subgraph
    from tableau_assistant.src.agents.insight.node import insight_node
"""

from tableau_assistant.src.agents.insight.prompts import (
    # Prompt Classes
    AnalystPrompt,
    AnalystPromptWithHistory,
    DirectorPrompt,
    # Prompt Instances
    ANALYST_PROMPT,
    ANALYST_PROMPT_WITH_HISTORY,
    DIRECTOR_PROMPT,
)

# Components - Insight analysis components
from tableau_assistant.src.agents.insight.components import (
    EnhancedDataProfiler,
    AnomalyDetector,
    SemanticChunker,
    ChunkAnalyzer,
    InsightAccumulator,
    StatisticalAnalyzer,
    AnalysisDirector,
)

# NOTE: Do NOT import subgraph or node at package level to avoid circular import
# The circular import chain is:
#   orchestration/workflow/state.py → agents/insight/models (Insight)
#   → agents/insight/__init__.py → agents/insight/subgraph.py
#   → agents/insight/state.py → orchestration/workflow/state.py (CYCLE!)
#
# Import directly when needed:
#   from tableau_assistant.src.agents.insight.subgraph import create_insight_subgraph
#   from tableau_assistant.src.agents.insight.node import insight_node

__all__ = [
    # Prompt Classes
    "AnalystPrompt",
    "AnalystPromptWithHistory",
    "DirectorPrompt",
    # Prompt Instances
    "ANALYST_PROMPT",
    "ANALYST_PROMPT_WITH_HISTORY",
    "DIRECTOR_PROMPT",
    # Components
    "EnhancedDataProfiler",
    "AnomalyDetector",
    "SemanticChunker",
    "ChunkAnalyzer",
    "InsightAccumulator",
    "StatisticalAnalyzer",
    "AnalysisDirector",
    # NOTE: create_insight_subgraph and insight_node are NOT exported here
    # Import them directly from their modules to avoid circular import
]
