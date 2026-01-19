# -*- coding: utf-8 -*-
"""
Core Data Models - 平台无关的语义层模型

本模块包含所有平台无关的数据模型，按领域分类：

1. 基础模型 (enums, fields, filters, computations)
2. 查询模型 (query)
3. 执行结果模型 (execute_result)
4. 验证模型 (validation)

注意：以下模型已迁移到其他层：
- DataModel, FieldMetadata → infra/storage/data_model.py
- DimensionHierarchy → agents/dimension_hierarchy/models/hierarchy.py
- FieldMapping, MappedQuery → agents/field_mapper/models/mapping.py
- Step1 模型 → agents/semantic_parser/models/step1.py
- Step2 模型 → agents/semantic_parser/models/step2.py
- Observer 模型 → agents/semantic_parser/models/observer.py
- ParseResult 模型 → agents/semantic_parser/models/parse_result.py
- Insight 模型 → agents/insight/models/insight.py
- Replan 模型 → agents/replanner/models/output.py (ExplorationQuestion, ReplanDecision)
"""

# Enums
from tableau_assistant.src.core.models.enums import (
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
from tableau_assistant.src.core.models.fields import (
    DimensionField,
    MeasureField,
    SortSpec,
)

# Computations
from tableau_assistant.src.core.models.computations import (
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
from tableau_assistant.src.core.models.filters import (
    DateRangeFilter,
    Filter,
    NumericRangeFilter,
    SetFilter,
    TextMatchFilter,
    TopNFilter,
)

# Query
from tableau_assistant.src.core.models.query import SemanticQuery

# Validation
from tableau_assistant.src.core.models.validation import (
    ValidationError,
    ValidationErrorType,
    ValidationResult,
)

# Execute Result
from tableau_assistant.src.core.models.execute_result import (
    ExecuteResult,
    ColumnInfo,
    RowData,
    RowValue,
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
    "ValidationError",
    "ValidationErrorType",
    "ValidationResult",
    # Execute Result
    "ExecuteResult",
    "ColumnInfo",
    "RowData",
    "RowValue",
]
