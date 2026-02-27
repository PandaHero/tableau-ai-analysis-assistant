# -*- coding: utf-8 -*-
"""
节点公共辅助函数

提供节点函数间共享的数据转换和合并逻辑。
"""
from typing import Optional

from .schemas.intermediate import FieldCandidate

def parse_field_candidates(raw: Optional[list[dict]]) -> list[FieldCandidate]:
    """从 state 中解析字段候选列表。"""
    if not raw:
        return []
    return [FieldCandidate.model_validate(c) for c in raw]

def _is_time_field(c: FieldCandidate) -> bool:
    """判断字段是否为时间字段。

    同时检查 data_type 和 category，避免遗漏 string 类型的日期字段。
    """
    if c.data_type in ("date", "datetime", "timestamp"):
        return True
    if c.category and c.category.lower() == "time":
        return True
    return False

def classify_fields(candidates: list[FieldCandidate]) -> dict:
    """将字段候选按 role 分类。"""
    return {
        "measures": [c for c in candidates if c.role.lower() == "measure"],
        "dimensions": [c for c in candidates if c.role.lower() == "dimension"],
        "time_fields": [c for c in candidates if _is_time_field(c)],
    }

def merge_metrics(state: dict, **new_metrics) -> dict:
    """合并优化指标。"""
    existing = state.get("optimization_metrics", {})
    return {**existing, **new_metrics}
