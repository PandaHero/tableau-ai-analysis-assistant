# -*- coding: utf-8 -*-
"""Core enumerations for the semantic layer.

All enums are platform-agnostic and represent user intent, not platform-specific concepts.

Organization:
1. Common Enums (Cross-Agent Shared)
2. Computation Parameter Enums (grouped by calc type)
3. Semantic Parser Enums
4. Field Mapper Enums
"""

from enum import Enum


# ═══════════════════════════════════════════════════════════════════════════
# Common Enums (Cross-Agent Shared)
# ═══════════════════════════════════════════════════════════════════════════

class AggregationType(str, Enum):
    """Aggregation function for measures and LOD expressions.
    
    <rule>
    total/sum -> SUM
    average/mean -> AVG
    count/number of -> COUNT
    distinct count/unique count -> COUNTD
    minimum/lowest -> MIN
    maximum/highest -> MAX
    median -> MEDIAN
    standard deviation -> STDEV
    variance -> VAR
    </rule>
    """
    SUM = "SUM"
    AVG = "AVG"
    COUNT = "COUNT"
    COUNTD = "COUNTD"
    MIN = "MIN"
    MAX = "MAX"
    MEDIAN = "MEDIAN"
    STDEV = "STDEV"
    VAR = "VAR"


class DateGranularity(str, Enum):
    """Date granularity: YEAR | QUARTER | MONTH | WEEK | DAY | HOUR | MINUTE"""
    YEAR = "YEAR"
    QUARTER = "QUARTER"
    MONTH = "MONTH"
    WEEK = "WEEK"
    DAY = "DAY"
    HOUR = "HOUR"
    MINUTE = "MINUTE"


class SortDirection(str, Enum):
    """Sort direction: DESC=descending (high to low) | ASC=ascending (low to high)"""
    ASC = "ASC"
    DESC = "DESC"


class FilterType(str, Enum):
    """Filter type: SET | DATE_RANGE | NUMERIC_RANGE | TEXT_MATCH | TOP_N"""
    SET = "SET"
    DATE_RANGE = "DATE_RANGE"
    NUMERIC_RANGE = "NUMERIC_RANGE"
    TEXT_MATCH = "TEXT_MATCH"
    TOP_N = "TOP_N"


class DateRangeType(str, Enum):
    """Date range type: CUSTOM (LLM calculates concrete start_date/end_date)"""
    CUSTOM = "CUSTOM"


class TextMatchType(str, Enum):
    """Text match type: CONTAINS | STARTS_WITH | ENDS_WITH | EXACT | REGEX"""
    CONTAINS = "CONTAINS"
    STARTS_WITH = "STARTS_WITH"
    ENDS_WITH = "ENDS_WITH"
    EXACT = "EXACT"
    REGEX = "REGEX"


# ═══════════════════════════════════════════════════════════════════════════
# Computation Parameter Enums (Grouped by Calc Type)
# ═══════════════════════════════════════════════════════════════════════════

# --- Ranking Parameters ---

class RankStyle(str, Enum):
    """Ranking style: COMPETITION=1,2,2,4 | DENSE=1,2,2,3 | UNIQUE=1,2,3,4"""
    COMPETITION = "COMPETITION"
    DENSE = "DENSE"
    UNIQUE = "UNIQUE"


# --- Difference Parameters ---

class RelativeTo(str, Enum):
    """Difference reference point: PREVIOUS | NEXT | FIRST | LAST"""
    PREVIOUS = "PREVIOUS"
    NEXT = "NEXT"
    FIRST = "FIRST"
    LAST = "LAST"


# --- Running/Moving Parameters ---

class WindowAggregation(str, Enum):
    """Window aggregation function for RUNNING_TOTAL and MOVING_CALC: SUM | AVG | MIN | MAX | COUNT"""
    SUM = "SUM"
    AVG = "AVG"
    MIN = "MIN"
    MAX = "MAX"
    COUNT = "COUNT"


# ═══════════════════════════════════════════════════════════════════════════
# Semantic Parser Enums
# ═══════════════════════════════════════════════════════════════════════════

