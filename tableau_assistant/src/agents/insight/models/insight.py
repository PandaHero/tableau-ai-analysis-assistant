# -*- coding: utf-8 -*-
"""Insight Models.

Data models for insight analysis.
Migrated from core/models/insight.py to agents/insight/models/insight.py.

Contains:
- ChunkPriority: Data chunk priority
- ColumnStats: Column statistics
- SemanticGroup: Semantic grouping
- DataProfile: Data profile
- AnomalyDetail/AnomalyResult: Anomaly detection results
- DataChunk/PriorityChunk: Data chunks
- TailDataSummary: Tail data summary
- InsightEvidence/Insight: Insights and evidence
- InsightQuality: Insight quality assessment
- NextBiteDecision: Next analysis decision
- ClusterInfo: Cluster information
- DataInsightProfile: Data insight profile
- InsightResult: Insight result
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Dict, List, Any, Optional, Literal, Union
from enum import IntEnum


class ChunkPriority(IntEnum):
    """Data chunk priority, lower value = higher priority."""
    URGENT = 1    # Anomalies, highest priority
    HIGH = 2      # Top 100 rows
    MEDIUM = 3    # Rows 101-500
    LOW = 4       # Rows 501-1000
    DEFERRED = 5  # 1000+ rows (tail data)


class ColumnStats(BaseModel):
    """Statistics for a single numeric column."""
    model_config = ConfigDict(extra="forbid")
    
    mean: float = Field(description="Mean value")
    median: float = Field(description="Median value")
    std: float = Field(description="Standard deviation")
    min: float = Field(description="Minimum value")
    max: float = Field(description="Maximum value")
    q25: float = Field(description="25th percentile")
    q75: float = Field(description="75th percentile")


class SemanticGroup(BaseModel):
    """Columns grouped by semantic type."""
    model_config = ConfigDict(extra="forbid")
    
    type: Literal["time", "category", "numeric", "geography"] = Field(
        description="Semantic type: time/geography/category/numeric"
    )
    columns: List[str] = Field(description="Column names in this semantic group")


class DataProfile(BaseModel):
    """Dataset profile with statistics and semantic groupings."""
    model_config = ConfigDict(extra="forbid")
    
    row_count: int = Field(description="Number of rows")
    column_count: int = Field(description="Number of columns")
    density: float = Field(ge=0.0, le=1.0, description="Data density (non-null ratio)")
    statistics: Dict[str, ColumnStats] = Field(default_factory=dict, description="Statistics for each numeric column")
    semantic_groups: List[SemanticGroup] = Field(default_factory=list, description="Semantic group list")


class AnomalyDetail(BaseModel):
    """Details of a single anomaly."""
    model_config = ConfigDict(extra="forbid")
    
    index: int = Field(description="Anomaly row index")
    values: Dict[str, Any] = Field(description="Values of the anomaly row")
    reason: str = Field(description="Anomaly reason")
    column: Optional[str] = Field(default=None, description="Column where anomaly occurred")
    severity: float = Field(default=0.0, ge=0.0, le=1.0, description="Severity (0-1)")


class AnomalyResult(BaseModel):
    """Anomaly detection result."""
    model_config = ConfigDict(extra="forbid")
    
    outliers: List[int] = Field(default_factory=list, description="Anomaly row indices")
    anomaly_ratio: float = Field(default=0.0, ge=0.0, le=1.0, description="Anomaly ratio")
    anomaly_details: List[AnomalyDetail] = Field(default_factory=list, description="Anomaly details list")


class DataChunk(BaseModel):
    """Data chunk for progressive analysis."""
    model_config = ConfigDict(extra="forbid")
    
    data: List[Dict[str, Any]] = Field(description="Data records list")
    chunk_id: int = Field(description="Chunk ID")
    chunk_name: str = Field(description="Chunk name")
    row_count: int = Field(description="Row count")
    column_names: List[str] = Field(description="Column names list")
    group_key: Optional[str] = Field(default=None, description="Group key")
    group_value: Optional[Union[str, int, float, bool]] = Field(default=None, description="Group value")


class TailDataSummary(BaseModel):
    """Tail data summary (1000+ rows)."""
    model_config = ConfigDict(extra="forbid")
    
    total_rows: int = Field(description="Total rows in tail data")
    sample_data: List[Dict[str, Any]] = Field(default_factory=list, description="Sample data (max 100 rows)")
    statistics: Dict[str, Any] = Field(default_factory=dict, description="Statistics")
    anomaly_count: int = Field(default=0, description="Anomaly count in tail data")
    patterns: Dict[str, Any] = Field(default_factory=dict, description="Detected patterns")


class PriorityChunk(BaseModel):
    """Data chunk with priority."""
    model_config = ConfigDict(extra="forbid")
    
    chunk_id: int = Field(description="Chunk ID")
    chunk_type: str = Field(description="Chunk type: anomalies/top_data/mid_data/low_data/tail_data/cluster_N/segment_N etc.")
    priority: int = Field(description="Priority (1-5, lower is higher)")
    data: List[Dict[str, Any]] = Field(default_factory=list, description="Data records list")
    tail_summary: Optional[TailDataSummary] = Field(default=None, description="Tail data summary (only for tail_data type)")
    row_count: int = Field(description="Row count")
    column_names: List[str] = Field(default_factory=list, description="Column names list")
    description: str = Field(default="", description="Chunk description")
    estimated_value: str = Field(default="unknown", description="Estimated value: high/medium/low/potential/unknown")



class InsightEvidence(BaseModel):
    """Insight evidence - specific data supporting the insight."""
    model_config = ConfigDict(extra="forbid")
    
    metric_name: Optional[str] = Field(default=None, description="Metric name")
    metric_value: Optional[float] = Field(default=None, description="Metric value")
    comparison_value: Optional[float] = Field(default=None, description="Comparison value")
    ratio: Optional[float] = Field(default=None, description="Ratio")
    percentage: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Percentage")
    period: Optional[str] = Field(default=None, description="Time period")
    additional_data: Optional[Dict[str, Union[str, int, float, bool]]] = Field(default=None, description="Additional data")


class Insight(BaseModel):
    """Single insight - Analyst LLM output.
    
    <what>Single data insight with type, title, description and evidence</what>
    
    <fill_order>
    1. type (ALWAYS)
    2. title (ALWAYS)
    3. description (ALWAYS)
    4. importance (ALWAYS)
    5. evidence (recommended)
    </fill_order>
    
    <examples>
    Trend: {"type": "trend", "title": "Sales growing steadily", "description": "Sales increased 15% MoM over last 6 months", "importance": 0.9}
    Anomaly: {"type": "anomaly", "title": "Store A sales abnormally high", "description": "Store A sales is 5x the second place", "importance": 0.95}
    </examples>
    
    <anti_patterns>
    X No data support: "Sales are high" (should include specific values)
    X Duplicate existing insights
    </anti_patterns>
    """
    model_config = ConfigDict(extra="forbid")
    
    type: Literal["trend", "anomaly", "comparison", "pattern"] = Field(
        description="""<what>Insight type</what>
