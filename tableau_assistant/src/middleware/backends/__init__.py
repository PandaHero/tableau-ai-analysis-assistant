"""
Backend implementations for FilesystemMiddleware.

This module provides pluggable storage backends:
- StateBackend: Ephemeral storage in LangGraph agent state
- SandboxBackendProtocol: Protocol for sandboxed backends with execution support

Based on deepagents backends design, adapted for production use.
"""

from tableau_assistant.src.middleware.backends.protocol import (
    BackendProtocol,
    SandboxBackendProtocol,
    FileInfo,
    GrepMatch,
    WriteResult,
    EditResult,
    FileDownloadResponse,
    FileUploadResponse,
    ExecuteResponse,
    FileOperationError,
    FileData,
    BACKEND_TYPES,
    BackendFactory,
)
from tableau_assistant.src.middleware.backends.state import StateBackend

__all__ = [
    # Protocols
    "BackendProtocol",
    "SandboxBackendProtocol",
    # Type aliases
    "BACKEND_TYPES",
    "BackendFactory",
    # Data types
    "FileInfo",
    "GrepMatch",
    "FileData",
    "FileOperationError",
    # Result types
    "WriteResult",
    "EditResult",
    "FileDownloadResponse",
    "FileUploadResponse",
    "ExecuteResponse",
    # Implementations
    "StateBackend",
]
