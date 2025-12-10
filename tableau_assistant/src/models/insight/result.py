"""
Result-related model definitions

Contains data models for query results, insights, statistical analysis, etc.
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Dict, Any, Optional, Literal
from enum import Enum


# ========== Enum Types ==========

class InsightType(str, Enum):
    """Insight type"""
    TREND = "trend"  # Trend insight
    ANOMALY = "anomaly"  # Anomaly insight
    COMPARISON = "comparison"  # Comparison insight
    CORRELATION = "correlation"  # Correlation insight
    DISTRIBUTION = "distribution"  # Distribution insight
    RANKING = "ranking"  # Ranking insight
    COMPOSITION = "composition"  # Composition insight
    SUMMARY = "summary"  # Summary insight


class Importance(str, Enum):
    """Importance level"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AnomalyType(str, Enum):
    """Anomaly type"""
    OUTLIER = "outlier"  # Outlier
    SPIKE = "spike"  # Spike
    DROP = "drop"  # Drop
    MISSING = "missing"  # Missing value
    INCONSISTENT = "inconsistent"  # Inconsistent


class TrendDirection(str, Enum):
    """Trend direction"""
    INCREASING = "increasing"  # Increasing
    DECREASING = "decreasing"  # Decreasing
    STABLE = "stable"  # Stable
    FLUCTUATING = "fluctuating"  # Fluctuating


# ========== Query Result Models ==========

class SubtaskResult(BaseModel):
    """
    Subtask execution result
    
    Execution result for each sub-query
    """
    model_config = ConfigDict(extra="allow")
    
    question_id: str = Field(
        ...,
        description="Sub-question ID"
    )
    
    question: str = Field(
        ...,
        description="Sub-question description"
    )
    
    stage: int = Field(
        ...,
        description="Execution stage (for dependency management)",
        ge=1
    )
    
    query: Dict[str, Any] = Field(
        ...,
        description="VizQL query object"
    )
    
    data: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Query result data"
    )
    
    row_count: int = Field(
        ...,
        description="Number of result rows",
        ge=0
    )
    
    column_count: int = Field(
        ...,
        description="Number of result columns",
        ge=0
    )
    
    execution_time_ms: Optional[int] = Field(
        None,
        description="Execution time in milliseconds"
    )
    
    success: bool = Field(
        default=True,
        description="Whether execution succeeded"
    )
    
    error: Optional[str] = Field(
        None,
        description="Error message (if failed)"
    )
    
    retry_count: int = Field(
        default=0,
        description="Number of retries",
        ge=0
    )


class MergedData(BaseModel):
    """
    Merged data
    
    Data merged from multiple sub-query results
    """
    model_config = ConfigDict(extra="allow")
    
    data: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Merged data"
    )
    
    merge_strategy: str = Field(
        ...,
        description="Merge strategy (join/union/append, etc.)"
    )
    
    source_count: int = Field(
        ...,
        description="Number of source data",
        ge=1
    )
    
    row_count: int = Field(
        ...,
        description="Number of rows after merge",
        ge=0
    )
    
    column_count: int = Field(
        ...,
        description="Number of columns after merge",
        ge=0
    )
    
    quality_score: float = Field(
        ...,
        description="Data quality score (0-1)",
        ge=0.0,
        le=1.0
    )
    
    issues: List[str] = Field(
        default_factory=list,
        description="List of data quality issues"
    )


# ========== Statistical Analysis Models ==========

class DescriptiveStatistics(BaseModel):
    """Descriptive statistics"""
    model_config = ConfigDict(extra="forbid")
    
    field_name: str = Field(..., description="Field name")
    count: int = Field(..., description="Count", ge=0)
    mean: Optional[float] = Field(None, description="Mean value")
    median: Optional[float] = Field(None, description="Median value")
    std: Optional[float] = Field(None, description="Standard deviation")
    min: Optional[float] = Field(None, description="Minimum value")
    max: Optional[float] = Field(None, description="Maximum value")
    q25: Optional[float] = Field(None, description="25th percentile")
    q75: Optional[float] = Field(None, description="75th percentile")
    missing_count: int = Field(default=0, description="Number of missing values", ge=0)
    missing_rate: float = Field(default=0.0, description="Missing value rate", ge=0.0, le=1.0)


