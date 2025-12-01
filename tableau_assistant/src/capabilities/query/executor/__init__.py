"""
查询执行器包

提供 VizQL 查询执行功能。

主要组件：
- QueryExecutor: 查询执行器，执行 VizQL 查询并处理结果
- execute_query_node: LangGraph 执行节点
- execute_vizql_query: LangChain 工具

使用示例：
    from tableau_assistant.src.capabilities.query.executor import QueryExecutor
    
    executor = QueryExecutor()
    result = executor.execute_query(query, datasource_luid, tableau_config)
"""
from tableau_assistant.src.capabilities.query.executor.query_executor import (
    QueryExecutor,
    QueryExecutionError,
    QueryErrorType,
)
from tableau_assistant.src.capabilities.query.executor.execute_node import execute_query_node
from tableau_assistant.src.capabilities.query.executor.tool import execute_vizql_query

__all__ = [
    "QueryExecutor",
    "QueryExecutionError",
    "QueryErrorType",
    "execute_query_node",
    "execute_vizql_query",
]