<when>ALWAYS required</when>
<rule>
- trend: temporal change trend
- anomaly: outlier/unexpected finding
- comparison: comparative analysis
- pattern: distribution/regularity
</rule>"""
    )
    title: str = Field(
        description="""<what>Insight title</what>
<when>ALWAYS required</when>
<rule>One sentence summary with key data</rule>"""
    )
    description: str = Field(
        description="""<what>Insight description</what>
<when>ALWAYS required</when>
<rule>Detailed explanation, must reference specific data</rule>
<must_not>Generic description without data support</must_not>"""
    )
    importance: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="""<what>Importance score</what>
<when>ALWAYS required</when>
<rule>0.9-1.0=critical finding, 0.7-0.9=important, 0.5-0.7=moderate, <0.5=minor</rule>"""
    )
    evidence: Optional[InsightEvidence] = Field(
        default=None,
        description="""<what>Supporting evidence</what>
<when>Recommended</when>
<rule>Include specific metric values, comparison values, ratios etc.</rule>"""
    )


class InsightQuality(BaseModel):
    """Insight quality assessment - Director LLM output.
    
    <what>Quality assessment of current insights</what>
    
    <fill_order>
    1. completeness (ALWAYS)
    2. confidence (ALWAYS)
    3. question_answered (ALWAYS)
    4. need_more_data (ALWAYS)
    </fill_order>
    """
    model_config = ConfigDict(extra="forbid")
    
    completeness: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="""<what>Completeness score</what>
