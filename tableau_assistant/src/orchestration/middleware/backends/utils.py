"""
Shared utility functions for memory backend implementations.

This module contains both user-facing string formatters and structured
helpers used by backends. Structured helpers enable composition without
fragile string parsing.
"""

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

try:
    import wcmatch.glob as wcglob
    HAS_WCMATCH = True
except ImportError:
    import fnmatch
    HAS_WCMATCH = False

from tableau_assistant.src.orchestration.middleware.backends.protocol import (
    FileInfo,
    GrepMatch,
    FileData,
)


# Constants
EMPTY_CONTENT_WARNING = "System reminder: File exists but has empty contents"
MAX_LINE_LENGTH = 10000
LINE_NUMBER_WIDTH = 6
TOOL_RESULT_TOKEN_LIMIT = 20000  # Same threshold as eviction
TRUNCATION_GUIDANCE = "... [results truncated, try being more specific with your parameters]"


def sanitize_tool_call_id(tool_call_id: str) -> str:
    r"""Sanitize tool_call_id to prevent path traversal and separator issues.
    
    Replaces dangerous characters (., /, \) with underscores.
    """
    sanitized = tool_call_id.replace(".", "_").replace("/", "_").replace("\\", "_")
    return sanitized


def format_content_with_line_numbers(
    content: str | list[str],
    start_line: int = 1,
) -> str:
    """Format file content with line numbers (cat -n style).
    
    Chunks lines longer than MAX_LINE_LENGTH with continuation markers (e.g., 5.1, 5.2).
    
    Args:
        content: File content as string or list of lines
        start_line: Starting line number (default: 1)
    
    Returns:
        Formatted content with line numbers and continuation markers
    """
    if isinstance(content, str):
        lines = content.split("\n")
        if lines and lines[-1] == "":
            lines = lines[:-1]
    else:
        lines = content
    
    result_lines = []
    for i, line in enumerate(lines):
        line_num = i + start_line
        
        if len(line) <= MAX_LINE_LENGTH:
            result_lines.append(f"{line_num:{LINE_NUMBER_WIDTH}d}\t{line}")
        else:
            # Split long line into chunks with continuation markers
            num_chunks = (len(line) + MAX_LINE_LENGTH - 1) // MAX_LINE_LENGTH
            for chunk_idx in range(num_chunks):
                start = chunk_idx * MAX_LINE_LENGTH
                end = min(start + MAX_LINE_LENGTH, len(line))
                chunk = line[start:end]
                if chunk_idx == 0:
                    # First chunk: use normal line number
                    result_lines.append(f"{line_num:{LINE_NUMBER_WIDTH}d}\t{chunk}")
                else:
                    # Continuation chunks: use decimal notation (e.g., 5.1, 5.2)
                    continuation_marker = f"{line_num}.{chunk_idx}"
                    result_lines.append(f"{continuation_marker:>{LINE_NUMBER_WIDTH}}\t{chunk}")
    
    return "\n".join(result_lines)


def check_empty_content(content: str) -> str | None:
    """Check if content is empty and return warning message.
    
    Args:
        content: Content to check
    
    Returns:
        Warning message if empty, None otherwise
    """
    if not content or content.strip() == "":
        return EMPTY_CONTENT_WARNING
    return None


def file_data_to_string(file_data: dict[str, Any]) -> str:
    """Convert FileData to plain string content.
    
    Args:
        file_data: FileData dict with 'content' key
    
    Returns:
        Content as string with lines joined by newlines
    """
    return "\n".join(file_data["content"])


def create_file_data(content: str, created_at: str | None = None) -> FileData:
    """Create a FileData object with timestamps.
    
    Args:
        content: File content as string
        created_at: Optional creation timestamp (ISO format)
    
    Returns:
        FileData dict with content and timestamps
    """
    lines = content.split("\n") if isinstance(content, str) else content
    now = datetime.now(UTC).isoformat()
    
    return {
        "content": lines,
        "created_at": created_at or now,
        "modified_at": now,
    }


