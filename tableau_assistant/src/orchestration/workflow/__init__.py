"""
Workflow module for Tableau Assistant.

This package provides workflow state types and routing functions.

Usage:
    # State types (safe to import)
    from tableau_assistant.src.orchestration.workflow.state import VizQLState, create_initial_state
    
    # Routes (safe to import)
    from tableau_assistant.src.orchestration.workflow.routes import route_after_semantic_parser
    
    # Context (safe to import)
    from tableau_assistant.src.orchestration.workflow.context import WorkflowContext
    
    # Factory and Executor (import directly from module to avoid circular imports)
    from tableau_assistant.src.orchestration.workflow.factory import create_workflow
    from tableau_assistant.src.orchestration.workflow.executor import WorkflowExecutor

Note:
    factory.py and executor.py import node implementations which import state.py.
    To avoid circular imports, they are NOT exported from this __init__.py.
    Import them directly from their modules.
"""

# State types (no circular dependency - these are pure data definitions)
from tableau_assistant.src.orchestration.workflow.state import (
    VizQLState,
    create_initial_state,
    ErrorRecord,
    WarningRecord,
    ReplanHistoryRecord,
    PerformanceMetrics,
    VisualizationData,
)

# Routes (no circular dependency - only imports state types)
from tableau_assistant.src.orchestration.workflow.routes import (
    route_after_replanner,
    route_after_semantic_parser,
    calculate_completeness_score,
)

# Context (no circular dependency - only imports state types)
from tableau_assistant.src.orchestration.workflow.context import (
    WorkflowContext,
    MetadataLoadStatus,
    create_workflow_config,
    get_context,
    get_context_or_raise,
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
    # Routing functions
    "route_after_replanner",
    "route_after_semantic_parser",
    "calculate_completeness_score",
    # Context management
    "WorkflowContext",
    "MetadataLoadStatus",
    "create_workflow_config",
    "get_context",
    "get_context_or_raise",
]
