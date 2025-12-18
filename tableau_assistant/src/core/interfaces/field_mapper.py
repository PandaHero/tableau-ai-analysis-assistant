"""Field mapper interface.

Abstract base class for field mapping.
Maps business terms to platform-specific technical field names.
"""

from abc import ABC, abstractmethod
from typing import Any

from ..models import SemanticQuery


class BaseFieldMapper(ABC):
    """Abstract base class for field mappers.
    
    Field mappers convert business terms (e.g., "销售额", "省份") to
    platform-specific technical field names (e.g., "[Sales].[Amount]").
    
    The existing two-stage retrieval (RAG + LLM) approach is preserved:
    1. RAG retrieval: Find candidate fields using vector similarity
    2. LLM selection: Select the best match from candidates
    """
    
    @abstractmethod
    async def map(
        self,
        semantic_query: SemanticQuery,
        datasource_id: str,
        **kwargs: Any,
    ) -> SemanticQuery:
        """Map all fields in a semantic query to technical field names.
        
        Maps fields in:
        - dimensions[].field_name
        - measures[].field_name
        - computations[].target
        - computations[].partition_by[]
        - filters[].field_name
        - sorts[].field_name
        
        Args:
            semantic_query: Query with business terms
            datasource_id: Platform-specific datasource identifier
            **kwargs: Additional parameters
            
        Returns:
            SemanticQuery with technical field names
        """
        pass
    
    @abstractmethod
    async def map_single_field(
        self,
        field_name: str,
        datasource_id: str,
        **kwargs: Any,
    ) -> str:
        """Map a single business term to technical field name.
        
        Args:
            field_name: Business term (e.g., "销售额")
            datasource_id: Platform-specific datasource identifier
            **kwargs: Additional parameters
            
        Returns:
            Technical field name (e.g., "[Sales].[Amount]")
        """
        pass