class HowType(str, Enum):
    """Computation complexity classification.
    
    <rule>
    COMPLEX (needs Step2 computation) - check these keywords FIRST:
    - ranking/rank/position/leaderboard -> COMPLEX (assigns rank number to each row)
    - percent/percentage/share/proportion/contribution -> COMPLEX
    - running/cumulative/YTD/MTD -> COMPLEX
    - moving/rolling/sliding window -> COMPLEX
    - difference/change/growth/MoM/YoY -> COMPLEX
    - LOD/per customer/per product -> COMPLEX
    
    SIMPLE (direct aggregation, no Step2) - only if NO complex keywords:
    - sum/total, average, count, min, max
    - grouping by dimension
    - Top N filtering (returns top rows, NOT ranking)
    
    CRITICAL: "percentage" or "ranking" means COMPLEX, not simple aggregation!
    </rule>
    """
    SIMPLE = "SIMPLE"
    COMPLEX = "COMPLEX"


class IntentType(str, Enum):
    """Intent classification.
    
    <rule>
    DATA_QUERY: complete query with all fields specified
    CLARIFICATION: needs info, references unspecified values
    GENERAL: asks about metadata/fields/schema
    IRRELEVANT: off-topic, not about data analysis
    </rule>
    """
    DATA_QUERY = "DATA_QUERY"
    CLARIFICATION = "CLARIFICATION"
    GENERAL = "GENERAL"
    IRRELEVANT = "IRRELEVANT"


class ObserverDecision(str, Enum):
    """Observer decision.
    
    <rule>
    ACCEPT: all checks pass
    CORRECT: small fixable conflict
    RETRY: large structural conflict
    CLARIFY: cannot determine, need user input
    </rule>
    """
    ACCEPT = "ACCEPT"
    CORRECT = "CORRECT"
    RETRY = "RETRY"
    CLARIFY = "CLARIFY"


# ═══════════════════════════════════════════════════════════════════════════
# Field Mapper Enums
# ═══════════════════════════════════════════════════════════════════════════

class MappingSource(str, Enum):
    """Field mapping source: RAG_DIRECT | RAG_HIGH_CONFIDENCE | RAG_LLM_FALLBACK | CACHE_HIT | EXACT_MATCH | LLM_ONLY"""
    RAG_DIRECT = "rag_direct"
    RAG_HIGH_CONFIDENCE = "rag_high_confidence"
    RAG_LLM_FALLBACK = "rag_llm_fallback"
    CACHE_HIT = "cache_hit"
    EXACT_MATCH = "exact_match"
    LLM_ONLY = "llm_only"


class DimensionCategory(str, Enum):
    """Dimension category: TIME | GEOGRAPHY | PRODUCT | CUSTOMER | ORGANIZATION | FINANCIAL | OTHER"""
    TIME = "time"
    GEOGRAPHY = "geography"
    PRODUCT = "product"
    CUSTOMER = "customer"
    ORGANIZATION = "organization"
    FINANCIAL = "financial"
    OTHER = "other"


class DimensionLevel(str, Enum):
    """Dimension hierarchy level: TOP=coarsest | HIGH=coarse | MEDIUM=medium | LOW=fine | DETAIL=finest"""
    TOP = "top"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    DETAIL = "detail"


# ═══════════════════════════════════════════════════════════════════════════
# Backward Compatibility (Deprecated - will be removed)
# ═══════════════════════════════════════════════════════════════════════════

# CalcType is deprecated, use Literal types in computations.py instead
class CalcType(str, Enum):
    """DEPRECATED: Use specific computation classes in computations.py instead.
    
    Kept for backward compatibility during migration.
    """
    # Ranking
    RANK = "RANK"
    DENSE_RANK = "DENSE_RANK"
    PERCENTILE = "PERCENTILE"
    # Running
    RUNNING_TOTAL = "RUNNING_TOTAL"
    MOVING_CALC = "MOVING_CALC"
    # Percent
    PERCENT_OF_TOTAL = "PERCENT_OF_TOTAL"
    # Difference
    DIFFERENCE = "DIFFERENCE"
    PERCENT_DIFFERENCE = "PERCENT_DIFFERENCE"
    # LOD
    LOD_FIXED = "LOD_FIXED"
    LOD_INCLUDE = "LOD_INCLUDE"
    LOD_EXCLUDE = "LOD_EXCLUDE"


# CalcAggregation has been removed - use WindowAggregation instead
