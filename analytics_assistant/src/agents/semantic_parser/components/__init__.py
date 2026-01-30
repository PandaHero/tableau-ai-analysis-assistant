# -*- coding: utf-8 -*-
"""
Semantic Parser Components

语义解析器组件模块，包含：
- IntentRouter: 意图路由器（L0 规则 + L1 可选 LLM）
- QueryCache: 查询缓存（精确匹配 + 语义相似）
- FieldRetriever: 字段检索（Top-K）
- FewShotManager: Few-shot 示例管理
- SemanticUnderstanding: LLM 语义理解
- FieldValueCache: 字段值缓存
- FilterValueValidator: 筛选值验证器
- QueryAdapter: 查询适配器
- ErrorCorrector: 错误修正
- FeedbackLearner: 反馈学习
- DynamicSchemaBuilder: 动态 Schema 构建器
"""

from .intent_router import IntentType, IntentRouterOutput, IntentRouter
from .semantic_cache import SemanticCache
from .query_cache import QueryCache, compute_schema_hash, compute_question_hash
from .feature_cache import FeatureCache, compute_feature_hash
from .field_retriever import FieldRetriever
# FieldCandidate 和 FieldRAGResult 从 schemas 导入
from ..schemas.prefilter import FieldRAGResult
from analytics_assistant.src.core.schemas.field_candidate import FieldCandidate
from .few_shot_manager import FewShotManager
from .semantic_understanding import (
    SemanticUnderstanding,
    get_low_confidence_threshold,
    get_default_timezone,
    get_fiscal_year_start_month,
    get_max_schema_tokens,
    get_max_few_shot_examples,
)
from .field_value_cache import FieldValueCache
from .filter_validator import FilterValueValidator, get_time_data_types
from .error_corrector import ErrorCorrector
from .feedback_learner import FeedbackLearner
from .history_manager import (
    HistoryManager,
    get_history_manager,
    truncate_history,
    check_history_tokens,
    estimate_tokens,
    estimate_message_tokens,
    estimate_history_tokens,
    get_max_history_tokens,
    get_use_summarization,
)
from .dynamic_schema_builder import (
    SchemaModule,
    DynamicSchemaResult,
    DynamicSchemaBuilder,
    get_max_schema_fields,
    COMPLEXITY_SCHEMA_FIELDS,
    COMPLEXITY_CALC_TYPES,
)
from .output_validator import (
    OutputValidator,
    get_fuzzy_match_threshold,
    get_auto_correct_case,
)
from .rule_prefilter import RulePrefilter
from .feature_extractor import FeatureExtractor, get_feature_extractor_config

from ..schemas.cache import CachedQuery, CachedFieldValues
from ..schemas.error_correction import ErrorCorrectionHistory, CorrectionResult
from ..schemas.feedback import FeedbackType, FeedbackRecord, SynonymMapping

__all__ = [
    # SemanticCache (基类)
    "SemanticCache",
    # IntentRouter
    "IntentType",
    "IntentRouterOutput",
    "IntentRouter",
    # QueryCache
    "CachedQuery",
    "QueryCache",
    "compute_schema_hash",
    "compute_question_hash",
    # FeatureCache
    "FeatureCache",
    "compute_feature_hash",
    # FieldRetriever
    "FieldCandidate",
    "FieldRetriever",
    "FieldRAGResult",
    # FewShotManager
    "FewShotManager",
    # SemanticUnderstanding
    "SemanticUnderstanding",
    "get_low_confidence_threshold",
    "get_default_timezone",
    "get_fiscal_year_start_month",
    "get_max_schema_tokens",
    "get_max_few_shot_examples",
    # FieldValueCache
    "FieldValueCache",
    "CachedFieldValues",
    # FilterValueValidator
    "FilterValueValidator",
    "get_time_data_types",
    # ErrorCorrector
    "ErrorCorrectionHistory",
    "CorrectionResult",
    "ErrorCorrector",
    # FeedbackLearner
    "FeedbackType",
    "FeedbackRecord",
    "SynonymMapping",
    "FeedbackLearner",
    # HistoryManager
    "HistoryManager",
    "get_history_manager",
    "truncate_history",
    "check_history_tokens",
    "estimate_tokens",
    "estimate_message_tokens",
    "estimate_history_tokens",
    "get_max_history_tokens",
    "get_use_summarization",
    # DynamicSchemaBuilder
    "SchemaModule",
    "DynamicSchemaResult",
    "DynamicSchemaBuilder",
    "get_max_schema_fields",
    "COMPLEXITY_SCHEMA_FIELDS",
    "COMPLEXITY_CALC_TYPES",
    # OutputValidator
    "OutputValidator",
    "get_fuzzy_match_threshold",
    "get_auto_correct_case",
    # RulePrefilter
    "RulePrefilter",
    # FeatureExtractor
    "FeatureExtractor",
    "get_feature_extractor_config",
]
