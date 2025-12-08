# 数据模型定义

## 概述

本文档集中定义所有数据模型，包括工作流状态、各节点的输入/输出模型。

**设计规范**：本文档遵循 `prompt-and-schema-design.md` 中定义的设计规范，基于 `PROMPT_AND_MODEL_GUIDE.md` 中的前沿研究。

**核心理念**：
- **思考与填写交织**：LLM 是逐 token 生成的，每填一个字段都是一次"微型思考"
- **XML 标签定位**：为每次微型思考提供精确的规则定位锚点
- **`<decision_rule>` 桥梁**：将 Prompt 中的抽象思考转化为具体填写动作

对应项目结构：`src/models/`

---

## 1. 工作流状态

### VizQLState

```python
# tableau_assistant/src/models/state.py

from typing import TypedDict, Optional, List, Dict, Any

class VizQLState(TypedDict):
    """
    工作流状态
    
    <what>LangGraph StateGraph 的状态定义，贯穿整个工作流</what>
    """
    
    # ═══════════════════════════════════════════════════════════════════════
    # 问题相关
    # ═══════════════════════════════════════════════════════════════════════
    question: str                          # 原始问题
    boost_question: bool                   # 是否需要增强问题
    boosted_question: Optional[str]        # 增强后的问题
    current_question: str                  # 当前处理的问题
    
    # ═══════════════════════════════════════════════════════════════════════
    # 元数据
    # ═══════════════════════════════════════════════════════════════════════
    datasource: str                        # 数据源名称
    metadata: Optional[Metadata]           # 数据源元数据
    
    # ═══════════════════════════════════════════════════════════════════════
    # 问题分类（Understanding Agent 输出）
    # ═══════════════════════════════════════════════════════════════════════
    is_analysis_question: bool               # 是否为分析类问题（用于路由决策）
    
    # ═══════════════════════════════════════════════════════════════════════
    # 理解和查询构建
    # ═══════════════════════════════════════════════════════════════════════
    semantic_query: Optional[SemanticQuery]  # Understanding Agent 输出（纯语义）
    mapped_query: Optional[MappedQuery]      # FieldMapper Node 输出（技术字段映射）
    vizql_query: Optional[VizQLQuery]        # QueryBuilder Node 输出（技术字段）
    
    # ═══════════════════════════════════════════════════════════════════════
    # 执行结果
    # ═══════════════════════════════════════════════════════════════════════
    query_result: Optional[QueryResult]    # Execute Node 输出
    
    # ═══════════════════════════════════════════════════════════════════════
    # 洞察（渐进式累积）
    # ═══════════════════════════════════════════════════════════════════════
    insights: List[Dict[str, Any]]         # 当前轮次的洞察
    all_insights: List[Dict[str, Any]]     # 所有轮次累积的洞察
    
    # ═══════════════════════════════════════════════════════════════════════
    # 重规划（智能重规划）
    # ═══════════════════════════════════════════════════════════════════════
    replan_decision: Optional[ReplanDecision]  # Replanner Agent 输出
    replan_count: int                          # 重规划次数
    max_replan_rounds: int                     # 最大重规划轮数
    replan_history: List[ReplanHistory]        # 重规划历史记录
    
    # ═══════════════════════════════════════════════════════════════════════
    # 错误和节点完成标志
    # ═══════════════════════════════════════════════════════════════════════
    errors: List[Dict[str, Any]]           # 错误列表
    understanding_complete: bool
    query_builder_complete: bool
    execute_complete: bool
    insight_complete: bool
```


---

## 2. 语义层模型

### 2.1 枚举类型

```python
# tableau_assistant/src/models/semantic/enums.py

from enum import Enum

class AnalysisType(str, Enum):
    """分析类型枚举"""
    CUMULATIVE = "cumulative"        # 累计计算
    RANKING = "ranking"              # 排名计算
    PERCENTAGE = "percentage"        # 占比计算
    PERIOD_COMPARE = "period_compare"  # 同比/环比
    MOVING = "moving"                # 移动计算

class ComputationScope(str, Enum):
    """计算范围枚举"""
    PER_GROUP = "per_group"          # 按组计算
    ACROSS_ALL = "across_all"        # 跨所有数据计算

class FilterType(str, Enum):
    """筛选类型枚举"""
    TIME_RANGE = "time_range"        # 时间范围筛选
    SET = "set"                      # 枚举值筛选
    QUANTITATIVE = "quantitative"    # 数值范围筛选
    MATCH = "match"                  # 模糊匹配筛选
```

