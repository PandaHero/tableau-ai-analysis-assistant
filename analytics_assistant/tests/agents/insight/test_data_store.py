# -*- coding: utf-8 -*-
"""
DataStore 单元测试

测试内容：
- 内存模式保存/读取
- 文件模式保存/读取
- 分批读取（offset/limit 边界）
- 筛选读取
- 文件清理
- 文件写入失败降级
"""
import json
import pytest
from pathlib import Path
from unittest.mock import patch

from analytics_assistant.src.agents.insight.components.data_store import DataStore
from analytics_assistant.src.agents.insight.schemas.output import (
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


def _make_execute_result(
    row_count: int,
    columns: list = None,
) -> ExecuteResult:
    """构造测试用 ExecuteResult。"""
    if columns is None:
        columns = [
            ColumnInfo(name="city", data_type="STRING", is_dimension=True),
            ColumnInfo(name="sales", data_type="FLOAT", is_measure=True),
        ]
    data = [
        {"city": f"city_{i}", "sales": float(i * 100)}
        for i in range(row_count)
    ]
    return ExecuteResult(
        data=data,
        columns=columns,
        row_count=row_count,
    )


def _make_data_profile() -> DataProfile:
    """构造测试用 DataProfile。"""
    return DataProfile(
        row_count=5,
        column_count=2,
        columns_profile=[
            ColumnProfile(
                column_name="city",
                data_type="STRING",
                is_numeric=False,
                null_count=0,
            ),
            ColumnProfile(
                column_name="sales",
                data_type="FLOAT",
                is_numeric=True,
                null_count=0,
                numeric_stats=NumericStats(
                    min=0.0, max=400.0, avg=200.0, median=200.0, std=141.42
                ),
            ),
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════
# 内存模式测试
# ═══════════════════════════════════════════════════════════════════════════


class TestMemoryMode:
    """内存模式保存/读取测试。"""

    @patch(
        "analytics_assistant.src.agents.insight.components.data_store.get_config",
        return_value={"agents": {"data_store": {"memory_threshold": 1000}}},
    )
    def test_save_and_read_all(self, mock_config):
        """保存后读取全部数据应一致。"""
        store = DataStore("test_mem")
        er = _make_execute_result(5)
        store.save(er)

        assert store.row_count == 5
        assert len(store.columns) == 2
        assert not store._is_file_mode

        data = store.read_batch(0, 5)
        assert len(data) == 5
        assert data == er.data

    @patch(
        "analytics_assistant.src.agents.insight.components.data_store.get_config",
        return_value={"agents": {"data_store": {"memory_threshold": 1000}}},
    )
    def test_empty_data(self, mock_config):
        """空数据保存/读取。"""
        store = DataStore("test_empty")
        er = _make_execute_result(0)
        store.save(er)

        assert store.row_count == 0
        assert store.read_batch(0, 10) == []


# ═══════════════════════════════════════════════════════════════════════════
# 文件模式测试
# ═══════════════════════════════════════════════════════════════════════════


class TestFileMode:
    """文件模式保存/读取测试。"""

    @patch(
        "analytics_assistant.src.agents.insight.components.data_store.get_config",
        return_value={
            "agents": {
                "data_store": {
                    "memory_threshold": 3,
                    "temp_dir": "analytics_assistant/data/temp_test",
                }
            }
        },
    )
    def test_save_triggers_file_mode(self, mock_config):
        """行数超过阈值时应使用文件模式。"""
        store = DataStore("test_file")
        er = _make_execute_result(5)
        store.save(er)

        assert store._is_file_mode
        assert store._file_path is not None
        assert store._file_path.exists()

        # 读取验证
        data = store.read_batch(0, 5)
        assert len(data) == 5
        assert data == er.data

        # 清理
        store.cleanup()
        assert not store._file_path.exists()

    @patch(
        "analytics_assistant.src.agents.insight.components.data_store.get_config",
        return_value={
            "agents": {
                "data_store": {
                    "memory_threshold": 3,
                    "temp_dir": "analytics_assistant/data/temp_test",
                }
            }
        },
    )
    def test_file_cleanup(self, mock_config):
        """cleanup 应删除临时文件。"""
        store = DataStore("test_cleanup")
        er = _make_execute_result(5)
        store.save(er)

        file_path = store._file_path
        assert file_path.exists()

        store.cleanup()
        assert not file_path.exists()
        assert store._data is None


# ═══════════════════════════════════════════════════════════════════════════
# 分批读取测试
# ═══════════════════════════════════════════════════════════════════════════


class TestReadBatch:
    """分批读取边界测试。"""

    @patch(
        "analytics_assistant.src.agents.insight.components.data_store.get_config",
        return_value={"agents": {"data_store": {"memory_threshold": 1000}}},
    )
    def test_offset_and_limit(self, mock_config):
        """offset/limit 分批读取。"""
        store = DataStore("test_batch")
        er = _make_execute_result(10)
        store.save(er)

        batch1 = store.read_batch(0, 3)
        assert len(batch1) == 3
        assert batch1[0]["city"] == "city_0"

        batch2 = store.read_batch(3, 3)
        assert len(batch2) == 3
        assert batch2[0]["city"] == "city_3"

    @patch(
        "analytics_assistant.src.agents.insight.components.data_store.get_config",
        return_value={"agents": {"data_store": {"memory_threshold": 1000}}},
    )
    def test_offset_beyond_data(self, mock_config):
        """offset 超出数据范围应返回空列表。"""
        store = DataStore("test_beyond")
        er = _make_execute_result(5)
        store.save(er)

        assert store.read_batch(100, 10) == []

    @patch(
        "analytics_assistant.src.agents.insight.components.data_store.get_config",
        return_value={"agents": {"data_store": {"memory_threshold": 1000}}},
    )
    def test_limit_exceeds_remaining(self, mock_config):
        """limit 超出剩余行数应返回剩余全部。"""
        store = DataStore("test_exceed")
        er = _make_execute_result(5)
        store.save(er)

        data = store.read_batch(3, 100)
        assert len(data) == 2


# ═══════════════════════════════════════════════════════════════════════════
# 筛选读取测试
# ═══════════════════════════════════════════════════════════════════════════


class TestReadFiltered:
    """筛选读取测试。"""

    @patch(
        "analytics_assistant.src.agents.insight.components.data_store.get_config",
        return_value={"agents": {"data_store": {"memory_threshold": 1000}}},
    )
    def test_filter_by_column(self, mock_config):
        """按列值筛选。"""
        store = DataStore("test_filter")
        er = _make_execute_result(10)
        store.save(er)

        result = store.read_filtered("city", ["city_0", "city_5"])
        assert len(result) == 2
        cities = {row["city"] for row in result}
        assert cities == {"city_0", "city_5"}

    @patch(
        "analytics_assistant.src.agents.insight.components.data_store.get_config",
        return_value={"agents": {"data_store": {"memory_threshold": 1000}}},
    )
    def test_filter_no_match(self, mock_config):
        """筛选无匹配应返回空列表。"""
        store = DataStore("test_no_match")
        er = _make_execute_result(5)
        store.save(er)

        result = store.read_filtered("city", ["nonexistent"])
        assert result == []

    @patch(
        "analytics_assistant.src.agents.insight.components.data_store.get_config",
        return_value={"agents": {"data_store": {"memory_threshold": 1000}}},
    )
    def test_filter_numeric_as_string(self, mock_config):
        """数值列筛选时应支持字符串比较。"""
        store = DataStore("test_num_filter")
        er = _make_execute_result(5)
        store.save(er)

        # sales 值为 0.0, 100.0, 200.0, 300.0, 400.0
        result = store.read_filtered("sales", ["200.0"])
        assert len(result) == 1
        assert result[0]["sales"] == 200.0


# ═══════════════════════════════════════════════════════════════════════════
# get_column_stats 测试
# ═══════════════════════════════════════════════════════════════════════════


class TestGetColumnStats:
    """get_column_stats 测试。"""

    @patch(
        "analytics_assistant.src.agents.insight.components.data_store.get_config",
        return_value={"agents": {"data_store": {"memory_threshold": 1000}}},
    )
    def test_without_profile_raises(self, mock_config):
        """未注入 DataProfile 时应抛出 ValueError。"""
        store = DataStore("test_no_profile")
        er = _make_execute_result(5)
        store.save(er)

        with pytest.raises(ValueError, match="DataProfile 未注入"):
            store.get_column_stats("city")

    @patch(
        "analytics_assistant.src.agents.insight.components.data_store.get_config",
        return_value={"agents": {"data_store": {"memory_threshold": 1000}}},
    )
    def test_with_profile(self, mock_config):
        """注入 DataProfile 后应返回列统计。"""
        store = DataStore("test_with_profile")
        er = _make_execute_result(5)
        store.save(er)
        store.set_profile(_make_data_profile())

        stats = store.get_column_stats("sales")
        assert stats["column_name"] == "sales"
        assert stats["is_numeric"] is True

    @patch(
        "analytics_assistant.src.agents.insight.components.data_store.get_config",
        return_value={"agents": {"data_store": {"memory_threshold": 1000}}},
    )
    def test_nonexistent_column_raises(self, mock_config):
        """查询不存在的列应抛出 KeyError。"""
        store = DataStore("test_bad_col")
        er = _make_execute_result(5)
        store.save(er)
        store.set_profile(_make_data_profile())

        with pytest.raises(KeyError, match="不存在"):
            store.get_column_stats("nonexistent")


# ═══════════════════════════════════════════════════════════════════════════
# 文件写入失败降级测试
# ═══════════════════════════════════════════════════════════════════════════


class TestFileFallback:
    """文件写入失败降级为内存模式。"""

    @patch(
        "analytics_assistant.src.agents.insight.components.data_store.get_config",
        return_value={
            "agents": {
                "data_store": {
                    "memory_threshold": 3,
                    "temp_dir": "analytics_assistant/data/temp_test",
                }
            }
        },
    )
    def test_fallback_to_memory(self, mock_config):
        """文件写入失败时应降级为内存模式。"""
        store = DataStore("test_fallback")
        er = _make_execute_result(5)

        # Mock _save_to_file 使其抛出 IOError，模拟文件写入失败
        with patch.object(store, "_save_to_file", side_effect=IOError("磁盘已满")):
            store.save(er)

        # 应降级为内存模式
        assert not store._is_file_mode
        assert store._data is not None

        # 数据仍可读取
        data = store.read_batch(0, 5)
        assert len(data) == 5
        assert data == er.data
