"""
execute_query Tool 包

封装 ExecuteNode，提供 LangChain Tool 接口。

功能：
- 执行 VizQL 查询
- 处理 API 响应
- 大结果集处理（通过 FilesystemMiddleware）

导出：
- execute_query: 同步 Tool
- execute_query_async: 异步版本
- ExecuteQueryInput: 输入模型
- ExecuteQueryOutput: 输出模型
- ExecutionError: 错误模型
- ExecutionErrorType: 错误类型枚举
"""

from tableau_assistant.src.orchestration.tools.execute_query.models import (
    ExecuteQueryInput,
    ExecuteQueryOutput,
    ExecutionError,
    ExecutionErrorType,
)

from tableau_assistant.src.orchestration.tools.execute_query.tool import (
    execute_query,
    execute_query_async,
)


__all__ = [
    # Tool
    "execute_query",
    "execute_query_async",
    # Models
    "ExecuteQueryInput",
    "ExecuteQueryOutput",
    "ExecutionError",
    "ExecutionErrorType",
]
