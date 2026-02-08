# -*- coding: utf-8 -*-
"""
缓存管理 Mixin

负责推断结果的缓存读写、序列化/反序列化。
从 inference.py 拆分而来。
"""
import logging
from typing import Any, Dict, List, Optional

from analytics_assistant.src.core.schemas.data_model import Field
from analytics_assistant.src.core.schemas.enums import DimensionCategory, MeasureCategory
from analytics_assistant.src.agents.field_semantic.schemas import (
    FieldSemanticAttributes,
)
from analytics_assistant.src.agents.field_semantic.utils import (
    compute_fields_hash,
    compute_single_field_hash,
)

logger = logging.getLogger(__name__)


class CacheMixin:
    """缓存管理 Mixin

    提供缓存读写、序列化/反序列化功能。
    需要宿主类提供 self._cache 属性。
    """

    def _get_cache(self, key: str) -> Optional[Dict[str, Any]]:
        return self._cache.get(key) if self._cache else None

    def _put_cache(
        self,
        key: str,
        field_hash: str,
        field_hashes: Dict[str, str],
        data: Dict[str, Any],
    ) -> bool:
        if not self._cache:
            return False
        return self._cache.set(key, {
            "field_hash": field_hash,
            "field_hashes": field_hashes,
            "data": data,
        })

    def _serialize_attrs(self, attrs: FieldSemanticAttributes) -> Dict[str, Any]:
        """序列化属性"""
        data = {
            "role": attrs.role,
            "business_description": attrs.business_description,
            "aliases": attrs.aliases,
            "confidence": attrs.confidence,
            "reasoning": attrs.reasoning,
        }

        if attrs.role == "dimension":
            data.update({
                "category": attrs.category.value if attrs.category else "other",
                "category_detail": attrs.category_detail,
                "level": attrs.level,
                "granularity": attrs.granularity,
                "parent_dimension": attrs.parent_dimension,
                "child_dimension": attrs.child_dimension,
            })
        else:
            data["measure_category"] = attrs.measure_category.value if attrs.measure_category else "other"

        return data

    def _deserialize_attrs(self, data: Dict[str, Any]) -> FieldSemanticAttributes:
        """反序列化属性"""
        role = data.get("role", "dimension")

        attrs_dict = {
            "role": role,
            "business_description": data.get("business_description", ""),
            "aliases": data.get("aliases", []),
            "confidence": data.get("confidence", 0.0),
            "reasoning": data.get("reasoning", "缓存命中"),
        }

        if role == "dimension":
            try:
                category = DimensionCategory(data.get("category", "other"))
            except ValueError:
                category = DimensionCategory.OTHER

            attrs_dict.update({
                "category": category,
                "category_detail": data.get("category_detail"),
                "level": data.get("level"),
                "granularity": data.get("granularity"),
                "parent_dimension": data.get("parent_dimension"),
                "child_dimension": data.get("child_dimension"),
            })
        else:
            try:
                measure_category = MeasureCategory(data.get("measure_category", "other"))
            except ValueError:
                measure_category = MeasureCategory.OTHER

            attrs_dict["measure_category"] = measure_category

        return FieldSemanticAttributes(**attrs_dict)

    def _update_cache(
        self,
        key: str,
        fields: List[Field],
        results: Dict[str, FieldSemanticAttributes],
    ) -> None:
        """更新缓存"""
        if not self._cache:
            return
        field_hash = compute_fields_hash(fields)
        field_hashes = {f.caption or f.name: compute_single_field_hash(f) for f in fields}
        data = {name: self._serialize_attrs(attrs) for name, attrs in results.items()}
        self._put_cache(key, field_hash, field_hashes, data)
