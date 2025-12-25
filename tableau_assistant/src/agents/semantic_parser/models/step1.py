"""Step 1 models - Semantic understanding and question restatement.

Step 1 is the "Intuition" phase of the LLM combination architecture.
It understands the user question, restates it as a complete standalone question,
extracts structured What/Where/How, and classifies intent.

直接使用核心层模型：
- MeasureField: 度量字段（包含排序）
- DimensionField: 维度字段
- Filter 及其子类: 过滤器（SetFilter, DateRangeFilter, TopNFilter 等）
"""

from pydantic import BaseModel, ConfigDict, Field

from tableau_assistant.src.core.models.fields import MeasureField, DimensionField
from tableau_assistant.src.core.models.filters import Filter
from tableau_assistant.src.core.models.enums import (
    FilterType,
    HowType,
    IntentType,
)


class What(BaseModel):
    """What - Target measures (part of Three-Element Model)."""
    model_config = ConfigDict(extra="forbid")
    
    measures: list[MeasureField] = Field(
        default_factory=list,
        description="List of measures to compute"
    )


class Where(BaseModel):
    """Where - Dimensions and filters (part of Three-Element Model)."""
    model_config = ConfigDict(extra="forbid")
    
    dimensions: list[DimensionField] = Field(
        default_factory=list,
        description="List of dimensions for grouping"
    )
    
    filters: list[Filter] = Field(
        default_factory=list,
        description="List of filter conditions (SetFilter, DateRangeFilter, TopNFilter, etc.)"
    )


class Intent(BaseModel):
    """Intent classification result."""
    model_config = ConfigDict(extra="forbid")
    
    type: IntentType = Field(
        description="Intent type"
    )
    
    reasoning: str = Field(
        description="Reasoning for classification"
    )


class FilterValidationCheck(BaseModel):
    """Single filter validation check result (filled by LLM)."""
    model_config = ConfigDict(extra="forbid")
    
    filter_field: str = Field(
        description="Field name of the filter being checked"
    )
    
    filter_type: FilterType = Field(
        description="Type of the filter"
    )
    
    is_complete: bool = Field(
        description="Whether filter has all required fields"
    )
    
    missing_fields: list[str] = Field(
        default_factory=list,
        description="List of missing required fields"
    )
    
    note: str = Field(
        default="",
        description="Explanation or suggestion for fixing"
    )


class Step1Validation(BaseModel):
    """Step 1 self-validation (LLM validates filter completeness)."""
    model_config = ConfigDict(extra="forbid")
    
    filter_checks: list[FilterValidationCheck] = Field(
        default_factory=list,
        description="Validation result for each filter"
    )
    
    all_valid: bool = Field(
        description="All filters are complete"
    )
    
    issues: list[str] = Field(
        default_factory=list,
        description="List of validation issues"
    )


class Step1Output(BaseModel):
    """Step 1 output: Semantic understanding and question restatement."""
    model_config = ConfigDict(extra="forbid")
    
    restated_question: str = Field(
        description="Complete standalone question in natural language"
    )
    
    what: What = Field(
        description="Target measures"
    )
    
    where: Where = Field(
        description="Dimensions + filters"
    )
    
    how_type: HowType = Field(
        default=HowType.SIMPLE,
        description="Computation complexity"
    )
    
    intent: Intent = Field(
        default_factory=lambda: Intent(type=IntentType.DATA_QUERY, reasoning="Default: assumed data query"),
        description="Intent classification + reasoning"
    )
    
    validation: Step1Validation = Field(
        default_factory=lambda: Step1Validation(all_valid=True),
        description="Self-validation of filter completeness"
    )


__all__ = [
    "What",
    "Where",
    "Intent",
    "FilterValidationCheck",
    "Step1Validation",
    "Step1Output",
]
