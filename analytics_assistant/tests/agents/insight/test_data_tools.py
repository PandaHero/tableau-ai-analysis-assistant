# -*- coding: utf-8 -*-
"""
Data Tools 单元测试

测试内容：
- 各工具的返回格式正确性
- finish_insight 返回停止信号
- 错误场景处理
"""
import json
import pytest
from unittest.mock import patch

from analytics_assistant.src.agents.insight.components.data_store import DataStore
from analytics_assistant.src.agents.insight.components.data_tools import (
    _FINISH_SIGNAL,
    create_insight_tools,
)
from analytics_assistant.src.agents.insight.schemas.output import (
    CategoricalStats,
    ColumnProfile,
    DataProfile,
    NumericStats,
)
from analytics_assistant.src.core.schemas.execute_result import (
    ColumnInfo,
    ExecuteResult,
)


# ═══════════════════════════════════════════════════════════════════════════
# 测试辅助
# ═══════════════════════════════════════════════════════════════════════════


def _make_store_and_profile():
    """构造已保存数据的 DataStore 和 DataProfile。"""
    columns = [
        ColumnInfo(name="city", data_type="STRING", is_dimension=True),
        ColumnInfo(name="sales", data_type="FLOAT", is_measure=True),
    ]
    data = [
        {"city": "北京", "sales": 100.0},
        {"city": "上海", "sales": 200.0},
        {"city": "广州", "sales": 150.0},
        {"city": "北京", "sales": 300.0},
        {"city": "深圳", "sales": 250.0},
    ]
    execute_result = ExecuteResult(
        data=data, columns=columns, row_count=5,
    )

    with patch(
        "analytics_assistant.src.agents.insight.components.data_store.get_config",
        return_value={"agents": {"data_store": {"memory_threshold": 10000}}},
    ):
        store = DataStore(store_id="test_tools")
    store.save(execute_result)

    profile = DataProfile(
        row_count=5,
        column_count=2,
        columns_profile=[
            ColumnProfile(
                column_name="city",
                data_type="STRING",
                is_numeric=False,
                categorical_stats=CategoricalStats(
                    unique_count=4,
                    top_values=[
                        {"value": "北京", "count": 2},
                        {"value": "上海", "count": 1},
                        {"value": "广州", "count": 1},
                        {"value": "深圳", "count": 1},
                    ],
                ),
            ),
            ColumnProfile(
                column_name="sales",
                data_type="FLOAT",
                is_numeric=True,
                numeric_stats=NumericStats(
                    min=100.0, max=300.0, avg=200.0, median=200.0, std=70.71,
                ),
            ),
        ],
    )
    store.set_profile(profile)
    return store, profile


def _get_tool_by_name(tools, name):
    """按名称查找工具。"""
    for t in tools:
        if t.name == name:
            return t
    raise ValueError(f"工具 '{name}' 不存在")


# ═══════════════════════════════════════════════════════════════════════════
# 测试：create_insight_tools 返回 5 个工具
# ═══════════════════════════════════════════════════════════════════════════


class TestCreateInsightTools:
    """测试工具集创建。"""

    def test_returns_five_tools(self):
        """应返回 5 个工具。"""
        store, profile = _make_store_and_profile()
        tools = create_insight_tools(store, profile)
        assert len(tools) == 5

    def test_tool_names(self):
        """工具名称应正确。"""
        store, profile = _make_store_and_profile()
        tools = create_insight_tools(store, profile)
        names = {t.name for t in tools}
        assert names == {
            "read_data_batch",
            "read_filtered_data",
            "get_column_stats",
            "get_data_profile",
            "finish_insight",
        }


# ═══════════════════════════════════════════════════════════════════════════
# 测试：read_data_batch
# ═══════════════════════════════════════════════════════════════════════════


class TestReadDataBatch:
    """测试 read_data_batch 工具。"""

    def test_basic_read(self):
        """基本分批读取。"""
        store, profile = _make_store_and_profile()
        tools = create_insight_tools(store, profile)
        tool = _get_tool_by_name(tools, "read_data_batch")

        result = tool.invoke({"offset": 0, "limit": 2})
        parsed = json.loads(result)
        assert parsed["count"] == 2
        assert parsed["offset"] == 0
        assert len(parsed["rows"]) == 2
        assert parsed["rows"][0]["city"] == "北京"

    def test_offset_beyond_data(self):
        """offset 超出数据范围应返回空。"""
        store, profile = _make_store_and_profile()
        tools = create_insight_tools(store, profile)
        tool = _get_tool_by_name(tools, "read_data_batch")

        result = tool.invoke({"offset": 100, "limit": 10})
        parsed = json.loads(result)
        assert parsed["count"] == 0
        assert parsed["rows"] == []

    def test_read_all(self):
        """读取全部数据。"""
        store, profile = _make_store_and_profile()
        tools = create_insight_tools(store, profile)
        tool = _get_tool_by_name(tools, "read_data_batch")

        result = tool.invoke({"offset": 0, "limit": 100})
        parsed = json.loads(result)
        assert parsed["count"] == 5


