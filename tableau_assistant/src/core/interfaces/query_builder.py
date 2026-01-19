"""Query builder interface.

Abstract base class for platform-specific query builders.
Converts SemanticQuery to platform-native query format.
"""

from abc import ABC, abstractmethod
from typing import Any

from tableau_assistant.src.core.models import SemanticQuery, ValidationResult



class BaseQueryBuilder(ABC):
    """Abstract base class for query builders.
    
    Query builders convert SemanticQuery to platform-specific query format.
    They handle the conversion of:
    - Dimensions → Platform dimension syntax
    - Measures → Platform measure syntax
    - Computations → Platform calculation syntax (e.g., TableCalc, DAX, window functions)
    - Filters → Platform filter syntax
    
    The key conversion is Computation.partition_by:
    - Tableau: partition_by → Partitioning/Addressing in Table Calculations
    - Power BI: partition_by → ALL/ALLEXCEPT in DAX
    - SQL: partition_by → PARTITION BY in window functions
    """
    
    @abstractmethod
    def build(
        self,
        semantic_query: SemanticQuery,
        **kwargs: Any,
    ) -> Any:
        """Build platform-specific query from SemanticQuery.
        
        Args:
            semantic_query: Platform-agnostic semantic query
            **kwargs: Additional platform-specific parameters
            
        Returns:
            Platform-specific query object
        """
        pass
    
    @abstractmethod
    def validate(
        self,
        semantic_query: SemanticQuery,
        **kwargs: Any,
    ) -> ValidationResult:
        """Validate semantic query for this platform.
        
        Checks if the query can be built for this platform.
        May auto-fix minor issues (e.g., fill default aggregation).
        
        Args:
            semantic_query: Platform-agnostic semantic query
            **kwargs: Additional platform-specific parameters
            
        Returns:
            ValidationResult with is_valid, errors, warnings, auto_fixed
        """
        pass
