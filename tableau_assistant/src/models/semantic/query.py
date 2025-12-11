"""
Semantic Query Models (按规范文档重构)

纯语义层模型 - 不包含 VizQL 技术概念。
这些模型表达用户的业务意图。

架构:
- Understanding Agent 输出 SemanticQuery (纯语义)
- FieldMapper Node 转换为 MappedQuery (技术字段映射)
- QueryBuilder Node 转换为 VizQLQuery (技术查询)

设计规范：遵循 `prompt-and-schema-design.md` 中定义的设计规范
核心理念：
- 思考与填写交织：LLM 是逐 token 生成的，每填一个字段都是一次"微型思考"
- XML 标签定位：为每次微型思考提供精确的规则定位锚点
- `<decision_rule>` 桥梁：将 Prompt 中的抽象思考转化为具体填写动作
"""
from pydantic import BaseModel, Field, ConfigDict, model_validator
from typing import List, Dict, Any, Optional, Literal, TYPE_CHECKING
from .enums import (
    AnalysisType,
    ComputationScope,
    MappingSource,
    TimeGranularity,
    AggregationType,
    FilterType,
    DimensionCategory,
    DimensionLevel,
    # 日期枚举（与 VizQL API 对齐）
    TimeFilterMode,
    PeriodType,
    DateRangeType,
)


# ═══════════════════════════════════════════════════════════════════════════
# SemanticQuery 组件
# ═══════════════════════════════════════════════════════════════════════════

class MeasureSpec(BaseModel):
    """
    度量规格
    
    <what>单个度量字段的规格，表示需要聚合计算的数值字段</what>
    """
    model_config = ConfigDict(extra="forbid")
    
    name: str = Field(
        min_length=1,
        description="""度量名称

<what>业务术语，不是技术字段名</what>
<when>ALWAYS required</when>
<how>Use exact term from user question</how>

<decision_rule>
Prompt Step 2 (提取业务实体) → 填写 name
- 使用问题中的原始术语
- 不使用技术字段名（如 Sales、Profit）
</decision_rule>

<examples>
- "各省份的销售额" → "销售额" (not "Sales")
- "平均利润" → "利润" (not "Profit")
</examples>

<anti_patterns>
❌ Using technical field names: "Sales" instead of "销售额"
</anti_patterns>"""
    )
    
    aggregation: Literal["sum", "avg", "count", "countd", "min", "max"] = Field(
        default="sum",
        description="""聚合方式

<what>SQL 聚合函数</what>
<when>ALWAYS (default: sum)</when>
<how>Detect from keywords in question</how>

<decision_rule>
Prompt Step 3 (分类实体角色) → 填写 aggregation
- "总" / "合计" / default → sum
- "平均" → avg
- "多少个" / "几种" → countd
- "最大" → max
- "最小" → min
</decision_rule>

<values>
- sum: 求和（默认）
- avg: 平均
- count: 计数
- countd: 去重计数
- min: 最小值
- max: 最大值
</values>

<examples>
- "各省份的销售额" → sum (default)
- "平均利润" → avg
- "有多少产品" → countd
</examples>"""
    )
    
    alias: Optional[str] = Field(
        default=None,
        description="可选的显示别名"
    )


class DimensionSpec(BaseModel):
    """
    维度规格
    
    <what>单个维度字段的规格，表示用于分组的分类字段</what>
    """
    model_config = ConfigDict(extra="forbid")
    
    name: str = Field(
        min_length=1,
        description="""维度名称

<what>业务术语，不是技术字段名</what>
<when>ALWAYS required</when>
<how>Use exact term from user question</how>

<decision_rule>
Prompt Step 2 (提取业务实体) → 填写 name
- 使用问题中的原始术语
- 不使用技术字段名
</decision_rule>

<examples>
- "各省份" → "省份"
- "按产品类别" → "产品类别"
</examples>"""
    )
    
    is_time: bool = Field(
        default=False,
        description="""是否是时间维度

<what>标识该维度是否为时间类型</what>
<when>ALWAYS required</when>
<how>Detect time-related terms</how>

<decision_rule>
Prompt Step 3 (分类实体角色) → 填写 is_time
- "日期" / "时间" / "年" / "月" / "日" / "周" / "季度" → true
- Other dimensions → false
</decision_rule>

<examples>
- "按月" → true
- "各省份" → false
</examples>"""
    )
    
    time_granularity: Optional[Literal["year", "quarter", "month", "week", "day"]] = Field(
        default=None,
        description="""时间粒度

<what>时间维度的聚合粒度</what>

<when>ONLY when is_time = true</when>

<dependency>
- field: is_time
- condition: is_time == true
- reason: 非时间维度不需要指定粒度
</dependency>

<decision_rule>
IF is_time == false THEN null (不填写！)
IF is_time == true:
  - "按年" / "年度" → year
  - "按季度" / "季度" → quarter
  - "按月" / "月度" → month
  - "按周" / "周" → week
  - "按日" / "按天" / "每天" → day
</decision_rule>

<values>
- year: 年
- quarter: 季度
- month: 月
- week: 周
- day: 日
</values>

<examples>
- "按月销售额" → month
- "各省份" (is_time=false) → null
</examples>

<anti_patterns>
❌ Setting time_granularity when is_time = false
</anti_patterns>"""
    )
    
    alias: Optional[str] = Field(
        default=None,
        description="可选的显示别名"
    )
    
    @model_validator(mode='after')
    def validate_time_granularity(self) -> 'DimensionSpec':
        """验证时间粒度与 is_time 的一致性"""
        if not self.is_time and self.time_granularity is not None:
            # 自动修正：非时间维度不应有时间粒度
            self.time_granularity = None
        return self


