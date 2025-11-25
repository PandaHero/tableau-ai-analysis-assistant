"""
Intent Data Models (Intermediate Layer)

Output by Task Planning Agent, contains field mapping and query detail identification.
Intent models serve as the bridge between business layer and execution layer.

Contains:
1. DimensionIntent - Dimension intent (dimension field mapping + optional aggregation + sorting)
2. MeasureIntent - Measure intent (measure field mapping + aggregation + sorting)
3. DateFieldIntent - Date field intent (date field mapping + date function + sorting)
4. DateFilterIntent - Date filter intent (date field mapping + time range)
5. FilterIntent - Non-date filter intent (field mapping + filter conditions)
6. TopNIntent - TopN intent (field mapping + TopN configuration)

Design principles:
- Dimensions, measures, and date fields are defined separately, corresponding to the role field in metadata
- Dimensions can use COUNT, COUNTD aggregation functions
- Measures must use aggregation functions (SUM, AVG, MIN, MAX, etc.)
- Date fields can use date functions (YEAR, MONTH, QUARTER, etc.)
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Union, List, Literal
from tableau_assistant.src.models.question import TimeRange, DateRequirements


# ============= 字段 Intent 模型 =============

class DimensionIntent(BaseModel):
    """
    Dimension Intent - For categorical/grouping fields
    
    Use for fields that categorize or group data (e.g., region, product category, customer name).
    Corresponds to metadata fields with role="dimension".
    
    Usage scenarios:
    - Grouping data by categories (GROUP BY in SQL)
    - Counting distinct values (COUNTD aggregation)
    - Aggregating dimension values (MIN/MAX aggregation)
    
    Distinction from DateFieldIntent:
    - DimensionIntent: Regular categorical fields, NO date_function field
    - DateFieldIntent: Date fields requiring time granularity functions (YEAR/MONTH/etc)
    
    CRITICAL: date_function field does NOT exist in DimensionIntent. For date fields with time 
    functions, use DateFieldIntent instead.
    """
    model_config = ConfigDict(extra="forbid")
    
    business_term: str = Field(
        description="""Business term from user question.

Usage:
- Store original business term mentioned by user
- Used for field mapping and display

Values: Business term string"""
    )
    
    technical_field: str = Field(
        description="""Technical field name from metadata.

Usage:
- Must be exact field name from metadata.fields
- Used for query construction

Values: Technical field name string"""
    )
    
    field_data_type: str = Field(
        description="""Data type of the field.

Usage:
- Specify field data type from metadata
- Used for validation and query construction

Values: 'STRING', 'REAL', 'INTEGER', 'BOOLEAN', 'DATE'"""
    )
    
    aggregation: Optional[Literal["COUNTD", "MIN", "MAX"]] = Field(
        None,
        description="""Aggregation function for dimension.

Usage:
- null: Grouping dimension (GROUP BY) - field used for categorization
- 'COUNTD': Count distinct values - field used for counting unique items
- 'MIN'/'MAX': Aggregate dimension values - field used for finding min/max

Selection guide:
- Question asks "how many distinct X": Use COUNTD
- Question asks "group by X" or "by X": Use null (grouping)
- Question asks "earliest/latest X": Use MIN/MAX

CRITICAL: For date fields with time functions (YEAR/MONTH/etc), use DateFieldIntent instead.
DimensionIntent is ONLY for regular categorical fields.
"""
    )
    
    sort_direction: Optional[Literal["ASC", "DESC"]] = Field(
        None,
        description="""Sort direction for this dimension.

Usage:
- Include if dimension needs sorting
- null if no sorting required"""
    )
    
    sort_priority: Optional[int] = Field(
        None,
        ge=0,
        description="""Sort priority for multi-field sorting.

Usage:
- Include if multiple fields need sorting
- Each field MUST have UNIQUE sort_priority value (cannot duplicate)
- Lower number = higher priority (0 is highest)
- null if no sorting or single field sort

