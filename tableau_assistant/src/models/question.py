"""
Question-related Data Models (Optimized)

Design Principles Applied:
1. Orthogonal Decomposition: Each entity is an independent decision unit
2. Semantic Consistency: Field names match Prompt terminology
3. Minimal Description Length: No redundant fields
4. Information Bottleneck: Only task-relevant information

Contains:
1. QueryEntity - Single entity with its role (atomic unit)
2. TimeRange - Time range specification (kept for compatibility)
3. QuestionUnderstanding - Question understanding result
"""
from pydantic import BaseModel, Field, ConfigDict, model_validator
from typing import Optional, List
from enum import Enum


# ============= Enum Types =============

class EntityRole(str, Enum):
    """Entity's role in SQL query - determines SQL operation"""
    GROUP_BY = "group_by"      # Dimension for GROUP BY clause
    AGGREGATE = "aggregate"    # Field being aggregated (COUNT/SUM/AVG)
    FILTER = "filter"          # Field for WHERE clause filtering


class AggregationType(str, Enum):
    """SQL aggregation function type"""
    SUM = "SUM"
    AVG = "AVG"
    COUNT = "COUNT"
    COUNTD = "COUNTD"
    MAX = "MAX"
    MIN = "MIN"


class EntityType(str, Enum):
    """Entity's data type - only two fundamental types.
    
    Note: Date is a special dimension with date_function, not a separate type.
    This follows the principle: date is categorical (grouping) with temporal semantics.
    """
    DIMENSION = "dimension"    # Categorical field (including date fields)
    MEASURE = "measure"        # Numeric field


class DateFunction(str, Enum):
    """Date function for time-based grouping"""
    YEAR = "YEAR"
    QUARTER = "QUARTER"
    MONTH = "MONTH"
    WEEK = "WEEK"
    DAY = "DAY"


class QuestionType(str, Enum):
    """Question type classification"""
    COMPARISON = "对比"
    TREND = "趋势"
    RANKING = "排名"
    DIAGNOSIS = "诊断"
    BREAKDOWN = "多维分解"
    PROPORTION = "占比"
    YOY_MOM = "同环比"


class Complexity(str, Enum):
    """Question complexity level"""
    SIMPLE = "Simple"
    MEDIUM = "Medium"
    COMPLEX = "Complex"


class TimeRangeType(str, Enum):
    """Time range type"""
    ABSOLUTE = "absolute"
    RELATIVE = "relative"
    COMPARISON = "comparison"


class RelativeType(str, Enum):
    """Relative time calculation type"""
    CURRENT = "CURRENT"
    LAST = "LAST"
    LASTN = "LASTN"
    TODATE = "TODATE"


class PeriodType(str, Enum):
    """Time period unit"""
    DAYS = "DAYS"
    WEEKS = "WEEKS"
    MONTHS = "MONTHS"
    QUARTERS = "QUARTERS"
    YEARS = "YEARS"





# ============= Atomic Data Models =============

