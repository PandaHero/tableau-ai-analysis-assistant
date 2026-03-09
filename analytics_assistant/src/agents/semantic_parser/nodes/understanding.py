# -*- coding: utf-8 -*-
"""语义理解节点"""
import logging
import re
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
from ..components.semantic_lexicon_builder import (
    SemanticLexicon,
    SemanticLexiconBuilder,
    collect_seed_hint_terms,
    expand_hint_variants,
    get_default_semantic_lexicon,
)
from ..components.semantic_understanding import (
    SemanticUnderstanding,
    get_low_confidence_threshold,
    get_simple_query_model_id,
)
from ..schemas.output import (
    ClarificationSource,
    DerivedComputation,
    SemanticOutput,
    SelfCheck,
    What,
    Where,
)
from ..schemas.planner import PlanMode, StepIntent, parse_analysis_plan, parse_step_intent
from ..schemas.prefilter import ComplexityType, FeatureExtractionOutput, PrefilterResult
from ..schemas.intermediate import FieldCandidate, FewShotExample

logger = logging.getLogger(__name__)

_FAST_SEMANTIC_MIN_CONFIDENCE = 0.75
_FAST_SEMANTIC_MAX_PROMPT_LENGTH = 2600
_SIMPLE_SHORTCUT_MIN_CONFIDENCE = 0.85
_CLARIFICATION_CANDIDATE_MIN_CONFIDENCE = 0.5
_fast_semantic_model_available: Optional[bool] = None
_SEMANTIC_LEXICON_BUILDER = SemanticLexiconBuilder()

