# 设计文档

## 概述

本设计文档描述如何修复 Tableau AI 分析助手中的 LLM 输出验证错误。核心策略是通过增强 Prompt 思维链和优化数据模型来提高 LLM 输出的准确性,而非添加后处理逻辑或模糊匹配。

**设计原则:**
1. **Schema优先**: 让 Field description 承担主要的说明工作
2. **思维链引导**: Prompt 提供 Schema 无法表达的决策逻辑
3. **约束性语言**: 使用 MUST、CRITICAL 等强制性词汇
4. **通用性规则**: 避免具体示例,使用可泛化的判断标准

## 架构

### 当前架构

```
User Question
    ↓
Understanding Agent (understanding.py)
    ↓ QuestionUnderstanding
Task Planner Agent (task_planner.py)
    ↓ QueryPlanningResult
Query Builder
    ↓ VizQL Query
Tableau API
```

### 修改点

```
1. understanding.py prompt
   - 增强探索性查询处理的思维链
   - 添加 processing_type 选择指导

2. task_planner.py prompt
   - 添加 Intent 类型选择的思维链步骤
   - 强化字段映射验证的约束性语言

3. intent.py 数据模型
   - 增强 Field description 说明
   - 优化枚举值的使用场景描述

4. question.py 数据模型
   - 扩展 TimeRange 支持日期范围
   - 添加 start_date 和 end_date 字段
```

## 组件和接口

### 1. Understanding Prompt 增强

**文件**: `tableau_assistant/prompts/understanding.py`

**修改内容**:

#### 1.1 Exploratory Question Handling Chain

Add to `get_specific_domain_knowledge()` thought chain:

```python
Step X: Handle exploratory questions
- Identify exploratory intent: Questions asking "why", "insights", "patterns"
- Set needs_exploration flag: Mark as true for exploratory questions
- Select starting dimensions: Choose 2-3 coarse-grained dimensions from metadata
  * Prefer level 1-2 fields (coarse granularity)
  * Prioritize semantic categories: Geographic, Temporal, Categorical
- Select starting measures: Choose 2-3 core measures from metadata
  * Prefer commonly used business metrics
  * Prioritize semantic categories: Revenue, Profit, Quantity
```



### 2. Task Planner Prompt 增强

**文件**: `tableau_assistant/prompts/task_planner.py`

**修改内容**:

#### 2.1 Intent Type Selection Chain

Add new Step 2 after Step 1 in `get_specific_domain_knowledge()`:

```python
Step 2: Determine Intent type for each entity
- Analyze entity characteristics: What is the nature of this field?
- Select appropriate Intent type:
  * Date field with time granularity (YEAR/MONTH/QUARTER/WEEK/DAY):
    → Use DateFieldIntent
    → Include date_function field
  * Regular dimension (for grouping or counting):
    → Use DimensionIntent
    → NO date_function field allowed
    → Include aggregation only if counting (COUNTD)
  * Measure (always aggregated):
    → Use MeasureIntent
    → MUST include aggregation field
- CRITICAL: date_function can ONLY appear in DateFieldIntent, never in DimensionIntent
```

#### 2.2 Field Mapping Validation Enhancement

Modify existing Step 1 to strengthen validation constraints:

```python
Step 1: For each business term, find technical field from metadata
- Review available fields: Examine metadata.fields list carefully
- Identify semantic match: Find field with matching business meaning
- Verify field existence: CRITICAL - technical_field MUST be exact name from metadata.fields
- If no exact match: Choose semantically closest field from metadata
- Double-check: Confirm selected field appears in metadata.fields list
```

Modify Mapping rules #1:

```python
1. **CRITICAL: technical_field MUST be exact field name from metadata.fields**
   - Verify field exists before using it
   - Use semantic understanding to find matching field
   - Never use business term directly as technical_field
```

### 3. Intent 数据模型增强

**文件**: `tableau_assistant/src/models/intent.py`

**修改内容**:

#### 3.1 DimensionIntent Field Description Enhancement

Emphasize model-specific selection rules in `aggregation` field description:

```python
aggregation: Optional[Literal["COUNTD", "MIN", "MAX"]] = Field(
    None,
    description="""Aggregation function for dimension.

Usage:
- Use null when dimension is for grouping (GROUP BY)
- Use 'COUNTD' when counting distinct values
- Use 'MIN'/'MAX' when finding min/max values

CRITICAL: For date fields with time granularity (YEAR/MONTH/QUARTER), use DateFieldIntent instead.
"""
)
```

