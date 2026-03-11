# -*- coding: utf-8 -*-
"""
CandidateResolver - 候选字段匹配、评分、解析与澄清构建

从 understanding.py 拆分出的独立模块，包含：
- 文本匹配原语（normalize, compact, text_matches）
- 候选字段信息提取（search_text, identifier_terms）
- 度量/维度语义匹配（基于 SemanticLexicon）
- 简单查询候选评分与解析
- 澄清问题与选项构建
- CandidateMatchContext：消除重复的候选解析上下文
"""

import re
from dataclasses import dataclass
from typing import Callable, Optional

from analytics_assistant.src.core.schemas.field_candidate import FieldCandidate

from .semantic_lexicon_builder import (
    SemanticLexicon,
    SemanticLexiconBuilder,
    collect_seed_hint_terms,
    expand_hint_variants,
    get_default_semantic_lexicon,
)

# ═══════════════════════════════════════════════════════════════════════════
# 常量
# ═══════════════════════════════════════════════════════════════════════════

SIMPLE_SHORTCUT_MIN_CONFIDENCE = 0.85
CLARIFICATION_CANDIDATE_MIN_CONFIDENCE = 0.6

# 度量类别消歧优先级：按具体性从高到低排列。
# 更具体的类别优先匹配，避免通用词（如"销售"）将候选误吸到 revenue 类别。
_MEASURE_CATEGORY_PRIORITY = [
    "quantity", "count", "profit", "cost", "revenue",
]

_SEMANTIC_LEXICON_BUILDER: Optional[SemanticLexiconBuilder] = None


def _get_semantic_lexicon_builder() -> SemanticLexiconBuilder:
    """惰性获取 SemanticLexiconBuilder 单例。"""
    global _SEMANTIC_LEXICON_BUILDER
    if _SEMANTIC_LEXICON_BUILDER is None:
        _SEMANTIC_LEXICON_BUILDER = SemanticLexiconBuilder()
    return _SEMANTIC_LEXICON_BUILDER

# 候选评分加分常量
_TEXT_MATCH_BONUS = 0.1       # 文本直接包含匹配的加分
_EXACT_MATCH_BONUS = 0.05    # match_type == "exact" 的加分

# ═══════════════════════════════════════════════════════════════════════════
# 文本匹配原语
# ═══════════════════════════════════════════════════════════════════════════


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


# ═══════════════════════════════════════════════════════════════════════════
# 候选字段信息提取
# ═══════════════════════════════════════════════════════════════════════════


def _field_display_name(field: FieldCandidate) -> str:
    return field.field_caption or field.field_name


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


# ═══════════════════════════════════════════════════════════════════════════
# 语义词典构建
# ═══════════════════════════════════════════════════════════════════════════


def _build_runtime_semantic_lexicon(
    field_candidates: list[FieldCandidate],
) -> SemanticLexicon:
    """为当前字段候选集合构建运行时语义词典。"""
    if not field_candidates:
        return get_default_semantic_lexicon()
    return _get_semantic_lexicon_builder().build(field_candidates=field_candidates)


# ═══════════════════════════════════════════════════════════════════════════
# 度量匹配
# ═══════════════════════════════════════════════════════════════════════════


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

    # 按具体性从高到低排列：更具体的类别（如 quantity）优先于更泛化的类别（如 revenue），
    # 避免"销售数量"这类同时携带通用销售词和具体数量信号的词被误吸到 revenue 候选。
    for category in _MEASURE_CATEGORY_PRIORITY:
        if category not in matched_categories:
            continue
        if _measure_candidate_matches_category(field, category, lexicon):
            return True

    return False


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


