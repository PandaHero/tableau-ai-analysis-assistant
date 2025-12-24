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
<when>ALWAYS required</when>"""
    )
    
    date_granularity: DateGranularity | None = Field(
        default=None,
        description="""<what>Time granularity for date dimensions</what>
<when>ONLY for date/time fields</when>"""
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
<when>ALWAYS required</when>"""
    )
    
    aggregation: AggregationType = Field(
        default=AggregationType.SUM,
        description="""<what>Aggregation function</what>
<when>ALWAYS required, defaults to SUM</when>"""
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
<when>ALWAYS required</when>"""
    )
    
    direction: SortDirection = Field(
        default=SortDirection.DESC,
        description="""<what>Sort direction</what>
<when>ALWAYS required, defaults to DESC</when>"""
    )
    
    priority: int = Field(
        default=0,
        description="""<what>Sort priority (lower = higher priority)</what>
<when>Optional, for multi-column sorting</when>"""
    )
