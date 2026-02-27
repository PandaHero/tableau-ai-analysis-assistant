# -*- coding: utf-8 -*-
"""语义层核心枚举类型。

所有枚举都是平台无关的，表示用户意图而非平台特定概念。

组织结构：
1. 通用枚举（跨 Agent 共享）
2. 计算参数枚举（按计算类型分组）
3. 语义解析器枚举
4. 字段映射器枚举
"""

from enum import Enum

# ═══════════════════════════════════════════════════════════════════════════
# 通用枚举（跨 Agent 共享）
# ═══════════════════════════════════════════════════════════════════════════

class AggregationType(str, Enum):
    """聚合函数类型，用于度量和 LOD 表达式。"""
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
    """日期粒度：年 | 季度 | 月 | 周 | 日 | 小时 | 分钟"""
    YEAR = "YEAR"
    QUARTER = "QUARTER"
    MONTH = "MONTH"
    WEEK = "WEEK"
    DAY = "DAY"
    HOUR = "HOUR"
    MINUTE = "MINUTE"

class SortDirection(str, Enum):
    """排序方向：DESC=降序（从高到低）| ASC=升序（从低到高）"""
    ASC = "ASC"
    DESC = "DESC"

class FilterType(str, Enum):
    """筛选器类型：集合 | 日期范围 | 数值范围 | 文本匹配 | Top N"""
    SET = "SET"
    DATE_RANGE = "DATE_RANGE"
    NUMERIC_RANGE = "NUMERIC_RANGE"
    TEXT_MATCH = "TEXT_MATCH"
    TOP_N = "TOP_N"

class DateRangeType(str, Enum):
    """日期范围类型。"""
    ABSOLUTE = "ABSOLUTE"      # 绝对日期范围（指定具体日期）
    RELATIVE = "RELATIVE"      # 相对日期范围（如"最近7天"）
    YTD = "YTD"                # 年初至今
    MTD = "MTD"                # 月初至今
    QTD = "QTD"                # 季初至今
    LAST_N_DAYS = "LAST_N_DAYS"    # 最近 N 天
    LAST_N_WEEKS = "LAST_N_WEEKS"  # 最近 N 周
    LAST_N_MONTHS = "LAST_N_MONTHS"  # 最近 N 月
    LAST_N_YEARS = "LAST_N_YEARS"    # 最近 N 年

class TextMatchType(str, Enum):
    """文本匹配类型：包含 | 开头 | 结尾 | 精确 | 正则"""
    CONTAINS = "CONTAINS"
    STARTS_WITH = "STARTS_WITH"
    ENDS_WITH = "ENDS_WITH"
    EXACT = "EXACT"
    REGEX = "REGEX"

# ═══════════════════════════════════════════════════════════════════════════
# 计算参数枚举（按计算类型分组）
# ═══════════════════════════════════════════════════════════════════════════

class RankStyle(str, Enum):
    """排名样式：COMPETITION=1,2,2,4 | DENSE=1,2,2,3 | UNIQUE=1,2,3,4"""
    COMPETITION = "COMPETITION"
    DENSE = "DENSE"
    UNIQUE = "UNIQUE"

class RelativeTo(str, Enum):
    """差异参考点：上一个 | 下一个 | 第一个 | 最后一个"""
    PREVIOUS = "PREVIOUS"
    NEXT = "NEXT"
    FIRST = "FIRST"
    LAST = "LAST"

# 注意：WindowAggregation 已移除，直接使用 AggregationType
# 窗口函数支持的聚合类型是 AggregationType 的子集

# ═══════════════════════════════════════════════════════════════════════════
# 语义解析器枚举
# ═══════════════════════════════════════════════════════════════════════════

class HowType(str, Enum):
    """计算复杂度：SIMPLE=简单聚合 | COMPLEX=派生计算"""
    SIMPLE = "SIMPLE"
    COMPLEX = "COMPLEX"

class IntentType(str, Enum):
    """意图分类：数据查询 | 澄清 | 通用问题 | 无关"""
    DATA_QUERY = "data_query"
    CLARIFICATION = "clarification"
    GENERAL = "general"
    IRRELEVANT = "irrelevant"

class ObserverDecision(str, Enum):
    """Observer 决策：接受 | 修正 | 重试 | 澄清"""
    ACCEPT = "ACCEPT"
    CORRECT = "CORRECT"
    RETRY = "RETRY"
    CLARIFY = "CLARIFY"

# ═══════════════════════════════════════════════════════════════════════════
# 字段映射器枚举
# ═══════════════════════════════════════════════════════════════════════════

class MappingSource(str, Enum):
    """字段映射来源。"""
    RAG_DIRECT = "rag_direct"
    RAG_HIGH_CONFIDENCE = "rag_high_confidence"
    RAG_LLM_FALLBACK = "rag_llm_fallback"
    CACHE_HIT = "cache_hit"
    EXACT_MATCH = "exact_match"
    LLM_ONLY = "llm_only"

class DimensionCategory(str, Enum):
    """维度类别：时间 | 地理 | 产品 | 客户 | 组织 | 财务 | 渠道 | 其他"""
    TIME = "time"
    GEOGRAPHY = "geography"
    PRODUCT = "product"
    CUSTOMER = "customer"
    ORGANIZATION = "organization"
    FINANCIAL = "financial"
    CHANNEL = "channel"
    OTHER = "other"

class DimensionLevel(str, Enum):
    """维度层级：顶层 | 高层 | 中层 | 低层 | 明细"""
    TOP = "top"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    DETAIL = "detail"

# ═══════════════════════════════════════════════════════════════════════════
# 字段语义枚举
# ═══════════════════════════════════════════════════════════════════════════

class MeasureCategory(str, Enum):
    """度量类别枚举
    
    用于分类度量字段的业务含义：
    - REVENUE: 收入类（销售额、营业收入、GMV）
    - COST: 成本类（成本、费用、支出）
    - PROFIT: 利润类（利润、毛利、净利）
    - QUANTITY: 数量类（数量、件数、订单数）
    - RATIO: 比率类（占比、增长率、转化率）
    - COUNT: 计数类（人数、次数、频次）
    - AVERAGE: 平均类（均价、平均值）
    - OTHER: 其他
    """
    REVENUE = "revenue"
    COST = "cost"
    PROFIT = "profit"
    QUANTITY = "quantity"
    RATIO = "ratio"
    COUNT = "count"
    AVERAGE = "average"
    OTHER = "other"
