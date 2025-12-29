# -*- coding: utf-8 -*-
"""
Insight Components - Progressive insight analysis components.

Three-layer architecture for progressive insight analysis:
- Coordination layer: AnalysisCoordinator (orchestration and strategy selection)
- Processing layer: EnhancedDataProfiler, SemanticChunker, ChunkAnalyzer
- Synthesis layer: InsightAccumulator, InsightSynthesizer

Architecture (Task 3.3.1):
- EnhancedDataProfiler is the single entry point for profiling
- It internally delegates to StatisticalAnalyzer and AnomalyDetector
- AnalysisCoordinator only calls EnhancedDataProfiler, not individual analyzers

Requirements:
- R8.1: Progressive insight analysis
- R8.2: Strategy selection (direct/progressive/hybrid)
- R8.3: Semantic chunking
- R8.4: Chunk analysis with context
- R8.5: Insight accumulation and deduplication
- R8.6: Insight synthesis
- R8.7: Streaming output support

Import Order Note:
To avoid circular imports, import order matters:
1. models (no dependencies)
2. Components without LLM dependencies (profiler, anomaly_detector, chunker, accumulator, synthesizer, statistical_analyzer)
3. analyzer (depends on agents/insight/prompt.py)
4. coordinator (depends on analyzer)
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
from .profiler import EnhancedDataProfiler
from .anomaly_detector import AnomalyDetector
from .chunker import SemanticChunker
from .accumulator import InsightAccumulator
from .synthesizer import InsightSynthesizer
from .statistical_analyzer import StatisticalAnalyzer

# 3. Import analyzer (depends on agents/insight/prompt.py)
from .analyzer import ChunkAnalyzer

# 4. Import coordinator (depends on analyzer)
from .coordinator import AnalysisCoordinator

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
    "InsightSynthesizer",
    "AnalysisCoordinator",
    "StatisticalAnalyzer",
]
