# 设计文档

## 概述

本设计文档描述如何修复Tableau Assistant查询流水线中的5个测试失败问题。修复方案遵循以下核心原则：

1. **职责清晰**：数据模型定义值的含义，提示模板引导思考流程
2. **普遍知识 vs 特殊知识**：只在代码中定义LLM不知道的系统设计知识
3. **英文表达**：所有description和提示词使用英文
4. **通用规则**：所有描述都是通用的，不针对特定场景

## 架构

### 系统组件

```
User Question
     ↓
Understanding Agent (uses question.py models + understanding.py prompt)
     ↓
QuestionUnderstanding
     ↓
Task Planner Agent (uses query_plan.py models + task_planner.py prompt)
     ↓
QueryPlanningResult
     ↓
Query Builder (generates VizQL API queries)
     ↓
Tableau VizQL API
```

### 修复点分布

1. **question.py** (数据模型)
   - RelativeType枚举注释
   - TimeRange字段description
   - QuerySubQuestion字段description

2. **understanding.py** (提示模板)
   - Step 2添加计数模式分析引导

3. **task_planner_agent.py** (Agent代码)
   - 元数据格式化逻辑

4. **task_planner.py** (提示模板)
   - 映射规则说明

5. **query_builder.py** (查询构建)
   - 日期计算公式生成
   - 排序优先级分配

## 组件和接口

### 1. TimeRange数据模型改进

**文件**: `tableau_assistant/src/models/question.py`

**改进内容**:

#### RelativeType枚举
```python
class RelativeType(str, Enum):
    """Relative time type"""
    CURRENT = "CURRENT"  # Current period to date
    LAST = "LAST"        # Complete previous period
    NEXT = "NEXT"        # Complete next period
    TODATE = "TODATE"    # From period start to today
    LASTN = "LASTN"      # Rolling N periods from today
    NEXTN = "NEXTN"      # Rolling N periods into future
```

#### TimeRange.relative_type字段
```python
relative_type: Optional[RelativeType] = Field(
    None,
    description="""Relative time type.

Usage:
- Include for relative time ranges
- null for absolute time ranges

Values:
- CURRENT: Current period to date
- LAST: Complete previous period
- NEXT: Complete next period  
- TODATE: From period start to today
- LASTN: Rolling N periods from today (requires range_n)
- NEXTN: Rolling N periods into future (requires range_n)"""
)
```

#### TimeRange.range_n字段
```python
range_n: Optional[int] = Field(
    None,
    ge=1,
    description="""Count for relative time ranges.

Usage:
- Required for LASTN/NEXTN relative types
- Represents the number of periods
- null for other relative types

Values: Positive integer (1, 2, 3, ...)"""
)
```

### 2. QuerySubQuestion数据模型改进

**文件**: `tableau_assistant/src/models/question.py`

**改进内容**:

#### 创建DateFunction枚举

```python
class DateFunction(str, Enum):
    """Date function for time-based grouping"""
    YEAR = "YEAR"        # Extract year from date
    QUARTER = "QUARTER"  # Extract quarter from date
    MONTH = "MONTH"      # Extract month from date
    WEEK = "WEEK"        # Extract week from date
    DAY = "DAY"          # Extract day from date
```

#### date_field_functions字段（修改类型为枚举）

```python
date_field_functions: Optional[dict[str, DateFunction]] = Field(
    None,
    description="""Maps date field names to time granularity functions for GROUP BY.

Usage:
- Include date field → Apply time granularity function for grouping
- Exclude date field → Use raw date value
- null or {} → No date functions applied

Values: DateFunction enum (YEAR, QUARTER, MONTH, WEEK, DAY)

Examples:
- "Sales by month" → {"date": DateFunction.MONTH}
- "Revenue per year" → {"date": DateFunction.YEAR}"""
)
```

#### mentioned_date_fields字段

```python
mentioned_date_fields: List[str] = Field(
    default_factory=list,
    description="""Date fields used for time-based grouping (GROUP BY time periods).

Usage:
- Include date fields that partition data into time periods
- Used with date_field_functions to specify granularity

Examples:
- "Sales by month" → ["date"]
- "Revenue per quarter" → ["date"]

Values: Business term strings"""
)
```

#### filter_date_field字段

