# -*- coding: utf-8 -*-
"""测试 query_builder 日期格式推断去硬编码优化。

覆盖：
1. _detect_date_format 样本值推断
2. _build_dimension_field STRING 日期字段
3. _build_date_range_filter 统一 DATEPARSE 路径
4. _build_date_match_fallback 降级
5. 表计算维度自动补充 DATEPARSE
"""

import pytest
from datetime import date

from analytics_assistant.src.platform.tableau.query_builder import TableauQueryBuilder
from analytics_assistant.src.core.schemas import (
    DateRangeFilter,
    DimensionField,
    DateGranularity,
)


@pytest.fixture
def builder():
    return TableauQueryBuilder()


# ── _detect_date_format ──────────────────────────────────────────────

class TestDetectDateFormat:
    """测试样本值日期格式推断。"""

    def test_yyyy_mm_dd(self):
        assert TableauQueryBuilder._detect_date_format(
            ["2024-01-15", "2024-02-20", "2023-12-01"]
        ) == "yyyy-MM-dd"

    def test_yyyymmdd(self):
        assert TableauQueryBuilder._detect_date_format(
            ["20240115", "20240220"]
        ) == "yyyyMMdd"

    def test_yyyy_mm(self):
        assert TableauQueryBuilder._detect_date_format(
            ["2024-01", "2024-02", "2023-12"]
        ) == "yyyy-MM"

    def test_yyyymm(self):
        assert TableauQueryBuilder._detect_date_format(
            ["202401", "202402", "202312"]
        ) == "yyyyMM"

    def test_yyyy(self):
        assert TableauQueryBuilder._detect_date_format(
            ["2024", "2023", "2022"]
        ) == "yyyy"

    def test_slash_format(self):
        assert TableauQueryBuilder._detect_date_format(
            ["2024/01/15", "2024/02/20"]
        ) == "yyyy/MM/dd"

    def test_dd_mm_yyyy(self):
        assert TableauQueryBuilder._detect_date_format(
            ["15-01-2024", "20-02-2024"]
        ) == "dd-MM-yyyy"

    def test_empty_returns_none(self):
        assert TableauQueryBuilder._detect_date_format([]) is None

    def test_single_value_returns_none(self):
        """单个样本不足以确认格式。"""
        assert TableauQueryBuilder._detect_date_format(["2024-01-15"]) is None

    def test_mixed_formats_returns_none(self):
        """混合格式无法匹配。"""
        assert TableauQueryBuilder._detect_date_format(
            ["2024-01-15", "202402", "hello"]
        ) is None

    def test_non_date_strings_returns_none(self):
        assert TableauQueryBuilder._detect_date_format(
            ["北京", "上海", "广州"]
        ) is None

    def test_none_values_filtered(self):
        """None 和空字符串被过滤。"""
        assert TableauQueryBuilder._detect_date_format(
            [None, "2024-01", "", "2024-02", None]
        ) == "yyyy-MM"

    def test_priority_long_format_first(self):
        """yyyyMMdd (8位) 优先于 yyyyMM (6位)。"""
        # 全是 8 位数字 → yyyyMMdd
        assert TableauQueryBuilder._detect_date_format(
            ["20240115", "20240220"]
        ) == "yyyyMMdd"


# ── _build_dimension_field ───────────────────────────────────────────

