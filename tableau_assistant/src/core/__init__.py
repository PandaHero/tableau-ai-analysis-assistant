"""Core layer - Platform-agnostic semantic models and interfaces.

This is the heart of the system, defining platform-independent semantic models
that can be adapted to any BI platform (Tableau, Power BI, Superset, etc.).

Modules:
    models: Core data models (SemanticQuery, Computation, Step1Output, etc.)
    interfaces: Abstract base classes for platform adapters
"""

from .interfaces import (
    BaseFieldMapper,
    BasePlatformAdapter,
    BaseQueryBuilder,
)
from .models import (
    # Enums
    AggregationType,
    DateGranularity,
    DateRangeType,
    FilterType,
    HowType,
    IntentType,
    ObserverDecision,
    OperationType,
    SortDirection,
    TextMatchType,
    OPERATION_TYPE_MAPPING,
    # Fields
    DimensionField,
    MeasureField,
    Sort,
    # Computations
    Computation,
    Operation,
    # Filters
    DateRangeFilter,
    Filter,
    NumericRangeFilter,
    SetFilter,
    TextMatchFilter,
    TopNFilter,
    # Query
    SemanticQuery,
    # Step 1
    DimensionSpec,
    FilterSpec,
    Intent,
    MeasureSpec,
    Step1Output,
    What,
    Where,
    # Step 2
    Step2Output,
    Step2Validation,
    ValidationCheck,
    # Observer
    Conflict,
    Correction,
    ObserverInput,
    ObserverOutput,
    # Parse Result
    ClarificationQuestion,
    SemanticParseResult,
    # Validation
    ColumnInfo,
    QueryResult,
    ValidationError,
    ValidationErrorType,
    ValidationResult,
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
    "OperationType",
    "SortDirection",
    "TextMatchType",
    "OPERATION_TYPE_MAPPING",
    # Fields
    "DimensionField",
    "MeasureField",
    "Sort",
    # Computations
    "Computation",
    "Operation",
    # Filters
    "DateRangeFilter",
    "Filter",
    "NumericRangeFilter",
    "SetFilter",
    "TextMatchFilter",
    "TopNFilter",
    # Query
    "SemanticQuery",
    # Step 1
    "DimensionSpec",
    "FilterSpec",
    "Intent",
    "MeasureSpec",
    "Step1Output",
    "What",
    "Where",
    # Step 2
    "Step2Output",
    "Step2Validation",
    "ValidationCheck",
    # Observer
    "Conflict",
    "Correction",
    "ObserverInput",
    "ObserverOutput",
    # Parse Result
    "ClarificationQuestion",
    "SemanticParseResult",
    # Validation
    "ColumnInfo",
    "QueryResult",
    "ValidationError",
    "ValidationErrorType",
    "ValidationResult",
]
