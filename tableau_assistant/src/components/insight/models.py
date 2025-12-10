"""
Insight System Data Models - DEPRECATED

This module is deprecated. Please import from tableau_assistant.src.models.insight instead.

Example:
    # Old (deprecated):
    from tableau_assistant.src.components.insight.models import InsightResult
    
    # New (recommended):
    from tableau_assistant.src.models.insight import InsightResult
"""

# Re-export all models for backward compatibility
from tableau_assistant.src.models.insight import (
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
