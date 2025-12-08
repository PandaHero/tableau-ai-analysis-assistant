"""
Execute Node

Pure code node that executes VizQL queries against VizQL Data Service.

Architecture:
- Receives VizQLQuery from QueryBuilder
- Builds API request
- Calls VizQL Data Service API
- Parses response into QueryResult

Requirements:
- R7.1: Execute VizQL API call
- R7.2: Parse API response
- R7.3: Error handling
- R7.4: Large result handling (via FilesystemMiddleware)
"""

import logging
import os
import time
import httpx
from typing import Dict, Any, Optional, List, TYPE_CHECKING
from dataclasses import dataclass, field
from datetime import datetime

from langgraph.types import RunnableConfig

logger = logging.getLogger(__name__)


@dataclass
class QueryResult:
    """
    Query execution result
    
    Contains:
    - data: List of row dictionaries
    - columns: Column metadata
    - row_count: Number of rows returned
    - execution_time: Query execution time in seconds
    - error: Error message if query failed
    """
    data: List[Dict[str, Any]] = field(default_factory=list)
    columns: List[Dict[str, Any]] = field(default_factory=list)
    row_count: int = 0
    execution_time: float = 0.0
    error: Optional[str] = None
    query_id: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def is_success(self) -> bool:
        """Check if query was successful."""
        return self.error is None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "data": self.data,
            "columns": self.columns,
            "row_count": self.row_count,
            "execution_time": self.execution_time,
            "error": self.error,
            "query_id": self.query_id,
            "timestamp": self.timestamp,
        }