class TimeFilterSpec(BaseModel):
    """
    时间筛选规格（新版，与 VizQL API 对齐）
    
    <what>时间筛选的结构化表示，直接映射到 VizQL 日期筛选类型</what>
    
    <design_principles>
    1. 与 VizQL API 的三种日期筛选类型直接对应
    2. LLM 输出 RFC 3339 格式日期（YYYY-MM-DD），无需 DateParser 再计算
    3. 相对日期由 DateParser 计算，绝对日期直接透传
    4. 所有多值字段使用 Enum 类型
    </design_principles>
    
    <vizql_mapping>
    - mode=ABSOLUTE_RANGE → filterType: "QUANTITATIVE_DATE"
    - mode=RELATIVE → filterType: "DATE" (RelativeDateFilter)
    - mode=SET → filterType: "SET"
    </vizql_mapping>
    
    <examples>
    # 场景1: 单点绝对 - "2024年"
    {"mode": "absolute_range", "start_date": "2024-01-01", "end_date": "2024-12-31"}
    
    # 场景2: 绝对范围 - "2024年1月到5月"
    {"mode": "absolute_range", "start_date": "2024-01-01", "end_date": "2024-05-31"}
    
    # 场景3: 相对范围 - "最近3个月"
    {"mode": "relative", "period_type": "MONTHS", "date_range_type": "LASTN", "range_n": 3}
    
    # 场景4: 相对范围 - "年初至今"
    {"mode": "relative", "period_type": "YEARS", "date_range_type": "TODATE"}
    
    # 场景5: 多离散点 - "2024年1月和2月"
    {"mode": "set", "date_values": ["2024-01", "2024-02"]}
    </examples>
    """
    model_config = ConfigDict(extra="forbid")
    
    mode: "TimeFilterMode" = Field(
        description="""时间筛选模式

<what>决定使用哪种 VizQL 筛选类型</what>
<when>ALWAYS required</when>

<decision_rule>
- 具体日期/日期范围 → ABSOLUTE_RANGE
- 相对表达（最近N、本月、年初至今）→ RELATIVE
- 多个离散日期点 → SET
</decision_rule>"""
    )
    
    # ABSOLUTE_RANGE 模式字段
    start_date: Optional[str] = Field(
        default=None,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="""开始日期（RFC 3339 格式 YYYY-MM-DD）
        
<when>REQUIRED when mode = ABSOLUTE_RANGE</when>
<format>LLM 必须直接输出计算后的日期</format>"""
    )
    
    end_date: Optional[str] = Field(
        default=None,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="""结束日期（RFC 3339 格式 YYYY-MM-DD）
        
<when>REQUIRED when mode = ABSOLUTE_RANGE</when>
<format>LLM 必须直接输出计算后的日期</format>"""
    )
    
    # RELATIVE 模式字段
    period_type: Optional["PeriodType"] = Field(
        default=None,
        description="""时间周期类型（与 VizQL PeriodType 对齐）
        
<when>REQUIRED when mode = RELATIVE</when>
<values>DAYS, WEEKS, MONTHS, QUARTERS, YEARS</values>"""
    )
    
    date_range_type: Optional["DateRangeType"] = Field(
        default=None,
        description="""相对日期范围类型（与 VizQL dateRangeType 对齐）
        
<when>REQUIRED when mode = RELATIVE</when>
<values>CURRENT, LAST, LASTN, NEXT, NEXTN, TODATE</values>"""
    )
    
    range_n: Optional[int] = Field(
        default=None,
        ge=1,
        description="""周期数量
        
<when>REQUIRED when date_range_type = LASTN or NEXTN</when>"""
    )
    
    anchor_date: Optional[str] = Field(
        default=None,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="""锚定日期（可选，默认今天）"""
    )
    
    # SET 模式字段
    date_values: Optional[List[str]] = Field(
        default=None,
        description="""离散日期值列表
        
<when>REQUIRED when mode = SET</when>
<format>支持年("2024")、季度("2024-Q1")、月("2024-01")、日("2024-01-15")</format>"""
    )
    
    @model_validator(mode='after')
    def validate_mode_dependencies(self) -> 'TimeFilterSpec':
        """验证模式相关的字段依赖"""
        from .enums import TimeFilterMode, DateRangeType
        
        if self.mode == TimeFilterMode.ABSOLUTE_RANGE:
            if self.start_date is None:
                raise ValueError("start_date is required when mode=absolute_range")
            if self.end_date is None:
                raise ValueError("end_date is required when mode=absolute_range")
        
        elif self.mode == TimeFilterMode.RELATIVE:
            if self.period_type is None:
                raise ValueError("period_type is required when mode=relative")
            if self.date_range_type is None:
                raise ValueError("date_range_type is required when mode=relative")
            if self.date_range_type in (DateRangeType.LASTN, DateRangeType.NEXTN):
                if self.range_n is None:
                    raise ValueError("range_n is required when date_range_type=LASTN/NEXTN")
        
        elif self.mode == TimeFilterMode.SET:
            if self.date_values is None or len(self.date_values) == 0:
                raise ValueError("date_values is required when mode=set")
        
        return self


