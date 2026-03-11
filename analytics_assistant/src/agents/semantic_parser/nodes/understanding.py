# -*- coding: utf-8 -*-
"""语义理解节点"""
import logging
import re
import threading
import time
from datetime import datetime
from typing import Any, Optional

from langchain_core.messages import HumanMessage
from langgraph.types import RunnableConfig

from analytics_assistant.src.agents.base.node import get_llm, stream_llm_structured
from analytics_assistant.src.core.schemas.enums import (
    AggregationType,
    FilterType,
    HowType,
    SortDirection,
)
from analytics_assistant.src.core.schemas.filters import TopNFilter

from analytics_assistant.src.infra.seeds import (
    COMPUTATION_SEEDS,
)

from ..node_utils import merge_metrics, parse_field_candidates
from ..state import SemanticParserState
from ..components.candidate_resolver import (
    CLARIFICATION_CANDIDATE_MIN_CONFIDENCE as _CLARIFICATION_CANDIDATE_MIN_CONFIDENCE,
    CandidateMatchContext,
    _field_display_name,
    _build_runtime_semantic_lexicon,
    _measure_name_matches_placeholder,
    _matches_measure_placeholder,
    _score_dimension_fallback_candidate,
    _resolve_simple_candidates,
    _format_clarification_option,
    _build_clarification_question,
    _build_missing_dimension_question,
    _should_use_missing_dimension_question,
    _collect_clarification_options,
)
from ..components.semantic_understanding import (
    SemanticUnderstanding,
    get_low_confidence_threshold,
    get_simple_query_model_id,
    get_confidence_blend_weights,
)
from ..schemas.output import (
    ClarificationSource,
    ComplexSemanticOutput,
    DerivedComputation,
    SemanticOutput,
    SelfCheck,
    What,
    Where,
)
from ..schemas.planner import EvidenceContext, PlanMode, StepIntent, parse_analysis_plan, parse_step_intent
from ..schemas.config import SemanticConfig
from ..prompts import DynamicPromptBuilder
from ..schemas.prefilter import ComplexityType, FeatureExtractionOutput, PrefilterResult
from ..schemas.intermediate import FieldCandidate, FewShotExample

logger = logging.getLogger(__name__)

_FAST_SEMANTIC_MIN_CONFIDENCE = 0.75
_FAST_SEMANTIC_MAX_PROMPT_LENGTH = 2600
_fast_semantic_model_available: Optional[bool] = None
_fast_semantic_model_unavailable_since: Optional[float] = None
_FAST_MODEL_RETRY_TTL_SECONDS = 300  # 5 分钟后重试
_fast_model_lock = threading.Lock()

_CN_DIGIT_MAP = {"一": "1", "二": "2", "三": "3", "四": "4", "五": "5",
                  "六": "6", "七": "7", "八": "8", "九": "9", "十": "10"}

_TOP_N_PATTERNS: tuple[tuple[re.Pattern[str], SortDirection], ...] = (
    (re.compile(r"(?:前|top)[\s\-]*(\d+)", re.IGNORECASE), SortDirection.DESC),
    (re.compile(r"(?:后|bottom)[\s\-]*(\d+)", re.IGNORECASE), SortDirection.ASC),
    (re.compile(r"最高(?:的)?\s*(\d+)", re.IGNORECASE), SortDirection.DESC),
    (re.compile(r"最低(?:的)?\s*(\d+)", re.IGNORECASE), SortDirection.ASC),
    (re.compile(r"排名(?:前|最高)?\s*(\d+)", re.IGNORECASE), SortDirection.DESC),
    (re.compile(r"排名(?:后|最低)\s*(\d+)", re.IGNORECASE), SortDirection.ASC),
    # 中文数字支持（前三名、前五等）
    (re.compile(r"前([一二三四五六七八九十])(?:名|个)?"), SortDirection.DESC),
    (re.compile(r"后([一二三四五六七八九十])(?:名|个)?"), SortDirection.ASC),
)

def _post_process_semantic_output(result: SemanticOutput) -> SemanticOutput:
    """后处理：检查自检结果

    如果任一置信度低于阈值，确保 potential_issues 非空。
    """
    self_check = result.self_check
    low_confidence_threshold = get_low_confidence_threshold()

    low_confidence_fields = []

    if self_check.field_mapping_confidence < low_confidence_threshold:
        low_confidence_fields.append(
            f"字段映射置信度较低 ({self_check.field_mapping_confidence:.2f})"
        )

    if self_check.time_range_confidence < low_confidence_threshold:
        low_confidence_fields.append(
            f"时间范围置信度较低 ({self_check.time_range_confidence:.2f})"
        )

    if self_check.computation_confidence < low_confidence_threshold:
        low_confidence_fields.append(
            f"计算逻辑置信度较低 ({self_check.computation_confidence:.2f})"
        )

    if self_check.overall_confidence < low_confidence_threshold:
        low_confidence_fields.append(
            f"整体置信度较低 ({self_check.overall_confidence:.2f})"
        )

    if low_confidence_fields and not self_check.potential_issues:
        self_check.potential_issues = low_confidence_fields
        result.parsing_warnings.append(
            "检测到低置信度但 LLM 未报告问题，已自动添加警告"
        )

    return result


