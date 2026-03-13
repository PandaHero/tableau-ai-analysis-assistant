# -*- coding: utf-8 -*-
"""洞察阶段只读文件工具。"""

from __future__ import annotations

import json
from typing import Any, Optional

from langchain_core.tools import BaseTool, StructuredTool

from .workspace import InsightWorkspace

FILESYSTEM_SYSTEM_PROMPT = """## 结果文件工作区

你当前只能通过只读文件工具访问查询结果。
请遵守以下规则：
1. 先调用 `list_result_files` 或阅读 `result_manifest.json`，不要假设文件一定存在。
2. 优先阅读 `result_manifest.json`、`profiles/*`、`preview.json`，只有在证据不足时再读 `chunks/*`。
3. 大文件必须分页读取；每次读取前先说明目的，例如“验证假设”或“补充证据”。
4. 禁止臆造文件内容，所有结论都要能回溯到具体文件或具体行数据。
"""


class InsightFilesystemMiddleware:
    """为洞察模型提供结果文件只读工具。"""

    def __init__(self, workspace: InsightWorkspace) -> None:
        self._workspace = workspace

    @property
    def workspace(self) -> InsightWorkspace:
        return self._workspace

    def get_system_prompt_suffix(self) -> str:
        """返回需要附加到 system prompt 的文件工具使用规则。"""
        return FILESYSTEM_SYSTEM_PROMPT

    def get_tools(self) -> list[BaseTool]:
        workspace = self._workspace

        def list_result_files() -> str:
            """列出当前工作区允许访问的结果文件。"""
            return json.dumps(
                {
                    "workspace_id": workspace.workspace_id,
                    "artifact_root": workspace.artifact_root,
                    "result_manifest_ref": workspace.result_manifest_ref,
                    "files": workspace.list_allowed_files(),
                },
                ensure_ascii=False,
            )

        def describe_result_file(file_path: str) -> str:
            """返回指定结果文件的结构摘要与元数据。"""
            return json.dumps(
                workspace.describe_file(file_path=file_path),
                ensure_ascii=False,
            )

        def read_result_file(
            file_path: str,
            offset: int = 0,
            limit: Optional[int] = None,
        ) -> str:
            """按行分页读取结果文件。"""
            return json.dumps(
                workspace.read_text_lines(
                    file_path=file_path,
                    offset=offset,
                    limit=limit,
                ),
                ensure_ascii=False,
            )

        def read_result_rows(
            file_path: str,
            offset: int = 0,
            limit: Optional[int] = None,
            columns: Optional[list[str]] = None,
        ) -> str:
            """分页读取 preview/chunk 中的结构化行数据。"""
            return json.dumps(
                workspace.read_rows(
                    file_path=file_path,
                    offset=offset,
                    limit=limit,
                    columns=columns,
                ),
                ensure_ascii=False,
            )

        def read_spilled_artifact(
            file_path: str,
            offset: int = 0,
            limit: Optional[int] = None,
        ) -> str:
            """读取 spill 目录中的大结果文件。"""
            normalized_path = str(file_path or "").replace("\\", "/")
            if "/spill/" not in f"/{normalized_path.strip('/')}":
                raise ValueError("read_spilled_artifact 只能读取 spill 目录中的文件")
            return json.dumps(
                workspace.read_text_lines(
                    file_path=file_path,
                    offset=offset,
                    limit=limit,
                ),
                ensure_ascii=False,
            )

        return [
            StructuredTool.from_function(
                name="list_result_files",
                description="列出当前工作区允许访问的结果文件。",
                func=list_result_files,
            ),
            StructuredTool.from_function(
                name="describe_result_file",
                description="描述指定结果文件的结构、行数、键名和大小。",
                func=describe_result_file,
            ),
            StructuredTool.from_function(
                name="read_result_file",
                description="按行分页读取结果文件，适合 manifest、profile 或普通文本。",
                func=read_result_file,
            ),
            StructuredTool.from_function(
                name="read_result_rows",
                description="分页读取 preview/chunk 中的结构化行数据，可选列裁剪。",
                func=read_result_rows,
            ),
            StructuredTool.from_function(
                name="read_spilled_artifact",
                description="读取 spill 目录中的大文件结果。",
                func=read_spilled_artifact,
            ),
        ]


__all__ = [
    "InsightFilesystemMiddleware",
]