class FilterSpec(BaseModel):
    """
    筛选规格
    
    <what>单个筛选条件的规格</what>
    
    <decision_tree>
    START
      │
      ├─► field = ? (ALWAYS fill)
      │
      ├─► filter_type = ? (ALWAYS fill, determines conditional fields)
      │   │
      │   ├─► time_range
      │   │   └─► fill time_range (required, structured TimeRangeSpec)
      │   │       ├─► range_type = absolute → fill value
      │   │       └─► range_type = relative → fill relative_type, period_unit, [period_count]
      │   │
      │   ├─► set
      │   │   ├─► fill values (required)
      │   │   └─► fill exclude (default: false)
      │   │
      │   ├─► quantitative
      │   │   └─► fill min_value and/or max_value
      │   │
      │   └─► match
      │       └─► fill pattern (required)
      │
    END
    </decision_tree>
    """
    model_config = ConfigDict(extra="forbid")
    
    field: str = Field(
        min_length=1,
        description="""筛选字段名（业务术语）

<what>被筛选的字段</what>
<when>ALWAYS required</when>
<how>Use exact term from question</how>

<decision_rule>
Prompt Step 4 (检测时间筛选) → 填写 field
- 使用问题中的原始术语
</decision_rule>"""
    )
    
    filter_type: FilterType = Field(
        description="""筛选类型

<what>筛选条件的类型</what>
<when>ALWAYS required</when>
<how>Detect from filter expression in question</how>

<decision_rule>
Prompt Step 4 (检测时间筛选) → 填写 filter_type
- 时间条件 ("2024年", "最近3个月") → time_range
- 枚举值 ("华东地区", "产品A") → set
- 数值范围 (">1000", "100-500") → quantitative
- 模糊匹配 ("包含XX") → match
</decision_rule>

<values>
- time_range: 时间范围筛选
- set: 枚举值筛选
- quantitative: 数值范围筛选
- match: 模糊匹配筛选
</values>"""
    )
    
    # time_filter 类型字段（与 VizQL API 对齐）
    time_filter: Optional[TimeFilterSpec] = Field(
        default=None,
        description="""时间筛选（新版，与 VizQL API 对齐）

<what>时间筛选的结构化表示，直接映射到 VizQL 日期筛选类型</what>

<when>ONLY when filter_type = time_range</when>

<dependency>
- field: filter_type
- condition: filter_type == "time_range"
</dependency>

<decision_rule>
IF filter_type != time_range THEN null (不填写！)
IF filter_type == time_range:
  - 绝对日期: {"mode": "absolute_range", "start_date": "2024-01-01", "end_date": "2024-12-31"}
  - 相对日期: {"mode": "relative", "period_type": "MONTHS", "date_range_type": "LASTN", "range_n": 3}
  - 离散日期: {"mode": "set", "date_values": ["2024-01", "2024-02"]}
</decision_rule>

<examples>
- "2024年" → {"mode": "absolute_range", "start_date": "2024-01-01", "end_date": "2024-12-31"}
- "2024年Q1" → {"mode": "absolute_range", "start_date": "2024-01-01", "end_date": "2024-03-31"}
- "2024年1月到5月" → {"mode": "absolute_range", "start_date": "2024-01-01", "end_date": "2024-05-31"}
- "最近3个月" → {"mode": "relative", "period_type": "MONTHS", "date_range_type": "LASTN", "range_n": 3}
- "年初至今" → {"mode": "relative", "period_type": "YEARS", "date_range_type": "TODATE"}
- "本月" → {"mode": "relative", "period_type": "MONTHS", "date_range_type": "CURRENT"}
- "2024年1月和2月" → {"mode": "set", "date_values": ["2024-01", "2024-02"]}
</examples>"""
    )
    
    # set 类型字段
    values: Optional[List[str]] = Field(
        default=None,
        description="""值列表

<what>枚举筛选的值列表</what>

<when>ONLY when filter_type = set</when>

<dependency>
- field: filter_type
- condition: filter_type == "set"
</dependency>

<decision_rule>
IF filter_type != set THEN null (不填写！)
IF filter_type == set:
  - 提取问题中的枚举值
</decision_rule>

<examples>
- "华东地区" → ["华东"]
- "产品A和产品B" → ["产品A", "产品B"]
</examples>"""
    )
    
    exclude: Optional[bool] = Field(
        default=None,
        description="""是否排除

<what>是包含还是排除这些值</what>

<when>ONLY when filter_type = set</when>

<dependency>
- field: filter_type
- condition: filter_type == "set"
</dependency>

<decision_rule>
IF filter_type != set THEN null (不填写！)
IF filter_type == set:
  - "不包括" / "排除" / "除了" → true
  - DEFAULT: false (包含)
</decision_rule>"""
    )
    
    # quantitative 类型字段
    min_value: Optional[float] = Field(
        default=None,
        description="""最小值

<when>ONLY when filter_type = quantitative</when>

<dependency>
- field: filter_type
- condition: filter_type == "quantitative"
</dependency>"""
    )
    
    max_value: Optional[float] = Field(
        default=None,
        description="""最大值

<when>ONLY when filter_type = quantitative</when>

<dependency>
- field: filter_type
- condition: filter_type == "quantitative"
</dependency>"""
    )
    
    # match 类型字段
    pattern: Optional[str] = Field(
        default=None,
        description="""匹配模式

<when>ONLY when filter_type = match</when>

<dependency>
- field: filter_type
- condition: filter_type == "match"
</dependency>"""
    )
    
    @model_validator(mode='after')
    def validate_filter_type_dependencies(self) -> 'FilterSpec':
        """验证筛选类型相关的字段依赖"""
        
        if self.filter_type == FilterType.TIME_RANGE:
            if self.time_filter is None:
                raise ValueError("time_filter is required when filter_type=time_range")
        
        if self.filter_type == FilterType.SET:
            if self.values is None:
                raise ValueError("values is required when filter_type=set")
        
        if self.filter_type == FilterType.MATCH:
            if self.pattern is None:
                raise ValueError("pattern is required when filter_type=match")
        
        return self


