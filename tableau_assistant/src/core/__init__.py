"""Core layer - Platform-agnostic semantic models and interfaces.

This is the heart of the system, defining platform-independent semantic models
that can be adapted to any BI platform (Tableau, Power BI, Superset, etc.).

Modules:
    models: Core data models (SemanticQuery, Computation, Step1Output, etc.)
    interfaces: Abstract base classes for platform adapters
    state: Workflow state types (VizQLState, etc.)
"""

from .interfaces import (
    BaseFieldMapper,
    BasePlatformAdapter,
    BaseQueryBuilder,
)
from .models import (
    # Enums
    AggregationType,
    CalcAggregation,
    CalcType,
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
    # Fields
    DimensionField,
    MeasureField,
    Sort,
    # Computations
    CalcParams,
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
    # Execute Result
    ExecuteResult,
    # Query Request
    QueryRequest,
)
from .state import (
    VizQLState,
    VizQLInput,
    VizQLOutput,
    create_initial_state,
    ErrorRecord,
    WarningRecord,
)

__all__ = [
    # Interfaces
    "BaseFieldMapper",
    "BasePlatformAdapter",
    "BaseQueryBuilder",
    # Enums
    "AggregationType",
    "CalcAggregation",
    "CalcType",
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
    # Fields
    "DimensionField",
    "MeasureField",
    "Sort",
    # Computations
    "CalcParams",
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
    # Execute Result
    "ExecuteResult",
    # State
    "VizQLState",
    "VizQLInput",
    "VizQLOutput",
    "create_initial_state",
    "ErrorRecord",
    "WarningRecord",
]