# ═══════════════════════════════════════════════════════════════════════════
# 维度匹配
# ═══════════════════════════════════════════════════════════════════════════


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
        # 避免把"部门"误吸附到"销售员/渠道经理"等更细粒度字段。
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
        # 语义词典中没有匹配的类别/层级，
        # 兜底检查候选标识符（field_name + caption + aliases）是否包含 term 的紧凑形式。
        return _compact_match_text(term_lower) in _compact_match_text(
            _candidate_identifier_text(field)
        )

    return _dimension_candidate_matches_preferences(
        field,
        preferred_categories=preferred_categories,
        preferred_levels=preferred_levels,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 候选评分与解析
# ═══════════════════════════════════════════════════════════════════════════


def _score_simple_candidate(
    term: str,
    field: FieldCandidate,
    matcher,
    *,
    min_confidence: float = SIMPLE_SHORTCUT_MIN_CONFIDENCE,
) -> Optional[float]:
    """为简单查询快捷路径计算候选字段分数。"""
    if field.confidence < min_confidence:
        return None
    if not matcher(term, field):
        return None

    score = field.confidence
    searchable_text = _candidate_search_text(field)
    if _text_matches(term, searchable_text):
        score += _TEXT_MATCH_BONUS
    if field.match_type == "exact":
        score += _EXACT_MATCH_BONUS
    return score


def _resolve_simple_candidates(
    required_terms: list[str],
    candidates: list[FieldCandidate],
    matcher,
    *,
    allow_partial: bool = False,
    min_confidence: float = SIMPLE_SHORTCUT_MIN_CONFIDENCE,
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


# ═══════════════════════════════════════════════════════════════════════════
# 澄清构建
# ═══════════════════════════════════════════════════════════════════════════


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


def _build_clarification_question(term: str, role_label: str) -> str:
    normalized = term.strip()
    if normalized:
        return f"\u201c{normalized}\u201d具体对应哪个{role_label}字段？"
    return f"请确认你想使用哪个{role_label}字段？"


def _build_missing_dimension_question(term: str) -> str:
    normalized = term.strip()
    if normalized:
        return f"当前候选中没有明显对应\u201c{normalized}\u201d的维度字段。以下哪个字段最接近你的分析意图？"
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


def _collect_clarification_options(
    required_terms: list[str],
    candidates: list[FieldCandidate],
    matcher,
    *,
    limit: int = 3,
    exclude_field_names: Optional[set[str]] = None,
    min_confidence: float = CLARIFICATION_CANDIDATE_MIN_CONFIDENCE,
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


# ═══════════════════════════════════════════════════════════════════════════
# CandidateMatchContext - 消除重复的候选解析上下文
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class CandidateMatchContext:
    """封装候选字段匹配所需的上下文，消除 understanding.py 中重复 3 次的候选解析模式。

    使用方式：
        ctx = CandidateMatchContext.from_field_candidates(candidates)
        selected, _ = _resolve_simple_candidates(terms, ctx.measure_candidates, ctx.measure_matcher)
    """

    measure_candidates: list[FieldCandidate]
    dimension_candidates: list[FieldCandidate]
    lexicon: SemanticLexicon
    measure_matcher: Callable[[str, FieldCandidate], bool]
    dimension_matcher: Callable[[str, FieldCandidate], bool]

    @classmethod
    def from_field_candidates(
        cls,
        candidates: list[FieldCandidate],
    ) -> "CandidateMatchContext":
        """从候选字段列表构建匹配上下文。"""
        measure_candidates = [
            candidate for candidate in candidates
            if candidate.role.lower() == "measure"
        ]
        dimension_candidates = [
            candidate for candidate in candidates
            if candidate.role.lower() == "dimension"
        ]
        lexicon = _build_runtime_semantic_lexicon(candidates)
        return cls(
            measure_candidates=measure_candidates,
            dimension_candidates=dimension_candidates,
            lexicon=lexicon,
            measure_matcher=lambda term, candidate: _measure_term_matches_candidate(
                term, candidate, lexicon
            ),
            dimension_matcher=lambda term, candidate: _dimension_term_matches_candidate(
                term, candidate, lexicon
            ),
        )


__all__ = [
    "SIMPLE_SHORTCUT_MIN_CONFIDENCE",
    "CLARIFICATION_CANDIDATE_MIN_CONFIDENCE",
    "CandidateMatchContext",
    "_normalize_match_text",
    "_compact_match_text",
    "_text_matches",
    "_normalize_required_terms",
    "_field_display_name",
    "_candidate_search_text",
    "_candidate_identifier_text",
    "_candidate_identifier_terms",
    "_candidate_identifier_hint_text",
    "_build_runtime_semantic_lexicon",
    "_measure_term_categories",
    "_measure_placeholder_hints",
    "_measure_identifier_hints",
    "_measure_candidate_matches_category",
    "_measure_name_matches_placeholder",
    "_measure_term_matches_candidate",
    "_matches_measure_placeholder",
    "_infer_dimension_preferences",
    "_dimension_term_preferences",
    "_get_dimension_candidate_category",
    "_get_dimension_candidate_level",
    "_dimension_candidate_matches_preferences",
    "_score_dimension_fallback_candidate",
    "_dimension_term_matches_candidate",
    "_score_simple_candidate",
    "_resolve_simple_candidates",
    "_format_clarification_option",
    "_build_clarification_question",
    "_build_missing_dimension_question",
    "_should_use_missing_dimension_question",
    "_collect_clarification_options",
]
