# -*- coding: utf-8 -*-
"""

Core Data Models - 平台无关的语义层模型

本模块包含所有平台无关的数据模型，按领域分类：

1. 基础模型 (enums, fields, filters, computations)

2. 查询模型 (query)

3. 执行结果模型 (execute_result)

4. 验证模型 (validation)
"""

# Enums

from analytics_assistant.src.core.schemas.enums import (

    AggregationType,

    DateGranularity,

    DateRangeType,

    DimensionCategory,

    DimensionLevel,

    FilterType,

    HowType,

    IntentType,

    MappingSource,

    MeasureCategory,

    ObserverDecision,

    RankStyle,

    RelativeTo,

    SortDirection,

    TextMatchType,

)

# Fields

from analytics_assistant.src.core.schemas.fields import (

    DimensionField,

    MeasureField,

    SortSpec,

)

# Computations

from analytics_assistant.src.core.schemas.computations import (

    # LOD types

    LODFixed,

    LODInclude,

    LODExclude,

    LODExpression,

    # Table Calc types

    RankCalc,

    DenseRankCalc,

    PercentileCalc,

    DifferenceCalc,

    PercentDifferenceCalc,

    RunningTotalCalc,

    MovingCalc,

    PercentOfTotalCalc,

    TableCalc,

    # Union type

    Computation,

)

# Filters

from analytics_assistant.src.core.schemas.filters import (

    DateRangeFilter,

    Filter,

    NumericRangeFilter,

    SetFilter,

    TextMatchFilter,

    TopNFilter,

)

# Query - 已移除 SemanticQuery，使用 SemanticOutput 代替

# from analytics_assistant.src.core.schemas.query import SemanticQuery

# Validation

from analytics_assistant.src.core.schemas.validation import (

    ValidationErrorDetail,

    ValidationErrorType,

    ValidationResult,

)

# Execute Result

from analytics_assistant.src.core.schemas.execute_result import (

    ExecuteResult,

    ColumnInfo,

    RowData,

    RowValue,

)

# Data Model

from analytics_assistant.src.core.schemas.data_model import (

    Field,

    LogicalTable,

    TableRelationship,

    DataModel,

)

# Field Candidate (跨模块共享)

from analytics_assistant.src.core.schemas.field_candidate import FieldCandidate

__all__ = [

    # Enums

    "AggregationType",

    "DateGranularity",

    "DateRangeType",

    "DimensionCategory",

    "DimensionLevel",

    "FilterType",

    "HowType",

    "IntentType",

    "MappingSource",

    "MeasureCategory",

    "ObserverDecision",

    "RankStyle",

    "RelativeTo",

    "SortDirection",

    "TextMatchType",

    # Fields

    "DimensionField",

    "MeasureField",

    "SortSpec",

    # Computations

    "LODFixed",

    "LODInclude",

    "LODExclude",

    "LODExpression",

    "RankCalc",

    "DenseRankCalc",

    "PercentileCalc",

    "DifferenceCalc",

    "PercentDifferenceCalc",

    "RunningTotalCalc",

    "MovingCalc",

    "PercentOfTotalCalc",

    "TableCalc",

    "Computation",

    # Filters

    "DateRangeFilter",

    "Filter",

    "NumericRangeFilter",

    "SetFilter",

    "TextMatchFilter",

    "TopNFilter",

    # Query - 已移除 SemanticQuery

    # "SemanticQuery",

    # Validation

    "ValidationErrorDetail",

    "ValidationErrorType",

    "ValidationResult",

    # Execute Result

    "ExecuteResult",

    "ColumnInfo",

    "RowData",

    "RowValue",

    # Data Model

    "Field",

    "LogicalTable",

    "TableRelationship",

    "DataModel",

    # Field Candidate

    "FieldCandidate",

]

