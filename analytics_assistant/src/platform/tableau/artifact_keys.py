"""Tableau metadata / artifact key builders.

集中定义 metadata、字段索引与预热请求的 key 规则，避免各模块各自拼接字符串。
"""

from __future__ import annotations

import re
from typing import Iterable, Optional


def normalize_tableau_site(site: Optional[str]) -> str:
    """统一 site 维度，缺省时回退到 `default`。"""

    return str(site or "").strip().lower() or "default"


def build_datasource_identity_cache_key(
    *,
    datasource_name: str,
    project_name: Optional[str],
    site: Optional[str],
) -> str:
    """构造 datasource 名称解析缓存 key。"""

    normalized_name = str(datasource_name or "").strip().lower()
    normalized_project = str(project_name or "").strip().lower()
    normalized_site = normalize_tableau_site(site)
    return f"{normalized_site}:{normalized_project}:{normalized_name}"


def build_data_model_cache_key(*, datasource_id: str, site: Optional[str]) -> str:
    """构造 DataModel 进程缓存 key。"""

    return f"{normalize_tableau_site(site)}:{datasource_id}"


def build_metadata_snapshot_cache_key(
    *,
    datasource_id: str,
    site: Optional[str],
    schema_hash: Optional[str],
) -> str:
    """构造 metadata snapshot 逻辑 key。"""

    return _build_versioned_artifact_cache_key(
        prefix="metadata_snapshot",
        datasource_id=datasource_id,
        site=site,
        schema_hash=schema_hash,
    )


def build_field_index_name(
    *,
    datasource_id: str,
    site: Optional[str],
    schema_hash: Optional[str],
) -> str:
    """构造字段语义索引名，显式纳入 site 和 schema 版本。"""

    return _build_versioned_index_name(
        prefix="field_semantic",
        datasource_id=datasource_id,
        site=site,
        schema_hash=schema_hash,
    )


def build_field_index_prefix(
    *,
    datasource_id: str,
    site: Optional[str],
) -> str:
    """构造字段语义索引前缀，用于清理旧 schema 版本。"""

    return _build_versioned_index_prefix(
        prefix="field_semantic",
        datasource_id=datasource_id,
        site=site,
    )


def build_field_values_index_name(
    *,
    datasource_id: str,
    site: Optional[str],
    schema_hash: Optional[str],
) -> str:
    """构造字段值索引名，显式纳入 site 和 schema 版本。"""

    return _build_versioned_index_name(
        prefix="field_values",
        datasource_id=datasource_id,
        site=site,
        schema_hash=schema_hash,
    )


def build_field_values_index_prefix(
    *,
    datasource_id: str,
    site: Optional[str],
) -> str:
    """构造字段值索引前缀，用于清理旧 schema 版本。"""

    return _build_versioned_index_prefix(
        prefix="field_values",
        datasource_id=datasource_id,
        site=site,
    )


def build_field_artifact_key(
    *,
    datasource_id: str,
    site: Optional[str],
    artifact_type: str,
    schema_hash: Optional[str],
) -> str:
    """构造字段 artifact 的版本化逻辑 key。"""

    return _build_versioned_artifact_cache_key(
        prefix="field_artifact",
        datasource_id=datasource_id,
        site=site,
        schema_hash=schema_hash,
        artifact_type=artifact_type,
    )


def build_prewarm_request_key(
    *,
    datasource_id: str,
    site: Optional[str],
    schema_hash: Optional[str],
    requested_artifacts: Optional[Iterable[str]],
) -> str:
    """构造后台预热去重 key。"""

    normalized_schema_hash = str(schema_hash or "").strip() or "default"
    artifact_tokens = [
        str(item or "").strip()
        for item in (requested_artifacts or ["all"])
        if str(item or "").strip()
    ]
    artifact_key = ",".join(sorted(artifact_tokens)) or "all"
    return (
        f"{normalize_tableau_site(site)}:{datasource_id}:"
        f"{normalized_schema_hash}:{artifact_key}"
    )


def _build_versioned_index_name(
    *,
    prefix: str,
    datasource_id: str,
    site: Optional[str],
    schema_hash: Optional[str],
) -> str:
    """构造带 schema token 的索引名。"""

    normalized_site = _normalize_index_token(normalize_tableau_site(site))
    normalized_datasource = _normalize_index_token(datasource_id)
    normalized_schema = _normalize_schema_token(schema_hash)
    normalized_prefix = _normalize_index_token(prefix)
    return (
        f"{normalized_prefix}_{normalized_site}_{normalized_datasource}_"
        f"{normalized_schema}"
    )


def _build_versioned_index_prefix(
    *,
    prefix: str,
    datasource_id: str,
    site: Optional[str],
) -> str:
    """构造不带 schema token 的索引前缀。"""

    normalized_site = _normalize_index_token(normalize_tableau_site(site))
    normalized_datasource = _normalize_index_token(datasource_id)
    normalized_prefix = _normalize_index_token(prefix)
    return f"{normalized_prefix}_{normalized_site}_{normalized_datasource}_"


def _normalize_index_token(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(value or "").strip())
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized or "default"


def _normalize_schema_token(schema_hash: Optional[str]) -> str:
    """把 schema hash 压缩成稳定索引 token，避免索引名过长。"""

    normalized_schema_hash = str(schema_hash or "").strip() or "latest"
    return _normalize_index_token(normalized_schema_hash[:12])


def _build_versioned_artifact_cache_key(
    *,
    prefix: str,
    datasource_id: str,
    site: Optional[str],
    schema_hash: Optional[str],
    artifact_type: Optional[str] = None,
) -> str:
    parts = [
        str(prefix or "").strip() or "artifact",
        normalize_tableau_site(site),
        str(datasource_id or "").strip() or "unknown",
    ]
    if artifact_type is not None:
        parts.append(str(artifact_type or "").strip() or "field_index")
    parts.append(str(schema_hash or "").strip() or "latest")
    return ":".join(parts)


__all__ = [
    "build_data_model_cache_key",
    "build_datasource_identity_cache_key",
    "build_field_artifact_key",
    "build_field_index_name",
    "build_field_index_prefix",
    "build_field_values_index_name",
    "build_field_values_index_prefix",
    "build_metadata_snapshot_cache_key",
    "build_prewarm_request_key",
    "normalize_tableau_site",
]
