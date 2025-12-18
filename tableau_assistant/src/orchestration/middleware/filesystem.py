"""
FilesystemMiddleware: Middleware for providing filesystem tools to an agent.

This middleware adds filesystem tools to the agent: ls, read_file, write_file,
edit_file, glob, and grep. Files can be stored using any backend that implements
the BackendProtocol.

Key features:
1. Large tool results are automatically evicted to filesystem
2. Provides read_file tool with offset/limit for paginated reading
3. Provides write_file and edit_file tools for file manipulation
4. Provides glob and grep tools for file search

Based on deepagents FilesystemMiddleware design, adapted for our use case.
"""

from collections.abc import Awaitable, Callable
from typing import Annotated, Any, Literal, NotRequired

from langchain.agents.middleware.types import (
    AgentMiddleware,
    AgentState,
    ModelRequest,
    ModelResponse,
)
from langchain.tools import ToolRuntime
from langchain.tools.tool_node import ToolCallRequest
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool, tool
from langgraph.types import Command
from typing_extensions import TypedDict

from tableau_assistant.src.orchestration.middleware.backends.protocol import (
    BackendProtocol,
    EditResult,
    WriteResult,
)
from tableau_assistant.src.orchestration.middleware.backends.state import StateBackend
from tableau_assistant.src.orchestration.middleware.backends.utils import (
    format_content_with_line_numbers,
    format_grep_matches,
    sanitize_tool_call_id,
    truncate_if_too_long,
    validate_path,
)


# ═══════════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════════

EMPTY_CONTENT_WARNING = "System reminder: File exists but has empty contents"
MAX_LINE_LENGTH = 2000
LINE_NUMBER_WIDTH = 6
DEFAULT_READ_OFFSET = 0
DEFAULT_READ_LIMIT = 500


# ═══════════════════════════════════════════════════════════════════════════
# State Schema
# ═══════════════════════════════════════════════════════════════════════════

class FileData(TypedDict):
    """Data structure for storing file contents with metadata."""
    content: list[str]
    created_at: str
    modified_at: str


def _file_data_reducer(
    left: dict[str, FileData] | None,
    right: dict[str, FileData | None]
) -> dict[str, FileData]:
    """Merge file updates with support for deletions."""
    if left is None:
        return {k: v for k, v in right.items() if v is not None}
    result = {**left}
    for key, value in right.items():
        if value is None:
            result.pop(key, None)
        else:
            result[key] = value
    return result


class FilesystemState(AgentState):
    """State for the filesystem middleware."""
    files: Annotated[NotRequired[dict[str, FileData]], _file_data_reducer]


# ═══════════════════════════════════════════════════════════════════════════
# Tool Descriptions
# ═══════════════════════════════════════════════════════════════════════════

LIST_FILES_TOOL_DESCRIPTION = """Lists all files in the filesystem, filtering by directory.
Usage: The path parameter must be an absolute path starting with /."""

READ_FILE_TOOL_DESCRIPTION = """Reads a file from the filesystem.
Usage: Use offset and limit for pagination. Default reads up to 500 lines."""

EDIT_FILE_TOOL_DESCRIPTION = """Performs exact string replacements in files.
Usage: Use replace_all=True for multiple instances."""

WRITE_FILE_TOOL_DESCRIPTION = """Writes to a new file in the filesystem.
Usage: The file_path parameter must be an absolute path."""

GLOB_TOOL_DESCRIPTION = """Find files matching a glob pattern.
Examples: **/*.py finds all Python files."""

GREP_TOOL_DESCRIPTION = """Search for a pattern in files.
Usage: output_mode can be files_with_matches, content, or count."""

FILESYSTEM_SYSTEM_PROMPT = """## Filesystem Tools
- ls: list files in a directory
- read_file: read a file from the filesystem
- write_file: write to a file in the filesystem
- edit_file: edit a file in the filesystem
- glob: find files matching a pattern
- grep: search for text within files"""


# ═══════════════════════════════════════════════════════════════════════════
# Backend Type Alias
# ═══════════════════════════════════════════════════════════════════════════

BackendFactory = Callable[[ToolRuntime], BackendProtocol]
BACKEND_TYPES = BackendProtocol | BackendFactory


def _get_backend(backend: BACKEND_TYPES, runtime: ToolRuntime) -> BackendProtocol:
    """Get the resolved backend instance from backend or factory."""
    if callable(backend):
        return backend(runtime)
    return backend


# ═══════════════════════════════════════════════════════════════════════════
# Tool Generators
# ═══════════════════════════════════════════════════════════════════════════

def _ls_tool_generator(backend: BACKEND_TYPES, custom_description: str | None = None) -> BaseTool:
    tool_description = custom_description or LIST_FILES_TOOL_DESCRIPTION
    @tool(description=tool_description)
    def ls(runtime: ToolRuntime[None, FilesystemState], path: str) -> str:
        resolved_backend = _get_backend(backend, runtime)
        validated_path = validate_path(path)
        infos = resolved_backend.ls_info(validated_path)
        paths = [fi.get("path", "") for fi in infos]
        return str(truncate_if_too_long(paths))
    return ls


