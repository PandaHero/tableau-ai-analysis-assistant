from __future__ import annotations

from typing import Any

from analytics_assistant.src.infra.config import get_config

WHY_SCREENING_WAVE_FLAG = "why_screening_wave"

_DEFAULT_FEATURE_FLAGS: dict[str, bool] = {
    WHY_SCREENING_WAVE_FLAG: True,
}


def _normalize_flag_overrides(raw_flags: Any) -> dict[str, bool]:
    """只接受布尔型开关，避免请求层把任意 payload 混进运行时状态。"""
    if not isinstance(raw_flags, dict):
        return {}

    normalized: dict[str, bool] = {}
    for raw_name, raw_value in raw_flags.items():
        name = str(raw_name or "").strip()
        if not name:
            continue
        if isinstance(raw_value, bool):
            normalized[name] = raw_value
    return normalized


def resolve_root_graph_feature_flags(
    *,
    tableau_username: str,
    session_id: str | None,
    request_overrides: Any = None,
) -> dict[str, bool]:
    """按全局默认 -> 租户覆盖 -> 会话覆盖 -> 请求覆盖解析 root_graph 功能开关。"""
    resolved = dict(_DEFAULT_FEATURE_FLAGS)

    try:
        config = get_config()
        raw_feature_flags = config.get("root_graph", {}).get("feature_flags", {})
    except Exception:
        raw_feature_flags = {}

    if isinstance(raw_feature_flags, dict):
        resolved.update(
            _normalize_flag_overrides(raw_feature_flags.get("defaults"))
        )

        tenant_overrides = raw_feature_flags.get("tenant_overrides") or {}
        if isinstance(tenant_overrides, dict):
            resolved.update(
                _normalize_flag_overrides(
                    tenant_overrides.get(str(tableau_username or "").strip())
                )
            )

        session_overrides = raw_feature_flags.get("session_overrides") or {}
        normalized_session_id = str(session_id or "").strip()
        if normalized_session_id and isinstance(session_overrides, dict):
            resolved.update(
                _normalize_flag_overrides(
                    session_overrides.get(normalized_session_id)
                )
            )

    resolved.update(_normalize_flag_overrides(request_overrides))
    return resolved


__all__ = [
    "WHY_SCREENING_WAVE_FLAG",
    "resolve_root_graph_feature_flags",
]