_TOP_N_PATTERNS: tuple[tuple[re.Pattern[str], SortDirection], ...] = (
    (re.compile(r"(?:前|top)\s*(\d+)", re.IGNORECASE), SortDirection.DESC),
    (re.compile(r"(?:后|bottom)\s*(\d+)", re.IGNORECASE), SortDirection.ASC),
    (re.compile(r"最高(?:的)?\s*(\d+)", re.IGNORECASE), SortDirection.DESC),
    (re.compile(r"最低(?:的)?\s*(\d+)", re.IGNORECASE), SortDirection.ASC),
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
    count_hints = ("count", "数量", "数", "个数", "次数", "笔数")
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
    global _fast_semantic_model_available
    use_fast_model = _should_use_fast_semantic_model(state, modular_prompt)
    simple_query_model_id = get_simple_query_model_id()
    if use_fast_model and _fast_semantic_model_available is not False:
        try:
            llm = get_llm(
                agent_name="semantic_parser",
                model_id=simple_query_model_id,
                enable_json_mode=True,
            )
            _fast_semantic_model_available = True
            return llm, True
        except Exception as exc:
            _fast_semantic_model_available = False
            logger.warning(
                "semantic_understanding_node: 快模型不可用，回退默认模型: %s",
                exc,
            )

    llm = get_llm(
        agent_name="semantic_parser",
        enable_json_mode=True,
    )
    return llm, False


def _field_display_name(field: FieldCandidate) -> str:
    return field.field_caption or field.field_name


def _normalize_match_text(text: str) -> str:
    normalized = re.sub(r"[_\-/]+", " ", text.strip().lower())
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def _compact_match_text(text: str) -> str:
    return _normalize_match_text(text).replace(" ", "")


def _text_matches(text: str, candidate_text: str) -> bool:
    normalized_text = _normalize_match_text(text)
    normalized_candidate = _normalize_match_text(candidate_text)
    if not normalized_text or not normalized_candidate:
        return False
    if normalized_text in normalized_candidate:
        return True
    return _compact_match_text(normalized_text) in _compact_match_text(normalized_candidate)


def _normalize_required_terms(required_terms: list[str]) -> list[str]:
    normalized_terms: list[str] = []
    seen_terms: set[str] = set()
    for term in required_terms:
        normalized = term.strip()
        if not normalized:
            continue
        key = _normalize_match_text(normalized)
        if key in seen_terms:
            continue
        seen_terms.add(key)
        normalized_terms.append(normalized)
    return normalized_terms


def _format_clarification_option(field: FieldCandidate) -> str:
    """将候选字段格式化为更适合展示给用户的澄清选项。"""
    technical_name = field.field_name.strip()
    display_name = _field_display_name(field).strip() or technical_name
    aliases = [
        alias.strip()
        for alias in (field.aliases or [])
        if alias and alias.strip()
    ]
    alias = next(
        (
            item
            for item in aliases
            if item.lower() not in {display_name.lower(), technical_name.lower()}
        ),
        "",
    )

    primary_label = display_name or technical_name
    details: list[str] = []
    if alias and primary_label.lower() == technical_name.lower():
        primary_label = alias
        if technical_name and technical_name.lower() != primary_label.lower():
            details.append(technical_name)
    else:
        if alias:
            details.append(alias)
        if technical_name and technical_name.lower() != primary_label.lower():
            details.append(technical_name)

    logical_table = (field.logical_table_caption or "").strip()
    detail_keys = {primary_label.lower()}
    detail_keys.update(item.lower() for item in details)
    if logical_table and logical_table.lower() not in detail_keys:
        details.append(f"表:{logical_table}")

    if details:
        return f"{primary_label} ({', '.join(details[:2])})"
    return primary_label


def _candidate_search_text(field: FieldCandidate) -> str:
    parts = [
        field.field_name,
        field.field_caption,
        field.business_description or "",
        " ".join(field.aliases or []),
    ]
    return _normalize_match_text(" ".join(part for part in parts if part))


def _candidate_identifier_text(field: FieldCandidate) -> str:
    parts = [
        field.field_name,
        field.field_caption,
        " ".join(field.aliases or []),
    ]
    return _normalize_match_text(" ".join(part for part in parts if part))


def _candidate_identifier_terms(field: FieldCandidate) -> set[str]:
    terms = collect_seed_hint_terms(
        field.field_name,
        field.field_caption,
        field.aliases or [],
    )
    expanded_terms: set[str] = set()
    for term in terms:
        expanded_terms.update(expand_hint_variants(term))
    return expanded_terms


def _candidate_identifier_hint_text(field: FieldCandidate) -> str:
    return " ".join(sorted(_candidate_identifier_terms(field)))


def _build_runtime_semantic_lexicon(
    field_candidates: list[FieldCandidate],
) -> SemanticLexicon:
    """为当前字段候选集合构建运行时语义词典。"""
    if not field_candidates:
        return get_default_semantic_lexicon()
    return _SEMANTIC_LEXICON_BUILDER.build(field_candidates=field_candidates)


def _measure_term_categories(
    term: str,
    lexicon: Optional[SemanticLexicon] = None,
) -> list[str]:
    term_lower = _normalize_match_text(term)
    if not term_lower:
        return []
    lexicon = lexicon or get_default_semantic_lexicon()
    return [
        category
        for category, hints in lexicon.measure_category_hints.items()
        if any(_text_matches(hint, term_lower) for hint in hints)
    ]


def _measure_placeholder_hints(
    placeholder: str,
    lexicon: Optional[SemanticLexicon] = None,
) -> set[str]:
    lexicon = lexicon or get_default_semantic_lexicon()
    hints = set(lexicon.measure_placeholder_hints.get(placeholder, {placeholder}))
    for raw_hint in list(hints):
        hints.update(expand_hint_variants(raw_hint))
    return {hint for hint in hints if hint}


def _measure_identifier_hints(
    category: str,
    lexicon: Optional[SemanticLexicon] = None,
) -> set[str]:
    lexicon = lexicon or get_default_semantic_lexicon()
    return set(lexicon.measure_identifier_hints.get(category, set()))


def _measure_candidate_matches_category(
    field: FieldCandidate,
    category: str,
    lexicon: Optional[SemanticLexicon] = None,
) -> bool:
    candidate_category = _normalize_match_text(field.measure_category or "")
    if candidate_category == category:
        return True

    identifier_hint_text = _candidate_identifier_hint_text(field)
    if not identifier_hint_text:
        return False

    return any(
        _text_matches(hint, identifier_hint_text)
        for hint in _measure_identifier_hints(category, lexicon)
    )


def _measure_name_matches_placeholder(
    name: str,
    placeholder: str,
    lexicon: Optional[SemanticLexicon] = None,
) -> bool:
    normalized_name = _normalize_match_text(name)
    if not normalized_name:
        return False
    return any(
        _text_matches(hint, normalized_name)
        for hint in _measure_placeholder_hints(placeholder, lexicon)
    )


def _infer_dimension_preferences(
    required_terms: list[str],
    lexicon: Optional[SemanticLexicon] = None,
) -> tuple[set[str], list[int]]:
    lexicon = lexicon or get_default_semantic_lexicon()
    preferred_categories: set[str] = set()
    preferred_levels: list[int] = []
    for term in _normalize_required_terms(required_terms):
        normalized_term = _normalize_match_text(term)
        if not normalized_term:
            continue
        for category, hints in lexicon.dimension_category_hints.items():
            if any(_text_matches(hint, normalized_term) for hint in hints):
                preferred_categories.add(category)
        for hints, level in lexicon.dimension_level_hints:
            if any(_text_matches(hint, normalized_term) for hint in hints):
                preferred_levels.append(level)
                break
    return preferred_categories, preferred_levels


def _dimension_term_preferences(
    term: str,
    lexicon: Optional[SemanticLexicon] = None,
) -> tuple[set[str], list[int]]:
    return _infer_dimension_preferences([term], lexicon)


def _get_dimension_candidate_category(field: FieldCandidate) -> str:
    category = (
        field.hierarchy_category
        or field.category
        or ""
    )
    return _normalize_match_text(str(category))


def _get_dimension_candidate_level(field: FieldCandidate) -> Optional[int]:
    return field.hierarchy_level or field.level


def _dimension_candidate_matches_preferences(
    field: FieldCandidate,
    *,
    preferred_categories: set[str],
    preferred_levels: list[int],
) -> bool:
    candidate_category = _get_dimension_candidate_category(field)
    candidate_level = _get_dimension_candidate_level(field)

    if preferred_categories:
        if candidate_category not in preferred_categories:
            return False

        # 如果用户问题已经隐含了明确层级（省份/部门/城市等），
        # 只有层级足够接近时才允许仅靠 semantic metadata 直接命中，
        # 避免把“部门”误吸附到“销售员/渠道经理”等更细粒度字段。
        if preferred_levels:
            if candidate_level is None:
                return False
            closest_gap = min(abs(candidate_level - level) for level in preferred_levels)
            return closest_gap <= 1

        return True

    if preferred_levels:
        if candidate_level is None:
            return False
        closest_gap = min(abs(candidate_level - level) for level in preferred_levels)
        return closest_gap <= 1

    return False


def _score_dimension_fallback_candidate(
    required_terms: list[str],
    field: FieldCandidate,
    lexicon: Optional[SemanticLexicon] = None,
) -> float:
    score = field.confidence
    preferred_categories, preferred_levels = _infer_dimension_preferences(
        required_terms,
        lexicon,
    )
    candidate_category = _get_dimension_candidate_category(field)
    candidate_level = _get_dimension_candidate_level(field)

    if preferred_categories:
        if candidate_category in preferred_categories:
            score += 0.25
        elif candidate_category == "time":
            score -= 0.25
        else:
            score -= 0.05

    if preferred_levels and candidate_level is not None:
        closest_gap = min(abs(candidate_level - level) for level in preferred_levels)
        score += max(0.0, 0.12 - 0.04 * closest_gap)

    if field.sample_values:
        score += 0.02

    return score


def _build_missing_dimension_question(term: str) -> str:
    normalized = term.strip()
    if normalized:
        return f"当前候选中没有明显对应“{normalized}”的维度字段。以下哪个字段最接近你的分析意图？"
    return "当前候选中没有明显对应的维度字段。以下哪个字段最接近你的分析意图？"


def _should_use_missing_dimension_question(
    required_terms: list[str],
    candidates: list[FieldCandidate],
    lexicon: Optional[SemanticLexicon] = None,
) -> bool:
    preferred_categories, _ = _infer_dimension_preferences(required_terms, lexicon)
    if not preferred_categories:
        return False
    return not any(
        _get_dimension_candidate_category(candidate) in preferred_categories
        for candidate in candidates
    )


def _measure_term_matches_candidate(
    term: str,
    field: FieldCandidate,
    lexicon: Optional[SemanticLexicon] = None,
) -> bool:
    term_lower = _normalize_match_text(term)
    if not term_lower:
        return False

    searchable_text = _candidate_search_text(field)
    if _text_matches(term_lower, searchable_text):
        return True

    matched_categories = _measure_term_categories(term_lower, lexicon)
    if not matched_categories:
        return False

    # “销售数量 / 订单数量”这类词同时带有通用销售词和更具体的数量信号，
    # 优先按数量/计数解释，避免误吸到 revenue 候选。
    category_priority = ["quantity", "count", "profit", "cost", "revenue"]
    for category in category_priority:
        if category not in matched_categories:
            continue
        if _measure_candidate_matches_category(field, category, lexicon):
            return True

        if category in {"quantity", "count"}:
            return False

    return False


def _dimension_term_matches_candidate(
    term: str,
    field: FieldCandidate,
    lexicon: Optional[SemanticLexicon] = None,
) -> bool:
    term_lower = _normalize_match_text(term)
    if not term_lower:
        return False
    if _text_matches(term_lower, _candidate_search_text(field)):
        return True

    preferred_categories, preferred_levels = _dimension_term_preferences(term_lower, lexicon)
    if not preferred_categories and not preferred_levels:
        return False

    return _dimension_candidate_matches_preferences(
        field,
        preferred_categories=preferred_categories,
        preferred_levels=preferred_levels,
    )


def _score_simple_candidate(
    term: str,
    field: FieldCandidate,
    matcher,
    *,
    min_confidence: float = _SIMPLE_SHORTCUT_MIN_CONFIDENCE,
) -> Optional[float]:
    """为简单查询快捷路径计算候选字段分数。"""
    if field.confidence < min_confidence:
        return None
    if not matcher(term, field):
        return None

    score = field.confidence
    searchable_text = _candidate_search_text(field)
    if _text_matches(term, searchable_text):
        score += 0.1
    if field.match_type == "exact":
        score += 0.05
    return score


def _resolve_simple_candidates(
    required_terms: list[str],
    candidates: list[FieldCandidate],
    matcher,
    *,
    allow_partial: bool = False,
    min_confidence: float = _SIMPLE_SHORTCUT_MIN_CONFIDENCE,
) -> tuple[list[FieldCandidate], list[str]]:
    """按需求词顺序解析简单查询候选，可选择保留未解析项。"""
    selected: list[FieldCandidate] = []
    unresolved: list[str] = []
    used_field_names: set[str] = set()

    for term in _normalize_required_terms(required_terms):
        # 同义词命中时复用已选字段，避免将一个业务字段误判为多个需求。
        if any(matcher(term, candidate) for candidate in selected):
            continue

        best_candidate: Optional[FieldCandidate] = None
        best_score = -1.0
        for candidate in candidates:
            if candidate.field_name in used_field_names:
                continue
            score = _score_simple_candidate(
                term,
                candidate,
                matcher,
                min_confidence=min_confidence,
            )
            if score is None:
                continue
            if score > best_score:
                best_candidate = candidate
                best_score = score

        if best_candidate is None:
            unresolved.append(term)
            if not allow_partial:
                return [], unresolved
            continue

        selected.append(best_candidate)
        used_field_names.add(best_candidate.field_name)

    return selected, unresolved


def _select_simple_candidates(
    required_terms: list[str],
    candidates: list[FieldCandidate],
    matcher,
) -> Optional[list[FieldCandidate]]:
    selected, unresolved = _resolve_simple_candidates(
        required_terms,
        candidates,
        matcher,
    )
    if unresolved:
        return None
    return selected


def _build_clarification_question(term: str, role_label: str) -> str:
    normalized = term.strip()
    if normalized:
        return f"“{normalized}”具体对应哪个{role_label}字段？"
    return f"请确认你想使用哪个{role_label}字段？"


def _collect_clarification_options(
    required_terms: list[str],
    candidates: list[FieldCandidate],
    matcher,
    *,
    limit: int = 3,
    exclude_field_names: Optional[set[str]] = None,
    min_confidence: float = _CLARIFICATION_CANDIDATE_MIN_CONFIDENCE,
    fallback_scorer=None,
) -> list[str]:
    """为规则澄清构造候选选项。"""
    exclude_field_names = exclude_field_names or set()
    matched_scored: list[tuple[float, FieldCandidate]] = []
    fallback_scored: list[tuple[float, FieldCandidate]] = []

    for candidate in candidates:
        if candidate.field_name in exclude_field_names:
            continue

        best_score: Optional[float] = None
        for term in _normalize_required_terms(required_terms):
            score = _score_simple_candidate(
                term,
                candidate,
                matcher,
                min_confidence=min_confidence,
            )
            if score is not None:
                best_score = max(best_score or score, score)

        if best_score is not None:
            matched_scored.append((best_score, candidate))
        else:
            score = (
                fallback_scorer(required_terms, candidate)
                if fallback_scorer is not None
                else candidate.confidence
            )
            fallback_scored.append((score, candidate))

    ranked_candidates = matched_scored or fallback_scored
    options: list[str] = []
    for _, candidate in sorted(
        ranked_candidates,
        key=lambda item: item[0],
        reverse=True,
    ):
        option = _format_clarification_option(candidate)
        if not option or option in options:
            continue
        options.append(option)
        if len(options) >= limit:
            break
    return options


def _try_build_simple_clarification_output(
    state: SemanticParserState,
    question: str,
) -> Optional[SemanticOutput]:
    """对简单但字段映射不明确的请求直接生成澄清输出。"""
    if _step_intent_requires_reasoning(state):
        return None
    prefilter_result = _get_prefilter_result(state)
    feature_output = _get_feature_output(state)
    if prefilter_result is None or feature_output is None:
        return None
    if prefilter_result.detected_complexity != [ComplexityType.SIMPLE]:
        return None
    if prefilter_result.time_hints or prefilter_result.matched_computations:
        return None
    if feature_output.is_degraded or feature_output.confirmed_computations:
        return None
    if feature_output.confirmation_confidence < _SIMPLE_SHORTCUT_MIN_CONFIDENCE:
        return None

    candidates = parse_field_candidates(state.get("field_candidates", []))
    measure_candidates = [
        candidate for candidate in candidates if candidate.role.lower() == "measure"
    ]
    dimension_candidates = [
        candidate for candidate in candidates if candidate.role.lower() == "dimension"
    ]
    lexicon = _build_runtime_semantic_lexicon(candidates)
    measure_matcher = (
        lambda term, candidate: _measure_term_matches_candidate(term, candidate, lexicon)
    )
    dimension_matcher = (
        lambda term, candidate: _dimension_term_matches_candidate(term, candidate, lexicon)
    )

    selected_measures, unresolved_measures = _resolve_simple_candidates(
        feature_output.required_measures,
        measure_candidates,
        measure_matcher,
        allow_partial=True,
        min_confidence=_CLARIFICATION_CANDIDATE_MIN_CONFIDENCE,
    )
    selected_dimensions, unresolved_dimensions = _resolve_simple_candidates(
        feature_output.required_dimensions,
        dimension_candidates,
        dimension_matcher,
        allow_partial=True,
        min_confidence=_CLARIFICATION_CANDIDATE_MIN_CONFIDENCE,
    )

    clarification_question = None
    clarification_options: list[str] = []

    if unresolved_measures:
        clarification_question = _build_clarification_question(
            unresolved_measures[0],
            "度量",
        )
        clarification_options = _collect_clarification_options(
            unresolved_measures,
            measure_candidates,
            measure_matcher,
            exclude_field_names={candidate.field_name for candidate in selected_measures},
        )
    elif unresolved_dimensions:
        if _should_use_missing_dimension_question(
            [unresolved_dimensions[0]],
            dimension_candidates,
            lexicon,
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
            dimension_candidates,
            dimension_matcher,
            exclude_field_names={
                candidate.field_name for candidate in selected_dimensions
            },
            fallback_scorer=lambda required_terms, candidate: (
                _score_dimension_fallback_candidate(required_terms, candidate, lexicon)
            ),
        )

    if not clarification_question or not clarification_options:
        return None

    return SemanticOutput(
        restated_question=question,
        what=What(measures=[candidate.field_name for candidate in selected_measures]),
        where=Where(
            dimensions=[candidate.field_name for candidate in selected_dimensions]
        ),
        how_type=HowType.SIMPLE,
        computations=[],
        needs_clarification=True,
        clarification_question=clarification_question,
        clarification_options=clarification_options,
        self_check=SelfCheck(
            field_mapping_confidence=0.55,
            time_range_confidence=1.0,
            computation_confidence=1.0,
            overall_confidence=0.55,
        ),
        parsing_warnings=["基于简单查询候选直接生成澄清问题"],
    )


def _try_build_simple_semantic_output(
    state: SemanticParserState,
    question: str,
) -> Optional[SemanticOutput]:
    """对高置信度简单查询直接构造语义输出，跳过 LLM。"""
    if _step_intent_requires_reasoning(state):
        return None
    prefilter_result = _get_prefilter_result(state)
    feature_output = _get_feature_output(state)
    if prefilter_result is None or feature_output is None:
        return None
    if prefilter_result.detected_complexity != [ComplexityType.SIMPLE]:
        return None
    if prefilter_result.time_hints or prefilter_result.matched_computations:
        return None
    if feature_output.is_degraded or feature_output.confirmed_computations:
        return None
    if feature_output.confirmation_confidence < _SIMPLE_SHORTCUT_MIN_CONFIDENCE:
        return None
    if state.get("few_shot_examples"):
        return None

    candidates = parse_field_candidates(state.get("field_candidates", []))
    measure_candidates = [
        candidate
        for candidate in candidates
        if candidate.role.lower() == "measure"
    ]
    dimension_candidates = [
        candidate
        for candidate in candidates
        if candidate.role.lower() == "dimension"
    ]
    lexicon = _build_runtime_semantic_lexicon(candidates)
    measure_matcher = (
        lambda term, candidate: _measure_term_matches_candidate(term, candidate, lexicon)
    )
    dimension_matcher = (
        lambda term, candidate: _dimension_term_matches_candidate(term, candidate, lexicon)
    )

    selected_measures = _select_simple_candidates(
        feature_output.required_measures,
        measure_candidates,
        measure_matcher,
    )
    if not selected_measures:
        return None

    selected_dimensions = _select_simple_candidates(
        feature_output.required_dimensions,
        dimension_candidates,
        dimension_matcher,
    )
    if feature_output.required_dimensions and not selected_dimensions:
        return None

    overall_confidence = min(1.0, max(0.9, feature_output.confirmation_confidence))
    return SemanticOutput(
        restated_question=question,
        what=What(measures=[candidate.field_name for candidate in selected_measures]),
        where=Where(
            dimensions=[
                candidate.field_name
                for candidate in (selected_dimensions or [])
            ]
        ),
        how_type=HowType.SIMPLE,
        computations=[],
        needs_clarification=False,
        self_check=SelfCheck(
            field_mapping_confidence=overall_confidence,
            time_range_confidence=1.0,
            computation_confidence=1.0,
            overall_confidence=overall_confidence,
        ),
        parsing_warnings=["基于简单查询高置信度候选直接生成语义输出"],
    )


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


def _matches_measure_placeholder(
    field: FieldCandidate,
    placeholder: str,
    lexicon: Optional[SemanticLexicon] = None,
) -> bool:
    placeholder_hints = _measure_placeholder_hints(placeholder, lexicon)
    category = _normalize_match_text(field.measure_category or "")
    if category and category in placeholder_hints:
        return True

    searchable_parts = [
        field.field_name,
        field.field_caption,
        " ".join(field.aliases or []),
    ]
    searchable_text = _normalize_match_text(
        " ".join(part for part in searchable_parts if part)
    )
    if any(_text_matches(hint, searchable_text) for hint in placeholder_hints):
        return True

    # 业务描述只作为兜底语义，不参与主类别判断，避免被通用词误吸附。
    business_description = _normalize_match_text(field.business_description or "")
    return bool(business_description) and any(
        _text_matches(hint, business_description)
        for hint in placeholder_hints
    )


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

        for idx, candidate in enumerate(measure_candidates):
            if idx in used_candidates:
                continue
            mapping[placeholder] = _field_display_name(candidate)
            used_candidates.add(idx)
            matched = True
            break

        if not matched and measure_names:
            fallback_index = min(len(mapping), len(measure_names) - 1)
            mapping[placeholder] = measure_names[fallback_index]

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

    seeds_by_name = {seed.name: seed for seed in COMPUTATION_SEEDS}
    seeds_by_name.update({seed.display_name: seed for seed in COMPUTATION_SEEDS})
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
            return int(match.group(1)), direction
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
    confidence_floor = max(
        getattr(feature_output, "confirmation_confidence", 0.0) if feature_output else 0.0,
        getattr(prefilter_result, "match_confidence", 0.0) if prefilter_result else 0.0,
    )
    if confidence_floor <= 0:
        return result

    has_structured_signal = bool(
        result.what.measures
        or result.where.dimensions
        or result.where.filters
        or result.computations
    )
    if not has_structured_signal:
        return result

    if not result.needs_clarification and confidence_floor < get_low_confidence_threshold():
        return result

    if confidence_floor > result.self_check.overall_confidence:
        result.self_check.overall_confidence = min(1.0, confidence_floor)
        result.self_check.field_mapping_confidence = max(
            result.self_check.field_mapping_confidence,
            min(1.0, confidence_floor),
        )
        if result.computations:
            result.self_check.computation_confidence = max(
                result.self_check.computation_confidence,
                min(1.0, confidence_floor),
            )
        result.parsing_warnings.append("基于前序节点信号校准 self_check 置信度")

    return result


def _enrich_clarification_output(
    result: SemanticOutput,
    state: SemanticParserState,
) -> SemanticOutput:
    """在需要澄清时保留已识别的候选字段，避免前序结果丢失。"""
    if not result.needs_clarification:
        return result

    feature_output = state.get("feature_extraction_output") or {}
    required_measures = [
        item.strip()
        for item in feature_output.get("required_measures", [])
        if isinstance(item, str) and item.strip()
    ]
    required_dimensions = [
        item.strip()
        for item in feature_output.get("required_dimensions", [])
        if isinstance(item, str) and item.strip()
    ]
    candidates = parse_field_candidates(state.get("field_candidates", []))
    measure_candidates = [
        candidate for candidate in candidates if candidate.role.lower() == "measure"
    ]
    dimension_candidates = [
        candidate for candidate in candidates if candidate.role.lower() == "dimension"
    ]
    lexicon = _build_runtime_semantic_lexicon(candidates)
    measure_matcher = (
        lambda term, candidate: _measure_term_matches_candidate(term, candidate, lexicon)
    )
    dimension_matcher = (
        lambda term, candidate: _dimension_term_matches_candidate(term, candidate, lexicon)
    )
    selected_measure_candidates, unresolved_measures = _resolve_simple_candidates(
        required_measures,
        measure_candidates,
        measure_matcher,
        allow_partial=True,
        min_confidence=_CLARIFICATION_CANDIDATE_MIN_CONFIDENCE,
    )
    selected_dimension_candidates, unresolved_dimensions = _resolve_simple_candidates(
        required_dimensions,
        dimension_candidates,
        dimension_matcher,
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
                measure_candidates,
                measure_matcher,
                exclude_field_names={
                    candidate.field_name for candidate in selected_measure_candidates
                },
            )
        elif unresolved_dimensions and not unresolved_measures:
            if _should_use_missing_dimension_question(
                [unresolved_dimensions[0]],
                dimension_candidates,
                lexicon,
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
                dimension_candidates,
                dimension_matcher,
                exclude_field_names={
                    candidate.field_name for candidate in selected_dimension_candidates
                },
                fallback_scorer=lambda required_terms, candidate: (
                    _score_dimension_fallback_candidate(required_terms, candidate, lexicon)
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
    used_simple_shortcut = False
    used_simple_clarification_shortcut = False

    if modular_prompt:
        if planner_requires_reasoning:
            logger.info(
                "semantic_understanding_node: analysis_plan 要求保留推理路径，跳过简单快捷路径"
            )
        else:
            shortcut_result = _try_build_simple_semantic_output(state, question)
            if shortcut_result is not None:
                logger.info("semantic_understanding_node: 命中简单查询直出快捷路径")
                result = shortcut_result
                used_simple_shortcut = True
                modular_prompt = None
            else:
                clarification_result = _try_build_simple_clarification_output(state, question)
                if clarification_result is not None:
                    logger.info("semantic_understanding_node: 命中简单查询澄清快捷路径")
                    result = clarification_result
                    used_simple_clarification_shortcut = True
                    modular_prompt = None

    if used_simple_shortcut or used_simple_clarification_shortcut:
        pass
    elif not modular_prompt:
        # 降级：如果没有 modular_prompt，使用旧的方式构建
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

        understanding = SemanticUnderstanding()
        result = await understanding.understand(
            question=question,
            field_candidates=field_candidates,
            current_date=current_date,
            history=history,
            few_shot_examples=few_shot_examples,
            return_thinking=True,
        )
    else:
        # 正常流程：直接使用 modular_prompt 调用 LLM
        logger.info(
            f"semantic_understanding_node: 使用 modular_prompt, "
            f"prompt_length={len(modular_prompt)}"
        )

        logger.info("[semantic_understanding_node] 获取 LLM...")
        llm, using_fast_model = _get_semantic_llm(state, modular_prompt)
        is_reasoning_model = bool(getattr(llm, "_is_reasoning_model", False))
        logger.info(
            "[semantic_understanding_node] 模型已选择: "
            f"model={getattr(llm, 'model_name', 'unknown')}, "
            f"fast_model={using_fast_model}, "
            f"reasoning_model={is_reasoning_model}"
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
                output_model=SemanticOutput,
                on_token=None,        # 不向前端发送 JSON token（结构化输出不应显示给用户）
                on_thinking=on_thinking,
                return_thinking=True,
            )
            logger.info("[semantic_understanding_node] LLM 调用完成")
        except Exception as e:
            if using_fast_model:
                global _fast_semantic_model_available
                _fast_semantic_model_available = False
                logger.warning(
                    "[semantic_understanding_node] 快模型调用失败，回退默认模型: %s",
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
                    output_model=SemanticOutput,
                    on_token=None,
                    on_thinking=on_thinking,
                    return_thinking=True,
                )
                logger.info("[semantic_understanding_node] 默认模型回退完成")
            else:
                logger.exception(f"[semantic_understanding_node] LLM 调用失败: {e}")
                raise

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

    output = {
        "semantic_output": result.model_dump(),
        "needs_clarification": result.needs_clarification,
    }

    if result.needs_clarification:
        output["clarification_question"] = result.clarification_question
        output["clarification_options"] = result.clarification_options
        output["clarification_source"] = (
            result.clarification_source.value
            if result.clarification_source
            else ClarificationSource.SEMANTIC_UNDERSTANDING.value
        )

    elapsed_ms = (time.time() - start_time) * 1000
    output["optimization_metrics"] = merge_metrics(
        state,
        semantic_understanding_ms=elapsed_ms,
        semantic_understanding_fast_model=(
            using_fast_model if modular_prompt else False
        ),
        semantic_understanding_reasoning_model=(
            is_reasoning_model if modular_prompt else False
        ),
        semantic_understanding_shortcut=used_simple_shortcut,
        semantic_understanding_clarification_shortcut=used_simple_clarification_shortcut,
        semantic_understanding_planner_forced_llm=planner_requires_reasoning,
    )

    logger.info("[semantic_understanding_node] 执行完成")
    logger.info("=" * 60)

    return output