#### 3.2 DateFieldIntent Docstring Enhancement

Emphasize distinction from DimensionIntent in class docstring:

```python
class DateFieldIntent(BaseModel):
    """
    Date field intent for time-based grouping.
    
    Use for date fields with time granularity transformation (YEAR/MONTH/QUARTER/WEEK/DAY).
    
    Distinction from DimensionIntent:
    - DateFieldIntent: Date field + time function
    - DimensionIntent: Regular dimension (grouping or counting)
    
    Distinction from DateFilterIntent:
    - DateFieldIntent: For grouping (GROUP BY)
    - DateFilterIntent: For filtering (WHERE)
    """
```

### 4. PostProcessing Data Model Enhancement

**File**: `tableau_assistant/src/models/question.py`

**Modification**:

Enhance `processing_type` field description with model-specific selection rules:

```python
processing_type: ProcessingType = Field(
    description="""Type of data processing operation.

Usage:
- Use 'yoy' when comparing across years
- Use 'mom' when comparing across months  
- Use 'growth_rate' when calculating growth over time
- Use 'percentage' when calculating proportions or ratios
- Use 'custom' when none of above types apply (requires calculation_formula)
"""
)
```

### 5. TimeRange 数据模型扩展

**文件**: `tableau_assistant/src/models/question.py`

**修改内容**:

扩展 `TimeRange` 模型支持日期范围:

```python
class TimeRange(BaseModel):
    """
    时间范围规范
    
    支持两种格式:
    1. 单个值: 使用 value 字段(如 "2024", "2024-09")
    2. 日期范围: 使用 start_date 和 end_date 字段
    """
    model_config = ConfigDict(extra="forbid")
    
    type: Literal["absolute", "relative"] = Field(
        description="""Time range type.
        
- 'absolute': Specific date or date range
- 'relative': Relative time period (e.g., last month, last quarter)
"""
    )
    
    # 单个值格式
    value: Optional[str] = Field(
        None,
        description="""Single time value for absolute or relative type.

For absolute type:
- Year: "2024"
- Year-Month: "2024-09"
- Year-Quarter: "2024-Q3"

For relative type:
- "last_month", "last_quarter", "last_year"
- "recent_7_days", "recent_30_days"

Use this field when specifying a single time point or period.
Use start_date/end_date when specifying a date range.
"""
    )
    
    # 日期范围格式
    start_date: Optional[str] = Field(
        None,
        description="""Start date for date range (absolute type only).

Format: "YYYY-MM-DD"
Example: "2024-01-01"

Use with end_date to specify a date range.
Example: "2024年1月到3月" → start_date="2024-01-01", end_date="2024-03-31"
"""
    )
    
    end_date: Optional[str] = Field(
        None,
        description="""End date for date range (absolute type only).

Format: "YYYY-MM-DD"
Example: "2024-03-31"

Use with start_date to specify a date range.
"""
    )
    
    # 相对时间类型
    relative_type: Optional[Literal["last", "recent", "current", "next"]] = Field(
        None,
        description="""Relative time type (for relative type only).

- 'last': Previous period (last month, last year)
- 'recent': Recent period (recent 7 days, recent 30 days)
- 'current': Current period (this month, this year)
- 'next': Next period (next month, next year)
"""
    )
    
    period_type: Optional[Literal["day", "week", "month", "quarter", "year"]] = Field(
        None,
        description="""Period type (for relative type only).

Specifies the granularity of the relative time period.
"""
    )
    
    range_n: Optional[int] = Field(
        None,
        ge=1,
        description="""Number of periods (for relative type only).

Example: "recent 7 days" → range_n=7, period_type="day"
"""
    )
```

## 数据模型

### 修改后的模型关系