def _read_file_tool_generator(backend: BACKEND_TYPES, custom_description: str | None = None) -> BaseTool:
    tool_description = custom_description or READ_FILE_TOOL_DESCRIPTION
    @tool(description=tool_description)
    def read_file(
        file_path: str,
        runtime: ToolRuntime[None, FilesystemState],
        offset: int = DEFAULT_READ_OFFSET,
        limit: int = DEFAULT_READ_LIMIT,
    ) -> str:
        resolved_backend = _get_backend(backend, runtime)
        file_path = validate_path(file_path)
        return resolved_backend.read(file_path, offset=offset, limit=limit)
    return read_file


def _write_file_tool_generator(backend: BACKEND_TYPES, custom_description: str | None = None) -> BaseTool:
    tool_description = custom_description or WRITE_FILE_TOOL_DESCRIPTION
    @tool(description=tool_description)
    def write_file(
        file_path: str,
        content: str,
        runtime: ToolRuntime[None, FilesystemState],
    ) -> Command | str:
        resolved_backend = _get_backend(backend, runtime)
        file_path = validate_path(file_path)
        res: WriteResult = resolved_backend.write(file_path, content)
        if res.error:
            return res.error
        if res.files_update is not None:
            return Command(update={
                "files": res.files_update,
                "messages": [ToolMessage(content=f"Updated file {res.path}", tool_call_id=runtime.tool_call_id)]
            })
        return f"Updated file {res.path}"
    return write_file


def _edit_file_tool_generator(backend: BACKEND_TYPES, custom_description: str | None = None) -> BaseTool:
    tool_description = custom_description or EDIT_FILE_TOOL_DESCRIPTION
    @tool(description=tool_description)
    def edit_file(
        file_path: str,
        old_string: str,
        new_string: str,
        runtime: ToolRuntime[None, FilesystemState],
        *,
        replace_all: bool = False,
    ) -> Command | str:
        resolved_backend = _get_backend(backend, runtime)
        file_path = validate_path(file_path)
        res: EditResult = resolved_backend.edit(file_path, old_string, new_string, replace_all=replace_all)
        if res.error:
            return res.error
        if res.files_update is not None:
            return Command(update={
                "files": res.files_update,
                "messages": [ToolMessage(content=f"Replaced {res.occurrences} instance(s) in '{res.path}'", tool_call_id=runtime.tool_call_id)]
            })
        return f"Replaced {res.occurrences} instance(s) in '{res.path}'"
    return edit_file


def _glob_tool_generator(backend: BACKEND_TYPES, custom_description: str | None = None) -> BaseTool:
    tool_description = custom_description or GLOB_TOOL_DESCRIPTION
    @tool(description=tool_description)
    def glob(pattern: str, runtime: ToolRuntime[None, FilesystemState], path: str = "/") -> str:
        resolved_backend = _get_backend(backend, runtime)
        infos = resolved_backend.glob_info(pattern, path=path)
        paths = [fi.get("path", "") for fi in infos]
        return str(truncate_if_too_long(paths))
    return glob


def _grep_tool_generator(backend: BACKEND_TYPES, custom_description: str | None = None) -> BaseTool:
    tool_description = custom_description or GREP_TOOL_DESCRIPTION
    @tool(description=tool_description)
    def grep(
        pattern: str,
        runtime: ToolRuntime[None, FilesystemState],
        path: str | None = None,
        glob: str | None = None,
        output_mode: Literal["files_with_matches", "content", "count"] = "files_with_matches",
    ) -> str:
        resolved_backend = _get_backend(backend, runtime)
        raw = resolved_backend.grep_raw(pattern, path=path, glob=glob)
        if isinstance(raw, str):
            return raw
        formatted = format_grep_matches(raw, output_mode)
        return truncate_if_too_long(formatted)
    return grep


TOOL_GENERATORS = {
    "ls": _ls_tool_generator,
    "read_file": _read_file_tool_generator,
    "write_file": _write_file_tool_generator,
    "edit_file": _edit_file_tool_generator,
    "glob": _glob_tool_generator,
    "grep": _grep_tool_generator,
}


def _get_filesystem_tools(backend: BackendProtocol, custom_tool_descriptions: dict[str, str] | None = None) -> list[BaseTool]:
    if custom_tool_descriptions is None:
        custom_tool_descriptions = {}
    tools = []
    for tool_name, tool_generator in TOOL_GENERATORS.items():
        t = tool_generator(backend, custom_tool_descriptions.get(tool_name))
        tools.append(t)
    return tools


# ═══════════════════════════════════════════════════════════════════════════
# Large Result Message Template
# ═══════════════════════════════════════════════════════════════════════════

TOO_LARGE_TOOL_MSG = """Tool result too large, saved at: {file_path}
Use read_file with offset and limit to read parts of the result.

First 10 lines preview:
{content_sample}
"""


