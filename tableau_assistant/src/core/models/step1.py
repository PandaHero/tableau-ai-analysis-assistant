"""Step 1 models - Semantic understanding and question restatement.

Step 1 is the "Intuition" phase of the LLM combination architecture.
It understands the user question, restates it as a complete standalone question,
extracts structured What/Where/How, and classifies intent.
"""

from pydantic import BaseModel, ConfigDict, Field

from .enums import (
    AggregationType,
    DateGranularity,
    FilterType,
    HowType,
    IntentType,
)


class MeasureSpec(BaseModel):
    """Measure specification in Step 1 output."""
    model_config = ConfigDict(extra="forbid")
    
    field: str = Field(
        description="""<what>Business term for the measure</what>
<when>ALWAYS required</when>
<rule>Use exact term from question</rule>"""
    )
    
    aggregation: AggregationType = Field(
        default=AggregationType.SUM,
        description="""<what>Aggregation function</what>
<when>Default SUM</when>"""
    )


class DimensionSpec(BaseModel):
    """Dimension specification in Step 1 output."""
    model_config = ConfigDict(extra="forbid")
    
    field: str = Field(
        description="""<what>Business term for the dimension</what>
<when>ALWAYS required</when>
<rule>Use exact term from question</rule>"""
    )
    
    granularity: DateGranularity | None = Field(
        default=None,
        description="""<what>Time granularity for date fields</what>
<when>ONLY for date/time fields</when>"""
    )


class FilterSpec(BaseModel):
    """Filter specification in Step 1 output."""
    model_config = ConfigDict(extra="forbid")
    
    field: str = Field(
        description="""<what>Field to filter on</what>
<when>ALWAYS required</when>"""
    )
    
    type: FilterType = Field(
        description="""<what>Type of filter</what>
<when>ALWAYS required</when>"""
    )
    
    values: list[str] | None = Field(
        default=None,
        description="""<what>Filter values</what>
<when>For SET filters</when>"""
    )


class What(BaseModel):
    """What - Target measures (part of Three-Element Model)."""
    model_config = ConfigDict(extra="forbid")
    
    measures: list[MeasureSpec] = Field(
        default_factory=list,
        description="""<what>List of measures to compute</what>
<when>ALWAYS required</when>
<rule>Extract from question, use business terms</rule>"""
    )


class Where(BaseModel):
    """Where - Dimensions and filters (part of Three-Element Model)."""
    model_config = ConfigDict(extra="forbid")
    
    dimensions: list[DimensionSpec] = Field(
        default_factory=list,
        description="""<what>List of dimensions for grouping</what>
<when>Usually required</when>
<rule>Extract from question, use business terms</rule>"""
    )
    
    filters: list[FilterSpec] = Field(
        default_factory=list,
        description="""<what>List of filter conditions</what>
<when>When user specifies filtering</when>"""
    )


class Intent(BaseModel):
    """Intent classification result."""
    model_config = ConfigDict(extra="forbid")
    
    type: IntentType = Field(
        description="""<what>Intent type</what>
<when>ALWAYS required</when>
<rule>
- Complete info → DATA_QUERY
- Unspecified values → CLARIFICATION
- Metadata question → GENERAL
- Unrelated → IRRELEVANT
</rule>"""
    )
    
    reasoning: str = Field(
        description="""<what>Reasoning for classification</what>
<when>ALWAYS required</when>
<rule>Explain why this intent was chosen</rule>"""
    )


class Step1Output(BaseModel):
    """Step 1 output: Semantic understanding and question restatement.
    
    <what>Restated question + structured What/Where/How + intent classification</what>
    
    <fill_order>
    1. restated_question (ALWAYS first)
    2. what (ALWAYS)
    3. where (ALWAYS)
    4. how_type (ALWAYS)
    5. intent (ALWAYS)
    </fill_order>
    
    <examples>
    Input: "各省份销售额"
    Output: {"restated_question": "按省份分组，计算销售额总和", "how_type": "SIMPLE", "intent": {"type": "DATA_QUERY"}}
    
    Input: History="各省份各月销售额", Current="每月排名呢？"
    Output: {"restated_question": "按省份和月份分组，在每个月内按销售额降序排名", "how_type": "RANKING"}
    </examples>
    
    <anti_patterns>
    ❌ Losing partition intent: "每月排名" → "按销售额排名" (lost "每月")
    ❌ Using technical field names: {"field": "[Sales].[Amount]"}
    </anti_patterns>
    """
    model_config = ConfigDict(extra="forbid")
    
    restated_question: str = Field(
        description="""<what>Complete standalone question in natural language</what>
<when>ALWAYS required</when>
<rule>Must preserve partition intent (每月→"在每个月内", 当月→"当月")</rule>
<must_not>Lose partition keywords (will cause wrong computation scope)</must_not>"""
    )
    
    what: What = Field(
        description="""<what>Target measures</what>
<when>ALWAYS required</when>
<rule>Extract from question, use business terms</rule>"""
    )
    
    where: Where = Field(
        description="""<what>Dimensions + filters</what>
<when>ALWAYS required</when>
<rule>Extract from question, use business terms</rule>"""
    )
    
    how_type: HowType = Field(
        description="""<what>Computation type</what>
<when>ALWAYS required</when>
<rule>排名→RANKING, 累计→CUMULATIVE, 占比/同比→COMPARISON, 固定粒度→GRANULARITY, 其他→SIMPLE</rule>"""
    )
    
    intent: Intent = Field(
        description="""<what>Intent classification + reasoning</what>
<when>ALWAYS required</when>
<rule>Complete info→DATA_QUERY, Unspecified values→CLARIFICATION, Metadata→GENERAL, Unrelated→IRRELEVANT</rule>"""
    )
