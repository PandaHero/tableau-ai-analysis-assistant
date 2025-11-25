"""
Question-related Data Models

Contains:
1. QuestionUnderstanding - Question understanding result
2. TimeRange - Time range specification
3. DateRequirements - Date requirements
4. Related enum types
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Literal, Optional, List, Union, Annotated
from enum import Enum


# ============= Enum Types =============

class QuestionType(str, Enum):
    """Question type"""
    COMPARISON = "对比"
    TREND = "趋势"
    RANKING = "排名"
    DIAGNOSIS = "诊断"
    MULTI_DIM = "多维分解"
    PROPORTION = "占比"
    YOY_MOM = "同环比"
    MOM = "环比"  # 环比分析


class SubQuestionExecutionType(str, Enum):
    """
    Sub-question execution type
    
    Describes how sub-questions are executed:
    - query: Generate VizQL query and execute data retrieval
    - post_processing: Calculation/analysis tasks after data retrieval
    """
    QUERY = "query"
    POST_PROCESSING = "post_processing"


class ProcessingType(str, Enum):
    """
    Data processing type (for post_processing type sub-questions)
    
    - yoy: Year-over-year analysis
    - mom: Month-over-month analysis
    - growth_rate: Growth rate calculation
    - percentage: Percentage calculation
    - custom: Custom calculation
    """
    YOY = "yoy"
    MOM = "mom"
    GROWTH_RATE = "growth_rate"
    PERCENTAGE = "percentage"
    CUSTOM = "custom"


class SubQuestionRelationType(str, Enum):
    """
    Relationship type between sub-questions
    
    Describes semantic relationships between multiple sub-questions:
    - comparison: Comparison relationship, for time/dimension comparisons
    - breakdown: Breakdown relationship, whole-to-part relationship
    - drill_down: Drill-down relationship, from coarse to fine granularity
    - independent: Independent relationship, no correlation between sub-questions
    """
    COMPARISON = "comparison"
    BREAKDOWN = "breakdown"
    DRILL_DOWN = "drill_down"
    INDEPENDENT = "independent"


class Complexity(str, Enum):
    """Question complexity"""
    SIMPLE = "Simple"
    MEDIUM = "Medium"
    COMPLEX = "Complex"


class TimeRangeType(str, Enum):
    """Time range type"""
    ABSOLUTE = "absolute"    # Absolute time, e.g., "2016"
    RELATIVE = "relative"    # Relative time, e.g., "last 3 months"
    CURRENT = "current"      # Current time, e.g., "this month"
    COMPARISON = "comparison" # Time comparison, e.g., "2016 vs 2015", "YoY", "MoM"


class RelativeType(str, Enum):
    """Relative time type"""
    CURRENT = "CURRENT"  # Current period to date
    LAST = "LAST"        # Complete previous period
    NEXT = "NEXT"        # Complete next period
    TODATE = "TODATE"    # From period start to today
    LASTN = "LASTN"      # Rolling N periods from today
    NEXTN = "NEXTN"      # Rolling N periods into future


class PeriodType(str, Enum):
    """Period type"""
    DAYS = "DAYS"
    WEEKS = "WEEKS"
    MONTHS = "MONTHS"
    QUARTERS = "QUARTERS"
    YEARS = "YEARS"


class DateFunction(str, Enum):
    """Date function for time-based grouping"""
    YEAR = "YEAR"        # Extract year from date
    QUARTER = "QUARTER"  # Extract quarter from date
    MONTH = "MONTH"      # Extract month from date
    WEEK = "WEEK"        # Extract week from date
    DAY = "DAY"          # Extract day from date


# ============= Data Models =============

class TimeRange(BaseModel):
    """Time range"""
    model_config = ConfigDict(extra="forbid")
    
    type: Optional[TimeRangeType] = Field(
        None,
        description="""Time range type.

Usage:
- Specify how time range is defined"""
    )
    value: Optional[str] = Field(
        None,
        description="""Absolute time value in ISO format.

Usage:
- Include for absolute time ranges (type='absolute')
- null for relative/current/comparison time ranges

Values: 
- Year: 'YYYY' (e.g., '2016')
- Year-Quarter: 'YYYY-QN' (e.g., '2016-Q1', '2016-Q2')
- Year-Month: 'YYYY-MM' (e.g., '2016-03', '2016-12')
- Full date: 'YYYY-MM-DD' (e.g., '2016-03-15')"""
    )
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
    period_type: Optional[PeriodType] = Field(
        None,
        description="""Period type for relative time.