class AnalysisSpec(BaseModel):
    """
    分析规格 - 纯语义，无 VizQL 概念
    
    <what>用户想要进行的派生计算</what>
    
    <decision_tree>
    START
      │
      ├─► type = ? (ALWAYS fill first, determines conditional fields)
      │   │
      │   ├─► cumulative/percentage
      │   │   │
      │   │   └─► dimensions.length > 1 ?
      │   │       ├─ YES → fill computation_scope (default: per_group)
      │   │       └─ NO  → skip computation_scope (null)
      │   │
      │   ├─► ranking
      │   │   ├─► fill order (default: desc)
      │   │   └─► dimensions.length > 1 ?
      │   │       ├─ YES → fill computation_scope (default: per_group)
      │   │       └─ NO  → skip computation_scope (null)
      │   │
      │   ├─► moving
      │   │   ├─► fill window_size (required)
      │   │   └─► dimensions.length > 1 ?
      │   │       ├─ YES → fill computation_scope (default: per_group)
      │   │       └─ NO  → skip computation_scope (null)
      │   │
      │   └─► period_compare
      │       └─► fill compare_type (required)
      │
      ├─► target_measure = ? (ALWAYS fill)
      │
      └─► aggregation = ? (ALWAYS fill, default: sum)
      
    END
    </decision_tree>
    
    <fill_order>
    ┌────┬─────────────────────────┬─────────────────────────────────────┐
    │ #  │ Field                   │ Condition                           │
    ├────┼─────────────────────────┼─────────────────────────────────────┤
    │ 1  │ type                    │ ALWAYS (determines other fields)    │
    │ 2  │ target_measure          │ ALWAYS                              │
    │ 3  │ aggregation             │ ALWAYS (default: sum)               │
    │ 4  │ computation_scope       │ IF dimensions.length > 1            │
    │ 5  │ order                   │ IF type = ranking                   │
    │ 6  │ window_size             │ IF type = moving                    │
    │ 7  │ compare_type            │ IF type = period_compare            │
    └────┴─────────────────────────┴─────────────────────────────────────┘
    </fill_order>
    
    <examples>
    Example 1 - Simple cumulative (single dimension):
    Input: "按月累计销售额"
    Output: {
        "type": "cumulative",
        "target_measure": "销售额",
        "aggregation": "sum"
    }
    Note: 没有 computation_scope，因为只有一个维度
    
    Example 2 - Multi-dimension cumulative (per_group):
    Input: "各省份按月累计销售额"
    Output: {
        "type": "cumulative",
        "target_measure": "销售额",
        "aggregation": "sum",
        "computation_scope": "per_group"
    }
    Note: 有 computation_scope，因为有两个维度（省份、月）
    
    Example 3 - Ranking:
    Input: "销售额排名"
    Output: {
        "type": "ranking",
        "target_measure": "销售额",
        "aggregation": "sum",
        "order": "desc"
    }
    </examples>
    
    <anti_patterns>
    ❌ ERROR 1: Setting computation_scope for single dimension
    Input: "按月累计销售额" (only one dimension: 月)
    Wrong: {"computation_scope": "per_group"}
    Right: {} (omit computation_scope)
    
    ❌ ERROR 2: Using technical field names
    Wrong: {"target_measure": "Sales"}
    Right: {"target_measure": "销售额"}
    
    ❌ ERROR 3: Setting order for non-ranking type
    Wrong: {"type": "cumulative", "order": "desc"}
    Right: {"type": "cumulative"} (omit order)
    </anti_patterns>
    """
    model_config = ConfigDict(extra="forbid")
    
    type: AnalysisType = Field(
        description="""分析类型

<what>派生计算的类型</what>
<when>ALWAYS required (determines other conditional fields)</when>
<how>Detect from keywords in question</how>

<decision_rule>
Prompt Step 5 (检测分析类型) → 填写 type
- "累计" / "累积" / "running" → cumulative
- "排名" / "排序" / "TOP" / "前N名" → ranking
- "占比" / "百分比" / "%" → percentage
- "同比" / "环比" / "对比" → period_compare
- "移动平均" / "滑动" → moving
</decision_rule>

<values>
- cumulative: 累计计算
- ranking: 排名计算
- percentage: 占比计算
- period_compare: 同比/环比
- moving: 移动计算
</values>

<examples>
- "按月累计销售额" → cumulative
- "销售额排名前10" → ranking
- "各省份销售额占比" → percentage
</examples>"""
    )
    
    target_measure: str = Field(
        min_length=1,
        description="""目标度量（业务术语）

<what>要进行派生计算的度量名称</what>
<when>ALWAYS required</when>
<how>Use exact term from question (business term, not technical field name)</how>

<decision_rule>
- 使用问题中的原始术语
- 必须是 measures 列表中的某个度量名称
</decision_rule>

<examples>
- "按月累计销售额" → "销售额"
- "利润排名" → "利润"
</examples>

<anti_patterns>
❌ Using technical field names: "Sales" instead of "销售额"
</anti_patterns>"""
    )
    
    aggregation: Literal["sum", "avg", "count", "countd", "min", "max"] = Field(
        default="sum",
        description="""聚合方式

<what>派生计算前的基础聚合函数</what>
<when>ALWAYS (default: sum)</when>
<how>Detect from keywords, default to sum</how>

<decision_rule>
- "总" / "合计" / default → sum
- "平均" → avg
- "多少个" / "几种" → countd
- "最大" → max
- "最小" → min
</decision_rule>

<values>
- sum: 求和（默认）
- avg: 平均
- count: 计数
- countd: 去重计数
- min: 最小值
- max: 最大值
</values>"""
    )
    
    computation_scope: Optional[ComputationScope] = Field(
        default=None,
        description="""计算范围（语义意图）

<what>是按组计算还是跨所有数据计算</what>

<when>ONLY when query has MULTIPLE dimensions (len(dimensions) > 1)</when>

<dependency>
- field: dimensions (from parent SemanticQuery)
- condition: length > 1
- reason: 单维度不需要指定计算范围，多维度才需要区分 per_group 或 across_all
</dependency>

<decision_rule>
Prompt Step 6 (确定计算范围) → 填写 computation_scope
IF dimensions.length == 1 THEN null (不填写！)
IF dimensions.length > 1:
  - "各XX" / "每个XX" in question → per_group
  - "总" / "全部" / "整体" in question → across_all
  - DEFAULT: per_group
</decision_rule>

<values>
- per_group: 按组计算（每个省份独立累计）
- across_all: 跨所有数据计算（所有数据一起累计）
</values>

<examples>
- "各省份按月累计销售额" (2 dims) → per_group
- "按月累计总销售额" (2 dims) → across_all
- "按月累计销售额" (1 dim) → null (不填写)
</examples>

<anti_patterns>
❌ 单维度查询时设置 computation_scope
❌ 没有明确"总"关键词时默认 across_all
</anti_patterns>"""
    )
    
    order: Optional[Literal["asc", "desc"]] = Field(
        default=None,
        description="""排序方向

<what>排名的排序方向</what>

<when>ONLY when type = ranking</when>

<dependency>
- field: type
- condition: type == "ranking"
</dependency>

<decision_rule>
IF type != ranking THEN null (不填写！)
IF type == ranking:
  - "前N名" / "TOP" / default → desc
  - "后N名" / "BOTTOM" → asc
</decision_rule>

<values>
- desc: 降序（默认，值大的排前面）
- asc: 升序（值小的排前面）
</values>

<anti_patterns>
❌ 非 ranking 类型时设置 order
</anti_patterns>"""
    )
    
    window_size: Optional[int] = Field(
        default=None,
        ge=1,
        description="""窗口大小

<what>移动计算的窗口大小</what>

<when>ONLY when type = moving</when>

<dependency>
- field: type
- condition: type == "moving"
</dependency>

<decision_rule>
IF type != moving THEN null (不填写！)
IF type == moving:
  - "移动平均3期" → 3
  - "滑动5日" → 5
</decision_rule>

<anti_patterns>
❌ 非 moving 类型时设置 window_size
</anti_patterns>"""
    )
    
    compare_type: Optional[Literal["yoy", "mom", "wow", "dod"]] = Field(
        default=None,
        description="""对比类型

<what>同比/环比的对比类型</what>

<when>ONLY when type = period_compare</when>

<dependency>
- field: type
- condition: type == "period_compare"
</dependency>

<decision_rule>
IF type != period_compare THEN null (不填写！)
IF type == period_compare:
  - "同比" / "去年同期" → yoy
  - "环比" / "上月" → mom
  - "周环比" → wow
  - "日环比" → dod
</decision_rule>

<values>
- yoy: 同比（Year over Year）
- mom: 月环比（Month over Month）
- wow: 周环比（Week over Week）
- dod: 日环比（Day over Day）
</values>

<anti_patterns>
❌ 非 period_compare 类型时设置 compare_type
</anti_patterns>"""
    )
    
    @model_validator(mode='after')
    def validate_type_dependencies(self) -> 'AnalysisSpec':
        """验证类型相关的字段依赖"""
        
        # Rule 1: order 只在 ranking 类型时有效
        if self.order is not None and self.type != AnalysisType.RANKING:
            raise ValueError("order should only be set when type=ranking")
        
        # Rule 2: window_size 只在 moving 类型时有效
        if self.window_size is not None and self.type != AnalysisType.MOVING:
            raise ValueError("window_size should only be set when type=moving")
        
        # Rule 3: compare_type 只在 period_compare 类型时有效
        if self.compare_type is not None and self.type != AnalysisType.PERIOD_COMPARE:
            raise ValueError("compare_type should only be set when type=period_compare")
        
        return self


