"""Tableau-specific models.

Contains VizQL types, table calculation specifications,
and LOD expression models aligned with Tableau's API.
"""

from tableau_assistant.src.platforms.tableau.models.vizql_types import (

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

from tableau_assistant.src.platforms.tableau.models.table_calc import (

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

from tableau_assistant.src.platforms.tableau.models.lod import (

    LODType,
    LODExpression,
    determine_lod_type,
)

# ExecuteResult is defined in core.models, re-export for convenience
from tableau_assistant.src.core.models.execute_result import (
    ExecuteResult,
    ColumnInfo,
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
    "ColumnInfo",
    "RowData",
    "RowValue",
]
