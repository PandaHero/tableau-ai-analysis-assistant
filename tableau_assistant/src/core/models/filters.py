"""Filter models for the semantic layer.

Platform-agnostic filter definitions.
"""

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .enums import (
    FilterType,
    SortDirection,
    TextMatchType,
)


class Filter(BaseModel):
    """Base filter class.
    
    All filters inherit from this base class.
    """
    model_config = ConfigDict(extra="forbid")
    
    field_name: str = Field(
        description="""<what>Field to filter on</what>
<when>ALWAYS required</when>
<rule>Use business term from user question</rule>"""
    )
    
    filter_type: FilterType = Field(
        description="""<what>Type of filter</what>
<when>ALWAYS required</when>"""
    )


class SetFilter(Filter):
    """Set filter - filter by specific values.
    
    <examples>
    Include: SetFilter(field_name="City", values=["Beijing", "Shanghai"])
    Exclude: SetFilter(field_name="Region", values=["North"], exclude=True)
    </examples>
    """
    filter_type: FilterType = Field(default=FilterType.SET)
    
    values: list[Any] = Field(
        description="""<what>Values to include/exclude</what>
<when>ALWAYS required</when>
<rule>Use exact values from user question</rule>"""
    )
    
    exclude: bool = Field(
        default=False,
        description="""<what>Whether to exclude these values</what>
<when>Default False (include)</when>
<rule>exclude/not include -> True, only/include -> False</rule>"""
    )
    
    include: bool = Field(
        default=True,
        description="""<what>Whether to include these values (opposite of exclude)</what>
<when>Default True</when>
<rule>only/include -> True, exclude/not include -> False</rule>"""
    )
    
    def model_post_init(self, __context) -> None:
        """Sync include and exclude fields."""
        # If include is explicitly set to False, set exclude to True
        if not self.include:
            object.__setattr__(self, 'exclude', True)
        # If exclude is explicitly set to True, set include to False
        if self.exclude:
            object.__setattr__(self, 'include', False)


class DateRangeFilter(Filter):
    """Date range filter - filter by date range.
    
    Uses concrete start_date and end_date values.
    LLM calculates these based on user intent and current_time.
    
    <examples>
    Year 2024: DateRangeFilter(field_name="Order Date", start_date="2024-01-01", end_date="2024-12-31")
    Last month (Dec 2024): DateRangeFilter(field_name="Order Date", start_date="2024-11-01", end_date="2024-11-30")
    </examples>
    """
    filter_type: FilterType = Field(default=FilterType.DATE_RANGE)
    
    start_date: date | None = Field(
        default=None,
        description="""<what>Start date of the range</what>
<when>REQUIRED for date filtering</when>"""
    )
    
    end_date: date | None = Field(
        default=None,
        description="""<what>End date of the range</what>
<when>REQUIRED for date filtering</when>"""
    )


class NumericRangeFilter(Filter):
    """Numeric range filter - filter by numeric range.
    
    <examples>
    Greater than: NumericRangeFilter(field_name="Sales", min_value=1000, include_min=False)
    Range: NumericRangeFilter(field_name="Price", min_value=10, max_value=100)
    </examples>
    """
    filter_type: FilterType = Field(default=FilterType.NUMERIC_RANGE)
    
    min_value: float | None = Field(
        default=None,
        description="""<what>Minimum value</what>
<when>For lower bound</when>"""
    )
    
    max_value: float | None = Field(
        default=None,
        description="""<what>Maximum value</what>
<when>For upper bound</when>"""
    )
    
    include_min: bool = Field(
        default=True,
        description="""<what>Include minimum value</what>
<when>Default True (>=)</when>
<rule>greater than -> False, greater than or equal -> True</rule>"""
    )
    
    include_max: bool = Field(
        default=True,
        description="""<what>Include maximum value</what>
<when>Default True (<=)</when>
<rule>less than -> False, less than or equal -> True</rule>"""
    )


class TextMatchFilter(Filter):
    """Text match filter - filter by text pattern.
    
    <examples>
    Contains: TextMatchFilter(field_name="ProductName", pattern="Phone", match_type=CONTAINS)
    Starts with: TextMatchFilter(field_name="Category", pattern="Tech", match_type=STARTS_WITH)
    </examples>
    """
    filter_type: FilterType = Field(default=FilterType.TEXT_MATCH)
    
    pattern: str = Field(
        description="""<what>Text pattern to match</what>
<when>ALWAYS required</when>"""
    )
    
    match_type: TextMatchType = Field(
        default=TextMatchType.CONTAINS,
        description="""<what>Type of text matching</what>
<when>Default CONTAINS</when>"""
    )


class TopNFilter(Filter):
    """Top N filter - filter to top/bottom N records.
    
    <examples>
    Top 10: TopNFilter(field_name="Product", n=10, by_field="Sales")
    Bottom 5: TopNFilter(field_name="Region", n=5, by_field="Revenue", direction=ASC)
    </examples>
    """
    filter_type: FilterType = Field(default=FilterType.TOP_N)
    
    n: int = Field(
        description="""<what>Number of records to keep</what>
<when>ALWAYS required</when>"""
    )
    
    by_field: str = Field(
        description="""<what>Field to rank by</what>
<when>ALWAYS required</when>
<rule>Use measure field name</rule>"""
    )
    
    direction: SortDirection = Field(
        default=SortDirection.DESC,
        description="""<what>Sort direction for ranking</what>
<when>Default DESC (top N)</when>"""
    )
