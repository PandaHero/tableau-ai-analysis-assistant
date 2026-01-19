# -*- coding: utf-8 -*-
"""Enhanced Data Profile Models.

Data models for Tableau Pulse-aligned enhanced data profiling.

Contains:
- ContributorAnalysis: Top/Bottom contributor analysis
- ConcentrationRisk: Concentration risk detection
- PeriodChangeAnalysis: Period-over-period change analysis (MoM, YoY)
- TrendAnalysis: Trend detection and analysis
- DimensionIndex: Dimension value index for precise reading
- AnomalyIndex: Anomaly index grouped by severity
- ChunkingStrategy: Recommended chunking strategy
- EnhancedDataProfile: Complete enhanced profile with all analyses
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Dict, List, Any, Optional, Literal, Tuple
from enum import Enum

from tableau_assistant.src.agents.insight.models.insight import ColumnStats



class ChunkingStrategy(str, Enum):
    """Recommended chunking strategy for data analysis.
    
    <rule>
    - by_anomaly: Data has significant anomalies, isolate anomalies for priority analysis
    - by_change_point: Data has significant change points, split at change points
    - by_pareto: Data follows Pareto distribution, prioritize top contributors
    - by_semantic: Data has semantic groupings (time, category), group by semantic type
    - by_statistics: Use statistical properties to determine chunks
    - by_position: Default position-based chunking (top N, mid, tail)
    </rule>
    """
    BY_ANOMALY = "by_anomaly"
    BY_CHANGE_POINT = "by_change_point"
    BY_PARETO = "by_pareto"
    BY_SEMANTIC = "by_semantic"
    BY_STATISTICS = "by_statistics"
    BY_POSITION = "by_position"


class ContributorAnalysis(BaseModel):
    """Top/Bottom contributor analysis - Tableau Pulse style.
    
    <what>Identifies top and bottom contributors to a measure</what>
    
    <fill_order>
    1. dimension (ALWAYS)
    2. measure (ALWAYS)
    3. top_contributors (ALWAYS)
    4. bottom_contributors (ALWAYS)
    5. top_contribution_pct (ALWAYS)
    6. concentration_warning (if applicable)
    </fill_order>
    """
    model_config = ConfigDict(extra="forbid")
    
    dimension: str = Field(
        description="""<what>Dimension used for grouping</what>
<when>ALWAYS required</when>"""
    )
    measure: str = Field(
        description="""<what>Measure being analyzed</what>
<when>ALWAYS required</when>"""
    )
    top_contributors: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="""<what>Top N contributors with values and percentages</what>
<when>ALWAYS required</when>
<rule>Format: [{"value": "Category A", "amount": 1000, "percentage": 0.35}, ...]</rule>"""
    )
    bottom_contributors: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="""<what>Bottom N contributors with values and percentages</what>
<when>ALWAYS required</when>"""
    )
    top_contribution_pct: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="""<what>Percentage contributed by top N</what>
<when>ALWAYS required</when>
<rule>Sum of top_contributors percentages</rule>"""
    )
    concentration_warning: Optional[str] = Field(
        default=None,
        description="""<what>Warning if concentration is too high</what>
<when>top_contribution_pct > 0.8</when>
<rule>E.g., "Top 3 contributors account for 85% of total"</rule>"""
    )


class ConcentrationRisk(BaseModel):
    """Concentration risk detection - Tableau Pulse style.
    
    <what>Detects if data is overly concentrated in few values</what>
    
    <fill_order>
    1. dimension (ALWAYS)
    2. measure (ALWAYS)
    3. hhi_index (ALWAYS)
    4. risk_level (ALWAYS)
    5. top_n_for_80_pct (ALWAYS)
    6. recommendation (if risk_level != low)
    </fill_order>
    """
    model_config = ConfigDict(extra="forbid")
    
    dimension: str = Field(
        description="""<what>Dimension being analyzed</what>
<when>ALWAYS required</when>"""
    )
    measure: str = Field(
        description="""<what>Measure being analyzed</what>