def _infer_fallback_aggregation(term: str) -> AggregationType:
    """为特征提取的度量候选推断一个合理的默认聚合。"""
    normalized = term.strip().lower()
    count_hints = ("count", "数量", "个数", "次数", "笔数", "总数", "条数", "单数")
    if any(hint in normalized for hint in count_hints):
        return AggregationType.COUNT
    return AggregationType.SUM


def _get_feature_output(state: SemanticParserState) -> Optional[FeatureExtractionOutput]:
    raw = state.get("feature_extraction_output")
    if not raw:
        return None
    try:
        return FeatureExtractionOutput.model_validate(raw)
    except Exception:
        return None


def _get_prefilter_result(state: SemanticParserState) -> Optional[PrefilterResult]:
    raw = state.get("prefilter_result")
    if not raw:
        return None
    try:
        return PrefilterResult.model_validate(raw)
    except Exception:
        return None


def _analysis_plan_requires_reasoning(state: SemanticParserState) -> bool:
    analysis_plan = parse_analysis_plan(
        raw_analysis_plan=state.get("analysis_plan"),
        raw_global_understanding=state.get("global_understanding"),
    )
    if analysis_plan is None:
        return False
    return bool(
        analysis_plan.requires_llm_reasoning
        or analysis_plan.plan_mode != PlanMode.DIRECT_QUERY
    )


def _get_current_step_intent(state: SemanticParserState) -> Optional[StepIntent]:
    return parse_step_intent(state.get("current_step_intent"))


def _step_intent_requires_reasoning(state: SemanticParserState) -> bool:
    current_step_intent = _get_current_step_intent(state)
    if current_step_intent is None:
        return False
    return bool(
        current_step_intent.depends_on
        or current_step_intent.semantic_focus
        or current_step_intent.candidate_axes
        or current_step_intent.expected_output
    )


def _should_use_fast_semantic_model(
    state: SemanticParserState,
    modular_prompt: str,
) -> bool:
    """简单且高置信度的请求优先走非推理模型。"""
    if not modular_prompt or len(modular_prompt) > _FAST_SEMANTIC_MAX_PROMPT_LENGTH:
        return False

    if state.get("few_shot_examples"):
        return False
    if _analysis_plan_requires_reasoning(state):
        return False
    if _step_intent_requires_reasoning(state):
        return False

    prefilter_result = _get_prefilter_result(state)
    if prefilter_result is None:
        return False
    if prefilter_result.detected_complexity != [ComplexityType.SIMPLE]:
        return False
    if prefilter_result.matched_computations:
        return False

    feature_output = _get_feature_output(state)
    if feature_output is None or feature_output.is_degraded:
        return False
    if feature_output.confirmation_confidence < _FAST_SEMANTIC_MIN_CONFIDENCE:
        return False

    return bool(
        feature_output.required_measures
        or feature_output.required_dimensions
        or feature_output.confirmed_time_hints
    )


def _get_semantic_llm(
    state: SemanticParserState,
    modular_prompt: str,
):
    """根据当前请求复杂度选择更合适的语义理解模型。"""
    global _fast_semantic_model_available, _fast_semantic_model_unavailable_since
    use_fast_model = _should_use_fast_semantic_model(state, modular_prompt)
    simple_query_model_id = get_simple_query_model_id()

    with _fast_model_lock:
        # TTL 重试：如果快模型之前不可用，检查是否已过 TTL
        if (
            _fast_semantic_model_available is False
            and _fast_semantic_model_unavailable_since is not None
            and (time.time() - _fast_semantic_model_unavailable_since) > _FAST_MODEL_RETRY_TTL_SECONDS
        ):
            logger.info("semantic_understanding_node: 快模型 TTL 已过期，重新尝试")
            _fast_semantic_model_available = None
            _fast_semantic_model_unavailable_since = None

        should_try_fast = use_fast_model and _fast_semantic_model_available is not False

    if should_try_fast:
        try:
            llm = get_llm(
                agent_name="semantic_parser",
                model_id=simple_query_model_id,
                enable_json_mode=True,
            )
            with _fast_model_lock:
                _fast_semantic_model_available = True
            return llm, True
        except Exception as exc:
            with _fast_model_lock:
                _fast_semantic_model_available = False
                _fast_semantic_model_unavailable_since = time.time()
            logger.warning(
                "semantic_understanding_node: 快模型不可用，回退默认模型 (TTL=%ds): %s",
                _FAST_MODEL_RETRY_TTL_SECONDS,
                exc,
            )

    llm = get_llm(
        agent_name="semantic_parser",
        enable_json_mode=True,
    )
    return llm, False