class OutputControl(BaseModel):
    """
    输出控制
    
    <what>结果排序和限制</what>
    """
    model_config = ConfigDict(extra="forbid")
    
    limit: Optional[int] = Field(
        default=None,
        ge=1,
        description="""结果限制数量

<what>返回结果的最大行数</what>
<when>IF question has TopN requirement</when>

<decision_rule>
- "前10名" / "TOP10" → 10
- "前5" / "TOP5" → 5
</decision_rule>"""
    )
    
    sort_by: Optional[str] = Field(
        default=None,
        description="""排序字段

<what>用于排序的字段名（业务术语）</what>
<when>IF question has sorting requirement</when>"""
    )
    
    sort_direction: Optional[Literal["asc", "desc"]] = Field(
        default=None,
        description="""排序方向

<what>排序的方向</what>
<when>IF sort_by is specified</when>

<dependency>
- field: sort_by
- condition: sort_by is not None
</dependency>

<values>
- desc: 降序（默认）
- asc: 升序
</values>"""
    )


class SemanticQuery(BaseModel):
    """
    语义查询 - LLM 输出的纯语义模型
    
    <what>Understanding Agent 输出的结构化查询意图，完全不包含 VizQL 技术概念</what>
    
    <design_principles>
    - 完全不包含 VizQL 技术概念（addressing、partitioning、RUNNING_SUM 等）
    - 只表达用户意图的语义
    - 使用业务术语，不使用技术字段名
    </design_principles>
    
    <decision_tree>
    START
      │
      ├─► measures = ? (ALWAYS fill, at least one)
      │   └─► Extract numeric concepts from question
      │
      ├─► dimensions = ? (IF grouping needed)
      │   └─► Extract categorical concepts from question
      │   └─► Mark is_time and time_granularity for time dimensions
      │
      ├─► filters = ? (IF filtering needed)
      │   └─► Extract filter conditions from question
      │
      ├─► analyses = ? (IF derived calculation needed)
      │   │
      │   └─► For each analysis:
      │       ├─► type = ? (from Step 5)
      │       ├─► target_measure = ? (which measure to analyze)
      │       ├─► aggregation = ? (default: sum)
      │       └─► computation_scope = ? (ONLY if dimensions.length > 1)
      │
      └─► output_control = ? (IF TopN/sorting needed)
    
    END
    </decision_tree>
    
    <fill_order>
    ┌────┬─────────────────────────┬─────────────────────────────────────┐
    │ #  │ Field                   │ Condition                           │
    ├────┼─────────────────────────┼─────────────────────────────────────┤
    │ 1  │ measures                │ ALWAYS (at least one required)      │
    │ 2  │ dimensions              │ IF grouping needed                  │
    │ 3  │ filters                 │ IF filtering needed                 │
    │ 4  │ analyses                │ IF derived calculation needed       │
    │ 5  │ output_control          │ IF TopN/sorting needed              │
    └────┴─────────────────────────┴─────────────────────────────────────┘
    </fill_order>
    
    <examples>
    Example 1 - Simple aggregation (no analysis):
    Input: "各省份的销售额"
    Output: {
        "measures": [{"name": "销售额", "aggregation": "sum"}],
        "dimensions": [{"name": "省份", "is_time": false}]
    }
    
    Example 2 - Single dimension cumulative (no computation_scope):
    Input: "按月累计销售额"
    Output: {
        "measures": [{"name": "销售额", "aggregation": "sum"}],
        "dimensions": [{"name": "日期", "is_time": true, "time_granularity": "month"}],
        "analyses": [{
            "type": "cumulative",
            "target_measure": "销售额",
            "aggregation": "sum"
        }]
    }
    
    Example 3 - Multi-dimension cumulative (with computation_scope):
    Input: "各省份按月累计销售额"
    Output: {
        "measures": [{"name": "销售额", "aggregation": "sum"}],
        "dimensions": [
            {"name": "省份", "is_time": false},
            {"name": "日期", "is_time": true, "time_granularity": "month"}
        ],
        "analyses": [{
            "type": "cumulative",
            "target_measure": "销售额",
            "aggregation": "sum",
            "computation_scope": "per_group"
        }]
    }
    
    Example 4 - With time filter (absolute year):
    Input: "2024年各省份销售额"
    Output: {
        "measures": [{"name": "销售额", "aggregation": "sum"}],
        "dimensions": [{"name": "省份", "is_time": false}],
        "filters": [{
            "field": "日期",
            "filter_type": "time_range",
            "time_filter": {"mode": "absolute_range", "start_date": "2024-01-01", "end_date": "2024-12-31"}
        }]
    }
    
    Example 5 - With time filter (relative):
    Input: "最近3个月各省份销售额"
    Output: {
        "measures": [{"name": "销售额", "aggregation": "sum"}],
        "dimensions": [{"name": "省份", "is_time": false}],
        "filters": [{
            "field": "日期",
            "filter_type": "time_range",
            "time_filter": {"mode": "relative", "period_type": "MONTHS", "date_range_type": "LASTN", "range_n": 3}
        }]
    }
    
    Example 6 - With time filter (absolute range):
    Input: "2024年1月到5月各省份销售额"
    Output: {
        "measures": [{"name": "销售额", "aggregation": "sum"}],
        "dimensions": [{"name": "省份", "is_time": false}],
        "filters": [{
            "field": "日期",
            "filter_type": "time_range",
            "time_filter": {"mode": "absolute_range", "start_date": "2024-01-01", "end_date": "2024-05-31"}
        }]
    }
    
    Example 7 - With time filter (multiple discrete dates):
    Input: "2024年1月和2月各省份销售额"
    Output: {
        "measures": [{"name": "销售额", "aggregation": "sum"}],
        "dimensions": [{"name": "省份", "is_time": false}],
        "filters": [{
            "field": "日期",
            "filter_type": "time_range",
            "time_filter": {"mode": "set", "date_values": ["2024-01", "2024-02"]}
        }]
    }
    
    Example 8 - With time filter (year to date):
    Input: "年初至今各省份销售额"
    Output: {
        "measures": [{"name": "销售额", "aggregation": "sum"}],
        "dimensions": [{"name": "省份", "is_time": false}],
        "filters": [{
            "field": "日期",
            "filter_type": "time_range",
            "time_filter": {"mode": "relative", "period_type": "YEARS", "date_range_type": "TODATE"}
        }]
    }
    </examples>
    
    <anti_patterns>
    ❌ ERROR 1: Using technical field names
    Wrong: {"measures": [{"name": "Sales"}]}
    Right: {"measures": [{"name": "销售额"}]}
    
    ❌ ERROR 2: Including VizQL concepts
    Wrong: {"analyses": [{"addressing": ["Order_Date"]}]}
    Right: {"analyses": [{"computation_scope": "per_group"}]}
    
    ❌ ERROR 3: Setting computation_scope for single dimension
    Input: "按月累计销售额" (only one dimension: 月)
    Wrong: {"analyses": [{"computation_scope": "per_group"}]}
    Right: {"analyses": [{}]} (omit computation_scope)
    </anti_patterns>
    """
    model_config = ConfigDict(extra="forbid")
    
    measures: List[MeasureSpec] = Field(
        min_length=1,
        description="""度量列表

<what>需要聚合计算的数值字段</what>
<when>ALWAYS required (at least one)</when>
<how>Extract numeric concepts from question</how>

<decision_rule>
Prompt Step 2 (提取业务实体) + Step 3 (分类实体角色) → 填写 measures
- 识别问题中的数值概念（销售额、利润、数量等）
- 每个数值概念对应一个 MeasureSpec
- 使用问题中的原始术语，不使用技术字段名
</decision_rule>

<examples>
- "各省份的销售额" → [{"name": "销售额", "aggregation": "sum"}]
- "平均利润" → [{"name": "利润", "aggregation": "avg"}]
</examples>"""
    )
    
    dimensions: List[DimensionSpec] = Field(
        default_factory=list,
        description="""维度列表

<what>用于分组的分类字段</what>
<when>IF question implies grouping ("各XX", "按XX", "每个XX")</when>
<how>Extract categorical concepts from question</how>

<decision_rule>
Prompt Step 2 (提取业务实体) + Step 3 (分类实体角色) → 填写 dimensions
- "各省份" → {"name": "省份", "is_time": false}
- "按月" → {"name": "日期", "is_time": true, "time_granularity": "month"}
- "每个产品" → {"name": "产品", "is_time": false}
</decision_rule>

<examples>
- "各省份按月销售额" → [
    {"name": "省份", "is_time": false},
    {"name": "日期", "is_time": true, "time_granularity": "month"}
  ]
</examples>"""
    )
    
    filters: List[FilterSpec] = Field(
        default_factory=list,
        description="""筛选列表

<what>数据筛选条件</what>
<when>IF question has filtering conditions</when>
<how>Extract filter conditions from question</how>

<decision_rule>
Prompt Step 4 (检测时间筛选) → 填写 filters
- "2024年" → time_range filter
- "华东地区" → set filter
- "销售额>1000" → quantitative filter
</decision_rule>"""
    )
    
    analyses: List[AnalysisSpec] = Field(
        default_factory=list,
        description="""分析列表（派生计算）

<what>需要进行的派生计算</what>
<when>IF question implies derived calculation (累计、排名、占比等)</when>
<how>Detect analysis keywords and fill AnalysisSpec</how>

<dependency>
- field: dimensions
- reason: computation_scope depends on dimensions.length
</dependency>

<decision_rule>
Prompt Step 5 (检测分析类型) → 填写 analyses
- "累计" → type=cumulative
- "排名" → type=ranking
- "占比" → type=percentage
- "同比" → type=period_compare
- SKIP IF: 问题中没有派生计算关键词
</decision_rule>"""
    )
    
    output_control: Optional[OutputControl] = Field(
        default=None,
        description="""输出控制

<what>结果排序和限制</what>
<when>IF question has TopN or sorting requirements</when>
<how>Detect TopN keywords</how>

<decision_rule>
- "前10名" → TopN with limit=10
- "TOP5" → TopN with limit=5
- "排名前3" → TopN with limit=3
</decision_rule>"""
    )
    
    @model_validator(mode='after')
    def validate_analyses_scope(self) -> 'SemanticQuery':
        """验证 analyses 中的 computation_scope 与 dimensions 的一致性"""
        dim_count = len(self.dimensions)
        
        for analysis in self.analyses:
            if analysis.computation_scope is not None and dim_count <= 1:
                # 自动修正：单维度时不应有 computation_scope
                analysis.computation_scope = None
        
        return self


