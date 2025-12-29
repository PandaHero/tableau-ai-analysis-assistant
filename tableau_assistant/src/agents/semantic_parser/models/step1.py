"""Step 1 models - Semantic understanding and question restatement.

Uses core layer models: MeasureField, DimensionField, Filter subclasses.
"""

from pydantic import BaseModel, ConfigDict, Field

from tableau_assistant.src.core.models.fields import MeasureField, DimensionField
from tableau_assistant.src.core.models.filters import (
    SetFilter,
    DateRangeFilter,
    NumericRangeFilter,
    TextMatchFilter,
    TopNFilter,
)
from tableau_assistant.src.core.models.enums import (
    FilterType,
    HowType,
    IntentType,
)

# Union type for all filter subclasses
FilterUnion = SetFilter | DateRangeFilter | NumericRangeFilter | TextMatchFilter | TopNFilter


class What(BaseModel):
    """Target measures.
    
    <fill_order>
    1. measures (extract from restated_question)
    </fill_order>
    
    <rule>
    Extract only the base measures mentioned in question.
    Do NOT add derived measures (like "Last Year Sales") - those are computed in Step2.
    </rule>
    
    <anti_patterns>
    X Adding same measure twice with different aliases
    X Adding computed measures like "Last Year Sales", "Growth Rate"
    </anti_patterns>
    """
    model_config = ConfigDict(extra="forbid")
    
    measures: list[MeasureField] = Field(
        default_factory=list,
        description="""<what>Base measures to compute</what>
<when>Question asks about amounts, counts, or values</when>
<must_not>Add same measure twice, add derived/computed measures</must_not>"""
    )


class Where(BaseModel):
    """Dimensions and filters.
    
    <fill_order>
    1. dimensions (grouping fields)
    2. filters (value constraints)
    </fill_order>
    
    <examples>
    Grouping: {"dimensions": [{"field_name": "City"}], "filters": []}
    Filtering: {"dimensions": [], "filters": [{"field_name": "City", "filter_type": "SET", "values": ["Beijing"]}]}
    </examples>
    
    <anti_patterns>
    X Adding values to DimensionField
    X Confusing grouping with filtering
    </anti_patterns>
    """
    model_config = ConfigDict(extra="forbid")
    
    dimensions: list[DimensionField] = Field(
        default_factory=list,
        description="""<what>Grouping fields for slicing data</what>
<when>Question asks "by X", "for each X", "per X"</when>
<must_not>Add values field - DimensionField has no values</must_not>"""
    )
    filters: list[FilterUnion] = Field(
        default_factory=list,
        description="""<what>Value constraints to filter data</what>
<when>Question specifies values: "in Beijing", "= X", date ranges</when>
<rule>Specific value -> SetFilter, date range -> DateRangeFilter</rule>"""
    )


class Intent(BaseModel):
    """Intent classification."""
    model_config = ConfigDict(extra="forbid")
    
    type: IntentType = Field(
        description="""<what>Query intent type</what>
<when>ALWAYS</when>"""
    )
    reasoning: str = Field(
        description="""<what>Explanation for classification</what>
<when>ALWAYS</when>"""
    )


class FilterValidationCheck(BaseModel):
    """Filter validation check."""
    model_config = ConfigDict(extra="forbid")
    
    filter_field: str = Field(
        description="""<what>Field being filtered</what>
<when>ALWAYS</when>"""
    )
    filter_type: FilterType = Field(
        description="""<what>Type of filter applied</what>
<when>ALWAYS</when>"""
    )
    is_complete: bool = Field(
        description="""<what>Whether filter has all required fields</what>
<when>ALWAYS</when>"""
    )
    missing_fields: list[str] = Field(
        default_factory=list,
        description="""<what>List of missing required fields</what>
<when>is_complete=False</when>"""
    )
    note: str = Field(
        default="",
        description="""<what>Additional notes</what>
<when>Optional</when>"""
    )


class Step1Validation(BaseModel):
    """Self-validation of filter completeness."""
    model_config = ConfigDict(extra="forbid")
    
    filter_checks: list[FilterValidationCheck] = Field(
        default_factory=list,
        description="""<what>Validation results for each filter</what>
<when>filters exist</when>"""
    )
    all_valid: bool = Field(
        description="""<what>Whether all filters are complete</what>
<when>ALWAYS</when>"""
    )
    issues: list[str] = Field(
        default_factory=list,
        description="""<what>List of validation issues</what>
<when>all_valid=False</when>"""
    )


class Step1Output(BaseModel):
    """Step 1 output: semantic understanding.
    
    <fill_order>
    1. restated_question (merge history + current, translate to English)
    2. what (extract from restated_question)
    3. where (extract from restated_question)
    4. how_type (classify from restated_question)
    5. intent (classify from restated_question)
    6. validation (validate filters)
    </fill_order>
    
    <rule>
    CRITICAL: All fields (what, where, how_type, intent) must be derived from restated_question, NOT from original question.
    </rule>
    """
    model_config = ConfigDict(extra="forbid")
    
    restated_question: str = Field(
        description="""<what>Complete standalone question in English</what>
<when>ALWAYS - fill this FIRST</when>
<must_not>Lose information from history</must_not>"""
    )
    what: What = Field(
        description="""<what>Target measures</what>
<when>ALWAYS</when>
<rule>Extract from restated_question, not original</rule>"""
    )
    where: Where = Field(
        description="""<what>Dimensions and filters</what>
<when>ALWAYS</when>
<rule>Extract from restated_question. Use current_time to calculate concrete date ranges for relative terms like "this year", "last month"</rule>"""
    )
    how_type: HowType = Field(
        default=HowType.SIMPLE,
        description="""<what>Computation complexity</what>
<when>ALWAYS</when>
<rule>Analyze restated_question for complexity keywords</rule>"""
    )
    intent: Intent = Field(
        default_factory=lambda: Intent(type=IntentType.DATA_QUERY, reasoning="Default"),
        description="""<what>Intent classification</what>
<when>ALWAYS</when>
<rule>Classify based on restated_question</rule>"""
    )
    validation: Step1Validation = Field(
        default_factory=lambda: Step1Validation(all_valid=True),
        description="""<what>Self-validation result</what>
<when>ALWAYS</when>"""
    )


__all__ = [
    "What",
    "Where",
    "Intent",
    "FilterValidationCheck",
    "Step1Validation",
    "Step1Output",
]