```python
filter_date_field: Optional[str] = Field(
    None,
    description="""Date field used for time range filtering (WHERE clause with time range).

Usage:
- Include if query filters data by time range
- Used with time_range to specify the range

Examples:
- "Sales in 2024" → "date"
- "Last month revenue" → "date"

Values: Business term string or null"""
)
```

#### mentioned_dimensions字段

```python
mentioned_dimensions: List[str] = Field(
    default_factory=list,
    description="""List of ALL dimension entities identified from query (business terms).

Usage:
- Include ALL dimensions (both grouping and counted)

Examples:
- "Sales by region" → ["region"]
- "How many stores per region?" → ["region", "store"]

Values: Business term strings"""
)
```

#### dimension_aggregations字段
```python
dimension_aggregations: Optional[dict[str, str]] = Field(
    None,
    description="""Maps dimension names to aggregation functions.

Usage:
- Include dimension → Dimension has SQL aggregation
- Exclude dimension → Dimension is for GROUP BY
- null or {} → All dimensions are for GROUP BY

Values: 'COUNTD', 'MAX', 'MIN'

Examples:
- "How many Y per X?" → {"Y": "COUNTD"}
- "Latest Z by X" → {"Z": "MAX"}
- "Earliest Z by X" → {"Z": "MIN"}
- "Sales by X" → {} or null"""
)
```

### 3. Understanding Prompt改进

**文件**: `tableau_assistant/prompts/understanding.py`

**改进内容**:

#### Step 2: 添加计数模式分析引导

```python
Step 2: Determine SQL role for EACH dimension
For each dimension, ask: "What is its SQL role in this query?"
- Analyze query pattern: Is dimension being counted/aggregated?
- Determine role: Aggregated (has SQL function) or Grouped (GROUP BY)
```

#### Step 4: 改进日期字段分析引导

```python
Step 4: Determine date field usage
For each date field, analyze its role:
- Grouping: Used to partition data by time periods (GROUP BY)
- Filtering: Used to filter data by time range (WHERE clause)
- Determine time granularity for grouping if applicable
```

**关键点**: 
- 提示词只引导分析流程，不给具体例子
- LLM通过数据模型的description理解字段含义
- 同一个日期字段可以既用于分组又用于筛选

**日期处理的三种场景**:

1. **按时间分组**（"显示每月的销售额"）:
   ```python
   {
     "mentioned_date_fields": ["日期"],
     "date_field_functions": {"日期": DateFunction.MONTH},
     "filter_date_field": None,
     "time_range": None
   }
   ```

2. **时间范围筛选**（"2024年销售额"）:
   ```python
   {
     "mentioned_date_fields": [],
     "date_field_functions": None,
     "filter_date_field": "日期",
     "time_range": {"type": "absolute", "value": "2024"}
   }
   ```

3. **既分组又筛选**（"2024年每月的销售额"）:
   ```python
   {
     "mentioned_date_fields": ["日期"],
     "date_field_functions": {"日期": DateFunction.MONTH},
     "filter_date_field": "日期",
     "time_range": {"type": "absolute", "value": "2024"}
   }
   ```

### 4. Task Planner Agent元数据格式化

**文件**: `tableau_assistant/src/agents/task_planner_agent.py`

**新增方法**:

```python
def _format_metadata_by_category(self, metadata: DataSourceMetadata) -> str:
    """
    Format metadata grouped by category for LLM input.
    
    Returns formatted string like:
    
    Geographic Dimensions:
    - pro_name (level: 2, samples: ['广东', '上海', '北京'])
    - city_name (level: 3, samples: ['深圳', '广州', '上海'])
    
    Product Dimensions:
    - 分类五级名称 (level: 5, samples: ['商品A', '商品B', '商品C'])
    ...
    """
    # Group fields by category (7 categories):
    # - geographic, temporal, product, customer, organizational, financial, other
    # Format each category section
    # Return formatted string
```

**修改方法**:

在`plan_tasks`方法中，调用新的格式化方法：

```python
async def plan_tasks(...):
    # ... existing code ...
    
    # Format metadata by category
    formatted_metadata = self._format_metadata_by_category(metadata)
    
    # Pass to LLM
    prompt_vars = {
        "metadata": formatted_metadata,
        # ... other vars ...
    }
```

### 5. Task Planner Prompt改进

**文件**: `tableau_assistant/prompts/task_planner.py`

