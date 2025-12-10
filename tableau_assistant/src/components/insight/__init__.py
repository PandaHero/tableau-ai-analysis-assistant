"""
Insight Components

Progressive insight analysis system with three-layer architecture:
- Coordinator Layer: AnalysisCoordinator (orchestration and strategy selection)
- Processing Layer: DataProfiler, AnomalyDetector, SemanticChunker, ChunkAnalyzer
- Synthesis Layer: InsightAccumulator, InsightSynthesizer

Requirements:
- R8.1: Progressive insight analysis
- R8.2: Strategy selection (direct/progressive/hybrid)
- R8.3: Semantic chunking
- R8.4: Chunk analysis with context
- R8.5: Insight accumulation and deduplication
- R8.6: Insight synthesis
- R8.7: Streaming output support
"""

from .models import (
    DataProfile,
    ColumnStats,
    SemanticGroup,
    AnomalyResult,
    AnomalyDetail,
    DataChunk,
    Insight,
    InsightResult,
    # Phase 1 统计分析模型
    ClusterInfo,
    DataInsightProfile,
    # 优先级相关
    ChunkPriority,
    PriorityChunk,
    TailDataSummary,
    NextBiteDecision,
    InsightQuality,
)
from .profiler import DataProfiler
from .anomaly_detector import AnomalyDetector
from .chunker import SemanticChunker
from .analyzer import ChunkAnalyzer
from .accumulator import InsightAccumulator
from .synthesizer import InsightSynthesizer
from .coordinator import AnalysisCoordinator
from .statistical_analyzer import StatisticalAnalyzer

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
    # Phase 1 统计分析模型
    "ClusterInfo",
    "DataInsightProfile",
    # 优先级相关
    "ChunkPriority",
    "PriorityChunk",
    "TailDataSummary",
    "NextBiteDecision",
    "InsightQuality",
    # Components
    "DataProfiler",
    "AnomalyDetector",
    "SemanticChunker",
    "ChunkAnalyzer",
    "InsightAccumulator",
    "InsightSynthesizer",
    "AnalysisCoordinator",
    "StatisticalAnalyzer",
]
