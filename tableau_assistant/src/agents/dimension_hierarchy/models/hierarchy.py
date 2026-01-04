# -*- coding: utf-8 -*-
"""Dimension Hierarchy Models.

Data models for dimension hierarchy inference.

Contains:
- DimensionAttributes: Hierarchy attributes for a single dimension
- DimensionHierarchyResult: Dimension hierarchy inference result

Note: Migrated from core/models/dimension_hierarchy.py per design document.
These are agent-specific models, not platform-agnostic core abstractions.
"""
from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator, model_validator

from tableau_assistant.src.core.models.enums import DimensionCategory


class DimensionAttributes(BaseModel):
    """Hierarchy attributes for a single dimension.
    
    <fill_order>
    1. category (ALWAYS)
    2. category_detail (ALWAYS)
    3. level (ALWAYS)
    4. granularity (ALWAYS, auto-match level)
    5. unique_count (ALWAYS)
    6. sample_values (ALWAYS)
    7. level_confidence (ALWAYS)
    8. reasoning (ALWAYS)
    9. parent_dimension (if certain)
    10. child_dimension (if certain)
    </fill_order>
    
    <examples>
    Province: {"category": "geography", "level": 2, "granularity": "coarse", "parent_dimension": null, "child_dimension": "City"}
    Month: {"category": "time", "level": 3, "granularity": "medium", "parent_dimension": "Quarter", "child_dimension": "Date"}
    </examples>
    
    <anti_patterns>
    X level and granularity mismatch: level=2 but granularity="finest"
    X Guessing parent/child when uncertain: should be null
    </anti_patterns>
    """
    
    category: DimensionCategory = Field(
        description="""<what>Dimension category</what>
<when>ALWAYS required</when>"""
    )
    
    category_detail: str = Field(
        description="""<what>Detailed category description</what>
<when>ALWAYS required</when>
<rule>Format: 'category-subcategory', e.g. 'geography-province'</rule>"""
    )
    
    level: int = Field(
        ge=1,
        le=5,
        description="""<what>Hierarchy level</what>
<when>ALWAYS required</when>
<rule>
- Level 1 (coarsest): country, year, top category
- Level 2 (coarse): province, quarter, category
- Level 3 (medium): city, month, subcategory
- Level 4 (fine): district, week, brand
- Level 5 (finest): address, date, SKU
</rule>"""
    )
    
    granularity: Literal["coarsest", "coarse", "medium", "fine", "finest"] = Field(
        description="""<what>Granularity description</what>
<when>ALWAYS required</when>
<rule>Must match level: 1=coarsest, 2=coarse, 3=medium, 4=fine, 5=finest</rule>
<dependency>One-to-one mapping with level</dependency>"""
    )
    
    unique_count: int = Field(
        description="""<what>Unique value count</what>
<when>ALWAYS required</when>"""
    )
    
    parent_dimension: Optional[str] = Field(
        default=None,
        description="""<what>Parent dimension field name (coarser granularity)</what>
<when>Fill when certain, null when uncertain</when>
<rule>Parent has smaller unique_count, broader semantics</rule>
<must_not>Guess when uncertain (should be null)</must_not>"""
    )
    
    child_dimension: Optional[str] = Field(
        default=None,
        description="""<what>Child dimension field name (finer granularity)</what>
<when>Fill when certain, null when uncertain</when>
<rule>Child has larger unique_count, more specific semantics</rule>
<must_not>Guess when uncertain (should be null)</must_not>"""
    )
    
    sample_values: List[str] = Field(
        description="""<what>Sample values list</what>
<when>ALWAYS required</when>
<rule>Maximum 10 values</rule>"""
    )
    
    level_confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="""<what>Level inference confidence</what>
<when>ALWAYS required</when>
<rule>0.9-1.0=clear semantics, 0.7-0.9=good match, 0.5-0.7=fuzzy, <0.5=very uncertain</rule>"""
    )
    
    reasoning: str = Field(
        description="""<what>Reasoning explanation</what>
<when>ALWAYS required</when>
<rule>Explain why this level/category was assigned</rule>"""
    )
    
    @field_validator('level')
    @classmethod
    def validate_level(cls, v):
        """确保 level 在 1-5 之间"""
        if v > 5:
            return 5
        elif v < 1:
            return 1
        return v
    
    @model_validator(mode='after')
    def validate_level_granularity_match(self) -> 'DimensionAttributes':
        """确保 level 和 granularity 一致"""
        level_to_granularity = {
            1: "coarsest",
            2: "coarse",
            3: "medium",
            4: "fine",
            5: "finest"
        }
        expected = level_to_granularity.get(self.level)
        if expected and self.granularity != expected:
            object.__setattr__(self, 'granularity', expected)
        return self


class DimensionHierarchyResult(BaseModel):
    """Dimension hierarchy inference result.
    
    <what>Dictionary of all dimension hierarchy attributes</what>
    
    <fill_order>
    1. dimension_hierarchy (ALWAYS)
    </fill_order>
    
    <examples>
    {"dimension_hierarchy": {"Province": {"category": "geography", "level": 2, ...}, "City": {"category": "geography", "level": 3, "parent_dimension": "Province", ...}}}
    </examples>
    """
    
    dimension_hierarchy: Dict[str, DimensionAttributes] = Field(
        description="""<what>Dimension hierarchy dictionary</what>
<when>ALWAYS required</when>
<rule>key is field name, value is DimensionAttributes</rule>"""
    )


__all__ = [
    "DimensionAttributes",
    "DimensionHierarchyResult",
]
