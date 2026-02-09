# -*- coding: utf-8 -*-
"""
DataProfiler 属性测试

使用 Hypothesis 验证 DataProfiler 的核心正确性属性：
- Property 4: 统计正确性（row_count、column_count、min<=avg<=max、
  std>=0、unique_count、top_values 排序）
"""
from typing import Dict, List
from unittest.mock import patch

from hypothesis import given, settings, strategies as st, assume

from analytics_assistant.src.agents.insight.components.data_profiler import (
    DataProfiler,
)
from analytics_assistant.src.core.schemas.execute_result import (
    ColumnInfo,
    ExecuteResult,
    RowData,
)


# ═══════════════════════════════════════════════════════════════════════════
# 测试策略（Generators）
# ═══════════════════════════════════════════════════════════════════════════

_safe_text = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")),
    min_size=1,
    max_size=10,
)


@st.composite
def numeric_execute_result(draw: st.DrawFn) -> ExecuteResult:
    """生成含数值列的 ExecuteResult。"""
    num_cols = draw(st.integers(min_value=1, max_value=3))
    col_names = [f"num_{i}" for i in range(num_cols)]
    columns = [
        ColumnInfo(
            name=name,
            data_type=draw(st.sampled_from(["INTEGER", "FLOAT", "DOUBLE", "DECIMAL"])),
            is_measure=True,
        )
        for name in col_names
    ]
    num_rows = draw(st.integers(min_value=1, max_value=30))
    data: List[RowData] = []
    for _ in range(num_rows):
        row: Dict[str, object] = {}
        for col in columns:
            # 偶尔生成 None
            if draw(st.booleans()) and draw(st.integers(min_value=0, max_value=9)) == 0:
                row[col.name] = None
            else:
                row[col.name] = draw(
                    st.floats(
                        min_value=-10000, max_value=10000,
                        allow_nan=False, allow_infinity=False,
                    )
                )
        data.append(row)
    return ExecuteResult(data=data, columns=columns, row_count=num_rows)


@st.composite
def categorical_execute_result(draw: st.DrawFn) -> ExecuteResult:
    """生成含分类列的 ExecuteResult。"""
    num_cols = draw(st.integers(min_value=1, max_value=3))
    col_names = [f"cat_{i}" for i in range(num_cols)]
    columns = [
        ColumnInfo(name=name, data_type="STRING", is_dimension=True)
        for name in col_names
    ]
    num_rows = draw(st.integers(min_value=1, max_value=30))
    data: List[RowData] = []
    for _ in range(num_rows):
        row: Dict[str, object] = {}
        for col in columns:
            if draw(st.booleans()) and draw(st.integers(min_value=0, max_value=9)) == 0:
                row[col.name] = None
            else:
                row[col.name] = draw(_safe_text)
        data.append(row)
    return ExecuteResult(data=data, columns=columns, row_count=num_rows)


@st.composite
def mixed_execute_result(draw: st.DrawFn) -> ExecuteResult:
    """生成混合列的 ExecuteResult。"""
    # 至少一个数值列 + 一个分类列
    num_numeric = draw(st.integers(min_value=1, max_value=2))
    num_categorical = draw(st.integers(min_value=1, max_value=2))
    columns = []
    for i in range(num_numeric):
        columns.append(ColumnInfo(
            name=f"num_{i}", data_type="FLOAT", is_measure=True,
        ))
    for i in range(num_categorical):
        columns.append(ColumnInfo(
            name=f"cat_{i}", data_type="STRING", is_dimension=True,
        ))
    num_rows = draw(st.integers(min_value=1, max_value=30))
    data: List[RowData] = []
    for _ in range(num_rows):
        row: Dict[str, object] = {}
        for col in columns:
            if col.data_type == "FLOAT":
                row[col.name] = draw(st.floats(
                    min_value=-10000, max_value=10000,
                    allow_nan=False, allow_infinity=False,
                ))
            else:
                row[col.name] = draw(_safe_text)
        data.append(row)
    return ExecuteResult(data=data, columns=columns, row_count=num_rows)


