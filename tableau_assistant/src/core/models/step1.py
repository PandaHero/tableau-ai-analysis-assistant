"""Step 1 models - Semantic understanding and question restatement.

Step 1 is the "Intuition" phase of the LLM combination architecture.
It understands the user question, restates it as a complete standalone question,
extracts structured What/Where/How, and classifies intent.

Includes LLM self-validation for filter completeness:
- DATE_RANGE filters must have at least one of start_date or end_date
- TOP_N filters must have n and by_field
- SET filters must have values
"""

from datetime import date
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .enums import (
    AggregationType,
    DateGranularity,
    FilterType,
    HowType,
    IntentType,
    SortDirection,
)


class MeasureSpec(BaseModel):
    """Measure specification in Step 1 output.
    
    <examples>
    Amount/revenue/sales: {"field": "Sales", "aggregation": "SUM"}
    Count/quantity/number of items: {"field": "Order ID", "aggregation": "COUNTD"}
    Average/mean: {"field": "Price", "aggregation": "AVG"}
    </examples>
    
    <anti_patterns>
    X "order count" with aggregation=SUM (should be COUNTD)
    X "number of customers" with aggregation=SUM (should be COUNT or COUNTD)
    </anti_patterns>
    """
    model_config = ConfigDict(extra="forbid")
    
    field: str = Field(
        description="""<what>Business term for the measure</what>
<when>ALWAYS required</when>"""
    )
    
    aggregation: AggregationType = Field(
        default=AggregationType.SUM,
        description="""<what>Aggregation function inferred from user intent</what>
<when>ALWAYS required</when>"""
    )
    
    sort_direction: SortDirection | None = Field(
        default=None,
        description="""<what>Sort direction for this measure</what>
<when>When user specifies sorting</when>"""
    )
    
    sort_priority: int = Field(
        default=0,
        description="""<what>Sort priority (lower = higher priority)</what>
<when>For multi-measure sorting, 0 = primary sort</when>"""
    )


class DimensionSpec(BaseModel):
    """Dimension specification in Step 1 output.
    
    <examples>
    Date with granularity: {"field": "Order Date", "granularity": "MONTH"}
    Non-date dimension: {"field": "Province", "granularity": null}
    </examples>
    
    <anti_patterns>
    X Using granularity word as field name: {"field": "Month"} (should be {"field": "Order Date", "granularity": "MONTH"})
    X Missing granularity for time-based grouping: "by month" without granularity=MONTH
    </anti_patterns>
    """
    model_config = ConfigDict(extra="forbid")
    
    field: str = Field(
        description="""<what>Business term for the dimension</what>
<when>ALWAYS required</when>
<rule>Use actual date field name (e.g., "Order Date"), not granularity word (e.g., "Month")</rule>"""
    )
    
    granularity: DateGranularity | None = Field(
        default=None,
        description="""<what>Time granularity for date fields</what>
<when>REQUIRED when user mentions time periods</when>
<rule>Infer from keywords: by month/monthly/per month -> MONTH | by quarter/quarterly -> QUARTER | by year/yearly/annual -> YEAR | by week/weekly -> WEEK | by day/daily -> DAY</rule>"""
    )


