"""
Dimension hierarchy related data models

Contains:
1. DimensionAttributes - Hierarchy attributes for a single dimension
2. DimensionHierarchyResult - Dimension hierarchy inference result
"""
from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


class DimensionAttributes(BaseModel):
    """Hierarchy attributes for a single dimension.
    
    EXAMPLES:
    
    Input: {"name": "省份", "unique_count": 31, "samples": ["广东", "北京", "上海"]}
    Output: {
        "category": "geographic",
        "category_detail": "geographic-province",
        "level": 2,
        "granularity": "coarse",
        "unique_count": 31,
        "parent_dimension": null,
        "child_dimension": null,
        "sample_values": ["广东", "北京", "上海"],
        "level_confidence": 0.9,
        "reasoning": "Province-level geographic dimension with 31 unique values"
    }
    
    Input: {"name": "产品名称", "unique_count": 1500, "samples": ["iPhone 15", "MacBook Pro"]}
    Output: {
        "category": "product",
        "category_detail": "product-item",
        "level": 5,
        "granularity": "finest",
        "unique_count": 1500,
        "parent_dimension": null,
        "child_dimension": null,
        "sample_values": ["iPhone 15", "MacBook Pro"],
        "level_confidence": 0.85,
        "reasoning": "Product name with high cardinality indicates finest granularity"
    }
    
    ANTI-PATTERNS:
    - Setting level > 5 or level < 1
    - Guessing parent/child when uncertain (use null instead)
    - Mismatching level and granularity (level=1 must be granularity="coarsest")
    """
    
    category: Literal["geographic", "time", "product", "customer", "organization", "financial", "other"] = Field(
        description="""Dimension category.

WHAT: High-level classification of the dimension
WHEN: Always required
HOW: Choose based on semantic meaning

VALUES:
- geographic: Location-related (country, province, city)
- time: Time-related (year, quarter, month)
- product: Product-related (category, brand, SKU)
- customer: Customer-related (segment, type)
- organization: Org-related (department, team)
- financial: Finance-related (cost center, account)
- other: None of the above"""
    )
    
    category_detail: str = Field(
        description="""Detailed category description.

WHAT: Specific sub-category within the main category
WHEN: Always required
HOW: Format as "category-subcategory"

EXAMPLES:
- "geographic-province"
- "geographic-city"
- "time-year"
- "time-month"
- "product-category"
- "product-sku" """
    )
    
    level: int = Field(
        ge=1,
        le=5,
        description="""Hierarchy level (1-5 scale).

WHAT: Position in hierarchy from coarsest to finest
WHEN: Always required
HOW: Integer 1-5 based on granularity

VALUES:
- 1 (coarsest): Country, Year, Top Category
- 2 (coarse): Province/State, Quarter, Category
- 3 (medium): City, Month, Subcategory
- 4 (fine): District, Week, Brand
- 5 (finest): Address, Date, SKU, Transaction ID

PRIORITY for determination:
1. Explicit indicators in name (Level 1/2/3)
2. Semantic meaning (Year vs Date)
3. Unique count (lower = coarser, same category)"""
    )
    
    granularity: Literal["coarsest", "coarse", "medium", "fine", "finest"] = Field(
        description="""Granularity description.

WHAT: Text description matching level
WHEN: Always required
HOW: Must match level value
DEPENDENCY: Must be consistent with level

VALUES:
- level=1 -> "coarsest"
- level=2 -> "coarse"
- level=3 -> "medium"
- level=4 -> "fine"
- level=5 -> "finest" """
    )
    
    unique_count: int = Field(
        description="""Unique value count.

WHAT: Number of distinct values
WHEN: Always required (from input data)
HOW: Copy from input metadata"""
    )
    
    parent_dimension: Optional[str] = Field(
        None,
        description="""Parent dimension field name.

WHAT: Coarser dimension in same hierarchy
WHEN: Only if clearly identifiable
HOW: Field name string or null

EXAMPLES:
- Province's parent might be Country
- City's parent might be Province
- null if uncertain (DO NOT GUESS)"""
    )
    
    child_dimension: Optional[str] = Field(
        None,
        description="""Child dimension field name.

WHAT: Finer dimension in same hierarchy
WHEN: Only if clearly identifiable
HOW: Field name string or null

EXAMPLES:
- Province's child might be City
- Category's child might be Subcategory
- null if uncertain (DO NOT GUESS)"""
    )
    
    sample_values: List[str] = Field(
        description="""Sample values list.

WHAT: Example values from the dimension
WHEN: Always required (from input data)
HOW: Copy from input, max 10 values"""
    )
    
    level_confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="""Confidence of hierarchy judgment.

WHAT: How confident in the level assignment
WHEN: Always required
HOW: Float 0.0-1.0

VALUES:
- 0.9-1.0: Clear semantics, explicit indicators
- 0.7-0.9: Good semantic match
- 0.5-0.7: Ambiguous signals
- 0.0-0.5: Very uncertain"""
    )
    
    reasoning: str = Field(
        description="""Reasoning explanation.

WHAT: Why this level/category was assigned
WHEN: Always required
HOW: 1-2 sentences explaining key factors"""
    )
    
    @field_validator('level')
    @classmethod
    def validate_level(cls, v):
        """Ensure level is between 1-5."""
        if v > 5:
            return 5
        elif v < 1:
            return 1
        return v
    
    @model_validator(mode='after')
    def validate_level_granularity_match(self) -> 'DimensionAttributes':
        """Ensure level and granularity are consistent."""
        level_to_granularity = {
            1: "coarsest",
            2: "coarse",
            3: "medium",
            4: "fine",
            5: "finest"
        }
        expected = level_to_granularity.get(self.level)
        if expected and self.granularity != expected:
            # Auto-correct granularity to match level
            object.__setattr__(self, 'granularity', expected)
        return self


class DimensionHierarchyResult(BaseModel):
    """Dimension hierarchy inference result.
    
    EXAMPLE:
    
    Input dimensions: ["省份", "城市", "销售额"]
    Output: {
        "dimension_hierarchy": {
            "省份": {
                "category": "geographic",
                "category_detail": "geographic-province",
                "level": 2,
                "granularity": "coarse",
                ...
            },
            "城市": {
                "category": "geographic",
                "category_detail": "geographic-city",
                "level": 3,
                "granularity": "medium",
                "parent_dimension": "省份",
                ...
            }
        }
    }
    
    Note: Only dimension fields are included, not measures like "销售额".
    """
    
    dimension_hierarchy: Dict[str, DimensionAttributes] = Field(
        description="""Dimension hierarchy dictionary.

WHAT: Map of dimension names to their hierarchy attributes
WHEN: Always required
HOW: Key is field name, value is DimensionAttributes

EXAMPLES:
- {"省份": {...}, "城市": {...}}
- {"年份": {...}, "月份": {...}}"""
    )


# ============= Exports =============

__all__ = [
    "DimensionAttributes",
    "DimensionHierarchyResult",
]