### 2.2 MeasureSpec

```python
# tableau_assistant/src/models/semantic/query.py

class MeasureSpec(BaseModel):
    """
    度量规格
    
    <what>单个度量字段的规格，表示需要聚合计算的数值字段</what>
    """
    model_config = ConfigDict(extra="forbid")
    
    name: str = Field(
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
```

### 2.3 DimensionSpec

```python
class DimensionSpec(BaseModel):
    """
    维度规格
    
    <what>单个维度字段的规格，表示用于分组的分类字段</what>
    """
    model_config = ConfigDict(extra="forbid")
    
    name: str = Field(
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
```

### 2.4 FilterSpec

```python
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
      │   │   └─► fill time_value (required)
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
    
    # time_range 类型字段
    time_value: Optional[str] = Field(
        default=None,
        description="""时间值

<what>时间筛选的值</what>

<when>ONLY when filter_type = time_range</when>

<dependency>
- field: filter_type
- condition: filter_type == "time_range"
</dependency>

<decision_rule>
IF filter_type != time_range THEN null (不填写！)
IF filter_type == time_range:
  - 保留原始时间表达式，由 parse_date 工具解析
</decision_rule>

<examples>
- "2024年" → "2024年"
- "最近3个月" → "最近3个月"
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
            if self.time_value is None:
                raise ValueError("time_value is required when filter_type=time_range")
        
        if self.filter_type == FilterType.SET:
            if self.values is None:
                raise ValueError("values is required when filter_type=set")
        
        if self.filter_type == FilterType.MATCH:
            if self.pattern is None:
                raise ValueError("pattern is required when filter_type=match")
        
        return self
```


### 2.5 AnalysisSpec

```python
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
    
    <conditional_groups>
    Group 1: ALWAYS fill (required fields)
    ├─ type
    ├─ target_measure
    └─ aggregation (default: sum)
    
    Group 2: type-dependent fields (fill based on type value)
    ├─ [type=ranking]           → order
    ├─ [type=moving]            → window_size
    └─ [type=period_compare]    → compare_type
    
    Group 3: context-dependent fields (fill based on query context)
    └─ [dimensions.length > 1]  → computation_scope
    </conditional_groups>
    
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
```


### 2.6 OutputControl

```python
class OutputControl(BaseModel):
    """
    输出控制
    
    <what>结果排序和限制</what>
    """
    model_config = ConfigDict(extra="forbid")
    
    limit: Optional[int] = Field(
        default=None,
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
```

### 2.7 SemanticQuery（完整定义）

```python
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
    
    Example 4 - With time filter:
    Input: "2024年各省份销售额"
    Output: {
        "measures": [{"name": "销售额", "aggregation": "sum"}],
        "dimensions": [{"name": "省份", "is_time": false}],
        "filters": [{
            "field": "日期",
            "filter_type": "time_range",
            "time_value": "2024年"
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
                raise ValueError(
                    f"computation_scope should only be set when dimensions.length > 1, "
                    f"but got {dim_count} dimensions"
                )
        
        return self
```


---

## 2.8 MappedQuery（FieldMapper Node 输出）

