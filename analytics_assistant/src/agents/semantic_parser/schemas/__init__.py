# -*- coding: utf-8 -*-
"""
Semantic Parser Schemas

语义解析器数据模型，按功能分类：
1. output.py - 核心输出模型 (SemanticOutput, SelfCheck, What, Where)
2. intermediate.py - 中间数据模型 (FieldCandidate, FewShotExample)
3. cache.py - 缓存相关模型 (CachedQuery, CachedFieldValues)
4. filters.py - 筛选器验证模型 (FilterValidationResult, FilterConfirmation)
"""

from analytics_assistant.src.agents.semantic_parser.schemas.output import (
    CalcType,
    ClarificationSource,
    DerivedComputation,
    SelfCheck,
    What,
    Where,
    SemanticOutput,
)

from analytics_assistant.src.agents.semantic_parser.schemas.intermediate import (
    FieldCandidate,
    FewShotExample,
)

from analytics_assistant.src.agents.semantic_parser.schemas.cache import (
    CachedQuery,
    CachedFieldValues,
)

from analytics_assistant.src.agents.semantic_parser.schemas.filters import (
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
