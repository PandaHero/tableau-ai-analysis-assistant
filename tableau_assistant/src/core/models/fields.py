"""Field models for the semantic layer.

Platform-agnostic field definitions using business terms.
"""

from pydantic import BaseModel, ConfigDict, Field

from .enums import AggregationType, DateGranularity, SortDirection


class SortSpec(BaseModel):
    """Sort specification for a field.
    
    Embedded in DimensionField or MeasureField when sorting is needed.
    """
    model_config = ConfigDict(extra="forbid")
    
    direction: SortDirection = Field(
        default=SortDirection.DESC,
        description="Sort direction"
    )
    
    priority: int = Field(
        default=0,
        description="Sort priority (lower = higher priority, 0 = primary sort)"
    )


class DimensionField(BaseModel):
    """Dimension field specification.
    
    Represents a dimension (categorical/time field) in the query.
    Uses business terms, not technical field names.
    """
    model_config = ConfigDict(extra="forbid")
    
    field_name: str = Field(
        description="Business term for the dimension"
    )
    
    date_granularity: DateGranularity | None = Field(
        default=None,
        description="Time granularity for date dimensions"
    )
    
    alias: str | None = Field(
        default=None,
        description="Display name for the field"
    )
    
    sort: SortSpec | None = Field(
        default=None,
        description="Sort specification (if this field is used for sorting)"
    )


class MeasureField(BaseModel):
    """Measure field specification.
    
    Represents a measure (numeric field) in the query.
    Uses business terms, not technical field names.
    """
    model_config = ConfigDict(extra="forbid")
    
    field_name: str = Field(
        description="Business term for the measure"
    )
    
    aggregation: AggregationType = Field(
        default=AggregationType.SUM,
        description="Aggregation function"
    )
    
    alias: str | None = Field(
        default=None,
        description="Display name for the field"
    )
    
    sort: SortSpec | None = Field(
        default=None,
        description="Sort specification (if this field is used for sorting)"
    )