def _get_measure_names(
    result: SemanticOutput,
    feature_output: Optional[FeatureExtractionOutput],
) -> list[str]:
    names = [
        measure.field_name.strip()
        for measure in result.what.measures
        if getattr(measure, "field_name", "").strip()
    ]
    if names:
        return names
    if feature_output:
        return [item.strip() for item in feature_output.required_measures if item.strip()]
    return []


def _get_dimension_names(
    result: SemanticOutput,
    feature_output: Optional[FeatureExtractionOutput],
) -> list[str]:
    names = [
        dimension.field_name.strip()
        for dimension in result.where.dimensions
        if getattr(dimension, "field_name", "").strip()
    ]
    if names:
        return names
    if feature_output:
        return [item.strip() for item in feature_output.required_dimensions if item.strip()]
    return []


def _build_measure_mapping(
    *,
    seed_name: str,
    base_measures: list[str],
    result: SemanticOutput,
    state: SemanticParserState,
    feature_output: Optional[FeatureExtractionOutput],
) -> dict[str, str]:
    measure_names = _get_measure_names(result, feature_output)
    measure_candidates = [
        candidate
        for candidate in parse_field_candidates(state.get("field_candidates", []))
        if candidate.role.lower() == "measure"
    ]
    lexicon = _build_runtime_semantic_lexicon(measure_candidates)
    used_candidates: set[int] = set()
    mapping: dict[str, str] = {}

    for placeholder in base_measures:
        if placeholder == "measure":
            if measure_names:
                mapping[placeholder] = measure_names[0]
                continue
            if measure_candidates:
                mapping[placeholder] = _field_display_name(measure_candidates[0])
                used_candidates.add(0)
                continue

        matched = False
        for idx, candidate in enumerate(measure_candidates):
            if idx in used_candidates:
                continue
            if _matches_measure_placeholder(candidate, placeholder, lexicon):
                mapping[placeholder] = _field_display_name(candidate)
                used_candidates.add(idx)
                matched = True
                break
        if matched:
            continue

        for name in measure_names:
            if _measure_name_matches_placeholder(name, placeholder, lexicon):
                mapping[placeholder] = name
                matched = True
                break
        if matched:
            continue

        if not matched:
            logger.warning(
                "semantic_understanding_node: 计算种子 %s 的占位符 '%s' "
                "无法匹配到任何候选度量，跳过该占位符",
                seed_name,
                placeholder,
            )

    logger.debug(
        "semantic_understanding_node: 计算种子 %s 的 measure_mapping=%s",
        seed_name,
        mapping,
    )
    return mapping


