# -*- coding: utf-8 -*-
"""
FieldMapper 数据模型

包含：
- SingleSelectionResult: LLM 单字段选择结果
- AlternativeMapping: 备选映射
- FieldMapping: 单字段映射结果
- MappedQuery: 映射后的查询
"""

from .mapping import (
    SingleSelectionResult,
    AlternativeMapping,
    FieldMapping,
    MappedQuery,
)

__all__ = [
    "SingleSelectionResult",
    "AlternativeMapping",
    "FieldMapping",
    "MappedQuery",
]