class VizQLDataServiceClient:
    """
    Client for VizQL Data Service API.
    
    Handles:
    - Authentication
    - Request building
    - Response parsing
    - Error handling
    """
    
    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: float = 60.0,
    ):
        """
        Initialize client.
        
        Args:
            base_url: VDS base URL (from env if not provided)
            api_key: API key for authentication
            timeout: Request timeout in seconds
        """
        self.base_url = base_url or os.getenv("VDS_BASE_URL", "")
        self.api_key = api_key or os.getenv("VDS_API_KEY", "")
        self.timeout = timeout
        
        # Tableau credentials
        self.tableau_server = os.getenv("TABLEAU_SERVER_URL", "")
        self.site_id = os.getenv("TABLEAU_SITE_ID", "")
        self.pat_name = os.getenv("TABLEAU_PAT_NAME", "")
        self.pat_secret = os.getenv("TABLEAU_PAT_SECRET", "")
    
    async def query(
        self,
        datasource_name: str,
        query: Dict[str, Any],
    ) -> QueryResult:
        """
        Execute a query against VizQL Data Service.
        
        Args:
            datasource_name: Name of the datasource
            query: VizQL query specification
            
        Returns:
            QueryResult with data or error
        """
        if not self.base_url:
            logger.warning("VDS_BASE_URL not configured, returning mock result")
            return self._mock_result(query)
        
        start_time = time.time()
        
        try:
            # Build request
            request_body = {
                "datasource": {
                    "datasourceName": datasource_name,
                },
                "query": query,
            }
            
            # Add authentication headers
            headers = self._build_headers()
            
            # Make request
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/query-datasource",
                    json=request_body,
                    headers=headers,
                )
                
                execution_time = time.time() - start_time
                
                if response.status_code == 200:
                    return self._parse_response(response.json(), execution_time)
                else:
                    return QueryResult(
                        error=f"API error: {response.status_code} - {response.text}",
                        execution_time=execution_time,
                    )
        
        except httpx.TimeoutException:
            return QueryResult(
                error="Query timeout",
                execution_time=time.time() - start_time,
            )
        except Exception as e:
            logger.exception(f"Query execution failed: {e}")
            return QueryResult(
                error=str(e),
                execution_time=time.time() - start_time,
            )
    
    def _build_headers(self) -> Dict[str, str]:
        """Build request headers with authentication."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        
        # Add Tableau credentials if available
        if self.pat_name and self.pat_secret:
            headers["X-Tableau-Auth"] = f"{self.pat_name}:{self.pat_secret}"
        
        return headers
    
    def _parse_response(
        self,
        response_data: Dict[str, Any],
        execution_time: float,
    ) -> QueryResult:
        """Parse API response into QueryResult."""
        try:
            # Extract data from response
            data = response_data.get("data", [])
            columns = response_data.get("columns", [])
            
            # Handle different response formats
            if isinstance(data, dict):
                # Object format
                rows = []
                if "rows" in data:
                    rows = data["rows"]
                elif "values" in data:
                    # Array format - convert to objects
                    col_names = [c.get("fieldCaption", f"col_{i}") for i, c in enumerate(columns)]
                    rows = [dict(zip(col_names, row)) for row in data["values"]]
                data = rows
            
            return QueryResult(
                data=data,
                columns=columns,
                row_count=len(data),
                execution_time=execution_time,
                query_id=response_data.get("queryId"),
            )
        
        except Exception as e:
            logger.exception(f"Failed to parse response: {e}")
            return QueryResult(
                error=f"Response parsing error: {e}",
                execution_time=execution_time,
            )
    
    def _mock_result(self, query: Dict[str, Any]) -> QueryResult:
        """Generate mock result for testing without VDS."""
        logger.info("Generating mock result (VDS not configured)")
        
        # Extract field names from query
        fields = query.get("fields", [])
        columns = []
        for f in fields:
            if isinstance(f, dict):
                col_name = f.get("fieldAlias") or f.get("fieldCaption", "unknown")
            else:
                col_name = str(f)
            columns.append({"fieldCaption": col_name, "dataType": "STRING"})
        
        # Generate mock data
        mock_data = []
        for i in range(5):
            row = {}
            for col in columns:
                col_name = col["fieldCaption"]
                if "date" in col_name.lower():
                    row[col_name] = f"2024-{(i % 12) + 1:02d}-01"
                elif any(kw in col_name.lower() for kw in ["sales", "amount", "revenue", "profit"]):
                    row[col_name] = 1000 * (i + 1)
                elif any(kw in col_name.lower() for kw in ["count", "qty", "quantity"]):
                    row[col_name] = 10 * (i + 1)
                else:
                    row[col_name] = f"Value_{i + 1}"
            mock_data.append(row)
        
        return QueryResult(
            data=mock_data,
            columns=columns,
            row_count=len(mock_data),
            execution_time=0.1,
            query_id="mock_query_id",
        )


class ExecuteNode:
    """
    Execute Node implementation.
    
    Executes VizQL queries and returns results.
    """
    
    def __init__(self, client: Optional[VizQLDataServiceClient] = None):
        """
        Initialize Execute Node.
        
        Args:
            client: VizQL Data Service client (created if not provided)
        """
        self.client = client or VizQLDataServiceClient()
    
    async def execute(
        self,
        vizql_query: Any,
        datasource: str,
    ) -> QueryResult:
        """
        Execute a VizQL query.
        
        Args:
            vizql_query: VizQLQuery object
            datasource: Datasource name
            
        Returns:
            QueryResult with data or error
        """
        # Convert query to dict if needed
        if hasattr(vizql_query, "to_dict"):
            query_dict = vizql_query.to_dict()
        elif isinstance(vizql_query, dict):
            query_dict = vizql_query
        else:
            return QueryResult(error="Invalid query format")
        
        logger.info(f"Executing query against datasource: {datasource}")
        logger.debug(f"Query: {query_dict}")
        
        return await self.client.query(datasource, query_dict)


async def execute_node(state: Dict[str, Any], config: RunnableConfig | None = None) -> Dict[str, Any]:
    """
    Execute node entry point for LangGraph.
    
    Args:
        state: VizQLState containing vizql_query and datasource
        config: Optional configuration
        
    Returns:
        Updated state with query_result
    """
    logger.info("Execute node started")
    
    vizql_query = state.get("vizql_query")
    datasource = state.get("datasource", "")
    
    if not vizql_query:
        logger.error("No vizql_query in state")
        return {
            "errors": state.get("errors", []) + [{
                "node": "execute",
                "error": "No vizql_query provided",
                "type": "missing_input",
            }],
            "execute_complete": True,
        }
    
    if not datasource:
        logger.warning("No datasource specified, using default")
        datasource = os.getenv("DEFAULT_DATASOURCE", "Sample - Superstore")
    
    try:
        # Execute query
        executor = ExecuteNode()
        result = await executor.execute(vizql_query, datasource)
        
        if result.is_success():
            logger.info(f"Execute node completed: {result.row_count} rows returned")
            return {
                "query_result": result,
                "execute_complete": True,
            }
        else:
            logger.error(f"Query execution failed: {result.error}")
            return {
                "query_result": result,
                "errors": state.get("errors", []) + [{
                    "node": "execute",
                    "error": result.error,
                    "type": "query_error",
                }],
                "execute_complete": True,
            }
    
    except Exception as e:
        logger.exception(f"Execute node failed: {e}")
        return {
            "errors": state.get("errors", []) + [{
                "node": "execute",
                "error": str(e),
                "type": "execution_error",
            }],
            "execute_complete": True,
        }
