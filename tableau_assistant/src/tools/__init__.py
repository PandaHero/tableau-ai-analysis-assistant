"""
Tools module for Tableau Assistant

This module provides the tool system for Agent nodes.

Tool categories:
- Business tools: get_data_model, parse_date, detect_date_format, get_schema_module
- Middleware tools: write_todos (from TodoListMiddleware), read_file (from FilesystemMiddleware)

Note:
- FieldMapper is an independent node (RAG + LLM hybrid), not a tool
- Boost Agent has been removed, its functionality merged into Understanding Agent
"""

from tableau_assistant.src.tools.registry import (
    ToolRegistry,
    ToolMetadata,
    NodeType,
    get_registry,
    get_tools_for_node,
    register_tool,
)

from tableau_assistant.src.tools.base import (
    ToolErrorCode,
    ToolError,
    ToolResponse,
    ToolInputBase,
    format_tool_response,
    safe_tool_execution,
    safe_async_tool_execution,
)

from tableau_assistant.src.tools.data_model_tool import (
    get_data_model,
    set_data_model_manager,
    get_data_model_manager,
    GetDataModelInput,
)

from tableau_assistant.src.tools.date_tool import (
    parse_date,
    detect_date_format,
    set_date_manager,
    get_date_manager,
)

from tableau_assistant.src.tools.schema_tool import (
    get_schema_module,
    SchemaModuleRegistry,
)

from tableau_assistant.src.tools.metadata_tool import (
    get_metadata,
    set_metadata_manager,
    get_metadata_manager,
    GetMetadataInput,
)

__all__ = [
    # Registry
    "ToolRegistry",
    "ToolMetadata",
    "NodeType",
    "get_registry",
    "get_tools_for_node",
    "register_tool",
    # Base
    "ToolErrorCode",
    "ToolError",
    "ToolResponse",
    "ToolInputBase",
    "format_tool_response",
    "safe_tool_execution",
    "safe_async_tool_execution",
    # Data model tool
    "get_data_model",
    "set_data_model_manager",
    "get_data_model_manager",
    "GetDataModelInput",
    # Date tools
    "parse_date",
    "detect_date_format",
    "set_date_manager",
    "get_date_manager",
    # Schema tool
    "get_schema_module",
    "SchemaModuleRegistry",
    # Metadata tool
    "get_metadata",
    "set_metadata_manager",
    "get_metadata_manager",
    "GetMetadataInput",
]
