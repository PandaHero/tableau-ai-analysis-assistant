"""
Orchestration Layer - 编排层

统一管理工作流编排、工具定义和中间件。

子模块：
- workflow/: LangGraph 工作流编排
- tools/: LangGraph 工具定义（Agent 能力扩展）
- middleware/: 中间件（横切关注点）

使用示例:
    from tableau_assistant.src.orchestration.workflow import (
        WorkflowExecutor,
        create_workflow,
    )
    from tableau_assistant.src.orchestration.tools import (
        get_tools_for_node,
        NodeType,
    )
    from tableau_assistant.src.orchestration.middleware import (
        FilesystemMiddleware,
        PatchToolCallsMiddleware,
    )
"""

# Re-export from submodules for convenience
from tableau_assistant.src.orchestration.workflow import (
    WorkflowExecutor,
    WorkflowResult,
    WorkflowEvent,
    EventType,
    WorkflowPrinter,
    create_workflow,
    create_middleware_stack,
    create_sqlite_checkpointer,
    get_default_config,
    get_workflow_info,
    route_after_replanner,
    route_after_understanding,
    calculate_completeness_score,
    WorkflowContext,
    MetadataLoadStatus,
    create_workflow_config,
    get_context,
    get_context_or_raise,
)

from tableau_assistant.src.orchestration.tools import (
    ToolRegistry,
    ToolMetadata,
    NodeType,
    get_registry,
    get_tools_for_node,
    register_tool,
    ToolErrorCode,
    ToolError,
    ToolResponse,
    ToolInputBase,
    format_tool_response,
    safe_tool_execution,
    safe_async_tool_execution,
)

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
    # Workflow
    "WorkflowExecutor",
    "WorkflowResult",
    "WorkflowEvent",
    "EventType",
    "WorkflowPrinter",
    "create_workflow",
    "create_middleware_stack",
    "create_sqlite_checkpointer",
    "get_default_config",
    "get_workflow_info",
    "route_after_replanner",
    "route_after_understanding",
    "calculate_completeness_score",
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
    "ToolResponse",
    "ToolInputBase",
    "format_tool_response",
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
