"""Core enumerations for the semantic layer.

All enums are platform-agnostic and represent user intent, not platform-specific concepts.
"""

from enum import Enum


class AggregationType(str, Enum):
    """Aggregation type for measures."""
    SUM = "SUM"
    AVG = "AVG"
    COUNT = "COUNT"
    COUNT_DISTINCT = "COUNT_DISTINCT"
    MIN = "MIN"
    MAX = "MAX"
    MEDIAN = "MEDIAN"
    STDEV = "STDEV"
    VAR = "VAR"


class DateGranularity(str, Enum):
    """Date granularity for time dimensions."""
    YEAR = "YEAR"
    QUARTER = "QUARTER"
    MONTH = "MONTH"
    WEEK = "WEEK"
    DAY = "DAY"
    HOUR = "HOUR"
    MINUTE = "MINUTE"


class SortDirection(str, Enum):
    """Sort direction."""
    ASC = "ASC"
    DESC = "DESC"


class FilterType(str, Enum):
    """Filter type."""
    SET = "SET"
    DATE_RANGE = "DATE_RANGE"
    NUMERIC_RANGE = "NUMERIC_RANGE"
    TEXT_MATCH = "TEXT_MATCH"
    TOP_N = "TOP_N"


class DateRangeType(str, Enum):
    """Date range type for relative date filters."""
    CURRENT = "CURRENT"      # Current period (this month, this year)
    PREVIOUS = "PREVIOUS"    # Previous period (last month, last year)
    PREVIOUS_N = "PREVIOUS_N"  # Previous N periods
    NEXT = "NEXT"            # Next period
    NEXT_N = "NEXT_N"        # Next N periods
    TO_DATE = "TO_DATE"      # Year to date, month to date
    CUSTOM = "CUSTOM"        # Custom date range


class TextMatchType(str, Enum):
    """Text match type for text filters."""
    CONTAINS = "CONTAINS"
    STARTS_WITH = "STARTS_WITH"
    ENDS_WITH = "ENDS_WITH"
    EXACT = "EXACT"
    REGEX = "REGEX"


class HowType(str, Enum):
    """Computation type (Step 1 output).
    
    Represents the high-level analysis type detected from user question.
    Used by LLM to classify the computation complexity.
    
    Mapping to OperationType (for LLM self-validation):
    - RANKING → RANK, DENSE_RANK
    - CUMULATIVE → RUNNING_SUM, RUNNING_AVG, MOVING_AVG, MOVING_SUM
    - COMPARISON → PERCENT, DIFFERENCE, GROWTH_RATE, YEAR_AGO, PERIOD_AGO
    - GRANULARITY → FIXED
    """
    SIMPLE = "SIMPLE"          # Simple aggregation, no complex computation
    RANKING = "RANKING"        # 排名/Top N
    CUMULATIVE = "CUMULATIVE"  # 累计/累积
    COMPARISON = "COMPARISON"  # 占比/同比/环比
    GRANULARITY = "GRANULARITY"  # 固定粒度聚合


class OperationType(str, Enum):
    """Operation type (Step 2 output).
    
    Specific computation operation inferred from restated_question.
    Must match HowType via OPERATION_TYPE_MAPPING (LLM self-validation).
    """
    # RANKING operations
    RANK = "RANK"              # Standard ranking (1, 2, 3, ...)
    DENSE_RANK = "DENSE_RANK"  # Dense ranking (1, 2, 2, 3, ...)
    
    # CUMULATIVE operations
    RUNNING_SUM = "RUNNING_SUM"    # Cumulative sum
    RUNNING_AVG = "RUNNING_AVG"    # Cumulative average
    MOVING_AVG = "MOVING_AVG"      # Moving average (params: window_size)
    MOVING_SUM = "MOVING_SUM"      # Moving sum (params: window_size)
    
    # COMPARISON operations
    PERCENT = "PERCENT"            # Percentage of total
    DIFFERENCE = "DIFFERENCE"      # Difference from reference
    GROWTH_RATE = "GROWTH_RATE"    # Growth rate
    YEAR_AGO = "YEAR_AGO"          # Year-over-year comparison
    PERIOD_AGO = "PERIOD_AGO"      # Period-over-period comparison
    
    # GRANULARITY operations
    FIXED = "FIXED"                # Fixed granularity aggregation (LOD)


class IntentType(str, Enum):
    """Intent type (Step 1 output).
    
    Classification of user question intent.
    Determines the processing branch after Step 1.
    """
    DATA_QUERY = "DATA_QUERY"        # Valid data query, has queryable fields
    CLARIFICATION = "CLARIFICATION"  # Needs clarification, references unspecified values
    GENERAL = "GENERAL"              # General question about metadata/fields
    IRRELEVANT = "IRRELEVANT"        # Not related to data analysis


class ObserverDecision(str, Enum):
    """Observer decision (Observer output).
    
    Decision made by Observer after checking consistency between Step 1 and Step 2.
    """
    ACCEPT = "ACCEPT"    # All checks pass, accept Step 2 result
    CORRECT = "CORRECT"  # Small conflict, Observer can fix it
    RETRY = "RETRY"      # Large conflict, need to re-run Step 2
    CLARIFY = "CLARIFY"  # Cannot determine, need user clarification


# OPERATION_TYPE_MAPPING - Reference for LLM self-validation
# This mapping is used by LLM (not code) to validate operation_check
OPERATION_TYPE_MAPPING = {
    HowType.RANKING: [OperationType.RANK, OperationType.DENSE_RANK],
    HowType.CUMULATIVE: [
        OperationType.RUNNING_SUM, OperationType.RUNNING_AVG,
        OperationType.MOVING_AVG, OperationType.MOVING_SUM
    ],
    HowType.COMPARISON: [
        OperationType.PERCENT, OperationType.DIFFERENCE,
        OperationType.GROWTH_RATE, OperationType.YEAR_AGO,
        OperationType.PERIOD_AGO
    ],
    HowType.GRANULARITY: [OperationType.FIXED],
}


# ═══════════════════════════════════════════════════════════════════════════
# Field Mapper Enums
# ═══════════════════════════════════════════════════════════════════════════

class MappingSource(str, Enum):
    """
    Field mapping source enum
    
    Indicates how a field mapping was determined.
    """
    RAG_DIRECT = "rag_direct"
    RAG_HIGH_CONFIDENCE = "rag_high_confidence"
    RAG_LLM_FALLBACK = "rag_llm_fallback"
    CACHE_HIT = "cache_hit"
    EXACT_MATCH = "exact_match"
    LLM_ONLY = "llm_only"


class DimensionCategory(str, Enum):
    """
    Dimension category enum
    
    Categorizes dimensions for hierarchy inference.
    """
    TIME = "time"
    GEOGRAPHY = "geography"
    PRODUCT = "product"
    CUSTOMER = "customer"
    ORGANIZATION = "organization"
    FINANCIAL = "financial"
    OTHER = "other"


class DimensionLevel(str, Enum):
    """
    Dimension level enum
    
    Indicates the level within a dimension hierarchy.
    """
    TOP = "top"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    DETAIL = "detail"
