"""
Orchestration Layer.

This package provides workflow orchestration, tools, and middleware.

Usage:
    # State types (safe to import from workflow)
    from tableau_assistant.src.orchestration.workflow import VizQLState, create_initial_state
    
    # Tools
    from tableau_assistant.src.orchestration.tools import get_tools_for_node, NodeType
    
    # Middleware
    from tableau_assistant.src.orchestration.middleware import FilesystemMiddleware
    
    # Factory and Executor (import directly from module)
    from tableau_assistant.src.orchestration.workflow.factory import create_workflow
    from tableau_assistant.src.orchestration.workflow.executor import WorkflowExecutor

Note:
    factory.py and executor.py are NOT exported from __init__.py to avoid circular imports.
    Import them directly from their modules.
"""

# State types (re-export from workflow for convenience)
from tableau_assistant.src.orchestration.workflow import (
    VizQLState,
    create_initial_state,
    ErrorRecord,
    WarningRecord,
    ReplanHistoryRecord,
    PerformanceMetrics,
    VisualizationData,
    route_after_replanner,
    route_after_semantic_parser,
    calculate_completeness_score,
    WorkflowContext,
    MetadataLoadStatus,
    create_workflow_config,
    get_context,
    get_context_or_raise,
)

# Tools
from tableau_assistant.src.orchestration.tools import (
    ToolRegistry,
    ToolMetadata,
    NodeType,
    get_registry,
    get_tools_for_node,
    register_tool,
    ToolErrorCode,
    ToolError,
    ToolResult,
    ToolInputBase,
    format_tool_result,
    safe_tool_execution,
    safe_async_tool_execution,
)

# Middleware
from tableau_assistant.src.orchestration.middleware import (
    FilesystemMiddleware,
    FilesystemState,
    FileData,
    PatchToolCallsMiddleware,
    find_dangling_tool_calls,
    count_dangling_tool_calls,
    OutputValidationMiddleware,
    OutputValidationError,
    BackendProtocol,
    StateBackend,
    FileInfo,
    GrepMatch,
    WriteResult,
    EditResult,
)

__all__ = [
    # State types
    "VizQLState",
    "create_initial_state",
    "ErrorRecord",
    "WarningRecord",
    "ReplanHistoryRecord",
    "PerformanceMetrics",
    "VisualizationData",
    # Routes
    "route_after_replanner",
    "route_after_semantic_parser",
    "calculate_completeness_score",
    # Context
    "WorkflowContext",
    "MetadataLoadStatus",
    "create_workflow_config",
    "get_context",
    "get_context_or_raise",
    # Tools
    "ToolRegistry",
    "ToolMetadata",
    "NodeType",
    "get_registry",
    "get_tools_for_node",
    "register_tool",
    "ToolErrorCode",
    "ToolError",
    "ToolResult",
    "ToolInputBase",
    "format_tool_result",
    "safe_tool_execution",
    "safe_async_tool_execution",
    # Middleware
    "FilesystemMiddleware",
    "FilesystemState",
    "FileData",
    "PatchToolCallsMiddleware",
    "find_dangling_tool_calls",
    "count_dangling_tool_calls",
    "OutputValidationMiddleware",
    "OutputValidationError",
    "BackendProtocol",
    "StateBackend",
    "FileInfo",
    "GrepMatch",
    "WriteResult",
    "EditResult",
]
