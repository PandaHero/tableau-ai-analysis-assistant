"""
Query Request Base Model

Platform-agnostic query request base class.
Platform-specific implementations (VizQL, Power BI, etc.) should inherit from this.

Architecture:
- QueryRequest: Abstract base for all platform query requests
- Used by QueryBuilder Node as output type
- Stored in workflow state
"""
from abc import ABC
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Dict, Optional, Any


class QueryRequest(BaseModel, ABC):
    """
    Abstract Query Request - Platform-agnostic base class
    
    All platform-specific query request types should inherit from this.
    This enables the workflow state to use a common type while allowing
    platform-specific implementations.
    
    Attributes:
        datasource: Datasource identifier (platform-specific format)
        fields: List of field specifications
        filters: Optional list of filter specifications
        sorts: Optional list of sort specifications
        row_limit: Optional row limit
    
    Example:
        class VizQLQueryRequest(QueryRequest):
            '''Tableau VizQL specific query request'''
            # Add VizQL-specific fields/methods
            pass
        
        class PowerBIQueryRequest(QueryRequest):
            '''Power BI specific query request'''
            # Add Power BI-specific fields/methods
            pass
    """
    model_config = ConfigDict(extra="forbid")
    
    datasource: Dict[str, Any] = Field(
        description="Datasource identifier (platform-specific format)"
    )
    
    fields: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Fields to query"
    )
    
    filters: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Filter conditions"
    )
    
    sorts: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Sort specifications"
    )
    
    row_limit: Optional[int] = Field(
        default=None,
        description="Maximum number of rows to return"
    )
    
    def to_api_dict(self) -> Dict[str, Any]:
        """Convert to API request dictionary.
        
        Subclasses may override this to customize serialization.
        """
        result = {
            "datasource": self.datasource,
            "fields": self.fields,
        }
        if self.filters:
            result["filters"] = self.filters
        if self.sorts:
            result["sorts"] = self.sorts
        if self.row_limit is not None:
            result["rowLimit"] = self.row_limit
        return result


__all__ = [
    "QueryRequest",
]
