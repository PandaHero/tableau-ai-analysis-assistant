# -*- coding: utf-8 -*-

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

from tableau_assistant.src.core.models.enums import (
    AggregationType,
    RankStyle,
    RelativeTo,
    SortDirection,
    WindowAggregation,
)
from tableau_assistant.src.core.models.fields import DimensionField



# ═══════════════════════════════════════════════════════════════════════════
# LOD Expression (Level of Detail)
# ═══════════════════════════════════════════════════════════════════════════

class LODFixed(BaseModel):
    """FIXED LOD - Compute metric at specified granularity, independent of query.
    
    Use when question needs metric "anchored" to specific dimensions.
    
    <fill_order>
    1. calc_type (ALWAYS = "LOD_FIXED")
    2. target (ALWAYS)
    3. dimensions (ALWAYS, can be empty for global)
    4. aggregation (ALWAYS)
    5. alias (recommended for combination scenarios)
    </fill_order>
    
    <examples>
    First purchase: {"calc_type": "LOD_FIXED", "target": "OrderDate", "dimensions": ["CustomerID"], "aggregation": "MIN", "alias": "FirstPurchase"}
    Customer lifetime: {"calc_type": "LOD_FIXED", "target": "Sales", "dimensions": ["CustomerID"], "aggregation": "SUM", "alias": "CustomerLifetimeValue"}
    </examples>
    
    <anti_patterns>
    X Using LOD_FIXED when query already has the needed granularity
    X Missing alias when result is used in subsequent table calc
    </anti_patterns>
    """
    model_config = ConfigDict(extra="forbid")
    
    calc_type: Literal["LOD_FIXED"] = Field(
        default="LOD_FIXED",
        description="""<what>LOD FIXED calculation type</what>
<when>ALWAYS = "LOD_FIXED"</when>"""
    )
    
    target: str = Field(
        description="""<what>Target measure field to aggregate</what>
<when>ALWAYS</when>
<must_not>Empty string</must_not>"""
    )
    
    dimensions: list[str] = Field(
        default_factory=list,
        description="""<what>Dimensions defining the fixed aggregation granularity</what>
<when>ALWAYS (empty list = global aggregation across entire dataset)</when>
<rule>These dimensions define the "anchor" - metric is computed at this granularity regardless of query</rule>"""
    )
    
    aggregation: AggregationType = Field(
        description="""<what>Aggregation function to apply</what>
<when>ALWAYS</when>"""
    )
    
    alias: str | None = Field(
        default=None,
        description="""<what>Result alias for reference in subsequent calculations</what>
<when>Recommended when used in combination with table calc</when>"""
    )
    
    @field_validator("target")
    @classmethod
    def target_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("target cannot be empty")
        return v.strip()


class LODInclude(BaseModel):
    """INCLUDE LOD - Compute at finer granularity than query (add dimensions).
    
    Use when query is too coarse and need to drill down first.
    
    <fill_order>
    1. calc_type (ALWAYS = "LOD_INCLUDE")
    2. target (ALWAYS)
    3. dimensions (ALWAYS, at least one)
    4. aggregation (ALWAYS)
    5. alias (optional)
    </fill_order>
    
    <examples>
    Order avg when query by Region: {"calc_type": "LOD_INCLUDE", "target": "Sales", "dimensions": ["OrderID"], "aggregation": "AVG"}
    </examples>
    
    <anti_patterns>
    X Using LOD_INCLUDE when the dimension is already in query
    X Empty dimensions list
    </anti_patterns>
    """
    model_config = ConfigDict(extra="forbid")
    
    calc_type: Literal["LOD_INCLUDE"] = Field(
        default="LOD_INCLUDE",
        description="""<what>LOD INCLUDE calculation type</what>
<when>ALWAYS = "LOD_INCLUDE"</when>"""
    )
    
    target: str = Field(
        description="""<what>Target measure field to aggregate</what>
<when>ALWAYS</when>
<must_not>Empty string</must_not>"""
    )
    
    dimensions: list[str] = Field(
        description="""<what>Dimensions to ADD to query granularity (making it finer)</what>
<when>ALWAYS (at least one dimension required)</when>
<rule>Result is calculated at query_dimensions + these dimensions</rule>
<must_not>Empty list</must_not>"""
    )
    
    aggregation: AggregationType = Field(
        description="""<what>Aggregation function to apply</what>
<when>ALWAYS</when>"""
    )
    
    alias: str | None = Field(
        default=None,
        description="""<what>Result alias</what>
<when>Optional</when>"""
    )
    
    @field_validator("target")
    @classmethod
    def target_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("target cannot be empty")
        return v.strip()
    
    @field_validator("dimensions")
    @classmethod
    def dimensions_not_empty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("dimensions cannot be empty for LOD_INCLUDE")
        return [s.strip() for s in v if s and s.strip()]


