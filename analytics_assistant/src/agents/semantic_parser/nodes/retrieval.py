# -*- coding: utf-8 -*-
"""检索相关节点：字段检索、Few-shot 示例检索"""
import logging
import time
from typing import Any, Optional

from langgraph.types import RunnableConfig

from ..state import SemanticParserState
from ..components import FieldRetriever, FewShotManager
from ..node_utils import merge_metrics
from ..schemas.planner import PlanMode, StepIntent, parse_analysis_plan, parse_step_intent
from ..schemas.prefilter import FeatureExtractionOutput, PrefilterResult, ComplexityType
from analytics_assistant.src.agents.base.context import get_context

logger = logging.getLogger(__name__)

_FEATURE_CONFIDENCE_FOR_SKIP_RERANK = 0.75


def _has_step_intent_context(step_intent: Optional[StepIntent]) -> bool:
    """当前 step 是否带有多步上下文约束。"""

    if step_intent is None:
        return False
    return bool(
        step_intent.depends_on
        or step_intent.semantic_focus
        or step_intent.candidate_axes
        or step_intent.expected_output
    )


def _dedupe_keep_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = (value or "").strip()
        if not normalized:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


def _apply_step_intent_hints(
    feature_output: FeatureExtractionOutput,
    step_intent: Optional[StepIntent],
) -> FeatureExtractionOutput:
    """将 step intent 中的候选轴/关注点温和注入到检索输入。

    当前仅将 candidate_axes 视为维度 hint，避免把 follow-up step
    错误地当成无上下文的简单查询。
    """

    if step_intent is None:
        return feature_output

    hinted_dimensions = _dedupe_keep_order(
        [
            *feature_output.required_dimensions,
            *step_intent.candidate_axes,
        ]
    )

    return feature_output.model_copy(
        update={
            "required_dimensions": hinted_dimensions,
        }
    )

async def field_retriever_node(
    state: SemanticParserState,
    config: Optional[RunnableConfig] = None,
) -> dict[str, Any]:
    """字段检索节点

    检索与问题相关的字段，并使用维度层级信息丰富结果。

    输入：
    - state["question"]: 用户问题
    - state["feature_extraction_output"]: 特征提取输出（可选）
    - config["configurable"]["workflow_context"]: WorkflowContext

    输出：
    - field_candidates: FieldCandidate 列表序列化后的 list[dict]
    """
    start_time = time.time()
    logger.info("=" * 60)
    logger.info("[field_retriever_node] 开始执行")
    question = state.get("question", "")
    logger.info(f"[field_retriever_node] 问题: {question}")

    if not question:
        logger.warning("field_retriever_node: 问题为空")
        return {"field_candidates": []}

    # 从 config 获取 WorkflowContext
    logger.info("[field_retriever_node] 获取 WorkflowContext...")
    ctx = get_context(config) if config else None
    data_model = ctx.data_model if ctx else None
    datasource_luid = ctx.datasource_luid if ctx else None
    logger.info(f"[field_retriever_node] datasource_luid={datasource_luid}")

    # 获取或创建 FeatureExtractionOutput
    feature_output_raw = state.get("feature_extraction_output")
    if feature_output_raw:
        logger.info("[field_retriever_node] 使用 feature_extraction_output")
        feature_output = FeatureExtractionOutput.model_validate(feature_output_raw)
    else:
        logger.debug("field_retriever_node: 未找到 feature_extraction_output，使用降级方案")
        feature_output = FeatureExtractionOutput(
            required_measures=[],
            required_dimensions=[],
            is_degraded=True,
        )

    prefilter_result_raw = state.get("prefilter_result")
    prefilter_result = (
        PrefilterResult.model_validate(prefilter_result_raw)
        if prefilter_result_raw else None
    )
    detected_complexity = (
        prefilter_result.detected_complexity if prefilter_result else [ComplexityType.SIMPLE]
    )
    low_confidence = bool(prefilter_result.low_confidence) if prefilter_result else False
    analysis_plan = parse_analysis_plan(
        raw_analysis_plan=state.get("analysis_plan"),
        raw_global_understanding=state.get("global_understanding"),
    )
    current_step_intent = parse_step_intent(state.get("current_step_intent"))
    feature_output = _apply_step_intent_hints(feature_output, current_step_intent)
    planner_requires_reasoning = bool(
        analysis_plan
        and (
            analysis_plan.requires_llm_reasoning
            or analysis_plan.plan_mode != PlanMode.DIRECT_QUERY
        )
    )
    step_requires_context = _has_step_intent_context(current_step_intent)
    feature_confident = (
        not feature_output.is_degraded
        and (
            bool(feature_output.required_measures)
            or bool(feature_output.required_dimensions)
            or bool(feature_output.confirmed_time_hints)
        )
        and feature_output.confirmation_confidence >= _FEATURE_CONFIDENCE_FOR_SKIP_RERANK
    )
    is_simple_query = detected_complexity == [ComplexityType.SIMPLE]
    effective_low_confidence = low_confidence and not feature_confident
    enable_rerank = (
        bool(state.get("is_degraded", False))
        or effective_low_confidence
        or not is_simple_query
        or planner_requires_reasoning
        or step_requires_context
    )

    logger.info(
        "[field_retriever_node] 创建 FieldRetriever... "
        f"enable_rerank={enable_rerank}, "
        f"complexity={[c.value if hasattr(c, 'value') else c for c in detected_complexity]}, "
        f"low_confidence={low_confidence}, "
        f"planner_requires_reasoning={planner_requires_reasoning}, "
        f"step_requires_context={step_requires_context}, "
        f"feature_confident={feature_confident}, "
        f"feature_confidence={feature_output.confirmation_confidence:.2f}"
    )
    retriever = FieldRetriever(enable_rerank=enable_rerank)

    # 检索字段
    logger.info("[field_retriever_node] 调用 retriever.retrieve()...")
    try:
        rag_result = await retriever.retrieve(
            feature_output=feature_output,
            data_model=data_model,
            datasource_luid=datasource_luid,
        )
        logger.info("[field_retriever_node] retriever.retrieve() 完成")
    except Exception as e:
        logger.exception(f"[field_retriever_node] retriever.retrieve() 失败: {e}")
        raise

    # 合并所有候选字段
    candidates = rag_result.measures + rag_result.dimensions + rag_result.time_fields

    # 使用字段语义信息丰富字段候选（Property 28: Hierarchy Enrichment）
    if ctx and ctx.field_semantic:
        logger.info("[field_retriever_node] 丰富字段候选...")
        candidates = ctx.enrich_field_candidates_with_hierarchy(candidates)

    logger.info(f"field_retriever_node: 检索到 {len(candidates)} 个字段")
    logger.info("[field_retriever_node] 执行完成")
    logger.info("=" * 60)
    elapsed_ms = (time.time() - start_time) * 1000

    return {
        "field_candidates": [c.model_dump() for c in candidates],
        "optimization_metrics": merge_metrics(
            state,
            field_retriever_ms=elapsed_ms,
            field_retriever_rerank_enabled=enable_rerank,
            field_retriever_feature_confident=feature_confident,
            field_retriever_planner_reasoning=planner_requires_reasoning,
            field_retriever_step_intent_focus=step_requires_context,
        ),
    }

