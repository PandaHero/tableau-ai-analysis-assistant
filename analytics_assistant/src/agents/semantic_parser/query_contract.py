# -*- coding: utf-8 -*-
"""语义查询契约辅助函数。"""

from __future__ import annotations

from typing import Any

from .schemas.output import SemanticOutput


def build_compiler_input_contract(
    semantic_output: SemanticOutput,
) -> dict[str, Any]:
    """构造显式的编译器输入契约。"""
    return {
        "mode": "compiler_input",
        "source": "semantic_output",
        "query_id": semantic_output.query_id,
        "restated_question": semantic_output.restated_question,
    }


def build_compiler_input_contract_from_raw(
    semantic_output_raw: Any,
) -> dict[str, Any]:
    """基于原始语义输出构造稳定的编译器输入契约。"""
    if isinstance(semantic_output_raw, dict):
        query_id = str(semantic_output_raw.get("query_id") or "").strip() or None
        restated_question = str(
            semantic_output_raw.get("restated_question") or ""
        ).strip()
        return {
            "mode": "compiler_input",
            "source": "semantic_output",
            "query_id": query_id,
            "restated_question": restated_question,
        }

    semantic_output = SemanticOutput.model_validate(semantic_output_raw)
    return build_compiler_input_contract(semantic_output)


def inspect_query_contract(semantic_query: Any) -> dict[str, Any]:
    """检查当前 query contract 是否满足编译器执行前提。"""
    if not isinstance(semantic_query, dict):
        return {
            "query_contract_mode": "missing",
            "query_contract_source": "missing",
            "compiler_ready": False,
        }

    mode = str(semantic_query.get("mode") or "").strip() or "unknown"
    source = str(semantic_query.get("source") or "").strip() or "unknown"
    compiler_ready = mode == "compiler_input" and source == "semantic_output"
    return {
        "query_contract_mode": mode,
        "query_contract_source": source,
        "compiler_ready": compiler_ready,
    }


def normalize_query_contract(
    semantic_output_raw: Any,
    semantic_query: Any,
) -> dict[str, Any]:
    """把缓存或历史状态里的 query contract 归一成 compiler_input 契约。"""
    if semantic_output_raw:
        return build_compiler_input_contract_from_raw(semantic_output_raw)

    if isinstance(semantic_query, dict):
        return {
            "mode": str(semantic_query.get("mode") or "").strip() or "compiler_input",
            "source": str(semantic_query.get("source") or "").strip() or "semantic_output",
            "query_id": str(semantic_query.get("query_id") or "").strip() or None,
            "restated_question": str(
                semantic_query.get("restated_question") or ""
            ).strip(),
        }

    return {
        "mode": "compiler_input",
        "source": "semantic_output",
        "query_id": None,
        "restated_question": "",
    }


__all__ = [
    "build_compiler_input_contract",
    "build_compiler_input_contract_from_raw",
    "inspect_query_contract",
    "normalize_query_contract",
]