**改进内容**:

在`get_specific_domain_knowledge`方法中更新映射规则：

```python
Mapping rules:
1. **technical_field MUST be exact field name from metadata.fields**
2. Match category first (product/geographic/temporal/organizational)
3. Then match name similarity within category
4. For COUNTD aggregation, prefer fine-grained fields (higher level value)
5. Prefer coarse level (1-2) for grouping unless fine detail needed
```

### 6. Query Builder日期公式修复

**文件**: `tableau_assistant/src/components/query_builder.py`

**数据流说明**:

完整的数据流如下：

1. **Understanding Agent** → `QuestionUnderstanding`
   - `mentioned_date_fields` + `date_field_functions` → 日期维度（用于分组）
   - `filter_date_field` + `time_range` → 日期筛选（用于过滤）

2. **Task Planner Agent** → `QueryPlanningResult`
   - `mentioned_date_fields` → `date_field_intents`（映射业务术语到技术字段）
   - `filter_date_field` → `date_filter_intent`（映射业务术语到技术字段）

3. **Query Builder** → `VizQLQuery`
   - `date_field_intents` → `CalculationField`（日期维度字段）
   - `date_filter_intent` → `QuantitativeDateFilter`（日期筛选条件）

**问题所在**: Query Builder在生成CalculationField和QuantitativeDateFilter时，使用了错误的公式语法。

**问题分析**:

当前生成的公式：
```
TRUNC_MONTH(DATEPARSE('yyyy-MM-dd', [日期]))
```

错误信息：`The formula for calculation is invalid.`

**根本原因**: Tableau VizQL API不支持嵌套函数调用。

**正确的做法**（参考test_string_date_simple.py）:

对于STRING类型的日期字段，应该使用单层函数：

```python
# ✓ 正确：使用MONTH函数提取月份
CalculationField(
    fieldCaption="MONTH_日期",
    calculation="MONTH(DATEPARSE('yyyy-MM-dd', [日期]))"
)

# ✓ 正确：日期筛选使用DATEPARSE
QuantitativeDateFilter(
    field=FilterField(calculation="DATEPARSE('yyyy-MM-dd', [日期])"),
    filterType="QUANTITATIVE_DATE",
    quantitativeFilterType="RANGE",
    minDate="2024-01-01",
    maxDate="2024-12-31"
)

# ✗ 错误：嵌套TRUNC_MONTH和DATEPARSE
calculation="TRUNC_MONTH(DATEPARSE('yyyy-MM-dd', [日期]))"
```

**修复方案**:

根据日期字段的dataType选择不同的处理方式：

#### STRING类型日期字段
```python
# 日期维度（提取月份）
CalculationField(
    fieldCaption="MONTH_日期",
    calculation="MONTH(DATEPARSE('yyyy-MM-dd', [日期]))"
)

# 日期筛选
QuantitativeDateFilter(
    field=FilterField(calculation="DATEPARSE('yyyy-MM-dd', [日期])"),
    filterType="QUANTITATIVE_DATE",
    quantitativeFilterType="RANGE",
    minDate="2024-01-01",
    maxDate="2024-12-31"
)
```

#### DATE/DATETIME类型日期字段
```python
# 日期维度（提取月份）
CalculationField(
    fieldCaption="MONTH_日期",
    calculation="MONTH([日期])"
)

# 日期筛选
QuantitativeDateFilter(
    field=FilterField(fieldCaption="日期"),
    filterType="QUANTITATIVE_DATE",
    quantitativeFilterType="RANGE",
    minDate="2024-01-01",
    maxDate="2024-12-31"
)
```

**关键规则**:
1. 对于日期维度（date_field_functions），使用MONTH/YEAR等提取函数，而不是TRUNC_*函数
2. 对于日期筛选（date_filter_intent），直接使用DATEPARSE转换后的日期进行范围筛选
3. 不使用嵌套函数调用
4. 根据字段的dataType判断是否需要DATEPARSE转换

### 7. Query Builder排序优先级修复

**文件**: `tableau_assistant/src/components/query_builder.py`

**问题**: 多个字段使用相同的sortPriority值

**修复方案**:

