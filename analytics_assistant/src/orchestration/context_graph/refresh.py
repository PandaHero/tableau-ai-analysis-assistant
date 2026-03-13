# -*- coding: utf-8 -*-
"""context_graph 的 artifact refresh 请求契约。"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class ArtifactRefreshRequest(BaseModel):
    """描述一次 datasource artifact 刷新的目标与触发原因。"""

    datasource_luid: str = Field(description="数据源 LUID")
    trigger: Literal["schema_change", "missing_artifacts", "manual_refresh"] = Field(
        description="刷新触发原因",
    )
    requested_artifacts: list[str] = Field(
        default_factory=list,
        description="需要刷新的 artifact 类型列表",
    )
    prefer_incremental: bool = Field(
        default=True,
        description="是否优先使用增量重建策略",
    )
    previous_schema_hash: Optional[str] = Field(
        default=None,
        description="上一轮 schema hash",
    )
    schema_hash: Optional[str] = Field(
        default=None,
        description="当前 schema hash",
    )
    refresh_reason: Optional[str] = Field(
        default=None,
        description="用于日志和可观测性的自然语言原因",
    )


def build_artifact_refresh_request(
    *,
    datasource_luid: str,
    schema_changed: bool,
    previous_schema_hash: Optional[str],
    schema_hash: Optional[str],
    field_semantic_available: bool,
    field_samples_available: bool,
) -> Optional[ArtifactRefreshRequest]:
    """根据当前上下文状态决定是否需要发起 refresh 请求。"""
    requested_artifacts: list[str] = []
    if schema_changed or not field_semantic_available:
        requested_artifacts.append("field_semantic_index")
    if schema_changed or not field_samples_available:
        requested_artifacts.append("field_values_index")

    if not requested_artifacts:
        return None

    if schema_changed:
        trigger: Literal["schema_change", "missing_artifacts", "manual_refresh"] = (
            "schema_change"
        )
        refresh_reason = "schema 变化后需要失效旧产物，并优先做增量重建。"
    else:
        trigger = "missing_artifacts"
        refresh_reason = "字段语义或字段值产物缺失，已安排后台补齐。"

    return ArtifactRefreshRequest(
        datasource_luid=datasource_luid,
        trigger=trigger,
        requested_artifacts=requested_artifacts,
        prefer_incremental=True,
        previous_schema_hash=str(previous_schema_hash or "").strip() or None,
        schema_hash=str(schema_hash or "").strip() or None,
        refresh_reason=refresh_reason,
    )


__all__ = [
    "ArtifactRefreshRequest",
    "build_artifact_refresh_request",
]
