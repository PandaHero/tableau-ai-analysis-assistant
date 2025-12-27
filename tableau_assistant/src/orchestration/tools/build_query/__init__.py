"""
build_query Tool 包

封装 QueryBuilderNode，将 MappedQuery 转换为 VizQL 查询请求。

功能：
- 应用字段映射到 SemanticQuery
- 使用 TableauQueryBuilder 构建 VizQL 请求
- 支持表计算和 LOD 表达式

错误处理：构建失败直接返回结构化错误
"""

from tableau_assistant.src.orchestration.tools.build_query.tool import (
    build_query,
    build_query_async,
)
from tableau_assistant.src.orchestration.tools.build_query.models import (
    BuildQueryInput,
    BuildQueryOutput,
    QueryBuildError,
    QueryBuildErrorType,
)

__all__ = [
    # Tool
    "build_query",
    "build_query_async",
    # Models
    "BuildQueryInput",
    "BuildQueryOutput",
    "QueryBuildError",
    "QueryBuildErrorType",
]
