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
"""

from .intent_router import IntentType, IntentRouterOutput, IntentRouter
from .query_cache import QueryCache, compute_schema_hash, compute_question_hash
from .field_retriever import (
    FieldCandidate,
    FieldRetriever,
    get_full_schema_threshold,
    get_min_rule_match_dimensions,
    get_default_top_k,
    get_category_keywords,
    extract_categories_by_rules,
    match_field_name_or_caption,
    get_full_schema_confidence,
    get_rule_match_confidence,
    get_hierarchy_expand_confidence,
    get_embedding_confidence_base,
)
from .few_shot_manager import FewShotManager
from .semantic_understanding import (
    SemanticUnderstanding,
    get_low_confidence_threshold,
    get_default_timezone,
    get_fiscal_year_start_month,
    get_max_schema_tokens,
    get_max_few_shot_examples,
)
from .field_value_cache import FieldValueCache, CachedFieldValues
from .filter_validator import FilterValueValidator, get_time_data_types
from .error_corrector import ErrorCorrector

from ..schemas.cache import CachedQuery
from ..schemas.error_correction import ErrorCorrectionHistory, CorrectionResult

__all__ = [
    # IntentRouter
    "IntentType",
    "IntentRouterOutput",
    "IntentRouter",
    # QueryCache
    "CachedQuery",
    "QueryCache",
    "compute_schema_hash",
    "compute_question_hash",
    # FieldRetriever
    "FieldCandidate",
    "FieldRetriever",
    "get_full_schema_threshold",
    "get_min_rule_match_dimensions",
    "get_default_top_k",
    "get_category_keywords",
    "extract_categories_by_rules",
    "match_field_name_or_caption",
    "get_full_schema_confidence",
    "get_rule_match_confidence",
    "get_hierarchy_expand_confidence",
    "get_embedding_confidence_base",
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
]
