# -*- coding: utf-8 -*-
"""缓存相关节点：查询缓存、特征缓存"""
import logging
import re
from typing import Any, Optional

from langgraph.types import RunnableConfig

from analytics_assistant.src.agents.base.context import get_context
from analytics_assistant.src.infra.seeds import COMPLEXITY_KEYWORDS

from ..state import SemanticParserState
from ..components import get_query_cache, get_feature_cache
from ..node_utils import merge_metrics
from ..schemas.planner import parse_step_intent
from ..schemas.prefilter import PrefilterResult, ComplexityType

logger = logging.getLogger(__name__)

_SEMANTIC_LOOKUP_MIN_QUESTION_LEN = 6
_SEMANTIC_LOOKUP_CONVERSATIONAL_MARKERS = (
    "帮我",
    "看一下",
    "请问",
    "能不能",
    "可以帮",
)
_SEMANTIC_LOOKUP_COMPLEXITY_KEYWORDS = tuple(
    keyword.lower()
    for keywords in COMPLEXITY_KEYWORDS.values()
    for keyword in keywords
    if len(keyword) >= 2
)


def _has_semantic_lookup_signal(question: str) -> bool:
    """判断问题是否值得进行语义缓存查找。"""
    question_lower = question.strip().lower()
    if not question_lower:
        return False

    if re.search(r"(?:前|后)\s*\d+|(?:top|bottom)\s*\d+", question_lower):
        return True

    if any(keyword in question_lower for keyword in _SEMANTIC_LOOKUP_COMPLEXITY_KEYWORDS):
        return True

    return (
        len(question_lower) >= _SEMANTIC_LOOKUP_MIN_QUESTION_LEN
        and any(marker in question_lower for marker in _SEMANTIC_LOOKUP_CONVERSATIONAL_MARKERS)
    )


def _should_allow_semantic_lookup(
    question: str,
    prefilter_result: Optional[PrefilterResult] = None,
) -> bool:
    """仅在复杂或明显自然语言重述场景启用语义查找。"""
    if prefilter_result is not None:
        if prefilter_result.detected_complexity != [ComplexityType.SIMPLE]:
            return True
        if prefilter_result.time_hints or prefilter_result.matched_computations:
            return True

    return _has_semantic_lookup_signal(question)


def _is_feature_cache_compatible(
    cached_feature_output: dict[str, Any],
    prefilter_result: Optional[PrefilterResult],
) -> bool:
    """校验缓存特征是否仍与当前规则信号一致。"""
    if prefilter_result is None:
        return True

    cached_computations = {
        str(name).strip()
        for name in cached_feature_output.get("confirmed_computations", [])
        if str(name).strip()
    }
    current_computations = {
        computation.seed_name.strip()
        for computation in prefilter_result.matched_computations
        if computation.seed_name and computation.seed_name.strip()
    }

    if cached_computations and prefilter_result.detected_complexity == [ComplexityType.SIMPLE]:
        return False

    if cached_computations != current_computations and (
        cached_computations or current_computations
    ):
        return False

    return True

