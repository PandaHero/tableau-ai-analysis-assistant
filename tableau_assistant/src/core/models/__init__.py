# -*- coding: utf-8 -*-
"""
Core Data Models - 平台无关的语义层模型

本模块包含所有平台无关的数据模型，按领域分类：

1. 基础模型 (enums, fields, filters, computations)
2. 查询模型 (query)
3. 数据模型 (data_model)
4. 验证模型 (validation)
5. 维度层级模型 (dimension_hierarchy)
6. 字段映射模型 (field_mapping)
7. 重规划模型 (replan)

注意：以下模型已迁移到 agents/ 层：
- Step1 模型 → agents/semantic_parser/models/step1.py
- Step2 模型 → agents/semantic_parser/models/step2.py
- Observer 模型 → agents/semantic_parser/models/observer.py
- ParseResult 模型 → agents/semantic_parser/models/parse_result.py
- Insight 模型 → agents/insight/models/insight.py
"""

# Enums
from .enums import (
    AggregationType,
    DateGranularity,
    DateRangeType,
    DimensionCategory,
    DimensionLevel,
    FilterType,
    HowType,
    IntentType,
    MappingSource,
    ObserverDecision,
    RankStyle,
    RelativeTo,
    SortDirection,
    TextMatchType,
    WindowAggregation,
)

# Fields
from .fields import (
    DimensionField,
    MeasureField,
    SortSpec,
)

# Computations
from .computations import (
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
from .filters import (
    DateRangeFilter,
    Filter,
    NumericRangeFilter,
    SetFilter,
    TextMatchFilter,
    TopNFilter,
)

# Query
from .query import SemanticQuery

# Validation
from .validation import (
    ColumnInfo,
    QueryResult,
    ValidationError,
    ValidationErrorType,
    ValidationResult,
)

# Data Model (包含 FieldMetadata)
from .data_model import (
    FieldMetadata,
    DataModel,
    LogicalTable,
    LogicalTableRelationship,
)

# Dimension Hierarchy
from .dimension_hierarchy import (
    DimensionAttributes,
    DimensionHierarchyResult,
)

# Field Mapping
from .field_mapping import (
    SingleSelectionResult,
    BatchSelectionResult,
    AlternativeMapping,
    FieldMapping,
    MappedQuery,
)

# Replan
from .replan import (
    ExplorationQuestion,
    ReplanDecision,
)

# Execute Result
from .execute_result import (
    ExecuteResult,
    ColumnMetadata,
    RowData,
    RowValue,
)

# Query Request (abstract base)
from .query_request import (
    QueryRequest,
)


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
    "ObserverDecision",
    "RankStyle",
    "RelativeTo",
    "SortDirection",
    "TextMatchType",
    "WindowAggregation",
    # Fields
    "DimensionField",
    "MeasureField",
    "SortSpec",
    # Computations
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
    # Union type
    "Computation",
    # Filters
    "DateRangeFilter",
    "Filter",
    "NumericRangeFilter",
    "SetFilter",
    "TextMatchFilter",
    "TopNFilter",
    # Query
    "SemanticQuery",
    # Validation
    "ColumnInfo",
    "QueryResult",
    "ValidationError",
    "ValidationErrorType",
    "ValidationResult",
    # Data Model
    "FieldMetadata",
    "DataModel",
    "LogicalTable",
    "LogicalTableRelationship",
    # Dimension Hierarchy
    "DimensionAttributes",
    "DimensionHierarchyResult",
    # Field Mapping
    "SingleSelectionResult",
    "BatchSelectionResult",
    "AlternativeMapping",
    "FieldMapping",
    "MappedQuery",
    # Replan
    "ExplorationQuestion",
    "ReplanDecision",
    # Execute Result
    "ExecuteResult",
    "ColumnMetadata",
    "RowData",
    "RowValue",
    # Query Request
    "QueryRequest",
]