class QueryEntity(BaseModel):
    """Single entity extracted from question - ATOMIC DECISION UNIT.
    
    Each entity is independently classified with:
    - name: business term from question
    - type: dimension/measure (date is a dimension with date_function)
    - role: how it's used in SQL (group_by/aggregate/filter)
    - aggregation: SQL function if role=aggregate
    - date_function: time granularity for date dimensions with role=group_by
    
    EXAMPLES:
    
    "各省份销售额":
    - {name: "省份", type: "dimension", role: "group_by"}
    - {name: "销售额", type: "measure", role: "aggregate", aggregation: "SUM"}
    
    "多少产品":
    - {name: "产品", type: "dimension", role: "aggregate", aggregation: "COUNTD"}
    
    "按月趋势":
    - {name: "日期", type: "dimension", role: "group_by", date_function: "MONTH"}
    
    ANTI-PATTERNS:
    ❌ role=group_by with aggregation set (group_by fields don't aggregate)
    ❌ role=aggregate without aggregation (must specify function)
    ❌ type=measure with aggregation=COUNTD (COUNTD is for dimensions)
    ❌ date_function with type=measure (date fields must be dimensions)
    """
    model_config = ConfigDict(extra="forbid")
    
    name: str = Field(
        ...,
        description="""Business term extracted from question.

WHAT: The entity name as mentioned in the question
HOW: Use exact business term, not technical field name

EXAMPLES:
- "各省份销售额" → "省份", "销售额"
- "多少产品" → "产品"
- "按月趋势" → "日期" """
    )
    
    type: EntityType = Field(
        ...,
        description="""Entity's data type.

WHAT: Whether this is a categorical or numeric field
HOW: Classify based on the nature of the entity

VALUES:
- dimension: Categorical field (省份, 产品, 品类, 日期)
- measure: Numeric field (销售额, 利润, 数量)

NOTE: Date fields are dimensions with date_function set for time grouping."""
    )
    
    role: EntityRole = Field(
        ...,
        description="""Entity's role in SQL query.

WHAT: How this entity will be used in the SQL query
HOW: Determine based on question context and modifiers

VALUES:
- group_by: For GROUP BY clause ("各X", "按X", "每个X")
- aggregate: Being aggregated ("总X", "平均X", "多少X")
- filter: For WHERE clause ("某个X", "X=Y")

DECISION RULES:
- "各/按/每个" + entity → role=group_by
- "多少/几个" + entity → role=aggregate (with COUNTD)
- "总/平均/最高" + entity → role=aggregate
- Specific value mentioned → role=filter"""
    )
    
    aggregation: Optional[AggregationType] = Field(
        None,
        description="""SQL aggregation function.

WHAT: The aggregation function to apply
WHEN: Required when role=aggregate, null otherwise
HOW: Choose based on question modifiers

VALUES:
- SUM: "总", "合计" (default for measures)
- AVG: "平均", "均值"
- COUNT: "次数"
- COUNTD: "多少", "几个" (for dimensions)
- MAX: "最高", "最大", "最新"
- MIN: "最低", "最小", "最早"

DEPENDENCY: Must be set when role=aggregate"""
    )
    
    date_function: Optional[DateFunction] = Field(
        None,
        description="""Time granularity for date grouping.

WHAT: How to extract time component for GROUP BY
WHEN: Only for date dimensions with role=group_by
HOW: Choose based on time granularity mentioned

VALUES:
- YEAR: "按年", "各年度"
- QUARTER: "按季度", "各季度"
- MONTH: "按月", "各月"
- WEEK: "按周"
- DAY: "按天", "每日"

INDICATOR: Presence of date_function marks this dimension as a date field.
DEPENDENCY: Only valid when role=group_by"""
    )
    
    @model_validator(mode='after')
    def validate_entity(self) -> 'QueryEntity':
        """Validate entity consistency."""
        # Aggregation required for aggregate role
        if self.role == EntityRole.AGGREGATE and not self.aggregation:
            raise ValueError("aggregation is required when role=aggregate")
        
        # No aggregation for group_by role
        if self.role == EntityRole.GROUP_BY and self.aggregation:
            raise ValueError("aggregation should be null when role=group_by")
        
        # COUNTD only for dimensions
        if self.aggregation == AggregationType.COUNTD and self.type == EntityType.MEASURE:
            raise ValueError("COUNTD is for dimensions, not measures")
        
        # date_function only for dimensions with group_by role
        if self.date_function:
            if self.type != EntityType.DIMENSION:
                raise ValueError("date_function only valid for type=dimension (date fields are dimensions)")
            if self.role != EntityRole.GROUP_BY:
                raise ValueError("date_function only valid for role=group_by")
        
        return self


