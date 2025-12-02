"""
Data models module

Contains all data model definitions:
- state.py: LangGraph state models
- context.py: Runtime context models
- api.py: API input/output models
- vizql_types.py: VizQL query types
- question.py: Question-related models
- result.py: Result-related models
"""

# ========== LangGraph 1.0 Models ==========
from .state import (
    VizQLState,
    VizQLInput,
    VizQLOutput,
    create_initial_state
)

from .context import VizQLContext

# ========== API Models ==========
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

# ========== VizQL Types ==========
from .vizql_types import (
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
    
    # VizQL API Metadata (for API responses)
    VizQLFieldMetadata,
    VizQLMetadataOutput,
    
    # Helper functions
    create_basic_field,
    create_function_field,
    create_set_filter,
    create_relative_date_filter
)

# ========== Question Models ==========
from .question import (
    # Enums
    QuestionType,
    Complexity,
    TimeRangeType,
    RelativeType,
    PeriodType,
    
    # Models
    TimeRange,
    DateRequirements,
    QuestionUnderstanding,
    
    # Helper functions
    create_time_range_absolute,
    create_time_range_relative,
    create_time_range_current,
)

# ========== Boost Models ==========
from .boost import QuestionBoost

# ========== Internal Metadata Models ==========
from .metadata import (
    FieldMetadata,  # Internal field metadata model
    Metadata,       # Internal datasource metadata model
)

# ========== Data Model ==========
from .data_model import (
    LogicalTable,
    LogicalTableRelationship,
    DataModel,
)

# ========== Result Models ==========
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
    # LangGraph 1.0
    "VizQLState",
    "VizQLInput",
    "VizQLOutput",
    "VizQLContext",
    "create_initial_state",
    
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
    "create_basic_field",
    "create_function_field",
    "create_set_filter",
    "create_relative_date_filter",
    
    # Question
    "QuestionType",
    "Complexity",
    "TimeRangeType",
    "RelativeType",
    "PeriodType",
    "TimeRange",
    "DateRequirements",
    "QuestionUnderstanding",
    "create_time_range_absolute",
    "create_time_range_relative",
    "create_time_range_current",
    
    # Boost
    "QuestionBoost",
    
    # Internal Metadata
    "FieldMetadata",
    "Metadata",
    
    # Data Model
    "LogicalTable",
    "LogicalTableRelationship",
    "DataModel",
    
    # Result
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
