"""
Data models module

Organized into subpackages:
- workflow/: LangGraph state and context models
- semantic/: Pure semantic layer models (SemanticQuery, MappedQuery)
- vizql/: VizQL technical models (VizQLQuery, QueryResult)
- common/: Shared error models
- api/: API request/response models
- metadata/: Metadata related models
- question/: Question understanding models
- insight/: Insight analysis models
- replanner/: Replanner agent models
"""

# ========== Workflow Models ==========
from .workflow import (
    VizQLState,
    VizQLInput,
    VizQLOutput,
    VizQLContext,
    create_initial_state,
)
from .workflow.context import get_tableau_config, set_tableau_config

# ========== Semantic Models ==========
from .semantic import (
    # Enums
    AnalysisType,
    ComputationScope,
    MappingSource,
    FilterType,
    TimeGranularity as SemanticTimeGranularity,
    AggregationType as SemanticAggregationType,
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

# ========== VizQL Models ==========
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

# ========== Common Models ==========
from .common import (
    TransientError,
    PermanentError,
    UserError,
    ErrorCategory,
    classify_error,
)

# ========== API Models ==========
from .api import (
    VizQLQueryRequest,
    QuestionBoostRequest,
    MetadataInitRequest,
    VizQLQueryResponse,
    QuestionBoostResponse,
    MetadataInitResponse,
    KeyFinding,
    AnalysisStep,
    Recommendation,
    Visualization,
    ErrorResponse,
    ErrorDetail,
    StreamEvent,
)

# ========== Metadata Models ==========
from .metadata import (
    FieldMetadata,
    Metadata,
    LogicalTable,
    LogicalTableRelationship,
    DataModel,
    DimensionHierarchyResult,
    DimensionAttributes,
    HierarchyLevel,
)

# ========== Question Models ==========
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
    # Time granularity
    TimeGranularity,
    get_field_granularity_from_format,
)

# ========== Insight Models ==========
from .insight import (
    # Legacy
    InsightType,
    Importance,
    AnomalyType,
    TrendDirection,
    SubtaskResult,
    MergedData,
    DescriptiveStatistics,
    AnomalyDetection,
    TrendAnalysis,
    StatisticsResult,
    LegacyInsight,
    InsightCollection,
    FinalReport,
    create_insight,
    create_anomaly_detection,
    # Progressive insight
    ChunkPriority,
    ColumnStats,
    SemanticGroup,
    DataProfile,
    AnomalyDetail,
    AnomalyResult,
    DataChunk,
    TailDataSummary,
    PriorityChunk,
    Insight,
    InsightQuality,
    InsightResult,
    NextBiteDecision,
    ClusterInfo,
    DataInsightProfile,
)

# ========== Replanner Models ==========
from .replanner import (
    ExplorationQuestion,
    ReplanDecision,
)


__all__ = [
    # Workflow
    "VizQLState",
    "VizQLInput",
    "VizQLOutput",
    "VizQLContext",
    "create_initial_state",
    "get_tableau_config",
    "set_tableau_config",
    
    # Semantic
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
    
    # VizQL
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
    
    # Common
    "TransientError",
    "PermanentError",
    "UserError",
    "ErrorCategory",
    "classify_error",
    
    # API
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
    
    # Metadata
    "FieldMetadata",
    "Metadata",
    "LogicalTable",
    "LogicalTableRelationship",
    "DataModel",
    "DimensionHierarchyResult",
    "DimensionAttributes",
    "HierarchyLevel",
    
    # Question
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
    "TimeGranularity",
    "get_field_granularity_from_format",
    
    # Insight
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
    "LegacyInsight",
    "InsightCollection",
    "FinalReport",
    "create_insight",
    "create_anomaly_detection",
    "ChunkPriority",
    "ColumnStats",
    "SemanticGroup",
    "DataProfile",
    "AnomalyDetail",
    "AnomalyResult",
    "DataChunk",
    "TailDataSummary",
    "PriorityChunk",
    "Insight",
    "InsightQuality",
    "InsightResult",
    "NextBiteDecision",
    "ClusterInfo",
    "DataInsightProfile",
    
    # Replanner
    "ExplorationQuestion",
    "ReplanDecision",
]
