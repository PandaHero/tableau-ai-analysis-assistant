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
    """Measure field. Example: {"field_name": "Sales", "aggregation": "SUM"}"""
    model_config = ConfigDict(extra="forbid")
    
    field_name: str = Field(description="Field name (business term)")
    aggregation: AggregationType = Field(default=AggregationType.SUM, description="SUM/AVG/COUNT/COUNTD/MIN/MAX")
    alias: str | None = Field(default=None, description="Display name")
    sort: SortSpec | None = Field(default=None, description="Sort spec")
