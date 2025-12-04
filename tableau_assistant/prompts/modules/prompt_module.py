"""
Prompt Module and Schema Module Definitions

PromptModule: Independent knowledge/rule unit with feature tags
SchemaModule: Related field definitions for dynamic schema

Design Principles:
- Self-contained: Each module is complete and independent
- Tagged: Activated by specific feature tags
- Composable: Multiple modules can be combined
"""
from dataclasses import dataclass, field
from typing import Set, List, Optional, Dict, Any
from .feature_tags import FeatureTag


@dataclass
class PromptModule:
    """Independent prompt knowledge/rule unit.
    
    Each module contains domain knowledge for a specific feature.
    Modules are activated when their tags match detected features.
    
    Attributes:
        name: Unique module identifier
        tags: Feature tags that activate this module
        knowledge: Domain knowledge content (markdown format)
        priority: Loading priority (lower = earlier, default 100)
        required: Always include regardless of features
    """
    name: str
    tags: Set[FeatureTag]
    knowledge: str
    priority: int = 100
    required: bool = False
    
    def matches(self, detected_tags: Set[FeatureTag]) -> bool:
        """Check if module should be activated for detected features."""
        if self.required:
            return True
        return bool(self.tags & detected_tags)


@dataclass
class SchemaModule:
    """Dynamic schema field definitions.
    
    Each module defines schema fields relevant to specific features.
    Used to build dynamic output schema based on question features.
    
    Attributes:
        name: Unique module identifier
        tags: Feature tags that activate this module
        fields: Field definitions (name -> schema dict)
        required: Always include regardless of features
    """
    name: str
    tags: Set[FeatureTag]
    fields: Dict[str, Dict[str, Any]]
    required: bool = False
    
    def matches(self, detected_tags: Set[FeatureTag]) -> bool:
        """Check if module should be activated for detected features."""
        if self.required:
            return True
        return bool(self.tags & detected_tags)


# ===== Pre-defined Prompt Modules =====

# Base module - always included
BASE_MODULE = PromptModule(
    name="base",
    tags=set(),
    required=True,
    priority=0,
    knowledge="""
┌─────────────┬──────────────┬─────────────────────────────────────────────────┐
│ Field       │ Values       │ Description                                     │
├─────────────┼──────────────┼─────────────────────────────────────────────────┤
│ type        │ dimension    │ Categorical field (省份/产品/品类)              │
│             │ measure      │ Numeric field (销售额/利润/数量)                │
├─────────────┼──────────────┼─────────────────────────────────────────────────┤
│ role        │ group_by     │ For GROUP BY clause                             │
│             │ aggregate    │ For aggregation (SUM/AVG/COUNTD)                │
│             │ filter       │ For WHERE clause                                │
└─────────────┴──────────────┴─────────────────────────────────────────────────┘

Validation: is_valid=false requires invalid_reason, no duplicate entity names"""
)

# Dimension module
DIMENSION_MODULE = PromptModule(
    name="dimension",
    tags={FeatureTag.DIMENSION, FeatureTag.GROUPING},
    priority=10,
    knowledge="""
┌─────────────────────────┬────────────┬──────────────────────────────────────┐
│ Chinese Trigger         │ Role       │ Output Example                       │
├─────────────────────────┼────────────┼──────────────────────────────────────┤
│ 各X / 按X / 每个X       │ group_by   │ {name:"省份", type:"dimension",      │
│                         │            │  role:"group_by"}                    │
├─────────────────────────┼────────────┼──────────────────────────────────────┤
│ 某个X / 只看X / X=Y     │ filter     │ {name:"地区", type:"dimension",      │
│                         │            │  role:"filter"}                      │
└─────────────────────────┴────────────┴──────────────────────────────────────┘"""
)

# Measure module
MEASURE_MODULE = PromptModule(
    name="measure",
    tags={FeatureTag.MEASURE, FeatureTag.AGGREGATION},
    priority=10,
    knowledge="""
┌─────────────────────────┬─────────────┬─────────────────────────────────────┐
│ Chinese Trigger         │ Aggregation │ Output Example                      │
├─────────────────────────┼─────────────┼─────────────────────────────────────┤
│ 总X / 合计X / 汇总X     │ SUM         │ {aggregation:"SUM"}                 │
│ 平均X / 均值X           │ AVG         │ {aggregation:"AVG"}                 │
│ 最高X / 最大X           │ MAX         │ {aggregation:"MAX"}                 │
│ 最低X / 最小X           │ MIN         │ {aggregation:"MIN"}                 │
└─────────────────────────┴─────────────┴─────────────────────────────────────┘

Rule: Measures require aggregation when role=aggregate"""
)

