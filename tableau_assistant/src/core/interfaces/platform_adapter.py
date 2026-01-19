"""Platform adapter interface.

Abstract base class for platform-specific adapters.
Each BI platform (Tableau, Power BI, Superset) implements this interface.
"""

from abc import ABC, abstractmethod
from typing import Any

from tableau_assistant.src.core.models import ExecuteResult, SemanticQuery, ValidationResult



class BasePlatformAdapter(ABC):
    """Abstract base class for platform adapters.
    
    Platform adapters convert SemanticQuery to platform-specific queries
    and execute them against the BI platform.
    
    Implementations:
    - TableauAdapter: Converts to VizQL API calls
    - PowerBIAdapter: Converts to DAX queries (future)
    - SupersetAdapter: Converts to SQL queries (future)
    """
    
    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Return the platform name (e.g., 'tableau', 'powerbi', 'superset')."""
        pass
    
    @abstractmethod
    async def execute_query(
        self,
        semantic_query: SemanticQuery,
        datasource_id: str,
        **kwargs: Any,
    ) -> ExecuteResult:
        """Execute a semantic query against the platform.
        
        This is the main entry point for query execution.
        It handles the full pipeline: validate → build → execute.
        
        Args:
            semantic_query: Platform-agnostic semantic query
            datasource_id: Platform-specific datasource identifier
            **kwargs: Additional platform-specific parameters
            
        Returns:
            ExecuteResult with columns and data
            
        Raises:
            ValidationError: If query validation fails
            ExecutionError: If query execution fails
        """
        pass
    
    @abstractmethod
    def build_query(
        self,
        semantic_query: SemanticQuery,
        **kwargs: Any,
    ) -> Any:
        """Build platform-specific query from SemanticQuery.
        
        Converts the platform-agnostic SemanticQuery to the platform's
        native query format (e.g., VizQL request, DAX query, SQL).
        
        Args:
            semantic_query: Platform-agnostic semantic query
            **kwargs: Additional platform-specific parameters
            
        Returns:
            Platform-specific query object
        """
        pass
    
    @abstractmethod
    def validate_query(
        self,
        semantic_query: SemanticQuery,
        **kwargs: Any,
    ) -> ValidationResult:
        """Validate a semantic query for this platform.
        
        Checks if the query can be executed on this platform.
        May auto-fix minor issues (e.g., fill default values).
        
        Args:
            semantic_query: Platform-agnostic semantic query
            **kwargs: Additional platform-specific parameters
            
        Returns:
            ValidationResult with is_valid, errors, warnings, auto_fixed
        """
        pass
