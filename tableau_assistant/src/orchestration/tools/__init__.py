"""
LangGraph 工具定义（Agent 能力扩展）

工具分类：
- 核心 Tools: map_fields, build_query, execute_query
- 辅助工具: get_data_model, get_metadata
- 中间件工具: write_todos (from TodoListMiddleware), read_file (from FilesystemMiddleware)

注意：
- 所有需要 data model/metadata 的工具应使用 WorkflowContext
- map_fields 封装 FieldMapperNode（RAG + LLM 混合策略）
"""

from tableau_assistant.src.orchestration.tools.registry import (
    ToolRegistry,
    ToolMetadata,
    NodeType,
    get_registry,
    get_tools_for_node,
    register_tool,
)

from tableau_assistant.src.orchestration.tools.base import (
    ToolErrorCode,
    ToolError,
    ToolResult,
    ToolInputBase,
    format_tool_result,
    safe_tool_execution,
    safe_async_tool_execution,
)

from tableau_assistant.src.orchestration.tools.data_model_tool import (
    get_data_model,
    GetDataModelInput,
)

from tableau_assistant.src.orchestration.tools.metadata_tool import (
    get_metadata,
    GetMetadataInput,
)

# map_fields Tool
from tableau_assistant.src.orchestration.tools.map_fields import (
    map_fields,
    map_fields_async,
    MapFieldsInput,
    MapFieldsOutput,
    FieldMappingError,
    FieldMappingErrorType,
)

# build_query Tool
from tableau_assistant.src.orchestration.tools.build_query import (
    build_query,
    build_query_async,
    BuildQueryInput,
    BuildQueryOutput,
    QueryBuildError,
    QueryBuildErrorType,
)

# execute_query Tool
from tableau_assistant.src.orchestration.tools.execute_query import (
    execute_query,
    execute_query_async,
    ExecuteQueryInput,
    ExecuteQueryOutput,
    ExecutionError,
    ExecutionErrorType,
)

__all__ = [
    # Registry
    "ToolRegistry", "ToolMetadata", "NodeType", "get_registry", "get_tools_for_node", "register_tool",
    # Base
    "ToolErrorCode", "ToolError", "ToolResult", "ToolInputBase", "format_tool_result",
    "safe_tool_execution", "safe_async_tool_execution",
    # map_fields Tool
    "map_fields", "map_fields_async", "MapFieldsInput", "MapFieldsOutput", 
    "FieldMappingError", "FieldMappingErrorType",
    # build_query Tool
    "build_query", "build_query_async", "BuildQueryInput", "BuildQueryOutput",
    "QueryBuildError", "QueryBuildErrorType",
    # execute_query Tool
    "execute_query", "execute_query_async", "ExecuteQueryInput", "ExecuteQueryOutput",
    "ExecutionError", "ExecutionErrorType",
    # Data model tool
    "get_data_model", "GetDataModelInput",
    # Metadata tool
    "get_metadata", "GetMetadataInput",
]