# Counting module
COUNTING_MODULE = PromptModule(
    name="counting",
    tags={FeatureTag.COUNTING},
    priority=20,
    knowledge="""
┌─────────────────────────┬─────────────┬─────────────────────────────────────┐
│ Chinese Trigger         │ Aggregation │ Output Example                      │
├─────────────────────────┼─────────────┼─────────────────────────────────────┤
│ 多少X / 几个X / X数量   │ COUNTD      │ {type:"dimension", role:"aggregate",│
│                         │             │  aggregation:"COUNTD"}              │
└─────────────────────────┴─────────────┴─────────────────────────────────────┘

Rule: COUNTD is for dimensions only, not measures"""
)

# Date field module
DATE_FIELD_MODULE = PromptModule(
    name="date_field",
    tags={FeatureTag.DATE_FIELD},
    priority=15,
    knowledge="""
┌─────────────────────────┬───────────────┬───────────────────────────────────┐
│ Chinese Trigger         │ date_function │ Output Example                    │
├─────────────────────────┼───────────────┼───────────────────────────────────┤
│ 按年 / 各年度 / 年度    │ YEAR          │ {type:"dimension",                │
│ 按季度 / 各季度         │ QUARTER       │  role:"group_by",                 │
│ 按月 / 各月 / 月度      │ MONTH         │  date_function:"MONTH"}           │
│ 按周 / 每周             │ WEEK          │                                   │
│ 按天 / 每日 / 日度      │ DAY           │                                   │
└─────────────────────────┴───────────────┴───────────────────────────────────┘

Rule: Date = dimension + date_function (not a separate type)"""
)

# Time absolute module
TIME_ABSOLUTE_MODULE = PromptModule(
    name="time_absolute",
    tags={FeatureTag.TIME_ABSOLUTE},
    priority=30,
    knowledge="""
┌─────────────────────────┬─────────────────┬──────────────────────────────────┐
│ Chinese Trigger         │ time_range.type │ time_range.value                 │
├─────────────────────────┼─────────────────┼──────────────────────────────────┤
│ 2024年 / 某年           │ absolute        │ "2024"                           │
│ Q1 / 第一季度           │ absolute        │ "2024-Q1"                        │
│ 3月 / 三月              │ absolute        │ "2024-03"                        │
│ 3月15日                 │ absolute        │ "2024-03-15"                     │
└─────────────────────────┴─────────────────┴──────────────────────────────────┘

Rule: Fill missing year/month from max_date"""
)

# Time relative module
TIME_RELATIVE_MODULE = PromptModule(
    name="time_relative",
    tags={FeatureTag.TIME_RELATIVE},
    priority=30,
    knowledge="""
┌─────────────────────────┬───────────────┬─────────────┬─────────────────────┐
│ Chinese Trigger         │ relative_type │ period_type │ range_n             │
├─────────────────────────┼───────────────┼─────────────┼─────────────────────┤
│ 本月 / 当月             │ CURRENT       │ MONTHS      │ null                │
│ 今年 / 本年             │ CURRENT       │ YEARS       │ null                │
│ 上个月                  │ LAST          │ MONTHS      │ null                │
│ 去年                    │ LAST          │ YEARS       │ null                │
│ 最近3个月               │ LASTN         │ MONTHS      │ 3                   │
│ 年初至今                │ TODATE        │ YEARS       │ null                │
└─────────────────────────┴───────────────┴─────────────┴─────────────────────┘"""
)

# Time comparison module
TIME_COMPARISON_MODULE = PromptModule(
    name="time_comparison",
    tags={FeatureTag.TIME_COMPARISON},
    priority=30,
    knowledge="""
┌─────────────────────────┬─────────────────┬──────────────────────────────────┐
│ Chinese Trigger         │ time_range.type │ question_types                   │
├─────────────────────────┼─────────────────┼──────────────────────────────────┤
│ 同比 / 与去年比         │ comparison      │ ["同环比"]                       │
│ 环比 / 与上月比         │ comparison      │ ["同环比"]                       │
└─────────────────────────┴─────────────────┴──────────────────────────────────┘"""
)

# Trend module
TREND_MODULE = PromptModule(
    name="trend",
    tags={FeatureTag.TREND},
    priority=40,
    knowledge="""
┌─────────────────────────┬──────────────────────────────────────────────────────┐
│ Chinese Trigger         │ Requirements                                         │
├─────────────────────────┼──────────────────────────────────────────────────────┤
│ 趋势 / 变化 / 走势      │ • Must have date entity with date_function          │
│                         │ • question_types includes "趋势"                     │
└─────────────────────────┴──────────────────────────────────────────────────────┘

Example: "销售额按月趋势" → date entity with date_function=MONTH"""
)

