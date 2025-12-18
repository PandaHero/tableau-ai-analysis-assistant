# 附件C：数据模型详细定义

## 概述

本文档定义了语义层的完整数据模型，所有模型都是平台无关的。

## Step 1 相关模型

```python
class Step1Output(BaseModel):
    """Step 1 输出"""
    
    # ===== 核心输出 =====
    restated_question: str
    """重述后的完整问题（自然语言）"""
    
    # ===== 结构化输出（用于 Step 2 验证） =====
    what: What
    """目标（度量）"""
    
    where: Where
    """范围（维度 + 筛选）"""
    
    how_type: HowType
    """计算类型"""
    
    # ===== 意图分类 =====
    intent: Intent
    """意图分类"""


class What(BaseModel):
    """What - 目标"""
    measures: list[MeasureSpec]


class MeasureSpec(BaseModel):
    """度量规格"""
    field: str
    """字段名（业务术语）"""
    
    aggregation: str = "SUM"
    """聚合方式"""


class Where(BaseModel):
    """Where - 范围"""
    dimensions: list[DimensionSpec]
    filters: list[FilterSpec]


class DimensionSpec(BaseModel):
    """维度规格"""
    field: str
    """字段名"""
    
    granularity: str | None = None
    """日期粒度（如 YEAR, MONTH, DAY）"""


class FilterSpec(BaseModel):
    """筛选规格"""
    field: str
    type: str  # SET, DATE_RANGE, NUMERIC_RANGE, TEXT_MATCH
    values: list | dict


class HowType(str, Enum):
    """操作类型"""
    SIMPLE = "SIMPLE"           # 简单聚合
    RANKING = "RANKING"         # 排名类
    CUMULATIVE = "CUMULATIVE"   # 累计类
    COMPARISON = "COMPARISON"   # 比较类（占比、同比环比）
    GRANULARITY = "GRANULARITY" # 粒度类（固定粒度聚合）


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
```

## Step 2 相关模型

```python
class Step2Output(BaseModel):
    """Step 2 输出"""
    
    computations: list[Computation]
    """计算定义列表"""
    
    reasoning: str
    """推理过程"""
    
    validation: Step2Validation
    """自我验证结果"""


class Step2Validation(BaseModel):
    """Step 2 自我验证结果"""
    
    target_check: ValidationCheck
    """target 验证"""
    
    partition_by_check: ValidationCheck
    """partition_by 验证"""
    
    operation_check: ValidationCheck
    """operation.type 验证"""
    
    all_valid: bool
    """所有检查是否都通过"""
    
    inconsistencies: list[str]
    """发现的不一致之处"""


class ValidationCheck(BaseModel):
    """验证检查"""
    
    inferred_value: str | list[str]
    """从 restated_question 推断的值"""
    
    reference_value: str | list[str]
    """Step 1 结构化输出中的值"""
    
    is_match: bool
    """是否匹配"""
    
    note: str
    """说明"""
```

## Observer 相关模型

```python
class ObserverInput(BaseModel):
    """Observer 输入"""
    
    original_question: str
    """原始问题（用于回溯）"""
    
    step1: Step1Output
    """Step 1 输出"""
    
    step2: Step2Output
    """Step 2 输出"""


class ObserverOutput(BaseModel):
    """Observer 输出"""
    
    is_consistent: bool
    """Step 1 和 Step 2 是否一致"""
    
    conflicts: list[Conflict]
    """发现的冲突"""
    
    decision: ObserverDecision
    """Observer 的决策"""
    
    correction: Correction | None = None
    """修正内容（仅当 decision=CORRECT）"""
    
    final_result: Computation | None = None
    """最终结果"""


class Conflict(BaseModel):
    """冲突"""
    
    aspect: str
    """冲突的方面（restatement/structure/semantic）"""
    
    description: str
    """冲突描述"""
    
    step1_value: str
    """Step 1 的值"""
    
    step2_value: str
    """Step 2 的值"""


class Correction(BaseModel):
    """修正"""
    
    field: str
    """要修正的字段"""
    
    original_value: str | list[str]
    """原值"""
    
    corrected_value: str | list[str]
    """修正值"""
    
    reason: str
    """修正原因"""


class ObserverDecision(str, Enum):
    """Observer 决策"""
    ACCEPT = "ACCEPT"       # 一致，接受 Step 2 结果
    CORRECT = "CORRECT"     # 有小冲突，Observer 修正
    RETRY = "RETRY"         # 有大冲突，需要重新推理
    CLARIFY = "CLARIFY"     # 无法判断，需要用户澄清
```

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
    """计算操作类型枚举
    
    这是通用模型的核心枚举，描述用户想要的计算操作。
    平台适配器根据此类型转换为平台特定实现。
    """
    
    # ========== 排名类 ==========
    RANK = "RANK"
    """排名（1, 2, 3, ...）"""
    
    DENSE_RANK = "DENSE_RANK"
    """密集排名（1, 2, 2, 3, ...）"""
    
    # ========== 累计类 ==========
    RUNNING_SUM = "RUNNING_SUM"
    """累计求和"""
    
    RUNNING_AVG = "RUNNING_AVG"
    """累计平均"""
    
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
    """固定粒度聚合（不受视图影响）
    
    平台适配器根据 partition_by 与视图维度的关系，
    自动决定使用 Tableau 的 FIXED/INCLUDE/EXCLUDE。
    """
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


