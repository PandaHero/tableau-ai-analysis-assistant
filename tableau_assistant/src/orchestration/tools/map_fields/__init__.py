"""
map_fields Tool 包

封装 FieldMapperNode，提供字段映射功能。

策略（保留现有 RAG+LLM 混合策略）：
1. 缓存检查 → 命中直接返回
2. RAG 检索 → confidence >= 0.9 直接返回
3. LLM Fallback → 从 top-k candidates 中选择
4. RAG 不可用 → LLM Only

错误处理：映射失败直接返回结构化错误，不做重试
"""

from tableau_assistant.src.orchestration.tools.map_fields.tool import (
    map_fields,
    map_fields_async,
)
from tableau_assistant.src.orchestration.tools.map_fields.models import (
    MapFieldsInput,
    MapFieldsOutput,
    FieldMappingError,
    FieldMappingErrorType,
)

__all__ = [
    # Tool
    "map_fields",
    "map_fields_async",
    # Models
    "MapFieldsInput",
    "MapFieldsOutput",
    "FieldMappingError",
    "FieldMappingErrorType",
]