Values: Non-negative integer or null (MUST be unique across all fields)"""
    )


class MeasureIntent(BaseModel):
    """
    Measure Intent - For numeric fields requiring aggregation
    
    Use for numeric fields that need aggregation (e.g., sales amount, profit, quantity).
    Corresponds to metadata fields with role="measure".
    
    Usage scenarios:
    - Calculating totals: SUM aggregation
    - Calculating averages: AVG aggregation
    - Finding extremes: MIN/MAX aggregation
    - Counting records: COUNT aggregation
    
    CRITICAL: aggregation field is REQUIRED for all measures. Measures cannot be used 
    without aggregation.
    """
    model_config = ConfigDict(extra="forbid")
    
    business_term: str = Field(
        description="""Business term from user question.

Usage:
- Store original business term mentioned by user
- Used for field mapping and display

Values: Business term string"""
    )
    
    technical_field: str = Field(
        description="""Technical field name from metadata.

Usage:
- Must be exact field name from metadata.fields
- Used for query construction

Values: Technical field name string"""
    )
    
    field_data_type: str = Field(
        description="""Data type of the field.

Usage:
- Specify field data type from metadata
- Used for validation and query construction

Values: 'STRING', 'REAL', 'INTEGER', 'BOOLEAN', 'DATE'"""
    )
    
    aggregation: Literal["SUM", "AVG", "MEDIAN", "MIN", "MAX", "STDEV", "VAR", "COUNT", "COUNTD"] = Field(
        description="""Aggregation function for measure.

Usage:
- MUST specify aggregation for all measures
- Use value from sub-question's measure_aggregations dict
- 'SUM' is the default choice for most cases"""
    )
    
    sort_direction: Optional[Literal["ASC", "DESC"]] = Field(
        None,
        description="""Sort direction for this measure.

Usage:
- Include if measure needs sorting
- null if no sorting required"""
    )
    
    sort_priority: Optional[int] = Field(
        None,
        ge=0,
        description="""Sort priority for multi-field sorting.

Usage:
- Include if multiple fields need sorting
- Lower number = higher priority (0 is highest)
- null if no sorting or single field sort

Values: Non-negative integer or null"""
    )


class DateFieldIntent(BaseModel):
    """
    Date Field Intent - For time-based grouping with granularity functions
    
    Use for date fields that require time granularity transformation for grouping 
    (e.g., group by year, by month, by quarter).
    
    Usage scenarios:
    - Time-based grouping: Questions asking for data "by year", "by month", "by quarter"
    - Requires date_function: YEAR, MONTH, QUARTER, WEEK, or DAY
    
    Distinction from DimensionIntent:
    - DateFieldIntent: Date fields WITH time function (GROUP BY YEAR(date))
    - DimensionIntent: Regular categorical fields WITHOUT time function (GROUP BY category)
    
    Distinction from DateFilterIntent:
    - DateFieldIntent: For grouping (GROUP BY) - appears in SELECT clause
    - DateFilterIntent: For filtering (WHERE) - appears in WHERE clause
    
    CRITICAL: Use DateFieldIntent when date field needs time granularity transformation.
    Use DimensionIntent for non-date categorical fields.
    """
    model_config = ConfigDict(extra="forbid")
    
    business_term: str = Field(
        description="""Business term from user question.

Usage:
- Store original business term mentioned by user
- Used for field mapping and display

Values: Business term string (e.g., 'order_date', 'ship_date')"""
    )
    
    technical_field: str = Field(
        description="""Technical field name from metadata.

Usage:
- Must be exact field name from metadata.fields
- Used for query construction

Values: Technical field name string"""
    )
    
    field_data_type: str = Field(
        description="""Data type of the field.

Usage:
- Specify field data type from metadata
- Used for validation and query construction

Values: 'DATE', 'DATETIME', 'STRING'"""
    )
    
    date_function: Optional[Literal["YEAR", "QUARTER", "MONTH", "WEEK", "DAY"]] = Field(
        None,
        description="""Date function for time granularity.