class LODExclude(BaseModel):
    """EXCLUDE LOD - Compute at coarser granularity than query (remove dimensions).
    
    Use when query is too fine and need to roll up.
    
    <fill_order>
    1. calc_type (ALWAYS = "LOD_EXCLUDE")
    2. target (ALWAYS)
    3. dimensions (ALWAYS, at least one)
    4. aggregation (ALWAYS)
    5. alias (optional)
    </fill_order>
    
    <examples>
    Category total when query by Subcategory: {"calc_type": "LOD_EXCLUDE", "target": "Sales", "dimensions": ["Subcategory"], "aggregation": "SUM"}
    </examples>
    
    <anti_patterns>
    X Using LOD_EXCLUDE when the dimension is not in query
    X Empty dimensions list
    </anti_patterns>
    """
    model_config = ConfigDict(extra="forbid")
    
    calc_type: Literal["LOD_EXCLUDE"] = Field(
        default="LOD_EXCLUDE",
        description="""<what>LOD EXCLUDE calculation type</what>
<when>ALWAYS = "LOD_EXCLUDE"</when>"""
    )
    
    target: str = Field(
        description="""<what>Target measure field to aggregate</what>
<when>ALWAYS</when>
<must_not>Empty string</must_not>"""
    )
    
    dimensions: list[str] = Field(
        description="""<what>Dimensions to REMOVE from query granularity (making it coarser)</what>
<when>ALWAYS (at least one dimension required)</when>
<rule>Result is calculated at query_dimensions - these dimensions</rule>
<must_not>Empty list</must_not>"""
    )
    
    aggregation: AggregationType = Field(
        description="""<what>Aggregation function to apply</what>
<when>ALWAYS</when>"""
    )
    
    alias: str | None = Field(
        default=None,
        description="""<what>Result alias</what>
<when>Optional</when>"""
    )
    
    @field_validator("target")
    @classmethod
    def target_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("target cannot be empty")
        return v.strip()
    
    @field_validator("dimensions")
    @classmethod
    def dimensions_not_empty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("dimensions cannot be empty for LOD_EXCLUDE")
        return [s.strip() for s in v if s and s.strip()]



# ═══════════════════════════════════════════════════════════════════════════
# Table Calculation - Ranking
# ═══════════════════════════════════════════════════════════════════════════