```python
def _assign_sort_priorities(self, fields_with_sort: List[FieldSpec]) -> None:
    """
    Assign unique sortPriority values to fields.
    
    Rules:
    - Measure fields get priority 0 (highest)
    - Dimension fields get priority 1, 2, 3... (lower)
    - Each field gets unique priority value
    """
    priority = 0
    
    # First assign to measures
    for field in fields_with_sort:
        if field.is_measure and field.sort_direction:
            field.sort_priority = priority
            priority += 1
    
    # Then assign to dimensions
    for field in fields_with_sort:
        if not field.is_measure and field.sort_direction:
            field.sort_priority = priority
            priority += 1
```

## 数据模型

### TimeRange
```python
class TimeRange(BaseModel):
    type: Optional[TimeRangeType]
    value: Optional[str]
    relative_type: Optional[RelativeType]  # Enhanced description
    period_type: Optional[PeriodType]
    range_n: Optional[int]  # Enhanced description
```

### QuerySubQuestion
```python
class QuerySubQuestion(SubQuestionBase):
    execution_type: Literal["query"] = "query"
    mentioned_dimensions: List[str]  # Enhanced description
    dimension_aggregations: Optional[dict[str, str]]  # Enhanced description
    mentioned_measures: List[str]
    measure_aggregations: Optional[dict[str, str]]
    # ... other fields ...
```

## 错误处理

### 日期公式验证

在Query Builder中添加验证逻辑：

```python
def _validate_date_calculation(self, calculation: str) -> bool:
    """
    Validate date calculation formula before sending to API.
    
    Returns:
        True if valid, False otherwise
    """
    # Check for known invalid patterns
    # Validate syntax
    # Return validation result
```

### 排序优先级验证

```python
def _validate_sort_priorities(self, fields: List[FieldSpec]) -> None:
    """
    Validate that all sortPriority values are unique.
    
    Raises:
        ValueError if duplicate priorities found
    """
    priorities = [f.sort_priority for f in fields if f.sort_priority is not None]
    if len(priorities) != len(set(priorities)):
        raise ValueError("Duplicate sortPriority values found")
```

## 测试策略

### 单元测试

1. **test_time_range_model.py**
   - 测试RelativeType枚举值的含义
   - 测试TimeRange字段的validation

2. **test_query_subquestion_model.py**
   - 测试mentioned_dimensions包含所有维度
   - 测试dimension_aggregations只包含被聚合的维度

3. **test_metadata_formatting.py**
   - 测试元数据按category分组
   - 测试格式化输出的正确性

4. **test_query_builder_dates.py**
   - 测试日期公式生成
   - 测试日期公式验证

5. **test_query_builder_sorting.py**
   - 测试排序优先级分配
   - 测试排序优先级验证

### 集成测试

使用现有的`test_complete_pipeline.py`，重点测试：

1. **date_filter_relative**: 相对日期筛选
2. **date_dimension**: 日期维度分组
3. **counted_dimension**: 计数查询
4. **mixed_dimensions**: 混合维度计数
5. **diagnostic**: TopN排序查询

## 实现顺序

1. **Phase 1**: 数据模型改进（需求1、2）
   - 修改question.py中的RelativeType、TimeRange、QuerySubQuestion
   - 运行单元测试验证

2. **Phase 2**: 提示模板改进（需求2）
   - 修改understanding.py的Step 2
   - 运行集成测试验证counted_dimension

3. **Phase 3**: Task Planner改进（需求3）
   - 实现元数据格式化方法
   - 修改task_planner.py的映射规则
   - 运行集成测试验证mixed_dimensions

4. **Phase 4**: Query Builder修复（需求4、5）
   - 调研并修复日期公式生成
   - 实现排序优先级分配逻辑
   - 运行集成测试验证date_filter_relative、date_dimension、diagnostic

5. **Phase 5**: 完整测试
   - 运行所有15个测试用例
   - 确认所有测试通过

## 性能考虑

- 元数据格式化是一次性操作，不影响性能
- 排序优先级分配是O(n)操作，n为字段数量，通常很小
- 日期公式验证是简单的字符串检查，性能影响可忽略

## 安全考虑

- 所有用户输入通过LLM处理，已有安全边界
- 日期公式验证防止注入攻击
- 排序优先级验证防止API错误

## 部署考虑

- 所有修改都是代码级别，无需数据库迁移
- 无需配置文件更改
- 可以逐步部署，每个Phase独立
