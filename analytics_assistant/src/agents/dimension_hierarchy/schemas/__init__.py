# -*- coding: utf-8 -*-
"""
维度层级 Schema 定义

包含：
- DimensionCategory: 维度类别枚举
- DimensionAttributes: 单个维度的层级属性
- DimensionHierarchyResult: 推断结果
- LLMDimensionOutput: LLM 输出 schema（用于 stream_llm_structured）
"""

from .output import (
    DimensionCategory,
    DimensionAttributes,
    DimensionHierarchyResult,
    LLMDimensionItem,
    LLMDimensionOutput,
)

__all__ = [
    "DimensionCategory",
    "DimensionAttributes",
    "DimensionHierarchyResult",
    "LLMDimensionItem",
    "LLMDimensionOutput",
]
