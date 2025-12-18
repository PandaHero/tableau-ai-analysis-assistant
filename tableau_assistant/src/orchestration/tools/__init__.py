"""
LangGraph 工具定义（Agent 能力扩展）

工具分类：
- 业务工具: get_data_model, get_metadata, get_schema_module
- 中间件工具: write_todos (from TodoListMiddleware), read_file (from FilesystemMiddleware)

注意：
- 所有需要 data model/metadata 的工具应使用 WorkflowContext
- FieldMapper 是独立节点（RAG + LLM 混合），不是工具
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
    ToolResponse,
    ToolInputBase,
    format_tool_response,
    safe_tool_execution,
    safe_async_tool_execution,
)

from tableau_assistant.src.orchestration.tools.data_model_tool import (
    get_data_model,
    GetDataModelInput,
)

from tableau_assistant.src.orchestration.tools.schema_tool import (
    get_schema_module,
)

from tableau_assistant.src.orchestration.tools.metadata_tool import (
    get_metadata,
    GetMetadataInput,
)

__all__ = [
    # Registry
    "ToolRegistry", "ToolMetadata", "NodeType", "get_registry", "get_tools_for_node", "register_tool",
    # Base
    "ToolErrorCode", "ToolError", "ToolResponse", "ToolInputBase", "format_tool_response",
    "safe_tool_execution", "safe_async_tool_execution",
    # Data model tool
    "get_data_model", "GetDataModelInput",
    # Schema tool
    "get_schema_module",
    # Metadata tool
    "get_metadata", "GetMetadataInput",
]
