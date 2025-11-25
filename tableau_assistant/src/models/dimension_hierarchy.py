"""
Dimension hierarchy related data models

Contains:
1. DimensionAttributes - Hierarchy attributes for a single dimension
2. DimensionHierarchyResult - Dimension hierarchy inference result
"""
from typing import Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class DimensionAttributes(BaseModel):
    """Hierarchy attributes for a single dimension"""
    category: str = Field(description="Dimension category (geographic/time/product/customer/organization/financial/other)")
    category_detail: str = Field(description="Detailed category description, e.g.: geographic-province, time-year")
    level: int = Field(ge=1, le=5, description="Hierarchy level (1=coarsest, 2=coarse, 3=medium, 4=fine, 5=finest), must be 1-5")
    granularity: str = Field(description="Granularity description (coarsest/coarse/medium/fine/finest)")
    unique_count: int = Field(description="Unique value count, obtained from input data")
    parent_dimension: Optional[str] = Field(None, description="Parent dimension field name (coarser granularity)")
    child_dimension: Optional[str] = Field(None, description="Child dimension field name (finer granularity)")
    sample_values: List[str] = Field(description="Sample values list (max 10)")
    level_confidence: float = Field(ge=0.0, le=1.0, description="Confidence of hierarchy judgment (0-1)")
    reasoning: str = Field(description="Reasoning process explanation")
    
    @field_validator('level')
    @classmethod
    def validate_level(cls, v):
        """Ensure level is between 1-5"""
        if v > 5:
            return 5  # Values over 5 are set to 5 (finest granularity)
        elif v < 1:
            return 1  # Values under 1 are set to 1 (coarsest granularity)
        return v


class DimensionHierarchyResult(BaseModel):
    """Dimension hierarchy inference result"""
    dimension_hierarchy: Dict[str, DimensionAttributes] = Field(
        description="Dimension hierarchy dictionary, key is field name, value is dimension attributes"
    )


# ============= Exports =============

__all__ = [
    "DimensionAttributes",
    "DimensionHierarchyResult",
]
