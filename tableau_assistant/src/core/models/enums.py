"""Core enumerations for the semantic layer.

All enums are platform-agnostic and represent user intent, not platform-specific concepts.
"""

from enum import Enum


# ═══════════════════════════════════════════════════════════════════════════
# Common Enums (Cross-Agent Shared)
# ═══════════════════════════════════════════════════════════════════════════

class AggregationType(str, Enum):
    """Aggregation type for basic statistical functions.
    
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
    """Date granularity.
    
    <rule>
    year/annual -> YEAR
    quarter/quarterly -> QUARTER
    month/monthly -> MONTH
    week/weekly -> WEEK
    day/daily -> DAY
    hour/hourly -> HOUR
    minute -> MINUTE
    </rule>
    """
    YEAR = "YEAR"
    QUARTER = "QUARTER"
    MONTH = "MONTH"
    WEEK = "WEEK"
    DAY = "DAY"
    HOUR = "HOUR"
    MINUTE = "MINUTE"


class SortDirection(str, Enum):
    """Sort direction.
    
    <rule>
    ascending/low to high/bottom N -> ASC
    descending/high to low/top N -> DESC
    </rule>
    """
    ASC = "ASC"
    DESC = "DESC"


class FilterType(str, Enum):
    """Filter type.
    
    <rule>
    categorical values -> SET
    time/date constraints -> DATE_RANGE
    number range -> NUMERIC_RANGE
    pattern match -> TEXT_MATCH
    top/bottom N -> TOP_N
    </rule>
    """
    SET = "SET"
    DATE_RANGE = "DATE_RANGE"
    NUMERIC_RANGE = "NUMERIC_RANGE"
    TEXT_MATCH = "TEXT_MATCH"
    TOP_N = "TOP_N"


class DateRangeType(str, Enum):
    """Date range type.
    
    Simplified to only CUSTOM - LLM calculates concrete start_date/end_date
    based on user intent and current_time.
    
    <rule>
    All date filtering uses concrete start_date and end_date values.
    LLM interprets user intent (this year, last month, 2024, etc.)
    and calculates the actual date range.
    </rule>
    """
    CUSTOM = "CUSTOM"


class TextMatchType(str, Enum):
    """Text match type.
    
    <rule>
    contains/includes -> CONTAINS
    starts with/begins with -> STARTS_WITH
    ends with -> ENDS_WITH
    exact/equals -> EXACT
    regex/pattern -> REGEX
    </rule>
    """
    CONTAINS = "CONTAINS"
    STARTS_WITH = "STARTS_WITH"
    ENDS_WITH = "ENDS_WITH"
    EXACT = "EXACT"
    REGEX = "REGEX"


# ═══════════════════════════════════════════════════════════════════════════
# Semantic Parser Enums
# ═══════════════════════════════════════════════════════════════════════════

class HowType(str, Enum):
    """Computation complexity: SIMPLE=no Step2 | COMPLEX=needs Step2
    
    <rule>
    SIMPLE - Direct aggregation, no computation needed:
    - Basic aggregation: total sales, average price, count of orders
    - Simple grouping: sales by region, orders by month
    - Top N / Bottom N filtering: "top 5 cities by sales", "bottom 10 products"
      (returns filtered subset, NOT a rank column)
    
    COMPLEX - Needs Step 2 for computation:
    - Ranking: "rank all provinces", "percentile ranking" (adds rank column to ALL rows)
    - Running: "YTD", "cumulative total", "running sum"
    - Comparison: "MoM growth", "YoY change", "difference from previous"
    - Moving: "3-month moving average", "rolling sum"
    - Percent: "percent of total", "share of category"
    - LOD: "per customer X", "first purchase date", "lifetime value"
    
    Key distinction - Top N filtering vs Rank calculation:
    - Top N filtering (SIMPLE): "top 5 cities" returns 5 rows (filtered subset)
    - Rank calculation (COMPLEX): "rank all cities" returns ALL rows with rank column added
    </rule>
    
    <anti_patterns>
    X "Top 5 cities by sales" classified as COMPLEX (should be SIMPLE - filtering)
    X "Rank all provinces" classified as SIMPLE (should be COMPLEX - adds rank column)
    X "Cumulative sales" classified as SIMPLE (should be COMPLEX - needs RUNNING_TOTAL)
    X "Percent of total" classified as SIMPLE (should be COMPLEX - needs PERCENT_OF_TOTAL)
    </anti_patterns>
    """
    SIMPLE = "SIMPLE"
    COMPLEX = "COMPLEX"


class CalcType(str, Enum):
    """Calculation type (Step2 output, platform-agnostic).
    
    <rule>
    Table Calculations:
    - ranking/Top N -> RANK, DENSE_RANK, PERCENTILE
    - running total/YTD -> RUNNING_TOTAL
    - moving average -> MOVING_CALC
    - percent of total -> PERCENT_OF_TOTAL
    - difference/change -> DIFFERENCE
    - growth rate/MoM -> PERCENT_DIFFERENCE
    
    LOD (change aggregation granularity):
    - per customer X/per product Y -> LOD_FIXED
    - add dimension -> LOD_INCLUDE
    - remove dimension -> LOD_EXCLUDE
    </rule>
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


class RankStyle(str, Enum):
    """Ranking style: COMPETITION=1,2,2,4 | DENSE=1,2,2,3 | UNIQUE=1,2,3,4"""
    COMPETITION = "COMPETITION"
    DENSE = "DENSE"
    UNIQUE = "UNIQUE"


class RelativeTo(str, Enum):
    """Difference reference: PREVIOUS=MoM | FIRST=vs start | LAST=vs end"""
    PREVIOUS = "PREVIOUS"
    NEXT = "NEXT"
    FIRST = "FIRST"
    LAST = "LAST"


class CalcAggregation(str, Enum):
    """Running/moving aggregation: SUM | AVG | MIN | MAX"""
    SUM = "SUM"
    AVG = "AVG"
    MIN = "MIN"
    MAX = "MAX"


class IntentType(str, Enum):
    """Intent type.
    
    <rule>
    complete query info -> DATA_QUERY
    needs clarification/unspecified values -> CLARIFICATION
    metadata/field question -> GENERAL
    off-topic/unrelated -> IRRELEVANT
    </rule>
    """
    DATA_QUERY = "DATA_QUERY"
    CLARIFICATION = "CLARIFICATION"
    GENERAL = "GENERAL"
    IRRELEVANT = "IRRELEVANT"


class ObserverDecision(str, Enum):
    """Observer decision.
    
    <rule>
    all checks pass -> ACCEPT
    small fixable conflict -> CORRECT
    large structural conflict -> RETRY
    cannot determine, need user -> CLARIFY
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
    """Dimension category.
    
    <rule>
    - geography: location (province, city, district)
    - time: temporal (year, month, day, quarter)
    - product: product (product, category, brand)
    - customer: customer (customer, customer type)
    - organization: org structure (department, team)
    - financial: financial (account, cost center)
    - other: other
    </rule>
    """
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
