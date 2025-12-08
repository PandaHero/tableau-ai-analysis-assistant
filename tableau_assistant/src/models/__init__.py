"""
Data models module (Refactored)

Organized into subpackages:
- workflow/: LangGraph state and context models
- semantic/: Pure semantic layer models (SemanticQuery, MappedQuery)
- vizql/: VizQL technical models (VizQLQuery, QueryResult)
- common/: Shared models (errors, metadata)

Legacy models are kept for backward compatibility but will be deprecated.
"""

# ========== Workflow Models (New Location) ==========
from .workflow import (
    VizQLState,
    VizQLInput,
    VizQLOutput,
    VizQLContext,
    create_initial_state,
)

# Context utilities (for backward compatibility with old import path)
from .workflow.context import get_tableau_config, set_tableau_config

# ========== Semantic Models (New - Updated per data-models.md spec) ==========
from .semantic import (
    # Enums
    AnalysisType,
    ComputationScope,
    MappingSource,
    FilterType,  # NEW: time_range, set, quantitative, match
    TimeGranularity as SemanticTimeGranularity,  # Avoid conflict with legacy
    AggregationType as SemanticAggregationType,  # Avoid conflict with legacy
    DimensionCategory,
    DimensionLevel,
    
    # Query components
    MeasureSpec,
    DimensionSpec,
    FilterSpec,
    AnalysisSpec,
    OutputControl,
    SemanticQuery,
    
    # Field mapping
    FieldMapping,
    MappedQuery,
)

# ========== VizQL Models (New Location) ==========
from .vizql import (
    # Enums
    FunctionEnum,
    SortDirection,
    ReturnFormat,
    DataType,
    
    # Field types
    BasicField,
    FunctionField,
    CalculationField,
    VizQLField,
    
    # Filter types
    FilterField,
    SetFilter,
    TopNFilter,
    MatchFilter,
    QuantitativeNumericalFilter,
    QuantitativeDateFilter,
    RelativeDateFilter,
    VizQLFilter,
    
    # Query structure
    VizQLQuery,
    Connection,
    Datasource,
    QueryOptions,
    QueryRequest,
    QueryOutput,
    
    # Metadata
    VizQLFieldMetadata,
    VizQLMetadataOutput,
    
    # Result
    QueryResult,
    
    # Helper functions
    create_basic_field,
    create_function_field,
    create_set_filter,
    create_relative_date_filter,
)

# ========== Common Models (New) ==========
from .common import (
    TransientError,
    PermanentError,
    UserError,
    ErrorCategory,
    classify_error,
)

# ========== Legacy Imports (Backward Compatibility) ==========
# These will be deprecated in future versions

from .api import (
    # Request models
    VizQLQueryRequest,
    QuestionBoostRequest,
    MetadataInitRequest,
    
    # Response models
    VizQLQueryResponse,
    QuestionBoostResponse,
    MetadataInitResponse,
    KeyFinding,
    AnalysisStep,
    Recommendation,
    Visualization,
    
    # Error models
    ErrorResponse,
    ErrorDetail,
    
    # Stream event models
    StreamEvent
)

from .question import (
    # Enums
    EntityRole,
    AggregationType as LegacyAggregationType,
    EntityType,
    DateFunction,
    QuestionType,
    Complexity,
    TimeRangeType,
    RelativeType,
    PeriodType,
    SubQuestionExecutionType,
    
    # Models
    QueryEntity,
    TimeRange,
    ReasoningStep,
    QuestionUnderstanding,
    SubQuestion,
    QuerySubQuestion,
    
    # Helper functions
    create_entity,
    create_time_range_absolute,
    create_time_range_relative,
)

from .boost import QuestionBoost

from .metadata import (
    FieldMetadata,
    Metadata,
)

from .data_model import (
    LogicalTable,
    LogicalTableRelationship,
    DataModel,
)

from .result import (
    # Enums
    InsightType,
    Importance,
    AnomalyType,
    TrendDirection,
    
    # Query results
    SubtaskResult,
    MergedData,
    
    # Statistical analysis
    DescriptiveStatistics,
    AnomalyDetection,
    TrendAnalysis,
    StatisticsResult,
    
    # Insights
    Insight,
    InsightCollection,
    
    # Replanning
    ReplanDecision,
    
    # Final report
    FinalReport,
    
    # Helper functions
    create_insight,
    create_anomaly_detection
)


__all__ = [
    # ========== Workflow ==========
    "VizQLState",
    "VizQLInput",
    "VizQLOutput",
    "VizQLContext",
    "create_initial_state",
    
    # ========== Semantic (New - Updated per data-models.md spec) ==========
    "AnalysisType",
    "ComputationScope",
    "MappingSource",
    "FilterType",
    "SemanticTimeGranularity",
    "SemanticAggregationType",
    "DimensionCategory",
    "DimensionLevel",
    "MeasureSpec",
    "DimensionSpec",
    "FilterSpec",
    "AnalysisSpec",
    "OutputControl",
    "SemanticQuery",
    "FieldMapping",
    "MappedQuery",
    
    # ========== VizQL ==========
    "FunctionEnum",
    "SortDirection",
    "ReturnFormat",
    "DataType",
    "BasicField",
    "FunctionField",
    "CalculationField",
    "VizQLField",
    "FilterField",
    "SetFilter",
    "TopNFilter",
    "MatchFilter",
    "QuantitativeNumericalFilter",
    "QuantitativeDateFilter",
    "RelativeDateFilter",
    "VizQLFilter",
    "VizQLQuery",
    "Connection",
    "Datasource",
    "QueryOptions",
    "QueryRequest",
    "QueryOutput",
    "VizQLFieldMetadata",
    "VizQLMetadataOutput",
    "QueryResult",
    "create_basic_field",
    "create_function_field",
    "create_set_filter",
    "create_relative_date_filter",
    
    # ========== Common ==========
    "TransientError",
    "PermanentError",
    "UserError",
    "ErrorCategory",
    "classify_error",
    
    # ========== Legacy (Backward Compatibility) ==========
    "VizQLQueryRequest",
    "QuestionBoostRequest",
    "MetadataInitRequest",
    "VizQLQueryResponse",
    "QuestionBoostResponse",
    "MetadataInitResponse",
    "KeyFinding",
    "AnalysisStep",
    "Recommendation",
    "Visualization",
    "ErrorResponse",
    "ErrorDetail",
    "StreamEvent",
    "EntityRole",
    "LegacyAggregationType",
    "EntityType",
    "DateFunction",
    "QuestionType",
    "Complexity",
    "TimeRangeType",
    "RelativeType",
    "PeriodType",
    "SubQuestionExecutionType",
    "QueryEntity",
    "TimeRange",
    "ReasoningStep",
    "QuestionUnderstanding",
    "SubQuestion",
    "QuerySubQuestion",
    "create_entity",
    "create_time_range_absolute",
    "create_time_range_relative",
    "QuestionBoost",
    "FieldMetadata",
    "Metadata",
    "LogicalTable",
    "LogicalTableRelationship",
    "DataModel",
    "InsightType",
    "Importance",
    "AnomalyType",
    "TrendDirection",
    "SubtaskResult",
    "MergedData",
    "DescriptiveStatistics",
    "AnomalyDetection",
    "TrendAnalysis",
    "StatisticsResult",
    "Insight",
    "InsightCollection",
    "ReplanDecision",
    "FinalReport",
    "create_insight",
    "create_anomaly_detection",
]
