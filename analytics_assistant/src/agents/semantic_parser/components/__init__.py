# -*- coding: utf-8 -*-
"""
Semantic Parser Components

语义解析器组件模块，包含：
- IntentRouter: 意图路由器（L0 规则 + L1 可选 LLM）
- QueryCache: 查询缓存（精确匹配 + 语义相似）
- FieldRetriever: 字段检索（Top-K）
- FewShotManager: Few-shot 示例管理
- SemanticUnderstanding: LLM 语义理解
- FilterValueValidator: 筛选值验证
- QueryAdapter: 查询适配器
- ErrorCorrector: 错误修正
- FeedbackLearner: 反馈学习
"""

from analytics_assistant.src.agents.semantic_parser.components.intent_router import (
    IntentType,
    IntentRouterOutput,
    IntentRouter,
)
from analytics_assistant.src.agents.semantic_parser.components.query_cache import (
    CachedQuery,
    QueryCache,
    compute_schema_hash,
    compute_question_hash,
)
from analytics_assistant.src.agents.semantic_parser.components.field_retriever import (
    FieldCandidate,
    FieldRetriever,
    get_full_schema_threshold,
    get_min_rule_match_dimensions,
    get_default_top_k,
    get_category_keywords,
    extract_categories_by_rules,
    match_field_name_or_caption,
)

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
]
