# -*- coding: utf-8 -*-
"""洞察阶段的结果文件工作区。"""

from __future__ import annotations

import fnmatch
import json
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from analytics_assistant.src.orchestration.query_graph import (
    load_json_artifact,
    resolve_artifact_ref,
)

_DEFAULT_PAGE_SIZE = 100
_DEFAULT_MAX_PAGE_SIZE = 500


class InsightWorkspace(BaseModel):
    """洞察阶段可访问的只读工作区。"""

    workspace_id: str
    run_id: str
    session_id: Optional[str] = None
    artifact_root: str
    result_manifest_ref: str
    result_manifest_path: str
    allowed_files: list[str] = Field(default_factory=list)
    default_page_size: int = _DEFAULT_PAGE_SIZE
    max_page_size: int = _DEFAULT_MAX_PAGE_SIZE
    artifact_root_dir: Optional[str] = None
    manifest: dict[str, Any] = Field(default_factory=dict)

    def artifact_root_path(self) -> Path:
        return resolve_artifact_ref(
            self.artifact_root,
            artifact_root_dir=self.artifact_root_dir,
        )

    def list_allowed_files(self) -> list[str]:
        """列出当前工作区允许读取的文件。"""
        base_dir = self.artifact_root_path()
        results: list[str] = []
        if not base_dir.exists():
            return results

        for path in sorted(base_dir.rglob("*")):
            if not path.is_file():
                continue
            relative_path = path.relative_to(base_dir).as_posix()
            if self.is_allowed(relative_path):
                results.append(f"{self.artifact_root}{relative_path}")
        return results

    def is_allowed(self, relative_path: str) -> bool:
        normalized = str(relative_path or "").strip().lstrip("/")
        if not normalized:
            return False
        return any(
            fnmatch.fnmatch(normalized, pattern)
            for pattern in self.allowed_files
        )

    def resolve_file(self, file_path: str) -> tuple[str, Path]:
        """把用户传入的路径解析成工作区相对路径和磁盘路径。"""
        normalized = str(file_path or "").strip().replace("\\", "/")
        if not normalized:
            raise ValueError("file_path 不能为空")

        artifact_root_prefix = self.artifact_root.rstrip("/")
        if normalized.startswith(f"{artifact_root_prefix}/"):
            relative_path = normalized[len(artifact_root_prefix) + 1:]
        elif normalized == artifact_root_prefix:
            raise ValueError("file_path 必须指向具体文件")
        else:
            relative_path = normalized.lstrip("/")

        relative_path = relative_path.strip("/")
        if not self.is_allowed(relative_path):
            raise ValueError(f"file_path 不在当前工作区 allowlist 内: {file_path}")

        resolved_path = self.artifact_root_path() / Path(relative_path)
        if not resolved_path.exists() or not resolved_path.is_file():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        return relative_path, resolved_path

    def read_text_lines(
        self,
        *,
        file_path: str,
        offset: int = 0,
        limit: Optional[int] = None,
    ) -> dict[str, Any]:
        """按行读取结果文件。"""
        relative_path, resolved_path = self.resolve_file(file_path)
        actual_limit = _normalize_page_size(
            limit=limit,
            default_page_size=self.default_page_size,
            max_page_size=self.max_page_size,
        )

        content = resolved_path.read_text(encoding="utf-8")
        lines = content.splitlines()
        start = max(0, int(offset))
        end = min(start + actual_limit, len(lines))
        return {
            "file_path": f"{self.artifact_root}{relative_path}",
            "relative_path": relative_path,
            "offset": start,
            "limit": actual_limit,
            "total_lines": len(lines),
            "lines": lines[start:end],
            "has_more": end < len(lines),
        }

    def read_rows(
        self,
        *,
        file_path: str,
        offset: int = 0,
        limit: Optional[int] = None,
        columns: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """按行读取 preview/chunk 中的结构化行数据。"""
        relative_path, resolved_path = self.resolve_file(file_path)
        actual_limit = _normalize_page_size(
            limit=limit,
            default_page_size=self.default_page_size,
            max_page_size=self.max_page_size,
        )
        suffix = resolved_path.suffix.lower()
        normalized_columns = [
            str(column).strip()
            for column in (columns or [])
            if str(column).strip()
        ]

        if suffix == ".jsonl":
            all_rows = [
                json.loads(line)
                for line in resolved_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        elif suffix == ".json":
            payload = json.loads(resolved_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and isinstance(payload.get("rows"), list):
                all_rows = list(payload["rows"])
            else:
                raise ValueError("当前文件不包含可直接读取的 rows")
        else:
            raise ValueError("read_result_rows 仅支持 .json 或 .jsonl 文件")

        start = max(0, int(offset))
        end = min(start + actual_limit, len(all_rows))
        rows = all_rows[start:end]
        if normalized_columns:
            rows = [
                {
                    column: row.get(column)
                    for column in normalized_columns
                }
                for row in rows
                if isinstance(row, dict)
            ]

        return {
            "file_path": f"{self.artifact_root}{relative_path}",
            "relative_path": relative_path,
            "offset": start,
            "limit": actual_limit,
            "row_count": len(all_rows),
            "rows": rows,
            "has_more": end < len(all_rows),
        }

    def describe_file(self, *, file_path: str) -> dict[str, Any]:
        """返回文件的元数据和结构摘要。"""
        relative_path, resolved_path = self.resolve_file(file_path)
        content = resolved_path.read_text(encoding="utf-8")
        suffix = resolved_path.suffix.lower()
        payload: dict[str, Any] = {
            "file_path": f"{self.artifact_root}{relative_path}",
            "relative_path": relative_path,
            "size_bytes": resolved_path.stat().st_size,
            "suffix": suffix,
        }

        if suffix == ".json":
            data = json.loads(content)
            if isinstance(data, dict):
                payload["keys"] = sorted(data.keys())
                if isinstance(data.get("rows"), list):
                    payload["row_count"] = len(data["rows"])
                if isinstance(data.get("columns"), list):
                    payload["columns"] = [column.get("name") for column in data["columns"]]
        elif suffix == ".jsonl":
            lines = [line for line in content.splitlines() if line.strip()]
            payload["row_count"] = len(lines)
        else:
            payload["line_count"] = len(content.splitlines())

        return payload


def prepare_insight_workspace(
    *,
    result_manifest_ref: str,
    session_id: Optional[str] = None,
    artifact_root_dir: Optional[str] = None,
    default_page_size: int = _DEFAULT_PAGE_SIZE,
    max_page_size: int = _DEFAULT_MAX_PAGE_SIZE,
) -> InsightWorkspace:
    """根据 `result_manifest_ref` 构建洞察工作区。"""
    manifest = load_json_artifact(
        result_manifest_ref,
        artifact_root_dir=artifact_root_dir,
    )
    if not isinstance(manifest, dict):
        raise ValueError("result_manifest 内容必须是对象")

    artifact_root = str(manifest.get("artifact_root") or "").strip()
    if not artifact_root:
        raise ValueError("result_manifest 缺少 artifact_root")

    allowed_files = manifest.get("allowed_files") or []
    if not isinstance(allowed_files, list) or not allowed_files:
        raise ValueError("result_manifest 缺少 allowed_files")

    run_id = str(manifest.get("run_id") or "").strip()
    if not run_id:
        raise ValueError("result_manifest 缺少 run_id")

    return InsightWorkspace(
        workspace_id=f"ws_{uuid4().hex[:12]}",
        run_id=run_id,
        session_id=session_id,
        artifact_root=artifact_root,
        result_manifest_ref=result_manifest_ref,
        result_manifest_path=str(
            resolve_artifact_ref(
                result_manifest_ref,
                artifact_root_dir=artifact_root_dir,
            )
        ),
        allowed_files=[str(item) for item in allowed_files],
        default_page_size=max(1, int(default_page_size)),
        max_page_size=max(max_page_size, default_page_size, 1),
        artifact_root_dir=str(artifact_root_dir) if artifact_root_dir is not None else None,
        manifest=manifest,
    )


def _normalize_page_size(
    *,
    limit: Optional[int],
    default_page_size: int,
    max_page_size: int,
) -> int:
    try:
        resolved_limit = int(limit) if limit is not None else int(default_page_size)
    except (TypeError, ValueError):
        resolved_limit = int(default_page_size)
    return max(1, min(resolved_limit, int(max_page_size)))


__all__ = [
    "InsightWorkspace",
    "prepare_insight_workspace",
]