# ═══════════════════════════════════════════════════════════════════════════
# FilesystemMiddleware Class
# ═══════════════════════════════════════════════════════════════════════════

class FilesystemMiddleware(AgentMiddleware):
    """Middleware for providing filesystem tools to an agent.
    
    Features:
    1. Large tool results are automatically evicted to filesystem
    2. Provides read_file tool with offset/limit for paginated reading
    3. Provides write_file and edit_file tools for file manipulation
    4. Provides glob and grep tools for file search
    """
    
    state_schema = FilesystemState
    
    def __init__(
        self,
        *,
        backend: BACKEND_TYPES | None = None,
        system_prompt: str | None = None,
        custom_tool_descriptions: dict[str, str] | None = None,
        tool_token_limit_before_evict: int | None = 20000,
    ) -> None:
        self.tool_token_limit_before_evict = tool_token_limit_before_evict
        self.backend = backend if backend is not None else (lambda rt: StateBackend(rt))
        self._custom_system_prompt = system_prompt
        self.tools = _get_filesystem_tools(self.backend, custom_tool_descriptions)
    
    def _get_backend(self, runtime: ToolRuntime) -> BackendProtocol:
        if callable(self.backend):
            return self.backend(runtime)
        return self.backend
    
    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        system_prompt = self._custom_system_prompt or FILESYSTEM_SYSTEM_PROMPT
        if system_prompt:
            new_system_prompt = (
                request.system_prompt + "\n\n" + system_prompt
                if request.system_prompt else system_prompt
            )
            request = request.override(system_prompt=new_system_prompt)
        return handler(request)
    
    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        system_prompt = self._custom_system_prompt or FILESYSTEM_SYSTEM_PROMPT
        if system_prompt:
            new_system_prompt = (
                request.system_prompt + "\n\n" + system_prompt
                if request.system_prompt else system_prompt
            )
            request = request.override(system_prompt=new_system_prompt)
        return await handler(request)
    
    def _process_large_message(
        self,
        message: ToolMessage,
        resolved_backend: BackendProtocol,
    ) -> tuple[ToolMessage, dict[str, FileData] | None]:
        content = message.content
        if not isinstance(content, str):
            return message, None
        if len(content) <= 4 * self.tool_token_limit_before_evict:
            return message, None
        
        sanitized_id = sanitize_tool_call_id(message.tool_call_id)
        file_path = f"/large_tool_results/{sanitized_id}"
        result = resolved_backend.write(file_path, content)
        
        if result.error:
            return message, None
        
        content_sample = format_content_with_line_numbers(
            [line[:1000] for line in content.splitlines()[:10]], start_line=1
        )
        processed_message = ToolMessage(
            TOO_LARGE_TOOL_MSG.format(file_path=file_path, content_sample=content_sample),
            tool_call_id=message.tool_call_id,
        )
        return processed_message, result.files_update
    
    def _intercept_large_tool_result(
        self,
        tool_result: ToolMessage | Command,
        runtime: ToolRuntime
    ) -> ToolMessage | Command:
        if isinstance(tool_result, ToolMessage) and isinstance(tool_result.content, str):
            if not (self.tool_token_limit_before_evict and len(tool_result.content) > 4 * self.tool_token_limit_before_evict):
                return tool_result
            resolved_backend = self._get_backend(runtime)
            processed_message, files_update = self._process_large_message(tool_result, resolved_backend)
            if files_update is not None:
                return Command(update={"files": files_update, "messages": [processed_message]})
            return processed_message
        
        if isinstance(tool_result, Command):
            update = tool_result.update
            if update is None:
                return tool_result
            command_messages = update.get("messages", [])
            accumulated_file_updates = dict(update.get("files", {}))
            resolved_backend = self._get_backend(runtime)
            processed_messages = []
            for message in command_messages:
                if not (self.tool_token_limit_before_evict and isinstance(message, ToolMessage) and isinstance(message.content, str) and len(message.content) > 4 * self.tool_token_limit_before_evict):
                    processed_messages.append(message)
                    continue
                processed_message, files_update = self._process_large_message(message, resolved_backend)
                processed_messages.append(processed_message)
                if files_update is not None:
                    accumulated_file_updates.update(files_update)
            return Command(update={**update, "messages": processed_messages, "files": accumulated_file_updates})
        return tool_result
    
    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command],
    ) -> ToolMessage | Command:
        if self.tool_token_limit_before_evict is None or request.tool_call["name"] in TOOL_GENERATORS:
            return handler(request)
        tool_result = handler(request)
        return self._intercept_large_tool_result(tool_result, request.runtime)
    
    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]],
    ) -> ToolMessage | Command:
        if self.tool_token_limit_before_evict is None or request.tool_call["name"] in TOOL_GENERATORS:
            return await handler(request)
        tool_result = await handler(request)
        return self._intercept_large_tool_result(tool_result, request.runtime)