<when>ALWAYS required</when>
<rule>>=0.8 mostly complete, 0.5-0.8 partially complete, <0.5 incomplete</rule>"""
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="""<what>Confidence score</what>
<when>ALWAYS required</when>
<rule>Based on data quality and analysis depth</rule>"""
    )
    need_more_data: bool = Field(
        default=True,
        description="""<what>Whether more data is needed</what>
<when>ALWAYS required</when>
<rule>completeness < 0.8 -> true</rule>"""
    )
    question_answered: bool = Field(
        default=False,
        description="""<what>Whether core question is answered</what>
<when>ALWAYS required</when>
<rule>Whether insight directly answers user question</rule>"""
    )


class NextBiteDecision(BaseModel):
    """Next bite decision - Director LLM output.
    
    <what>Director decides whether to continue analysis and which chunk to analyze</what>
    
    <fill_order>
    1. should_continue (ALWAYS)
    2. completeness_estimate (ALWAYS)
    3. reason (ALWAYS)
    4. next_chunk_id (if should_continue=True)
    </fill_order>
    
    <examples>
    Continue: {"should_continue": true, "next_chunk_id": 3, "reason": "Anomaly chunk needs investigation", "completeness_estimate": 0.6}
    Stop: {"should_continue": false, "next_chunk_id": null, "reason": "Core question answered", "completeness_estimate": 0.9}
    </examples>
    
    <anti_patterns>
    X should_continue=true but next_chunk_id=null
    X completeness_estimate >= 0.9 but should_continue=true
    </anti_patterns>
    """
    model_config = ConfigDict(extra="forbid")
    
    should_continue: bool = Field(
        description="""<what>Whether to continue analysis</what>
<when>ALWAYS required</when>
<rule>completeness < 0.8 and high-value chunks exist -> true</rule>"""
    )
    next_chunk_id: Optional[int] = Field(
        default=None,
        description="""<what>Next chunk ID to analyze</what>
<when>Required when should_continue=True</when>
<dependency>should_continue == True</dependency>"""
    )
    reason: str = Field(
        default="",
        description="""<what>Decision reason</what>
<when>ALWAYS required</when>
<rule>Explain why continue/stop</rule>"""
    )
    completeness_estimate: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="""<what>Completeness estimate</what>
