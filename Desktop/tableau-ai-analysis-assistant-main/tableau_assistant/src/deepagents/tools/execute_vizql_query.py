"""
Execute VizQL Query Tool - VizQL 查询执行工具

封装 QueryExecutor 组件为 LangChain 工具，用于执行 VizQL 查询。
"""
import json
import logging
from typing import Optional
from langchain_core.tools import tool

from tableau_assistant.src.components.query_executor import QueryExecutor, QueryExecutionError
from tableau_assistant.src.models.vizql_types import VizQLQuery

logger = logging.getLogger(__name__)


@tool
def execute_vizql_query(
    query_json: str,
    datasource_luid: str,
    tableau_token: str,
    tableau_domain: str,
    tableau_site: Optional[str] = None,
    enable_retry: bool = True,
    max_retries: int = 3
) -> dict:
    """Execute a VizQL query against Tableau.
    
    This tool executes a VizQL query using the Tableau VizQL Data Service API.
    It includes automatic retry logic for transient failures and comprehensive
    error handling.
    
    The tool handles:
    - Query validation
    - Automatic retries for network/timeout errors
    - Error classification and reporting
    - Performance monitoring
    - Result parsing and formatting
    
    Args:
        query_json: JSON string of VizQLQuery object with fields:
            - fields: List of field objects (BasicField, FunctionField, or CalculationField)
            - filters: Optional list of filter objects
        datasource_luid: Tableau datasource LUID (unique identifier)
        tableau_token: Tableau API authentication token
        tableau_domain: Tableau server domain (e.g., "https://tableau.example.com")
        tableau_site: Optional Tableau site name (for multi-site deployments)
        enable_retry: Whether to enable automatic retries (default: True)
        max_retries: Maximum number of retry attempts (default: 3)
    
    Returns:
        Dictionary with:
            - data: List of data rows as dictionaries
            - row_count: Number of rows returned
            - columns: List of column names
            - query_time_ms: Query execution time in milliseconds
            - execution_time_ms: Total execution time including retries
            - retry_count: Number of retries performed
            - performance: Performance metrics including:
                - execution_time: Execution time in seconds
                - row_count: Number of rows
                - fields_count: Number of fields in query
                - filters_count: Number of filters in query
                - retry_count: Number of retries
    
    Raises:
        ValueError: If input validation fails
        RuntimeError: If query execution fails after all retries
    
    Examples:
        # Simple query
        >>> execute_vizql_query(
        ...     query_json='{"fields": [{"fieldCaption": "Sales", "function": "SUM"}], "filters": null}',
        ...     datasource_luid="abc-123-def",
        ...     tableau_token="your-token",
        ...     tableau_domain="https://tableau.example.com"
        ... )
        {"data": [...], "row_count": 100, "columns": ["Sales"], ...}
        
        # Query with filters
        >>> execute_vizql_query(
        ...     query_json='{"fields": [...], "filters": [{"filterType": "SET", ...}]}',
        ...     datasource_luid="abc-123-def",
        ...     tableau_token="your-token",
        ...     tableau_domain="https://tableau.example.com",
        ...     tableau_site="my-site"
        ... )
        {"data": [...], "row_count": 50, ...}
    """
    try:
        # Parse query JSON
        query_dict = json.loads(query_json)
        query = VizQLQuery(**query_dict)
        
        # Build Tableau config
        tableau_config = {
            "tableau_token": tableau_token,
            "tableau_domain": tableau_domain,
        }
        if tableau_site:
            tableau_config["tableau_site"] = tableau_site
        
        # Create executor with retry configuration
        executor = QueryExecutor(
            max_retries=max_retries,
            retry_delay=1.0,
            timeout=30
        )
        
        logger.info(
            f"Executing VizQL query: datasource={datasource_luid}, "
            f"fields={len(query.fields)}, "
            f"filters={len(query.filters) if query.filters else 0}"
        )
        
        # Execute query
        result = executor.execute_query(
            query=query,
            datasource_luid=datasource_luid,
            tableau_config=tableau_config,
            enable_retry=enable_retry
        )
        
        # Remove raw_result to reduce response size
        if "raw_result" in result:
            del result["raw_result"]
        
        logger.info(
            f"Query executed successfully: {result['row_count']} rows, "
            f"{result['execution_time_ms']}ms, "
            f"{result['retry_count']} retries"
        )
        
        return result
    
    except json.JSONDecodeError as e:
        error_msg = f"Invalid query JSON: {str(e)}"
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    except QueryExecutionError as e:
        error_msg = f"Query execution failed ({e.error_type.value}): {str(e)}"
        logger.error(error_msg)
        raise RuntimeError(error_msg)
    
    except Exception as e:
        error_msg = f"Unexpected error executing query: {str(e)}"
        logger.error(error_msg)
        raise RuntimeError(error_msg)


__all__ = ["execute_vizql_query"]
