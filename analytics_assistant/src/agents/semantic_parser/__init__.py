# -*- coding: utf-8 -*-
"""
Semantic Parser Agent

语义解析器：将用户自然语言问题转换为结构化数据查询。

采用 LLM 驱动的简化架构：
1. 信任 LLM 的推理能力
2. 通过 Prompt 和 Few-shot 提升准确性
3. 支持渐进式查询构建
4. 持续学习改进
"""

from analytics_assistant.src.agents.semantic_parser.schemas import (
    # Output - Enums
    CalcType,
    ClarificationSource,
    # Output - Models
    DerivedComputation,
    SelfCheck,
    What,
    Where,
    SemanticOutput,
    # Intermediate
    FieldCandidate,
    FewShotExample,
    # Cache
    CachedQuery,
    CachedFieldValues,
    # Filters
    FilterValidationType,
    FilterValidationResult,
    FilterValidationSummary,
    FilterConfirmation,
)

__all__ = [
    # Output - Enums
    "CalcType",
    "ClarificationSource",
    # Output - Models
    "DerivedComputation",
    "SelfCheck",
    "What",
    "Where",
    "SemanticOutput",
    # Intermediate
    "FieldCandidate",
    "FewShotExample",
    # Cache
    "CachedQuery",
    "CachedFieldValues",
    # Filters
    "FilterValidationType",
    "FilterValidationResult",
    "FilterValidationSummary",
    "FilterConfirmation",
]