# ═══════════════════════════════════════════════════════════════════════════
# MappedQuery 组件 (FieldMapper Node 输出)
# ═══════════════════════════════════════════════════════════════════════════

class FieldMapping(BaseModel):
    """
    单个字段的映射结果
    
    <what>业务术语到技术字段的映射</what>
    """
    model_config = ConfigDict(extra="forbid")
    
    business_term: str = Field(
        min_length=1,
        description="业务术语（来自 SemanticQuery）"
    )
    
    technical_field: str = Field(
        min_length=1,
        description="技术字段名（数据源中的实际字段名）"
    )
    
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="映射置信度（0-1）"
    )
    
    mapping_source: MappingSource = Field(
        description="""映射来源
        
<values>
- rag_high_confidence: RAG 高置信度直接返回（>= 0.9）
- rag_llm_fallback: RAG 低置信度 + LLM 判断（< 0.9）
- cache_hit: 缓存命中
- exact_match: 精确匹配
</values>"""
    )
    
    # 字段数据类型（用于日期筛选策略选择）
    data_type: Optional[str] = Field(
        default=None,
        description="""字段数据类型（来自元数据）

<what>字段在数据源中的数据类型</what>
<values>DATE, DATETIME, STRING, INTEGER, REAL, BOOLEAN</values>

<usage>
QueryBuilder 根据 data_type 选择日期筛选策略：
- DATE/DATETIME: 使用 QUANTITATIVE_DATE 或 DATE (RelativeDateFilter)
- STRING: 使用 DATEPARSE + QUANTITATIVE_DATE，或 SET/MATCH
</usage>"""
    )
    
    # 字段日期格式（STRING 类型日期字段）
    date_format: Optional[str] = Field(
        default=None,
        description="""日期格式（仅 STRING 类型日期字段）

<what>STRING 类型字段的日期格式模式</what>
<format>Tableau DATEPARSE 格式，如 'yyyy-MM-dd', 'MM/dd/yyyy'</format>

<usage>
QueryBuilder 使用此格式生成 DATEPARSE 表达式：
DATEPARSE('yyyy-MM-dd', [field_name])
</usage>"""
    )
    
    # 维度层级信息（可选）
    category: Optional[DimensionCategory] = Field(
        default=None,
        description="维度类别（time、geography、product 等）"
    )
    
    level: Optional[DimensionLevel] = Field(
        default=None,
        description="层级级别（top、high、medium、low、detail）"
    )
    
    granularity: Optional[str] = Field(
        default=None,
        description="粒度描述（country、province、city 等）"
    )
    
    # 低置信度备选项
    alternatives: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="备选映射（置信度 < 0.7 时提供）"
    )


