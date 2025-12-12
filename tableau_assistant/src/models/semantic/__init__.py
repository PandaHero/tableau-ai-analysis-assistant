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
    
    # 维度层级
    DimensionCategory,
    DimensionLevel,
    
    # 日期枚举（与 VizQL API 对齐）
    TimeFilterMode,
    PeriodType,
    DateRangeType,
)

from .query import (
    # SemanticQuery 组件
    MeasureSpec,
    DimensionSpec,
    FilterSpec,
    TimeFilterSpec,
    AnalysisSpec,
    OutputControl,
    SemanticQuery,
)

# 注意: FieldMapping 和 MappedQuery 已移至 models/field_mapper/models.py
# 请从 tableau_assistant.src.models.field_mapper 导入

__all__ = [
    # ========== Enums ==========
    "AnalysisType",
    "ComputationScope",
    "MappingSource",
    "FilterType",
    "TimeGranularity",
    "AggregationType",
    "DimensionCategory",
    "DimensionLevel",
    "TimeFilterMode",
    "PeriodType",
    "DateRangeType",
    
    # ========== SemanticQuery ==========
    "MeasureSpec",
    "DimensionSpec",
    "FilterSpec",
    "TimeFilterSpec",
    "AnalysisSpec",
    "OutputControl",
    "SemanticQuery",
    
]