def update_file_data(file_data: dict[str, Any], content: str) -> FileData:
    """Update FileData with new content, preserving creation timestamp.
    
    Args:
        file_data: Existing FileData dict
        content: New content as string
    
    Returns:
        Updated FileData dict
    """
    lines = content.split("\n") if isinstance(content, str) else content
    now = datetime.now(UTC).isoformat()
    
    return {
        "content": lines,
        "created_at": file_data["created_at"],
        "modified_at": now,
    }


def format_read_response(
    file_data: dict[str, Any],
    offset: int,
    limit: int,
) -> str:
    """Format file data for read response with line numbers.
    
    Args:
        file_data: FileData dict
        offset: Line offset (0-indexed)
        limit: Maximum number of lines
    
    Returns:
        Formatted content or error message
    """
    content = file_data_to_string(file_data)
    empty_msg = check_empty_content(content)
    if empty_msg:
        return empty_msg
    
    lines = content.splitlines()
    start_idx = offset
    end_idx = min(start_idx + limit, len(lines))
    
    if start_idx >= len(lines):
        return f"Error: Line offset {offset} exceeds file length ({len(lines)} lines)"
    
    selected_lines = lines[start_idx:end_idx]
    return format_content_with_line_numbers(selected_lines, start_line=start_idx + 1)


def perform_string_replacement(
    content: str,
    old_string: str,
    new_string: str,
    replace_all: bool,
) -> tuple[str, int] | str:
    """Perform string replacement with occurrence validation.
    
    Args:
        content: Original content
        old_string: String to replace
        new_string: Replacement string
        replace_all: Whether to replace all occurrences
    
    Returns:
        Tuple of (new_content, occurrences) on success, or error message string
    """
    occurrences = content.count(old_string)
    
    if occurrences == 0:
        return f"Error: String not found in file: '{old_string}'"
    
    if occurrences > 1 and not replace_all:
        return (
            f"Error: String '{old_string}' appears {occurrences} times in file. "
            "Use replace_all=True to replace all instances, or provide a more "
            "specific string with surrounding context."
        )
    
    new_content = content.replace(old_string, new_string)
    return new_content, occurrences


def truncate_if_too_long(result: list[str] | str) -> list[str] | str:
    """Truncate list or string result if it exceeds token limit (rough estimate: 4 chars/token)."""
    if isinstance(result, list):
        total_chars = sum(len(item) for item in result)
        if total_chars > TOOL_RESULT_TOKEN_LIMIT * 4:
            truncated_len = len(result) * TOOL_RESULT_TOKEN_LIMIT * 4 // total_chars
            return result[:truncated_len] + [TRUNCATION_GUIDANCE]
        return result
    # string
    if len(result) > TOOL_RESULT_TOKEN_LIMIT * 4:
        return result[:TOOL_RESULT_TOKEN_LIMIT * 4] + "\n" + TRUNCATION_GUIDANCE
    return result


def validate_path(path: str | None) -> str:
    """Validate and normalize a path.
    
    Args:
        path: Path to validate
    
    Returns:
        Normalized path starting with /
    
    Raises:
        ValueError: If path is invalid
    """
    path = path or "/"
    if not path or path.strip() == "":
        raise ValueError("Path cannot be empty")
    
    # Check for path traversal
    if ".." in path or path.startswith("~"):
        raise ValueError(f"Path traversal not allowed: {path}")
    
    # Reject Windows absolute paths
    if re.match(r"^[a-zA-Z]:", path):
        raise ValueError(
            f"Windows absolute paths are not supported: {path}. "
            "Please use virtual paths starting with / (e.g., /workspace/file.txt)"
        )
    
    normalized = path if path.startswith("/") else "/" + path
    return normalized


