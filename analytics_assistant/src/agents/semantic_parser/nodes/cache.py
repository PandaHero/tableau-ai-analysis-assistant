# -*- coding: utf-8 -*-
"""缓存相关节点：查询缓存、特征缓存"""
import logging
from typing import Any, Optional

from langgraph.types import RunnableConfig

from ..state import SemanticParserState
from ..components import QueryCache, FeatureCache
from analytics_assistant.src.agents.base.context import get_context

logger = logging.getLogger(__name__)

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
    """
    question = state.get("question", "")
    datasource_luid = state.get("datasource_luid", "")

    if not question or not datasource_luid:
        logger.debug("query_cache_node: 缺少必要参数，跳过缓存检查")
        return {"cache_hit": False}

    # 从 WorkflowContext 获取 schema_hash
    ctx = get_context(config) if config else None
    if ctx is not None:
        current_schema_hash = ctx.schema_hash
    else:
        logger.warning("query_cache_node: 未提供 WorkflowContext，缓存可能无法正确验证")
        current_schema_hash = ""

    cache = QueryCache()

    # 精确匹配
    cached = cache.get(question, datasource_luid, current_schema_hash)

    if cached is None:
        # 尝试语义相似匹配
        cached = cache.get_similar(question, datasource_luid, current_schema_hash)

    if cached is not None:
        logger.info(f"query_cache_node: 缓存命中, hit_count={cached.hit_count}")
        return {
            "cache_hit": True,
            "semantic_output": cached.semantic_output,
            "semantic_query": {"query": cached.query},
        }

    logger.debug("query_cache_node: 缓存未命中")
    return {"cache_hit": False}

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
        return {}

    cache = FeatureCache()

    # 精确匹配
    cached = cache.get(question, datasource_luid)

    if cached is None:
        # 尝试语义相似匹配
        cached = cache.get_similar(question, datasource_luid)

    if cached is not None:
        logger.info(f"feature_cache_node: 缓存命中, hit_count={cached.hit_count}")
        return {
            "feature_extraction_output": cached.feature_output,
            "optimization_metrics": {
                "feature_cache_hit": True,
            },
        }

    logger.debug("feature_cache_node: 缓存未命中")
    return {
        "optimization_metrics": {
            "feature_cache_hit": False,
        },
    }
