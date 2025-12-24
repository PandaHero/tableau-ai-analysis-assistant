# -*- coding: utf-8 -*-
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

Note:
- 大数据处理由 Insight 节点的 AnalysisCoordinator 负责（Profiling + Chunking）
- 查询结果直接通过 State 传递，不需要额外的文件存储
"""

import logging
import time
from typing import Any, Dict, List, Optional

from langgraph.types import RunnableConfig

from tableau_assistant.src.platforms.tableau.vizql_client import VizQLClient
from tableau_assistant.src.core.models.execute_result import ExecuteResult
from tableau_assistant.src.platforms.tableau.models import VizQLQueryRequest as VizQLQuery
from tableau_assistant.src.infra.exceptions import VizQLError
from tableau_assistant.src.core.state import VizQLState

logger = logging.getLogger(__name__)


class ExecuteNode:
    """Execute Node implementation."""
    
    def __init__(self, client: Optional[VizQLClient] = None):
        self._client = client
        self._owns_client = client is None
    
    def _get_client(self, domain: Optional[str] = None) -> VizQLClient:
        if self._client is None:
            from tableau_assistant.src.platforms.tableau.vizql_client import VizQLClientConfig
            from tableau_assistant.src.infra.config.settings import settings
            from tableau_assistant.src.infra.config.tableau_env import get_tableau_config
            
            tableau_config = get_tableau_config(domain)
            config = VizQLClientConfig(
                base_url=tableau_config.domain,
                verify_ssl=settings.vizql_verify_ssl,
                ca_bundle=settings.vizql_ca_bundle or None,
                timeout=settings.vizql_timeout,
                max_retries=settings.vizql_max_retries,
            )
            self._client = VizQLClient(config=config)
            self._owns_client = True
        return self._client
    
    def _round_numeric_values(self, data: List[Dict[str, Any]], precision: int) -> List[Dict[str, Any]]:
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

    def _parse_response(self, response_data: Dict[str, object], execution_time: float) -> ExecuteResult:
        try:
            data = response_data.get("data", [])
            columns = response_data.get("columns", [])
            
            if isinstance(data, dict):
                rows = []
                if "rows" in data:
                    rows = data["rows"]
                elif "values" in data:
                    col_names = [c.get("fieldCaption", f"col_{i}") for i, c in enumerate(columns)]
                    rows = [dict(zip(col_names, row)) for row in data["values"]]
                data = rows
            
            from tableau_assistant.src.infra.config.settings import settings
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
            return ExecuteResult(error=f"Response parsing error: {e}", execution_time=execution_time)
    
    async def execute(
        self,
        vizql_query: "VizQLQuery",
        datasource_luid: str,
        api_key: str,
        site: Optional[str] = None,
        domain: Optional[str] = None,
    ) -> ExecuteResult:
        if hasattr(vizql_query, "model_dump"):
            query_dict = vizql_query.model_dump(exclude_none=True)
        elif hasattr(vizql_query, "to_dict"):
            query_dict = vizql_query.to_dict()
        elif isinstance(vizql_query, dict):
            query_dict = vizql_query
        else:
            return ExecuteResult(error="Invalid query format")
        
        query_dict.pop("datasource", None)
        logger.info(f"Executing query against datasource: {datasource_luid}")
        logger.debug(f"Query: {query_dict}")
        
        start_time = time.time()
        try:
            client = self._get_client(domain=domain)
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
            return ExecuteResult(error=str(e), execution_time=execution_time)
        except Exception as e:
            execution_time = time.time() - start_time
            logger.exception(f"Query execution failed: {e}")
            return ExecuteResult(error=str(e), execution_time=execution_time)
    
    def close(self):
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None


async def execute_node(state: VizQLState, config: RunnableConfig | None = None) -> Dict[str, object]:
    """Execute node entry point for LangGraph."""
    logger.info("Execute node started")
    
    vizql_query = state.get("vizql_query")
    if not vizql_query:
        logger.error("No vizql_query in state")
        return {
            "errors": state.get("errors", []) + [{"node": "execute", "error": "No vizql_query provided", "type": "missing_input"}],
            "execute_complete": True,
        }
    
    datasource_luid = state.get("datasource_luid")
    if not datasource_luid:
        data_model = state.get("data_model")
        if data_model and hasattr(data_model, "datasource_luid"):
            datasource_luid = data_model.datasource_luid
    if not datasource_luid:
        from tableau_assistant.src.infra.config.settings import settings
        datasource_luid = settings.datasource_luid
    if not datasource_luid:
        logger.error("No datasource_luid provided")
        return {
            "errors": state.get("errors", []) + [{"node": "execute", "error": "No datasource_luid provided", "type": "missing_input"}],
            "execute_complete": True,
        }
    
    from tableau_assistant.src.platforms.tableau import ensure_valid_auth_async, TableauAuthError
    
    try:
        auth_ctx = await ensure_valid_auth_async(config)
        api_key = auth_ctx.api_key
        site = auth_ctx.site
        domain = auth_ctx.domain
        logger.debug(f"使用 Tableau 认证 (method={auth_ctx.auth_method}, domain={domain}, remaining={auth_ctx.remaining_seconds:.0f}s)")
    except TableauAuthError as e:
        logger.error(f"Tableau 认证失败: {e}")
        return {
            "errors": state.get("errors", []) + [{"node": "execute", "error": str(e), "type": "auth_error"}],
            "execute_complete": True,
        }
    
    executor = None
    try:
        executor = ExecuteNode()
        result = await executor.execute(
            vizql_query=vizql_query,
            datasource_luid=datasource_luid,
            api_key=api_key,
            site=site,
            domain=domain,
        )
        
        if result.is_success():
            logger.info(f"Execute node completed: {result.row_count} rows returned")
            return {"query_result": result, "execute_complete": True}
        else:
            logger.error(f"Query execution failed: {result.error}")
            return {
                "query_result": result,
                "errors": state.get("errors", []) + [{"node": "execute", "error": result.error, "type": "query_error"}],
                "execute_complete": True,
            }
    except Exception as e:
        logger.exception(f"Execute node failed: {e}")
        return {
            "errors": state.get("errors", []) + [{"node": "execute", "error": str(e), "type": "execution_error"}],
            "execute_complete": True,
        }
    finally:
        if executor:
            executor.close()