class TestBuildDimensionField:
    """测试维度字段构建（STRING 日期字段）。"""

    def test_string_date_with_samples(self, builder):
        """有样本值时，用 DATEPARSE + DATETRUNC。"""
        dim = DimensionField(field_name="dt", date_granularity=DateGranularity.MONTH)
        meta = {
            "dt": {
                "dataType": "STRING",
                "sample_values": ["2024-01-15", "2024-02-20", "2024-03-10"],
            }
        }
        result = builder._build_dimension_field(dim, meta)
        assert result["fieldCaption"] == "dt_month"
        assert "DATEPARSE('yyyy-MM-dd'" in result["calculation"]
        assert "DATETRUNC('month'" in result["calculation"]

    def test_string_date_yyyymm_samples(self, builder):
        """yyyyMM 格式样本值。"""
        dim = DimensionField(field_name="yyyymm", date_granularity=DateGranularity.MONTH)
        meta = {
            "yyyymm": {
                "dataType": "STRING",
                "sample_values": ["202401", "202402", "202312"],
            }
        }
        result = builder._build_dimension_field(dim, meta)
        assert "DATEPARSE('yyyyMM'" in result["calculation"]

    def test_string_date_no_samples_fallback(self, builder):
        """无样本值时，降级为原始字段。"""
        dim = DimensionField(field_name="dt", date_granularity=DateGranularity.MONTH)
        meta = {"dt": {"dataType": "STRING"}}
        result = builder._build_dimension_field(dim, meta)
        assert result == {"fieldCaption": "dt"}
        assert "calculation" not in result

    def test_native_date_field(self, builder):
        """原生 DATE 字段用 TRUNC 函数。"""
        dim = DimensionField(field_name="order_date", date_granularity=DateGranularity.YEAR)
        meta = {"order_date": {"dataType": "DATE"}}
        result = builder._build_dimension_field(dim, meta)
        assert result["fieldCaption"] == "order_date"
        assert result["function"] == "TRUNC_YEAR"


# ── _build_date_range_filter ─────────────────────────────────────────

class TestBuildDateRangeFilter:
    """测试日期范围过滤器构建。"""

    def test_string_field_with_samples_uses_dateparse(self, builder):
        """STRING 字段 + 有样本值 → DATEPARSE + QUANTITATIVE_DATE。"""
        f = DateRangeFilter(
            field_name="dt",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )
        meta = {
            "dt": {
                "dataType": "STRING",
                "sample_values": ["2024-01-15", "2024-02-20"],
            }
        }
        result = builder._build_date_range_filter(f, meta)
        assert result["filterType"] == "QUANTITATIVE_DATE"
        assert "calculation" in result["field"]
        assert "DATEPARSE('yyyy-MM-dd'" in result["field"]["calculation"]
        assert result["minDate"] == "2024-01-01"
        assert result["maxDate"] == "2024-12-31"

    def test_string_yyyymm_uses_dateparse_not_set(self, builder):
        """yyyyMM 格式也走 DATEPARSE，不再走 SET 枚举。"""
        f = DateRangeFilter(
            field_name="yyyymm",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 30),
        )
        meta = {
            "yyyymm": {
                "dataType": "STRING",
                "sample_values": ["202401", "202402", "202312"],
            }
        }
        result = builder._build_date_range_filter(f, meta)
        assert result["filterType"] == "QUANTITATIVE_DATE"
        assert "DATEPARSE('yyyyMM'" in result["field"]["calculation"]
        # 不应该是 SET filter
        assert result["filterType"] != "SET"

    def test_native_date_uses_fieldcaption(self, builder):
        """原生 DATE 字段直接用 fieldCaption。"""
        f = DateRangeFilter(
            field_name="order_date",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )
        meta = {"order_date": {"dataType": "DATE"}}
        result = builder._build_date_range_filter(f, meta)
        assert result["field"] == {"fieldCaption": "order_date"}
        assert result["filterType"] == "QUANTITATIVE_DATE"

    def test_string_no_samples_falls_back_to_match(self, builder):
        """STRING 字段无样本值 → 降级为 MATCH startsWith。"""
        f = DateRangeFilter(
            field_name="dt",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )
        meta = {"dt": {"dataType": "STRING"}}
        result = builder._build_date_range_filter(f, meta)
        assert result["filterType"] == "MATCH"
        assert result["startsWith"] == "2024"

    def test_string_no_samples_no_start_date_returns_none(self, builder):
        """无样本值且无 start_date → 返回 None。"""
        f = DateRangeFilter(
            field_name="dt",
            end_date=date(2024, 12, 31),
        )
        meta = {"dt": {"dataType": "STRING"}}
        result = builder._build_date_range_filter(f, meta)
        assert result is None

    def test_min_max_date_auto_fill(self, builder):
        """只有 start_date 时自动补全 maxDate。"""
        f = DateRangeFilter(
            field_name="dt",
            start_date=date(2024, 1, 1),
        )
        meta = {
            "dt": {
                "dataType": "STRING",
                "sample_values": ["2024-01-15", "2024-02-20"],
            }
        }
        result = builder._build_date_range_filter(f, meta)
        assert result["minDate"] == "2024-01-01"
        assert result["maxDate"] == "2099-12-31"
