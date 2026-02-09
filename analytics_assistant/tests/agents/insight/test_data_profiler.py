# -*- coding: utf-8 -*-
"""
DataProfiler 单元测试

测试内容：
- 数值列统计正确性
- 分类列统计正确性
- 空数据处理
- 单列失败跳过
"""
import pytest
from unittest.mock import patch

from analytics_assistant.src.agents.insight.components.data_profiler import (
    DataProfiler,
)
from analytics_assistant.src.core.schemas.execute_result import (
    ColumnInfo,
    ExecuteResult,
)


_MOCK_CONFIG = {
    "agents": {"data_profiler": {"top_values_count": 10}}
}


def _patch_config():
    return patch(
        "analytics_assistant.src.agents.insight.components.data_profiler.get_config",
        return_value=_MOCK_CONFIG,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 数值列统计测试
# ═══════════════════════════════════════════════════════════════════════════


class TestNumericColumn:
    """数值列统计正确性。"""

    def test_basic_numeric_stats(self):
        """基本数值列统计。"""
        er = ExecuteResult(
            data=[
                {"amount": 10.0},
                {"amount": 20.0},
                {"amount": 30.0},
                {"amount": 40.0},
                {"amount": 50.0},
            ],
            columns=[ColumnInfo(name="amount", data_type="FLOAT", is_measure=True)],
            row_count=5,
        )
        with _patch_config():
            profiler = DataProfiler()
        profile = profiler.generate(er)

        assert profile.row_count == 5
        assert profile.column_count == 1
        assert len(profile.columns_profile) == 1

        col = profile.columns_profile[0]
        assert col.column_name == "amount"
        assert col.is_numeric is True
        assert col.null_count == 0
        assert col.numeric_stats is not None
        assert col.numeric_stats.min == 10.0
        assert col.numeric_stats.max == 50.0
        assert col.numeric_stats.avg == 30.0
        assert col.numeric_stats.median == 30.0
        assert col.numeric_stats.std is not None
        assert col.numeric_stats.std > 0

    def test_numeric_with_nulls(self):
        """含 None 值的数值列。"""
        er = ExecuteResult(
            data=[
                {"val": 100},
                {"val": None},
                {"val": 200},
            ],
            columns=[ColumnInfo(name="val", data_type="INTEGER")],
            row_count=3,
        )
        with _patch_config():
            profiler = DataProfiler()
        profile = profiler.generate(er)

        col = profile.columns_profile[0]
        assert col.null_count == 1
        assert col.numeric_stats.min == 100.0
        assert col.numeric_stats.max == 200.0

    def test_all_numeric_types(self):
        """所有数值类型都应被识别。"""
        numeric_types = [
            "INTEGER", "INT", "REAL", "FLOAT",
            "DOUBLE", "DECIMAL", "NUMBER", "NUMERIC",
        ]
        for dt in numeric_types:
            er = ExecuteResult(
                data=[{"x": 1}, {"x": 2}],
                columns=[ColumnInfo(name="x", data_type=dt)],
                row_count=2,
            )
            with _patch_config():
                profiler = DataProfiler()
            profile = profiler.generate(er)
            assert profile.columns_profile[0].is_numeric is True, (
                f"data_type={dt} 应被识别为数值列"
            )

    def test_case_insensitive_type(self):
        """data_type 大小写不敏感。"""
        er = ExecuteResult(
            data=[{"x": 1}],
            columns=[ColumnInfo(name="x", data_type="float")],
            row_count=1,
        )
        with _patch_config():
            profiler = DataProfiler()
        profile = profiler.generate(er)
        assert profile.columns_profile[0].is_numeric is True

    def test_single_value_std_zero(self):
        """单值数值列 std 应为 0。"""
        er = ExecuteResult(
            data=[{"x": 42.0}],
            columns=[ColumnInfo(name="x", data_type="FLOAT")],
            row_count=1,
        )
        with _patch_config():
            profiler = DataProfiler()
        profile = profiler.generate(er)
        assert profile.columns_profile[0].numeric_stats.std == 0.0


# ═══════════════════════════════════════════════════════════════════════════
# 分类列统计测试
# ═══════════════════════════════════════════════════════════════════════════


class TestCategoricalColumn:
    """分类列统计正确性。"""

    def test_basic_categorical_stats(self):
        """基本分类列统计。"""
        er = ExecuteResult(
            data=[
                {"city": "北京"},
                {"city": "上海"},
                {"city": "北京"},
                {"city": "广州"},
                {"city": "北京"},
            ],
            columns=[ColumnInfo(name="city", data_type="STRING", is_dimension=True)],
            row_count=5,
        )
        with _patch_config():
            profiler = DataProfiler()
        profile = profiler.generate(er)

        col = profile.columns_profile[0]
        assert col.column_name == "city"
        assert col.is_numeric is False
        assert col.null_count == 0
        assert col.categorical_stats is not None
        assert col.categorical_stats.unique_count == 3
        # top_values 按频率降序
        assert len(col.categorical_stats.top_values) == 3
        assert col.categorical_stats.top_values[0]["value"] == "北京"
        assert col.categorical_stats.top_values[0]["count"] == 3

    def test_categorical_with_nulls(self):
        """含 None 值的分类列。"""
        er = ExecuteResult(
            data=[
                {"tag": "A"},
                {"tag": None},
                {"tag": "B"},
                {"tag": None},
            ],
            columns=[ColumnInfo(name="tag", data_type="STRING")],
            row_count=4,
        )
        with _patch_config():
            profiler = DataProfiler()
        profile = profiler.generate(er)

        col = profile.columns_profile[0]
        assert col.null_count == 2
        assert col.categorical_stats.unique_count == 2

    def test_top_values_limit(self):
        """top_values 应受 top_values_count 配置限制。"""
        mock_config = {"agents": {"data_profiler": {"top_values_count": 2}}}
        er = ExecuteResult(
            data=[{"c": f"v{i}"} for i in range(10)],
            columns=[ColumnInfo(name="c", data_type="STRING")],
            row_count=10,
        )
        with patch(
            "analytics_assistant.src.agents.insight.components.data_profiler.get_config",
            return_value=mock_config,
        ):
            profiler = DataProfiler()
        profile = profiler.generate(er)
        assert len(profile.columns_profile[0].categorical_stats.top_values) == 2


# ═══════════════════════════════════════════════════════════════════════════
# 空数据处理测试
# ═══════════════════════════════════════════════════════════════════════════


class TestEmptyData:
    """空数据处理。"""

    def test_empty_rows(self):
        """空数据应返回零值 DataProfile。"""
        er = ExecuteResult(
            data=[],
            columns=[
                ColumnInfo(name="a", data_type="STRING"),
                ColumnInfo(name="b", data_type="INTEGER"),
            ],
            row_count=0,
        )
        with _patch_config():
            profiler = DataProfiler()
        profile = profiler.generate(er)

        assert profile.row_count == 0
        assert profile.column_count == 2
        assert profile.columns_profile == []

    def test_no_columns(self):
        """无列定义。"""
        er = ExecuteResult(data=[], columns=[], row_count=0)
        with _patch_config():
            profiler = DataProfiler()
        profile = profiler.generate(er)

        assert profile.row_count == 0
        assert profile.column_count == 0


# ═══════════════════════════════════════════════════════════════════════════
# 单列失败跳过测试
# ═══════════════════════════════════════════════════════════════════════════


class TestColumnFailure:
    """单列计算失败时跳过并标记 error。"""

    def test_bad_column_skipped(self):
        """某列数据异常时应跳过并标记 error，不影响其他列。"""
        er = ExecuteResult(
            data=[
                {"good": 1.0, "bad": "not_a_number"},
                {"good": 2.0, "bad": "still_not"},
            ],
            columns=[
                ColumnInfo(name="good", data_type="FLOAT"),
                ColumnInfo(name="bad", data_type="FLOAT"),
            ],
            row_count=2,
        )
        with _patch_config():
            profiler = DataProfiler()

        # bad 列的值无法转为 float，但不会抛异常（会被当作 null）
        profile = profiler.generate(er)
        assert len(profile.columns_profile) == 2

        good_col = profile.columns_profile[0]
        assert good_col.numeric_stats is not None
        assert good_col.numeric_stats.min == 1.0

        bad_col = profile.columns_profile[1]
        # bad 列的值无法转 float，全部被计为 null
        assert bad_col.null_count == 2

    def test_exception_in_column_marked_error(self):
        """列计算抛异常时应标记 error 字段。"""
        er = ExecuteResult(
            data=[{"a": 1}, {"a": 2}],
            columns=[ColumnInfo(name="a", data_type="FLOAT")],
            row_count=2,
        )
        with _patch_config():
            profiler = DataProfiler()

        # Mock _profile_numeric_column 使其抛异常
        with patch.object(
            profiler, "_profile_numeric_column",
            side_effect=ValueError("计算错误"),
        ):
            profile = profiler.generate(er)

        assert len(profile.columns_profile) == 1
        col = profile.columns_profile[0]
        assert col.error == "计算错误"
        assert col.numeric_stats is None


# ═══════════════════════════════════════════════════════════════════════════
# 混合列测试
# ═══════════════════════════════════════════════════════════════════════════


class TestMixedColumns:
    """混合数值列和分类列。"""

    def test_mixed_columns(self):
        """同时包含数值列和分类列。"""
        er = ExecuteResult(
            data=[
                {"city": "北京", "sales": 100.0},
                {"city": "上海", "sales": 200.0},
                {"city": "北京", "sales": 150.0},
            ],
            columns=[
                ColumnInfo(name="city", data_type="STRING", is_dimension=True),
                ColumnInfo(name="sales", data_type="FLOAT", is_measure=True),
            ],
            row_count=3,
        )
        with _patch_config():
            profiler = DataProfiler()
        profile = profiler.generate(er)

        assert profile.row_count == 3
        assert profile.column_count == 2

        city_col = profile.columns_profile[0]
        assert city_col.is_numeric is False
        assert city_col.categorical_stats is not None

        sales_col = profile.columns_profile[1]
        assert sales_col.is_numeric is True
        assert sales_col.numeric_stats is not None
        assert sales_col.numeric_stats.min == 100.0
        assert sales_col.numeric_stats.max == 200.0