class RankCalc(BaseModel):
    """RANK - Rank query results with possible gaps (1,2,2,4).
    
    Use when question asks for ranking/ordering of results.
    
    <fill_order>
    1. calc_type (ALWAYS = "RANK")
    2. target (ALWAYS)
    3. partition_by (ALWAYS, can be empty for global)
    4. direction (default: DESC)
    5. rank_style (optional, default: COMPETITION)
    6. top_n (optional, for filtering)
    7. alias (optional)
    </fill_order>
    
    <examples>
    Global rank: {"calc_type": "RANK", "target": "Sales", "partition_by": [], "direction": "DESC"}
    Rank within month: {"calc_type": "RANK", "target": "Sales", "partition_by": [{"field_name": "Order Date", "date_granularity": "MONTH"}], "direction": "DESC"}
    </examples>
    
    <anti_patterns>
    X Using RANK for simple Top N filtering (use filter instead)
    X partition_by contains dimensions not in query
    X Inventing field names like "Month" instead of using DimensionField with date_granularity
    </anti_patterns>
    """
    model_config = ConfigDict(extra="forbid")
    
    calc_type: Literal["RANK"] = Field(
        default="RANK",
        description="""<what>RANK calculation type</what>
<when>ALWAYS = "RANK"</when>"""
    )
    
    target: str = Field(
        description="""<what>Target measure field to rank by</what>
<when>ALWAYS</when>
<must_not>Empty string</must_not>"""
    )
    
    partition_by: list[DimensionField] = Field(
        default_factory=list,
        description="""<what>Dimensions defining ranking scope (restart ranking within each partition)</what>
<when>ALWAYS (empty = global ranking across all results)</when>
<rule>Copy from Step 1 where.dimensions, preserving field_name and date_granularity</rule>
<must_not>Invent field names - use exact DimensionField from Step 1</must_not>"""
    )
    
    direction: SortDirection = Field(
        default=SortDirection.DESC,
        description="""<what>Sort direction for ranking</what>
<when>ALWAYS (default: DESC = highest value gets rank 1)</when>"""
    )
    
    rank_style: RankStyle | None = Field(
        default=None,
        description="""<what>Ranking style for ties</what>
<when>Optional (default: COMPETITION = 1,2,2,4)</when>"""
    )
    
    top_n: int | None = Field(
        default=None,
        description="""<what>Filter to top/bottom N after ranking</what>
<when>Optional, when user wants ranked subset</when>
<rule>Combines with direction: DESC+top_n=top N, ASC+top_n=bottom N</rule>"""
    )
    
    alias: str | None = Field(
        default=None,
        description="""<what>Result alias for the calculation</what>
<when>Optional</when>"""
    )
    
    @field_validator("target")
    @classmethod
    def target_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("target cannot be empty")
        return v.strip()


class DenseRankCalc(BaseModel):
    """DENSE_RANK - Rank query results without gaps (1,2,2,3).
    
    <fill_order>
    1. calc_type (ALWAYS = "DENSE_RANK")
    2. target (ALWAYS)
    3. partition_by (ALWAYS, can be empty)
    4. direction (default: DESC)
    5. top_n (optional)
    6. alias (optional)
    </fill_order>
    
    <examples>
    Dense rank: {"calc_type": "DENSE_RANK", "target": "Sales", "partition_by": [], "direction": "DESC"}
    </examples>
    """
    model_config = ConfigDict(extra="forbid")
    
    calc_type: Literal["DENSE_RANK"] = Field(
        default="DENSE_RANK",
        description="""<what>DENSE_RANK calculation type</what>
<when>ALWAYS = "DENSE_RANK"</when>"""
    )
    
    target: str = Field(
        description="""<what>Target measure field to rank by</what>
<when>ALWAYS</when>
<must_not>Empty string</must_not>"""
    )
    
    partition_by: list[DimensionField] = Field(
        default_factory=list,
        description="""<what>Dimensions defining ranking scope</what>
<when>ALWAYS (empty = global ranking)</when>
<rule>Copy from Step 1 where.dimensions</rule>"""
    )
    
    direction: SortDirection = Field(
        default=SortDirection.DESC,
        description="""<what>Sort direction for ranking</what>
<when>ALWAYS (default: DESC)</when>"""
    )
    
    top_n: int | None = Field(
        default=None,
        description="""<what>Filter to top/bottom N</what>
<when>Optional</when>"""
    )
    
    alias: str | None = Field(
        default=None,
        description="""<what>Result alias for the calculation</what>
<when>Optional</when>"""
    )
    
    @field_validator("target")
    @classmethod
    def target_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("target cannot be empty")
        return v.strip()


class PercentileCalc(BaseModel):
    """PERCENTILE - Percent rank of query results (0-100%).
    
    <fill_order>
    1. calc_type (ALWAYS = "PERCENTILE")
    2. target (ALWAYS)
    3. partition_by (ALWAYS, can be empty)
    4. direction (default: DESC)
    5. alias (optional)
    </fill_order>
    
    <examples>
    Percentile: {"calc_type": "PERCENTILE", "target": "Sales", "partition_by": [], "direction": "DESC"}
    </examples>
    """
    model_config = ConfigDict(extra="forbid")
    
    calc_type: Literal["PERCENTILE"] = Field(
        default="PERCENTILE",
        description="""<what>PERCENTILE calculation type</what>
<when>ALWAYS = "PERCENTILE"</when>"""
    )
    
    target: str = Field(
        description="""<what>Target measure field</what>
<when>ALWAYS</when>
<must_not>Empty string</must_not>"""
    )
    
    partition_by: list[DimensionField] = Field(
        default_factory=list,
        description="""<what>Dimensions defining percentile scope</what>
<when>ALWAYS (empty = global percentile)</when>
<rule>Copy from Step 1 where.dimensions</rule>"""
    )
    
    direction: SortDirection = Field(
        default=SortDirection.DESC,
        description="""<what>Sort direction</what>
<when>ALWAYS (default: DESC)</when>"""
    )
    
    alias: str | None = Field(
        default=None,
        description="""<what>Result alias for the calculation</what>
<when>Optional</when>"""
    )
    
    @field_validator("target")
    @classmethod
    def target_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("target cannot be empty")
        return v.strip()


