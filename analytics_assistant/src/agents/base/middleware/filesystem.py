# -*- coding: utf-8 -*-
"""
FilesystemMiddleware — 虚拟文件系统中间件

参考 deepagents.FilesystemMiddleware 的核心设计，为本项目定制实现。
不依赖 deepagents 包，仅使用 LangChain 标准接口。

核心能力：
1. 当工具返回结果超过 token 阈值时，自动将完整结果存入内存虚拟文件系统，
   截断 ToolMessage 并附加文件路径引用。
2. 向 Agent 注入 read_file 工具，允许按需读取被截断的完整结果。
3. 在 LLM 调用前注入文件系统使用说明到 system prompt。

与 MiddlewareRunner 兼容：
- 实现 awrap_tool_call(request, handler) 钩子
- 实现 awrap_model_call(request, handler) 钩子

使用示例：
    from analytics_assistant.src.agents.base.middleware.filesystem import (
        FilesystemMiddleware,
    )

    fs_mw = FilesystemMiddleware(
        tool_token_limit_before_evict=2000,
    )
    middleware_stack = [fs_mw, ...]
"""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any, Optional

from langchain_core.messages import BaseMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool, StructuredTool

logger = logging.getLogger(__name__)

# 粗略估算：1 token ≈ 4 个字符
NUM_CHARS_PER_TOKEN = 4

# 这些工具的输出不需要做截断检查（它们自身已有大小控制或输出较小）
TOOLS_EXCLUDED_FROM_EVICTION = frozenset({
    "ls",
    "read_file",
    "write_file",
})

TOO_LARGE_TOOL_MSG = (
    "工具返回结果过大，已保存到虚拟文件系统：{file_path}\n"
    "请使用 read_file 工具按需读取，建议指定 offset 和 limit 分页读取。\n"
    "例如：read_file(file_path=\"{file_path}\", offset=0, limit=100)\n\n"
    "以下是结果的头尾预览：\n\n{content_sample}"
)

FILESYSTEM_SYSTEM_PROMPT = """## 虚拟文件系统

当工具返回的结果过大时，系统会自动将完整结果保存到虚拟文件系统中，并提供文件路径引用。
你可以使用 read_file 工具按需读取被截断的完整结果：

- read_file(file_path, offset, limit)：读取指定文件，支持分页
  - file_path: 文件路径（如 /large_tool_results/xxx）
  - offset: 起始行号（0-indexed，默认 0）
  - limit: 读取行数（默认 100）

使用建议：
- 先用小的 limit 浏览文件结构
- 根据需要读取特定区域的数据
- 避免一次性读取整个大文件"""

READ_FILE_DESCRIPTION = (
    "读取虚拟文件系统中的文件。当工具返回结果过大被截断时，"
    "可通过此工具按需读取完整内容。支持 offset 和 limit 参数分页读取。"
)


# ═══════════════════════════════════════════════════════════════════════════
# 虚拟文件存储
# ═══════════════════════════════════════════════════════════════════════════

class VirtualFileStore:
    """简单的内存虚拟文件存储。

    线程安全不是必需的，因为每个 Agent 执行实例会创建独立的
    FilesystemMiddleware（进而创建独立的 VirtualFileStore）。
    """

    def __init__(self) -> None:
        self._files: dict[str, dict[str, Any]] = {}

    def write(self, path: str, content: str) -> None:
        """写入文件。"""
        now = datetime.now(timezone.utc).isoformat()
        self._files[path] = {
            "content": content,
            "created_at": now,
            "modified_at": now,
        }
        logger.debug(f"VirtualFileStore: 写入 {path} ({len(content)} chars)")

    def read(
        self,
        path: str,
        offset: int = 0,
        limit: int = 100,
    ) -> str:
        """读取文件，支持分页。

        Args:
            path: 文件路径
            offset: 起始行号（0-indexed）
            limit: 读取行数

        Returns:
            带行号的文件内容
        """
        file_data = self._files.get(path)
        if file_data is None:
            return f"错误：文件 {path} 不存在"

        content = file_data["content"]
        lines = content.splitlines()
        total_lines = len(lines)

        if offset >= total_lines:
            return f"错误：offset ({offset}) 超出文件总行数 ({total_lines})"

        end = min(offset + limit, total_lines)
        selected = lines[offset:end]

        # 带行号输出（类似 cat -n 格式）
        numbered_lines = []
        for i, line in enumerate(selected, start=offset + 1):
            numbered_lines.append(f"{i:>6}\t{line}")

        result = "\n".join(numbered_lines)
        if end < total_lines:
            result += f"\n\n[显示 {offset + 1}-{end} 行，共 {total_lines} 行]"

        return result

    def list_files(self) -> list[str]:
        """列出所有文件路径。"""
        return list(self._files.keys())

    @property
    def file_count(self) -> int:
        return len(self._files)

    def cleanup(self) -> None:
        """清空所有文件。"""
        self._files.clear()


