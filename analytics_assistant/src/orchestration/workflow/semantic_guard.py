# -*- coding: utf-8 -*-
"""语义守卫相关的确定性执行闸门。"""

from __future__ import annotations

from typing import Any, Optional


def resolve_compiler_semantic_input(
    parse_result: dict[str, Any],
) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    """从 parse_result 中提取允许进入编译器的语义输入。"""
    semantic_raw = parse_result.get("semantic_output") or {}
    if not isinstance(semantic_raw, dict) or not semantic_raw:
        return None, "missing semantic_output compiler input"

    semantic_guard = dict(parse_result.get("semantic_guard") or {})
    if semantic_guard and not bool(semantic_guard.get("allowed_to_execute", False)):
        return None, (
            "semantic_guard rejected compiler input: "
            f"verified={bool(semantic_guard.get('verified', False))}, "
            f"compiler_ready={bool(semantic_guard.get('compiler_ready', False))}, "
            f"query_contract_mode={semantic_guard.get('query_contract_mode') or 'unknown'}"
        )

    return semantic_raw, None


__all__ = ["resolve_compiler_semantic_input"]
