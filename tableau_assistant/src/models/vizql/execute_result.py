"""
Execute Node Result Data Model

Defines the output data structure for Execute Node.
This is the result returned from VizQL Data Service API calls.

Architecture:
- ExecuteResult: Raw API response from VizQL Data Service
- Used by Execute Node as output
- Stored in VizQLState.query_result
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Dict, Optional, Union, TypedDict
from datetime import datetime


# Type aliases for API response data
# Row data can contain various value types from the API
RowValue = Union[str, int, float, bool, None]
RowData = Dict[str, RowValue]


class ColumnMetadata(TypedDict, total=False):
    """Column metadata structure from VizQL API response"""
    fieldCaption: str
    name: str
    dataType: str
    role: str


class ExecuteResult(BaseModel):
    """
    Execute Node Result - Pydantic model
    
    Contains the raw result from VizQL Data Service API call.
    
    Attributes:
        data: List of row dictionaries (raw API response format)
        columns: Column metadata from API response
        row_count: Number of rows returned
        execution_time: Query execution time in seconds
        error: Error message if query failed
        query_id: Query ID from API response
        timestamp: Execution timestamp
    
    Usage:
        result = ExecuteResult(
            data=[{"region": "East", "sales": 1000}],
            columns=[{"fieldCaption": "region"}, {"fieldCaption": "sales"}],
            row_count=1,
            execution_time=0.5
        )
        
        if result.is_success():
            print(f"Got {result.row_count} rows")
    """
    model_config = ConfigDict(extra="forbid")
    
    data: List[RowData] = Field(
        default_factory=list,
        description="Query result data as list of row dictionaries"
    )
    
    columns: List[ColumnMetadata] = Field(
        default_factory=list,
        description="Column metadata from API response"
    )
    
    row_count: int = Field(
        default=0,
        ge=0,
        description="Number of rows returned"
    )
    
    execution_time: float = Field(
        default=0.0,
        ge=0.0,
        description="Query execution time in seconds"
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
        """Extract column names from column metadata."""
        return [
            col.get("fieldCaption", col.get("name", f"col_{i}"))
            for i, col in enumerate(self.columns)
        ]


__all__ = [
    "ExecuteResult",
]