# ═══════════════════════════════════════════════════════════════════════════
# 内容预览生成
# ═══════════════════════════════════════════════════════════════════════════

def _create_content_preview(
    content: str,
    *,
    head_lines: int = 5,
    tail_lines: int = 5,
) -> str:
    """创建内容预览，显示头部和尾部，中间截断。

    Args:
        content: 完整内容
        head_lines: 显示头部行数
        tail_lines: 显示尾部行数

    Returns:
        格式化的预览文本
    """
    lines = content.splitlines()

    if len(lines) <= head_lines + tail_lines:
        numbered = [f"{i:>6}\t{line[:1000]}" for i, line in enumerate(lines, 1)]
        return "\n".join(numbered)

    head = [f"{i:>6}\t{line[:1000]}" for i, line in enumerate(lines[:head_lines], 1)]
    truncated_count = len(lines) - head_lines - tail_lines
    tail_start = len(lines) - tail_lines + 1
    tail = [
        f"{i:>6}\t{line[:1000]}"
        for i, line in enumerate(lines[-tail_lines:], tail_start)
    ]

    return (
        "\n".join(head)
        + f"\n... [{truncated_count} 行已省略] ...\n"
        + "\n".join(tail)
    )


def _sanitize_tool_call_id(tool_call_id: str) -> str:
    """清理 tool_call_id 使其可作为文件名。"""
    return re.sub(r"[^a-zA-Z0-9_\-]", "_", tool_call_id or "unknown")


# ═══════════════════════════════════════════════════════════════════════════
# FilesystemMiddleware
# ═══════════════════════════════════════════════════════════════════════════