class FilterSpec(BaseModel):
    """Filter specification in Step 1 output.
    
    <what>Filter condition for data query</what>
    
    <fill_order>
    1. field (ALWAYS)
    2. type (ALWAYS)
    3. values (if SET)
    4. start_date, end_date (if DATE_RANGE)
    5. n, by_field, direction (if TOP_N)
    </fill_order>
    
    <examples>
    SET filter: {"field": "city", "type": "SET", "values": ["Beijing"]}
    DATE_RANGE filter: {"field": "order_date", "type": "DATE_RANGE", "start_date": "2024-01-01", "end_date": "2024-12-31"}
    TOP_N filter: {"field": "city", "type": "TOP_N", "n": 5, "by_field": "sales", "direction": "DESC"}
    </examples>
    
    <anti_patterns>
    X Year constraint with type=SET (should be DATE_RANGE)
    X DATE_RANGE without start_date or end_date
    X top N without by_field (must specify measure to rank by)
    </anti_patterns>
    """
    model_config = ConfigDict(extra="forbid")
    
    field: str = Field(
        description="""<what>Field to filter on</what>
<when>ALWAYS required</when>"""
    )
    
    type: FilterType = Field(
        description="""<what>Filter type</what>
<when>ALWAYS required</when>"""
    )
    
    # For SET filters
    values: list[str] | None = Field(
        default=None,
        description="""<what>Filter values</what>
<when>ONLY for type=SET</when>
<dependency>type == SET</dependency>"""
    )
    
    # For DATE_RANGE filters - LLM calculates concrete dates
    start_date: str | None = Field(
        default=None,
        description="""<what>Start date in YYYY-MM-DD format</what>
<when>REQUIRED for type=DATE_RANGE</when>
<dependency>type == DATE_RANGE</dependency>
<rule>Calculate based on user intent and current_time</rule>"""
    )
    
    end_date: str | None = Field(
        default=None,
        description="""<what>End date in YYYY-MM-DD format</what>
<when>REQUIRED for type=DATE_RANGE</when>
<dependency>type == DATE_RANGE</dependency>
<rule>Calculate based on user intent and current_time</rule>"""
    )
    
    # For TOP_N filters
    n: int | None = Field(
        default=None,
        description="""<what>Number of top/bottom items</what>
<when>REQUIRED for type=TOP_N</when>
<dependency>type == TOP_N</dependency>"""
    )
    
    by_field: str | None = Field(
        default=None,
        description="""<what>Measure field to rank by</what>
<when>REQUIRED for type=TOP_N</when>
<dependency>type == TOP_N</dependency>"""
    )
    
    direction: SortDirection | None = Field(
        default=None,
        description="""<what>Sort direction for TOP_N</what>
<when>For type=TOP_N, default DESC for top N, ASC for bottom N</when>
<dependency>type == TOP_N</dependency>"""
    )
    
    @field_validator('start_date', 'end_date')
    @classmethod
    def validate_date_format(cls, v: str | None) -> str | None:
        """Validate date string is in YYYY-MM-DD format."""
        if v is None:
            return v
        try:
            date.fromisoformat(v)
            return v
        except (ValueError, TypeError) as e:
            raise ValueError(f"Invalid date format '{v}'. Expected YYYY-MM-DD format.") from e


class What(BaseModel):
    """What - Target measures (part of Three-Element Model)."""
    model_config = ConfigDict(extra="forbid")
    
    measures: list[MeasureSpec] = Field(
        default_factory=list,
        description="""<what>List of measures to compute</what>
<when>ALWAYS required</when>"""
    )


class Where(BaseModel):
    """Where - Dimensions and filters (part of Three-Element Model)."""
    model_config = ConfigDict(extra="forbid")
    
    dimensions: list[DimensionSpec] = Field(
        default_factory=list,
        description="""<what>List of dimensions for grouping</what>
<when>Usually required</when>"""
    )
    
    filters: list[FilterSpec] = Field(
        default_factory=list,
        description="""<what>List of filter conditions</what>
<when>When user specifies filtering</when>"""
    )


class Intent(BaseModel):
    """Intent classification result."""
    model_config = ConfigDict(extra="forbid")
    
    type: IntentType = Field(
        description="""<what>Intent type</what>
<when>ALWAYS required</when>"""
    )
    
    reasoning: str = Field(
        description="""<what>Reasoning for classification</what>
<when>ALWAYS required</when>"""
    )


class FilterValidationCheck(BaseModel):
    """Single filter validation check result (filled by LLM)."""
    model_config = ConfigDict(extra="forbid")
    
    filter_field: str = Field(
        description="""<what>Field name of the filter being checked</what>
<when>ALWAYS required</when>"""
    )
    
    filter_type: FilterType = Field(
        description="""<what>Type of the filter</what>
<when>ALWAYS required</when>"""
    )
    
    is_complete: bool = Field(
        description="""<what>Whether filter has all required fields</what>
<when>ALWAYS required</when>
<rule>DATE_RANGE: has start_date OR end_date | TOP_N: has n AND by_field | SET: has values</rule>"""
    )
    
    missing_fields: list[str] = Field(
        default_factory=list,
        description="""<what>List of missing required fields</what>
<when>If is_complete=False</when>
<examples>["start_date", "end_date"], ["n", "by_field"], ["values"]</examples>"""
    )
    
    note: str = Field(
        default="",
        description="""<what>Explanation or suggestion for fixing</what>
<when>Recommended when is_complete=False</when>"""
    )


