# -*- coding: utf-8 -*-
"""
Insight Components - 洞察分析组件

渐进式洞察分析系统的三层架构：
- 协调层: AnalysisCoordinator (编排和策略选择)
- 处理层: DataProfiler, AnomalyDetector, SemanticChunker, ChunkAnalyzer
- 合成层: InsightAccumulator, InsightSynthesizer

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

# 1. Import models from core/models
from tableau_assistant.src.core.models import (
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
