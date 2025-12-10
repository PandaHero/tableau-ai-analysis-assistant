"""
Insight Models Package

Contains insight analysis related models.
"""

# From result.py (legacy insight models)
from tableau_assistant.src.models.insight.result import (
    # Enums
    InsightType,
    Importance,
    AnomalyType,
    TrendDirection,
    
    # Query results
    SubtaskResult,
    MergedData,
    
    # Statistical analysis
    DescriptiveStatistics,
    AnomalyDetection,
    TrendAnalysis,
    StatisticsResult,
    
    # Insights
    Insight as LegacyInsight,
    InsightCollection,
    
    # Final report
    FinalReport,
    
    # Helper functions
    create_insight,
    create_anomaly_detection,
)

# From models.py (progressive insight models)
from tableau_assistant.src.models.insight.models import (
    # Enums
    ChunkPriority,
    
    # Statistics models
    ColumnStats,
    SemanticGroup,
    DataProfile,
    
    # Anomaly models
    AnomalyDetail,
    AnomalyResult,
    
    # Chunk models
    DataChunk,
    TailDataSummary,
    PriorityChunk,
    
    # Insight models
    Insight,
    InsightQuality,
    InsightResult,
    
    # AI decision models
    NextBiteDecision,
    
    # Clustering models
    ClusterInfo,
    DataInsightProfile,
)

__all__ = [
    # Legacy (from result.py)
    "InsightType",
    "Importance",
    "AnomalyType",
    "TrendDirection",
    "SubtaskResult",
    "MergedData",
    "DescriptiveStatistics",
    "AnomalyDetection",
    "TrendAnalysis",
    "StatisticsResult",
    "LegacyInsight",
    "InsightCollection",
    "FinalReport",
    "create_insight",
    "create_anomaly_detection",
    
    # Progressive insight (from models.py)
    "ChunkPriority",
    "ColumnStats",
    "SemanticGroup",
    "DataProfile",
    "AnomalyDetail",
    "AnomalyResult",
    "DataChunk",
    "TailDataSummary",
    "PriorityChunk",
    "Insight",
    "InsightQuality",
    "InsightResult",
    "NextBiteDecision",
    "ClusterInfo",
    "DataInsightProfile",
]
