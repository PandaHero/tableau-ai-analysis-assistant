"""
VizQL Query Middleware

自动注入 VizQL 查询执行工具的中间件。

设计原则：
- 只负责工具注入，不管理提示词
- 提示词由现有的 Prompt 类系统管理
- 复用现有的 QueryExecutor 组件
"""
from typing import Dict, Any, List
from langchain_core.tools import tool
import logging

logger = logging.getLogger(__name__)


class VizQLQueryMiddleware:
    """
    VizQL 查询中间件
    
    职责：
    - 注入 execute_vizql_query 工具
    - 不设置系统提示词（使用现有 Prompt 类）
    
    使用方式：
        middleware = VizQLQueryMiddleware()
        agent = create_deep_agent(
            middleware=[middleware, ...],
            ...
        )
    """
    
    def __init__(self):
        """初始化中间件"""
        self.tools = [self._create_query_tool()]
        logger.info("VizQLQueryMiddleware initialized")
    
    def _create_query_tool(self):
        """
        创建 VizQL 查询执行工具
        
        Returns:
            LangChain tool 对象
        """
        @tool
        def execute_vizql_query(
            query: Dict[str, Any],
            datasource_luid: str
        ) -> Dict[str, Any]:
            """Execute a VizQL query against a Tableau datasource.
            
            This tool executes a VizQL query and returns the results. VizQL is Tableau's
            query language for data visualization and analysis.
            
            Args:
                query: VizQL query object with structure:
                    {
                        "dimensions": [
                            {
                                "field": "field_name",
                                "aggregation": "none" | "year" | "quarter" | "month",
                                "alias": "optional_alias"
                            }
                        ],
                        "measures": [
                            {
                                "field": "field_name",
                                "aggregation": "sum" | "avg" | "count" | "min" | "max",
                                "alias": "optional_alias"
                            }
                        ],
                        "filters": [
                            {
                                "field": "field_name",
                                "operator": "=" | "!=" | ">" | "<" | ">=" | "<=",
                                "value": filter_value
                            }
                        ],
                        "date_filters": [
                            {
                                "field": "date_field_name",
                                "range_type": "between" | "last_n_days" | "this_year",
                                "start_date": "YYYY-MM-DD",
                                "end_date": "YYYY-MM-DD"
                            }
                        ],
                        "limit": 1000,
                        "order_by": [
                            {
                                "field": "field_name",
                                "direction": "asc" | "desc"
                            }
                        ]
                    }
                datasource_luid: The unique identifier (LUID) of the Tableau datasource.
                    Format: 32-character hexadecimal string
            
            Returns:
                Dictionary containing:
                    - data: List of data rows as dictionaries
                    - columns: List of column names
                    - row_count: Number of rows returned
                    - execution_time_ms: Query execution time in milliseconds
                    - metadata: Additional query metadata
            
            Examples:
                # Simple aggregation query
                >>> execute_vizql_query(
                ...     query={
                ...         "measures": [
                ...             {"field": "Sales", "aggregation": "sum"}
                ...         ],
                ...         "dimensions": [
                ...             {"field": "Region", "aggregation": "none"}
                ...         ]
                ...     },
                ...     datasource_luid="a1b2c3d4-e5f6-7890-abcd-ef1234567890"
                ... )
                {
                    "data": [
                        {"Region": "East", "Sales": 125000},
                        {"Region": "West", "Sales": 98000}
                    ],
                    "columns": ["Region", "Sales"],
                    "row_count": 2,
                    "execution_time_ms": 245
                }
                
                # Query with filters and date grouping
                >>> execute_vizql_query(
                ...     query={
                ...         "measures": [
                ...             {"field": "Sales", "aggregation": "sum"}
                ...         ],
                ...         "dimensions": [
                ...             {"field": "Order Date", "aggregation": "month"}
                ...         ],
                ...         "filters": [
                ...             {"field": "Region", "operator": "=", "value": "East"}
                ...         ],
                ...         "date_filters": [
                ...             {
                ...                 "field": "Order Date",
                ...                 "range_type": "between",
                ...                 "start_date": "2024-01-01",
                ...                 "end_date": "2024-12-31"
                ...             }
                ...         ],
                ...         "limit": 100
                ...     },
                ...     datasource_luid="a1b2c3d4-e5f6-7890-abcd-ef1234567890"
                ... )
            
            Note:
                - Query results are limited to 10,000 rows by default
                - Large result sets may take longer to execute
                - Use filters to reduce result size when possible
                - Execution time includes network latency
            """
            from tableau_assistant.src.components.query_executor import QueryExecutor
            from tableau_assistant.src.utils.tableau.auth import _get_tableau_context_from_env
            
            try:
                logger.info(
                    f"Executing VizQL query on datasource: {datasource_luid}"
                )
                
                # Get authentication context
                context = _get_tableau_context_from_env()
                token = context.get("api_key")
                
                if not token:
                    raise RuntimeError("Failed to get authentication token")
                
                # Create executor and execute query
                executor = QueryExecutor(token, datasource_luid)
                result = executor.execute(query)
                
                logger.info(
                    f"✅ Query executed: {result.get('row_count', 0)} rows, "
                    f"{result.get('execution_time_ms', 0)}ms"
                )
                
                return result
                
            except Exception as e:
                error_msg = f"Failed to execute VizQL query: {str(e)}"
                logger.error(error_msg)
                raise RuntimeError(error_msg)
        
        return execute_vizql_query
    
    def get_tools(self) -> List:
        """
        获取中间件提供的工具列表
        
        Returns:
            工具列表
        """
        return self.tools


# 导出
__all__ = ["VizQLQueryMiddleware"]