# ═══════════════════════════════════════════════════════════════════════════
# Table Calculation - Difference/Comparison
# ═══════════════════════════════════════════════════════════════════════════

class DifferenceCalc(BaseModel):
    """DIFFERENCE - Absolute difference between query result rows.
    
    Use when question asks for change/difference from a reference point.
    
    <fill_order>
    1. calc_type (ALWAYS = "DIFFERENCE")
    2. target (ALWAYS)
    3. partition_by (ALWAYS, can be empty)
    4. relative_to (ALWAYS)
    5. alias (optional)
    </fill_order>
    
    <rule>
    Covers derived measures: "X Change", "X vs Last", "X Difference"
    If Step1 has duplicate measures for comparison, target should be base measure only
    </rule>
    
    <examples>
    vs Previous: {"calc_type": "DIFFERENCE", "target": "Sales", "partition_by": [], "relative_to": "PREVIOUS"}
    vs First within Region: {"calc_type": "DIFFERENCE", "target": "Sales", "partition_by": [{"field_name": "Region"}], "relative_to": "FIRST"}
    </examples>
    """
    model_config = ConfigDict(extra="forbid")
    
    calc_type: Literal["DIFFERENCE"] = Field(
        default="DIFFERENCE",
        description="""<what>DIFFERENCE calculation type</what>
<when>ALWAYS = "DIFFERENCE"</when>"""
    )
    
    target: str = Field(
        description="""<what>Target measure field</what>
<when>ALWAYS</when>
<must_not>Empty string</must_not>"""
    )
    
    partition_by: list[DimensionField] = Field(
        default_factory=list,
        description="""<what>Dimensions defining comparison scope</what>
<when>ALWAYS (empty = global comparison)</when>
<rule>Copy from Step 1 where.dimensions</rule>"""
    )
    
    relative_to: RelativeTo = Field(
        description="""<what>Reference point for difference</what>
<when>ALWAYS</when>"""
    )
    
    alias: str | None = Field(
        default=None,
        description="""<what>Result alias for the calculation</what>
<when>Optional</when>"""
    )
    
    @field_validator("target")
    @classmethod
    def target_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("target cannot be empty")
        return v.strip()


class PercentDifferenceCalc(BaseModel):
    """PERCENT_DIFFERENCE - Percentage change between query result rows.
    
    Use when question asks for growth rate or percent change.
    
    <fill_order>
    1. calc_type (ALWAYS = "PERCENT_DIFFERENCE")
    2. target (ALWAYS)
    3. partition_by (ALWAYS, can be empty)
    4. relative_to (ALWAYS)
    5. alias (optional)
    </fill_order>
    
    <rule>
    Covers derived measures: "Last Year X", "X Growth", "YoY X", "MoM X"
    If Step1 has [Sales, Sales(alias="Last Year Sales")], target should be "Sales" only
    </rule>
    
    <examples>
    YoY within region: {"calc_type": "PERCENT_DIFFERENCE", "target": "Sales", "partition_by": [{"field_name": "Region"}], "relative_to": "PREVIOUS"}
    By month: {"calc_type": "PERCENT_DIFFERENCE", "target": "Sales", "partition_by": [{"field_name": "Order Date", "date_granularity": "MONTH"}], "relative_to": "PREVIOUS"}
    </examples>
    """
    model_config = ConfigDict(extra="forbid")
    
    calc_type: Literal["PERCENT_DIFFERENCE"] = Field(
        default="PERCENT_DIFFERENCE",
        description="""<what>PERCENT_DIFFERENCE calculation type</what>
<when>ALWAYS = "PERCENT_DIFFERENCE"</when>"""
    )
    
    target: str = Field(
        description="""<what>Target measure field</what>
<when>ALWAYS</when>
<must_not>Empty string</must_not>"""
    )
    
    partition_by: list[DimensionField] = Field(
        default_factory=list,
        description="""<what>Dimensions defining comparison scope</what>
<when>ALWAYS (empty = global comparison)</when>
<rule>Copy from Step 1 where.dimensions, preserving field_name and date_granularity</rule>
<must_not>Invent field names like "Month" - use "Order Date" with date_granularity instead</must_not>"""
    )
    
    relative_to: RelativeTo = Field(
        description="""<what>Reference point for percent change</what>
<when>ALWAYS</when>"""
    )
    
    alias: str | None = Field(
        default=None,
        description="""<what>Result alias for the calculation</what>
<when>Optional</when>"""
    )
    
    @field_validator("target")
    @classmethod
    def target_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("target cannot be empty")
        return v.strip()