# Ranking module
RANKING_MODULE = PromptModule(
    name="ranking",
    tags={FeatureTag.RANKING},
    priority=40,
    knowledge="""
┌─────────────────────────┬──────────────────────────────────────────────────────┐
│ Chinese Trigger         │ Requirements                                         │
├─────────────────────────┼──────────────────────────────────────────────────────┤
│ 排名 / 前N / Top        │ • question_types includes "排名"                     │
│ 最高的N个 / 最低的N个   │ • Usually involves sorting by measure                │
└─────────────────────────┴──────────────────────────────────────────────────────┘

Example: "销售额前10的产品" → question_types=["排名"]"""
)

# Comparison module
COMPARISON_MODULE = PromptModule(
    name="comparison",
    tags={FeatureTag.COMPARISON},
    priority=40,
    knowledge="""
┌─────────────────────────┬──────────────────────────────────────────────────────┐
│ Chinese Trigger         │ Requirements                                         │
├─────────────────────────┼──────────────────────────────────────────────────────┤
│ 对比 / vs / 比较        │ • question_types includes "对比"                     │
│ A和B / A与B             │ • Usually compares across dimension values           │
└─────────────────────────┴──────────────────────────────────────────────────────┘

Example: "华东和华南销售额对比" → question_types=["对比"]"""
)

# Proportion module
PROPORTION_MODULE = PromptModule(
    name="proportion",
    tags={FeatureTag.PROPORTION},
    priority=40,
    knowledge="""
┌─────────────────────────┬──────────────────────────────────────────────────────┐
│ Chinese Trigger         │ Requirements                                         │
├─────────────────────────┼──────────────────────────────────────────────────────┤
│ 占比 / 比例 / 百分比    │ • question_types includes "占比"                     │
│ 份额                    │ • May require table calculation for percentage       │
└─────────────────────────┴──────────────────────────────────────────────────────┘

Example: "各品类销售额占比" → question_types=["占比"]"""
)

# Table calculation module
TABLE_CALC_MODULE = PromptModule(
    name="table_calc",
    tags={FeatureTag.TABLE_CALC},
    priority=50,
    knowledge="""
┌─────────────────────────┬──────────────────────────────────────────────────────┐
│ Chinese Trigger         │ Table Calc Type                                      │
├─────────────────────────┼──────────────────────────────────────────────────────┤
│ 累计 / 累计销售额       │ RUNNING_TOTAL                                        │
│ 移动平均 / 滚动平均     │ MOVING_CALCULATION                                   │
│ 排名计算                │ RANK                                                 │
│ 占总百分比              │ PERCENT_OF_TOTAL                                     │
└─────────────────────────┴──────────────────────────────────────────────────────┘

Note: Table calculations operate on query results, not raw data"""
)

# Exploration module
EXPLORATION_MODULE = PromptModule(
    name="exploration",
    tags={FeatureTag.EXPLORATION},
    priority=50,
    knowledge="""
┌─────────────────────────┬──────────────────────────────────────────────────────┐
│ Chinese Trigger         │ Requirements                                         │
├─────────────────────────┼──────────────────────────────────────────────────────┤
│ 为什么 / 原因           │ • needs_exploration = true                           │
│ 分析原因 / 怎么回事     │ • May require multiple queries and drill-down        │
└─────────────────────────┴──────────────────────────────────────────────────────┘

Example: "为什么销售下降" → needs_exploration=true"""
)


# All pre-defined modules
ALL_MODULES: List[PromptModule] = [
    BASE_MODULE,
    DIMENSION_MODULE,
    MEASURE_MODULE,
    COUNTING_MODULE,
    DATE_FIELD_MODULE,
    TIME_ABSOLUTE_MODULE,
    TIME_RELATIVE_MODULE,
    TIME_COMPARISON_MODULE,
    TREND_MODULE,
    RANKING_MODULE,
    COMPARISON_MODULE,
    PROPORTION_MODULE,
    TABLE_CALC_MODULE,
    EXPLORATION_MODULE,
]


__all__ = [
    "PromptModule",
    "SchemaModule",
    "ALL_MODULES",
    "BASE_MODULE",
    "DIMENSION_MODULE",
    "MEASURE_MODULE",
    "COUNTING_MODULE",
    "DATE_FIELD_MODULE",
    "TIME_ABSOLUTE_MODULE",
    "TIME_RELATIVE_MODULE",
    "TIME_COMPARISON_MODULE",
    "TREND_MODULE",
    "RANKING_MODULE",
    "COMPARISON_MODULE",
    "PROPORTION_MODULE",
    "TABLE_CALC_MODULE",
    "EXPLORATION_MODULE",
]
