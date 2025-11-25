"""
Insight result model

Pydantic model for with_structured_output
"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class InsightItem(BaseModel):
    """Single insight item"""
    insight_type: str = Field(description="Insight type: trend, anomaly, comparison, correlation, distribution, ranking, composition, summary")
    title: str = Field(description="Insight title")
    description: str = Field(description="Insight description")
    importance: str = Field(description="Importance: high, medium, low")
    confidence: float = Field(description="Confidence: between 0-1")
    supporting_data: Dict[str, Any] = Field(description="Supporting data")
    related_fields: List[str] = Field(description="Related fields")
    actionable: bool = Field(description="Whether actionable")
    recommendations: List[str] = Field(default_factory=list, description="Action recommendations")


class InsightResult(BaseModel):
    """Insight analysis result"""
    insights: List[InsightItem] = Field(description="Insights list")
    summary: str = Field(description="Summary")
    key_findings: List[str] = Field(description="Key findings")
