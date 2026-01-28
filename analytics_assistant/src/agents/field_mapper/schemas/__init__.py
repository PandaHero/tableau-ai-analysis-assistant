# -*- coding: utf-8 -*-
"""
FieldMapper 数据模型

包含：
- FieldMappingConfig: 配置类
- FieldCandidate: RAG 检索的候选字段
- SingleSelectionResult: LLM 单字段选择结果
- AlternativeMapping: 备选映射
- FieldMapping: 单字段映射结果
- MappedQuery: 映射后的查询
"""

from .config import FieldMappingConfig
from .mapping import (
    FieldCandidate,
    SingleSelectionResult,
    AlternativeMapping,
    FieldMapping,
    MappedQuery,
)

__all__ = [
    "FieldMappingConfig",
    "FieldCandidate",
    "SingleSelectionResult",
    "AlternativeMapping",
    "FieldMapping",
    "MappedQuery",
]
