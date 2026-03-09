# -*- coding: utf-8 -*-
"""执行相关节点：查询适配、错误修正、反馈学习"""
import logging
from typing import Any, Optional

from langgraph.types import RunnableConfig

from analytics_assistant.src.agents.base.context import get_context

from ..state import SemanticParserState
from ..components import (
    ErrorCorrector,
    FeedbackLearner,
    get_query_cache,
)
from ..schemas.output import SemanticOutput
from ..schemas.error_correction import ErrorCorrectionHistory
from ..schemas.prefilter import PrefilterResult, ComplexityType

logger = logging.getLogger(__name__)

async def query_adapter_node(
    state: SemanticParserState,
    config: Optional[RunnableConfig] = None,
) -> dict[str, Any]:
    """查询适配节点

    将 SemanticOutput 转换为目标查询语言（VizQL）。

    输入：
    - state["semantic_output"]: 语义输出
    - config: RunnableConfig，包含 WorkflowContext

    输出：
    - semantic_query: 生成的 VizQL 查询
    - pipeline_error: 执行错误（如果有）
    """
    semantic_output_raw = state.get("semantic_output")

    if not semantic_output_raw:
        logger.warning("query_adapter_node: 缺少 semantic_output")
        return {
            "pipeline_error": {
                "error_type": "missing_input",
                "message": "缺少 semantic_output",
                "is_retryable": False,
            }
        }

    semantic_output = SemanticOutput.model_validate(semantic_output_raw)
    ctx = get_context(config) if config else None

    if ctx is None or ctx.platform_adapter is None:
        logger.warning(
            "query_adapter_node: 未提供 platform_adapter，直接返回 semantic_output。"
        )
        return {
            "semantic_query": semantic_output_raw,
        }

    try:
        platform_adapter = ctx.platform_adapter
        datasource_id = ctx.datasource_luid

        validation = platform_adapter.validate_query(semantic_output)
        if not validation.is_valid:
            error_msgs = [e.message for e in (validation.errors or [])]
            return {
                "pipeline_error": {
                    "error_type": "validation_error",
                    "message": f"查询验证失败: {'; '.join(error_msgs)}",
                    "is_retryable": True,
                }
            }

        vizql_query = platform_adapter.build_query(
            semantic_output,
            datasource_id=datasource_id,
            data_model=ctx.data_model,
            field_samples=ctx.field_samples,
        )

        logger.info("query_adapter_node: 成功构建 VizQL 查询")

        return {
            "semantic_query": vizql_query,
        }

    except Exception as e:
        logger.error(f"query_adapter_node: 构建查询失败: {e}")
        return {
            "pipeline_error": {
                "error_type": "build_error",
                "message": str(e),
                "is_retryable": True,
            }
        }

async def error_corrector_node(state: SemanticParserState) -> dict[str, Any]:
    """错误修正节点

    基于执行错误反馈，让 LLM 修正语义理解输出。

    输入：
    - state["question"]: 用户问题
    - state["semantic_output"]: 之前的语义输出
    - state["pipeline_error"]: 执行错误
    - state["error_history"]: 错误历史
    - state["retry_count"]: 当前重试次数

    输出：
    - semantic_output: 修正后的语义输出
    - error_history: 更新后的错误历史
    - retry_count: 更新后的重试次数
    - correction_abort_reason: 修正终止原因（如果终止）
    - thinking: LLM 思考过程
    """
    question = state.get("question", "")
    semantic_output_raw = state.get("semantic_output")
    pipeline_error = state.get("pipeline_error")
    error_history = state.get("error_history", [])
    retry_count = state.get("retry_count", 0)

    if not pipeline_error:
        logger.warning("error_corrector_node: 没有错误需要修正")
        return {}

    if not semantic_output_raw:
        logger.warning("error_corrector_node: 缺少 semantic_output")
        return {
            "correction_abort_reason": "missing_semantic_output",
        }

    semantic_output = SemanticOutput.model_validate(semantic_output_raw)

    error_type = pipeline_error.get("error_type", "unknown")
    error_message = pipeline_error.get("message", "")

    corrector = ErrorCorrector()

    # 恢复错误历史
    for h in error_history:
        corrector._error_history.append(
            ErrorCorrectionHistory.model_validate(h)
        )

    result = await corrector.correct(
        question=question,
        previous_output=semantic_output,
        error_info=error_message,
        error_type=error_type,
    )

    new_error_history = [h.model_dump() for h in corrector.error_history]
    new_retry_count = corrector.retry_count

    if not result.should_continue:
        logger.info(
            f"error_corrector_node: 修正终止, reason={result.abort_reason}"
        )
        return {
            "error_history": new_error_history,
            "retry_count": new_retry_count,
            "correction_abort_reason": result.abort_reason,
            "thinking": result.thinking,
        }

    logger.info(
        f"error_corrector_node: 修正完成, retry_count={new_retry_count}"
    )

    return {
        "semantic_output": result.corrected_output.model_dump() if result.corrected_output else semantic_output_raw,
        "error_history": new_error_history,
        "retry_count": new_retry_count,
        "pipeline_error": None,
        "thinking": result.thinking,
    }