Usage:
- Include for relative time ranges
- Specify time granularity"""
    )
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
    start_date: Optional[str] = Field(
        None,
        description="""Start date for date range (absolute type only).

Usage:
- Include for date ranges (type='absolute')
- Use with end_date to specify a date range
- null for single date values or relative time ranges

Format: 'YYYY-MM-DD'
Example: '2024-01-01' for "January to March 2024" → start_date='2024-01-01', end_date='2024-03-31'"""
    )
    end_date: Optional[str] = Field(
        None,
        description="""End date for date range (absolute type only).

Usage:
- Include for date ranges (type='absolute')
- Use with start_date to specify a date range
- null for single date values or relative time ranges

Format: 'YYYY-MM-DD'
Example: '2024-03-31' for "January to March 2024" → start_date='2024-01-01', end_date='2024-03-31'"""
    )


class WeekStartDay(str, Enum):
    """Week start day enum"""
    MONDAY = "MONDAY"      # Monday
    SUNDAY = "SUNDAY"      # Sunday


class WeekStartDayInfo(BaseModel):
    """
    Week start day information
    
    Specifies which day a week starts from.
    """
    model_config = ConfigDict(extra="forbid")
    
    day: WeekStartDay = Field(
        description="""Week start day.

Usage:
- Specify which day the week starts from"""
    )
    keywords: List[str] = Field(
        default_factory=list,
        description="""Identified keywords from user question.

Usage:
- Store keywords that indicate week start day
- Used for validation and debugging

Values: List of keyword strings (e.g., 'start from Monday', 'from Sunday')"""
    )


class HolidayInfo(BaseModel):
    """Holiday information"""
    model_config = ConfigDict(extra="forbid")
    
    holiday_name: str = Field(
        description="""Holiday name.

Usage:
- Store recognized holiday name from user question

Values: Holiday name string (e.g., 'Spring Festival', 'National Day', 'Labor Day')"""
    )
    keywords: List[str] = Field(
        default_factory=list,
        description="""Identified keywords from user question.

Usage:
- Store keywords that indicate this holiday
- Used for validation and debugging

Values: List of keyword strings"""
    )


class LunarInfo(BaseModel):
    """Lunar calendar information"""
    model_config = ConfigDict(extra="forbid")
    
    lunar_reference: str = Field(
        description="""Lunar calendar reference.

Usage:
- Store lunar calendar reference from user question

Values: Lunar reference string (e.g., 'first month', 'fifteenth day')"""
    )
    keywords: List[str] = Field(
        default_factory=list,
        description="""Identified keywords from user question.

Usage:
- Store keywords that indicate lunar calendar
- Used for validation and debugging

Values: List of keyword strings (e.g., 'lunar', 'lunar calendar')"""
    )


class DateRequirements(BaseModel):
    """
    Date requirements
    
    Captures special date requirements in questions, such as holidays, lunar calendar, week start day, etc.
    """
    model_config = ConfigDict(extra="forbid")
    
    week_start_day: Optional[WeekStartDayInfo] = Field(
        None,
        description="""Week start day information.

Usage:
- Include only when explicitly mentioned in question
- null if not mentioned

Values: WeekStartDayInfo object or null"""
    )
    
    holidays: Optional[List[HolidayInfo]] = Field(
        None,
        description="""Holiday information list.

Usage:
- Include when holidays are mentioned in question
- null if no holidays mentioned

Values: List of HolidayInfo objects or null"""
    )
    
    lunar: Optional[LunarInfo] = Field(
        None,
        description="""Lunar calendar information.

Usage:
- Include only when lunar calendar is mentioned in question
- null if not mentioned

Values: LunarInfo object or null"""
    )


class SubQuestionBase(BaseModel):
    """Sub-question base class"""
    model_config = ConfigDict(extra="forbid")
    
    text: str = Field(
        description="""Sub-question text.

Usage:
- Store decomposed sub-question text
- Use business terms, not technical names

Values: Sub-question text string"""
    )
    
    completed_text: Optional[str] = Field(
        None,
        description="""Explicit sub-question text with context.

Usage:
- Include when implicit context needs to be made explicit
- null if text is already complete