class TopNFilter(Filter):
    """Top N 筛选"""
    filter_type: Literal[FilterType.TOP_N] = FilterType.TOP_N
    
    n: int
    """返回前 N 条"""
    
    by_field: str
    """按哪个字段排序"""
    
    direction: SortDirection = SortDirection.DESC
    """排序方向（DESC = 前 N 名，ASC = 后 N 名）"""
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

## 验证和结果模型

```python
class ValidationResult(BaseModel):
    """验证结果"""
    
    is_valid: bool
    """是否验证通过"""
    
    errors: list[ValidationError] = []
    """错误列表"""
    
    warnings: list[str] = []
    """警告列表"""
    
    auto_fixed: bool = False
    """是否进行了自动修正"""


class ValidationError(BaseModel):
    """验证错误"""
    
    error_type: str
    """错误类型"""
    
    field_path: str
    """错误字段路径"""
    
    message: str
    """错误消息"""
    
    suggestion: str | None = None
    """修复建议"""


class QueryResult(BaseModel):
    """查询结果"""
    
    columns: list[ColumnInfo]
    """列信息"""
    
    rows: list[dict]
    """数据行"""
    
    row_count: int
    """行数"""
    
    execution_time_ms: int | None = None
    """执行时间（毫秒）"""


class ColumnInfo(BaseModel):
    """列信息"""
    
    name: str
    """列名"""
    
    data_type: str
    """数据类型"""
    
    is_dimension: bool = False
    """是否是维度"""
    
    is_measure: bool = False
    """是否是度量"""
    
    is_computation: bool = False
    """是否是计算字段"""
```

## 模型关系图

```
SemanticParseResult
├── restated_question: str
├── intent: Intent
│   ├── type: IntentType (DATA_QUERY | CLARIFICATION | GENERAL | IRRELEVANT)
│   └── reasoning: str
├── semantic_query: SemanticQuery (仅 DATA_QUERY)
│   ├── dimensions: list[DimensionField]
│   ├── measures: list[MeasureField]
│   ├── computations: list[Computation]
│   │   ├── target: str
│   │   ├── partition_by: list[str]
│   │   ├── operation: Operation
│   │   │   ├── type: OperationType
│   │   │   └── params: dict
│   │   └── alias: str | None
│   ├── filters: list[Filter]
│   │   ├── SetFilter
│   │   ├── DateRangeFilter
│   │   ├── NumericRangeFilter
│   │   ├── TextMatchFilter
│   │   └── TopNFilter
│   ├── sorts: list[Sort]
│   └── row_limit: int | None
├── clarification: ClarificationQuestion (仅 CLARIFICATION)
│   ├── question: str
│   ├── options: list[str] | None
│   └── field_reference: str | None
└── general_response: str (仅 GENERAL)
```

## LLM 组合数据流

