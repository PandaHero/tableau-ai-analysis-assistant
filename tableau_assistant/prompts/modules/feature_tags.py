"""
Feature Tags for Dynamic Prompt System

FeatureTag identifies question characteristics that determine which
prompt modules should be activated.

Design Principles:
- Orthogonal: Each tag represents an independent feature
- Exhaustive: Cover all common question patterns
- Minimal: No redundant or overlapping tags
"""
from enum import Enum, auto


class FeatureTag(str, Enum):
    """Question feature identifiers.
    
    Each tag triggers specific prompt modules to be included.
    Multiple tags can be active for a single question.
    
    Categories:
    1. Entity Features - What entities are involved
    2. Operation Features - What operations are needed
    3. Time Features - Time-related patterns
    4. Analysis Features - Analysis type patterns
    """
    
    # ===== Entity Features =====
    DIMENSION = "dimension"          # Has dimension entities (省份, 产品)
    MEASURE = "measure"              # Has measure entities (销售额, 利润)
    DATE_FIELD = "date_field"        # Has date field for grouping (按月, 按年)
    
    # ===== Operation Features =====
    AGGREGATION = "aggregation"      # Needs aggregation (总, 平均, 多少)
    GROUPING = "grouping"            # Needs GROUP BY (各, 按, 每个)
    FILTERING = "filtering"          # Has filter conditions (某个, 只看)
    COUNTING = "counting"            # Count distinct (多少, 几个)
    
    # ===== Time Features =====
    TIME_ABSOLUTE = "time_absolute"  # Absolute time (2024年, Q1)
    TIME_RELATIVE = "time_relative"  # Relative time (最近3个月, 本月)
    TIME_COMPARISON = "time_comparison"  # Time comparison (同比, 环比)
    
    # ===== Analysis Features =====
    TREND = "trend"                  # Trend analysis (趋势, 变化)
    RANKING = "ranking"              # Ranking (排名, 前N, Top)
    COMPARISON = "comparison"        # Comparison (对比, vs)
    PROPORTION = "proportion"        # Proportion (占比, 比例)
    BREAKDOWN = "breakdown"          # Multi-dimensional (各X的Y)
    
    # ===== Advanced Features =====
    TABLE_CALC = "table_calc"        # Table calculations (累计, 移动平均)
    EXPLORATION = "exploration"      # Exploratory (为什么, 原因)


# Feature tag groups for convenience
ENTITY_TAGS = {FeatureTag.DIMENSION, FeatureTag.MEASURE, FeatureTag.DATE_FIELD}
OPERATION_TAGS = {FeatureTag.AGGREGATION, FeatureTag.GROUPING, FeatureTag.FILTERING, FeatureTag.COUNTING}
TIME_TAGS = {FeatureTag.TIME_ABSOLUTE, FeatureTag.TIME_RELATIVE, FeatureTag.TIME_COMPARISON}
ANALYSIS_TAGS = {FeatureTag.TREND, FeatureTag.RANKING, FeatureTag.COMPARISON, FeatureTag.PROPORTION, FeatureTag.BREAKDOWN}
ADVANCED_TAGS = {FeatureTag.TABLE_CALC, FeatureTag.EXPLORATION}


__all__ = [
    "FeatureTag",
    "ENTITY_TAGS",
    "OPERATION_TAGS",
    "TIME_TAGS",
    "ANALYSIS_TAGS",
    "ADVANCED_TAGS",
]
