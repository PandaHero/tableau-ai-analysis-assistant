"""
Execute VizQL Query Tool - VizQL 查询执行工具

封装 QueryExecutor 组件为 LangChain 工具，用于执行 VizQL 查询。
"""
import json
import logging
from typing import Optional
from langchain_core.tools import tool

from tableau_assistant.src.capabilities.query.executor.query_executor import QueryExecutor, QueryExecutionError
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
    
    Args:
        query_json: JSON string of VizQLQuery object with fields and filters
        datasource_luid: Tableau datasource LUID (unique identifier)
        tableau_token: Tableau API authentication token
        tableau_domain: Tableau server domain (e.g., "https://tableau.example.com")
        tableau_site: Optional Tableau site name (for multi-site deployments)
        enable_retry: Whether to enable automatic retries (default: True)
        max_retries: Maximum number of retry attempts (default: 3)
    
    Returns:
        Dictionary with data, row_count, columns, and performance metrics
    
    Raises:
        ValueError: If input validation fails
        RuntimeError: If query execution fails after all retries
    """
    try:
        query_dict = json.loads(query_json)
        query = VizQLQuery(**query_dict)
        
        tableau_config = {
            "tableau_token": tableau_token,
            "tableau_domain": tableau_domain,
        }
        if tableau_site:
            tableau_config["tableau_site"] = tableau_site
        
        executor = QueryExecutor(max_retries=max_retries, retry_delay=1.0, timeout=30)
        
        logger.info(f"Executing VizQL query: datasource={datasource_luid}, fields={len(query.fields)}")
        
        result = executor.execute_query(
            query=query,
            datasource_luid=datasource_luid,
            tableau_config=tableau_config,
            enable_retry=enable_retry
        )
        
        if "raw_result" in result:
            del result["raw_result"]
        
        logger.info(f"Query executed successfully: {result['row_count']} rows")
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
