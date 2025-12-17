# 附件C：数据模型详细定义

## 概述

本文档定义了语义层的完整数据模型，所有模型都是平台无关的。

## 核心模型

### SemanticQuery

```python
class SemanticQuery(BaseModel):
    """核心语义查询（平台无关）
    
    描述用户想要查询什么数据，不涉及任何平台实现细节。
    """
    
    dimensions: list[DimensionField] | None = None
    """维度字段列表"""
    
    measures: list[MeasureField] | None = None
    """度量字段列表"""
    
    computations: list[Computation] | None = None
    """计算列表（排名、累计、占比等）"""
    
    filters: list[Filter] | None = None
    """筛选条件列表"""
    
    sorts: list[Sort] | None = None
    """排序规则列表"""
    
    row_limit: int | None = None
    """行数限制"""
```

### DimensionField

```python
class DimensionField(BaseModel):
    """维度字段（平台无关）"""
    
    field_name: str
    """字段名（业务术语）"""
    
    date_granularity: DateGranularity | None = None
    """日期粒度（仅日期字段需要）"""
    
    alias: str | None = None
    """显示别名"""


class DateGranularity(str, Enum):
    """日期粒度"""
    YEAR = "YEAR"
    QUARTER = "QUARTER"
    MONTH = "MONTH"
    WEEK = "WEEK"
    DAY = "DAY"
    HOUR = "HOUR"
    MINUTE = "MINUTE"
```

### MeasureField

```python
class MeasureField(BaseModel):
    """度量字段（平台无关）"""
    
    field_name: str
    """字段名（业务术语）"""
    
    aggregation: AggregationType = AggregationType.SUM
    """聚合方式"""
    
    alias: str | None = None
    """显示别名"""


class AggregationType(str, Enum):
    """聚合类型"""
    SUM = "SUM"
    AVG = "AVG"
    COUNT = "COUNT"
    COUNT_DISTINCT = "COUNT_DISTINCT"
    MIN = "MIN"
    MAX = "MAX"
    MEDIAN = "MEDIAN"
    STDEV = "STDEV"
    VAR = "VAR"
```

### Computation

```python
class Computation(BaseModel):
    """计算定义 = 目标 × 分区 × 操作
    
    这是通用计算模型的核心，通过 partition_by 统一描述所有复杂计算。
    """
    
    target: str
    """计算目标（度量字段名）"""
    
    partition_by: list[str] = []
    """分区维度
    
    - [] = 全局（所有数据一起计算）
    - ["月份"] = 按月份分区（每个月内单独计算）
    - 视图维度全部 = 视图粒度（每行单独计算）
    
    计算方向 = 视图维度 - partition_by
    
    平台映射：
    - Tableau: partition_by → Partitioning
    - Power BI: partition_by → CALCULATE + ALL/ALLEXCEPT
    - SQL: partition_by → PARTITION BY
    """
    
    operation: Operation
    """计算操作"""
    
    alias: str | None = None
    """结果字段别名"""


class Operation(BaseModel):
    """计算操作"""
    
    type: OperationType
    """操作类型"""
    
    params: dict = {}
    """操作参数"""


class OperationType(str, Enum):
    """操作类型枚举"""
    
    # ========== 排名类 ==========
    RANK = "RANK"
    """排名（1, 2, 3, ...）"""
    
    DENSE_RANK = "DENSE_RANK"
    """密集排名（1, 2, 2, 3, ...）"""
    
    TOP_N = "TOP_N"
    """前 N 名，params: {n: int}"""
    
    # ========== 累计类 ==========
    RUNNING_SUM = "RUNNING_SUM"
    """累计求和"""
    
    RUNNING_AVG = "RUNNING_AVG"
    """累计平均"""
    
    RUNNING_COUNT = "RUNNING_COUNT"
    """累计计数"""
    
    # ========== 移动类 ==========
    MOVING_AVG = "MOVING_AVG"
    """移动平均，params: {window_size: int}"""
    
    MOVING_SUM = "MOVING_SUM"
    """移动求和，params: {window_size: int}"""
    
    # ========== 比较类 ==========
    PERCENT = "PERCENT"
    """占比（当前值 / 分区总值）"""
    
    DIFFERENCE = "DIFFERENCE"
    """差值"""
    
    GROWTH_RATE = "GROWTH_RATE"
    """增长率（(当前 - 基准) / 基准）"""
    
    # ========== 时间比较类 ==========
    YEAR_AGO = "YEAR_AGO"
    """去年同期，params: {calculation: "VALUE" | "DIFFERENCE" | "GROWTH_RATE"}"""
    
    PERIOD_AGO = "PERIOD_AGO"
    """上一周期，params: {calculation: "VALUE" | "DIFFERENCE" | "GROWTH_RATE"}"""
    
    # ========== 粒度类 ==========
    FIXED = "FIXED"
    """固定粒度聚合（不受视图影响）"""
```

