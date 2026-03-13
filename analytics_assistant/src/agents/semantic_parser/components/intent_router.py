# -*- coding: utf-8 -*-
"""Intent router for semantic parsing."""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from analytics_assistant.src.infra.config import get_config
from analytics_assistant.src.infra.seeds import (
    INTENT_KEYWORDS,
    IRRELEVANT_PATTERNS,
)

from ..schemas.intent import IntentRouterOutput, IntentType

logger = logging.getLogger(__name__)

METADATA_KEYWORDS = INTENT_KEYWORDS["metadata"]
DATA_ANALYSIS_KEYWORDS = INTENT_KEYWORDS["data_analysis"]
SHORT_AMBIGUOUS_KEYWORDS = INTENT_KEYWORDS["ambiguous"]

_WEAK_TIME_KEYWORDS = {
    "今天",
    "昨天",
    "明天",
    "本周",
    "这周",
    "上周",
    "下周",
    "本月",
    "这个月",
    "上个月",
    "上月",
    "今年",
    "去年",
    "本年",
    "上一年",
}


class IntentRouter:
    """Three-stage intent router with rule-first decisions."""

    _DEFAULT_BASE_CONFIDENCE = 0.7
    _DEFAULT_CONFIDENCE_INCREMENT = 0.1
    _DEFAULT_MAX_CONFIDENCE = 0.95
    _DEFAULT_HIGH_CONFIDENCE = 0.95
    _DEFAULT_FALLBACK_CONFIDENCE = 0.5
    _DEFAULT_SHORT_QUESTION_THRESHOLD = 10
    _DEFAULT_L1_CONFIDENCE_THRESHOLD = 0.8

    def __init__(
        self,
        l1_confidence_threshold: Optional[float] = None,
        enable_l1: Optional[bool] = None,
    ) -> None:
        self._load_config()
        if l1_confidence_threshold is not None:
            self.l1_confidence_threshold = l1_confidence_threshold
        if enable_l1 is not None:
            self.enable_l1 = enable_l1

    def _load_config(self) -> None:
        """Load runtime thresholds from config."""
        try:
            config = get_config()
            intent_config = config.get_intent_router_config()
            confidence_config = intent_config.get("confidence", {})
            l1_config = intent_config.get("l1", {})
            rules_config = intent_config.get("rules", {})

            self.base_confidence = confidence_config.get(
                "base",
                self._DEFAULT_BASE_CONFIDENCE,
            )
            self.confidence_increment = confidence_config.get(
                "increment",
                self._DEFAULT_CONFIDENCE_INCREMENT,
            )
            self.max_confidence = confidence_config.get(
                "max",
                self._DEFAULT_MAX_CONFIDENCE,
            )
            self.high_confidence = confidence_config.get(
                "high",
                self._DEFAULT_HIGH_CONFIDENCE,
            )
            self.fallback_confidence = confidence_config.get(
                "fallback",
                self._DEFAULT_FALLBACK_CONFIDENCE,
            )
            self.enable_l1 = l1_config.get("enabled", False)
            self.l1_confidence_threshold = l1_config.get(
                "threshold",
                self._DEFAULT_L1_CONFIDENCE_THRESHOLD,
            )
            self.short_question_threshold = rules_config.get(
                "short_question_threshold",
                self._DEFAULT_SHORT_QUESTION_THRESHOLD,
            )
        except Exception as exc:
            logger.warning("加载 IntentRouter 配置失败，使用默认值: %s", exc)
            self.base_confidence = self._DEFAULT_BASE_CONFIDENCE
            self.confidence_increment = self._DEFAULT_CONFIDENCE_INCREMENT
            self.max_confidence = self._DEFAULT_MAX_CONFIDENCE
            self.high_confidence = self._DEFAULT_HIGH_CONFIDENCE
            self.fallback_confidence = self._DEFAULT_FALLBACK_CONFIDENCE
            self.short_question_threshold = self._DEFAULT_SHORT_QUESTION_THRESHOLD
            self.enable_l1 = False
            self.l1_confidence_threshold = self._DEFAULT_L1_CONFIDENCE_THRESHOLD

        self._irrelevant_patterns = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in IRRELEVANT_PATTERNS
        ]
        self._metadata_keywords = [keyword.lower() for keyword in METADATA_KEYWORDS]
        self._data_analysis_keywords = [
            keyword.lower() for keyword in DATA_ANALYSIS_KEYWORDS
        ]
        self._ambiguous_keywords = [
            keyword.lower() for keyword in SHORT_AMBIGUOUS_KEYWORDS
        ]

    async def route(
        self,
        question: str,
        context: Optional[dict[str, Any]] = None,
    ) -> IntentRouterOutput:
        """Route a user question to an intent."""
        del context

        l0_result = self._try_l0_rules(question)
        if l0_result is not None:
            return l0_result

        if self.enable_l1:
            l1_result = await self._try_l1_classifier(question, context)
            if (
                l1_result is not None
                and l1_result.confidence >= self.l1_confidence_threshold
            ):
                return l1_result

        return IntentRouterOutput(
            intent_type=IntentType.DATA_QUERY,
            confidence=self.fallback_confidence,
            reason="L0 未命中，默认进入数据分析流程",
            source="L2_FALLBACK",
        )

    def _try_l0_rules(self, question: str) -> Optional[IntentRouterOutput]:
        """Rule-first routing."""
        question_lower = str(question or "").strip().lower()
        if not question_lower:
            return IntentRouterOutput(
                intent_type=IntentType.IRRELEVANT,
                confidence=self.high_confidence,
                reason="问题为空",
                source="L0_RULES",
            )

        metadata_keywords = self._match_keywords(
            question_lower,
            self._metadata_keywords,
        )
        matched_data_keywords, strong_data_keywords = (
            self._get_data_analysis_keyword_matches(question_lower)
        )

        if result := self._check_irrelevant(question_lower):
            return result

        if strong_data_keywords:
            return self._build_data_analysis_output(
                question_lower=question_lower,
                matched_keywords=matched_data_keywords,
                strong_keywords=strong_data_keywords,
            )

        if metadata_keywords:
            return self._build_metadata_output(metadata_keywords)

        if matched_data_keywords:
            return self._build_data_analysis_output(
                question_lower=question_lower,
                matched_keywords=matched_data_keywords,
                strong_keywords=strong_data_keywords,
            )

        return None

    @staticmethod
    def _match_keywords(question_lower: str, keywords: list[str]) -> list[str]:
        return [keyword for keyword in keywords if keyword in question_lower]

    def _get_data_analysis_keyword_matches(
        self,
        question_lower: str,
    ) -> tuple[list[str], list[str]]:
        matched_keywords = self._match_keywords(
            question_lower,
            self._data_analysis_keywords,
        )
        if not matched_keywords:
            return [], []

        deduplicated_keywords = self._deduplicate_keywords(matched_keywords)
        strong_keywords = self._filter_weak_keywords(deduplicated_keywords)
        strong_keywords = [
            keyword
            for keyword in strong_keywords
            if keyword not in _WEAK_TIME_KEYWORDS
        ]
        return deduplicated_keywords, strong_keywords

    def _check_irrelevant(
        self,
        question_lower: str,
    ) -> Optional[IntentRouterOutput]:
        """Return IRRELEVANT only when no strong data signal exists."""
        for pattern in self._irrelevant_patterns:
            if not pattern.search(question_lower):
                continue

            _, strong_keywords = self._get_data_analysis_keyword_matches(
                question_lower
            )
            if strong_keywords:
                logger.debug(
                    "IntentRouter: irrelevant pattern hit but strong data keywords exist"
                )
                return None

            return IntentRouterOutput(
                intent_type=IntentType.IRRELEVANT,
                confidence=self.high_confidence,
                reason="检测到与数据分析无关的问题",
                source="L0_RULES",
            )
        return None

    def _build_metadata_output(
        self,
        matched_keywords: list[str],
    ) -> IntentRouterOutput:
        keyword = matched_keywords[0]
        return IntentRouterOutput(
            intent_type=IntentType.GENERAL,
            confidence=self.high_confidence,
            reason=f"检测到元数据问答关键词: {keyword}",
            source="L0_RULES",
        )

    def _build_data_analysis_output(
        self,
        *,
        question_lower: str,
        matched_keywords: list[str],
        strong_keywords: list[str],
    ) -> Optional[IntentRouterOutput]:
        if not matched_keywords:
            return None

        if not strong_keywords:
            if len(question_lower) < self.short_question_threshold:
                return None
            return IntentRouterOutput(
                intent_type=IntentType.DATA_QUERY,
                confidence=self.fallback_confidence,
                reason=f"仅检测到模糊关键词: {', '.join(matched_keywords[:3])}",
                source="L0_RULES",
            )

        confidence = self._calculate_confidence(len(strong_keywords))
        return IntentRouterOutput(
            intent_type=IntentType.DATA_QUERY,
            confidence=confidence,
            reason=f"检测到数据分析关键词: {', '.join(strong_keywords[:3])}",
            source="L0_RULES",
        )

    @staticmethod
    def _deduplicate_keywords(keywords: list[str]) -> list[str]:
        sorted_keywords = sorted(keywords, key=len, reverse=True)
        result: list[str] = []
        for keyword in sorted_keywords:
            if any(keyword in kept and keyword != kept for kept in result):
                continue
            result.append(keyword)
        return result

    def _filter_weak_keywords(self, keywords: list[str]) -> list[str]:
        return [
            keyword
            for keyword in keywords
            if keyword not in self._ambiguous_keywords
        ]

    def _calculate_confidence(self, match_count: int) -> float:
        return min(
            self.base_confidence + match_count * self.confidence_increment,
            self.max_confidence,
        )

    async def _try_l1_classifier(
        self,
        question: str,
        context: Optional[dict[str, Any]],
    ) -> Optional[IntentRouterOutput]:
        del question, context
        logger.debug("L1 classifier is disabled in the current implementation")
        return None


__all__ = [
    "IntentType",
    "IntentRouterOutput",
    "IntentRouter",
    "METADATA_KEYWORDS",
    "DATA_ANALYSIS_KEYWORDS",
]