async def feedback_learner_node(
    state: SemanticParserState,
    config: Optional[RunnableConfig] = None,
) -> dict[str, Any]:
    """反馈学习节点

    记录成功的查询，更新缓存，学习用户反馈。

    输入：
    - state["question"]: 用户问题
    - state["semantic_output"]: 语义输出
    - state["semantic_query"]: 生成的查询
    - state["datasource_luid"]: 数据源 ID
    - state["confirmed_filters"]: 确认的筛选值

    输出：
    - parse_result: 解析结果汇总
    """
    question = state.get("question", "")
    semantic_output_raw = state.get("semantic_output")
    semantic_query = state.get("semantic_query")
    datasource_luid = state.get("datasource_luid", "")
    confirmed_filters = state.get("confirmed_filters", [])
    optimization_metrics = dict(state.get("optimization_metrics") or {})
    is_degraded = bool(state.get("is_degraded", False))
    ctx = get_context(config) if config else None
    prefilter_result_raw = state.get("prefilter_result")
    prefilter_result = (
        PrefilterResult.model_validate(prefilter_result_raw)
        if prefilter_result_raw else None
    )

    if not semantic_output_raw:
        logger.warning("feedback_learner_node: 缺少 semantic_output")
        return {
            "parse_result": {
                "success": False,
                "error": {"message": "缺少 semantic_output"},
            }
        }

    semantic_output = SemanticOutput.model_validate(semantic_output_raw)

    # 缓存成功的查询
    if datasource_luid and semantic_query:
        cache = get_query_cache()
        schema_hash = getattr(ctx, "schema_hash", "")
        if schema_hash:
            include_cache_embedding = (
                is_degraded
                or (bool(prefilter_result.low_confidence) if prefilter_result else False)
                or (
                    prefilter_result.detected_complexity != [ComplexityType.SIMPLE]
                    if prefilter_result else False
                )
            )
            optimization_metrics["query_cache_embedding_written"] = include_cache_embedding
            cache.set(
                question=question,
                datasource_luid=datasource_luid,
                schema_hash=schema_hash,
                semantic_output=semantic_output_raw,
                query=semantic_query,
                analysis_plan=state.get("analysis_plan"),
                global_understanding=state.get("global_understanding"),
                include_embedding=include_cache_embedding,
            )
        else:
            logger.warning(
                "feedback_learner_node: 缺少 schema_hash，跳过 QueryCache 写入"
            )

    # 学习同义词
    if confirmed_filters and datasource_luid:
        learner = FeedbackLearner()
        for conf in confirmed_filters:
            await learner.learn_synonym(
                original_term=conf.get("original_value", ""),
                correct_field=conf.get("confirmed_value", ""),
                datasource_luid=datasource_luid,
            )

    logger.info(
        f"feedback_learner_node: 完成, query_id={semantic_output.query_id}"
    )

    return {
        "parse_result": {
            "success": True,
            "query_id": semantic_output.query_id,
            "semantic_output": semantic_output_raw,
            "analysis_plan": state.get("analysis_plan"),
            "global_understanding": state.get("global_understanding"),
            "query": semantic_query,
            "is_degraded": is_degraded,
            "optimization_metrics": optimization_metrics,
            "query_cache_hit": bool(state.get("cache_hit", False)),
        }
    }