class FilesystemMiddleware:
    """虚拟文件系统中间件。

    与 MiddlewareRunner 兼容，通过 awrap_tool_call 和 awrap_model_call 钩子工作。

    功能：
    1. 自动截断超过 token 阈值的工具返回结果，存入虚拟文件系统
    2. 提供 read_file 工具，允许 Agent 按需读取被截断的完整结果
    3. 在 LLM 调用前注入文件系统使用说明

    Args:
        tool_token_limit_before_evict: 触发截断的 token 阈值。
            当工具返回结果的估算 token 数超过此值时，自动存入虚拟文件系统。
            设为 None 禁用自动截断。默认 2000。
        system_prompt: 自定义系统提示（覆盖默认提示）。
    """

    def __init__(
        self,
        tool_token_limit_before_evict: Optional[int] = 2000,
        system_prompt: Optional[str] = None,
    ) -> None:
        self._tool_token_limit_before_evict = tool_token_limit_before_evict
        self._system_prompt = system_prompt or FILESYSTEM_SYSTEM_PROMPT
        self._store = VirtualFileStore()
        self._read_file_tool = self._create_read_file_tool()

    @property
    def store(self) -> VirtualFileStore:
        """获取虚拟文件存储实例。"""
        return self._store

    @property
    def read_file_tool(self) -> BaseTool:
        """获取 read_file 工具实例（可添加到工具列表中）。"""
        return self._read_file_tool

    def get_tools(self) -> list[BaseTool]:
        """获取此中间件提供的所有工具。"""
        return [self._read_file_tool]

    def cleanup(self) -> None:
        """清理虚拟文件存储。"""
        self._store.cleanup()

    # ═══════════════════════════════════════════════════════════════════════
    # 工具创建
    # ═══════════════════════════════════════════════════════════════════════

    def _create_read_file_tool(self) -> BaseTool:
        """创建 read_file 工具。"""
        store = self._store

        def read_file(
            file_path: str,
            offset: int = 0,
            limit: int = 100,
        ) -> str:
            """读取虚拟文件系统中的文件。

            Args:
                file_path: 文件路径
                offset: 起始行号（0-indexed）
                limit: 读取行数
            """
            return store.read(file_path, offset=offset, limit=limit)

        return StructuredTool.from_function(
            name="read_file",
            description=READ_FILE_DESCRIPTION,
            func=read_file,
        )

    # ═══════════════════════════════════════════════════════════════════════
    # MiddlewareRunner 钩子
    # ═══════════════════════════════════════════════════════════════════════

    async def awrap_tool_call(
        self,
        request: Any,
        handler: Callable[[Any], Awaitable[Any]],
    ) -> Any:
        """截断大工具结果并存入虚拟文件系统。

        当工具返回结果的估算 token 数超过阈值时：
        1. 将完整结果写入虚拟文件系统
        2. 用截断预览 + 文件路径引用替换原始结果

        Args:
            request: ToolCallRequest
            handler: 下一个处理器

        Returns:
            ToolMessage（可能已截断）
        """
        result = await handler(request)

        # 无阈值或工具在排除列表中，直接返回
        if self._tool_token_limit_before_evict is None:
            return result

        tool_name = ""
        tool_call_id = ""
        if hasattr(request, "tool_call") and isinstance(request.tool_call, dict):
            tool_name = request.tool_call.get("name", "")
            tool_call_id = request.tool_call.get("id", "")

        if tool_name in TOOLS_EXCLUDED_FROM_EVICTION:
            return result

        # 提取文本内容
        content_str = ""
        if isinstance(result, ToolMessage):
            content_str = (
                result.content
                if isinstance(result.content, str)
                else str(result.content)
            )
        elif isinstance(result, str):
            content_str = result
        else:
            return result

        # 检查是否超过阈值
        char_limit = NUM_CHARS_PER_TOKEN * self._tool_token_limit_before_evict
        if len(content_str) <= char_limit:
            return result

        # 存入虚拟文件系统
        sanitized_id = _sanitize_tool_call_id(tool_call_id)
        file_path = f"/large_tool_results/{sanitized_id}"
        self._store.write(file_path, content_str)

        # 创建预览
        content_sample = _create_content_preview(content_str)
        replacement_text = TOO_LARGE_TOOL_MSG.format(
            file_path=file_path,
            content_sample=content_sample,
        )

        logger.info(
            f"FilesystemMiddleware: 工具 '{tool_name}' 结果过大 "
            f"({len(content_str)} chars ≈ {len(content_str) // NUM_CHARS_PER_TOKEN} tokens)，"
            f"已截断并存入 {file_path}"
        )

        # 返回截断后的结果
        if isinstance(result, ToolMessage):
            return ToolMessage(
                content=replacement_text,
                tool_call_id=result.tool_call_id,
                name=result.name,
            )
        return replacement_text

    async def awrap_model_call(
        self,
        request: Any,
        handler: Callable[[Any], Awaitable[Any]],
    ) -> Any:
        """在 LLM 调用前注入文件系统使用说明。

        当虚拟文件系统中有文件时，在 system prompt 中追加使用说明，
        让 Agent 知道可以用 read_file 工具读取被截断的结果。

        Args:
            request: ModelRequest
            handler: 下一个处理器

        Returns:
            ModelResponse
        """
        # 只有在有文件时才注入提示
        if self._store.file_count == 0:
            return await handler(request)

        # 注入系统提示
        if hasattr(request, "messages") and request.messages:
            messages = list(request.messages)
            file_list = "\n".join(
                f"  - {fp}" for fp in self._store.list_files()
            )
            prompt_addition = (
                f"\n\n{self._system_prompt}\n\n"
                f"当前虚拟文件系统中的文件：\n{file_list}"
            )

            # 查找并追加到 system message
            injected = False
            for i, msg in enumerate(messages):
                if isinstance(msg, SystemMessage):
                    content = str(msg.content)
                    if "虚拟文件系统" not in content:
                        messages[i] = SystemMessage(
                            content=content + prompt_addition
                        )
                        injected = True
                    break

            if injected and hasattr(request, "override"):
                request = request.override(messages=messages)

        return await handler(request)


# ═══════════════════════════════════════════════════════════════════════════
# 导出
# ═══════════════════════════════════════════════════════════════════════════

__all__ = [
    "FilesystemMiddleware",
    "VirtualFileStore",
]
