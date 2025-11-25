"""
Replanning decision model

Pydantic model for with_structured_output
"""
from typing import List, Optional
from pydantic import BaseModel, Field


class ReplanDecision(BaseModel):
    """Replanning decision result"""
    should_replan: bool = Field(description="Whether replanning is needed")
    reason: str = Field(description="Decision reason")
    completeness_score: float = Field(description="Completeness score: between 0-1")
    missing_aspects: List[str] = Field(default_factory=list, description="Missing aspects")
    new_questions: List[str] = Field(default_factory=list, description="New questions list")
    confidence: float = Field(description="Confidence: between 0-1")