def _backfill_computations(
    result: SemanticOutput,
    state: SemanticParserState,
) -> SemanticOutput:
    feature_output = _get_feature_output(state)
    prefilter_result = _get_prefilter_result(state)

    seed_names: list[str] = []
    if feature_output:
        for seed_name in feature_output.confirmed_computations:
            if seed_name and seed_name not in seed_names:
                seed_names.append(seed_name)
    if prefilter_result:
        for computation in prefilter_result.matched_computations:
            if computation.seed_name and computation.seed_name not in seed_names:
                seed_names.append(computation.seed_name)

    if not seed_names:
        return result

    seeds_by_name: dict[str, Any] = {}
    for seed in COMPUTATION_SEEDS:
        seeds_by_name.setdefault(seed.name, seed)
        seeds_by_name.setdefault(seed.display_name, seed)
    ordered_seeds = [seeds_by_name[name] for name in seed_names if name in seeds_by_name]
    if not ordered_seeds:
        return result

    def _build_seed_payload(seed_name: str) -> Optional[dict[str, Any]]:
        seed = seeds_by_name.get(seed_name)
        if seed is None:
            return None
        measure_mapping = _build_measure_mapping(
            seed_name=seed.name,
            base_measures=seed.base_measures,
            result=result,
            state=state,
            feature_output=feature_output,
        )
        return seed.to_computation_dict(measure_mapping or None)

    if result.computations:
        enriched = False
        updated_computations = []
        for computation in result.computations:
            if computation.formula:
                updated_computations.append(computation)
                continue

            matched_seed = None
            comp_name = computation.name.lower()
            comp_display = computation.display_name.lower()
            for seed in ordered_seeds:
                if seed.name.lower() == comp_name or seed.display_name.lower() == comp_display:
                    matched_seed = seed
                    break
                if seed.display_name.lower() in comp_name or seed.name.lower() in comp_name:
                    matched_seed = seed
                    break
            if matched_seed is None and len(ordered_seeds) == 1:
                matched_seed = ordered_seeds[0]

            if matched_seed is None:
                updated_computations.append(computation)
                continue

            seed_payload = _build_seed_payload(matched_seed.name)
            if not seed_payload:
                updated_computations.append(computation)
                continue

            computation_payload = computation.model_dump()
            if not computation_payload.get("formula"):
                computation_payload["formula"] = seed_payload.get("formula")
            if not computation_payload.get("base_measures"):
                computation_payload["base_measures"] = seed_payload.get("base_measures", [])
            updated_computations.append(DerivedComputation.model_validate(computation_payload))
            enriched = True

        if enriched:
            result.computations = updated_computations
            result.how_type = HowType.COMPLEX
            result.parsing_warnings.append("基于规则计算种子补全 computation 公式")
        return result

    computations = []
    for seed in ordered_seeds:
        seed_payload = _build_seed_payload(seed.name)
        if seed_payload:
            computations.append(seed_payload)

    if computations:
        result.computations = [DerivedComputation.model_validate(item) for item in computations]
        result.how_type = HowType.COMPLEX
        result.parsing_warnings.append("基于规则计算种子补全 computations")

    return result


def _extract_top_n_spec(question: str) -> Optional[tuple[int, SortDirection]]:
    for pattern, direction in _TOP_N_PATTERNS:
        match = pattern.search(question)
        if match:
            raw = match.group(1)
            # 中文数字转换
            n_str = _CN_DIGIT_MAP.get(raw, raw)
            try:
                return int(n_str), direction
            except ValueError:
                continue
    return None


def _has_top_n_filter(result: SemanticOutput) -> bool:
    for filter_obj in result.where.filters:
        filter_type = getattr(filter_obj, "filter_type", None)
        filter_value = getattr(filter_type, "value", filter_type)
        if str(filter_value).upper() == FilterType.TOP_N.value:
            return True
    return False


def _backfill_top_n_filter(
    result: SemanticOutput,
    state: SemanticParserState,
) -> SemanticOutput:
    if _has_top_n_filter(result):
        return result

    rank_spec = _extract_top_n_spec(state.get("question", ""))
    if rank_spec is None:
        return result

    feature_output = _get_feature_output(state)
    dimension_names = _get_dimension_names(result, feature_output)
    measure_names = _get_measure_names(result, feature_output)

    if not dimension_names or not measure_names:
        return result

    top_n, direction = rank_spec
    where_payload = result.where.model_dump()
    filters_payload = list(where_payload.get("filters") or [])
    filters_payload.append(
        TopNFilter(
            field_name=dimension_names[0],
            n=top_n,
            by_field=measure_names[0],
            direction=direction,
        ).model_dump()
    )
    where_payload["filters"] = filters_payload
    result.where = Where.model_validate(where_payload)
    result.parsing_warnings.append("基于问题中的排名表达补全 Top N 筛选器")
    return result


def _backfill_confidence_from_signals(
    result: SemanticOutput,
    state: SemanticParserState,
) -> SemanticOutput:
    feature_output = _get_feature_output(state)
    prefilter_result = _get_prefilter_result(state)
    upstream_confidence = max(
        getattr(feature_output, "confirmation_confidence", 0.0) if feature_output else 0.0,
        getattr(prefilter_result, "match_confidence", 0.0) if prefilter_result else 0.0,
    )
    if upstream_confidence <= 0:
        return result

    has_structured_signal = bool(
        result.what.measures
        or result.where.dimensions
        or result.where.filters
        or result.computations
    )
    if not has_structured_signal:
        return result

    weights = get_confidence_blend_weights()
    llm_w = weights["llm_weight"]
    upstream_w = weights["upstream_weight"]
    divergence_threshold = weights["divergence_threshold"]

    llm_confidence = result.self_check.overall_confidence

    # 如果 LLM 给出的置信度显著低于上游信号，记录警告而非强行覆盖。
    # LLM 可能发现了上游无法检测的语义问题。
    if upstream_confidence - llm_confidence > divergence_threshold:
        result.parsing_warnings.append(
            f"LLM 自评置信度 ({llm_confidence:.2f}) 显著低于上游信号 "
            f"({upstream_confidence:.2f})，保留 LLM 判断"
        )
        return result

    # 对需要澄清的结果：取两者较低值，避免虚高。
    if result.needs_clarification:
        blended = min(llm_confidence, upstream_confidence)
    else:
        # 正常结果：取加权平均，LLM 权重更高，因为它能看到全局上下文。
        blended = llm_confidence * llm_w + upstream_confidence * upstream_w

    if blended != llm_confidence:
        result.self_check.overall_confidence = min(1.0, blended)
        result.self_check.field_mapping_confidence = min(
            1.0,
            result.self_check.field_mapping_confidence * llm_w
            + upstream_confidence * upstream_w,
        )
        if result.computations:
            result.self_check.computation_confidence = min(
                1.0,
                result.self_check.computation_confidence * llm_w
                + upstream_confidence * upstream_w,
            )
        result.parsing_warnings.append("基于前序节点信号与 LLM 自评加权校准置信度")

    return result


