"""
Protocol definition for pluggable memory backends.

This module defines the BackendProtocol that all backend implementations
must follow. Backends can store files in different locations (state, filesystem,
database, etc.) and provide a uniform interface for file operations.

Based on deepagents backends protocol, adapted for production use.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, NotRequired, Protocol, TypeAlias, runtime_checkable
from typing_extensions import TypedDict

from langchain.tools import ToolRuntime


FileOperationError = Literal[
    "file_not_found",      # File doesn't exist
    "permission_denied",   # Access denied
    "is_directory",        # Tried to read directory as file
    "invalid_path",        # Path syntax malformed
    "file_exists",         # File already exists (for write)
    "parent_not_found",    # Parent directory doesn't exist (upload)
]
"""Standardized error codes for file operations.

These represent common, recoverable errors that an LLM can understand and potentially fix:
- file_not_found: The requested file doesn't exist (download/read)
- parent_not_found: The parent directory doesn't exist (upload/write)
- permission_denied: Access denied for the operation
- is_directory: Attempted to read a directory as a file
- invalid_path: Path syntax is malformed or contains invalid characters
- file_exists: File already exists (for write operations that don't allow overwrite)
"""


class FileInfo(TypedDict):
    """Structured file listing info.
    
    Minimal contract used across backends. Only "path" is required.
    Other fields are best-effort and may be absent depending on backend.
    """
    path: str
    is_dir: NotRequired[bool]
    size: NotRequired[int]  # bytes (approx)
    modified_at: NotRequired[str]  # ISO timestamp if known


class GrepMatch(TypedDict):
    """Structured grep match entry."""
    path: str
    line: int
    text: str


class FileData(TypedDict):
    """Data structure for storing file contents with metadata."""
    content: list[str]
    """Lines of the file."""
    created_at: str
    """ISO 8601 timestamp of file creation."""
    modified_at: str
    """ISO 8601 timestamp of last modification."""


@dataclass
class WriteResult:
    """Result from backend write operations.
    
    Attributes:
        error: Error message on failure, None on success.
        path: Absolute path of written file, None on failure.
        files_update: State update dict for checkpoint backends, None for external storage.
            Checkpoint backends populate this with {file_path: file_data} for LangGraph state.
            External backends set None (already persisted to disk/S3/database/etc).
    
    Examples:
        >>> # Checkpoint storage
        >>> WriteResult(path="/f.txt", files_update={"/f.txt": {...}})
        >>> # External storage
        >>> WriteResult(path="/f.txt", files_update=None)
        >>> # Error
        >>> WriteResult(error="File exists")
    """
    error: str | None = None
    path: str | None = None
    files_update: dict[str, Any] | None = None


@dataclass
class EditResult:
    """Result from backend edit operations.
    
    Attributes:
        error: Error message on failure, None on success.
        path: Absolute path of edited file, None on failure.
        files_update: State update dict for checkpoint backends, None for external storage.
            Checkpoint backends populate this with {file_path: file_data} for LangGraph state.
            External backends set None (already persisted to disk/S3/database/etc).
        occurrences: Number of replacements made, None on failure.
    
    Examples:
        >>> # Checkpoint storage
        >>> EditResult(path="/f.txt", files_update={"/f.txt": {...}}, occurrences=1)
        >>> # External storage
        >>> EditResult(path="/f.txt", files_update=None, occurrences=2)
        >>> # Error
        >>> EditResult(error="File not found")
    """
    error: str | None = None
    path: str | None = None
    files_update: dict[str, Any] | None = None
    occurrences: int | None = None


@dataclass
class FileDownloadResponse:
    """Result of a single file download operation.
    
    The response is designed to allow partial success in batch operations.
    The errors are standardized using FileOperationError literals
    for certain recoverable conditions for use cases that involve
    LLMs performing file operations.
    
    Attributes:
        path: The file path that was requested. Included for easy correlation
            when processing batch results, especially useful for error messages.
        content: File contents as bytes on success, None on failure.
        error: Standardized error code on failure, None on success.
    
    Examples:
        >>> # Success
        >>> FileDownloadResponse(path="/app/config.json", content=b"{...}", error=None)
        >>> # Failure
        >>> FileDownloadResponse(path="/wrong/path.txt", content=None, error="file_not_found")
    """
    path: str
    content: bytes | None = None
    error: FileOperationError | None = None


@dataclass
class FileUploadResponse:
    """Result of a single file upload operation.
    
    The response is designed to allow partial success in batch operations.
    The errors are standardized using FileOperationError literals
    for certain recoverable conditions for use cases that involve
    LLMs performing file operations.
    
    Attributes:
        path: The file path that was requested. Included for easy correlation
            when processing batch results and for clear error messages.
        error: Standardized error code on failure, None on success.
    
    Examples:
        >>> # Success
        >>> FileUploadResponse(path="/app/data.txt", error=None)
        >>> # Failure
        >>> FileUploadResponse(path="/readonly/file.txt", error="permission_denied")
    """
    path: str
    error: FileOperationError | None = None


@dataclass
class ExecuteResponse:
    """Result of code execution in sandbox backends.
    
    Simplified schema optimized for LLM consumption.
    
    Attributes:
        output: Combined stdout and stderr output of the executed command.
        exit_code: The process exit code. 0 indicates success, non-zero indicates failure.
        truncated: Whether the output was truncated due to backend limitations.
    """
    output: str
    exit_code: int | None = None
    truncated: bool = False


@runtime_checkable
class BackendProtocol(Protocol):
    """Protocol for pluggable memory backends.
    
    Backends can store files in different locations (state, filesystem, database, etc.)
    and provide a uniform interface for file operations.
    
    All file data is represented as dicts with the following structure:
    {
        "content": list[str],  # Lines of text content
        "created_at": str,     # ISO format timestamp
        "modified_at": str,    # ISO format timestamp
    }
    """
    
    def ls_info(self, path: str) -> list[FileInfo]:
        """Structured listing with file metadata.
        
        Args:
            path: Absolute path to directory.
        
        Returns:
            List of FileInfo dicts for files and directories.
        """
        ...
    
    def read(
        self,
        file_path: str,
        offset: int = 0,
        limit: int = 2000,
    ) -> str:
        """Read file content with line numbers or an error string.
        
        Args:
            file_path: Absolute file path.
            offset: Line offset to start reading from (0-indexed).
            limit: Maximum number of lines to read.
        
        Returns:
            Formatted file content with line numbers, or error message.
        """
        ...
    
    def grep_raw(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
    ) -> list[GrepMatch] | str:
        """Structured search results or error string for invalid input.
        
        Args:
            pattern: Regex pattern to search for.
            path: Base path to search from (default: "/").
            glob: Optional glob pattern to filter files.
        
        Returns:
            List of GrepMatch dicts, or error string for invalid input.
        """
        ...
    
    def glob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        """Structured glob matching returning FileInfo dicts.
        
        Args:
            pattern: Glob pattern (e.g., "*.py", "**/*.ts").
            path: Base path to search from.
        
        Returns:
            List of FileInfo dicts for matching files.
        """
        ...
    
    def write(
        self,
        file_path: str,
        content: str,
    ) -> WriteResult:
        """Create a new file. Returns WriteResult; error populated on failure.
        
        Args:
            file_path: Absolute file path.
            content: File content as string.
        
        Returns:
            WriteResult with path and optional files_update for state backends.
        """
        ...
    
    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        """Edit a file by replacing string occurrences. Returns EditResult.
        
        Args:
            file_path: Absolute file path.
            old_string: String to replace.
            new_string: Replacement string.
            replace_all: Whether to replace all occurrences.
        
        Returns:
            EditResult with path, occurrences, and optional files_update.
        """
        ...
    
    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        """Upload multiple files to the backend.
        
        This API is designed to allow developers to use it either directly or
        by exposing it to LLMs via custom tools.
        
        Args:
            files: List of (path, content) tuples to upload.
        
        Returns:
            List of FileUploadResponse objects, one per input file.
            Response order matches input order (response[i] for files[i]).
            Check the error field to determine success/failure per file.
        
        Examples:
            ```python
            responses = backend.upload_files([
                ("/app/config.json", b"{...}"),
                ("/app/data.txt", b"content"),
            ])
            ```
        """
        ...
    
    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        """Download multiple files from the backend.
        
        This API is designed to allow developers to use it either directly or
        by exposing it to LLMs via custom tools.
        
        Args:
            paths: List of file paths to download.
        
        Returns:
            List of FileDownloadResponse objects, one per input path.
            Response order matches input order (response[i] for paths[i]).
            Check the error field to determine success/failure per file.
        """
        ...


@runtime_checkable
class SandboxBackendProtocol(BackendProtocol, Protocol):
    """Protocol for sandboxed backends with isolated runtime.
    
    Sandboxed backends run in isolated environments (e.g., separate processes,
    containers) and communicate via defined interfaces. They support command
    execution in addition to file operations.
    """
    
    def execute(self, command: str) -> ExecuteResponse:
        """Execute a command in the sandbox.
        
        Simplified interface optimized for LLM consumption.
        
        Args:
            command: Full shell command string to execute.
        
        Returns:
            ExecuteResponse with combined output, exit code, and truncation flag.
        """
        ...
    
    @property
    def id(self) -> str:
        """Unique identifier for the sandbox backend instance."""
        ...


# Type aliases for backend factories
BackendFactory: TypeAlias = Callable[[ToolRuntime], BackendProtocol]
BACKEND_TYPES = BackendProtocol | BackendFactory
