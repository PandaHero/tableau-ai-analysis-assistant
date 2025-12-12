"""
Data models module

Organized into subpackages:
- workflow/: LangGraph state and context models
- semantic/: Pure semantic layer models (SemanticQuery, MappedQuery)
- vizql/: VizQL technical models (VizQLQuery, ExecuteResult)
- common/: Shared error models
- api/: API request/response models
- metadata/: Metadata related models
- insight/: Insight analysis models
- replanner/: Replanner agent models
- field_mapper/: Field mapper agent models
"""

# ========== Workflow Models ==========
from .workflow import (
    VizQLState,
    VizQLInput,
    VizQLOutput,
    VizQLContext,
    create_initial_state,
)


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
    ExecuteResult,
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
)

# ========== Insight Models ==========
from .insight import (
    # Progressive insight models
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

# ========== Field Mapper Models ==========
from .field_mapper import (
    SingleSelectionResult,
    BatchSelectionResult,
    AlternativeMapping,
    FieldMapping,
    MappedQuery,
)


__all__ = [
    # Workflow
    "VizQLState",
    "VizQLInput",
    "VizQLOutput",
    "VizQLContext",
    "create_initial_state",
    
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
    "ExecuteResult",
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
    
    # Insight
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
    
    # Field Mapper
    "SingleSelectionResult",
    "BatchSelectionResult",
    "AlternativeMapping",
    "FieldMapping",
    "MappedQuery",
]