# ═══════════════════════════════════════════════════════════════════════════
# Table Calculation - Running/Cumulative
# ═══════════════════════════════════════════════════════════════════════════

class RunningTotalCalc(BaseModel):
    """RUNNING_TOTAL - Cumulative aggregation of query results.
    
    Use when question asks for cumulative/running/YTD totals.
    
    <fill_order>
    1. calc_type (ALWAYS = "RUNNING_TOTAL")
    2. target (ALWAYS)
    3. partition_by (ALWAYS, can be empty)
    4. aggregation (default: SUM)
    5. restart_every (optional, for periodic restart like YTD)
    6. alias (optional)
    </fill_order>
    
    <rule>
    Covers derived measures: "Cumulative X", "YTD X", "Running X"
    If Step1 has duplicate measures for cumulative, target should be base measure only
    </rule>
    
    <examples>
    Cumulative sum: {"calc_type": "RUNNING_TOTAL", "target": "Sales", "partition_by": [], "aggregation": "SUM"}
    YTD: {"calc_type": "RUNNING_TOTAL", "target": "Sales", "partition_by": [], "aggregation": "SUM", "restart_every": "Year"}
    </examples>
    
    <anti_patterns>
    X Missing restart_every for YTD/MTD scenarios
    </anti_patterns>
    """
    model_config = ConfigDict(extra="forbid")
    
    calc_type: Literal["RUNNING_TOTAL"] = Field(
        default="RUNNING_TOTAL",
        description="""<what>RUNNING_TOTAL calculation type</what>
<when>ALWAYS = "RUNNING_TOTAL"</when>"""
    )
    
    target: str = Field(
        description="""<what>Target measure field</what>
<when>ALWAYS</when>
<must_not>Empty string</must_not>"""
    )
    
    partition_by: list[DimensionField] = Field(
        default_factory=list,
        description="""<what>Dimensions defining cumulative scope</what>
<when>ALWAYS (empty = global cumulative)</when>
<rule>Copy from Step 1 where.dimensions</rule>"""
    )
    
    aggregation: WindowAggregation = Field(
        default=WindowAggregation.SUM,
        description="""<what>Aggregation function for running calc</what>
<when>ALWAYS (default: SUM)</when>"""
    )
    
    restart_every: str | None = Field(
        default=None,
        description="""<what>Dimension to restart cumulative calculation</what>
<when>For YTD (restart_every="Year"), MTD (restart_every="Month"), etc.</when>"""
    )
    
    alias: str | None = Field(
        default=None,
        description="""<what>Result alias for the calculation</what>
<when>Optional</when>"""
    )
    
    @field_validator("target")
    @classmethod
    def target_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("target cannot be empty")
        return v.strip()


# ═══════════════════════════════════════════════════════════════════════════
# Table Calculation - Moving Window
# ═══════════════════════════════════════════════════════════════════════════