<when>ALWAYS required</when>"""
    )
    hhi_index: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="""<what>Herfindahl-Hirschman Index (0-1)</what>
<when>ALWAYS required</when>
<rule>0=perfectly distributed, 1=single contributor</rule>"""
    )
    risk_level: Literal["low", "medium", "high", "critical"] = Field(
        default="low",
        description="""<what>Concentration risk level</what>
<when>ALWAYS required</when>
<rule>
- low: HHI < 0.15
- medium: 0.15 <= HHI < 0.25
- high: 0.25 <= HHI < 0.5
- critical: HHI >= 0.5
</rule>"""
    )
    top_n_for_80_pct: int = Field(
        default=0,
        description="""<what>Number of items contributing 80% of total</what>
<when>ALWAYS required</when>"""
    )
    recommendation: Optional[str] = Field(
        default=None,
        description="""<what>Recommendation for high concentration</what>
<when>risk_level in [medium, high, critical]</when>"""
    )


class PeriodChangeAnalysis(BaseModel):
    """Period-over-period change analysis - Tableau Pulse style.
    
    <what>Analyzes changes between time periods (MoM, YoY, etc.)</what>
    
    <fill_order>
    1. measure (ALWAYS)
    2. period_type (ALWAYS)
    3. current_value (ALWAYS)
    4. previous_value (ALWAYS)
    5. absolute_change (ALWAYS)
    6. percentage_change (ALWAYS)
    7. change_direction (ALWAYS)
    8. is_significant (ALWAYS)
    </fill_order>
    """
    model_config = ConfigDict(extra="forbid")
    
    measure: str = Field(
        description="""<what>Measure being compared</what>
<when>ALWAYS required</when>"""
    )
    period_type: Literal["MoM", "QoQ", "YoY", "WoW", "DoD", "custom"] = Field(
        description="""<what>Type of period comparison</what>
<when>ALWAYS required</when>
<rule>
- MoM: Month over Month
- QoQ: Quarter over Quarter
- YoY: Year over Year
- WoW: Week over Week
- DoD: Day over Day
- custom: Custom period
</rule>"""
    )
    current_value: float = Field(
        description="""<what>Current period value</what>
<when>ALWAYS required</when>"""
    )
    previous_value: float = Field(
        description="""<what>Previous period value</what>
<when>ALWAYS required</when>"""
    )
    absolute_change: float = Field(
        description="""<what>Absolute change (current - previous)</what>
<when>ALWAYS required</when>"""
    )
    percentage_change: float = Field(
        description="""<what>Percentage change</what>
<when>ALWAYS required</when>
<rule>(current - previous) / previous * 100</rule>"""
    )
    change_direction: Literal["up", "down", "stable"] = Field(
        description="""<what>Direction of change</what>
<when>ALWAYS required</when>
<rule>
- up: percentage_change > 1%
- down: percentage_change < -1%
- stable: -1% <= percentage_change <= 1%
</rule>"""
    )
    is_significant: bool = Field(
        default=False,
        description="""<what>Whether change is statistically significant</what>
<when>ALWAYS required</when>
<rule>abs(percentage_change) > 5% or exceeds historical variance</rule>"""
    )
    current_period: Optional[str] = Field(
        default=None,
        description="""<what>Current period label</what>
<when>Recommended</when>"""
    )
    previous_period: Optional[str] = Field(
        default=None,
        description="""<what>Previous period label</what>
<when>Recommended</when>"""
    )


class TrendAnalysis(BaseModel):
    """Trend detection and analysis - Tableau Pulse style.
    
    <what>Detects and analyzes trends in time series data</what>
    
    <fill_order>
    1. measure (ALWAYS)
    2. time_dimension (ALWAYS)
    3. trend_direction (ALWAYS)
    4. trend_strength (ALWAYS)
    5. slope (ALWAYS)
    6. r_squared (ALWAYS)
    7. change_points (if detected)
    8. forecast (optional)
    </fill_order>
    """
    model_config = ConfigDict(extra="forbid")
    
    measure: str = Field(
        description="""<what>Measure being analyzed</what>
