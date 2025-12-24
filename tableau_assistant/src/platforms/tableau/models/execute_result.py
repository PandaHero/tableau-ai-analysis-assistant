"""
Execute Result - Re-export from core.models

This module re-exports ExecuteResult from core.models for backward compatibility.
The actual implementation is in tableau_assistant.src.core.models.execute_result.

For new code, prefer importing directly from:
    from tableau_assistant.src.core.models import ExecuteResult
"""

# Re-export from core.models for backward compatibility
from tableau_assistant.src.core.models.execute_result import (
    ExecuteResult,
    ColumnMetadata,
    RowData,
    RowValue,
)

__all__ = [
    "ExecuteResult",
    "ColumnMetadata",
    "RowData",
    "RowValue",
]
