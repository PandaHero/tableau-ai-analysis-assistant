"""Tableau-specific models.

Contains VizQL types, table calculation specifications,
and LOD expression models aligned with Tableau's API.
"""

from .vizql_types import (
    VizQLFunction,
    VizQLSortDirection,
    VizQLDataType,
    VizQLFieldRole,
    VizQLColumnClass,
    VizQLFieldBase,
    VizQLDimensionField,
    VizQLMeasureField,
    VizQLCalculatedField,
    VizQLFilterType,
    VizQLFilterBase,
    VizQLSetFilter,
    VizQLDateFilter,
    VizQLQuantitativeDateFilter,
    VizQLQuantitativeNumericalFilter,
    VizQLMatchFilter,
    VizQLTopFilter,
    VizQLQueryRequest,
    VizQLQueryResponse,
)

from .table_calc import (
    TableCalcType,
    TableCalcAggregation,
    RankType,
    RelativeTo,
    TableCalcFieldReference,
    TableCalcCustomSort,
    TableCalcSpecification,
    RankTableCalcSpecification,
    PercentOfTotalTableCalcSpecification,
    RunningTotalTableCalcSpecification,
    MovingTableCalcSpecification,
    DifferenceTableCalcSpecification,
    PercentDifferenceTableCalcSpecification,
    TableCalcField,
)

from .lod import (
    LODType,
    LODExpression,
    determine_lod_type,
)

from .execute_result import (
    ExecuteResult,
    ColumnMetadata,
    RowData,
    RowValue,
)

__all__ = [
    # VizQL Types
    "VizQLFunction",
    "VizQLSortDirection",
    "VizQLDataType",
    "VizQLFieldRole",
    "VizQLColumnClass",
    "VizQLFieldBase",
    "VizQLDimensionField",
    "VizQLMeasureField",
    "VizQLCalculatedField",
    "VizQLFilterType",
    "VizQLFilterBase",
    "VizQLSetFilter",
    "VizQLDateFilter",
    "VizQLQuantitativeDateFilter",
    "VizQLQuantitativeNumericalFilter",
    "VizQLMatchFilter",
    "VizQLTopFilter",
    "VizQLQueryRequest",
    "VizQLQueryResponse",
    # Table Calculations
    "TableCalcType",
    "TableCalcAggregation",
    "RankType",
    "RelativeTo",
    "TableCalcFieldReference",
    "TableCalcCustomSort",
    "TableCalcSpecification",
    "RankTableCalcSpecification",
    "PercentOfTotalTableCalcSpecification",
    "RunningTotalTableCalcSpecification",
    "MovingTableCalcSpecification",
    "DifferenceTableCalcSpecification",
    "PercentDifferenceTableCalcSpecification",
    "TableCalcField",
    # LOD
    "LODType",
    "LODExpression",
    "determine_lod_type",
    # Execute Result
    "ExecuteResult",
    "ColumnMetadata",
    "RowData",
    "RowValue",
]
