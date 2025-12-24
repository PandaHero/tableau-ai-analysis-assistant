"""
VizQL workflow state definition - Re-export from core.state

This module re-exports state types from core.state for backward compatibility.
The actual implementation is in tableau_assistant.src.core.state to avoid
circular imports between nodes/ and orchestration/ packages.

For new code, prefer importing directly from:
    from tableau_assistant.src.core.state import VizQLState
"""

# Re-export everything from core.state for backward compatibility
from tableau_assistant.src.core.state import (
    VizQLState,
    VizQLInput,
    VizQLOutput,
    create_initial_state,
    ErrorRecord,
    WarningRecord,
    ReplanHistoryRecord,
    PerformanceMetrics,
    VisualizationData,
    AnalysisPathStep,
)

__all__ = [
    "VizQLState",
    "VizQLInput",
    "VizQLOutput",
    "create_initial_state",
    "ErrorRecord",
    "WarningRecord",
    "ReplanHistoryRecord",
    "PerformanceMetrics",
    "VisualizationData",
    "AnalysisPathStep",
]
