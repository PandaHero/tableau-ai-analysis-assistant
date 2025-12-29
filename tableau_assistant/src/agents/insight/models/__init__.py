# -*- coding: utf-8 -*-
"""InsightAgent Models Package.

This package contains data models specific to the InsightAgent Subgraph.

Models:
- profile.py: EnhancedDataProfile, ContributorAnalysis, ConcentrationRisk, etc.
- insight.py: Insight, InsightQuality (migrated from core/models/insight.py)
- director.py: DirectorInput, DirectorDecision, DirectorOutputWithAccumulation
- analyst.py: AnalystOutputWithHistory, HistoricalInsightAction
"""

from .insight import (
    # Priority and Stats
    ChunkPriority,
    ColumnStats,
    SemanticGroup,
    DataProfile,
    # Anomaly
    AnomalyDetail,
    AnomalyResult,
    # Chunks
    DataChunk,
    PriorityChunk,
    TailDataSummary,
    # Insights
    InsightEvidence,
    Insight,
    InsightQuality,
    InsightResult,
    # Decisions
    NextBiteDecision,
    # Analysis Profile
    ClusterInfo,
    DataInsightProfile,
)

from .profile import (
    ContributorAnalysis,
    ConcentrationRisk,
    PeriodChangeAnalysis,
    TrendAnalysis,
    DimensionIndex,
    AnomalyIndex,
    EnhancedDataProfile,
    ChunkingStrategy,
)

from .director import (
    DirectorAction,
    DirectorInput,
    DirectorDecision,
    InsightAction,
    InsightActionItem,
    DirectorOutputWithAccumulation,
)

from .analyst import (
    HistoricalInsightActionType,
    HistoricalInsightAction,
    AnalystOutputWithHistory,
)

__all__ = [
    # From insight.py (migrated from core/models/insight.py)
    "ChunkPriority",
    "ColumnStats",
    "SemanticGroup",
    "DataProfile",
    "AnomalyDetail",
    "AnomalyResult",
    "DataChunk",
    "PriorityChunk",
    "TailDataSummary",
    "InsightEvidence",
    "Insight",
    "InsightQuality",
    "InsightResult",
    "NextBiteDecision",
    "ClusterInfo",
    "DataInsightProfile",
    # From profile.py
    "ContributorAnalysis",
    "ConcentrationRisk",
    "PeriodChangeAnalysis",
    "TrendAnalysis",
    "DimensionIndex",
    "AnomalyIndex",
    "EnhancedDataProfile",
    "ChunkingStrategy",
    # From director.py
    "DirectorAction",
    "DirectorInput",
    "DirectorDecision",
    "InsightAction",
    "InsightActionItem",
    "DirectorOutputWithAccumulation",
    # From analyst.py
    "HistoricalInsightActionType",
    "HistoricalInsightAction",
    "AnalystOutputWithHistory",
]