```
QuestionUnderstanding
├── sub_questions[]
│   ├── mentioned_dimensions[]
│   ├── mentioned_measures[]
│   ├── mentioned_date_fields[]
│   ├── date_field_functions{}  ← 指导生成 DateFieldIntent
│   ├── dimension_aggregations{}  ← 指导生成 DimensionIntent.aggregation
│   ├── measure_aggregations{}  ← 指导生成 MeasureIntent.aggregation
│   ├── time_range: TimeRange  ← 扩展支持 start_date/end_date
│   └── needs_exploration: bool  ← 探索性查询标记

QueryPlanningResult
├── subtasks[]
│   ├── dimension_intents[]  ← 不包含 date_function
│   ├── measure_intents[]
│   ├── date_field_intents[]  ← 包含 date_function
│   └── date_filter_intent
│       └── time_range: TimeRange  ← 支持范围格式
```

## 错误处理

### 验证错误的根本原因

| 错误类型 | 根本原因 | 修复位置 | 修复方法 |
|---------|---------|---------|---------|
| date_function 位置错误 | 思维链缺少 Intent 类型选择指导 | task_planner.py | 添加 Step 2 指导 Intent 选择 |
| 字段映射到不存在的字段 | 思维链验证步骤不够强 | task_planner.py | 强化验证约束,使用 CRITICAL 关键词 |
| 枚举值不匹配 | Field description 不够清晰 | question.py | 详细说明每个枚举值的使用场景 |
| 日期范围解析失败 | TimeRange 模型不支持范围 | question.py | 添加 start_date 和 end_date 字段 |
| 探索性查询失败 | 思维链缺少字段选择指导 | understanding.py | 添加探索性查询处理步骤 |

### 错误预防机制

1. **思维链验证**: 在关键步骤使用约束性语言(MUST、CRITICAL)
2. **Field Description**: 详细说明字段用途和约束
3. **模型扩展**: 支持更多数据格式(如日期范围)
4. **示例避免**: 不在 Prompt 中硬编码具体示例

## 测试策略

### 单元测试

针对每个修复点创建测试用例:

1. **Intent 类型选择测试**
   - 输入: "显示每月的销售额"
   - 预期: 生成 DateFieldIntent with date_function='MONTH'
   - 验证: dimension_intents 中不包含 date_function

2. **字段映射验证测试**
   - 输入: "总销售额是多少?"
   - 预期: technical_field 为 "netplamt" 或 "收入"
   - 验证: technical_field 存在于 metadata.fields

3. **枚举值选择测试**
   - 输入: "2024年和2023年的销售额对比"
   - 预期: processing_type='yoy'
   - 验证: 不是 'comparison' 或其他无效值

4. **日期范围解析测试**
   - 输入: "2024年1月到3月的销售额"
   - 预期: start_date="2024-01-01", end_date="2024-03-31"
   - 验证: 不是 value="2024-01-01/2024-03-31"

5. **探索性查询测试**
   - 输入: "销售数据有什么洞察?"
   - 预期: needs_exploration=true, 包含 2-3 个维度和度量
   - 验证: dimension_intents 和 measure_intents 不为空

### 集成测试

使用现有的 35 个测试用例验证修复效果:

**目标指标:**
- 执行成功率: 从 74.3% 提升到 > 90%
- 验证通过率: 从 45.7% 提升到 > 80%

**重点测试用例:**
- `date_dimension_and_filter`: 验证 DateFieldIntent 生成
- `aggregation`: 验证字段映射准确性
- `edge_yoy`: 验证枚举值选择
- `edge_date_range`: 验证日期范围解析
- `exploration_open`: 验证探索性查询处理

## 实施计划

### Phase 1: Prompt Enhancement (Priority: High)

1. Modify `understanding.py`
   - Add exploratory question handling chain
   - Use coarse-grained fields (level 1-2) for exploration

2. Modify `task_planner.py`
   - Add Intent type selection chain
   - Strengthen field mapping validation constraints

### Phase 2: Data Model Optimization (Priority: High)

1. Modify `intent.py`
   - Enhance DimensionIntent Field description
   - Enhance DateFieldIntent docstring
   - Focus on Usage and Values, avoid implementation details

2. Modify `question.py`
   - Extend TimeRange model with start_date/end_date
   - Enhance processing_type Field description
   - Use concise format without examples

### Phase 3: Testing and Validation (Priority: Medium)

1. Run unit tests for each fix
2. Run complete 35 test cases
3. Analyze failures and iterate

### Phase 4: Documentation Update (Priority: Low)

1. Update Prompt design documentation
2. Update data model documentation
3. Add best practices guide
