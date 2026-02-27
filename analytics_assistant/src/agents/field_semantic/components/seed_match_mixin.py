# -*- coding: utf-8 -*-
"""
种子匹配 Mixin

负责种子数据的精确匹配和初始化。
从 inference.py 拆分而来。
"""
import logging
from typing import Any, Optional

from analytics_assistant.src.core.schemas.enums import DimensionCategory, MeasureCategory
from analytics_assistant.src.agents.field_semantic.schemas import (
    FieldSemanticAttributes,
)
from analytics_assistant.src.infra.seeds import DIMENSION_SEEDS, MEASURE_SEEDS
from analytics_assistant.src.agents.field_semantic.utils import (
    FIELD_SEMANTIC_PATTERNS_INDEX,
    PatternSource,
    generate_pattern_id,
)

logger = logging.getLogger(__name__)

class SeedMatchMixin:
    """种子匹配 Mixin

    提供种子数据精确匹配和初始化功能。
    需要宿主类提供:
    - self._dimension_seed_index
    - self._measure_seed_index
    - self._pattern_store
    - self._seed_initialized
    """

    def _match_seed(self, caption: str, role: str) -> Optional[dict[str, Any]]:
        """精确匹配种子数据"""
        caption_lower = caption.lower()

        if role == "measure":
            return self._measure_seed_index.get(caption_lower)
        else:
            return self._dimension_seed_index.get(caption_lower)

    def _seed_to_attrs(self, seed: dict[str, Any], role: str) -> FieldSemanticAttributes:
        """将种子数据转换为 FieldSemanticAttributes"""
        if role == "measure":
            return FieldSemanticAttributes(
                role="measure",
                measure_category=MeasureCategory(seed["measure_category"]),
                business_description=seed.get("business_description", seed["field_caption"]),
                aliases=seed.get("aliases", []),
                confidence=1.0,
                reasoning=f"种子匹配: {seed.get('reasoning', seed['field_caption'])}",
            )
        else:
            return FieldSemanticAttributes(
                role="dimension",
                category=DimensionCategory(seed["category"]),
                category_detail=seed["category_detail"],
                level=seed["level"],
                granularity=seed["granularity"],
                business_description=seed.get("business_description", seed["field_caption"]),
                aliases=seed.get("aliases", []),
                confidence=1.0,
                reasoning=f"种子匹配: {seed.get('reasoning', seed['field_caption'])}",
            )

    def _ensure_seed_data(self) -> None:
        """确保种子数据已初始化"""
        if self._seed_initialized:
            return

        patterns = self._load_patterns()
        metadata_count = len(patterns)
        index_count = self._get_index_count()

        logger.debug(f"一致性检查: index={index_count}, metadata={metadata_count}")

        if metadata_count == 0:
            logger.info("metadata 为空，初始化种子数据")
            self._init_seed_patterns()
        elif index_count != metadata_count and index_count > 0:
            logger.warning(
                f"索引 ({index_count}) 和 metadata ({metadata_count}) 数量不一致，"
                f"将在 RAG 初始化时重建索引"
            )
            self._rag_initialized = False

        self._seed_initialized = True

    def _load_patterns(self) -> list[dict[str, Any]]:
        """加载已存储的 pattern"""
        if not self._pattern_store:
            return []
        pattern_index = self._pattern_store.get("_pattern_index") or []
        return [p for pid in pattern_index if (p := self._pattern_store.get(pid))]

    def _init_seed_patterns(self) -> list[dict[str, Any]]:
        """初始化种子数据到 pattern store"""
        if not self._pattern_store:
            return []

        patterns, pattern_ids = [], []

        # 维度种子
        for seed in DIMENSION_SEEDS:
            pid = generate_pattern_id(seed["field_caption"], seed["data_type"])
            pattern = {
                "pattern_id": pid,
                "field_caption": seed["field_caption"],
                "data_type": seed["data_type"],
                "role": "dimension",
                "category": seed["category"],
                "category_detail": seed["category_detail"],
                "level": seed["level"],
                "granularity": seed["granularity"],
                "business_description": seed.get("business_description", seed["field_caption"]),
                "aliases": seed.get("aliases", []),
                "reasoning": seed.get("reasoning", "种子数据"),
                "confidence": 1.0,
                "source": PatternSource.SEED.value,
                "verified": True,
            }
            self._pattern_store.set(pid, pattern)
            patterns.append(pattern)
            pattern_ids.append(pid)

        # 度量种子
        for seed in MEASURE_SEEDS:
            pid = generate_pattern_id(seed["field_caption"], seed["data_type"])
            pattern = {
                "pattern_id": pid,
                "field_caption": seed["field_caption"],
                "data_type": seed["data_type"],
                "role": "measure",
                "measure_category": seed["measure_category"],
                "business_description": seed.get("business_description", seed["field_caption"]),
                "aliases": seed.get("aliases", []),
                "reasoning": seed.get("reasoning", "种子数据"),
                "confidence": 1.0,
                "source": PatternSource.SEED.value,
                "verified": True,
            }
            self._pattern_store.set(pid, pattern)
            patterns.append(pattern)
            pattern_ids.append(pid)

        self._pattern_store.set("_pattern_index", pattern_ids)
        logger.info(f"种子数据初始化: {len(patterns)} 个模式")
        return patterns
