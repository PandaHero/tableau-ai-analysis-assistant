# -*- coding: utf-8 -*-
"""
维度层级推断模块

提供维度字段的语义推断功能：
- 类别分类（时间、地理、产品、客户等）
- 层级判断（1-5 级，从粗到细）
- 粒度描述（coarsest/coarse/medium/fine/finest）

推断策略：缓存 → 种子匹配 → RAG → LLM
"""
from analytics_assistant.src.agents.dimension_hierarchy.schema import (
    DimensionCategory,
    DimensionAttributes,
    DimensionHierarchyResult,
)
from analytics_assistant.src.agents.dimension_hierarchy.inference import (
    DimensionHierarchyInference,
    IncrementalFieldsResult,
    PatternSource,
    compute_fields_hash,
    compute_incremental_fields,
    build_cache_key,
    infer_dimension_hierarchy,
)
from analytics_assistant.src.agents.dimension_hierarchy.prompt import (
    SYSTEM_PROMPT,
    build_user_prompt,
    build_dimension_inference_prompt,
    get_system_prompt,
)

__all__ = [
    # Schema
    "DimensionCategory",
    "DimensionAttributes",
    "DimensionHierarchyResult",
    # Inference
    "DimensionHierarchyInference",
    "IncrementalFieldsResult",
    "PatternSource",
    "compute_fields_hash",
    "compute_incremental_fields",
    "build_cache_key",
    "infer_dimension_hierarchy",
    # Prompt
    "SYSTEM_PROMPT",
    "build_user_prompt",
    "build_dimension_inference_prompt",
    "get_system_prompt",
]