class Step1Validation(BaseModel):
    """Step 1 self-validation (LLM validates filter completeness).
    
    <fill_order>
    1. filter_checks (one per filter, empty if no filters)
    2. all_valid
    3. issues (if any)
    </fill_order>
    
    <examples>
    No filters: {"filter_checks": [], "all_valid": true, "issues": []}
    Valid filter: {"filter_checks": [{"filter_field": "date", "filter_type": "DATE_RANGE", "is_complete": true}], "all_valid": true, "issues": []}
    </examples>
    
    <anti_patterns>
    X all_valid=true when any filter_check has is_complete=false
    X Missing filter_checks entry for a filter in where.filters
    </anti_patterns>
    """
    model_config = ConfigDict(extra="forbid")
    
    filter_checks: list[FilterValidationCheck] = Field(
        default_factory=list,
        description="""<what>Validation result for each filter</what>
<when>One entry per filter in where.filters</when>
<rule>Empty list if no filters</rule>"""
    )
    
    all_valid: bool = Field(
        description="""<what>All filters are complete</what>
<when>ALWAYS required</when>
<rule>True only if all filter_checks have is_complete=True, or no filters exist</rule>"""
    )
    
    issues: list[str] = Field(
        default_factory=list,
        description="""<what>List of validation issues</what>
<when>If all_valid=False</when>
<examples>["DATE_RANGE filter 'order_date' missing start_date and end_date"]</examples>"""
    )


class Step1Output(BaseModel):
    """Step 1 output: Semantic understanding and question restatement.
    
    <what>Restated question + structured What/Where/How + intent classification + self-validation</what>
    
    <fill_order>
    1. restated_question (ALWAYS first)
    2. what (ALWAYS)
    3. where (ALWAYS)
    4. how_type (ALWAYS)
    5. intent (ALWAYS)
    6. validation (ALWAYS - self-check filter completeness)
    </fill_order>
    
    <examples>
    Simple: {"restated_question": "Group by province, calculate total sales", "how_type": "SIMPLE", "validation": {"all_valid": true, "filter_checks": [], "issues": []}}
    With filter: {"restated_question": "Show 2024 sales by month", "where": {"filters": [{"field": "date", "type": "DATE_RANGE", "start_date": "2024-01-01", "end_date": "2024-12-31"}]}, "validation": {"all_valid": true, "filter_checks": [{"filter_field": "date", "filter_type": "DATE_RANGE", "is_complete": true}], "issues": []}}
    </examples>
    
    <anti_patterns>
    X Losing scope modifiers: "monthly ranking" becomes "rank by sales" (lost "monthly")
    X Using technical field names: {"field": "[Sales].[Amount]"}
    X DATE_RANGE filter without dates: validation.all_valid must be false
    </anti_patterns>
    """
    model_config = ConfigDict(extra="forbid")
    
    restated_question: str = Field(
        description="""<what>Complete standalone question in natural language</what>
<when>ALWAYS required</when>
<must_not>Lose scope keywords (will cause wrong computation scope)</must_not>"""
    )
    
    what: What = Field(
        description="""<what>Target measures</what>
<when>ALWAYS required</when>"""
    )
    
    where: Where = Field(
        description="""<what>Dimensions + filters</what>
<when>ALWAYS required</when>"""
    )
    
    how_type: HowType = Field(
        default=HowType.SIMPLE,
        description="""<what>Computation complexity</what>
<when>ALWAYS required</when>"""
    )
    
    intent: Intent = Field(
        default_factory=lambda: Intent(type=IntentType.DATA_QUERY, reasoning="Default: assumed data query"),
        description="""<what>Intent classification + reasoning</what>
<when>ALWAYS required</when>"""
    )
    
    validation: Step1Validation = Field(
        default_factory=lambda: Step1Validation(all_valid=True),
        description="""<what>Self-validation of filter completeness</what>
<when>ALWAYS required</when>
<rule>Check each filter has required fields based on its type</rule>"""
    )