def _enrich_clarification_output(
    result: SemanticOutput,
    state: SemanticParserState,
) -> SemanticOutput:
    """在需要澄清时保留已识别的候选字段，避免前序结果丢失。"""
    if not result.needs_clarification:
        return result

    feature_output = _get_feature_output(state)
    required_measures = [
        item.strip()
        for item in (feature_output.required_measures if feature_output else [])
        if isinstance(item, str) and item.strip()
    ]
    required_dimensions = [
        item.strip()
        for item in (feature_output.required_dimensions if feature_output else [])
        if isinstance(item, str) and item.strip()
    ]
    candidates = parse_field_candidates(state.get("field_candidates", []))
    ctx = CandidateMatchContext.from_field_candidates(candidates)
    selected_measure_candidates, unresolved_measures = _resolve_simple_candidates(
        required_measures,
        ctx.measure_candidates,
        ctx.measure_matcher,
        allow_partial=True,
        min_confidence=_CLARIFICATION_CANDIDATE_MIN_CONFIDENCE,
    )
    selected_dimension_candidates, unresolved_dimensions = _resolve_simple_candidates(
        required_dimensions,
        ctx.dimension_candidates,
        ctx.dimension_matcher,
        allow_partial=True,
        min_confidence=_CLARIFICATION_CANDIDATE_MIN_CONFIDENCE,
    )

    enriched = False
    required_measure_keys = {item.lower() for item in required_measures}
    required_dimension_keys = {item.lower() for item in required_dimensions}
    existing_measure_names = [
        measure.field_name.strip()
        for measure in result.what.measures
        if getattr(measure, "field_name", "").strip()
    ]
    existing_dimension_names = [
        dimension.field_name.strip()
        for dimension in result.where.dimensions
        if getattr(dimension, "field_name", "").strip()
    ]

    if required_measures:
        merged_measure_names: list[str] = []
        seen_measure_names: set[str] = set()
        for measure_name in existing_measure_names:
            normalized = measure_name.lower()
            if normalized in required_measure_keys or normalized in seen_measure_names:
                continue
            merged_measure_names.append(measure_name)
            seen_measure_names.add(normalized)
        for candidate in selected_measure_candidates:
            normalized = candidate.field_name.strip().lower()
            if not normalized or normalized in seen_measure_names:
                continue
            merged_measure_names.append(candidate.field_name.strip())
            seen_measure_names.add(normalized)

        should_update_measures = bool(selected_measure_candidates) and (
            not existing_measure_names
            or any(name.lower() in required_measure_keys for name in existing_measure_names)
        )
        if should_update_measures and merged_measure_names:
            result.what = What.model_validate({"measures": merged_measure_names})
            enriched = True
        elif not result.what.measures:
            result.what = What.model_validate(
                {
                    "measures": [
                        {
                            "field_name": measure,
                            "aggregation": _infer_fallback_aggregation(measure).value,
                        }
                        for measure in required_measures
                    ]
                }
            )
            enriched = True

    if required_dimensions:
        merged_dimension_names: list[str] = []
        seen_dimension_names: set[str] = set()
        for dimension_name in existing_dimension_names:
            normalized = dimension_name.lower()
            if normalized in required_dimension_keys or normalized in seen_dimension_names:
                continue
            merged_dimension_names.append(dimension_name)
            seen_dimension_names.add(normalized)
        for candidate in selected_dimension_candidates:
            normalized = candidate.field_name.strip().lower()
            if not normalized or normalized in seen_dimension_names:
                continue
            merged_dimension_names.append(candidate.field_name.strip())
            seen_dimension_names.add(normalized)

        should_update_dimensions = bool(selected_dimension_candidates) and (
            not existing_dimension_names
            or any(
                name.lower() in required_dimension_keys
                for name in existing_dimension_names
            )
        )
        if should_update_dimensions and merged_dimension_names:
            where_payload = result.where.model_dump()
            where_payload["dimensions"] = merged_dimension_names
            result.where = Where.model_validate(where_payload)
            enriched = True
        elif not result.where.dimensions:
            where_payload = result.where.model_dump()
            where_payload["dimensions"] = [
                {"field_name": dimension}
                for dimension in required_dimensions
            ]
            result.where = Where.model_validate(where_payload)
            enriched = True

    # 如果 LLM 已经提供了澄清选项，尝试将其映射到已知候选字段的友好显示名。
    # 避免前端显示技术字段名（如 SUM(Sales)）。
    if result.clarification_options:
        all_candidates = ctx.measure_candidates + ctx.dimension_candidates
        reformatted_options: list[str] = []
        for option in result.clarification_options:
            option_lower = option.strip().lower()
            matched_candidate = next(
                (
                    c for c in all_candidates
                    if c.field_name.strip().lower() == option_lower
                    or (c.field_caption or "").strip().lower() == option_lower
                ),
                None,
            )
            if matched_candidate is not None:
                reformatted_options.append(_format_clarification_option(matched_candidate))
            else:
                reformatted_options.append(option.strip())
        if reformatted_options:
            result.clarification_options = reformatted_options

    if not result.clarification_options:
        clarification_question = None
        clarification_options: list[str] = []
        if unresolved_measures and not unresolved_dimensions:
            clarification_question = _build_clarification_question(
                unresolved_measures[0],
                "度量",
            )
            clarification_options = _collect_clarification_options(
                unresolved_measures,
                ctx.measure_candidates,
                ctx.measure_matcher,
                exclude_field_names={
                    candidate.field_name for candidate in selected_measure_candidates
                },
            )
        elif unresolved_dimensions and not unresolved_measures:
            if _should_use_missing_dimension_question(
                [unresolved_dimensions[0]],
                ctx.dimension_candidates,
                ctx.lexicon,
            ):
                clarification_question = _build_missing_dimension_question(
                    unresolved_dimensions[0],
                )
            else:
                clarification_question = _build_clarification_question(
                    unresolved_dimensions[0],
                    "维度",
                )
            clarification_options = _collect_clarification_options(
                unresolved_dimensions,
                ctx.dimension_candidates,
                ctx.dimension_matcher,
                exclude_field_names={
                    candidate.field_name for candidate in selected_dimension_candidates
                },
                fallback_scorer=lambda required_terms, candidate: (
                    _score_dimension_fallback_candidate(required_terms, candidate, ctx.lexicon)
                ),
            )

        if clarification_options:
            result.clarification_options = clarification_options
            if not result.clarification_question:
                result.clarification_question = clarification_question
            enriched = True

    if enriched:
        result.parsing_warnings.append(
            "语义理解请求澄清，已将可确定字段收敛为真实候选字段并补齐澄清选项"
        )

    return result

