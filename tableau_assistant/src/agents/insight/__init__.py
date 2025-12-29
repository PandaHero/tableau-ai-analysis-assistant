"""
Insight Agent

LLM Agent that analyzes query results and generates insights.

Architecture (per insight-design.md):
- Dual LLM collaboration mode:
  - Coordinator LLM (CoordinatorPrompt): decides analysis order, accumulates insights, decides early stop
  - Analyst LLM (AnalystPrompt): analyzes single data chunk, generates structured insights
- AnalysisCoordinator coordinates the two LLMs
- ChunkAnalyzer encapsulates LLM calls

Import Note:
- Only import prompt at package level (no circular dependency)
- node.py needs separate import: from tableau_assistant.src.agents.insight.node import ...
- This avoids circular import:
  components/analyzer.py → agents/insight/prompt.py → agents/insight/__init__.py
  If __init__.py imports node.py, and node.py imports components, it would be circular
"""

from .prompt import (
    # Output Models
    InsightListOutput,
    CoordinatorDecisionOutput,
    # Prompt Classes
    CoordinatorPrompt,
    AnalystPrompt,
    DirectAnalysisPrompt,
    # Prompt Instances
    COORDINATOR_PROMPT,
    ANALYST_PROMPT,
    DIRECT_ANALYSIS_PROMPT,
)

# Components - Insight analysis components
from .components import (
    # Components
    EnhancedDataProfiler,
    AnomalyDetector,
    SemanticChunker,
    ChunkAnalyzer,
    InsightAccumulator,
    InsightSynthesizer,
    AnalysisCoordinator,
    StatisticalAnalyzer,
)

# Note: Do not import node.py at package level to avoid circular import
# When you need to use node, import directly:
# from tableau_assistant.src.agents.insight.node import insight_node, InsightAgent

__all__ = [
    # Output Models
    "InsightListOutput",
    "CoordinatorDecisionOutput",
    # Prompt Classes
    "CoordinatorPrompt",
    "AnalystPrompt",
    "DirectAnalysisPrompt",
    # Prompt Instances
    "COORDINATOR_PROMPT",
    "ANALYST_PROMPT",
    "DIRECT_ANALYSIS_PROMPT",
    # Components
    "EnhancedDataProfiler",
    "AnomalyDetector",
    "SemanticChunker",
    "ChunkAnalyzer",
    "InsightAccumulator",
    "InsightSynthesizer",
    "AnalysisCoordinator",
    "StatisticalAnalyzer",
]
