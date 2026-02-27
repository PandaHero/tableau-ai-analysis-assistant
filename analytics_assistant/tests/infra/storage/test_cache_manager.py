# -*- coding: utf-8 -*-
"""
CacheManager 批量删除正确性属性测试

Property 7: 批量删除正确性

验证 delete_by_filter 删除所有满足条件的项且不影响其他项。
删除后，满足条件的项不可通过 get 获取。

验证: 需求 7.2
"""

from hypothesis import given, settings, strategies as st
from langgraph.store.memory import InMemoryStore

from analytics_assistant.src.infra.storage.cache import CacheManager


# ---------------------------------------------------------------------------
# Hypothesis 策略
# ---------------------------------------------------------------------------

# 缓存值策略：带 category 字段的字典
_cache_entry_strategy = st.fixed_dictionaries({
    "category": st.sampled_from(["alpha", "beta", "gamma"]),
    "score": st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    "data": st.text(min_size=1, max_size=50),
})

# 缓存键策略
_cache_key_strategy = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789",
    min_size=3,
    max_size=12,
)

# 缓存条目列表策略（键值对）
_cache_entries_strategy = st.lists(
    st.tuples(_cache_key_strategy, _cache_entry_strategy),
    min_size=1,
    max_size=20,
    unique_by=lambda x: x[0],  # 键唯一
)


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _create_cache_manager(namespace: str = "test") -> CacheManager:
    """创建使用 InMemoryStore 的 CacheManager 实例。"""
    store = InMemoryStore()
    return CacheManager(
        namespace=namespace,
        store=store,
        enable_stats=True,
    )


# ---------------------------------------------------------------------------
# Property 7: 批量删除正确性
# ---------------------------------------------------------------------------

class TestCacheManagerDeleteByFilterPBT:
    """Property 7: 批量删除正确性

    **Validates: Requirements 7.2**

    *For any* 缓存内容集合和过滤条件，delete_by_filter 应删除所有
    满足条件的项且不影响不满足条件的项。
    """

    @given(
        entries=_cache_entries_strategy,
        target_category=st.sampled_from(["alpha", "beta", "gamma"]),
    )
    @settings(max_examples=100, deadline=5000)
    def test_delete_by_filter_removes_matching_items(
        self, entries, target_category
    ):
        """满足过滤条件的项被删除，不满足的项保留。"""
        cache = _create_cache_manager("test_filter")

        # 写入所有条目
        for key, value in entries:
            cache.set(key, value)

        # 按 category 过滤删除
        deleted = cache.delete_by_filter(
            lambda v: v.get("category") == target_category
        )

        # 验证：满足条件的项已删除
        expected_deleted = sum(
            1 for _, v in entries if v["category"] == target_category
        )
        assert deleted == expected_deleted

        # 验证：满足条件的项不可获取
        for key, value in entries:
            result = cache.get(key)
            if value["category"] == target_category:
                assert result is None, (
                    f"键 {key} 应已被删除（category={target_category}）"
                )
            else:
                assert result is not None, (
                    f"键 {key} 不应被删除（category={value['category']}）"
                )

    @given(entries=_cache_entries_strategy)
    @settings(max_examples=50, deadline=5000)
    def test_delete_by_filter_with_always_false_deletes_nothing(self, entries):
        """过滤条件始终为 False 时，不删除任何项。"""
        cache = _create_cache_manager("test_no_delete")

        for key, value in entries:
            cache.set(key, value)

        deleted = cache.delete_by_filter(lambda _: False)
        assert deleted == 0

        # 所有项仍可获取
        for key, _ in entries:
            assert cache.get(key) is not None

    @given(entries=_cache_entries_strategy)
    @settings(max_examples=50, deadline=5000)
    def test_delete_by_filter_with_always_true_deletes_all(self, entries):
        """过滤条件始终为 True 时，删除所有项。"""
        cache = _create_cache_manager("test_delete_all")

        for key, value in entries:
            cache.set(key, value)

        deleted = cache.delete_by_filter(lambda _: True)
        assert deleted == len(entries)

        # 所有项不可获取
        for key, _ in entries:
            assert cache.get(key) is None

    @given(
        entries=_cache_entries_strategy,
        target_category=st.sampled_from(["alpha", "beta", "gamma"]),
    )
    @settings(max_examples=50, deadline=5000)
    def test_delete_stats_updated_correctly(self, entries, target_category):
        """删除后统计信息正确更新。"""
        cache = _create_cache_manager("test_stats")

        for key, value in entries:
            cache.set(key, value)

        deleted = cache.delete_by_filter(
            lambda v: v.get("category") == target_category
        )

        stats = cache.get_stats()
        # 统计中的 deletes 应包含本次批量删除数
        assert stats["deletes"] >= deleted


# ---------------------------------------------------------------------------
# Property 12: CacheManager 存取对称性
# ---------------------------------------------------------------------------

# 可序列化的缓存值策略
_json_value_strategy = st.one_of(
    st.text(min_size=0, max_size=50),
    st.integers(min_value=-10000, max_value=10000),
    st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
    st.booleans(),
    st.lists(st.integers(min_value=-100, max_value=100), max_size=10),
    st.fixed_dictionaries({
        "name": st.text(min_size=1, max_size=20),
        "value": st.integers(min_value=0, max_value=100),
    }),
)


class TestCacheManagerSymmetryPBT:
    """Property 12: CacheManager 存取对称性

    **Validates: Requirements 21.2**

    *For any* key 和 value，set(key, value) 后 get(key) 返回等价对象。
    """

    @given(
        key=_cache_key_strategy,
        value=_json_value_strategy,
    )
    @settings(max_examples=100, deadline=5000)
    def test_set_then_get_returns_equivalent(self, key: str, value):
        """set(key, value) 后 get(key) 返回等价对象。"""
        cache = _create_cache_manager("symmetry_test")
        cache.set(key, value)
        result = cache.get(key)
        assert result == value, (
            f"存取不对称: set({key!r}, {value!r}) → get 返回 {result!r}"
        )

    @given(
        key=_cache_key_strategy,
        value1=_json_value_strategy,
        value2=_json_value_strategy,
    )
    @settings(max_examples=50, deadline=5000)
    def test_overwrite_returns_latest_value(self, key: str, value1, value2):
        """覆盖写入后 get 返回最新值。"""
        cache = _create_cache_manager("overwrite_test")
        cache.set(key, value1)
        cache.set(key, value2)
        result = cache.get(key)
        assert result == value2, (
            f"覆盖后应返回最新值: {value2!r}，实际返回 {result!r}"
        )

    @given(key=_cache_key_strategy)
    @settings(max_examples=50, deadline=5000)
    def test_get_nonexistent_returns_default(self, key: str):
        """获取不存在的键返回默认值。"""
        cache = _create_cache_manager("nonexistent_test")
        assert cache.get(key) is None
        assert cache.get(key, "fallback") == "fallback"

    @given(
        key=_cache_key_strategy,
        value=_json_value_strategy,
    )
    @settings(max_examples=50, deadline=5000)
    def test_delete_then_get_returns_none(self, key: str, value):
        """删除后 get 返回 None。"""
        cache = _create_cache_manager("delete_test")
        cache.set(key, value)
        cache.delete(key)
        assert cache.get(key) is None
