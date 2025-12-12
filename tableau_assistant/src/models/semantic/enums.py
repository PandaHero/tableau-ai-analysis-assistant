"""
Semantic layer enums

Pure semantic concepts, no VizQL-specific types.
"""
from enum import Enum


class AnalysisType(str, Enum):
    """
    Analysis type enum
    
    Defines the type of analysis to perform on measures.
    These are semantic concepts that will be translated to
    VizQL table calculations or LOD expressions by QueryBuilder.
    
    Phase 1 (Core):
    - cumulative: Running total/sum
    - moving: Moving average/sum
    - ranking: Rank values
    - percentage: Percentage of total
    - period_compare: Period over period comparison
    
    Phase 2 (Extended):
    - difference: Absolute difference from reference
    - percent_difference: Percentage difference from reference
    - ranking_dense: Dense ranking (no gaps)
    - ranking_percentile: Percentile ranking
    
    Phase 3 (Advanced):
    - position: Position-based calculations
    """
    # Phase 1
    CUMULATIVE = "cumulative"
    MOVING = "moving"
    RANKING = "ranking"
    PERCENTAGE = "percentage"
    PERIOD_COMPARE = "period_compare"
    
    # Phase 2
    DIFFERENCE = "difference"
    PERCENT_DIFFERENCE = "percent_difference"
    RANKING_DENSE = "ranking_dense"
    RANKING_PERCENTILE = "ranking_percentile"
    
    # Phase 3
    POSITION = "position"


class ComputationScope(str, Enum):
    """
    Computation scope enum
    
    Defines how the analysis should be scoped across dimensions.
    
    - per_group: Calculate within each group (partition by other dimensions)
    - across_all: Calculate across all data (no partitioning)
    
    Example:
    - "累计销售额按省份" → per_group (each province has its own running total)
    - "全国累计销售额" → across_all (single running total across all data)
    
    Note: Only applicable when dimensions.length > 1
    When dimensions.length <= 1, this should be null.
    """
    PER_GROUP = "per_group"
    ACROSS_ALL = "across_all"


class MappingSource(str, Enum):
    """
    Field mapping source enum
    
    Indicates how a field mapping was determined.
    
    - rag_direct: RAG retrieval direct match (high confidence, no LLM needed)
    - rag_high_confidence: RAG retrieval with confidence >= 0.9 (fast path)
    - rag_llm_fallback: RAG retrieval with LLM selection (confidence < 0.9)
    - cache_hit: Retrieved from cache
    - exact_match: Exact string match
    - llm_only: LLM direct matching (when RAG is not available)
    """
    RAG_DIRECT = "rag_direct"
    RAG_HIGH_CONFIDENCE = "rag_high_confidence"
    RAG_LLM_FALLBACK = "rag_llm_fallback"
    CACHE_HIT = "cache_hit"
    EXACT_MATCH = "exact_match"
    LLM_ONLY = "llm_only"


class TimeGranularity(str, Enum):
    """
    Time granularity enum
    
    Defines the granularity for time-based dimensions.
    """
    YEAR = "year"
    QUARTER = "quarter"
    MONTH = "month"
    WEEK = "week"
    DAY = "day"
    HOUR = "hour"
    MINUTE = "minute"


class AggregationType(str, Enum):
    """
    Aggregation type enum
    
    Defines how measures should be aggregated.
    """
    SUM = "sum"
    AVG = "avg"
    COUNT = "count"
    COUNTD = "countd"
    MIN = "min"
    MAX = "max"
    MEDIAN = "median"
    STDEV = "stdev"
    VAR = "var"


class FilterType(str, Enum):
    """
    Filter type enum (按规范文档定义)
    
    筛选类型枚举，决定筛选条件的结构。
    
    <decision_rule>
    - 时间条件 ("2024年", "最近3个月") → TIME_RANGE
    - 枚举值 ("华东地区", "产品A") → SET
    - 数值范围 (">1000", "100-500") → QUANTITATIVE
    - 模糊匹配 ("包含XX") → MATCH
    </decision_rule>
    """
    TIME_RANGE = "time_range"      # 时间范围筛选
    SET = "set"                    # 枚举值筛选
    QUANTITATIVE = "quantitative"  # 数值范围筛选
    MATCH = "match"                # 模糊匹配筛选


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


# ═══════════════════════════════════════════════════════════════════════════
# 日期枚举（与 VizQL API 对齐）
# ═══════════════════════════════════════════════════════════════════════════

class TimeFilterMode(str, Enum):
    """
    时间筛选模式（与 VizQL filterType 对齐）
    
    <mapping_to_vizql>
    - ABSOLUTE_RANGE → filterType: "QUANTITATIVE_DATE"
    - RELATIVE → filterType: "DATE" (RelativeDateFilter)
    - SET → filterType: "SET"
    </mapping_to_vizql>
    
    <decision_rule>
    - 具体日期/日期范围 ("2024年", "1月到5月") → ABSOLUTE_RANGE
    - 相对表达 ("最近3个月", "本月", "年初至今") → RELATIVE
    - 多个离散日期点 ("1月和2月", "Q1和Q3") → SET
    </decision_rule>
    """
    ABSOLUTE_RANGE = "absolute_range"  # 绝对日期范围（单点或范围）
    RELATIVE = "relative"              # 相对日期（最近N天/月/年）
    SET = "set"                        # 多个离散日期点


class PeriodType(str, Enum):
    """
    时间周期类型（与 VizQL PeriodType 完全对齐）
    
    <vizql_mapping>
    直接映射到 VizQL API 的 PeriodType enum
    </vizql_mapping>
    
    <decision_rule>
    - "分钟" → MINUTES
    - "小时" → HOURS
    - "天/日" → DAYS
    - "周" → WEEKS
    - "月" → MONTHS
    - "季度" → QUARTERS
    - "年" → YEARS
    </decision_rule>
    """
    MINUTES = "MINUTES"
    HOURS = "HOURS"
    DAYS = "DAYS"
    WEEKS = "WEEKS"
    MONTHS = "MONTHS"
    QUARTERS = "QUARTERS"
    YEARS = "YEARS"


class DateRangeType(str, Enum):
    """
    相对日期范围类型（与 VizQL dateRangeType 完全对齐）
    
    <vizql_mapping>
    直接映射到 VizQL API 的 RelativeDateFilter.dateRangeType
    </vizql_mapping>
    
    <decision_rule>
    - "本月" / "今年" / "本周" → CURRENT
    - "上个月" / "去年" / "上周" → LAST
    - "最近3个月" / "最近7天" → LASTN
    - "下个月" / "明年" → NEXT
    - "未来3个月" → NEXTN
    - "年初至今" / "月初至今" → TODATE
    </decision_rule>
    """
    CURRENT = "CURRENT"    # 当前周期（本月、今年）
    LAST = "LAST"          # 上一个周期（上个月、去年）
    LASTN = "LASTN"        # 最近N个周期（最近3个月）
    NEXT = "NEXT"          # 下一个周期
    NEXTN = "NEXTN"        # 未来N个周期
    TODATE = "TODATE"      # 至今（年初至今、月初至今）
