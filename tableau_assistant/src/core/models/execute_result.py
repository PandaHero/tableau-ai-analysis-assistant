"""
Execute Result Data Model

Platform-agnostic query execution result.
This is the result returned from any data service API calls.

Architecture:
- ExecuteResult: Raw API response from data service
- Used by Execute Node as output
- Stored in workflow state
- Replaces the old QueryResult from validation.py
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Dict, Optional, Union, Any
from datetime import datetime


# Type aliases for API response data
# Row data can contain various value types from the API
RowValue = Union[str, int, float, bool, None]
RowData = Dict[str, RowValue]


class ColumnInfo(BaseModel):
    """Column information in query result.
    
    Provides semantic information about each column in the result set.
    """
    model_config = ConfigDict(extra="forbid")
    
    name: str = Field(
        description="Column name"
    )
    
    data_type: str = Field(
        default="STRING",
        description="Data type of the column"
    )
    
    is_dimension: bool = Field(
        default=False,
        description="Whether this is a dimension column"
    )
    
    is_measure: bool = Field(
        default=False,
        description="Whether this is a measure column"
    )
    
    is_computation: bool = Field(
        default=False,
        description="Whether this is a computed column"
    )


class ExecuteResult(BaseModel):
    """
    Execute Result - Platform-agnostic Pydantic model
    
    Contains the result from data service API call.
    Unified model replacing both old ExecuteResult and QueryResult from validation.py.
    
    Attributes:
        data: List of row dictionaries (raw API response format)
        columns: Column information with semantic metadata
        row_count: Number of rows returned
        execution_time_ms: Query execution time in milliseconds
        error: Error message if query failed
        query_id: Query ID from API response
        timestamp: Execution timestamp
    
    Usage:
        result = ExecuteResult(
            data=[{"region": "East", "sales": 1000}],
            columns=[
                ColumnInfo(name="region", data_type="STRING", is_dimension=True),
                ColumnInfo(name="sales", data_type="REAL", is_measure=True)
            ],
            row_count=1,
            execution_time_ms=500
        )
        
        if result.is_success():
            print(f"Got {result.row_count} rows")
    """
    model_config = ConfigDict(extra="forbid")
    
    data: List[RowData] = Field(
        default_factory=list,
        description="Query result data as list of row dictionaries"
    )
    
    columns: List[ColumnInfo] = Field(
        default_factory=list,
        description="Column information with semantic metadata"
    )
    
    row_count: int = Field(
        default=0,
        ge=0,
        description="Number of rows returned"
    )
    
    execution_time_ms: int = Field(
        default=0,
        ge=0,
        description="Query execution time in milliseconds"
    )
    
    error: Optional[str] = Field(
        default=None,
        description="Error message if query failed"
    )
    
    query_id: Optional[str] = Field(
        default=None,
        description="Query ID from API response"
    )
    
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="Execution timestamp (ISO format)"
    )
    
    def is_success(self) -> bool:
        """Check if query was successful."""
        return self.error is None
    
    def is_empty(self) -> bool:
        """Check if result has no data."""
        return self.row_count == 0 or not self.data
    
    def get_column_names(self) -> List[str]:
        """Extract column names from columns."""
        return [col.name for col in self.columns]
    
    # Alias for backward compatibility
    @property
    def rows(self) -> List[Dict[str, Any]]:
        """Alias for data (backward compatibility with old QueryResult)."""
        return self.data


__all__ = [
    "ExecuteResult",
    "ColumnInfo",
    "RowData",
    "RowValue",
]