<when>ALWAYS required</when>
<rule>>=0.8 mostly complete, 0.5-0.8 partially complete, <0.5 just started</rule>"""
    )


class ClusterInfo(BaseModel):
    """Cluster information."""
    model_config = ConfigDict(extra="forbid")
    
    cluster_id: int = Field(description="Cluster ID")
    center: Dict[str, float] = Field(default_factory=dict, description="Cluster center")
    size: int = Field(description="Cluster size (row count)")
    label: str = Field(default="", description="Cluster label: high-performer/medium/low-performer/anomaly")
    indices: List[int] = Field(default_factory=list, description="Row indices in this cluster")


class DataInsightProfile(BaseModel):
    """Data insight profile - Phase 1 statistical/ML analysis result."""
    model_config = ConfigDict(extra="forbid")
    
    # Distribution analysis
    distribution_type: Literal["normal", "long_tail", "bimodal", "uniform", "unknown"] = Field(
        default="unknown", description="Distribution type"
    )
    skewness: float = Field(default=0.0, description="Skewness")
    kurtosis: float = Field(default=0.0, description="Kurtosis")
    
    # Pareto analysis
    pareto_ratio: float = Field(default=0.0, ge=0.0, le=1.0, description="Pareto ratio (top 20% contribution)")
    pareto_threshold: float = Field(default=0.0, ge=0.0, le=1.0, description="Pareto threshold (data ratio contributing 80%)")
    
    # Anomaly detection
    anomaly_indices: List[int] = Field(default_factory=list, description="Anomaly row indices")
    anomaly_ratio: float = Field(default=0.0, ge=0.0, le=1.0, description="Anomaly ratio")
    anomaly_method: str = Field(default="IQR", description="Anomaly detection method: IQR/Z-Score/Isolation Forest")
    
    # Clustering analysis
    clusters: List[ClusterInfo] = Field(default_factory=list, description="Clustering result")
    optimal_k: int = Field(default=0, description="Optimal cluster count")
    clustering_method: str = Field(default="KMeans", description="Clustering method")
    
    # Trend detection (optional)
    trend: Optional[Literal["increasing", "decreasing", "stable"]] = Field(default=None, description="Trend direction")
    trend_slope: Optional[float] = Field(default=None, description="Trend slope")
    change_points: Optional[List[int]] = Field(default=None, description="Change point indices")
    
    # Correlation analysis
    correlations: Dict[str, float] = Field(default_factory=dict, description="Column correlations")
    
    # Statistics
    statistics: Dict[str, ColumnStats] = Field(default_factory=dict, description="Statistics for each numeric column")
    
    # Recommended chunking strategy
    recommended_chunking_strategy: Literal[
        "by_cluster", "by_change_point", "by_pareto", "by_semantic", "by_statistics", "by_position"
    ] = Field(default="by_position", description="Recommended chunking strategy")
    
    # Primary measure column
    primary_measure: Optional[str] = Field(default=None, description="Primary measure column name")
    
    # Top N data summary
    top_n_summary: List[Dict[str, Any]] = Field(default_factory=list, description="Top N data summary")


class InsightResult(BaseModel):
    """Insight result - Insight Agent final output."""
    model_config = ConfigDict(extra="forbid")
    
    # Core output fields
    summary: Optional[str] = Field(default=None, description="One sentence summary")
    findings: List[Insight] = Field(default_factory=list, description="Insight list")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Overall confidence")
    
    # Phase 1 statistical/ML analysis result
    data_insight_profile: Optional[DataInsightProfile] = Field(default=None, description="Data insight profile")
    
    # Analysis process info
    strategy_used: str = Field(default="direct", description="Analysis strategy used: direct/progressive/hybrid")
    chunks_analyzed: int = Field(default=0, description="Number of chunks analyzed")
    total_rows_analyzed: int = Field(default=0, description="Total rows analyzed")
    execution_time: float = Field(default=0.0, description="Execution time (seconds)")
    
    # Replan related fields
    need_more_data: bool = Field(default=False, description="Whether more data is needed")
    missing_aspects: List[str] = Field(default_factory=list, description="Missing aspects")
    exploration_rounds: int = Field(default=1, description="Exploration rounds")
    questions_executed: int = Field(default=0, description="Questions executed")


__all__ = [
    # Priority and Stats
    "ChunkPriority",
    "ColumnStats",
    "SemanticGroup",
    "DataProfile",
    # Anomaly
    "AnomalyDetail",
    "AnomalyResult",
    # Chunks
    "DataChunk",
    "PriorityChunk",
    "TailDataSummary",
    # Insights
    "InsightEvidence",
    "Insight",
    "InsightQuality",
    "InsightResult",
    # Decisions
    "NextBiteDecision",
    # Analysis Profile
    "ClusterInfo",
    "DataInsightProfile",
]