class TimeRange(BaseModel):
    """Time range specification for date filtering.
    
    EXAMPLES:
    
    "2024年销售额":
    {type: "absolute", value: "2024", filter_field: "日期"}
    
    "最近3个月趋势":
    {type: "relative", relative_type: "CURRENT", period_type: "MONTHS", 
     range_n: 3, filter_field: "日期"}
    
    "同比增长":
    {type: "comparison", filter_field: "日期"}
    
    ANTI-PATTERNS:
    ❌ type=relative without period_type
    ❌ range_n without relative_type=CURRENT or LASTN
    """
    model_config = ConfigDict(extra="forbid")
    
    type: TimeRangeType = Field(
        ...,
        description="""Time range type.

VALUES:
- absolute: Specific period ("2024年", "Q1", "3月")
- relative: Relative to now ("最近3个月", "本月", "上个月")
- comparison: Time comparison ("同比", "环比")"""
    )
    
    filter_field: Optional[str] = Field(
        None,
        description="""Date field for WHERE clause filtering.

WHAT: The date field to apply time filter on
HOW: Use business term (e.g., "日期", "订单日期")

EXAMPLES:
- "2024年销售额" → "日期"
- "最近3个月订单" → "订单日期" """
    )
    
    value: Optional[str] = Field(
        None,
        description="""Absolute time value (ISO format).

WHEN: Only when type=absolute
HOW: Fill missing year/month from max_date

VALUES: 'YYYY', 'YYYY-QN', 'YYYY-MM', 'YYYY-MM-DD'

EXAMPLES:
- "2024年" → "2024"
- "Q1" → "2024-Q1" (year from max_date)
- "3月15日" → "2024-03-15" """
    )
    
    relative_type: Optional[RelativeType] = Field(
        None,
        description="""Relative time calculation method.

WHEN: Only when type=relative

VALUES:
- CURRENT: "本月", "今年", "最近N个月"
- LAST: "上个月", "去年"
- LASTN: "最近N个月" (with range_n)
- TODATE: "年初至今", "月初至今" """
    )
    
    period_type: Optional[PeriodType] = Field(
        None,
        description="""Time period unit.

WHEN: Required when type=relative

VALUES: DAYS, WEEKS, MONTHS, QUARTERS, YEARS"""
    )
    
    range_n: Optional[int] = Field(
        None,
        ge=1,
        description="""Number of periods for "最近N个..." patterns.

WHEN: Only when relative_type=CURRENT or LASTN and N is specified

EXAMPLES:
- "最近3个月" → 3
- "本月" → null"""
    )
    
    start_date: Optional[str] = Field(
        None,
        description="""Start date for explicit range (YYYY-MM-DD).

WHEN: For "X到Y" patterns"""
    )
    
    end_date: Optional[str] = Field(
        None,
        description="""End date for explicit range (YYYY-MM-DD).

WHEN: For "X到Y" patterns"""
    )


# ============= Reasoning Models (Structured CoT) =============

class ReasoningStep(BaseModel):
    """Single reasoning step in structured Chain-of-Thought.
    
    Each step represents one stage of the reasoning process:
    1. intent - Understand what user wants
    2. entities - Extract business terms
    3. roles - Classify each entity's SQL role
    4. time - Identify time scope
    5. validation - Check consistency
    
    This provides:
    - Traceability: Can see why each decision was made
    - Accuracy: Forces systematic thinking
    - Debuggability: Easy to identify where reasoning went wrong
    """
    model_config = ConfigDict(extra="forbid")
    
    step_name: str = Field(
        ...,
        description="""Name of reasoning step.
        
VALUES: intent, entities, roles, time, validation"""
    )
    
    analysis: str = Field(
        ...,
        description="""Analysis process for this step.
        
WHAT: The thinking process, observations, considerations
HOW: Write in natural language, be specific

EXAMPLES:
- intent: "用户想要按省份分组查看销售额的汇总数据"
- entities: "识别到两个业务术语：'省份'（分类字段）和'销售额'（数值字段）"
- roles: "'各省份'表示按省份分组，'销售额'需要聚合求和" """
    )
    
    conclusion: str = Field(
        ...,
        description="""Conclusion of this step.
        
WHAT: The decision or result from this step
HOW: Be concise and specific

EXAMPLES:
- intent: "多维分解查询"
- entities: "省份(dimension), 销售额(measure)"
- roles: "省份→group_by, 销售额→aggregate(SUM)" """
    )


# ============= Main Model =============