class MovingCalc(BaseModel):
    """MOVING_CALC - Sliding window aggregation of query results.
    
    Use when question asks for moving average or rolling calculations.
    
    <fill_order>
    1. calc_type (ALWAYS = "MOVING_CALC")
    2. target (ALWAYS)
    3. partition_by (ALWAYS, can be empty)
    4. aggregation (default: AVG)
    5. window_previous (default: 2)
    6. window_next (default: 0)
    7. include_current (default: True)
    8. alias (optional)
    </fill_order>
    
    <examples>
    3-month MA: {"calc_type": "MOVING_CALC", "target": "Sales", "partition_by": [], "aggregation": "AVG", "window_previous": 2, "window_next": 0, "include_current": true}
    Rolling 5-day sum: {"calc_type": "MOVING_CALC", "target": "Sales", "partition_by": [], "aggregation": "SUM", "window_previous": 4, "window_next": 0}
    </examples>
    """
    model_config = ConfigDict(extra="forbid")
    
    calc_type: Literal["MOVING_CALC"] = Field(
        default="MOVING_CALC",
        description="""<what>MOVING_CALC calculation type</what>
<when>ALWAYS = "MOVING_CALC"</when>"""
    )
    
    target: str = Field(
        description="""<what>Target measure field</what>
<when>ALWAYS</when>
<must_not>Empty string</must_not>"""
    )
    
    partition_by: list[DimensionField] = Field(
        default_factory=list,
        description="""<what>Dimensions defining window scope</what>
<when>ALWAYS (empty = global window)</when>
<rule>Copy from Step 1 where.dimensions</rule>"""
    )
    
    aggregation: WindowAggregation = Field(
        default=WindowAggregation.AVG,
        description="""<what>Aggregation function for window</what>
<when>ALWAYS (default: AVG for moving average)</when>"""
    )
    
    window_previous: int = Field(
        default=2,
        description="""<what>Number of previous rows in window</what>
<when>ALWAYS (default: 2, so 3-period window with current)</when>"""
    )
    
    window_next: int = Field(
        default=0,
        description="""<what>Number of next rows in window</what>
<when>ALWAYS (default: 0 for trailing window)</when>"""
    )
    
    include_current: bool = Field(
        default=True,
        description="""<what>Include current row in window</what>
<when>ALWAYS (default: True)</when>"""
    )
    
    alias: str | None = Field(
        default=None,
        description="""<what>Result alias for the calculation</what>
<when>Optional</when>"""
    )
    
    @field_validator("target")
    @classmethod
    def target_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("target cannot be empty")
        return v.strip()


# ═══════════════════════════════════════════════════════════════════════════
# Table Calculation - Percent of Total
# ═══════════════════════════════════════════════════════════════════════════

class PercentOfTotalCalc(BaseModel):
    """PERCENT_OF_TOTAL - Calculate proportion of query results.
    
    Use when question asks for share/proportion/percentage of total.
    
    <fill_order>
    1. calc_type (ALWAYS = "PERCENT_OF_TOTAL")
    2. target (ALWAYS)
    3. partition_by (ALWAYS, can be empty for global total)
    4. level_of (optional)
    5. alias (optional)
    </fill_order>
    
    <examples>
    Global percent: {"calc_type": "PERCENT_OF_TOTAL", "target": "Sales", "partition_by": []}
    Within region: {"calc_type": "PERCENT_OF_TOTAL", "target": "Sales", "partition_by": [{"field_name": "Region"}]}
    </examples>
    """
    model_config = ConfigDict(extra="forbid")
    
    calc_type: Literal["PERCENT_OF_TOTAL"] = Field(
        default="PERCENT_OF_TOTAL",
        description="""<what>PERCENT_OF_TOTAL calculation type</what>
<when>ALWAYS = "PERCENT_OF_TOTAL"</when>"""
    )
    
    target: str = Field(
        description="""<what>Target measure field</what>
<when>ALWAYS</when>
<must_not>Empty string</must_not>"""
    )
    
    partition_by: list[DimensionField] = Field(
        default_factory=list,
        description="""<what>Dimensions defining the "total" scope</what>
<when>ALWAYS (empty = percent of grand total)</when>
<rule>Copy from Step 1 where.dimensions</rule>"""
    )
    
    level_of: str | None = Field(
        default=None,
        description="""<what>Specific level for percent calculation</what>
<when>When specific aggregation level needed</when>"""
    )
    
    alias: str | None = Field(
        default=None,
        description="""<what>Result alias for the calculation</what>
<when>Optional</when>"""
    )
    
    @field_validator("target")
    @classmethod
    def target_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("target cannot be empty")
        return v.strip()