class MappedQuery(BaseModel):
    """
    映射后的查询 - FieldMapper Node 输出
    
    <what>SemanticQuery 中的业务术语已映射为技术字段名</what>
    
    <design_principles>
    - 保留 SemanticQuery 的语义结构
    - 添加字段映射信息
    - 包含映射置信度和来源
    </design_principles>
    """
    model_config = ConfigDict(extra="forbid")
    
    # 原始 SemanticQuery（保留语义结构）
    semantic_query: SemanticQuery = Field(
        description="原始语义查询"
    )
    
    # 字段映射结果
    field_mappings: Dict[str, FieldMapping] = Field(
        description="""字段映射字典
        
<what>业务术语 → 技术字段的映射</what>
<how>key 是业务术语，value 是 FieldMapping</how>

<examples>
{
    "销售额": FieldMapping(
        business_term="销售额",
        technical_field="Sales",
        confidence=0.95,
        mapping_source="rag_high_confidence"
    ),
    "省份": FieldMapping(
        business_term="省份",
        technical_field="Province",
        confidence=0.85,
        mapping_source="rag_llm_fallback",
        category="geography",
        level="medium"
    )
}
</examples>"""
    )
    
    # 聚合置信度（可选，默认自动计算）
    overall_confidence: Optional[float] = Field(
        default=None,
        ge=0.0, le=1.0,
        description="整体映射置信度（所有映射的最小值），如果不提供则自动计算"
    )
    
    # 低置信度警告
    low_confidence_fields: List[str] = Field(
        default_factory=list,
        description="置信度 < 0.7 的字段列表"
    )
    
    @model_validator(mode='after')
    def compute_overall_confidence(self) -> 'MappedQuery':
        """自动计算 overall_confidence 和 low_confidence_fields"""
        if self.field_mappings:
            confidences = [m.confidence for m in self.field_mappings.values()]
            if self.overall_confidence is None:
                self.overall_confidence = min(confidences) if confidences else 1.0
            # 自动填充低置信度字段
            if not self.low_confidence_fields:
                self.low_confidence_fields = [
                    term for term, mapping in self.field_mappings.items()
                    if mapping.confidence < 0.7
                ]
        elif self.overall_confidence is None:
            self.overall_confidence = 1.0
        return self
    
    def get_technical_field(self, business_term: str) -> Optional[str]:
        """获取业务术语对应的技术字段名"""
        mapping = self.field_mappings.get(business_term)
        return mapping.technical_field if mapping else None
    
    def get_confidence(self, business_term: str) -> Optional[float]:
        """获取业务术语映射的置信度"""
        mapping = self.field_mappings.get(business_term)
        return mapping.confidence if mapping else None


# ═══════════════════════════════════════════════════════════════════════════
# 导出
# ═══════════════════════════════════════════════════════════════════════════

__all__ = [
    # SemanticQuery 组件
    "MeasureSpec",
    "DimensionSpec",
    "FilterSpec",
    "TimeFilterSpec",     # 与 VizQL API 对齐
    "AnalysisSpec",
    "OutputControl",
    "SemanticQuery",
    
    # MappedQuery 组件
    "FieldMapping",
    "MappedQuery",
]