```python
# tableau_assistant/src/models/semantic/mapped_query.py

from pydantic import BaseModel, Field
from typing import Dict, List, Optional

class FieldMapping(BaseModel):
    """
    单个字段的映射结果
    
    <what>业务术语到技术字段的映射</what>
    """
    model_config = ConfigDict(extra="forbid")
    
    business_term: str = Field(
        description="业务术语（来自 SemanticQuery）"
    )
    
    technical_field: str = Field(
        description="技术字段名（数据源中的实际字段名）"
    )
    
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="映射置信度（0-1）"
    )
    
    mapping_source: Literal["rag_direct", "rag_llm_fallback", "cache"] = Field(
        description="""映射来源
        
<values>
- rag_direct: RAG 高置信度直接返回（>= 0.9）
- rag_llm_fallback: RAG 低置信度 + LLM 判断（< 0.9）
- cache: 缓存命中
</values>"""
    )
    
    # 维度层级信息（可选）
    category: Optional[str] = Field(
        default=None,
        description="维度类别（geographic、temporal、product 等）"
    )
    
    level: Optional[int] = Field(
        default=None,
        description="层级级别（1=最高级，如国家；2=次级，如省份）"
    )
    
    granularity: Optional[str] = Field(
        default=None,
        description="粒度描述（country、province、city 等）"
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
        mapping_source="rag_direct"
    ),
    "省份": FieldMapping(
        business_term="省份",
        technical_field="Province",
        confidence=0.85,
        mapping_source="rag_llm_fallback",
        category="geographic",
        level=2,
        granularity="province"
    )
}
</examples>"""
    )
    
    # 低置信度备选项（置信度 < 0.7 时提供）
    low_confidence_alternatives: Optional[Dict[str, List[FieldMapping]]] = Field(
        default=None,
        description="""低置信度字段的备选项
        
<when>当某个字段的映射置信度 < 0.7 时提供 top-3 备选</when>

<examples>
{
    "区域": [
        FieldMapping(business_term="区域", technical_field="Region", confidence=0.65),
        FieldMapping(business_term="区域", technical_field="Province", confidence=0.55),
        FieldMapping(business_term="区域", technical_field="City", confidence=0.45)
    ]
}
</examples>"""
    )
    
    def get_technical_field(self, business_term: str) -> Optional[str]:
        """获取业务术语对应的技术字段名"""
        mapping = self.field_mappings.get(business_term)
        return mapping.technical_field if mapping else None
    
    def get_all_technical_fields(self) -> List[str]:
        """获取所有技术字段名"""
        return [m.technical_field for m in self.field_mappings.values()]
```


---

## 3. VizQL 层模型

### 3.1 VizQLQuery

```python
# tableau_assistant/src/models/vizql/query.py

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Union

class VizQLQuery(BaseModel):
    """
    VizQL 查询
    
    <what>QueryBuilder Node 输出的技术查询，包含 VizQL 技术概念</what>
    
    注意：这个模型由代码组件（FieldMapper、ImplementationResolver、ExpressionGenerator）
    生成，不是 LLM 直接输出。
    """
    
    fields: List["VizQLField"] = Field(
        description="字段列表"
    )
    
    filters: Optional[List["VizQLFilter"]] = Field(
        default=None,
        description="筛选器列表"
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为 API 请求格式"""
        result = {"fields": [f.to_dict() for f in self.fields]}
        if self.filters:
            result["filters"] = [f.to_dict() for f in self.filters]
        return result


# VizQL 字段类型
VizQLField = Union["DimensionField", "MeasureField", "CalculatedField", "TableCalcField"]


class DimensionField(BaseModel):
    """维度字段"""
    fieldCaption: str
    dateFunction: Optional[str] = None  # YEAR, QUARTER, MONTH, WEEK, DAY
    sortDirection: Optional[str] = None  # ASC, DESC
    sortPriority: Optional[int] = None


class MeasureField(BaseModel):
    """度量字段"""
    fieldCaption: str
    function: str  # SUM, AVG, COUNT, COUNTD, MIN, MAX
    sortDirection: Optional[str] = None
    sortPriority: Optional[int] = None


class CalculatedField(BaseModel):
    """计算字段（LOD、COUNTD 等）"""
    fieldCaption: str
    calculation: str  # VizQL 表达式
    sortDirection: Optional[str] = None
    sortPriority: Optional[int] = None


class TableCalcField(BaseModel):
    """表计算字段"""
    fieldCaption: str
    calculation: str  # VizQL 表达式
    tableCalculation: "TableCalcSpecification"
    sortDirection: Optional[str] = None
    sortPriority: Optional[int] = None


class TableCalcSpecification(BaseModel):
    """表计算规格"""
    tableCalcType: str = "CUSTOM"
    dimensions: List["TableCalcFieldReference"]


class TableCalcFieldReference(BaseModel):
    """表计算字段引用"""
    fieldCaption: str
```

