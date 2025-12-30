"""
StateBackend: Store files in LangGraph agent state (ephemeral).

This backend stores files in the agent's state, which is automatically
checkpointed by LangGraph. Files persist within a conversation thread
but not across threads.

Large data optimization:
- Files exceeding LARGE_DATA_THRESHOLD are stored in SqliteStore instead of state
- This prevents memory issues with large query results
- SqliteStore provides persistent storage with TTL-based cleanup

Based on deepagents StateBackend design, adapted for production use.
"""

import logging
from typing import Any, Optional

from langchain.tools import ToolRuntime

from tableau_assistant.src.infra.storage.langgraph_store import get_langgraph_store
from tableau_assistant.src.orchestration.middleware.backends.protocol import (
    BackendProtocol,
    EditResult,
    FileDownloadResponse,
    FileInfo,
    FileUploadResponse,
    GrepMatch,
    WriteResult,
)
from tableau_assistant.src.orchestration.middleware.backends.utils import (
    create_file_data,
    file_data_to_string,
    format_read_response,
    glob_search_files,
    grep_matches_from_files,
    perform_string_replacement,
    update_file_data,
    validate_directory_path,
    validate_path,
)

logger = logging.getLogger(__name__)

# Large data threshold: 100KB - files larger than this go to SqliteStore
LARGE_DATA_THRESHOLD = 100 * 1024

# TTL for large data in SqliteStore (minutes) - short TTL since query results are temporary
LARGE_DATA_TTL_MINUTES = 60


