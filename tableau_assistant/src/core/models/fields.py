"""Field models for the semantic layer. Platform-agnostic field definitions."""

from pydantic import BaseModel, ConfigDict, Field

from .enums import AggregationType, DateGranularity, SortDirection


class SortSpec(BaseModel):
    """Sort specification."""
    model_config = ConfigDict(extra="forbid")
    
    direction: SortDirection = Field(default=SortDirection.DESC, description="ASC or DESC")
    priority: int = Field(default=0, description="Sort priority (0=primary)")


class DimensionField(BaseModel):
    """Dimension field. Example: {"field_name": "Region"} or {"field_name": "Order Date", "date_granularity": "MONTH"}"""
    model_config = ConfigDict(extra="forbid")
    
    field_name: str = Field(description="Field name (business term)")
    date_granularity: DateGranularity | None = Field(default=None, description="YEAR/QUARTER/MONTH/WEEK/DAY")
    alias: str | None = Field(default=None, description="Display name")
    sort: SortSpec | None = Field(default=None, description="Sort spec")


class MeasureField(BaseModel):
    """Measure field for query.
    
    <fill_order>
    1. field_name (ALWAYS)
    2. aggregation (check if pre-aggregated)
    3. alias (optional)
    4. sort (optional)
    </fill_order>
    
    <examples>
    Regular: {"field_name": "Sales", "aggregation": "SUM"}
    Pre-aggregated: {"field_name": "Profit Ratio", "aggregation": null}
    </examples>
    
    <anti_patterns>
    X aggregation=SUM for pre-aggregated measure (causes "already aggregated" error)
    X aggregation=null for regular measure (missing aggregation)
    </anti_patterns>
    """
    model_config = ConfigDict(extra="forbid")
    
    field_name: str = Field(
        description="""<what>Field name (business term)</what>
<when>ALWAYS</when>"""
    )
    aggregation: AggregationType | None = Field(
        default=AggregationType.SUM, 
        description="""<what>Aggregation function</what>
<when>ALWAYS - but null for pre-aggregated measures</when>
<rule>Check Available Fields: if [pre-aggregated] marker exists, set null</rule>"""
    )
    alias: str | None = Field(
        default=None, 
        description="""<what>Display name</what>
<when>Optional</when>"""
    )
    sort: SortSpec | None = Field(
        default=None, 
        description="""<what>Sort specification</what>
<when>Optional</when>"""
    )
