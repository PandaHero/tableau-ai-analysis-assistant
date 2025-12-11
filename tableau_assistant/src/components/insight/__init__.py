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

Import Order Note:
为避免循环导入，导入顺序很重要：
1. models（无依赖）
2. 无 LLM 依赖的组件（profiler, anomaly_detector, chunker, accumulator, synthesizer, statistical_analyzer）
3. analyzer（依赖 agents/insight/prompt.py）
4. coordinator（依赖 analyzer）
"""

# 1. Import models from centralized models package
from tableau_assistant.src.models.insight import (
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

# 2. Import components without LLM dependencies
from .profiler import DataProfiler
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