def _make_profiler() -> DataProfiler:
    """创建 mock 配置的 DataProfiler。"""
    with patch(
        "analytics_assistant.src.agents.insight.components.data_profiler.get_config",
        return_value={"agents": {"data_profiler": {"top_values_count": 10}}},
    ):
        return DataProfiler()


# ═══════════════════════════════════════════════════════════════════════════
# Property 4: DataProfiler 统计正确性
# Validates: Requirements 2.1, 2.2, 2.3
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty4StatisticalCorrectness:
    """Property 4: DataProfiler 统计正确性。

    **Validates: Requirements 2.1, 2.2, 2.3**

    对于任意非空的 ExecuteResult，DataProfiler 生成的 DataProfile 应满足：
    - row_count 等于输入行数
    - column_count 等于输入列数
    - columns_profile 长度等于 column_count
    - 数值列: min <= avg <= max 且 std >= 0
    - 分类列: unique_count 等于去重后值数量，top_values 按频率降序
    """

    @given(er=numeric_execute_result())
    @settings(max_examples=100, deadline=5000)
    def test_numeric_column_invariants(self, er: ExecuteResult) -> None:
        """数值列统计不变量：min <= avg <= max, std >= 0。"""
        profiler = _make_profiler()
        profile = profiler.generate(er)

        assert profile.row_count == er.row_count
        assert profile.column_count == len(er.columns)
        assert len(profile.columns_profile) == len(er.columns)

        for col in profile.columns_profile:
            assert col.is_numeric is True
            if col.numeric_stats and col.numeric_stats.min is not None:
                stats = col.numeric_stats
                assert stats.min <= stats.avg, (
                    f"min({stats.min}) > avg({stats.avg})"
                )
                assert stats.avg <= stats.max, (
                    f"avg({stats.avg}) > max({stats.max})"
                )
                assert stats.std >= 0, f"std({stats.std}) < 0"

    @given(er=categorical_execute_result())
    @settings(max_examples=100, deadline=5000)
    def test_categorical_column_invariants(self, er: ExecuteResult) -> None:
        """分类列统计不变量：unique_count 正确，top_values 降序。"""
        profiler = _make_profiler()
        profile = profiler.generate(er)

        assert profile.row_count == er.row_count
        assert profile.column_count == len(er.columns)

        for i, col in enumerate(profile.columns_profile):
            assert col.is_numeric is False
            assert col.categorical_stats is not None

            # 验证 unique_count
            col_name = er.columns[i].name
            actual_values = [
                row.get(col_name) for row in er.data
                if row.get(col_name) is not None
            ]
            expected_unique = len(set(actual_values))
            assert col.categorical_stats.unique_count == expected_unique, (
                f"列 '{col_name}': unique_count={col.categorical_stats.unique_count}, "
                f"期望={expected_unique}"
            )

            # 验证 top_values 按频率降序
            top = col.categorical_stats.top_values
            for j in range(len(top) - 1):
                assert top[j]["count"] >= top[j + 1]["count"], (
                    f"top_values 未按频率降序: "
                    f"{top[j]['count']} < {top[j+1]['count']}"
                )

    @given(er=mixed_execute_result())
    @settings(max_examples=100, deadline=5000)
    def test_mixed_columns_metadata(self, er: ExecuteResult) -> None:
        """混合列：row_count、column_count、columns_profile 长度一致。"""
        profiler = _make_profiler()
        profile = profiler.generate(er)

        assert profile.row_count == er.row_count
        assert profile.column_count == len(er.columns)
        assert len(profile.columns_profile) == len(er.columns)

        # 每列的 is_numeric 应与 data_type 一致
        numeric_types = {
            "INTEGER", "INT", "REAL", "FLOAT",
            "DOUBLE", "DECIMAL", "NUMBER", "NUMERIC",
        }
        for i, col in enumerate(profile.columns_profile):
            expected_numeric = er.columns[i].data_type.upper() in numeric_types
            assert col.is_numeric == expected_numeric