class QuestionUnderstanding(BaseModel):
    """Question understanding result - orthogonal entity-based structure with structured reasoning.
    
    Design Principles:
    1. Each entity is an independent decision unit (QueryEntity)
    2. Structured CoT provides traceability and accuracy
    3. No cross-field dependencies for entity classification
    
    EXAMPLES:
    
    Input: "各省份的销售额"
    Output: {
        "question": "各省份的销售额",
        "is_valid": true,
        "reasoning": [
            {"step_name": "intent", "analysis": "用户想按省份分组查看销售额", "conclusion": "多维分解查询"},
            {"step_name": "entities", "analysis": "识别到'省份'和'销售额'", "conclusion": "2个实体"},
            {"step_name": "roles", "analysis": "'各省份'表示分组，'销售额'需要聚合", "conclusion": "省份→group_by, 销售额→aggregate(SUM)"}
        ],
        "entities": [
            {"name": "省份", "type": "dimension", "role": "group_by"},
            {"name": "销售额", "type": "measure", "role": "aggregate", "aggregation": "SUM"}
        ],
        "time_range": null,
        "question_types": ["多维分解"],
        "complexity": "Simple"
    }
    
    Input: "2024年各省份销售额按月趋势"
    Output: {
        "question": "2024年各省份销售额按月趋势",
        "is_valid": true,
        "reasoning": [...],
        "entities": [
            {"name": "省份", "type": "dimension", "role": "group_by"},
            {"name": "销售额", "type": "measure", "role": "aggregate", "aggregation": "SUM"},
            {"name": "日期", "type": "dimension", "role": "group_by", "date_function": "MONTH"}
        ],
        "time_range": {"type": "absolute", "value": "2024", "filter_field": "日期"},
        "question_types": ["趋势", "多维分解"],
        "complexity": "Medium"
    }
    
    ANTI-PATTERNS:
    ❌ Using technical field names like "[Sales].[Amount]"
    ❌ Missing entity in "count of X per Y" - both X and Y should be entities
    ❌ Duplicate entity names in entities list
    ❌ is_valid=false without invalid_reason
    ❌ Empty reasoning for valid questions
    """
    model_config = ConfigDict(extra="forbid")
    
    # ===== Core Fields =====
    
    question: str = Field(
        ...,
        description="""Original question text (verbatim copy)."""
    )
    
    is_valid: bool = Field(
        ...,
        description="""Whether this is a valid data analysis question.

VALUES:
- true: Valid data analysis question
- false: Invalid (greeting, off-topic, unclear)

EXAMPLES:
- "各省份销售额" → true
- "你好" → false
- "今天天气" → false"""
    )
    
    invalid_reason: Optional[str] = Field(
        None,
        description="""Reason for invalid question (Chinese).

WHEN: Required when is_valid=false

EXAMPLES:
- "你好" → "这是问候语，不是数据分析问题"
- "天气" → "天气查询不在数据分析范围内" """
    )
    
    # ===== Structured Reasoning (CoT) =====
    
    reasoning: List[ReasoningStep] = Field(
        default_factory=list,
        description="""Structured reasoning steps (Chain-of-Thought).

WHAT: Step-by-step reasoning process for question understanding
WHEN: For valid questions, provide reasoning steps
HOW: Follow the 5-step process: intent → entities → roles → time → validation

STEPS:
1. intent: What does the user want? (query type)
2. entities: What business terms are mentioned?
3. roles: How is each entity used in SQL?
4. time: Is there a time scope?
5. validation: Are the results consistent?

BENEFITS:
- Traceability: Can see why each decision was made
- Accuracy: Forces systematic thinking
- Debuggability: Easy to identify reasoning errors"""
    )
    
    # ===== Entity Recognition (Orthogonal) =====
    
    entities: List[QueryEntity] = Field(
        default_factory=list,
        description="""All entities extracted from question.

WHAT: List of QueryEntity objects, each independently classified
WHEN: For valid questions
HOW: Extract all business terms, classify each independently

Each entity has: name, type, role, aggregation?, date_function?

EXAMPLES:
- "各省份销售额" → 2 entities (省份, 销售额)
- "多少产品" → 1 entity (产品 with COUNTD)
- "按月趋势" → 1 entity (日期 with MONTH function)"""
    )
    
    # ===== Time Range =====
    
    time_range: Optional[TimeRange] = Field(
        None,
        description="""Time range for filtering.

WHEN: When question specifies a time period
HOW: Create TimeRange object

EXAMPLES:
- "2024年销售额" → TimeRange(type=absolute, value="2024")
- "最近3个月" → TimeRange(type=relative, ...)
- "各省份销售额" → null (no time filter)"""
    )
    
    # ===== Classification =====
    
    question_types: List[QuestionType] = Field(
        default_factory=list,
        description="""Question type classification.

VALUES:
- 对比: "A vs B", "对比"
- 趋势: "趋势", "变化", "走势"
- 排名: "排名", "前N", "Top"
- 多维分解: "各X", "按X分析"
- 占比: "占比", "比例"
- 同环比: "同比", "环比"

EXAMPLES:
- "各省份销售额" → ["多维分解"]
- "销售额趋势" → ["趋势"]
- "各省份销售额同比" → ["多维分解", "同环比"]"""
    )
    
    complexity: Complexity = Field(
        ...,
        description="""Query complexity level.

VALUES:
- Simple: Single entity or basic query
- Medium: Multiple entities or time analysis
- Complex: Calculations or advanced analytics"""
    )
    
    needs_exploration: bool = Field(
        default=False,
        description="""Whether exploratory analysis is needed.

WHEN: true for "why", "reason" type questions

EXAMPLES:
- "为什么销售下降" → true
- "各省份销售额" → false"""
    )
    
    @model_validator(mode='after')
    def validate_consistency(self) -> 'QuestionUnderstanding':
        """Validate model consistency."""
        # Invalid reason required when invalid
        if not self.is_valid and not self.invalid_reason:
            raise ValueError("invalid_reason required when is_valid=false")
        
        # Check for duplicate entity names
        names = [e.name for e in self.entities]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate entity names in entities list")
        
        return self