```
用户问题 + 历史对话 + 元数据
        │
        ▼
┌───────────────────────────────────────────────────────────────┐
│  Step 1: 语义理解与问题重述                                    │
│                                                               │
│  输出: Step1Output                                            │
│  ├── restated_question ──────────────────────────────────────┼──→ Step 2 主要输入
│  ├── what ───────────────────────────────────────────────────┼──→ Step 2 验证 target
│  ├── where ──────────────────────────────────────────────────┼──→ Step 2 验证 partition_by
│  ├── how_type ───────────────────────────────────────────────┼──→ Step 2 验证 operation.type
│  └── intent ─────────────────────────────────────────────────┼──→ 决定后续流程
└───────────────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────────┐
│                    intent.type == ?                            │
├───────────────┬───────────────┬───────────────┬───────────────┤
│  DATA_QUERY   │ CLARIFICATION │    GENERAL    │  IRRELEVANT   │
└───────┬───────┴───────┬───────┴───────┬───────┴───────┬───────┘
        │               │               │               │
        ▼               ▼               ▼               ▼
  继续处理        生成澄清问题     生成通用响应      拒绝处理
        │               │               │               │
        │               ▼               ▼               ▼
        │         返回 clarification  返回 general_response  返回提示
        │
        ▼
    how_type == SIMPLE?
        │
    ┌───┴───┐
   Yes      No
    │       │
    ▼       ▼
  直接   ┌───────────────────────────────────────────────────────┐
  构建   │  Step 2: 计算推理与自我验证                            │
  查询   │                                                       │
         │  输出: Step2Output                                    │
         │  ├── computations ────────────────────────────────────┼──→ 计算定义
         │  ├── reasoning                                        │
         │  └── validation                                       │
         │      ├── target_check                                 │
         │      ├── partition_by_check                           │
         │      ├── operation_check                              │
         │      ├── all_valid ───────────────────────────────────┼──→ 决定是否需要 Observer
         │      └── inconsistencies                              │
         └───────────────────────────────────────────────────────┘
                │
                ▼
         validation.all_valid?
                │
            ┌───┴───┐
           Yes      No
            │       │
            ▼       ▼
         输出   ┌───────────────────────────────────────────────┐
         结果   │  Observer: 一致性检查（按需介入）              │
               │                                                │
               │  输出: ObserverOutput                          │
               │  ├── is_consistent                             │
               │  ├── conflicts                                 │
               │  ├── decision ─────────────────────────────────┼──→ ACCEPT/CORRECT/RETRY/CLARIFY
               │  ├── correction                                │
               │  └── final_result ─────────────────────────────┼──→ 最终计算定义
               └────────────────────────────────────────────────┘
                        │
                        ▼
                ┌───────────────┐
                │ ACCEPT/CORRECT │ → 输出结果
                │ RETRY          │ → 重新执行 Step 1/2
                │ CLARIFY        │ → 请求用户澄清
                └───────────────┘
```

## 验证规则映射

### operation_check 的映射关系

```python
OPERATION_TYPE_MAPPING = {
    HowType.RANKING: [
        OperationType.RANK, 
        OperationType.DENSE_RANK
    ],
    HowType.CUMULATIVE: [
        OperationType.RUNNING_SUM, 
        OperationType.RUNNING_AVG, 
        OperationType.MOVING_AVG, 
        OperationType.MOVING_SUM
    ],
    HowType.COMPARISON: [
        OperationType.PERCENT, 
        OperationType.DIFFERENCE, 
        OperationType.GROWTH_RATE, 
        OperationType.YEAR_AGO, 
        OperationType.PERIOD_AGO
    ],
    HowType.GRANULARITY: [
        OperationType.FIXED
    ],
}

# 验证逻辑
is_match = operation.type in OPERATION_TYPE_MAPPING[how_type]
```

### 分区推断规则

| restated_question 中的关键词 | partition_by | 说明 |
|---------------------------|--------------|------|
| "排名"（无分区词） | [] | 全局排名 |
| "每月排名"、"月内排名" | [时间维度] | 按月分区 |
| "每省排名" | [省份] | 按省份分区 |
| "占全国比例"、"占总体" | [] | 分母是全局 |
| "占当月比例" | [时间维度] | 分母是当月 |
| "同比"、"去年同期" | [非时间维度] | 沿时间比较 |
| "累计"（无分区词） | [] | 全局累计 |
| "每省累计" | [省份] | 按省份分区累计 |