async def semantic_understanding_node(
    state: SemanticParserState,
    config: Optional[RunnableConfig] = None,
) -> dict[str, Any]:
    """语义理解节点

    使用 modular_prompt_builder_node 构建的 Prompt 调用 LLM 进行语义理解。

    输入：
    - state["question"]: 用户问题
    - state["modular_prompt"]: 由 modular_prompt_builder_node 构建的 Prompt
    - state["chat_history"]: 对话历史（可选）

    输出：
    - semantic_output: SemanticOutput 序列化后的 dict
    - needs_clarification: 是否需要澄清
    - clarification_question: 澄清问题
    - clarification_options: 澄清选项
    - clarification_source: 澄清来源
    - thinking: LLM 思考过程
    """
    start_time = time.time()
    logger.info("=" * 60)
    logger.info("[semantic_understanding_node] 开始执行")
    question = state.get("question", "")
    logger.info(f"[semantic_understanding_node] 问题: {question}")

    if not question:
        logger.warning("semantic_understanding_node: 问题为空")
        return {
            "needs_clarification": True,
            "clarification_question": "请输入您的问题",
            "clarification_source": ClarificationSource.SEMANTIC_UNDERSTANDING.value,
        }

    # 获取 modular_prompt_builder_node 构建的 Prompt
    modular_prompt = state.get("modular_prompt")
    planner_requires_reasoning = _analysis_plan_requires_reasoning(state)
    using_fast_model = False
    is_reasoning_model = False
    thinking = None

    if not modular_prompt:
        # 降级：modular_prompt 缺失，就地构建 Prompt 并尽量传递所有可用的上游信息
        logger.warning(
            "semantic_understanding_node: 未找到 modular_prompt，使用降级模式"
        )
        field_candidates_raw = state.get("field_candidates", [])
        field_candidates = [
            FieldCandidate.model_validate(c) for c in field_candidates_raw
        ]

        few_shot_examples_raw = state.get("few_shot_examples", [])
        few_shot_examples = [
            FewShotExample.model_validate(e) for e in few_shot_examples_raw
        ] if few_shot_examples_raw else None

        history = state.get("chat_history")

        current_time_str = state.get("current_time")
        current_date = None
        if current_time_str:
            try:
                current_date = datetime.fromisoformat(current_time_str).date()
            except (ValueError, TypeError):
                pass

        semantic_config = SemanticConfig(current_date=current_date or datetime.now().date())

        prefilter_result = _get_prefilter_result(state)
        feature_output = _get_feature_output(state)

        analysis_plan = parse_analysis_plan(
            raw_analysis_plan=state.get("analysis_plan"),
            raw_global_understanding=state.get("global_understanding"),
        )
        current_step_intent = parse_step_intent(state.get("current_step_intent"))
        evidence_context_raw = state.get("evidence_context")
        evidence_context = (
            EvidenceContext.model_validate(evidence_context_raw)
            if evidence_context_raw else None
        )

        dynamic_schema_result_raw = state.get("dynamic_schema_result")
        schema_text = ""
        detected_complexity = [ComplexityType.SIMPLE]
        allowed_calc_types: list[str] = []
        if dynamic_schema_result_raw:
            schema_text = dynamic_schema_result_raw.get("schema_text", "")
            detected_complexity = [
                ComplexityType(c)
                for c in dynamic_schema_result_raw.get("detected_complexity", ["simple"])
            ]
            allowed_calc_types = dynamic_schema_result_raw.get("allowed_calc_types", [])

        prompt_builder = DynamicPromptBuilder()
        modular_prompt = prompt_builder.build(
            question=question,
            config=semantic_config,
            field_candidates=field_candidates,
            schema_json=schema_text,
            detected_complexity=detected_complexity,
            allowed_calc_types=allowed_calc_types,
            history=history,
            few_shot_examples=few_shot_examples,
            prefilter_result=prefilter_result,
            feature_output=feature_output,
            analysis_plan=analysis_plan,
            current_step_intent=current_step_intent,
            evidence_context=evidence_context,
        )

        logger.info(
            "semantic_understanding_node: 降级模式 Prompt 已构建, "
            f"prompt_length={len(modular_prompt)}"
        )

        llm = get_llm(agent_name="semantic_parser", enable_json_mode=True)
        messages = [HumanMessage(content=modular_prompt)]

        result, thinking = await stream_llm_structured(
            llm=llm,
            messages=messages,
            output_model=SemanticOutput,
            on_token=None,
            on_thinking=None,
            return_thinking=True,
        )
    else:
        # 正常流程：直接使用 modular_prompt 调用 LLM
        logger.info(
            f"semantic_understanding_node: 使用 modular_prompt, "
            f"prompt_length={len(modular_prompt)}"
        )

        # 复杂查询使用 ComplexSemanticOutput，让 LLM 同时输出全局理解字段
        use_complex_output = planner_requires_reasoning
        output_model = ComplexSemanticOutput if use_complex_output else SemanticOutput

        logger.info("[semantic_understanding_node] 获取 LLM...")
        llm, using_fast_model = _get_semantic_llm(state, modular_prompt)
        is_reasoning_model = bool(getattr(llm, "_is_reasoning_model", False))
        logger.info(
            "[semantic_understanding_node] 模型已选择: "
            f"model={getattr(llm, 'model_name', 'unknown')}, "
            f"fast_model={using_fast_model}, "
            f"reasoning_model={is_reasoning_model}, "
            f"complex_output={use_complex_output}"
        )

        messages = [HumanMessage(content=modular_prompt)]

        on_token = None
        on_thinking = None
        if config:
            configurable = config.get("configurable", {})
            on_token = configurable.get("on_token")
            on_thinking = configurable.get("on_thinking")

        logger.info("[semantic_understanding_node] 调用 LLM...")
        try:
            result, thinking = await stream_llm_structured(
                llm=llm,
                messages=messages,
                output_model=output_model,
                on_token=None,        # 不向前端发送 JSON token（结构化输出不应显示给用户）
                on_thinking=on_thinking,
                return_thinking=True,
            )
            logger.info("[semantic_understanding_node] LLM 调用完成")
        except Exception as e:
            if using_fast_model:
                global _fast_semantic_model_available, _fast_semantic_model_unavailable_since
                with _fast_model_lock:
                    _fast_semantic_model_available = False
                    _fast_semantic_model_unavailable_since = time.time()
                logger.warning(
                    "[semantic_understanding_node] 快模型调用失败，回退默认模型 (TTL=%ds): %s",
                    _FAST_MODEL_RETRY_TTL_SECONDS,
                    e,
                )
                llm = get_llm(
                    agent_name="semantic_parser",
                    enable_json_mode=True,
                )
                using_fast_model = False
                is_reasoning_model = bool(getattr(llm, "_is_reasoning_model", False))
                result, thinking = await stream_llm_structured(
                    llm=llm,
                    messages=messages,
                    output_model=output_model,
                    on_token=None,
                    on_thinking=on_thinking,
                    return_thinking=True,
                )
                logger.info("[semantic_understanding_node] 默认模型回退完成")
            else:
                logger.exception(f"[semantic_understanding_node] LLM 调用失败: {e}")
                raise

    # ── 提取复杂查询的全局理解字段 ──────────────────────────────────────
    complex_global_fields: Optional[dict[str, Any]] = None
    if isinstance(result, ComplexSemanticOutput):
        complex_global_fields = {
            "analysis_mode": result.analysis_mode.value,
            "single_query_feasible": result.single_query_feasible,
            "decomposition_reason": result.decomposition_reason,
            "risk_flags": result.risk_flags,
            "llm_confidence": result.self_check.overall_confidence,
        }
        logger.info(
            "semantic_understanding_node: complex output extracted, "
            "analysis_mode=%s, single_query_feasible=%s",
            result.analysis_mode.value,
            result.single_query_feasible,
        )

    result = _post_process_semantic_output(result)
    result = _backfill_computations(result, state)

    if result.needs_clarification:
        result.clarification_source = ClarificationSource.SEMANTIC_UNDERSTANDING
        result = _enrich_clarification_output(result, state)

    result = _backfill_top_n_filter(result, state)
    result = _backfill_confidence_from_signals(result, state)

    logger.info(
        f"semantic_understanding_node: query_id={result.query_id}, "
        f"needs_clarification={result.needs_clarification}"
    )

    # ── 构建输出 ──────────────────────────────────────────────────────────
    # 存储 semantic_output 时排除 ComplexSemanticOutput 的额外字段，
    # 确保下游 SemanticOutput.model_validate() 不会因 extra="forbid" 报错
    _complex_extra_fields = {"analysis_mode", "single_query_feasible", "decomposition_reason", "risk_flags"}
    semantic_output_dump = result.model_dump(exclude=_complex_extra_fields)

    output = {
        "semantic_output": semantic_output_dump,
        "needs_clarification": result.needs_clarification,
        "thinking": thinking if thinking else None,
    }

    if result.needs_clarification:
        output["clarification_question"] = result.clarification_question
        output["clarification_options"] = result.clarification_options
        output["clarification_source"] = (
            result.clarification_source.value
            if result.clarification_source
            else ClarificationSource.SEMANTIC_UNDERSTANDING.value
        )

    # 复杂查询：用 LLM 的全局理解判断更新 state 中的 global_understanding
    if complex_global_fields:
        existing_global = state.get("global_understanding") or {}
        output["global_understanding"] = {
            **existing_global,
            **complex_global_fields,
            "primary_restated_question": result.restated_question,
        }

        # LLM 判断单查可行时，覆盖规则 plan 的 needs_planning，
        # 防止 executor 错误地执行多步
        llm_mode = complex_global_fields["analysis_mode"]
        llm_feasible = complex_global_fields["single_query_feasible"]
        if llm_feasible and llm_mode in ("single_query", "complex_single_query"):
            existing_plan = state.get("analysis_plan") or {}
            output["analysis_plan"] = {
                **existing_plan,
                "needs_planning": False,
                "plan_mode": "direct_query",
                "single_query_feasible": True,
                "requires_llm_reasoning": False,
                "decomposition_reason": complex_global_fields.get("decomposition_reason"),
            }
            logger.info(
                "semantic_understanding_node: LLM 判断单查可行 (mode=%s)，"
                "覆盖规则 plan needs_planning=False",
                llm_mode,
            )

    elapsed_ms = (time.time() - start_time) * 1000
    output["optimization_metrics"] = merge_metrics(
        state,
        semantic_understanding_ms=elapsed_ms,
        semantic_understanding_fast_model=using_fast_model,
        semantic_understanding_reasoning_model=is_reasoning_model,
        semantic_understanding_planner_forced_llm=planner_requires_reasoning,
        semantic_understanding_complex_output=complex_global_fields is not None,
    )

    logger.info("[semantic_understanding_node] 执行完成")
    logger.info("=" * 60)

    return output