### Filter

```python
class Filter(BaseModel):
    """筛选条件基类"""
    
    field_name: str
    """筛选字段名"""
    
    filter_type: FilterType
    """筛选类型"""


class FilterType(str, Enum):
    """筛选类型"""
    SET = "SET"                     # 集合筛选
    DATE_RANGE = "DATE_RANGE"       # 日期范围
    NUMERIC_RANGE = "NUMERIC_RANGE" # 数值范围
    TEXT_MATCH = "TEXT_MATCH"       # 文本匹配
    TOP_N = "TOP_N"                 # Top N 筛选


class SetFilter(Filter):
    """集合筛选"""
    filter_type: Literal[FilterType.SET] = FilterType.SET
    values: list[str]
    """包含的值列表"""
    
    exclude: bool = False
    """是否排除（True = 排除这些值）"""


class DateRangeFilter(Filter):
    """日期范围筛选"""
    filter_type: Literal[FilterType.DATE_RANGE] = FilterType.DATE_RANGE
    
    range_type: DateRangeType
    """范围类型"""
    
    start_date: date | None = None
    """开始日期（CUSTOM 类型需要）"""
    
    end_date: date | None = None
    """结束日期（CUSTOM 类型需要）"""
    
    n: int | None = None
    """N 值（PREVIOUS_N、NEXT_N 类型需要）"""
    
    granularity: DateGranularity = DateGranularity.DAY
    """日期粒度"""


class DateRangeType(str, Enum):
    """日期范围类型"""
    CURRENT = "CURRENT"           # 当前期间
    PREVIOUS = "PREVIOUS"         # 上一期间
    PREVIOUS_N = "PREVIOUS_N"     # 最近 N 个期间
    NEXT = "NEXT"                 # 下一期间
    NEXT_N = "NEXT_N"             # 未来 N 个期间
    TO_DATE = "TO_DATE"           # 期间至今
    CUSTOM = "CUSTOM"             # 自定义范围


class NumericRangeFilter(Filter):
    """数值范围筛选"""
    filter_type: Literal[FilterType.NUMERIC_RANGE] = FilterType.NUMERIC_RANGE
    
    min_value: float | None = None
    """最小值"""
    
    max_value: float | None = None
    """最大值"""
    
    include_min: bool = True
    """是否包含最小值"""
    
    include_max: bool = True
    """是否包含最大值"""


class TextMatchFilter(Filter):
    """文本匹配筛选"""
    filter_type: Literal[FilterType.TEXT_MATCH] = FilterType.TEXT_MATCH
    
    pattern: str
    """匹配模式"""
    
    match_type: TextMatchType = TextMatchType.CONTAINS
    """匹配类型"""


class TextMatchType(str, Enum):
    """文本匹配类型"""
    CONTAINS = "CONTAINS"         # 包含
    STARTS_WITH = "STARTS_WITH"   # 开头
    ENDS_WITH = "ENDS_WITH"       # 结尾
    EXACT = "EXACT"               # 精确匹配
    REGEX = "REGEX"               # 正则表达式
```

