# -*- coding: utf-8 -*-
"""合并节点：将可合并/可并行的节点组合为单个节点，减少 state 序列化开销。

包含：
- unified_feature_and_understanding_node:
    合并 rule_prefilter + feature_cache + feature_extractor + global_understanding
    global_understanding 始终使用规则 fallback（不调 LLM），复杂查询的 LLM 全局理解
    延迟到 semantic_understanding_node 通过 ComplexSemanticOutput 合并完成
- prepare_prompt_node:
    合并 dynamic_schema_builder + modular_prompt_builder
- parallel_retrieval_node:
    使用 asyncio.gather() 并行执行 field_retriever + few_shot_manager
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Optional

from ..state import SemanticParserState
from ..components import (
    RulePrefilter,
    get_feature_cache,
)
from ..node_utils import merge_metrics
from ..schemas.planner import parse_step_intent, EvidenceContext
from ..schemas.prefilter import (
    ComplexityType,
    FeatureExtractionOutput,
    PrefilterResult,
)

from .cache import (
    _should_allow_semantic_lookup,
    _is_feature_cache_compatible,
)
from .optimization import feature_extractor_node
from analytics_assistant.src.agents.base.context import get_context
from .planner import build_analysis_plan, build_global_understanding_fallback

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# unified_feature_and_understanding_node
# ═══════════════════════════════════════════════════════════════════════════

async def unified_feature_and_understanding_node(
    state: SemanticParserState,
    config=None,
) -> dict[str, Any]:
    """统一特征提取与全局理解节点。

    合并原有的 4 个节点为 1 个，减少 state 序列化开销：
    1. rule_prefilter   （纯规则，~1ms）
    2. feature_cache    （缓存查找，~5ms）
    3. feature_extractor（规则快路径 ~1ms 或 LLM ~500ms）
    4. global_understanding（纯规则 fallback，~1ms）

    优化策略：
    - 全局理解始终使用规则 fallback 生成初步 analysis_plan（供 prepare_prompt 注入 prompt）
    - 复杂查询的 LLM 全局理解判断延迟到 semantic_understanding_node 中执行，
      通过 ComplexSemanticOutput 让 LLM 一次调用同时输出全局理解 + 结构化查询
    - 复杂查询 LLM 从 3 次降为 2 次（feature_extractor + semantic_understanding）

    输入（从 state 读取）：
    - question, datasource_luid, current_time
    - current_step_intent, evidence_context（多步分析场景）

    输出（写入 state）：
    - prefilter_result
    - feature_extraction_output, is_degraded
    - global_understanding, analysis_plan
    - optimization_metrics
    """
    total_start = time.time()
    question = state.get("question", "")
    datasource_luid = state.get("datasource_luid", "")

    if not question:
        logger.warning("unified_feature_and_understanding: 问题为空")
        return {
            "prefilter_result": PrefilterResult().model_dump(),
            "feature_extraction_output": FeatureExtractionOutput(
                is_degraded=True
            ).model_dump(),
            "is_degraded": True,
        }

    # ── Step 1: rule_prefilter (~1ms) ──────────────────────────────────────
    prefilter_start = time.time()
    current_time_str = state.get("current_time")
    current_date = None
    if current_time_str:
        try:
            current_date = datetime.fromisoformat(current_time_str).date()
        except (ValueError, TypeError):
            pass

    prefilter = RulePrefilter(current_date=current_date)
    prefilter_result = prefilter.prefilter(question)
    prefilter_ms = (time.time() - prefilter_start) * 1000

    logger.info(
        "unified: prefilter done, time_hints=%d, computations=%d, "
        "confidence=%.2f, elapsed=%.1fms",
        len(prefilter_result.time_hints),
        len(prefilter_result.matched_computations),
        prefilter_result.match_confidence,
        prefilter_ms,
    )

    prefilter_result_dump = prefilter_result.model_dump()

    # ── Step 2: feature_cache check (~5ms) ─────────────────────────────────
    cached_feature: Optional[dict[str, Any]] = None
    feature_cache_hit = False
    current_step_intent = parse_step_intent(state.get("current_step_intent"))
    feature_cache_context_bypass = current_step_intent is not None

    if datasource_luid and not feature_cache_context_bypass:
        cache = get_feature_cache()

        cached_entry = cache.get(question, datasource_luid)

        allow_semantic_lookup = _should_allow_semantic_lookup(
            question, prefilter_result
        )
        if cached_entry is None and allow_semantic_lookup:
            cached_entry = cache.get_similar(question, datasource_luid)

        if cached_entry is not None and not _is_feature_cache_compatible(
            cached_entry.feature_output, prefilter_result
        ):
            logger.info(
                "unified: feature cache hit but incompatible with prefilter, ignoring"
            )
            cached_entry = None

        if cached_entry is not None:
            cached_feature = cached_entry.feature_output
            feature_cache_hit = True
            logger.info(
                "unified: feature cache hit, hit_count=%d", cached_entry.hit_count
            )

    # ── Step 3: feature_extraction ─────────────────────────────────────────
    enriched_state = {**state, "prefilter_result": prefilter_result_dump}

    if cached_feature is not None:
        feature_output_dump = cached_feature
        is_degraded = bool(cached_feature.get("is_degraded", False))
    else:
        logger.info("unified: running feature_extractor")
        try:
            feature_result = await feature_extractor_node(enriched_state)
            feature_output_dump = feature_result.get(
                "feature_extraction_output",
                FeatureExtractionOutput(is_degraded=True).model_dump(),
            )
            is_degraded = bool(feature_result.get("is_degraded", False))
        except Exception as exc:
            logger.error("unified: feature_extractor failed: %s", exc)
            feature_output_dump = FeatureExtractionOutput(
                is_degraded=True
            ).model_dump()
            is_degraded = True

    feature_ms = (time.time() - total_start) * 1000 - prefilter_ms

    # ── Step 4: rule-based global understanding (~1ms, no LLM) ─────────────
    # 规则 planner 生成初步 analysis_plan，供 prepare_prompt 注入 prompt。
    # 复杂查询的精确全局理解由 semantic_understanding_node 通过
    # ComplexSemanticOutput 在同一次 LLM 调用中完成。
    plan_start = time.time()
    feature_output_obj: Optional[FeatureExtractionOutput] = None
    try:
        feature_output_obj = FeatureExtractionOutput.model_validate(feature_output_dump)
    except Exception:
        pass

    # 从 WorkflowContext 获取 field_semantic，用于动态生成 candidate_axes
    field_semantic = None
    try:
        ctx = get_context(config) if config else None
        if ctx is not None:
            field_semantic = ctx.field_semantic
    except Exception:
        pass

    analysis_plan = build_analysis_plan(
        question=question,
        prefilter_result=prefilter_result,
        feature_output=feature_output_obj,
        field_semantic=field_semantic,
    )
    global_understanding = build_global_understanding_fallback(question, analysis_plan)
    plan_ms = (time.time() - plan_start) * 1000

    is_complex = analysis_plan.needs_planning
    logger.info(
        "unified: rule-based plan, mode=%s, is_complex=%s, plan_ms=%.1fms",
        analysis_plan.plan_mode.value,
        is_complex,
        plan_ms,
    )

    # ── Merge results ──────────────────────────────────────────────────────
    total_ms = (time.time() - total_start) * 1000

    merged: dict[str, Any] = {
        "prefilter_result": prefilter_result_dump,
        "feature_extraction_output": feature_output_dump,
        "is_degraded": is_degraded,
        "analysis_plan": analysis_plan.model_dump(),
        "global_understanding": global_understanding.model_dump(),
        "optimization_metrics": merge_metrics(
            state,
            rule_prefilter_ms=prefilter_ms,
            feature_cache_hit=feature_cache_hit,
            feature_cache_context_bypass=feature_cache_context_bypass,
            feature_extractor_ms=feature_ms,
            global_understanding_ms=plan_ms,
            global_understanding_mode=global_understanding.analysis_mode.value,
            global_understanding_llm_used=False,
            global_understanding_rule_only=True,
            unified_total_ms=total_ms,
        ),
    }

    logger.info(
        "unified: done, cache_hit=%s, total=%.1fms (prefilter=%.1f, feature=%.1f, plan=%.1f)",
        feature_cache_hit,
        total_ms,
        prefilter_ms,
        feature_ms,
        plan_ms,
    )

    return merged


# ═══════════════════════════════════════════════════════════════════════════
# prepare_prompt_node
# ═══════════════════════════════════════════════════════════════════════════

async def prepare_prompt_node(state: SemanticParserState) -> dict[str, Any]:
    """统一 Prompt 准备节点。

    合并原有的 dynamic_schema_builder + modular_prompt_builder 为 1 个节点。
    两者都是纯逻辑（无 LLM），各 ~10ms，合并后减少 1 次 state 序列化。

    输入（从 state 读取）：
    - feature_extraction_output, field_candidates, prefilter_result
    - question, few_shot_examples, current_time, chat_history
    - analysis_plan, current_step_intent, evidence_context, global_understanding

    输出（写入 state）：
    - dynamic_schema_result, field_candidates（已裁剪）
    - modular_prompt
    - optimization_metrics
    """
    from ..components import DynamicSchemaBuilder
    from ..schemas.prefilter import FieldRAGResult
    from ..schemas.planner import AnalysisPlan, parse_analysis_plan
    from ..schemas.intermediate import FewShotExample
    from ..schemas.config import SemanticConfig
    from ..prompts import DynamicPromptBuilder
    from ..node_utils import parse_field_candidates, classify_fields

    start_time = time.time()

    # ── Step 1: dynamic_schema_builder ─────────────────────────────────────
    feature_output_raw = state.get("feature_extraction_output")
    field_candidates_raw = state.get("field_candidates", [])
    prefilter_result_raw = state.get("prefilter_result")

    feature_output = None
    if feature_output_raw:
        feature_output = FeatureExtractionOutput.model_validate(feature_output_raw)

    prefilter_result = None
    if prefilter_result_raw:
        prefilter_result = PrefilterResult.model_validate(prefilter_result_raw)

    field_candidates = parse_field_candidates(field_candidates_raw)
    classified = classify_fields(field_candidates)

    field_rag_result = FieldRAGResult(
        measures=classified["measures"],
        dimensions=classified["dimensions"],
        time_fields=classified["time_fields"],
    )

    schema_builder = DynamicSchemaBuilder()
    schema_result = schema_builder.build(
        feature_output=feature_output,
        field_rag_result=field_rag_result,
        prefilter_result=prefilter_result,
    )

    schema_ms = (time.time() - start_time) * 1000

    # Schema 输出
    dynamic_schema_result = {
        "field_candidates": [c.model_dump() for c in schema_result.field_candidates],
        "schema_text": schema_result.schema_text,
        "modules": list(schema_result.modules),
        "detected_complexity": [c.value for c in schema_result.detected_complexity],
        "allowed_calc_types": schema_result.allowed_calc_types,
        "time_expressions": schema_result.time_expressions,
    }

    # ── Step 2: modular_prompt_builder ─────────────────────────────────────
    prompt_start = time.time()

    question = state.get("question", "")
    analysis_plan_raw = state.get("analysis_plan")
    current_step_intent_raw = state.get("current_step_intent")
    evidence_context_raw = state.get("evidence_context")
    global_understanding_raw = state.get("global_understanding")
    few_shot_examples_raw = state.get("few_shot_examples", [])
    current_time_str = state.get("current_time")
    chat_history = state.get("chat_history")

    few_shot_examples = (
        [FewShotExample.model_validate(e) for e in few_shot_examples_raw]
        if few_shot_examples_raw
        else None
    )

    current_date = None
    if current_time_str:
        try:
            current_date = datetime.fromisoformat(current_time_str).date()
        except (ValueError, TypeError):
            pass

    config = SemanticConfig(current_date=current_date or datetime.now().date())

    analysis_plan = parse_analysis_plan(
        raw_analysis_plan=analysis_plan_raw,
        raw_global_understanding=global_understanding_raw,
    )
    current_step_intent = parse_step_intent(current_step_intent_raw)
    evidence_context = None
    if evidence_context_raw:
        evidence_context = EvidenceContext.model_validate(evidence_context_raw)

    prompt_builder = DynamicPromptBuilder()
    prompt = prompt_builder.build(
        question=question,
        config=config,
        field_candidates=schema_result.field_candidates,
        schema_json=schema_result.schema_text,
        detected_complexity=schema_result.detected_complexity,
        allowed_calc_types=schema_result.allowed_calc_types,
        history=chat_history,
        few_shot_examples=few_shot_examples,
        prefilter_result=prefilter_result,
        feature_output=feature_output,
        analysis_plan=analysis_plan,
        current_step_intent=current_step_intent,
        evidence_context=evidence_context,
    )

    prompt_ms = (time.time() - prompt_start) * 1000
    total_ms = (time.time() - start_time) * 1000

    logger.info(
        "prepare_prompt: done, complexity=%s, schema_len=%d, prompt_len=%d, "
        "schema_ms=%.1f, prompt_ms=%.1f, total=%.1fms",
        [c.value for c in schema_result.detected_complexity],
        len(schema_result.schema_text),
        len(prompt),
        schema_ms,
        prompt_ms,
        total_ms,
    )

    return {
        "dynamic_schema_result": dynamic_schema_result,
        "field_candidates": [c.model_dump() for c in schema_result.field_candidates],
        "modular_prompt": prompt,
        "optimization_metrics": merge_metrics(
            state,
            dynamic_schema_builder_ms=schema_ms,
            modular_prompt_builder_ms=prompt_ms,
            prepare_prompt_total_ms=total_ms,
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════
# parallel_retrieval_node
# ═══════════════════════════════════════════════════════════════════════════

async def parallel_retrieval_node(
    state: SemanticParserState,
    config=None,
) -> dict[str, Any]:
    """并行检索节点：field_retriever ∥ few_shot_manager。

    两者互不依赖：
    - field_retriever 需要 feature_extraction_output + global_understanding（来自 unified）
    - few_shot_manager 需要 question + datasource_luid + prefilter_result（来自 unified）

    合并后减少 1 个图节点，同时并行执行减少 ~150-300ms。

    输入（从 state 读取）：
    - 继承 field_retriever_node 和 few_shot_manager_node 的全部输入

    输出（写入 state）：
    - field_candidates
    - few_shot_examples
    - optimization_metrics
    """
    from .retrieval import field_retriever_node, few_shot_manager_node

    start_time = time.time()
    logger.info("parallel_retrieval: field_retriever ∥ few_shot_manager")

    field_task = field_retriever_node(state, config=config)
    fewshot_task = few_shot_manager_node(state)

    raw_field, raw_fewshot = await asyncio.gather(
        field_task, fewshot_task, return_exceptions=True
    )

    if isinstance(raw_field, BaseException):
        logger.error("parallel_retrieval: field_retriever failed: %s", raw_field)
        field_result: dict[str, Any] = {"field_candidates": []}
    else:
        field_result = raw_field

    if isinstance(raw_fewshot, BaseException):
        logger.error("parallel_retrieval: few_shot_manager failed: %s", raw_fewshot)
        fewshot_result: dict[str, Any] = {"few_shot_examples": []}
    else:
        fewshot_result = raw_fewshot

    total_ms = (time.time() - start_time) * 1000

    field_metrics = field_result.get("optimization_metrics", {})
    fewshot_metrics = fewshot_result.get("optimization_metrics", {})

    merged: dict[str, Any] = {}
    for key, value in field_result.items():
        if key != "optimization_metrics":
            merged[key] = value
    for key, value in fewshot_result.items():
        if key != "optimization_metrics":
            merged[key] = value

    merged["optimization_metrics"] = {
        **field_metrics,
        **fewshot_metrics,
        "parallel_retrieval_total_ms": total_ms,
        "parallel_retrieval_executed": True,
    }

    logger.info("parallel_retrieval: done, total=%.1fms", total_ms)

    return merged


__all__ = [
    "unified_feature_and_understanding_node",
    "prepare_prompt_node",
    "parallel_retrieval_node",
]