class StateBackend(BackendProtocol):
    """Backend that stores files in agent state (ephemeral).
    
    Uses LangGraph's state management and checkpointing. Files persist within
    a conversation thread but not across threads. State is automatically
    checkpointed after each agent step.
    
    Large data optimization:
    - Files exceeding LARGE_DATA_THRESHOLD are stored in SqliteStore
    - This prevents memory issues with large query results
    - SqliteStore data is keyed by (thread_id, file_path) for isolation
    
    Special handling: Since LangGraph state must be updated via Command objects
    (not direct mutation), operations return WriteResult/EditResult with
    files_update dict that should be applied to state.
    """
    
    def __init__(self, runtime: ToolRuntime):
        """Initialize StateBackend with runtime.
        
        Args:
            runtime: LangGraph tool runtime providing access to state
        """
        self.runtime = runtime
        self._store = get_langgraph_store()
    
    def _get_thread_id(self) -> str:
        """Get thread_id from runtime config for namespace isolation."""
        config = getattr(self.runtime, "config", {}) or {}
        configurable = config.get("configurable", {})
        return configurable.get("thread_id", "default")
    
    def _get_large_data_namespace(self) -> tuple:
        """Get namespace for large data in SqliteStore."""
        return ("large_results", self._get_thread_id())
    
    def _get_files(self) -> dict[str, Any]:
        """Get files dict from state."""
        return self.runtime.state.get("files", {})
    
    def _is_large_data(self, content: str) -> bool:
        """Check if content exceeds large data threshold."""
        return len(content.encode("utf-8")) > LARGE_DATA_THRESHOLD
    
    def _write_to_sqlite_store(self, file_path: str, content: str) -> None:
        """Write large data to SqliteStore with short TTL."""
        namespace = self._get_large_data_namespace()
        self._store.put(
            namespace=namespace,
            key=file_path,
            value={"content": content, "type": "large_data"},
            ttl=LARGE_DATA_TTL_MINUTES,  # 1小时 TTL，查询结果是临时的
        )
        logger.info(f"Large data written to SqliteStore: {file_path} ({len(content)} bytes), TTL={LARGE_DATA_TTL_MINUTES}min")
    
    def _read_from_sqlite_store(self, file_path: str) -> Optional[str]:
        """Read large data from SqliteStore."""
        namespace = self._get_large_data_namespace()
        item = self._store.get(namespace=namespace, key=file_path)
        if item is not None and hasattr(item, "value"):
            value = item.value
            if isinstance(value, dict) and "content" in value:
                return value["content"]
        return None
    
    def ls_info(self, path: str) -> list[FileInfo]:
        """List files and directories in the specified directory (non-recursive).
        
        Args:
            path: Absolute path to directory.
        
        Returns:
            List of FileInfo dicts for files and directories directly in the directory.
            Directories have a trailing / in their path and is_dir=True.
        """
        files = self._get_files()
        infos: list[FileInfo] = []
        subdirs: set[str] = set()
        
        # Normalize path to have trailing slash for proper prefix matching
        try:
            normalized_path = validate_directory_path(path)
        except ValueError:
            return []
        
        for k, fd in files.items():
            # Check if file is in the specified directory or a subdirectory
            if not k.startswith(normalized_path):
                continue
            
            # Get the relative path after the directory
            relative = k[len(normalized_path):]
            
            # If relative path contains '/', it's in a subdirectory
            if "/" in relative:
                # Extract the immediate subdirectory name
                subdir_name = relative.split("/")[0]
                subdirs.add(normalized_path + subdir_name + "/")
                continue
            
            # This is a file directly in the current directory
            size = len("\n".join(fd.get("content", [])))
            infos.append({
                "path": k,
                "is_dir": False,
                "size": int(size),
                "modified_at": fd.get("modified_at", ""),
            })
        
        # Add directories to the results
        for subdir in sorted(subdirs):
            infos.append({
                "path": subdir,
                "is_dir": True,
                "size": 0,
                "modified_at": "",
            })
        
        infos.sort(key=lambda x: x.get("path", ""))
        return infos
    
    def read(
        self,
        file_path: str,
        offset: int = 0,
        limit: int = 2000,
    ) -> str:
        """Read file content with line numbers.
        
        Checks both state.files and SqliteStore for large data.
        
        Args:
            file_path: Absolute file path
            offset: Line offset to start reading from (0-indexed)
            limit: Maximum number of lines to read
        
        Returns:
            Formatted file content with line numbers, or error message.
        """
        files = self._get_files()
        file_data = files.get(file_path)
        
        # If not in state, check SqliteStore for large data
        if file_data is None:
            content = self._read_from_sqlite_store(file_path)
            if content is not None:
                # Create temporary file_data structure for format_read_response
                file_data = {"content": content.split("\n")}
        
        if file_data is None:
            return f"Error: File '{file_path}' not found"
        
        return format_read_response(file_data, offset, limit)
    
    def write(
        self,
        file_path: str,
        content: str,
    ) -> WriteResult:
        """Create a new file with content.
        
        Large data (> LARGE_DATA_THRESHOLD) is stored in SqliteStore instead of state.
        This prevents memory issues with large query results.
        
        Returns WriteResult with files_update to update LangGraph state.
        For large data, files_update is None (data is in SqliteStore).
        """
        files = self._get_files()
        
        if file_path in files:
            return WriteResult(
                error=f"Cannot write to {file_path} because it already exists. "
                      "Read and then make an edit, or write to a new path."
            )
        
        # Check if this is large data
        if self._is_large_data(content):
            # Store in SqliteStore, not in state
            self._write_to_sqlite_store(file_path, content)
            # Return without files_update - data is persisted externally
            return WriteResult(path=file_path, files_update=None)
        
        # Small data goes to state as before
        new_file_data = create_file_data(content)
        return WriteResult(path=file_path, files_update={file_path: new_file_data})
    
    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        """Edit a file by replacing string occurrences.
        
        Returns EditResult with files_update and occurrences.
        """
        files = self._get_files()
        file_data = files.get(file_path)
        
        if file_data is None:
            return EditResult(error=f"Error: File '{file_path}' not found")
        
        content = file_data_to_string(file_data)
        result = perform_string_replacement(content, old_string, new_string, replace_all)
        
        if isinstance(result, str):
            return EditResult(error=result)
        
        new_content, occurrences = result
        new_file_data = update_file_data(file_data, new_content)
        return EditResult(
            path=file_path,
            files_update={file_path: new_file_data},
            occurrences=int(occurrences)
        )
    
    def grep_raw(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
    ) -> list[GrepMatch] | str:
        """Search file contents for regex pattern.
        
        Args:
            pattern: Regex pattern to search for
            path: Base path to search from (default: "/")
            glob: Optional glob pattern to filter files
        
        Returns:
            List of GrepMatch dicts, or error string for invalid input
        """
        files = self._get_files()
        return grep_matches_from_files(files, pattern, path or "/", glob)
    
    def glob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        """Get FileInfo for files matching glob pattern.
        
        Args:
            pattern: Glob pattern (e.g., "*.py", "**/*.ts")
            path: Base path to search from
        
        Returns:
            List of FileInfo dicts for matching files
        """
        files = self._get_files()
        matching_paths = glob_search_files(files, pattern, path)
        
        infos: list[FileInfo] = []
        for p in matching_paths:
            fd = files.get(p)
            size = len("\n".join(fd.get("content", []))) if fd else 0
            infos.append({
                "path": p,
                "is_dir": False,
                "size": int(size),
                "modified_at": fd.get("modified_at", "") if fd else "",
            })
        return infos
    
    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        """Upload multiple files to state.
        
        Note: For StateBackend, this creates files in memory. The files_update
        must be applied to state separately via Command.
        
        Args:
            files: List of (path, content) tuples to upload.
        
        Returns:
            List of FileUploadResponse objects, one per input file.
        """
        responses: list[FileUploadResponse] = []
        
        for file_path, content in files:
            try:
                validated_path = validate_path(file_path)
                # Decode bytes to string for text storage
                text_content = content.decode("utf-8")
                # Use write internally
                result = self.write(validated_path, text_content)
                if result.error:
                    responses.append(FileUploadResponse(
                        path=file_path,
                        error="file_exists" if "exists" in result.error.lower() else "invalid_path",
                    ))
                else:
                    responses.append(FileUploadResponse(path=file_path, error=None))
            except ValueError:
                responses.append(FileUploadResponse(path=file_path, error="invalid_path"))
            except UnicodeDecodeError:
                # Binary files not supported in state backend
                responses.append(FileUploadResponse(path=file_path, error="invalid_path"))
        
        return responses
    
    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        """Download multiple files from state.
        
        Args:
            paths: List of file paths to download.
        
        Returns:
            List of FileDownloadResponse objects, one per input path.
        """
        files = self._get_files()
        responses: list[FileDownloadResponse] = []
        
        for file_path in paths:
            try:
                validated_path = validate_path(file_path)
                file_data = files.get(validated_path)
                
                if file_data is None:
                    responses.append(FileDownloadResponse(
                        path=file_path,
                        content=None,
                        error="file_not_found",
                    ))
                else:
                    content = file_data_to_string(file_data)
                    responses.append(FileDownloadResponse(
                        path=file_path,
                        content=content.encode("utf-8"),
                        error=None,
                    ))
            except ValueError:
                responses.append(FileDownloadResponse(
                    path=file_path,
                    content=None,
                    error="invalid_path",
                ))
        
        return responses