async def query_cache_node(
    state: SemanticParserState,
    config: Optional[RunnableConfig] = None,
) -> dict[str, Any]:
    """查询缓存节点

    检查缓存是否命中。

    输入：
    - state["question"]: 用户问题
    - state["datasource_luid"]: 数据源 ID
    - config: RunnableConfig，包含 WorkflowContext

    输出：
    - cache_hit: 是否命中缓存
    - semantic_output: 缓存的语义输出（如果命中）
    - semantic_query: 缓存的查询（如果命中）
    - analysis_plan / global_understanding: 缓存的规划上下文（如果命中）
    """
    question = state.get("question", "")
    datasource_luid = state.get("datasource_luid", "")

    if not question or not datasource_luid:
        logger.debug("query_cache_node: 缺少必要参数，跳过缓存检查")
        return {
            "cache_hit": False,
            "optimization_metrics": merge_metrics(state, query_cache_hit=False),
        }

    # 从 WorkflowContext 获取 schema_hash
    ctx = get_context(config) if config else None
    if ctx is not None:
        current_schema_hash = ctx.schema_hash
    else:
        logger.warning("query_cache_node: 未提供 WorkflowContext，缓存可能无法正确验证")
        current_schema_hash = ""

    cache = get_query_cache()
    allow_semantic_lookup = _should_allow_semantic_lookup(question)

    # 精确匹配
    cached = cache.get(question, datasource_luid, current_schema_hash)

    if cached is None and allow_semantic_lookup:
        # 尝试语义相似匹配
        cached = cache.get_similar(question, datasource_luid, current_schema_hash)

    if cached is not None:
        logger.info(f"query_cache_node: 缓存命中, hit_count={cached.hit_count}")
        cached_query = cached.query
        if isinstance(cached_query, dict):
            semantic_query = cached_query
        elif isinstance(cached_query, str):
            semantic_query = {"query": cached_query}
        else:
            semantic_query = {"query": str(cached_query)}
        return {
            "cache_hit": True,
            "semantic_output": cached.semantic_output,
            "semantic_query": semantic_query,
            "analysis_plan": cached.analysis_plan,
            "global_understanding": cached.global_understanding,
            "optimization_metrics": merge_metrics(
                state,
                query_cache_hit=True,
                query_cache_semantic_lookup=allow_semantic_lookup,
            ),
        }

    logger.debug("query_cache_node: 缓存未命中")
    return {
        "cache_hit": False,
        "optimization_metrics": merge_metrics(
            state,
            query_cache_hit=False,
            query_cache_semantic_lookup=allow_semantic_lookup,
        ),
    }

async def feature_cache_node(
    state: SemanticParserState,
    config: Optional[RunnableConfig] = None,
) -> dict[str, Any]:
    """特征缓存节点

    检查特征缓存是否命中。

    输入：
    - state["question"]: 用户问题
    - state["datasource_luid"]: 数据源 ID

    输出：
    - feature_extraction_output: 缓存的特征输出（如果命中）
    - is_degraded: 是否为降级模式
    """
    question = state.get("question", "")
    datasource_luid = state.get("datasource_luid", "")

    if not question or not datasource_luid:
        logger.debug("feature_cache_node: 缺少必要参数，跳过缓存检查")
        return {
            "optimization_metrics": merge_metrics(state, feature_cache_hit=False),
        }

    current_step_intent = parse_step_intent(state.get("current_step_intent"))
    if current_step_intent is not None:
        logger.debug("feature_cache_node: 存在 step intent，上下文化步骤跳过特征缓存")
        return {
            "optimization_metrics": merge_metrics(
                state,
                feature_cache_hit=False,
                feature_cache_context_bypass=True,
            ),
        }

    cache = get_feature_cache()

    # 精确匹配
    cached = cache.get(question, datasource_luid)

    prefilter_result_raw = state.get("prefilter_result")
    prefilter_result = (
        PrefilterResult.model_validate(prefilter_result_raw)
        if prefilter_result_raw else None
    )
    detected_complexity = (
        prefilter_result.detected_complexity if prefilter_result else [ComplexityType.SIMPLE]
    )
    allow_semantic_lookup = _should_allow_semantic_lookup(question, prefilter_result)

    if cached is None and allow_semantic_lookup:
        # 尝试语义相似匹配
        cached = cache.get_similar(question, datasource_luid)

    if cached is not None and not _is_feature_cache_compatible(
        cached.feature_output,
        prefilter_result,
    ):
        logger.info("feature_cache_node: 缓存命中但与当前规则信号不兼容，忽略缓存")
        cached = None

    if cached is not None:
        logger.info(f"feature_cache_node: 缓存命中, hit_count={cached.hit_count}")
        return {
            "feature_extraction_output": cached.feature_output,
            "is_degraded": bool(cached.feature_output.get("is_degraded", False)),
            "optimization_metrics": merge_metrics(
                state,
                feature_cache_hit=True,
                feature_cache_semantic_lookup=allow_semantic_lookup,
            ),
        }

    logger.debug("feature_cache_node: 缓存未命中")
    return {
        "optimization_metrics": merge_metrics(
            state,
            feature_cache_hit=False,
            feature_cache_semantic_lookup=allow_semantic_lookup,
        ),
    }