def validate_directory_path(path: str | None) -> str:
    """Validate and normalize a directory path (ensures trailing slash).
    
    Args:
        path: Path to validate
    
    Returns:
        Normalized path starting with / and ending with /
    
    Raises:
        ValueError: If path is invalid
    """
    normalized = validate_path(path)
    if not normalized.endswith("/"):
        normalized += "/"
    return normalized


def glob_match(filename: str, pattern: str) -> bool:
    """Match filename against glob pattern.
    
    Args:
        filename: Filename to match
        pattern: Glob pattern
    
    Returns:
        True if matches, False otherwise
    """
    if HAS_WCMATCH:
        return wcglob.globmatch(filename, pattern, flags=wcglob.BRACE | wcglob.GLOBSTAR)
    else:
        # Fallback to fnmatch (less powerful but works)
        return fnmatch.fnmatch(filename, pattern)


def glob_search_files(
    files: dict[str, Any],
    pattern: str,
    path: str = "/",
) -> list[str]:
    """Search files dict for paths matching glob pattern.
    
    Args:
        files: Dictionary of file paths to FileData.
        pattern: Glob pattern (e.g., "*.py", "**/*.ts").
        path: Base path to search from.
    
    Returns:
        List of matching file paths, sorted by modification time (most recent first).
    """
    try:
        normalized_path = validate_directory_path(path)
    except ValueError:
        return []
    
    filtered = {fp: fd for fp, fd in files.items() if fp.startswith(normalized_path)}
    
    matches = []
    for file_path, file_data in filtered.items():
        relative = file_path[len(normalized_path):].lstrip("/")
        if not relative:
            relative = file_path.split("/")[-1]
        
        if glob_match(relative, pattern):
            matches.append((file_path, file_data.get("modified_at", "")))
    
    matches.sort(key=lambda x: x[1], reverse=True)
    return [fp for fp, _ in matches]


def grep_matches_from_files(
    files: dict[str, Any],
    pattern: str,
    path: str | None = None,
    glob_pattern: str | None = None,
) -> list[GrepMatch] | str:
    """Return structured grep matches from an in-memory files mapping.
    
    Returns a list of GrepMatch on success, or a string for invalid inputs
    (e.g., invalid regex).
    """
    try:
        regex = re.compile(pattern)
    except re.error as e:
        return f"Invalid regex pattern: {e}"
    
    try:
        normalized_path = validate_directory_path(path)
    except ValueError:
        return []
    
    filtered = {fp: fd for fp, fd in files.items() if fp.startswith(normalized_path)}
    
    if glob_pattern:
        filtered = {
            fp: fd for fp, fd in filtered.items()
            if glob_match(Path(fp).name, glob_pattern)
        }
    
    matches: list[GrepMatch] = []
    for file_path, file_data in filtered.items():
        content_lines = file_data.get("content", [])
        for line_num, line in enumerate(content_lines, 1):
            if regex.search(line):
                matches.append({
                    "path": file_path,
                    "line": int(line_num),
                    "text": line
                })
    return matches


def format_grep_matches(
    matches: list[GrepMatch],
    output_mode: Literal["files_with_matches", "content", "count"],
) -> str:
    """Format structured grep matches.
    
    Args:
        matches: List of GrepMatch dicts
        output_mode: Output format
    
    Returns:
        Formatted string output
    """
    if not matches:
        return "No matches found"
    
    # Group by file
    grouped: dict[str, list[tuple[int, str]]] = {}
    for m in matches:
        grouped.setdefault(m["path"], []).append((m["line"], m["text"]))
    
    if output_mode == "files_with_matches":
        return "\n".join(sorted(grouped.keys()))
    
    if output_mode == "count":
        lines = []
        for file_path in sorted(grouped.keys()):
            count = len(grouped[file_path])
            lines.append(f"{file_path}: {count}")
        return "\n".join(lines)
    
    # content mode
    lines = []
    for file_path in sorted(grouped.keys()):
        lines.append(f"{file_path}:")
        for line_num, line in grouped[file_path]:
            lines.append(f"  {line_num}: {line}")
    return "\n".join(lines)
