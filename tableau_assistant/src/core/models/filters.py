"""Filter models for the semantic layer.

Platform-agnostic filter definitions.
Uses XML tags per spec: <what>, <when>, <fill_order>
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
    """Base filter class."""
    model_config = ConfigDict(extra="forbid")
    
    field_name: str = Field(
        description="""<what>Field to filter on</what>
<when>ALWAYS</when>"""
    )
    filter_type: FilterType = Field(
        description="""<what>Filter type discriminator</what>
<when>ALWAYS</when>"""
    )


class SetFilter(Filter):
    """Filter by specific values.
    
    <fill_order>
    1. field_name
    2. values
    3. exclude (if excluding)
    </fill_order>
    """
    filter_type: FilterType = Field(default=FilterType.SET)
    
    values: list[Any] = Field(
        default_factory=list,
        description="""<what>Values to include/exclude</what>
<when>Question mentions specific values</when>"""
    )
    
    exclude: bool = Field(
        default=False,
        description="""<what>Exclude mode</what>
<when>Question says "except", "not", "exclude"</when>"""
    )
    
    include: bool = Field(
        default=True,
        description="""<what>Include mode</what>
<when>Default</when>"""
    )
    
    def model_post_init(self, __context) -> None:
        """Sync include and exclude fields."""
        if not self.include:
            object.__setattr__(self, 'exclude', True)
        if self.exclude:
            object.__setattr__(self, 'include', False)


class DateRangeFilter(Filter):
    """Filter by date range.
    
    <fill_order>
    1. field_name
    2. start_date
    3. end_date
    </fill_order>
    
    <rule>
    Use current_time to calculate concrete dates for relative terms:
    this year -> YYYY-01-01 to YYYY-12-31
    last year -> (YYYY-1)-01-01 to (YYYY-1)-12-31
    this month -> YYYY-MM-01 to YYYY-MM-last
    last month -> previous month range
    </rule>
    """
    filter_type: FilterType = Field(default=FilterType.DATE_RANGE)
    
    start_date: date | None = Field(
        default=None,
        description="""<what>Range start date (YYYY-MM-DD)</what>
<when>Question specifies date range or relative date</when>"""
    )
    end_date: date | None = Field(
        default=None,
        description="""<what>Range end date (YYYY-MM-DD)</what>
<when>Question specifies date range or relative date</when>"""
    )


class NumericRangeFilter(Filter):
    """Filter by numeric range.
    
    <fill_order>
    1. field_name
    2. min_value (if lower bound)
    3. max_value (if upper bound)
    </fill_order>
    """
    filter_type: FilterType = Field(default=FilterType.NUMERIC_RANGE)
    
    min_value: float | None = Field(
        default=None,
        description="""<what>Minimum value</what>
<when>Question specifies lower bound</when>"""
    )
    max_value: float | None = Field(
        default=None,
        description="""<what>Maximum value</what>
<when>Question specifies upper bound</when>"""
    )
    include_min: bool = Field(
        default=True,
        description="""<what>Include min (>=)</what>
<when>Default True</when>"""
    )
    include_max: bool = Field(
        default=True,
        description="""<what>Include max (<=)</what>
<when>Default True</when>"""
    )


class TextMatchFilter(Filter):
    """Filter by text pattern.
    
    <fill_order>
    1. field_name
    2. pattern
    3. match_type
    </fill_order>
    """
    filter_type: FilterType = Field(default=FilterType.TEXT_MATCH)
    
    pattern: str = Field(
        description="""<what>Text pattern to match</what>
<when>Question asks for text matching</when>"""
    )
    match_type: TextMatchType = Field(
        default=TextMatchType.CONTAINS,
        description="""<what>Match type</what>
<when>ALWAYS</when>"""
    )


class TopNFilter(Filter):
    """Filter to top/bottom N records.
    
    <fill_order>
    1. field_name
    2. n
    3. by_field
    4. direction
    </fill_order>
    """
    filter_type: FilterType = Field(default=FilterType.TOP_N)
    
    n: int = Field(
        description="""<what>Number of records</what>
<when>Question asks for "top N" or "bottom N"</when>"""
    )
    by_field: str = Field(
        description="""<what>Measure to rank by</what>
<when>ALWAYS</when>"""
    )
    direction: SortDirection = Field(
        default=SortDirection.DESC,
        description="""<what>Rank direction</what>
<when>ALWAYS</when>"""
    )