# ═══════════════════════════════════════════════════════════════════════════
# Union Types
# ═══════════════════════════════════════════════════════════════════════════

# LOD Expression Union
LODExpression = Annotated[
    Union[LODFixed, LODInclude, LODExclude],
    Field(discriminator="calc_type")
]
"""Union of all LOD expression types, discriminated by calc_type.

<rule>
LOD Selection (based on granularity relationship to query):

LOD_FIXED - Need metric at SPECIFIC granularity, independent of query:
  → "per customer X", "customer lifetime value", "first purchase date"
  → dimensions = the anchor dimensions (e.g., CustomerID)

LOD_INCLUDE - Need FINER granularity than query (add dimensions):
  → "average order amount" when query is by Region
  → dimensions = dimensions to ADD (e.g., OrderID)

LOD_EXCLUDE - Need COARSER granularity than query (remove dimensions):
  → "category total" when query is by Subcategory
  → dimensions = dimensions to REMOVE (e.g., Subcategory)
</rule>
"""

# Table Calculation Union
TableCalc = Annotated[
    Union[
        RankCalc, DenseRankCalc, PercentileCalc,
        DifferenceCalc, PercentDifferenceCalc,
        RunningTotalCalc, MovingCalc, PercentOfTotalCalc
    ],
    Field(discriminator="calc_type")
]
"""Union of all table calculation types, discriminated by calc_type.

<rule>
Table Calc Selection (based on transformation type):

Ranking (RANK, DENSE_RANK, PERCENTILE):
  → "rank by sales", "top 10 with rank", "percentile position"

Cumulative (RUNNING_TOTAL):
  → "YTD sales", "cumulative total", "running sum"

Moving Window (MOVING_CALC):
  → "3-month moving average", "rolling 7-day sum"

Proportion (PERCENT_OF_TOTAL):
  → "percent of total", "share within region"

Comparison (DIFFERENCE, PERCENT_DIFFERENCE):
  → "vs previous month", "MoM growth", "YoY change"
</rule>
"""

# Top-Level Computation Union (LOD + TableCalc)
Computation = Annotated[
    Union[
        # LOD types
        LODFixed, LODInclude, LODExclude,
        # Table Calc types
        RankCalc, DenseRankCalc, PercentileCalc,
        DifferenceCalc, PercentDifferenceCalc,
        RunningTotalCalc, MovingCalc, PercentOfTotalCalc
    ],
    Field(discriminator="calc_type")
]
"""Union of all computation types (LOD + TableCalc), discriminated by calc_type.

<rule>
Decision Framework (From Question Perspective):

Step 1 - Does question need metric at DIFFERENT granularity than query?
  YES → LOD
    - LOD_FIXED: Metric anchored to specific dimensions
      → "per customer X", "customer lifetime value"
    - LOD_INCLUDE: Need finer granularity (add dimensions)
      → "average order amount" when query by Region
    - LOD_EXCLUDE: Need coarser granularity (remove dimensions)
      → "category total" when query by Subcategory
  NO → Continue to Step 2

Step 2 - Does question need to TRANSFORM query results?
  YES → Table Calc
    - RANK/DENSE_RANK/PERCENTILE: Ranking
    - RUNNING_TOTAL: Cumulative (YTD, running sum)
    - MOVING_CALC: Sliding window (moving average)
    - PERCENT_OF_TOTAL: Share/proportion
    - DIFFERENCE/PERCENT_DIFFERENCE: Comparison (MoM, YoY)
  NO → Basic aggregation (no Computation needed)

Combination (LOD + Table Calc):
When question needs BOTH different granularity AND transformation.
Example: "Rank customers by first purchase date"
→ [LOD_FIXED for first purchase, then RANK]
Output order: LOD first, then Table Calc
</rule>
"""


__all__ = [
    # LOD types
    "LODFixed",
    "LODInclude", 
    "LODExclude",
    "LODExpression",
    # Table Calc types
    "RankCalc",
    "DenseRankCalc",
    "PercentileCalc",
    "DifferenceCalc",
    "PercentDifferenceCalc",
    "RunningTotalCalc",
    "MovingCalc",
    "PercentOfTotalCalc",
    "TableCalc",
    # Combined
    "Computation",
]
