"""
Semantic models - Pure semantic layer (no VizQL concepts)

按规范文档重构，遵循 `prompt-and-schema-design.md` 中定义的设计规范。

Contains:
- enums.py: AnalysisType, ComputationScope, FilterType, etc.
- query.py: SemanticQuery, AnalysisSpec, MappedQuery
"""

from .enums import (
    # 分析类型
    AnalysisType,
    ComputationScope,
    
    # 映射来源
    MappingSource,
    
    # 筛选类型
    FilterType,
    
    # 时间粒度
    TimeGranularity,
    
    # 聚合类型
    AggregationType,
    
    # 筛选操作符（保留用于兼容）
    FilterOperator,
    
    # 维度层级
    DimensionCategory,
    DimensionLevel,
    
    # 时间范围类型（新增）
    TimeRangeType,
    RelativeTimeType,
    PeriodUnit,
)

from .query import (
    # SemanticQuery 组件
    MeasureSpec,
    DimensionSpec,
    FilterSpec,
    TimeRangeSpec,
    AnalysisSpec,
    OutputControl,
    SemanticQuery,
    
    # MappedQuery 组件
    FieldMapping,
    MappedQuery,
)

__all__ = [
    # ========== Enums ==========
    "AnalysisType",
    "ComputationScope",
    "MappingSource",
    "FilterType",
    "TimeGranularity",
    "AggregationType",
    "FilterOperator",
    "DimensionCategory",
    "DimensionLevel",
    "TimeRangeType",
    "RelativeTimeType",
    "PeriodUnit",
    
    # ========== SemanticQuery ==========
    "MeasureSpec",
    "DimensionSpec",
    "FilterSpec",
    "TimeRangeSpec",
    "AnalysisSpec",
    "OutputControl",
    "SemanticQuery",
    
    # ========== MappedQuery ==========
    "FieldMapping",
    "MappedQuery",
]