<when>ALWAYS required</when>"""
    )
    time_dimension: str = Field(
        description="""<what>Time dimension used for trend analysis</what>
<when>ALWAYS required</when>"""
    )
    trend_direction: Literal["increasing", "decreasing", "stable", "volatile"] = Field(
        description="""<what>Overall trend direction</what>
<when>ALWAYS required</when>
<rule>
- increasing: positive slope, r² > 0.5
- decreasing: negative slope, r² > 0.5
- stable: abs(slope) < threshold, r² > 0.5
- volatile: r² < 0.5 (no clear trend)
</rule>"""
    )
    trend_strength: Literal["strong", "moderate", "weak"] = Field(
        description="""<what>Strength of the trend</what>
<when>ALWAYS required</when>
<rule>
- strong: r² >= 0.8
- moderate: 0.5 <= r² < 0.8
- weak: r² < 0.5
</rule>"""
    )
    slope: float = Field(
        description="""<what>Trend slope (rate of change per period)</what>
<when>ALWAYS required</when>"""
    )
    r_squared: float = Field(
        ge=0.0,
        le=1.0,
        description="""<what>R-squared value (goodness of fit)</what>
<when>ALWAYS required</when>"""
    )
    change_points: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="""<what>Detected change points in the trend</what>
<when>If change points detected</when>
<rule>Format: [{"index": 10, "date": "2024-06", "type": "increase"}, ...]</rule>"""
    )
    change_point_method: Optional[str] = Field(
        default=None,
        description="""<what>Method used for change point detection</what>
<when>If change points detected</when>
<rule>Values: "pelt" (ruptures PELT algorithm), "rolling_mean" (simple fallback)</rule>"""
    )
    forecast: Optional[Dict[str, Any]] = Field(
        default=None,
        description="""<what>Simple forecast based on trend</what>
<when>Optional</when>
<rule>Format: {"next_period": "2024-12", "predicted_value": 1500, "confidence": 0.8}</rule>"""
    )


class DimensionIndex(BaseModel):
    """Dimension value index for precise reading.
    
    <what>Index mapping dimension values to row indices for precise data access</what>
    
    <fill_order>
    1. dimension (ALWAYS)
    2. value_to_indices (ALWAYS)
    3. total_unique_values (ALWAYS)
    </fill_order>
    """
    model_config = ConfigDict(extra="forbid")
    
    dimension: str = Field(
        description="""<what>Dimension name</what>
<when>ALWAYS required</when>"""
    )
    value_to_indices: Dict[str, List[int]] = Field(
        default_factory=dict,
        description="""<what>Mapping from dimension value to row indices</what>
<when>ALWAYS required</when>
<rule>Format: {"Category A": [0, 5, 10], "Category B": [1, 2, 3], ...}</rule>"""
    )
    total_unique_values: int = Field(
        default=0,
        description="""<what>Total number of unique dimension values</what>
<when>ALWAYS required</when>"""
    )
    value_counts: Dict[str, int] = Field(
        default_factory=dict,
        description="""<what>Count of rows for each dimension value</what>
<when>Recommended</when>"""
    )


class AnomalyIndex(BaseModel):
    """Anomaly index grouped by severity.
    
    <what>Index of anomalies grouped by severity level for prioritized analysis</what>
    
    <fill_order>
    1. total_anomalies (ALWAYS)
    2. anomaly_ratio (ALWAYS)
    3. by_severity (ALWAYS)
    4. by_column (ALWAYS)
    </fill_order>
    """
    model_config = ConfigDict(extra="forbid")
    
    total_anomalies: int = Field(
        default=0,
        description="""<what>Total number of anomalies detected</what>
<when>ALWAYS required</when>"""
    )
    anomaly_ratio: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="""<what>Ratio of anomalies to total rows</what>
<when>ALWAYS required</when>"""
    )
    by_severity: Dict[str, List[int]] = Field(
        default_factory=dict,
        description="""<what>Anomaly indices grouped by severity</what>