# ============= Helper Functions =============

def create_entity(
    name: str,
    entity_type: EntityType,
    role: EntityRole,
    aggregation: Optional[AggregationType] = None,
    date_function: Optional[DateFunction] = None
) -> QueryEntity:
    """Create a QueryEntity with validation."""
    return QueryEntity(
        name=name,
        type=entity_type,
        role=role,
        aggregation=aggregation,
        date_function=date_function
    )


def create_time_range_absolute(value: str, filter_field: str = "日期") -> TimeRange:
    """Create absolute time range."""
    return TimeRange(
        type=TimeRangeType.ABSOLUTE,
        value=value,
        filter_field=filter_field
    )


def create_time_range_relative(
    relative_type: RelativeType,
    period_type: PeriodType,
    filter_field: str = "日期",
    range_n: Optional[int] = None
) -> TimeRange:
    """Create relative time range."""
    return TimeRange(
        type=TimeRangeType.RELATIVE,
        relative_type=relative_type,
        period_type=period_type,
        filter_field=filter_field,
        range_n=range_n
    )


# ============= Legacy Compatibility Layer =============
# These models are deprecated but kept for backward compatibility with task_planner
# TODO: Remove after task_planner is refactored to use entity-based model

class SubQuestionExecutionType(str, Enum):
    """DEPRECATED: Sub-question execution type (legacy compatibility)"""
    QUERY = "query"
    CALCULATION = "calculation"
    POST_PROCESSING = "post_processing"


class SubQuestion(BaseModel):
    """DEPRECATED: Sub-question for task decomposition (legacy compatibility).
    
    Note: This is a legacy model for compatibility with task_planner.
    New code should use QuestionUnderstanding with entities.
    """
    model_config = ConfigDict(extra="forbid")
    
    text: str = Field(..., description="Sub-question text")
    completed_text: str = Field(default="", description="Completed sub-question text")
    execution_type: SubQuestionExecutionType = Field(
        default=SubQuestionExecutionType.QUERY,
        description="Execution type"
    )
    mentioned_dimensions: List[str] = Field(default_factory=list)
    mentioned_measures: List[str] = Field(default_factory=list)
    mentioned_date_fields: List[str] = Field(default_factory=list)
    dimension_aggregations: Optional[dict] = Field(default=None)
    measure_aggregations: Optional[dict] = Field(default=None)
    date_field_functions: Optional[dict] = Field(default=None)
    time_range: Optional[TimeRange] = Field(default=None)
    filter_date_field: Optional[str] = Field(default=None)
    depends_on_indices: List[int] = Field(default_factory=list)
    processing_type: Optional[str] = Field(default=None)


# Alias for backward compatibility
QuerySubQuestion = SubQuestion


# ============= Exports =============

__all__ = [
    # Enums
    "EntityRole",
    "AggregationType", 
    "EntityType",
    "DateFunction",
    "QuestionType",
    "Complexity",
    "TimeRangeType",
    "RelativeType",
    "PeriodType",
    "SubQuestionExecutionType",  # Legacy
    
    # Models
    "QueryEntity",
    "TimeRange",
    "ReasoningStep",
    "QuestionUnderstanding",
    "SubQuestion",  # Legacy
    "QuerySubQuestion",  # Legacy alias
    
    # Helpers
    "create_entity",
    "create_time_range_absolute",
    "create_time_range_relative",
]
