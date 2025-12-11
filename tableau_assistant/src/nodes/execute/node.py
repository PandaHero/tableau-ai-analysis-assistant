"""
Execute Node

Pure code node that executes VizQL queries against VizQL Data Service.

Architecture:
- Receives VizQLQuery from QueryBuilder
- Uses VizQLClient from bi_platforms.tableau for API calls
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
from typing import Dict, Any, Optional, List
from datetime import datetime

from langgraph.types import RunnableConfig

from tableau_assistant.src.bi_platforms.tableau.vizql_client import VizQLClient
from tableau_assistant.src.models.workflow.context import get_tableau_config
from tableau_assistant.src.exceptions import VizQLError

logger = logging.getLogger(__name__)


from pydantic import BaseModel, Field, ConfigDict


class QueryResult(BaseModel):
    """
    Query execution result - Pydantic model
    
    Contains:
    - data: List of row dictionaries
    - columns: Column metadata
    - row_count: Number of rows returned
    - execution_time: Query execution time in seconds
    - error: Error message if query failed
    """
    model_config = ConfigDict(extra="forbid")
    
    data: List[Dict[str, Any]] = Field(default_factory=list)
    columns: List[Dict[str, Any]] = Field(default_factory=list)
    row_count: int = Field(default=0)
    execution_time: float = Field(default=0.0)
    error: Optional[str] = Field(default=None)
    query_id: Optional[str] = Field(default=None)
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    
    def is_success(self) -> bool:
        """Check if query was successful."""
        return self.error is None


class ExecuteNode:
    """
    Execute Node implementation.
    
    Uses VizQLClient for production-grade API calls with:
    - Connection pooling
    - Automatic retry with exponential backoff
    - Unified error handling
    """
    
    def __init__(self, client: Optional[VizQLClient] = None):
        """
        Initialize Execute Node.
        
        Args:
            client: VizQL client (created if not provided)
        """
        self._client = client
        self._owns_client = client is None
    
    def _get_client(self) -> VizQLClient:
        """Get or create VizQL client."""
        if self._client is None:
            self._client = VizQLClient()
            self._owns_client = True
        return self._client
    
    def _parse_response(
        self,
        response_data: Dict[str, Any],
        execution_time: float,
    ) -> QueryResult:
        """Parse VizQL API response into QueryResult."""
        try:
            # Extract data from response
            data = response_data.get("data", [])
            columns = response_data.get("columns", [])
            
            # Handle different response formats
            if isinstance(data, dict):
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
    
    async def execute(
        self,
        vizql_query: Any,
        datasource_luid: str,
        api_key: str,
        site: Optional[str] = None,
    ) -> QueryResult:
        """
        Execute a VizQL query.
        
        Args:
            vizql_query: VizQLQuery object or dict
            datasource_luid: Datasource LUID
            api_key: Tableau auth token
            site: Tableau site (optional)
            
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
        
        logger.info(f"Executing query against datasource: {datasource_luid}")
        logger.debug(f"Query: {query_dict}")
        
        start_time = time.time()
        
        try:
            client = self._get_client()
            response = await client.query_datasource_async(
                datasource_luid=datasource_luid,
                query=query_dict,
                api_key=api_key,
                site=site,
            )
            
            execution_time = time.time() - start_time
            return self._parse_response(response, execution_time)
            
        except VizQLError as e:
            execution_time = time.time() - start_time
            logger.error(f"VizQL API error: {e}")
            return QueryResult(
                error=str(e),
                execution_time=execution_time,
            )
        except Exception as e:
            execution_time = time.time() - start_time
            logger.exception(f"Query execution failed: {e}")
            return QueryResult(
                error=str(e),
                execution_time=execution_time,
            )
    
    def close(self):
        """Close client if owned."""
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None


async def execute_node(state: Dict[str, Any], config: RunnableConfig | None = None) -> Dict[str, Any]:
    """
    Execute node entry point for LangGraph.
    
    Args:
        state: VizQLState containing:
            - vizql_query: VizQLQuery object or dict (required)
            - datasource_luid: Datasource LUID (required, or from metadata)
            - api_key: Tableau auth token (optional, from config if not provided)
            - site: Tableau site (optional, from config if not provided)
        config: Optional configuration
        
    Returns:
        Updated state with query_result
    """
    logger.info("Execute node started")
    
    vizql_query = state.get("vizql_query")
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
    
    # Get datasource_luid from state or metadata
    datasource_luid = state.get("datasource_luid")
    if not datasource_luid:
        metadata = state.get("metadata")
        if metadata and hasattr(metadata, "datasource_luid"):
            datasource_luid = metadata.datasource_luid
    
    if not datasource_luid:
        # Fallback to environment variable
        datasource_luid = os.getenv("DATASOURCE_LUID", "")
    
    if not datasource_luid:
        logger.error("No datasource_luid provided")
        return {
            "errors": state.get("errors", []) + [{
                "node": "execute",
                "error": "No datasource_luid provided",
                "type": "missing_input",
            }],
            "execute_complete": True,
        }
    
    # Get Tableau credentials from state or global config
    api_key = state.get("api_key")
    site = state.get("site")
    
    if not api_key:
        # Try to get from global config via store_manager
        store_manager = state.get("store_manager")
        if store_manager:
            try:
                tableau_config = get_tableau_config(store_manager)
                if tableau_config:
                    api_key = tableau_config.get("tableau_token", "")
                    site = site or tableau_config.get("tableau_site", "")
            except Exception:
                pass
    
    if not api_key:
        # Fallback to environment variables
        api_key = os.getenv("TABLEAU_API_KEY", "") or os.getenv("TABLEAU_PAT_SECRET", "")
        site = site or os.getenv("TABLEAU_SITE", "")
    
    if not api_key:
        logger.error("No Tableau API key provided")
        return {
            "errors": state.get("errors", []) + [{
                "node": "execute",
                "error": "No Tableau API key provided",
                "type": "auth_error",
            }],
            "execute_complete": True,
        }
    
    executor = None
    try:
        # Execute query
        executor = ExecuteNode()
        result = await executor.execute(
            vizql_query=vizql_query,
            datasource_luid=datasource_luid,
            api_key=api_key,
            site=site,
        )
        
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
    finally:
        if executor:
            executor.close()