class AnomalyDetection(BaseModel):
    """Anomaly detection result"""
    model_config = ConfigDict(extra="forbid")
    
    field_name: str = Field(..., description="Field name")
    anomaly_type: AnomalyType = Field(..., description="Anomaly type")
    anomaly_values: List[Any] = Field(..., description="List of anomaly values")
    anomaly_indices: List[int] = Field(..., description="Indices of anomaly values")
    threshold: Optional[float] = Field(None, description="Threshold")
    method: str = Field(..., description="Detection method (z-score/iqr/isolation-forest, etc.)")
    confidence: float = Field(..., description="Confidence level (0-1)", ge=0.0, le=1.0)


class TrendAnalysis(BaseModel):
    """Trend analysis result"""
    model_config = ConfigDict(extra="forbid")
    
    field_name: str = Field(..., description="Field name")
    direction: TrendDirection = Field(..., description="Trend direction")
    slope: Optional[float] = Field(None, description="Slope (linear regression)")
    r_squared: Optional[float] = Field(None, description="R-squared value", ge=0.0, le=1.0)
    p_value: Optional[float] = Field(None, description="P-value", ge=0.0, le=1.0)
    is_significant: bool = Field(..., description="Whether significant (p<0.05)")
    change_rate: Optional[float] = Field(None, description="Rate of change")


class StatisticsResult(BaseModel):
    """
    Statistical analysis result
    
    Generated by statistics detector
    """
    model_config = ConfigDict(extra="allow")
    
    descriptive_stats: List[DescriptiveStatistics] = Field(
        default_factory=list,
        description="List of descriptive statistics"
    )
    
    anomalies: List[AnomalyDetection] = Field(
        default_factory=list,
        description="List of anomaly detection results"
    )
    
    trends: List[TrendAnalysis] = Field(
        default_factory=list,
        description="List of trend analysis results"
    )
    
    correlations: Dict[str, float] = Field(
        default_factory=dict,
        description="Correlation matrix (field pair -> correlation coefficient)"
    )
    
    data_quality_score: float = Field(
        ...,
        description="Data quality score (0-1)",
        ge=0.0,
        le=1.0
    )


# ========== Insight Models ==========

class Insight(BaseModel):
    """
    Single insight
    
    Generated by insight agent
    """
    model_config = ConfigDict(extra="allow")
    
    insight_type: InsightType = Field(
        ...,
        description="Insight type"
    )
    
    title: str = Field(
        ...,
        description="Insight title (one-sentence summary)"
    )
    
    description: str = Field(
        ...,
        description="Detailed insight description"
    )
    
    importance: Importance = Field(
        ...,
        description="Importance level"
    )
    
    confidence: float = Field(
        ...,
        description="Confidence level (0-1)",
        ge=0.0,
        le=1.0
    )
    
    supporting_data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Supporting data"
    )
    
    related_fields: List[str] = Field(
        default_factory=list,
        description="List of related fields"
    )
    
    actionable: bool = Field(
        default=False,
        description="Whether actionable"
    )
    
    recommendations: List[str] = Field(
        default_factory=list,
        description="Action recommendations"
    )


class InsightCollection(BaseModel):
    """
    Insight collection
    
    Summary of all insights
    """
    model_config = ConfigDict(extra="allow")
    
    insights: List[Insight] = Field(
        default_factory=list,
        description="List of insights"
    )
    
    summary: str = Field(
        ...,
        description="Insights summary"
    )
    
    key_findings: List[str] = Field(
        default_factory=list,
        description="Key findings (3-5 items)"
    )
    
    total_count: int = Field(
        ...,
        description="Total number of insights",
        ge=0
    )
    
    high_importance_count: int = Field(
        default=0,
        description="Number of high importance insights",
        ge=0
    )


# ========== Replanning Models ==========

class ReplanDecision(BaseModel):
    """
    Replanning decision
    
    Generated by replanning agent
    """
    model_config = ConfigDict(extra="allow")
    
    should_replan: bool = Field(
        ...,
        description="Whether replanning is needed"
    )
    
    reason: str = Field(
        ...,
        description="Decision rationale"
    )
    
    completeness_score: float = Field(
        ...,
        description="Completeness score (0-1)",
        ge=0.0,
        le=1.0
    )
    
    missing_aspects: List[str] = Field(
        default_factory=list,
        description="Missing aspects"
    )
    
    new_questions: List[str] = Field(
        default_factory=list,
        description="List of new questions (if replanning needed)"
    )
    
    confidence: float = Field(
        ...,
        description="Decision confidence (0-1)",
        ge=0.0,
        le=1.0
    )


