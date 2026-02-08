# -*- coding: utf-8 -*-
"""
字段语义 Schema 定义

包含：
- FieldSemanticAttributes: 字段语义属性
- FieldSemanticResult: 推断结果
- LLMFieldSemanticOutput: LLM 输出 schema
"""
from .output import (
    FieldSemanticAttributes,
    FieldSemanticResult,
    LLMFieldSemanticItem,
    LLMFieldSemanticOutput,
)

__all__ = [
    "FieldSemanticAttributes",
    "FieldSemanticResult",
    "LLMFieldSemanticItem",
    "LLMFieldSemanticOutput",
]