Values: Completed text string (e.g., 'sales' → 'this year sales') or null"""
    )


class QuerySubQuestion(SubQuestionBase):
    """
    Query type sub-question
    
    Requires executing VizQL query to retrieve data.
    Contains field identification, date information, and other query-related information.
    """
    execution_type: Literal["query"] = "query"
    
    depends_on_indices: List[int] = Field(
        default_factory=list,
        description="""List of dependent sub-question indices.

Usage:
- Include indices of sub-questions this query depends on
- Empty list if no dependencies

Values: List of integers (0-based indices)"""
    )
    
    # ===== Field Recognition (dimensions, measures, dates separated) =====
    
    mentioned_dimensions: List[str] = Field(
        default_factory=list,
        description="""List of ALL dimension entities identified from query (business terms).

Usage:
- Include ALL dimensions (both grouping and counted)

Values: Business term strings (e.g., 'region', 'product', 'store')"""
    )
    
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
- "Earliest Z by X" → {"Z": "MIN"}"""
    )
    
    mentioned_measures: List[str] = Field(
        default_factory=list,
        description="""List of ALL measure entities identified from query (business terms).

Usage:
- Include ALL numeric measures
- Exclude 'count of X' patterns (those are dimensions)

Values: Business term strings (e.g., 'sales', 'profit', 'revenue')"""
    )
    
    measure_aggregations: Optional[dict[str, str]] = Field(
        None,
        description="""Maps measure names to aggregation functions.

Usage:
- Include ALL measures with aggregation function

Values: 'SUM' (default), 'AVG', 'MIN', 'MAX', 'COUNT'"""
    )
    
    mentioned_date_fields: List[str] = Field(
        default_factory=list,
        description="""Date fields used for time-based grouping (GROUP BY time periods).

Usage:
- Include date fields that partition data into time periods
- Used with date_field_functions to specify granularity

Values: Business term strings"""
    )
    
    date_field_functions: Optional[dict[str, DateFunction]] = Field(
        None,
        description="""Maps date field names to time granularity functions for GROUP BY.

Usage:
- Include date field → Apply time granularity function for grouping
- Exclude date field → Use raw date value
- null or {} → No date functions applied

Values: DateFunction enum (YEAR, QUARTER, MONTH, WEEK, DAY)"""
    )
    
    # ===== Date Filtering Information =====
    
    filter_date_field: Optional[str] = Field(
        None,
        description="""Date field used for time range filtering (WHERE clause with time range).

Usage:
- Include if query filters data by time range
- Used with time_range to specify the range

Values: Business term string or null"""
    )
    
    time_range: Optional[TimeRange] = Field(
        None,
        description="""Time range specification for date filtering.

Usage:
- Include if query specifies time range

Values: TimeRange object (absolute, relative, current, or comparison)"""
    )
    
    date_requirements: Optional[DateRequirements] = Field(
        None,
        description="""Special date requirements.

Usage:
- Include if query mentions special date requirements

Values: DateRequirements object (week_start_day, holidays, lunar)"""
    )
    
    needs_exploration: bool = Field(
        default=False,
        description="""Indicates if exploratory analysis is needed.

Usage:
- Set to true for 'why' questions or open-ended exploratory queries
- Set to false for direct data queries

Values: true (exploratory), false (direct query)"""
    )


class ProcessingSubQuestion(SubQuestionBase):
    """
    Processing type sub-question
    
    Performs calculations and processing on query results (e.g., year-over-year, month-over-month, growth rate, etc.).
    """
    execution_type: Literal["post_processing"] = "post_processing"
    
    processing_type: ProcessingType = Field(
        description="""Type of data processing operation.

Usage:
- Specify the calculation type to perform on query results"""
    )
    
    depends_on_indices: List[int] = Field(
        min_length=1,
        description="""List of dependent sub-question indices.

Usage:
- MUST include at least one query task index
- Processing tasks depend on query results

Values: List of integers (0-based indices, minimum 1 element)"""
    )


# Use discriminated union
SubQuestion = Annotated[
    Union[QuerySubQuestion, ProcessingSubQuestion],
    Field(discriminator='execution_type')
]


