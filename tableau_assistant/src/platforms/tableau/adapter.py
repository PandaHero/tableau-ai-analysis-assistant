"""Tableau Platform Adapter - Implements BasePlatformAdapter for Tableau.

This adapter handles the complete flow:
SemanticQuery → validate → build VizQL → execute → QueryResult
"""

import logging
from typing import Any

from ...core.interfaces import BasePlatformAdapter
from ...core.models import (
    ColumnInfo,
    QueryResult,
    SemanticQuery,
    ValidationResult,
)
from .query_builder import TableauQueryBuilder

logger = logging.getLogger(__name__)


class TableauAdapter(BasePlatformAdapter):
    """Tableau platform adapter.
    
    Converts SemanticQuery to VizQL API requests and executes them.
    """
    
    def __init__(self, vizql_client: Any = None):
        """Initialize Tableau adapter.
        
        Args:
            vizql_client: VizQL API client (lazy loaded if None)
        """
        self._vizql_client = vizql_client
        self._query_builder = TableauQueryBuilder()
    
    @property
    def platform_name(self) -> str:
        """Return platform name."""
        return "tableau"
    
    def _get_vizql_client(self):
        """Get or create VizQL client."""
        if self._vizql_client is None:
            # Lazy load from existing implementation
            try:
                from tableau_assistant.src.platforms.tableau.vizql_client import (
                    VizQLClient,
                )
                self._vizql_client = VizQLClient()
            except ImportError:
                logger.warning("VizQL client not available, using mock")
                self._vizql_client = MockVizQLClient()
        return self._vizql_client
    
    async def execute_query(
        self,
        semantic_query: SemanticQuery,
        datasource_id: str,
        **kwargs: Any,
    ) -> QueryResult:
        """Execute semantic query against Tableau.
        
        Args:
            semantic_query: Platform-agnostic semantic query
            datasource_id: Tableau datasource ID
            **kwargs: Additional parameters
            
        Returns:
            QueryResult with columns and rows
        """
        # Validate query
        validation = self.validate_query(semantic_query, **kwargs)
        if not validation.is_valid:
            error_msgs = [e.message for e in (validation.errors or [])]
            raise ValueError(f"Query validation failed: {'; '.join(error_msgs)}")
        
        # Build VizQL request
        vizql_request = self.build_query(
            semantic_query,
            datasource_id=datasource_id,
            **kwargs,
        )
        
        # Execute query
        client = self._get_vizql_client()
        
        try:
            response = await client.query_datasource(
                datasource_id=datasource_id,
                request=vizql_request,
            )
            
            # Convert response to QueryResult
            return self._convert_response(response)
            
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            raise
    
    def build_query(
        self,
        semantic_query: SemanticQuery,
        **kwargs: Any,
    ) -> dict:
        """Build VizQL request from SemanticQuery.
        
        Args:
            semantic_query: Platform-agnostic semantic query
            **kwargs: Additional parameters
            
        Returns:
            VizQL API request dictionary
        """
        return self._query_builder.build(semantic_query, **kwargs)
    
    def validate_query(
        self,
        semantic_query: SemanticQuery,
        **kwargs: Any,
    ) -> ValidationResult:
        """Validate semantic query for Tableau.
        
        Args:
            semantic_query: Query to validate
            **kwargs: Additional parameters
            
        Returns:
            ValidationResult
        """
        return self._query_builder.validate(semantic_query, **kwargs)
    
    def _convert_response(self, response: dict) -> QueryResult:
        """Convert VizQL response to QueryResult."""
        columns = []
        for col in response.get("columns", []):
            columns.append(ColumnInfo(
                name=col.get("fieldCaption", col.get("name", "")),
                data_type=col.get("dataType", "STRING"),
                is_dimension=col.get("fieldRole") == "DIMENSION",
                is_measure=col.get("fieldRole") == "MEASURE",
                is_computation=col.get("columnClass") == "TABLE_CALCULATION",
            ))
        
        rows = response.get("data", [])
        row_count = response.get("rowCount", len(rows))
        execution_time = response.get("executionTimeMs", 0)
        
        return QueryResult(
            columns=columns,
            rows=rows,
            row_count=row_count,
            execution_time_ms=execution_time,
        )


class MockVizQLClient:
    """Mock VizQL client for testing."""
    
    async def query_datasource(
        self,
        datasource_id: str,
        request: dict,
    ) -> dict:
        """Mock query execution."""
        logger.warning("Using mock VizQL client - no actual query executed")
        return {
            "columns": [],
            "data": [],
            "rowCount": 0,
        }