### 3.2 QueryResult

```python
# tableau_assistant/src/models/vizql/result.py

class QueryResult(BaseModel):
    """
    查询结果
    
    <what>Execute Node 输出的查询结果</what>
    """
    
    data: List[Dict[str, Any]] = Field(
        description="数据行列表"
    )
    
    columns: List[str] = Field(
        description="列名列表"
    )
    
    row_count: int = Field(
        description="行数"
    )
    
    execution_time: Optional[float] = Field(
        default=None,
        description="执行时间（秒）"
    )
    
    @property
    def dataframe(self) -> "DataFrame":
        """转换为 DataFrame"""
        import pandas as pd
        return pd.DataFrame(self.data)
```

---

## 4. Replanner 模型

### 4.1 ReplanDecision

```python
# tableau_assistant/src/models/replanner.py

class ReplanDecision(BaseModel):
    """
    智能重规划决策
    
    <what>Replanner Agent 输出的决策结果</what>
    
    <fill_order>
    ┌────┬─────────────────────────┬─────────────────────────────────────┐
    │ #  │ Field                   │ Condition                           │
    ├────┼─────────────────────────┼─────────────────────────────────────┤
    │ 1  │ completeness_score      │ ALWAYS                              │
    │ 2  │ should_replan           │ ALWAYS (based on completeness_score)│
    │ 3  │ reason                  │ ALWAYS                              │
    │ 4  │ missing_aspects         │ IF should_replan = true             │
    │ 5  │ new_questions           │ IF should_replan = true             │
    │ 6  │ confidence              │ ALWAYS (default: 0.8)               │
    └────┴─────────────────────────┴─────────────────────────────────────┘
    </fill_order>
    """
    model_config = ConfigDict(extra="forbid")
    
    completeness_score: float = Field(
        ge=0.0,
        le=1.0,
        description="""分析完整度评分（0-1）

<what>当前分析对用户问题的回答完整程度</what>
<when>ALWAYS required</when>
<how>Evaluate based on question coverage, data completeness, insight depth</how>

<decision_rule>
评分标准：
- 0.9-1.0: 完全回答问题，洞察深入 → should_replan = false
- 0.7-0.9: 基本回答问题，可以更深入 → 考虑重规划
- 0.5-0.7: 部分回答问题，缺少关键信息 → should_replan = true
- <0.5: 未能回答问题 → should_replan = true
</decision_rule>"""
    )
    
    should_replan: bool = Field(
        description="""是否需要重规划

<what>是否需要继续分析</what>
<when>ALWAYS required</when>

<decision_rule>
- completeness_score >= 0.9 → false
- completeness_score < 0.9 AND missing_aspects exist → true
- replan_count >= max_replan_rounds → false (强制结束)
</decision_rule>"""
    )
    
    reason: str = Field(
        description="""评估理由

<what>为什么做出这个决策</what>
<when>ALWAYS required</when>"""
    )
    
    missing_aspects: List[str] = Field(
        default_factory=list,
        description="""缺失的分析方面

<what>当前分析缺少的方面</what>
<when>IF should_replan = true</when>

<dependency>
- field: should_replan
- condition: should_replan == true
</dependency>

<examples>
- ["利润率分析", "华东地区异常原因"]
</examples>"""
    )
    
    new_questions: List[str] = Field(
        default_factory=list,
        description="""新问题列表

<what>针对缺失方面生成的具体问题</what>
<when>IF should_replan = true</when>

<dependency>
- field: should_replan
- condition: should_replan == true
</dependency>

<decision_rule>
新问题生成原则：
- 针对性：针对 missing_aspects 中的缺失信息
- 具体性：问题要具体明确
- 可执行性：可以通过查询回答
- 增量性：基于已有结果，增量补充
</decision_rule>

<examples>
- ["各地区的利润率是多少？", "华东地区利润率低的原因？"]
</examples>"""
    )
    
    confidence: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="""决策置信度

<what>对这个决策的置信程度</what>
<when>ALWAYS (default: 0.8)</when>"""
    )
```

