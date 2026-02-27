# -*- coding: utf-8 -*-
"""
维度模式种子数据包

按类别拆分，使用 DimensionSeed dataclass 替代 list[dict]。
通过 generate_case_variants 自动生成大小写变体。

用法：
    from analytics_assistant.src.infra.seeds.dimensions import (
        DIMENSION_SEEDS,
        DimensionSeed,
        get_dimension_few_shot_examples,
        generate_case_variants,
    )
"""
from typing import Any, Optional

from ._types import DimensionSeed, MeasureSeed
from ._utils import generate_case_variants, expand_seeds
from .time import _TIME_SEEDS
from .geography import _GEOGRAPHY_SEEDS
from .product import _PRODUCT_SEEDS
from .customer import _CUSTOMER_SEEDS
from .organization import _ORGANIZATION_SEEDS
from .channel import _CHANNEL_SEEDS
from .financial import _FINANCIAL_SEEDS
from .common import _COMMON_SEEDS

# 汇总所有基础种子并展开大小写变体
_ALL_BASE_SEEDS: list[DimensionSeed] = (
    _TIME_SEEDS
    + _GEOGRAPHY_SEEDS
    + _PRODUCT_SEEDS
    + _CUSTOMER_SEEDS
    + _ORGANIZATION_SEEDS
    + _CHANNEL_SEEDS
    + _FINANCIAL_SEEDS
    + _COMMON_SEEDS
)

# 展开大小写变体后的完整种子列表
_ALL_EXPANDED: list[DimensionSeed] = expand_seeds(_ALL_BASE_SEEDS)

# 兼容旧接口：导出为 list[dict]
DIMENSION_SEEDS: list[dict[str, Any]] = [s.to_dict() for s in _ALL_EXPANDED]

def get_dimension_few_shot_examples(
    categories: Optional[list[str]] = None,
    max_per_category: int = 1,
) -> list[dict[str, Any]]:
    """获取维度种子数据作为 few-shot 示例

    Args:
        categories: 要获取的类别列表，None 表示所有主要类别
        max_per_category: 每个类别最多返回的示例数

    Returns:
        few-shot 示例列表
    """
    if categories is None:
        categories = [
            "time", "geography", "product", "customer",
            "organization", "channel", "financial",
        ]

    examples: list[dict[str, Any]] = []
    category_counts: dict[str, int] = {cat: 0 for cat in categories}

    for pattern in DIMENSION_SEEDS:
        cat = pattern["category"]
        if cat in categories and category_counts[cat] < max_per_category:
            examples.append({
                "field_caption": pattern["field_caption"],
                "data_type": pattern["data_type"],
                "category": pattern["category"],
                "category_detail": pattern["category_detail"],
                "level": pattern["level"],
                "granularity": pattern["granularity"],
            })
            category_counts[cat] += 1

    return examples

__all__ = [
    "DimensionSeed",
    "MeasureSeed",
    "DIMENSION_SEEDS",
    "generate_case_variants",
    "expand_seeds",
    "get_dimension_few_shot_examples",
]
