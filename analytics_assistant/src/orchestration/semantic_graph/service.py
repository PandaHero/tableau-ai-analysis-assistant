# -*- coding: utf-8 -*-
"""Deterministic semantic-stage helpers."""

from __future__ import annotations

from typing import Any


def build_semantic_summary(semantic_raw: dict[str, Any]) -> dict[str, Any]:
    """Extract the frontend-facing summary fields from a semantic output payload."""
    if not isinstance(semantic_raw, dict):
        return {}

    restated = semantic_raw.get("restated_question", "")

    what = semantic_raw.get("what", {}) or {}
    measures = [
        measure.get("field_name", "")
        for measure in (what.get("measures") or [])
        if isinstance(measure, dict) and measure.get("field_name")
    ]

    where = semantic_raw.get("where", {}) or {}
    dimensions = [
        dimension.get("field_name", "")
        for dimension in (where.get("dimensions") or [])
        if isinstance(dimension, dict) and dimension.get("field_name")
    ]

    filters: list[str] = []
    for raw_filter in (where.get("filters") or []):
        if not isinstance(raw_filter, dict):
            continue
        field_name = raw_filter.get("field_name", "")
        if field_name:
            filters.append(field_name)

    return {
        "restated_question": restated,
        "measures": measures,
        "dimensions": dimensions,
        "filters": filters,
    }


__all__ = [
    "build_semantic_summary",
]
