"""Filter models for the semantic layer.

Platform-agnostic filter definitions.
"""

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .enums import (
    DateGranularity,
    DateRangeType,
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
    
    Example: "只看北京和上海" → SetFilter(field_name="城市", values=["北京", "上海"])
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
<rule>排除/不包括→True, 只看/包括→False</rule>"""
    )
    
    include: bool = Field(
        default=True,
        description="""<what>Whether to include these values (opposite of exclude)</what>
<when>Default True</when>
<rule>只看/包括→True, 排除/不包括→False</rule>"""
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
    
    Supports both relative (last month, this year) and absolute (2024-01-01 to 2024-12-31) ranges.
    """
    filter_type: FilterType = Field(default=FilterType.DATE_RANGE)
    
    range_type: DateRangeType = Field(
        description="""<what>Type of date range</what>
<when>ALWAYS required</when>
<rule>
- 本月/当月→CURRENT, 上月→PREVIOUS
- 最近N月→PREVIOUS_N, 年初至今→TO_DATE
- 具体日期→CUSTOM
</rule>"""
    )
    
    start_date: date | None = Field(
        default=None,
        description="""<what>Start date for CUSTOM range</what>
<when>ONLY when range_type=CUSTOM</when>"""
    )
    
    end_date: date | None = Field(
        default=None,
        description="""<what>End date for CUSTOM range</what>
<when>ONLY when range_type=CUSTOM</when>"""
    )
    
    n: int | None = Field(
        default=None,
        description="""<what>Number of periods for PREVIOUS_N/NEXT_N</what>
<when>ONLY when range_type=PREVIOUS_N or NEXT_N</when>"""
    )
    
    granularity: DateGranularity = Field(
        default=DateGranularity.MONTH,
        description="""<what>Granularity for relative ranges</what>
<when>For relative date ranges</when>
<rule>最近3个月→MONTH, 最近2年→YEAR</rule>"""
    )


class NumericRangeFilter(Filter):
    """Numeric range filter - filter by numeric range.
    
    Example: "销售额大于1000" → NumericRangeFilter(field_name="销售额", min_value=1000)
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
<rule>大于→False, 大于等于→True</rule>"""
    )
    
    include_max: bool = Field(
        default=True,
        description="""<what>Include maximum value</what>
<when>Default True (<=)</when>
<rule>小于→False, 小于等于→True</rule>"""
    )


class TextMatchFilter(Filter):
    """Text match filter - filter by text pattern.
    
    Example: "产品名包含'手机'" → TextMatchFilter(field_name="产品名", pattern="手机", match_type=CONTAINS)
    """
    filter_type: FilterType = Field(default=FilterType.TEXT_MATCH)
    
    pattern: str = Field(
        description="""<what>Text pattern to match</what>
<when>ALWAYS required</when>"""
    )
    
    match_type: TextMatchType = Field(
        default=TextMatchType.CONTAINS,
        description="""<what>Type of text matching</what>
<when>Default CONTAINS</when>
<rule>包含→CONTAINS, 开头→STARTS_WITH, 结尾→ENDS_WITH, 精确→EXACT</rule>"""
    )


class TopNFilter(Filter):
    """Top N filter - filter to top/bottom N records.
    
    Example: "销售额前10的产品" → TopNFilter(field_name="产品", n=10, by_field="销售额")
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
<when>Default DESC (top N)</when>
<rule>前N/Top N→DESC, 后N/Bottom N→ASC</rule>"""
    )
