"""
查询能力包

提供 VizQL 查询的构建、执行和结果处理功能。

子包：
- builder: 查询构建器，将 Intent 转换为 VizQL 查询
- executor: 查询执行器，执行 VizQL 查询并处理结果

使用示例：
    from tableau_assistant.src.capabilities.query import QueryExecutor, QueryBuilder
    from tableau_assistant.src.capabilities.query.builder import build_vizql_query
    from tableau_assistant.src.capabilities.query.executor import execute_vizql_query
    
    # 执行查询
    executor = QueryExecutor()
    result = executor.execute_query(query, datasource_luid, tableau_config)
    
    # 构建查询
    builder = QueryBuilder(metadata=metadata)
    vizql_query = builder.build_query(subtask)
"""
# 从 builder 包导入
from tableau_assistant.src.capabilities.query.builder import (
    QueryBuilder,
    IntentConverter,
    DateFilterConverter,
    FilterConverter,
    StringDateFilterBuilder,
    build_vizql_query,
)

# 从 executor 包导入
from tableau_assistant.src.capabilities.query.executor import (
    QueryExecutor,
    QueryExecutionError,
    QueryErrorType,
    execute_query_node,
    execute_vizql_query,
)

__all__ = [
    # Builder
    "QueryBuilder",
    "IntentConverter",
    "DateFilterConverter",
    "FilterConverter",
    "StringDateFilterBuilder",
    "build_vizql_query",
    # Executor
    "QueryExecutor",
    "QueryExecutionError",
    "QueryErrorType",
    "execute_query_node",
    "execute_vizql_query",
]