### Sort

```python
class Sort(BaseModel):
    """排序规则"""
    
    field_name: str
    """排序字段名"""
    
    direction: SortDirection = SortDirection.DESC
    """排序方向"""
    
    priority: int = 0
    """排序优先级（多字段排序时使用）"""


class SortDirection(str, Enum):
    """排序方向"""
    ASC = "ASC"
    DESC = "DESC"
```

## Step 1 相关模型

```python
class Step1Output(BaseModel):
    """Step 1 输出"""
    
    what: What
    where: Where
    how: How
    semantic_restatement: str


class What(BaseModel):
    """What - 目标"""
    measures: list[MeasureSpec]


class MeasureSpec(BaseModel):
    """度量规格"""
    field: str
    aggregation: str = "SUM"


class Where(BaseModel):
    """Where - 范围"""
    dimensions: list[DimensionSpec]
    filters: list[FilterSpec]


class DimensionSpec(BaseModel):
    """维度规格"""
    field: str
    granularity: str | None = None


class FilterSpec(BaseModel):
    """筛选规格"""
    field: str
    type: str
    values: list | dict


class How(BaseModel):
    """How - 操作"""
    type: HowType
    hints: dict = {}


class HowType(str, Enum):
    """操作类型"""
    SIMPLE = "SIMPLE"
    RANKING = "RANKING"
    CUMULATIVE = "CUMULATIVE"
    COMPARISON = "COMPARISON"
    GRANULARITY = "GRANULARITY"
```

## Step 2 相关模型

```python
class Step2Output(BaseModel):
    """Step 2 输出"""
    computations: list[Computation]
```

## 解析结果模型

```python
class SemanticParseResult(BaseModel):
    """语义解析完整结果"""
    
    restated_question: str
    """重述后的问题"""
    
    intent: Intent
    """意图分类"""
    
    semantic_query: SemanticQuery | None = None
    """语义查询（仅 DATA_QUERY 意图）"""
    
    clarification: ClarificationQuestion | None = None
    """澄清问题（仅 CLARIFICATION 意图）"""
    
    general_response: str | None = None
    """通用响应（仅 GENERAL 意图）"""


class Intent(BaseModel):
    """意图"""
    type: IntentType
    reasoning: str


class IntentType(str, Enum):
    """意图类型"""
    DATA_QUERY = "DATA_QUERY"
    CLARIFICATION = "CLARIFICATION"
    GENERAL = "GENERAL"
    IRRELEVANT = "IRRELEVANT"


class ClarificationQuestion(BaseModel):
    """澄清问题"""
    question: str
    options: list[str] | None = None
    field_reference: str | None = None
```

## 元数据模型

```python
class DataSourceMetadata(BaseModel):
    """数据源元数据"""
    
    datasource_id: str
    """数据源 ID"""
    
    datasource_name: str
    """数据源名称"""
    
    dimensions: list[FieldMetadata]
    """维度字段列表"""
    
    measures: list[FieldMetadata]
    """度量字段列表"""


class FieldMetadata(BaseModel):
    """字段元数据"""
    
    field_name: str
    """字段名"""
    
    field_caption: str
    """字段显示名"""
    
    data_type: str
    """数据类型"""
    
    description: str | None = None
    """字段描述"""
    
    sample_values: list[str] | None = None
    """示例值"""
```

## 模型关系图

```
SemanticParseResult
├── restated_question: str
├── intent: Intent
├── semantic_query: SemanticQuery
│   ├── dimensions: list[DimensionField]
│   ├── measures: list[MeasureField]
│   ├── computations: list[Computation]
│   │   ├── target: str
│   │   ├── partition_by: list[str]
│   │   └── operation: Operation
│   │       ├── type: OperationType
│   │       └── params: dict
│   ├── filters: list[Filter]
│   └── sorts: list[Sort]
├── clarification: ClarificationQuestion
└── general_response: str
```
