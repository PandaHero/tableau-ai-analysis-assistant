# -*- coding: utf-8 -*-
"""Semantic lexicon builder for runtime grounding hints."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Iterable, Optional

from analytics_assistant.src.core.schemas.field_candidate import FieldCandidate
from analytics_assistant.src.infra.seeds import DIMENSION_SEEDS, MEASURE_SEEDS

_MEASURE_IDENTIFIER_FALLBACK_HINTS: dict[str, set[str]] = {
    # 仅保留种子较难直接覆盖的技术缩写，作为最后兜底。
    "revenue": {"amt", "netamt"},
    "quantity": {"qty"},
    "count": {"cnt"},
}

_MEASURE_PLACEHOLDER_FALLBACK_HINTS: dict[str, set[str]] = {
    "orders": {"orders", "order", "订单", "单数", "笔数", "count"},
    "returns": {"returns", "return", "退货", "退款"},
    "visitors": {"visitors", "visitor", "访问", "访客", "流量"},
    "conversions": {"conversions", "conversion", "转化", "成交"},
    "actual": {"actual", "实际"},
    "target": {"target", "目标"},
}


def normalize_seed_hint(value: Any) -> str:
    """Normalize seed / semantic text into a stable comparable string."""
    return re.sub(r"\s+", " ", str(value).strip().lower())


def collect_seed_hint_terms(*values: Any) -> set[str]:
    """Collect normalized non-empty terms from mixed inputs."""
    terms: set[str] = set()
    for value in values:
        if value is None:
            continue
        if isinstance(value, (list, tuple, set)):
            for item in value:
                normalized = normalize_seed_hint(item)
                if normalized:
                    terms.add(normalized)
            continue
        normalized = normalize_seed_hint(value)
        if normalized:
            terms.add(normalized)
    return terms


def expand_hint_variants(term: str) -> set[str]:
    """Generate match-friendly variants for seed / semantic terms."""
    normalized = normalize_seed_hint(term)
    if not normalized:
        return set()

    variants = {normalized}
    compact = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", normalized)
    if compact and compact != normalized:
        variants.add(compact)

    if re.fullmatch(r"[a-z0-9 ]+", normalized):
        tokens = [token for token in normalized.split(" ") if token]
        if len(tokens) == 1:
            variants.update(token for token in tokens if len(token) >= 3)
        elif len(tokens) > 1:
            variants.add(" ".join(tokens))
            variants.add("".join(tokens))
            # 多词英文短语只保留更有辨识度的尾词，避免 sales/gross 等泛词跨类别串味。
            if len(tokens[-1]) >= 3:
                variants.add(tokens[-1])

    return variants


def _iter_sample_terms(values: Optional[list[str]], *, limit: int = 5) -> list[str]:
    """Pick a few stable sample values into lexicon hints."""
    if not values:
        return []

    terms: list[str] = []
    for raw in values[:limit]:
        normalized = normalize_seed_hint(raw)
        if not normalized:
            continue
        if len(normalized) > 32:
            continue
        if re.fullmatch(r"[\d\-\./: ]+", normalized):
            continue
        terms.append(str(raw))
    return terms


def _expand_terms(terms: Iterable[str]) -> set[str]:
    expanded: set[str] = set()
    for term in terms:
        expanded.update(expand_hint_variants(term))
    return expanded


def _field_identifier_terms(field: FieldCandidate) -> set[str]:
    return collect_seed_hint_terms(
        field.field_name,
        field.field_caption,
        field.aliases or [],
    )


def _field_category_terms(field: FieldCandidate, *, include_samples: bool) -> set[str]:
    return collect_seed_hint_terms(
        field.field_name,
        field.field_caption,
        field.aliases or [],
        field.business_description,
        _iter_sample_terms(field.sample_values, limit=3) if include_samples else [],
    )


def _field_semantic_identifier_terms(field_name: str, semantic_info: dict[str, Any]) -> set[str]:
    return collect_seed_hint_terms(
        field_name,
        semantic_info.get("field_caption"),
        semantic_info.get("aliases", []),
    )


def _field_semantic_category_terms(
    field_name: str,
    semantic_info: dict[str, Any],
    *,
    include_samples: bool,
) -> set[str]:
    return collect_seed_hint_terms(
        field_name,
        semantic_info.get("field_caption"),
        semantic_info.get("aliases", []),
        semantic_info.get("business_description"),
        _iter_sample_terms(semantic_info.get("sample_values"), limit=3)
        if include_samples
        else [],
    )


@dataclass(frozen=True)
class SemanticLexicon:
    """Normalized semantic priors used by semantic understanding fallback matching."""

    measure_category_hints: dict[str, set[str]]
    measure_identifier_hints: dict[str, set[str]]
    measure_placeholder_hints: dict[str, set[str]]
    dimension_category_hints: dict[str, set[str]]
    dimension_level_hints: tuple[tuple[set[str], int], ...]


class SemanticLexiconBuilder:
    """Build semantic lexicon from seeds plus runtime field semantics."""

    def build(
        self,
        *,
        field_candidates: Optional[Iterable[FieldCandidate]] = None,
        field_semantic: Optional[dict[str, Any]] = None,
    ) -> SemanticLexicon:
        measure_category_hints: dict[str, set[str]] = defaultdict(set)
        measure_identifier_hints: dict[str, set[str]] = defaultdict(set)
        dimension_category_hints: dict[str, set[str]] = defaultdict(set)
        dimension_level_hints: dict[int, set[str]] = defaultdict(set)

        self._ingest_measure_seeds(measure_category_hints, measure_identifier_hints)
        self._ingest_dimension_seeds(dimension_category_hints, dimension_level_hints)
        self._ingest_field_candidates(
            field_candidates or [],
            measure_category_hints,
            measure_identifier_hints,
            dimension_category_hints,
            dimension_level_hints,
        )
        self._ingest_field_semantic(
            field_semantic or {},
            measure_category_hints,
            measure_identifier_hints,
            dimension_category_hints,
            dimension_level_hints,
        )

        self._backfill_identifier_fallback_hints(measure_identifier_hints)
        measure_placeholder_hints = self._build_placeholder_hints(
            measure_category_hints,
        )

        return self._assemble_lexicon(
            measure_category_hints,
            measure_identifier_hints,
            measure_placeholder_hints,
            dimension_category_hints,
            dimension_level_hints,
        )

    def _ingest_measure_seeds(
        self,
        category_hints: dict[str, set[str]],
        identifier_hints: dict[str, set[str]],
    ) -> None:
        for seed in MEASURE_SEEDS:
            category = normalize_seed_hint(seed.get("measure_category", ""))
            if not category:
                continue
            category_terms = collect_seed_hint_terms(
                seed.get("field_caption"),
                seed.get("aliases", []),
            )
            category_hints[category].update(category_terms)
            identifier_hints[category].update(_expand_terms(category_terms))

    def _ingest_dimension_seeds(
        self,
        category_hints: dict[str, set[str]],
        level_hints: dict[int, set[str]],
    ) -> None:
        for seed in DIMENSION_SEEDS:
            category = normalize_seed_hint(seed.get("category", ""))
            category_terms = collect_seed_hint_terms(
                seed.get("field_caption"),
                seed.get("aliases", []),
            )
            if category and category_terms:
                category_hints[category].update(category_terms)

            level = seed.get("level")
            if isinstance(level, int) and category_terms:
                level_hints[level].update(category_terms)

    def _ingest_field_candidates(
        self,
        candidates: Iterable[FieldCandidate],
        measure_category_hints: dict[str, set[str]],
        measure_identifier_hints: dict[str, set[str]],
        dimension_category_hints: dict[str, set[str]],
        dimension_level_hints: dict[int, set[str]],
    ) -> None:
        for field in candidates:
            if field.role.lower() == "measure":
                category = normalize_seed_hint(field.measure_category or "")
                if category:
                    category_terms = _field_category_terms(field, include_samples=False)
                    identifier_terms = _field_identifier_terms(field)
                    measure_category_hints[category].update(category_terms)
                    measure_identifier_hints[category].update(_expand_terms(identifier_terms))
            elif field.role.lower() == "dimension":
                category = normalize_seed_hint(field.hierarchy_category or field.category or "")
                category_terms = _field_category_terms(field, include_samples=True)
                if category and category_terms:
                    dimension_category_hints[category].update(category_terms)

                level = field.hierarchy_level or field.level
                if isinstance(level, int) and category_terms:
                    dimension_level_hints[level].update(category_terms)

    def _ingest_field_semantic(
        self,
        field_semantic: dict[str, Any],
        measure_category_hints: dict[str, set[str]],
        measure_identifier_hints: dict[str, set[str]],
        dimension_category_hints: dict[str, set[str]],
        dimension_level_hints: dict[int, set[str]],
    ) -> None:
        for field_name, raw_info in field_semantic.items():
            if not isinstance(raw_info, dict):
                continue

            measure_category = normalize_seed_hint(raw_info.get("measure_category", ""))
            if measure_category:
                category_terms = _field_semantic_category_terms(
                    field_name,
                    raw_info,
                    include_samples=False,
                )
                identifier_terms = _field_semantic_identifier_terms(field_name, raw_info)
                measure_category_hints[measure_category].update(category_terms)
                measure_identifier_hints[measure_category].update(_expand_terms(identifier_terms))

            dimension_category = normalize_seed_hint(
                raw_info.get("hierarchy_category") or raw_info.get("category") or ""
            )
            dimension_terms = _field_semantic_category_terms(
                field_name,
                raw_info,
                include_samples=True,
            )
            if dimension_category and dimension_terms:
                dimension_category_hints[dimension_category].update(dimension_terms)

            level = raw_info.get("hierarchy_level") or raw_info.get("level")
            if isinstance(level, int) and dimension_terms:
                dimension_level_hints[level].update(dimension_terms)

    @staticmethod
    def _backfill_identifier_fallback_hints(
        measure_identifier_hints: dict[str, set[str]],
    ) -> None:
        """将技术缩写兜底词补入 identifier hints。"""
        for category, hints in _MEASURE_IDENTIFIER_FALLBACK_HINTS.items():
            normalized_category = normalize_seed_hint(category)
            measure_identifier_hints[normalized_category].update(hints)

    @staticmethod
    def _build_placeholder_hints(
        measure_category_hints: dict[str, set[str]],
    ) -> dict[str, set[str]]:
        """从 category hints 和 fallback 构建 placeholder hints。"""
        measure_placeholder_hints = {
            category: set(hints)
            for category, hints in measure_category_hints.items()
            if hints
        }
        for category, hints in _MEASURE_PLACEHOLDER_FALLBACK_HINTS.items():
            normalized_category = normalize_seed_hint(category)
            measure_placeholder_hints.setdefault(normalized_category, set()).update(hints)

        return measure_placeholder_hints

    @staticmethod
    def _assemble_lexicon(
        measure_category_hints: dict[str, set[str]],
        measure_identifier_hints: dict[str, set[str]],
        measure_placeholder_hints: dict[str, set[str]],
        dimension_category_hints: dict[str, set[str]],
        dimension_level_hints: dict[int, set[str]],
    ) -> SemanticLexicon:
        return SemanticLexicon(
            measure_category_hints={
                category: set(hints)
                for category, hints in measure_category_hints.items()
                if hints
            },
            measure_identifier_hints={
                category: set(hints)
                for category, hints in measure_identifier_hints.items()
                if hints
            },
            measure_placeholder_hints={
                category: set(hints)
                for category, hints in measure_placeholder_hints.items()
                if hints
            },
            dimension_category_hints={
                category: set(hints)
                for category, hints in dimension_category_hints.items()
                if hints
            },
            dimension_level_hints=tuple(
                (set(terms), level)
                for level, terms in sorted(dimension_level_hints.items())
                if terms
            ),
        )


@lru_cache(maxsize=1)
def get_default_semantic_lexicon() -> SemanticLexicon:
    """Get the seed-only semantic lexicon used as global fallback."""
    return SemanticLexiconBuilder().build()


__all__ = [
    "SemanticLexicon",
    "SemanticLexiconBuilder",
    "collect_seed_hint_terms",
    "expand_hint_variants",
    "get_default_semantic_lexicon",
    "normalize_seed_hint",
]
