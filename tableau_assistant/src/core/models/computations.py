"""Computation models - Core abstraction for complex calculations.

The Computation model is the heart of the platform-agnostic semantic layer.
It represents: Computation = Target × CalcType × Partition × Params

partition_by is the key abstraction that unifies:
- Tableau: Partitioning/Addressing in Table Calculations
- Power BI: ALL/ALLEXCEPT in DAX
- SQL: PARTITION BY in window functions
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .enums import (
    AggregationType,
    CalcAggregation,
    CalcType,
    RankStyle,
    RelativeTo,
    SortDirection,
)


class CalcParams(BaseModel):
    """Calculation parameters (platform-agnostic).
    
    <fill_order>
    1. lod_dimensions, lod_aggregation (if LOD_*)
    2. direction, rank_style, top_n (if RANK/DENSE_RANK/PERCENTILE)
    3. relative_to (if DIFFERENCE/PERCENT_DIFFERENCE)
    4. aggregation, restart_every (if RUNNING_TOTAL)
    5. aggregation, window_previous, window_next, include_current (if MOVING_CALC)
    6. level_of (if PERCENT_OF_TOTAL)
    </fill_order>
    
    <anti_patterns>
    X Fill params not matching calc_type
    X LOD type without lod_dimensions/lod_aggregation
    X rank_style = TOP_N (use top_n field instead)
    </anti_patterns>
    """
    model_config = ConfigDict(extra="forbid")
    
    # LOD params (first, as LOD is computed before table calcs)
    lod_dimensions: list[str] | None = Field(
        default=None,
        description="""<what>LOD dimension list</what>
<when>calc_type in [LOD_FIXED, LOD_INCLUDE, LOD_EXCLUDE]</when>
<dependency>Required for LOD types</dependency>"""
    )
    
    lod_aggregation: AggregationType | None = Field(
        default=None,
        description="""<what>LOD aggregation function</what>
<when>calc_type in [LOD_FIXED, LOD_INCLUDE, LOD_EXCLUDE]</when>
<dependency>Required for LOD types</dependency>"""
    )
    
    # Ranking params
    direction: SortDirection | None = Field(
        default=None,
        description="""<what>Sort direction for ranking</what>
<when>calc_type in [RANK, DENSE_RANK, PERCENTILE]</when>"""
    )
    
    rank_style: RankStyle | None = Field(
        default=None,
        description="""<what>Ranking style</what>
<when>calc_type = RANK</when>"""
    )
    
    top_n: int | None = Field(
        default=None,
        description="""<what>Limit to top/bottom N results</what>
<when>calc_type in [RANK, DENSE_RANK] and user wants top N or bottom N</when>
<rule>top N with DESC direction, bottom N with ASC direction</rule>"""
    )
    
    # Difference params
    relative_to: RelativeTo | None = Field(
        default=None,
        description="""<what>Difference reference position</what>
<when>calc_type in [DIFFERENCE, PERCENT_DIFFERENCE]</when>"""
    )
    
    # Running/Moving params
    aggregation: CalcAggregation | None = Field(
        default=None,
        description="""<what>Aggregation for running/moving calc</what>
<when>calc_type in [RUNNING_TOTAL, MOVING_CALC]</when>"""
    )
    
    restart_every: str | None = Field(
        default=None,
        description="""<what>Dimension to restart running calc</what>
<when>calc_type = RUNNING_TOTAL and needs restart (YTD, MTD)</when>"""
    )
    
    window_previous: int | None = Field(
        default=None,
        description="""<what>Number of previous values in window</what>
<when>calc_type = MOVING_CALC</when>"""
    )
    
    window_next: int | None = Field(
        default=None,
        description="""<what>Number of next values in window</what>
<when>calc_type = MOVING_CALC</when>"""
    )
    
    include_current: bool | None = Field(
        default=None,
        description="""<what>Include current value in window</what>
<when>calc_type = MOVING_CALC</when>"""
    )
    
    # Percent params
    level_of: str | None = Field(
        default=None,
        description="""<what>Level for percent calculation</what>
<when>calc_type = PERCENT_OF_TOTAL and needs specific level</when>"""
    )


class Computation(BaseModel):
    """Computation = Target x CalcType x Partition x Params
    
    <fill_order>
    1. target (ALWAYS)
    2. calc_type (ALWAYS)
    3. partition_by (ALWAYS, can be empty)
    4. params (based on calc_type)
    5. alias (optional, recommended for LOD)
    </fill_order>
    
    <examples>
    Ranking: {"target": "Sales", "calc_type": "RANK", "partition_by": ["Month"], "params": {"direction": "DESC"}}
    LOD: {"target": "OrderDate", "calc_type": "LOD_FIXED", "params": {"lod_dimensions": ["CustomerID"], "lod_aggregation": "MIN"}, "alias": "FirstPurchase"}
    </examples>
    
    <anti_patterns>
    X partition_by not subset of where.dimensions
    X calc_type and params mismatch
    </anti_patterns>
    """
    model_config = ConfigDict(extra="forbid")
    
    target: str = Field(
        description="""<what>Target measure field</what>
<when>ALWAYS</when>
<dependency>Must be in what.measures</dependency>"""
    )
    
    calc_type: CalcType = Field(
        description="""<what>Calculation type</what>
<when>ALWAYS</when>"""
    )
    
    partition_by: list[str] = Field(
        default_factory=list,
        description="""<what>Partition dimensions (computation scope)</what>
<when>ALWAYS (can be empty for global)</when>
<dependency>Must be subset of where.dimensions</dependency>"""
    )
    
    params: CalcParams = Field(
        default_factory=CalcParams,
        description="""<what>Calculation parameters</what>
<when>Based on calc_type</when>"""
    )
    
    alias: str | None = Field(
        default=None,
        description="""<what>Result alias</what>
<when>Optional, recommended for LOD</when>"""
    )
    
    @field_validator("target")
    @classmethod
    def target_not_empty(cls, v: str) -> str:
        """Validate target is not empty."""
        if not v or not v.strip():
            raise ValueError("target cannot be empty")
        return v.strip()
    
    @field_validator("partition_by")
    @classmethod
    def partition_by_is_list(cls, v: list[str]) -> list[str]:
        """Validate partition_by is a list of strings."""
        if not isinstance(v, list):
            raise ValueError("partition_by must be a list")
        return [s.strip() for s in v if s and s.strip()]
