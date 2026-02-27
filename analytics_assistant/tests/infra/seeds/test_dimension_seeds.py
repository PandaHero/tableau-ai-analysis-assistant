# -*- coding: utf-8 -*-
"""
维度种子数据属性测试

Property 9: 种子数据类型完整性
Property 10: 大小写变体生成正确性
"""
import pytest
from hypothesis import given, strategies as st, assume

from analytics_assistant.src.infra.seeds.dimensions import (
    DIMENSION_SEEDS,
    DimensionSeed,
    generate_case_variants,
)
from analytics_assistant.src.infra.seeds.dimensions._types import _LEVEL_GRANULARITY_MAP


# ══════════════════════════════════════════════════════════════
# Property 9: 种子数据类型完整性
# ══════════════════════════════════════════════════════════════

# 从实际数据中提取有效值范围
_VALID_LEVELS = set(_LEVEL_GRANULARITY_MAP.keys())
_VALID_GRANULARITIES = set(_LEVEL_GRANULARITY_MAP.values())


class TestDimensionSeedIntegrity:
    """验证所有 DIMENSION_SEEDS 的数据完整性"""

    @pytest.mark.parametrize("seed", DIMENSION_SEEDS, ids=lambda s: s["field_caption"])
    def test_required_fields_not_empty(self, seed: dict) -> None:
        """必填字段不为空"""
        assert seed["field_caption"], "field_caption 不能为空"
        assert seed["data_type"], "data_type 不能为空"
        assert seed["category"], "category 不能为空"
        assert seed["level"] in _VALID_LEVELS, f"level={seed['level']} 不在有效范围内"

    @pytest.mark.parametrize("seed", DIMENSION_SEEDS, ids=lambda s: s["field_caption"])
    def test_granularity_consistent_with_level(self, seed: dict) -> None:
        """granularity 与 level 一致"""
        expected = _LEVEL_GRANULARITY_MAP[seed["level"]]
        assert seed["granularity"] == expected, (
            f"level={seed['level']} 应对应 granularity='{expected}'，"
            f"实际为 '{seed['granularity']}'"
        )


# ══════════════════════════════════════════════════════════════
# Property 10: 大小写变体生成正确性
# ══════════════════════════════════════════════════════════════

# 用于 Hypothesis 的 DimensionSeed 策略
_dimension_seed_strategy = st.builds(
    DimensionSeed,
    field_caption=st.text(min_size=1, max_size=50),
    data_type=st.sampled_from(["string", "integer", "date", "float"]),
    category=st.sampled_from(["time", "geography", "product", "customer"]),
    category_detail=st.text(min_size=1, max_size=30),
    level=st.sampled_from(list(_VALID_LEVELS)),
    business_description=st.text(min_size=1, max_size=100),
    aliases=st.lists(st.text(min_size=1, max_size=20), max_size=5),
    reasoning=st.text(max_size=100),
)


class TestCaseVariantGeneration:
    """验证 generate_case_variants 的正确性"""

    @given(seed=_dimension_seed_strategy)
    def test_original_seed_in_variants(self, seed: DimensionSeed) -> None:
        """变体列表始终包含原始种子"""
        variants = generate_case_variants(seed)
        assert seed in variants, "变体列表必须包含原始种子"

    @given(seed=_dimension_seed_strategy)
    def test_variants_only_differ_in_caption_case(self, seed: DimensionSeed) -> None:
        """变体仅在 field_caption 大小写上不同，其他字段保持不变"""
        variants = generate_case_variants(seed)
        for v in variants:
            assert v.data_type == seed.data_type
            assert v.category == seed.category
            assert v.category_detail == seed.category_detail
            assert v.level == seed.level
            assert v.business_description == seed.business_description
            assert v.aliases == seed.aliases
            assert v.reasoning == seed.reasoning
            # field_caption 仅大小写不同
            assert v.field_caption.lower() == seed.field_caption.lower()

    @given(seed=_dimension_seed_strategy)
    def test_ascii_seeds_generate_at_most_two_variants(self, seed: DimensionSeed) -> None:
        """ASCII 种子最多生成 2 个变体（原始 + 大小写变体）"""
        variants = generate_case_variants(seed)
        if seed.field_caption.isascii() and len(seed.field_caption) > 0:
            assert len(variants) <= 2
        else:
            # 非 ASCII 不生成变体
            assert len(variants) == 1

    @given(seed=_dimension_seed_strategy)
    def test_non_ascii_seeds_no_variants(self, seed: DimensionSeed) -> None:
        """非 ASCII 种子不生成额外变体"""
        assume(not seed.field_caption.isascii())
        variants = generate_case_variants(seed)
        assert len(variants) == 1
        assert variants[0] is seed
