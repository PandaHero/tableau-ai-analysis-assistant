# -*- coding: utf-8 -*-
"""
Semantic Parser Schemas

语义解析器数据模型，按功能分类：
1. output.py - 核心输出模型 (SemanticOutput, SelfCheck, What, Where)
2. intermediate.py - 中间数据模型 (FieldCandidate, FewShotExample)
3. cache.py - 缓存相关模型 (CachedQuery, CachedFieldValues)
4. filters.py - 筛选器验证模型 (FilterValidationResult, FilterConfirmation)
5. enums.py - 枚举类型 (PromptComplexity)
6. config.py - 运行时上下文模型 (SemanticConfig) - 注意：不是配置文件！
7. error_correction.py - 错误修正模型 (ErrorCorrectionHistory, CorrectionResult)
8. intent.py - 意图识别模型 (IntentType, IntentRouterOutput)

注意：配置参数统一放在 app.yaml 中，config.py 中的 SemanticConfig 是运行时上下文，不是配置。
"""

from .output import (
    CalcType,
    ClarificationSource,
    DerivedComputation,
    SelfCheck,
    What,
    Where,
    SemanticOutput,
)

from .intermediate import TimeHint, FieldCandidate, FewShotExample
from .cache import CachedQuery, CachedFieldValues
from .filters import (
    FilterValidationType,
    FilterValidationResult,
    FilterValidationSummary,
    FilterConfirmation,
)
from .error_correction import ErrorCorrectionHistory, CorrectionResult
from .enums import PromptComplexity
from .config import SemanticConfig
from .intent import IntentType, IntentRouterOutput

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
    "TimeHint",
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
    # Error Correction
    "ErrorCorrectionHistory",
    "CorrectionResult",
    # Enums
    "PromptComplexity",
    # Config (运行时上下文，不是配置文件)
    "SemanticConfig",
    # Intent
    "IntentType",
    "IntentRouterOutput",
]
