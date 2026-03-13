# -*- coding: utf-8 -*-
"""查询结果工件物化服务。

这个模块负责把查询结果正式落盘为 `result_manifest`、`profiles` 和 `chunks`。
设计目标有三点：
1. 让 `query_graph` 输出稳定的文件工件，而不是只返回内存中的 `tableData`。
2. 为后续 `answer_graph` 的文件驱动洞察提供固定入口。
3. 控制 SSE 预览体积，避免把整份结果直接塞进流事件。
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from analytics_assistant.src.agents.insight.components.data_profiler import DataProfiler
from analytics_assistant.src.agents.insight.schemas.output import DataProfile
from analytics_assistant.src.core.schemas.execute_result import ExecuteResult
from analytics_assistant.src.infra.config import get_config

_DEFAULT_PREVIEW_ROW_LIMIT = 50
_DEFAULT_CHUNK_ROW_LIMIT = 500


def materialize_result_artifacts(
    *,
    execute_result: ExecuteResult,
    run_id: str,
    data_profile: Optional[DataProfile] = None,
    artifact_root_dir: Optional[str | Path] = None,
    preview_row_limit: Optional[int] = None,
    chunk_row_limit: Optional[int] = None,
) -> dict[str, Any]:
    """把查询结果物化为 manifest/chunks/profiles。

    返回值同时包含：
    - 文件引用：给 root/query/answer graph 和 SSE 使用
    - 预览数据：给 `table_result` 事件直接展示
    - allowlist：给后续文件工具工作区使用
    """

    normalized_run_id = _sanitize_path_segment(run_id) or "run_local"
    preview_limit = max(1, int(preview_row_limit or _DEFAULT_PREVIEW_ROW_LIMIT))
    chunk_limit = max(1, int(chunk_row_limit or _DEFAULT_CHUNK_ROW_LIMIT))

    artifact_base_dir = _resolve_artifact_base_dir(artifact_root_dir)
    result_dir = artifact_base_dir / "runs" / normalized_run_id / "result"
    profiles_dir = result_dir / "profiles"
    chunks_dir = result_dir / "chunks"

    if result_dir.exists():
        # 每个 run 的结果目录都视为本轮独占，重新物化时直接覆盖旧内容。
        shutil.rmtree(result_dir)
    profiles_dir.mkdir(parents=True, exist_ok=True)
    chunks_dir.mkdir(parents=True, exist_ok=True)

    resolved_profile = data_profile or DataProfiler().generate(execute_result)
    preview_rows = list(execute_result.data[:preview_limit])
    preview_truncated = execute_result.row_count > len(preview_rows)

    public_root = _resolve_artifact_public_root()
    preview_ref = _public_ref(public_root, "runs", normalized_run_id, "result", "preview.json")
    data_profile_ref = _public_ref(
        public_root, "runs", normalized_run_id, "result", "profiles", "data_profile.json"
    )
    summary_profile_ref = _public_ref(
        public_root, "runs", normalized_run_id, "result", "profiles", "summary.json"
    )

    _write_json(
        result_dir / "preview.json",
        {
            "columns": [
                {
                    "name": column.name,
                    "dataType": column.data_type,
                    "isDimension": column.is_dimension,
                    "isMeasure": column.is_measure,
                    "isComputation": column.is_computation,
                }
                for column in execute_result.columns
            ],
            "rows": preview_rows,
            "rowCount": execute_result.row_count,
            "previewRowCount": len(preview_rows),
            "truncated": preview_truncated,
            "executionTimeMs": execute_result.execution_time_ms,
            "queryId": execute_result.query_id,
        },
    )
    _write_json(
        profiles_dir / "data_profile.json",
        resolved_profile.model_dump(mode="json"),
    )
    _write_json(
        profiles_dir / "summary.json",
        _build_profile_summary_payload(resolved_profile),
    )

    chunk_entries: list[dict[str, Any]] = []
    for index in range(0, len(execute_result.data), chunk_limit):
        chunk_rows = execute_result.data[index:index + chunk_limit]
        chunk_number = index // chunk_limit + 1
        chunk_name = f"chunk_{chunk_number:04d}.jsonl"
        chunk_path = chunks_dir / chunk_name
        _write_jsonl(chunk_path, chunk_rows)
        chunk_entries.append({
            "path": _public_ref(
                public_root,
                "runs",
                normalized_run_id,
                "result",
                "chunks",
                chunk_name,
            ),
            "row_start": index,
            "row_end": index + len(chunk_rows) - 1,
            "row_count": len(chunk_rows),
        })

    manifest_ref = _public_ref(public_root, "runs", normalized_run_id, "result", "result_manifest.json")
    profiles_ref = _public_ref(public_root, "runs", normalized_run_id, "result", "profiles") + "/"
    chunks_ref = _public_ref(public_root, "runs", normalized_run_id, "result", "chunks") + "/"
    artifact_root_ref = _public_ref(public_root, "runs", normalized_run_id, "result") + "/"

    manifest_payload = {
        "version": "1.0",
        "generated_at": _utc_now_iso(),
        "run_id": normalized_run_id,
        "query_id": execute_result.query_id,
        "row_count": execute_result.row_count,
        "column_count": len(execute_result.columns),
        "execution_time_ms": execute_result.execution_time_ms,
        "truncated": preview_truncated,
        "artifact_root": artifact_root_ref,
        "preview_ref": preview_ref,
        "profiles_ref": profiles_ref,
        "chunks_ref": chunks_ref,
        "allowed_files": [
            "result_manifest.json",
            "preview.json",
            "profiles/*",
            "chunks/*",
        ],
        "columns": [
            {
                "name": column.name,
                "data_type": column.data_type,
                "is_dimension": column.is_dimension,
                "is_measure": column.is_measure,
                "is_computation": column.is_computation,
            }
            for column in execute_result.columns
        ],
        "profiles": [
            {
                "name": "data_profile",
                "path": data_profile_ref,
            },
            {
                "name": "summary",
                "path": summary_profile_ref,
            },
        ],
        "chunks": chunk_entries,
    }
    _write_json(result_dir / "result_manifest.json", manifest_payload)

    return {
        "result_manifest_ref": manifest_ref,
        "profiles_ref": profiles_ref,
        "chunks_ref": chunks_ref,
        "artifact_root": artifact_root_ref,
        "allowed_files": list(manifest_payload["allowed_files"]),
        "preview_table_data": {
            "columns": [
                {
                    "name": column.name,
                    "dataType": column.data_type,
                    "isDimension": column.is_dimension,
                    "isMeasure": column.is_measure,
                }
                for column in execute_result.columns
            ],
            "rows": preview_rows,
            "rowCount": execute_result.row_count,
            "executionTimeMs": execute_result.execution_time_ms,
        },
        "truncated": preview_truncated,
        "data_profile_dict": resolved_profile.model_dump(mode="json"),
    }


def resolve_artifact_ref(
    artifact_ref: str,
    *,
    artifact_root_dir: Optional[str | Path] = None,
) -> Path:
    """把对外工件引用解析为磁盘路径。"""

    normalized_ref = str(artifact_ref or "").strip().replace("\\", "/")
    if not normalized_ref:
        raise ValueError("artifact_ref must not be empty")

    public_root = _resolve_artifact_public_root()
    relative_ref = normalized_ref.strip("/")
    prefix = public_root.strip("/") + "/"
    if relative_ref.startswith(prefix):
        relative_ref = relative_ref[len(prefix):]

    return _resolve_artifact_base_dir(artifact_root_dir) / Path(relative_ref)


def load_json_artifact(
    artifact_ref: str,
    *,
    artifact_root_dir: Optional[str | Path] = None,
) -> Any:
    """读取 JSON 工件。"""

    return json.loads(
        resolve_artifact_ref(
            artifact_ref,
            artifact_root_dir=artifact_root_dir,
        ).read_text(encoding="utf-8")
    )


def _resolve_artifact_base_dir(custom_root_dir: Optional[str | Path]) -> Path:
    """解析工件根目录。

    优先级：
    1. 显式传入
    2. `app.yaml` 中的 `artifacts.root_dir`
    3. 仓库根目录下的 `artifacts/`
    """

    if custom_root_dir is not None:
        return Path(custom_root_dir).resolve()

    try:
        config = get_config()
        configured_root = str(config.get("artifacts", {}).get("root_dir") or "").strip()
        if configured_root:
            return Path(configured_root).resolve()
    except Exception:
        # 配置加载失败时回退到默认目录，不阻断结果物化。
        pass

    return Path(__file__).resolve().parents[4] / "artifacts"


def _build_profile_summary_payload(data_profile: DataProfile) -> dict[str, Any]:
    """生成轻量级 profile 摘要，供 manifest 和文件工具快速浏览。"""

    return {
        "row_count": data_profile.row_count,
        "column_count": data_profile.column_count,
        "columns": [
            {
                "column_name": column.column_name,
                "data_type": column.data_type,
                "is_numeric": column.is_numeric,
                "null_count": column.null_count,
                "error": column.error,
                "numeric_stats": (
                    column.numeric_stats.model_dump(mode="json")
                    if column.numeric_stats is not None
                    else None
                ),
                "categorical_stats": (
                    column.categorical_stats.model_dump(mode="json")
                    if column.categorical_stats is not None
                    else None
                ),
            }
            for column in data_profile.columns_profile
        ],
    }


def _resolve_artifact_public_root() -> str:
    """解析对外暴露的工件前缀。

    物理落盘位置允许被配置或在测试中重定向，但对外引用保持稳定的逻辑前缀。
    """

    try:
        config = get_config()
        configured_prefix = str(config.get("artifacts", {}).get("public_prefix") or "").strip()
        if configured_prefix:
            return configured_prefix.strip("/").replace("\\", "/")
    except Exception:
        pass

    return "artifacts"


def _public_ref(public_root: str, *parts: str) -> str:
    return "/".join([public_root.strip("/"), *[str(part).strip("/") for part in parts if str(part).strip("/")]])


def _sanitize_path_segment(value: str) -> str:
    text = str(value or "").strip()
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in text)


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    lines = [
        json.dumps(row, ensure_ascii=False, default=str)
        for row in rows
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


__all__ = [
    "load_json_artifact",
    "materialize_result_artifacts",
    "resolve_artifact_ref",
]