class SubQuestionRelationship(BaseModel):
    """
    Sub-question relationship
    
    Describes relationships between multiple sub-questions in sub_questions, used to guide subsequent query planning and insight analysis
    """
    model_config = ConfigDict(extra="forbid")
    
    relation_type: SubQuestionRelationType = Field(
        description="""Relationship type between sub-questions.

Usage:
- Classify how sub-questions relate to each other"""
    )
    
    question_indices: List[int] = Field(
        min_length=1,
        description="""Related sub-question indices.

Usage:
- Include indices of related sub-questions
- Minimum 1 element required

Values: List of integers (0-based indices corresponding to sub_questions list)"""
    )
    
    description: str = Field(
        description="""Relationship description.

Usage:
- Explain how these sub-questions are related
- Provide context for downstream processing

Values: Description string"""
    )
    
    comparison_dimension: Optional[str] = Field(
        None,
        description="""Comparison dimension.

Usage:
- Include only when relation_type is 'comparison'
- null for other relation types

Values: 'time' (time comparison), 'dimension' (dimension comparison), or null"""
    )


class QuestionUnderstanding(BaseModel):
    """
    Question understanding result
    
    Output by question understanding agent, contains all key information about the question
    
    Important field descriptions:
    - original_question: User's original question
    - sub_questions: List of sub-questions split based on VizQL capabilities
      - If no splitting needed, list contains only 1 element (original question)
      - If splitting needed, list contains multiple sub-questions
      - Each sub-question contains independent field identification and date information
    
    Design philosophy:
    - Field identification and date information belong to sub-questions, not top level
    - Understanding Agent focuses on intent understanding, does not identify sorting, TopN, filtering requirements
    - Remove redundant fields, simplify output structure
    """
    model_config = ConfigDict(extra="forbid")
    
    original_question: str = Field(
        ...,
        description="""User's original question.

Usage:
- Store the exact question text from user

Values: Question text string"""
    )
    
    sub_questions: List[SubQuestion] = Field(
        ...,
        min_length=1,
        description="""List of decomposed sub-questions.

Usage:
- Include 1 element if no decomposition needed
- Include multiple elements if decomposition required
- Each sub-question contains field recognition and date information

Values: List of SubQuestion objects (minimum 1 element)"""
    )
    
    is_valid_question: bool = Field(
        ...,
        description="""Whether this is a valid data analysis question.

Usage:
- Set to true for valid questions
- Set to false for invalid questions

Values: true (valid), false (invalid)"""
    )
    
    invalid_reason: Optional[str] = Field(
        None,
        description="""Reason for invalidity.

Usage:
- Include only when is_valid_question=false
- null when is_valid_question=true

Values: Reason string or null"""
    )
    
    question_type: List[QuestionType] = Field(
        default_factory=list,
        description="""Question type classification.

Usage:
- Include ALL applicable question types
- Can have multiple types for complex questions

Values: List of QuestionType enum values

Examples:
- "Sales by province" → ["多维分解"]
- "Top 5 provinces by sales" → ["排名"]
- "This year vs last year sales" → ["对比", "趋势"]"""
    )
    
    complexity: Complexity = Field(
        ...,
        description="""Question complexity level.

Usage:
- Classify based on query complexity

Values: 'Simple', 'Medium', 'Complex'

Examples:
- "Total sales" → Simple
- "Sales by province and channel" → Medium
- "YoY growth rate by province with filters" → Complex"""
    )


# ============= Helper Functions =============

def create_time_range_absolute(value: str) -> TimeRange:
    """Create absolute time range"""
    return TimeRange(
        type=TimeRangeType.ABSOLUTE,
        value=value
    )


def create_time_range_relative(
    relative_type: RelativeType,
    period_type: PeriodType,
    range_n: Optional[int] = None
) -> TimeRange:
    """Create relative time range"""
    return TimeRange(
        type=TimeRangeType.RELATIVE,
        relative_type=relative_type,
        period_type=period_type,
        range_n=range_n
    )


def create_time_range_current() -> TimeRange:
    """Create current time range"""
    return TimeRange(type=TimeRangeType.CURRENT)


# ============= Exports =============

__all__ = [
    # 枚举
    "QuestionType",
    "Complexity",
    "TimeRangeType",
    "RelativeType",
    "PeriodType",
    "DateFunction",
    "SubQuestionExecutionType",
    "ProcessingType",
    "SubQuestionRelationType",
    "WeekStartDay",
    
    # 模型
    "TimeRange",
    "WeekStartDayInfo",
    "HolidayInfo",
    "LunarInfo",
    "DateRequirements",
    "SubQuestionBase",
    "QuerySubQuestion",
    "ProcessingSubQuestion",
    "SubQuestion",
    "SubQuestionRelationship",
    "QuestionUnderstanding",
    
    # 辅助函数
    "create_time_range_absolute",
    "create_time_range_relative",
    "create_time_range_current",
]
