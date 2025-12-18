"""Field models for the semantic layer.

Platform-agnostic field definitions using business terms.
"""

from pydantic import BaseModel, ConfigDict, Field

from .enums import AggregationType, DateGranularity, SortDirection


class DimensionField(BaseModel):
    """Dimension field specification.
    
    Represents a dimension (categorical/time field) in the query.
    Uses business terms, not technical field names.
    """
    model_config = ConfigDict(extra="forbid")
    
    field_name: str = Field(
        description="""<what>Business term for the dimension</what>
<when>ALWAYS required</when>
<rule>Use exact term from user question, e.g. "省份", "订单日期"</rule>
<must_not>Use technical field names like "[Region].[Province]"</must_not>"""
    )
    
    date_granularity: DateGranularity | None = Field(
        default=None,
        description="""<what>Time granularity for date dimensions</what>
<when>ONLY for date/time fields</when>
<rule>年→YEAR, 季度→QUARTER, 月→MONTH, 周→WEEK, 日→DAY</rule>"""
    )
    
    alias: str | None = Field(
        default=None,
        description="""<what>Display name for the field</what>
<when>Optional, when different from field_name</when>"""
    )


class MeasureField(BaseModel):
    """Measure field specification.
    
    Represents a measure (numeric field) in the query.
    Uses business terms, not technical field names.
    """
    model_config = ConfigDict(extra="forbid")
    
    field_name: str = Field(
        description="""<what>Business term for the measure</what>
<when>ALWAYS required</when>
<rule>Use exact term from user question, e.g. "销售额", "利润"</rule>
<must_not>Use technical field names like "[Measures].[Sales]"</must_not>"""
    )
    
    aggregation: AggregationType = Field(
        default=AggregationType.SUM,
        description="""<what>Aggregation function</what>
<when>ALWAYS required, defaults to SUM</when>
<rule>总和→SUM, 平均→AVG, 计数→COUNT, 去重计数→COUNT_DISTINCT</rule>"""
    )
    
    alias: str | None = Field(
        default=None,
        description="""<what>Display name for the field</what>
<when>Optional, when different from field_name</when>"""
    )


class Sort(BaseModel):
    """Sort specification.
    
    Defines sorting order for query results.
    """
    model_config = ConfigDict(extra="forbid")
    
    field_name: str = Field(
        description="""<what>Field to sort by</what>
<when>ALWAYS required</when>
<rule>Can be dimension, measure, or computation alias</rule>"""
    )
    
    direction: SortDirection = Field(
        default=SortDirection.DESC,
        description="""<what>Sort direction</what>
<when>ALWAYS required, defaults to DESC</when>
<rule>升序→ASC, 降序→DESC</rule>"""
    )
    
    priority: int = Field(
        default=0,
        description="""<what>Sort priority (lower = higher priority)</what>
<when>Optional, for multi-column sorting</when>"""
    )
