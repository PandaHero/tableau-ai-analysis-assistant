# -*- coding: utf-8 -*-
"""
Semantic Parser Schemas

语义解析器数据模型，按功能分类：
1. output.py - 核心输出模型 (SemanticOutput, SelfCheck, What, Where)
2. intermediate.py - 中间数据模型 (TimeHint, FieldCandidate, FewShotExample)
3. cache.py - 缓存相关模型 (CachedQuery, CachedFeature, CachedFieldValues)
4. filters.py - 筛选器验证模型 (FilterValidationResult, FilterConfirmation)
5. config.py - 运行时上下文模型 (SemanticConfig) - 注意：不是配置文件！
6. error_correction.py - 错误修正模型 (ErrorCorrectionHistory, CorrectionResult)
7. intent.py - 意图识别模型 (IntentType, IntentRouterOutput)
8. feedback.py - 反馈模型 (FeedbackType, FeedbackRecord, SynonymMapping)
9. prefilter.py - 规则预处理模型 (PrefilterResult, FeatureExtractionOutput, FieldRAGResult, ValidationResult)
10. planner.py - 分析计划模型 (AnalysisPlan, AnalysisPlanStep, PlanMode)

注意：
- 配置参数统一放在 app.yaml 中，config.py 中的 SemanticConfig 是运行时上下文，不是配置。
- FieldCandidate 从 core/schemas/field_candidate.py 导入，跨模块共享。
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
from .cache import CachedQuery, CachedFeature, CachedFieldValues
from .filters import (
    FilterValidationType,
    FilterValidationResult,
    FilterValidationSummary,
    FilterConfirmation,
)
from .error_correction import ErrorCorrectionHistory, CorrectionResult
from .config import SemanticConfig
from .intent import IntentType, IntentRouterOutput
from .feedback import FeedbackType, FeedbackRecord, SynonymMapping
from .prefilter import (
    ComplexityType,
    ValidationErrorType,
    RuleTimeHint,
    MatchedComputation,
    PrefilterResult,
    FeatureExtractionOutput,
    FieldRAGResult,
    OutputValidationError,
    ValidationResult,
)
from .dynamic_schema import DynamicSchemaResult
from .planner import (
    AnalysisMode,
    QueryFeasibilityBlocker,
    PlanMode,
    PlanStepType,
    StepIntent,
    AnalysisPlanStep,
    AxisEvidenceScore,
    StepArtifact,
    EvidenceContext,
    GlobalUnderstandingOutput,
    AnalysisPlan,
    parse_analysis_plan,
    parse_step_intent,
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
    "TimeHint",
    "FieldCandidate",
    "FewShotExample",
    # Cache
    "CachedQuery",
    "CachedFeature",
    "CachedFieldValues",
    # Filters
    "FilterValidationType",
    "FilterValidationResult",
    "FilterValidationSummary",
    "FilterConfirmation",
    # Error Correction
    "ErrorCorrectionHistory",
    "CorrectionResult",
    # Config (运行时上下文，不是配置文件)
    "SemanticConfig",
    # Intent
    "IntentType",
    "IntentRouterOutput",
    # Feedback
    "FeedbackType",
    "FeedbackRecord",
    "SynonymMapping",
    # Prefilter (规则预处理)
    "ComplexityType",
    "ValidationErrorType",
    "RuleTimeHint",
    "MatchedComputation",
    "PrefilterResult",
    "FeatureExtractionOutput",
    "FieldRAGResult",
    "OutputValidationError",
    "ValidationResult",
    # DynamicSchema
    "DynamicSchemaResult",
    # Planner
    "AnalysisMode",
    "QueryFeasibilityBlocker",
    "PlanMode",
    "PlanStepType",
    "StepIntent",
    "AnalysisPlanStep",
    "AxisEvidenceScore",
    "StepArtifact",
    "EvidenceContext",
    "GlobalUnderstandingOutput",
    "AnalysisPlan",
    "parse_analysis_plan",
    "parse_step_intent",
]
