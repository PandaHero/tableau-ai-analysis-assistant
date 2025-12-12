"""
Tools module for Tableau Assistant

This module provides the tool system for Agent nodes.

Tool categories:
- Business tools: get_data_model, get_metadata, process_time_filter, detect_date_format, get_schema_module
- Middleware tools: write_todos (from TodoListMiddleware), read_file (from FilesystemMiddleware)

Note:
- All tools that need data model/metadata should use WorkflowContext
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
    GetDataModelInput,
)

from tableau_assistant.src.tools.date_tool import (
    process_time_filter,
    calculate_relative_dates,
    detect_date_format,
    ProcessTimeFilterInput,
    DetectDateFormatInput,
)

from tableau_assistant.src.tools.schema_tool import (
    get_schema_module,
)

from tableau_assistant.src.tools.metadata_tool import (
    get_metadata,
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
    "GetDataModelInput",
    # Date tools
    "process_time_filter",
    "calculate_relative_dates",
    "detect_date_format",
    "ProcessTimeFilterInput",
    "DetectDateFormatInput",
    # Schema tool
    "get_schema_module",
    # Metadata tool
    "get_metadata",
    "GetMetadataInput",
]
