"""
Execute Node

Pure code node that executes VizQL queries against VizQL Data Service.

Architecture:
- Receives VizQLQuery from QueryBuilder
- Uses VizQLClient from bi_platforms.tableau for API calls
- Parses response into ExecuteResult

Requirements:
- R7.1: Execute VizQL API call
- R7.2: Parse API response
- R7.3: Error handling
- R7.4: Large result handling (via FilesystemMiddleware)
"""

import logging
import os
import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from langgraph.types import RunnableConfig

from tableau_assistant.src.bi_platforms.tableau.vizql_client import VizQLClient
from tableau_assistant.src.models.vizql.execute_result import ExecuteResult
from tableau_assistant.src.exceptions import VizQLError

if TYPE_CHECKING:
    from tableau_assistant.src.models.workflow.state import VizQLState
    from tableau_assistant.src.models.vizql.types import VizQLQuery

logger = logging.getLogger(__name__)


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
    
    def _round_numeric_values(self, data: List[Dict[str, Any]], precision: int) -> List[Dict[str, Any]]:
        """
        对数据中的浮点数进行四舍五入。
        
        Args:
            data: 原始数据行列表
            precision: 小数位数
            
        Returns:
            处理后的数据
        """
        if precision < 0:
            return data
        
        rounded_data = []
        for row in data:
            rounded_row = {}
            for key, value in row.items():
                if isinstance(value, float):
                    rounded_row[key] = round(value, precision)
                else:
                    rounded_row[key] = value
            rounded_data.append(rounded_row)
        return rounded_data
    
    def _parse_response(
        self,
        response_data: Dict[str, object],
        execution_time: float,
    ) -> ExecuteResult:
        """Parse VizQL API response into ExecuteResult."""
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
            
            # 对浮点数进行四舍五入（根据配置）
            from tableau_assistant.src.config.settings import settings
            data = self._round_numeric_values(data, settings.decimal_precision)
            
            return ExecuteResult(
                data=data,
                columns=columns,
                row_count=len(data),
                execution_time=execution_time,
                query_id=response_data.get("queryId"),
            )
        
        except Exception as e:
            logger.exception(f"Failed to parse response: {e}")
            return ExecuteResult(
                error=f"Response parsing error: {e}",
                execution_time=execution_time,
            )
    
    async def execute(
        self,
        vizql_query: "VizQLQuery",
        datasource_luid: str,
        api_key: str,
        site: Optional[str] = None,
    ) -> ExecuteResult:
        """
        Execute a VizQL query.
        
        Args:
            vizql_query: VizQLQuery object or dict
            datasource_luid: Datasource LUID
            api_key: Tableau auth token
            site: Tableau site (optional)
            
        Returns:
            ExecuteResult with data or error
        """
        # Convert query to dict if needed
        if hasattr(vizql_query, "model_dump"):
            # Pydantic v2 model
            query_dict = vizql_query.model_dump(exclude_none=True)
        elif hasattr(vizql_query, "to_dict"):
            # Legacy or custom to_dict method
            query_dict = vizql_query.to_dict()
        elif isinstance(vizql_query, dict):
            query_dict = vizql_query
        else:
            return ExecuteResult(error="Invalid query format")
        
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
            return ExecuteResult(
                error=str(e),
                execution_time=execution_time,
            )
        except Exception as e:
            execution_time = time.time() - start_time
            logger.exception(f"Query execution failed: {e}")
            return ExecuteResult(
                error=str(e),
                execution_time=execution_time,
            )
    
    def close(self):
        """Close client if owned."""
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None


async def execute_node(state: "VizQLState", config: RunnableConfig | None = None) -> Dict[str, object]:
    """
    Execute node entry point for LangGraph.
    
    认证机制：
    - 优先从 config["configurable"]["tableau_auth"] 获取认证信息
    - 如果 config 中没有或已过期，则调用 ensure_valid_auth() 获取新 token
    
    Args:
        state: VizQLState containing:
            - vizql_query: VizQLQuery object or dict (required)
            - datasource_luid: Datasource LUID (required, or from metadata)
        config: RunnableConfig containing:
            - configurable.tableau_auth: TableauAuthContext (from executor)
        
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
        # Fallback to settings
        from tableau_assistant.src.config.settings import settings
        datasource_luid = settings.datasource_luid
    
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
    
    # 从 RunnableConfig 获取 Tableau 认证（由 executor 在工作流启动时设置）
    from tableau_assistant.src.bi_platforms.tableau import (
        ensure_valid_auth_async,
        TableauAuthError,
    )
    
    try:
        auth_ctx = await ensure_valid_auth_async(config)
        api_key = auth_ctx.api_key
        site = auth_ctx.site
        logger.debug(f"使用 Tableau 认证 (method={auth_ctx.auth_method}, remaining={auth_ctx.remaining_seconds:.0f}s)")
    except TableauAuthError as e:
        logger.error(f"Tableau 认证失败: {e}")
        return {
            "errors": state.get("errors", []) + [{
                "node": "execute",
                "error": str(e),
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