<when>ALWAYS required</when>
<rule>Format: {"critical": [5, 10], "high": [2, 8], "medium": [1, 3, 7], "low": [4, 6]}</rule>"""
    )
    by_column: Dict[str, List[int]] = Field(
        default_factory=dict,
        description="""<what>Anomaly indices grouped by column</what>
<when>ALWAYS required</when>
<rule>Format: {"Sales": [5, 10, 2], "Profit": [8, 1]}</rule>"""
    )
    detection_method: str = Field(
        default="IQR",
        description="""<what>Method used for anomaly detection</what>
<when>ALWAYS required</when>
<rule>IQR, Z-Score, Isolation Forest, etc.</rule>"""
    )


class EnhancedDataProfile(BaseModel):
    """Enhanced data profile with Tableau Pulse-aligned analyses.
    
    <what>Complete enhanced profile including all Tableau Pulse style analyses</what>
    
    <fill_order>
    1. row_count, column_count (ALWAYS)
    2. statistics (ALWAYS)
    3. contributor_analyses (if categorical dimensions exist)
    4. concentration_risks (if categorical dimensions exist)
    5. period_changes (if time dimension exists)
    6. trend_analyses (if time dimension exists)
    7. dimension_indices (ALWAYS)
    8. anomaly_index (ALWAYS)
    9. recommended_strategy (ALWAYS)
    </fill_order>
    """
    model_config = ConfigDict(extra="forbid")
    
    # Basic profile
    row_count: int = Field(
        description="""<what>Total number of rows</what>
<when>ALWAYS required</when>"""
    )
    column_count: int = Field(
        description="""<what>Total number of columns</what>
<when>ALWAYS required</when>"""
    )
    statistics: Dict[str, ColumnStats] = Field(
        default_factory=dict,
        description="""<what>Statistics for each numeric column</what>
<when>ALWAYS required</when>"""
    )
    
    # Tableau Pulse style analyses
    contributor_analyses: List[ContributorAnalysis] = Field(
        default_factory=list,
        description="""<what>Top/Bottom contributor analyses</what>
<when>If categorical dimensions exist</when>"""
    )
    concentration_risks: List[ConcentrationRisk] = Field(
        default_factory=list,
        description="""<what>Concentration risk assessments</what>
<when>If categorical dimensions exist</when>"""
    )
    period_changes: List[PeriodChangeAnalysis] = Field(
        default_factory=list,
        description="""<what>Period-over-period change analyses</what>
<when>If time dimension exists</when>"""
    )
    trend_analyses: List[TrendAnalysis] = Field(
        default_factory=list,
        description="""<what>Trend analyses</what>
<when>If time dimension exists</when>"""
    )
    
    # Indices for precise reading
    dimension_indices: List[DimensionIndex] = Field(
        default_factory=list,
        description="""<what>Dimension value indices for precise reading</what>
<when>ALWAYS required</when>"""
    )
    anomaly_index: Optional[AnomalyIndex] = Field(
        default=None,
        description="""<what>Anomaly index for prioritized analysis</what>
<when>ALWAYS required</when>"""
    )
    
    # Recommended strategy
    recommended_strategy: ChunkingStrategy = Field(
        default=ChunkingStrategy.BY_POSITION,
        description="""<what>Recommended chunking strategy</what>
<when>ALWAYS required</when>"""
    )
    strategy_reason: str = Field(
        default="",
        description="""<what>Reason for recommended strategy</what>
<when>Recommended</when>"""
    )
    
    # Summary for LLM
    profile_summary: str = Field(
        default="",
        description="""<what>Natural language summary of the profile</what>
<when>Recommended</when>
<rule>Brief summary highlighting key findings for Director LLM</rule>"""
    )


__all__ = [
    "ChunkingStrategy",
    "ContributorAnalysis",
    "ConcentrationRisk",
    "PeriodChangeAnalysis",
    "TrendAnalysis",
    "DimensionIndex",
    "AnomalyIndex",
    "EnhancedDataProfile",
]