Usage:
- Include if date field needs time granularity transformation
- Use value from sub-question's date_field_functions dict (YEAR/QUARTER/MONTH/WEEK/DAY)
- Use extraction functions (YEAR/MONTH/DAY), NOT truncation functions (TRUNC_*)
- null if using raw date value

Examples:
- YEAR: Extract year from date
- MONTH: Extract month from date
- DAY: Extract day from date"""
    )
    
    sort_direction: Optional[Literal["ASC", "DESC"]] = Field(
        None,
        description="""Sort direction for this date field.

Usage:
- Include if date field needs sorting
- null if no sorting required"""
    )
    
    sort_priority: Optional[int] = Field(
        None,
        ge=0,
        description="""Sort priority for multi-field sorting.

Usage:
- Include if multiple fields need sorting
- Lower number = higher priority (0 is highest)
- null if no sorting or single field sort

Values: Non-negative integer or null"""
    )


# ============= 筛选 Intent 模型 =============


class DateFilterIntent(BaseModel):
    """
    日期筛选意图
    
    包含日期字段的映射和时间范围信息。
    由 Task Planning Agent 生成。
    
    设计理念：
    - 只做字段映射，time_range 和 date_requirements 原样传递
    - Query Builder 负责根据 field_data_type 选择处理策略
    """
    model_config = ConfigDict(extra="forbid")
    
    business_term: str = Field(
        description="""Business term for date field.

Usage:
- Use value from sub-question's filter_date_field
- This is the user-facing date field name

Values: Business term string (e.g., 'order_date', 'ship_date')"""
    )
    
    technical_field: str = Field(
        description="""Technical field name from metadata.

Usage:
- Map business_term to exact field name in metadata.fields
- Must be actual date field name in datasource

Values: Technical field name string (e.g., 'Order Date', 'Ship Date')"""
    )
    
    field_data_type: str = Field(
        description="""Data type of the date field.

Usage:
- Get from metadata for the technical_field
- Used by Query Builder to determine date handling strategy

Values: 'DATE', 'DATETIME', 'STRING'"""
    )
    
    time_range: TimeRange = Field(
        description="""Time range specification.

Usage:
- Copy directly from sub-question's time_range (DO NOT modify)
- Pass through to Query Builder unchanged

Values: TimeRange object from sub-question"""
    )
    
    date_requirements: Optional[DateRequirements] = Field(
        None,
        description="""Special date requirements.

Usage:
- Copy directly from sub-question's date_requirements (DO NOT modify)
- null if sub-question has no special date requirements

Values: DateRequirements object from sub-question or null"""
    )


class FilterIntent(BaseModel):
    """
    非日期筛选意图
    
    包含筛选条件的字段映射和操作符。
    由 Task Planning Agent 从原始问题中识别。
    
    设计理念：
    - 从原始问题识别筛选条件（如'华东地区'、'销售额大于1000'）
    - 映射字段到技术字段
    - Query Builder 根据 filter_type 和 operator 生成对应的 VizQL Filter
    
    VizQL Filter 类型映射：
    - filter_type="SET" → SetFilter（集合筛选）
    - filter_type="QUANTITATIVE" → QuantitativeNumericalFilter（数值范围筛选）
    - filter_type="MATCH" → MatchFilter（文本匹配筛选）
    """
    model_config = ConfigDict(extra="forbid")
    
    business_term: str = Field(
        description="""Business term from user question.

Usage:
- Store original business term for filtered field
- Used for field mapping

Values: Business term string (e.g., 'region', 'sales')"""
    )
    
    technical_field: str = Field(
        description="""Technical field name from metadata.

Usage:
- Must be exact field name from metadata.fields
- Used for filter construction

Values: Technical field name string"""
    )
    
    filter_type: Literal["SET", "QUANTITATIVE", "MATCH"] = Field(
        description="""Type of filter operation.

Usage:
- Determine which VizQL filter type to generate
- SET → SetFilter (e.g., region in ['East', 'West'])
- QUANTITATIVE → QuantitativeNumericalFilter (e.g., sales > 1000)
- MATCH → MatchFilter (e.g., name contains 'John')"""
    )
    
    # SET Filter 字段
    values: Optional[List[Union[str, int, bool]]] = Field(
        None,
        description="""List of values for SET filter.