async def few_shot_manager_node(state: SemanticParserState) -> dict[str, Any]:
    """Few-shot 示例检索节点

    输入：
    - state["question"]: 用户问题
    - state["datasource_luid"]: 数据源 ID

    输出：
    - few_shot_examples: FewShotExample 列表序列化后的 list[dict]
    """
    start_time = time.time()
    question = state.get("question", "")
    datasource_luid = state.get("datasource_luid", "")

    if not question or not datasource_luid:
        logger.debug("few_shot_manager_node: 缺少必要参数")
        return {
            "few_shot_examples": [],
            "optimization_metrics": merge_metrics(
                state,
                few_shot_manager_ms=0.0,
                few_shot_skipped=True,
            ),
        }

    dynamic_schema_result = state.get("dynamic_schema_result") or {}
    detected_complexity = dynamic_schema_result.get("detected_complexity", [])
    analysis_plan = parse_analysis_plan(
        raw_analysis_plan=state.get("analysis_plan"),
        raw_global_understanding=state.get("global_understanding"),
    )
    current_step_intent = parse_step_intent(state.get("current_step_intent"))
    planner_requires_reasoning = bool(
        analysis_plan
        and (
            analysis_plan.requires_llm_reasoning
            or analysis_plan.plan_mode != PlanMode.DIRECT_QUERY
        )
    )
    step_requires_context = _has_step_intent_context(current_step_intent)
    is_simple_query = (
        detected_complexity == ["simple"]
        and not planner_requires_reasoning
        and not step_requires_context
    )
    if is_simple_query and not bool(state.get("is_degraded", False)):
        logger.info("few_shot_manager_node: 简单查询，跳过 few-shot 检索")
        return {
            "few_shot_examples": [],
            "optimization_metrics": merge_metrics(
                state,
                few_shot_manager_ms=0.0,
                few_shot_skipped=True,
            ),
        }

    manager = FewShotManager()
    examples = await manager.retrieve(
        question=question,
        datasource_luid=datasource_luid,
        top_k=3,
    )
    elapsed_ms = (time.time() - start_time) * 1000

    logger.info(f"few_shot_manager_node: 检索到 {len(examples)} 个示例")

    return {
        "few_shot_examples": [e.model_dump() for e in examples],
        "optimization_metrics": merge_metrics(
            state,
            few_shot_manager_ms=elapsed_ms,
            few_shot_skipped=False,
            few_shot_step_intent_focus=step_requires_context,
        ),
    }
