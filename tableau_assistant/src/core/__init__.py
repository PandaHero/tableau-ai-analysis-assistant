"""Core layer - Platform-agnostic semantic models and interfaces.

This is the heart of the system, defining platform-independent semantic models
that can be adapted to any BI platform (Tableau, Power BI, Superset, etc.).

Modules:
    models: Core data models (SemanticQuery, Computation, etc.)
    interfaces: Abstract base classes for platform adapters

Note:
    - State types (VizQLState, etc.) are in orchestration/workflow/state.py
    - Agent-specific models (Step1, Step2, ParseResult) are in agents/{agent}/models/
    - DataModel, FieldMetadata are in infra/storage/data_model.py
    - DimensionHierarchy models are in agents/dimension_hierarchy/models/hierarchy.py
    - FieldMapping models are in agents/field_mapper/models/mapping.py
"""

from tableau_assistant.src.core.interfaces import (
    BaseFieldMapper,
    BasePlatformAdapter,
    BaseQueryBuilder,
)
from tableau_assistant.src.core.models import (

    # Enums
    AggregationType,
    DateGranularity,
    DateRangeType,
    FilterType,
    HowType,
    IntentType,
    ObserverDecision,
    RankStyle,
    RelativeTo,
    SortDirection,
    TextMatchType,
    WindowAggregation,
    # Fields
    DimensionField,
    MeasureField,
    SortSpec,
    # Computations
    Computation,
    # Filters
    DateRangeFilter,
    Filter,
    NumericRangeFilter,
    SetFilter,
    TextMatchFilter,
    TopNFilter,
    # Query
    SemanticQuery,
    # Validation
    ValidationError,
    ValidationErrorType,
    ValidationResult,
    # Execute Result
    ExecuteResult,
    ColumnInfo,
)

__all__ = [
    # Interfaces
    "BaseFieldMapper",
    "BasePlatformAdapter",
    "BaseQueryBuilder",
    # Enums
    "AggregationType",
    "DateGranularity",
    "DateRangeType",
    "FilterType",
    "HowType",
    "IntentType",
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
]
