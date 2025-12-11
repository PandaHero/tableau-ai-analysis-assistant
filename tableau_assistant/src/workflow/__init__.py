"""
Workflow module for Tableau Assistant

This module provides the workflow orchestration using LangGraph StateGraph.

Middleware stack (7 middleware):
- TodoListMiddleware (LangChain) - Task queue management
- SummarizationMiddleware (LangChain) - Auto-summarize conversation history
- ModelRetryMiddleware (LangChain) - Auto-retry LLM calls with exponential backoff
- ToolRetryMiddleware (LangChain) - Auto-retry tool calls with exponential backoff
- HumanInTheLoopMiddleware (LangChain, optional) - Human confirmation
- FilesystemMiddleware (custom) - Large result auto-save
- PatchToolCallsMiddleware (custom) - Fix dangling tool calls

Checkpointer options:
- MemorySaver: In-memory checkpointer (default, for development)
- SqliteSaver: SQLite checkpointer (for production persistence)
"""

from tableau_assistant.src.workflow.factory import (
    create_tableau_workflow,
    create_middleware_stack,
    create_sqlite_checkpointer,
    get_default_config,
    get_workflow_info,
)
from tableau_assistant.src.workflow.routes import (
    route_after_replanner,
    route_after_understanding,
    calculate_completeness_score,
)
from tableau_assistant.src.workflow.executor import (
    WorkflowExecutor,
    WorkflowResult,
    WorkflowEvent,
    EventType,
)
from tableau_assistant.src.workflow.printer import WorkflowPrinter

__all__ = [
    # Executor (主要对外接口)
    "WorkflowExecutor",
    "WorkflowResult",
    "WorkflowEvent",
    "EventType",
    "WorkflowPrinter",
    # Factory functions
    "create_tableau_workflow",
    "create_middleware_stack",
    "create_sqlite_checkpointer",
    "get_default_config",
    "get_workflow_info",
    # Routing functions
    "route_after_replanner",
    "route_after_understanding",
    "calculate_completeness_score",
]
