# -*- coding: utf-8 -*-
"""
维度层级 Schema 定义

包含：
- DimensionAttributes: 单个维度的层级属性
- DimensionHierarchyResult: 推断结果
- LLMDimensionOutput: LLM 输出 schema（用于 stream_llm_structured）

注意：DimensionCategory 枚举已移至 core/schemas/enums.py
"""

from .output import (
    DimensionAttributes,
    DimensionHierarchyResult,
    LLMDimensionItem,
    LLMDimensionOutput,
)

__all__ = [
    "DimensionAttributes",
    "DimensionHierarchyResult",
    "LLMDimensionItem",
    "LLMDimensionOutput",
]