### 4.2 ReplanHistory

```python
class ReplanHistory(BaseModel):
    """
    重规划历史记录
    
    <what>记录每轮重规划的信息</what>
    """
    
    round: int = Field(
        description="重规划轮次"
    )
    
    reason: str = Field(
        description="重规划原因"
    )
    
    new_questions: List[str] = Field(
        description="该轮生成的新问题"
    )
    
    completeness_score: float = Field(
        description="该轮的完成度评分"
    )
```

---

## 5. 洞察模型

### 5.1 InsightResult

```python
# tableau_assistant/src/models/insight.py

class InsightResult(BaseModel):
    """
    洞察结果
    
    <what>Insight Agent 输出的分析洞察</what>
    """
    
    summary: Optional[str] = Field(
        default=None,
        description="一句话总结"
    )
    
    findings: List["Insight"] = Field(
        default_factory=list,
        description="洞察列表"
    )
    
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="置信度"
    )


class Insight(BaseModel):
    """
    单个洞察
    
    <what>一条具体的分析发现</what>
    """
    
    type: Literal["trend", "anomaly", "comparison", "pattern"] = Field(
        description="""洞察类型

<values>
- trend: 趋势洞察
- anomaly: 异常洞察
- comparison: 对比洞察
- pattern: 模式洞察
</values>"""
    )
    
    title: str = Field(
        description="洞察标题"
    )
    
    description: str = Field(
        description="洞察描述"
    )
    
    importance: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="重要性评分"
    )
    
    evidence: Optional[Dict[str, Any]] = Field(
        default=None,
        description="支持证据"
    )
```

---

## 6. 错误类型

```python
# tableau_assistant/src/models/errors.py

class TransientError(Exception):
    """
    瞬态错误（可重试）
    
    <what>临时性错误，可以通过重试解决</what>
    
    <examples>
    - 网络超时
    - API 限流
    - 服务暂时不可用
    </examples>
    """
    pass


class PermanentError(Exception):
    """
    永久错误（不可重试）
    
    <what>永久性错误，重试无法解决</what>
    
    <examples>
    - 无效配置
    - 权限不足
    - 资源不存在
    </examples>
    """
    pass


class UserError(Exception):
    """
    用户错误（需要用户修正）
    
    <what>由用户输入导致的错误</what>
    
    <examples>
    - 无效输入
    - 字段不存在
    - 语法错误
    </examples>
    """
    pass


class ValidationError(Exception):
    """验证错误"""
    pass


class FieldMappingError(Exception):
    """字段映射错误"""
    pass
```

---

## 附录：设计规范检查清单

**每个数据模型必须包含**：

- [ ] Class Docstring 中的 `<what>` 标签
- [ ] Class Docstring 中的 `<decision_tree>`（如果有条件字段）
- [ ] Class Docstring 中的 `<fill_order>`（如果有多个字段）
- [ ] Class Docstring 中的 `<examples>`
- [ ] Class Docstring 中的 `<anti_patterns>`

**每个字段必须包含**：

- [ ] `<what>` 标签（字段含义）
- [ ] `<when>` 标签（填写条件）
- [ ] `<how>` 标签（填写方式）
- [ ] `<dependency>` 标签（如果是条件字段）
- [ ] `<decision_rule>` 标签（如果有复杂决策逻辑）
- [ ] `<values>` 标签（如果是枚举类型）
- [ ] `<examples>` 标签（推荐）
- [ ] `<anti_patterns>` 标签（推荐）

**Pydantic Validator**：

- [ ] 验证字段依赖关系
- [ ] 验证条件字段的一致性
- [ ] 提供清晰的错误消息

---

**文档版本**: v2.0
**最后更新**: 2025-12-05
**参考文档**: 
- `prompt-and-schema-design.md`
- `tableau_assistant/docs/PROMPT_AND_MODEL_GUIDE.md`
