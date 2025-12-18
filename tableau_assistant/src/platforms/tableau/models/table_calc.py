"""Tableau Table Calculation models - Aligned with VizQL API.

Table calculations are computed after the initial query aggregation.
They use Partitioning (scope) and Addressing (direction) to define computation.

Key concept: partition_by → Tableau Partitioning
- partition_by=[] → No partitioning, compute across all rows
- partition_by=[月份] → Partition by month, compute within each month
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .vizql_types import VizQLFunction, VizQLSortDirection


class TableCalcType(str, Enum):
    """Tableau table calculation types (from OpenAPI spec)."""
    CUSTOM = "CUSTOM"
    NESTED = "NESTED"
    DIFFERENCE_FROM = "DIFFERENCE_FROM"
    PERCENT_DIFFERENCE_FROM = "PERCENT_DIFFERENCE_FROM"
    PERCENT_FROM = "PERCENT_FROM"
    PERCENT_OF_TOTAL = "PERCENT_OF_TOTAL"
    RANK = "RANK"
    PERCENTILE = "PERCENTILE"
    RUNNING_TOTAL = "RUNNING_TOTAL"
    MOVING_CALCULATION = "MOVING_CALCULATION"


class TableCalcAggregation(str, Enum):
    """Aggregation for running/moving calculations."""
    SUM = "SUM"
    AVG = "AVG"
    MIN = "MIN"
    MAX = "MAX"


class RankType(str, Enum):
    """Rank calculation types."""
    COMPETITION = "COMPETITION"
    MODIFIED_COMPETITION = "MODIFIED COMPETITION"
    DENSE = "DENSE"
    UNIQUE = "UNIQUE"


class RelativeTo(str, Enum):
    """Relative position for difference calculations."""
    PREVIOUS = "PREVIOUS"
    NEXT = "NEXT"
    FIRST = "FIRST"
    LAST = "LAST"


# ═══════════════════════════════════════════════════════════════════════════
# Table Calculation Field Reference
# ═══════════════════════════════════════════════════════════════════════════

class TableCalcFieldReference(BaseModel):
    """Reference to a field in table calculation."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    
    field_caption: str = Field(alias="fieldCaption")
    function: VizQLFunction | None = None


class TableCalcCustomSort(BaseModel):
    """Custom sort for table calculation."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    
    field_caption: str = Field(alias="fieldCaption")
    function: VizQLFunction
    direction: VizQLSortDirection


# ═══════════════════════════════════════════════════════════════════════════
# Table Calculation Specifications
# ═══════════════════════════════════════════════════════════════════════════

class TableCalcSpecification(BaseModel):
    """Base table calculation specification.
    
    The 'dimensions' field defines the PARTITIONING:
    - Dimensions listed here are used for partitioning (scope)
    - Dimensions NOT listed are used for addressing (direction)
    
    Mapping from SemanticQuery.Computation:
    - partition_by → dimensions (partitioning)
    - remaining dimensions → addressing (implicit)
    """
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    
    table_calc_type: TableCalcType = Field(alias="tableCalcType")
    dimensions: list[TableCalcFieldReference] = Field(
        description="Partitioning dimensions (scope of calculation)"
    )


class RankTableCalcSpecification(TableCalcSpecification):
    """Rank table calculation.
    
    Maps from: OperationType.RANK, OperationType.DENSE_RANK
    """
    table_calc_type: TableCalcType = Field(default=TableCalcType.RANK, alias="tableCalcType")
    rank_type: RankType = Field(default=RankType.COMPETITION, alias="rankType")
    direction: VizQLSortDirection = VizQLSortDirection.DESC


class PercentOfTotalTableCalcSpecification(TableCalcSpecification):
    """Percent of total table calculation.
    
    Maps from: OperationType.PERCENT
    """
    table_calc_type: TableCalcType = Field(default=TableCalcType.PERCENT_OF_TOTAL, alias="tableCalcType")
    level_address: TableCalcFieldReference | None = Field(default=None, alias="levelAddress")
    custom_sort: TableCalcCustomSort | None = Field(default=None, alias="customSort")


class RunningTotalTableCalcSpecification(TableCalcSpecification):
    """Running total table calculation.
    
    Maps from: OperationType.RUNNING_SUM, OperationType.RUNNING_AVG
    """
    table_calc_type: TableCalcType = Field(default=TableCalcType.RUNNING_TOTAL, alias="tableCalcType")
    aggregation: TableCalcAggregation = TableCalcAggregation.SUM
    restart_every: TableCalcFieldReference | None = Field(default=None, alias="restartEvery")
    custom_sort: TableCalcCustomSort | None = Field(default=None, alias="customSort")


class MovingTableCalcSpecification(TableCalcSpecification):
    """Moving calculation (moving average, moving sum).
    
    Maps from: OperationType.MOVING_AVG, OperationType.MOVING_SUM
    """
    table_calc_type: TableCalcType = Field(default=TableCalcType.MOVING_CALCULATION, alias="tableCalcType")
    aggregation: TableCalcAggregation = TableCalcAggregation.AVG
    previous: int = 2
    next: int = 0
    include_current: bool = Field(default=True, alias="includeCurrent")
    fill_in_null: bool = Field(default=False, alias="fillInNull")
    custom_sort: TableCalcCustomSort | None = Field(default=None, alias="customSort")


class DifferenceTableCalcSpecification(TableCalcSpecification):
    """Difference from table calculation.
    
    Maps from: OperationType.DIFFERENCE, OperationType.GROWTH_RATE
    """
    table_calc_type: TableCalcType = Field(default=TableCalcType.DIFFERENCE_FROM, alias="tableCalcType")
    level_address: TableCalcFieldReference | None = Field(default=None, alias="levelAddress")
    relative_to: RelativeTo = Field(default=RelativeTo.PREVIOUS, alias="relativeTo")
    custom_sort: TableCalcCustomSort | None = Field(default=None, alias="customSort")


class PercentDifferenceTableCalcSpecification(TableCalcSpecification):
    """Percent difference from table calculation.
    
    Maps from: OperationType.GROWTH_RATE (percentage form)
    """
    table_calc_type: TableCalcType = Field(default=TableCalcType.PERCENT_DIFFERENCE_FROM, alias="tableCalcType")
    level_address: TableCalcFieldReference | None = Field(default=None, alias="levelAddress")
    relative_to: RelativeTo = Field(default=RelativeTo.PREVIOUS, alias="relativeTo")
    custom_sort: TableCalcCustomSort | None = Field(default=None, alias="customSort")


# ═══════════════════════════════════════════════════════════════════════════
# Table Calculation Field (combines base field + table calc spec)
# ═══════════════════════════════════════════════════════════════════════════

class TableCalcField(BaseModel):
    """Complete table calculation field for VizQL API.
    
    This is the final output format for table calculations.
    """
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    
    field_caption: str = Field(alias="fieldCaption")
    field_alias: str | None = Field(default=None, alias="fieldAlias")
    function: VizQLFunction | None = None
    calculation: str | None = None  # For custom calculations
    table_calculation: TableCalcSpecification = Field(alias="tableCalculation")
    nested_table_calculations: list[TableCalcSpecification] | None = Field(
        default=None, alias="nestedTableCalculations"
    )
    sort_direction: VizQLSortDirection | None = Field(default=None, alias="sortDirection")
    sort_priority: int | None = Field(default=None, alias="sortPriority")
