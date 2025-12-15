"""
Custom middleware for Tableau Assistant workflow.

This module contains custom middleware implementations:
- FilesystemMiddleware: Auto-save large results to files, provides filesystem tools
- PatchToolCallsMiddleware: Fix dangling tool calls in message history

Backends:
- StateBackend: Ephemeral storage in LangGraph agent state

LLM Caching:
- Use LangChain's built-in caching instead of custom implementation:
  ```python
  from langchain_core.globals import set_llm_cache
  from langchain_community.cache import SQLiteCache
  set_llm_cache(SQLiteCache(database_path="data/llm_cache.db"))
  ```

Based on deepagents middleware design, adapted for production use.
"""

from tableau_assistant.src.middleware.filesystem import (
    FilesystemMiddleware,
    FilesystemState,
    FileData,
)
from tableau_assistant.src.middleware.patch_tool_calls import (
    PatchToolCallsMiddleware,
    find_dangling_tool_calls,
    count_dangling_tool_calls,
)
from tableau_assistant.src.middleware.output_validation import (
    OutputValidationMiddleware,
    OutputValidationError,
)
from tableau_assistant.src.middleware.backends import (
    BackendProtocol,
    StateBackend,
    FileInfo,
    GrepMatch,
    WriteResult,
    EditResult,
)

__all__ = [
    # Middleware
    "FilesystemMiddleware",
    "FilesystemState",
    "FileData",
    "PatchToolCallsMiddleware",
    "find_dangling_tool_calls",
    "count_dangling_tool_calls",
    "OutputValidationMiddleware",
    "OutputValidationError",
    # Backends
    "BackendProtocol",
    "StateBackend",
    "FileInfo",
    "GrepMatch",
    "WriteResult",
    "EditResult",
]