# ═══════════════════════════════════════════════════════════════════════════
# 测试：read_filtered_data
# ═══════════════════════════════════════════════════════════════════════════


class TestReadFilteredData:
    """测试 read_filtered_data 工具。"""

    def test_filter_single_value(self):
        """按单个值筛选。"""
        store, profile = _make_store_and_profile()
        tools = create_insight_tools(store, profile)
        tool = _get_tool_by_name(tools, "read_filtered_data")

        result = tool.invoke({"column": "city", "values": ["北京"]})
        parsed = json.loads(result)
        assert parsed["count"] == 2
        assert all(r["city"] == "北京" for r in parsed["rows"])

    def test_filter_multiple_values(self):
        """按多个值筛选（OR 关系）。"""
        store, profile = _make_store_and_profile()
        tools = create_insight_tools(store, profile)
        tool = _get_tool_by_name(tools, "read_filtered_data")

        result = tool.invoke({"column": "city", "values": ["北京", "上海"]})
        parsed = json.loads(result)
        assert parsed["count"] == 3

    def test_filter_no_match(self):
        """筛选无匹配应返回空。"""
        store, profile = _make_store_and_profile()
        tools = create_insight_tools(store, profile)
        tool = _get_tool_by_name(tools, "read_filtered_data")

        result = tool.invoke({"column": "city", "values": ["不存在"]})
        parsed = json.loads(result)
        assert parsed["count"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# 测试：get_column_stats
# ═══════════════════════════════════════════════════════════════════════════


class TestGetColumnStats:
    """测试 get_column_stats 工具。"""

    def test_numeric_column(self):
        """获取数值列统计。"""
        store, profile = _make_store_and_profile()
        tools = create_insight_tools(store, profile)
        tool = _get_tool_by_name(tools, "get_column_stats")

        result = tool.invoke({"column": "sales"})
        parsed = json.loads(result)
        assert parsed["is_numeric"] is True
        assert parsed["numeric_stats"]["min"] == 100.0
        assert parsed["numeric_stats"]["max"] == 300.0

    def test_categorical_column(self):
        """获取分类列统计。"""
        store, profile = _make_store_and_profile()
        tools = create_insight_tools(store, profile)
        tool = _get_tool_by_name(tools, "get_column_stats")

        result = tool.invoke({"column": "city"})
        parsed = json.loads(result)
        assert parsed["is_numeric"] is False
        assert parsed["categorical_stats"]["unique_count"] == 4

    def test_nonexistent_column(self):
        """不存在的列应返回错误。"""
        store, profile = _make_store_and_profile()
        tools = create_insight_tools(store, profile)
        tool = _get_tool_by_name(tools, "get_column_stats")

        result = tool.invoke({"column": "nonexistent"})
        parsed = json.loads(result)
        assert "error" in parsed


# ═══════════════════════════════════════════════════════════════════════════
# 测试：get_data_profile
# ═══════════════════════════════════════════════════════════════════════════


class TestGetDataProfile:
    """测试 get_data_profile 工具。"""

    def test_returns_valid_json(self):
        """应返回有效的 DataProfile JSON。"""
        store, profile = _make_store_and_profile()
        tools = create_insight_tools(store, profile)
        tool = _get_tool_by_name(tools, "get_data_profile")

        result = tool.invoke({})
        parsed = json.loads(result)
        assert parsed["row_count"] == 5
        assert parsed["column_count"] == 2
        assert len(parsed["columns_profile"]) == 2

    def test_roundtrip_with_model(self):
        """返回的 JSON 应能反序列化回 DataProfile。"""
        store, profile = _make_store_and_profile()
        tools = create_insight_tools(store, profile)
        tool = _get_tool_by_name(tools, "get_data_profile")

        result = tool.invoke({})
        restored = DataProfile.model_validate_json(result)
        assert restored.row_count == profile.row_count
        assert restored.column_count == profile.column_count


# ═══════════════════════════════════════════════════════════════════════════
# 测试：finish_insight
# ═══════════════════════════════════════════════════════════════════════════


class TestFinishInsight:
    """测试 finish_insight 工具。"""

    def test_returns_stop_signal(self):
        """应返回停止信号。"""
        store, profile = _make_store_and_profile()
        tools = create_insight_tools(store, profile)
        tool = _get_tool_by_name(tools, "finish_insight")

        result = tool.invoke({})
        assert result == _FINISH_SIGNAL

    def test_signal_is_string(self):
        """停止信号应为字符串。"""
        store, profile = _make_store_and_profile()
        tools = create_insight_tools(store, profile)
        tool = _get_tool_by_name(tools, "finish_insight")

        result = tool.invoke({})
        assert isinstance(result, str)
