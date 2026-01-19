# -*- coding: utf-8 -*-
"""
Insight Components - Progressive insight analysis components.

Architecture (Subgraph-based):
- Profiler: EnhancedDataProfiler (Tableau Pulse-style analysis)
- Director: AnalysisDirector (LLM-based decision making + insight accumulation)
- Analyzer: ChunkAnalyzer (LLM-based chunk analysis)
- Accumulator: InsightAccumulator (code-level deduplication helper)

Flow:
- profiler_node → director_node ↔ analyzer_node (loop)
- Director LLM handles insight accumulation and final summary generation
- No separate Synthesizer - Director generates final_summary when stopping

Requirements:
- R8.1: Progressive insight analysis
- R8.3: Semantic chunking
- R8.4: Chunk analysis with context
- R8.5: Insight accumulation and deduplication
- R8.7: Streaming output support
"""

# 1. Import models from agents/insight/models
from tableau_assistant.src.agents.insight.models import (
    DataProfile,
    ColumnStats,
    SemanticGroup,
    AnomalyResult,
    AnomalyDetail,
    DataChunk,
    Insight,
    InsightResult,
    ClusterInfo,
    DataInsightProfile,
    ChunkPriority,
    PriorityChunk,
    TailDataSummary,
    NextBiteDecision,
    InsightQuality,
)

# 2. Import components without LLM dependencies
from tableau_assistant.src.agents.insight.components.profiler import EnhancedDataProfiler
from tableau_assistant.src.agents.insight.components.anomaly_detector import AnomalyDetector
from tableau_assistant.src.agents.insight.components.chunker import SemanticChunker
from tableau_assistant.src.agents.insight.components.accumulator import InsightAccumulator
from tableau_assistant.src.agents.insight.components.statistical_analyzer import StatisticalAnalyzer
from tableau_assistant.src.agents.insight.components.utils import to_dataframe, format_insights_with_index

# 3. Import analyzer (depends on agents/insight/prompt.py)
from tableau_assistant.src.agents.insight.components.analyzer import ChunkAnalyzer

# 4. Import director (Task 3.5)
from tableau_assistant.src.agents.insight.components.director import AnalysisDirector


# Note: Node functions are in agents/insight/nodes/, not here

__all__ = [
    # Models (per data-models.md spec)
    "DataProfile",
    "ColumnStats",
    "SemanticGroup",
    "AnomalyResult",
    "AnomalyDetail",
    "DataChunk",
    "Insight",
    "InsightResult",
    # Phase 1 statistical analysis models
    "ClusterInfo",
    "DataInsightProfile",
    # Priority related
    "ChunkPriority",
    "PriorityChunk",
    "TailDataSummary",
    "NextBiteDecision",
    "InsightQuality",
    # Components
    "EnhancedDataProfiler",
    "AnomalyDetector",
    "SemanticChunker",
    "ChunkAnalyzer",
    "InsightAccumulator",
    "StatisticalAnalyzer",
    "AnalysisDirector",
    # Utilities
    "to_dataframe",
    "format_insights_with_index",
]