# ========== Final Report Models ==========

class FinalReport(BaseModel):
    """
    Final report
    
    Generated by summary agent
    """
    model_config = ConfigDict(extra="allow")
    
    executive_summary: str = Field(
        ...,
        description="Executive summary (one-sentence answer)"
    )
    
    key_findings: List[str] = Field(
        default_factory=list,
        description="Key findings list (3-5 items)"
    )
    
    detailed_analysis: str = Field(
        ...,
        description="Detailed analysis"
    )
    
    insights: List[Insight] = Field(
        default_factory=list,
        description="Insights list"
    )
    
    visualizations: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Visualization data list"
    )
    
    recommendations: List[str] = Field(
        default_factory=list,
        description="Follow-up exploration recommendations (3-5 items)"
    )
    
    analysis_path: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Analysis path (showing analysis process)"
    )
    
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Metadata (token consumption, execution time, etc.)"
    )
    
    confidence: float = Field(
        ...,
        description="Overall confidence (0-1)",
        ge=0.0,
        le=1.0
    )


# ========== Helper Functions ==========

def create_insight(
    insight_type: InsightType,
    title: str,
    description: str,
    importance: Importance,
    confidence: float
) -> Insight:
    """Helper function to create insight"""
    return Insight(
        insight_type=insight_type,
        title=title,
        description=description,
        importance=importance,
        confidence=confidence
    )


def create_anomaly_detection(
    field_name: str,
    anomaly_type: AnomalyType,
    anomaly_values: List[Any],
    method: str,
    confidence: float
) -> AnomalyDetection:
    """Helper function to create anomaly detection result"""
    return AnomalyDetection(
        field_name=field_name,
        anomaly_type=anomaly_type,
        anomaly_values=anomaly_values,
        anomaly_indices=list(range(len(anomaly_values))),
        method=method,
        confidence=confidence
    )


# ========== Example Usage ==========

if __name__ == "__main__":
    # Example 1: Subtask result
    subtask_result = SubtaskResult(
        question_id="q1",
        question="Sales by region in 2016",
        stage=1,
        query={"fields": [], "filters": []},
        data=[
            {"Region": "East", "Sales": 5000000},
            {"Region": "North", "Sales": 3000000}
        ],
        row_count=2,
        column_count=2,
        execution_time_ms=1500,
        success=True
    )
    
    print("Subtask result example:")
    print(subtask_result.model_dump_json(indent=2))
    
    # Example 2: Insight
    insight = create_insight(
        insight_type=InsightType.COMPARISON,
        title="East region has highest sales",
        description="East region sales is 5M, accounting for 40% of total sales, 67% higher than North region",
        importance=Importance.HIGH,
        confidence=0.95
    )
    
    print("\nInsight example:")
    print(insight.model_dump_json(indent=2))
    
    # Example 3: Replan decision
    replan = ReplanDecision(
        should_replan=True,
        reason="Current analysis lacks profit margin dimension, unable to fully evaluate performance",
        completeness_score=0.6,
        missing_aspects=["Profit margin analysis", "Year-over-year growth"],
        new_questions=[
            "What is the profit margin for each region?",
            "What is the year-over-year sales growth rate?"
        ],
        confidence=0.85
    )
    
    print("\nReplan decision example:")
    print(replan.model_dump_json(indent=2))
    
    # Example 4: Final report
    report = FinalReport(
        executive_summary="East region has highest sales in 2016 (5M), but profit margin is low (5%)",
        key_findings=[
            "East region sales is 5M, accounting for 40% of total sales",
            "East region profit margin is only 5%, below average (8%)",
            "North region has lower sales but highest profit margin (12%)"
        ],
        detailed_analysis="Detailed analysis content...",
        insights=[insight],
        visualizations=[],
        recommendations=[
            "Analyze reasons for low profit margin in East region",
            "Learn from North region's high profit margin experience"
        ],
        analysis_path=[],
        metadata={
            "token_count": 15000,
            "execution_time_ms": 8500,
            "llm_calls": 5
        },
        confidence=0.90
    )
    
    print("\nFinal report example:")
    print(report.model_dump_json(indent=2))
