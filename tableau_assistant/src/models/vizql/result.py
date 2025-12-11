"""
Query and Processing Result Data Models

Defines data structures between query executor and data processor
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Dict, Any, Optional
import pandas as pd


class QueryResult(BaseModel):
    """
    Query Result Model
    
    Encapsulates query executor return results
    """
    model_config = ConfigDict(
        extra="forbid",
        arbitrary_types_allowed=True  # Allow Pandas DataFrame
    )
    
    task_id: str = Field(
        description="Task ID (e.g., q1, q2)"
    )
    
    data: pd.DataFrame = Field(
        description="Query data (Pandas DataFrame)"
    )
    
    row_count: int = Field(
        ge=0,
        description="Row count"
    )
    
    columns: List[str] = Field(
        description="Column name list"
    )
    
    query_time_ms: Optional[int] = Field(
        default=None,
        description="Query time (milliseconds)"
    )
    
    execution_time_ms: Optional[int] = Field(
        default=None,
        description="Total execution time (milliseconds)"
    )
    
    retry_count: Optional[int] = Field(
        default=0,
        description="Retry count"
    )
    
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Additional metadata"
    )
    
    @classmethod
    def from_executor_result(
        cls,
        task_id: str,
        executor_result: Dict[str, Any]
    ) -> "QueryResult":
        """
        Create QueryResult from query executor result
        
        Args:
            task_id: Task ID
            executor_result: Dictionary returned by query executor
            
        Returns:
            QueryResult instance
        """
        data_list = executor_result.get("data", [])
        if data_list:
            df = pd.DataFrame(data_list)
        else:
            df = pd.DataFrame()
        
        return cls(
            task_id=task_id,
            data=df,
            row_count=executor_result.get("row_count", len(data_list)),
            columns=executor_result.get("columns", list(df.columns) if not df.empty else []),
            query_time_ms=executor_result.get("query_time_ms"),
            execution_time_ms=executor_result.get("execution_time_ms"),
            retry_count=executor_result.get("retry_count", 0),
            metadata={}
        )


__all__ = [
    "QueryResult",
]