Usage:
- Include for filter_type='SET'
- null for other filter types

Values: List of strings, integers, or booleans (e.g., ['East', 'West'])"""
    )
    
    exclude: Optional[bool] = Field(
        None,
        description="""Whether to exclude matched values.

Usage:
- Include for filter_type='SET'
- true → Exclude these values
- false or null → Include these values (default)

Values: true, false, or null"""
    )
    
    # QUANTITATIVE Filter 字段
    quantitative_filter_type: Optional[Literal["RANGE", "MIN", "MAX", "ONLY_NULL", "ONLY_NON_NULL"]] = Field(
        None,
        description="""Type of quantitative filter.

Usage:
- Include for filter_type='QUANTITATIVE'
- null for other filter types"""
    )
    
    min_value: Optional[float] = Field(
        None,
        description="""Minimum value for quantitative filter.

Usage:
- Include for quantitative_filter_type='RANGE' or 'MIN'
- null for other types

Values: Numeric value or null"""
    )
    
    max_value: Optional[float] = Field(
        None,
        description="""Maximum value for quantitative filter.

Usage:
- Include for quantitative_filter_type='RANGE' or 'MAX'
- null for other types

Values: Numeric value or null"""
    )
    
    include_nulls: Optional[bool] = Field(
        None,
        description="""Whether to include null values.

Usage:
- Include for filter_type='QUANTITATIVE'
- true → Include nulls
- false or null → Exclude nulls (default)

Values: true, false, or null"""
    )
    
    # MATCH Filter 字段
    match_type: Optional[Literal["startsWith", "endsWith", "contains"]] = Field(
        None,
        description="""Type of text matching.

Usage:
- Include for filter_type='MATCH'
- null for other filter types"""
    )
    
    match_value: Optional[str] = Field(
        None,
        description="""Text value to match.

Usage:
- Include for filter_type='MATCH'
- null for other filter types

Values: Text string to match"""
    )
    
    match_exclude: Optional[bool] = Field(
        None,
        description="""Whether to exclude matched results.

Usage:
- Include for filter_type='MATCH'
- true → Exclude matches
- false or null → Include matches (default)

Values: true, false, or null"""
    )


class TopNIntent(BaseModel):
    """
    TopN 意图
    
    包含 TopN 配置的字段映射。
    由 Task Planning Agent 从原始问题中识别。
    
    设计理念：
    - TopN 不是必备的，只在原始问题明确要求时生成（如'前10个'、'最高的5个'）
    - Query Builder 负责条件验证（必须有分组维度）
    
    注意：
    - 如果原始问题不包含 TopN 关键词，Task Planning Agent 不应生成此 Intent
    """
    model_config = ConfigDict(extra="forbid")
    
    business_term: str = Field(
        description="""Business term for measure field.

Usage:
- Store original business term for TopN measure
- Used for field mapping

Values: Business term string (e.g., 'sales', 'profit')"""
    )
    
    technical_field: str = Field(
        description="""Technical field name from metadata.

Usage:
- Must be exact measure field name from metadata.fields
- Used for TopN filter construction

Values: Technical field name string"""
    )
    
    n: int = Field(
        ge=1,
        le=1000,
        description="""Number of top/bottom items.

Usage:
- Extract from original question (e.g., 'top 5' → n=5)
- Must be between 1 and 1000

Values: Integer from 1 to 1000"""
    )
    
    direction: Literal["TOP", "BOTTOM"] = Field(
        description="""Direction of TopN selection.

Usage:
- TOP for highest/largest values
- BOTTOM for lowest/smallest values"""
    )


# ============= 导出 =============

__all__ = [
    "DimensionIntent",
    "MeasureIntent",
    "DateFieldIntent",
    "DateFilterIntent",
    "FilterIntent",
    "TopNIntent",
]
