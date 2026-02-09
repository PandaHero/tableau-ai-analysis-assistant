# -*- coding: utf-8 -*-
"""
DataStore 属性测试

使用 Hypothesis 验证 DataStore 的核心正确性属性：
- Property 1: 保存/读取往返一致性
- Property 2: 存储策略选择正确性
- Property 3: 筛选读取正确性
"""
import shutil
from pathlib import Path
from typing import Dict, List
from unittest.mock import patch

import pytest
from hypothesis import given, settings, strategies as st, assume

from analytics_assistant.src.agents.insight.components.data_store import DataStore
from analytics_assistant.src.core.schemas.execute_result import (
    ColumnInfo,
    ExecuteResult,
    RowData,
)


# ═══════════════════════════════════════════════════════════════════════════
# 测试策略（Generators）
# ═══════════════════════════════════════════════════════════════════════════

# 安全的字符串值策略（避免 Hypothesis 生成过于极端的字符串）
_safe_text = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
    min_size=1,
    max_size=20,
)

# 行值策略：字符串或数值
_row_value = st.one_of(
    _safe_text,
    st.integers(min_value=-10000, max_value=10000),
    st.floats(min_value=-10000, max_value=10000, allow_nan=False, allow_infinity=False),
)


@st.composite
def execute_result_strategy(draw: st.DrawFn) -> ExecuteResult:
    """生成随机有效的 ExecuteResult。

    列数 1~5，行数 0~50，每行数据与列名对齐。
    """
    num_cols = draw(st.integers(min_value=1, max_value=5))
    col_names = [f"col_{i}" for i in range(num_cols)]
    columns = [
        ColumnInfo(
            name=name,
            data_type=draw(st.sampled_from(["STRING", "INTEGER", "FLOAT"])),
            is_dimension=(i == 0),
            is_measure=(i > 0),
        )
        for i, name in enumerate(col_names)
    ]

    num_rows = draw(st.integers(min_value=0, max_value=50))
    data: List[RowData] = []
    for _ in range(num_rows):
        row: Dict[str, object] = {}
        for col in columns:
            if col.data_type == "STRING":
                row[col.name] = draw(_safe_text)
            elif col.data_type == "INTEGER":
                row[col.name] = draw(st.integers(min_value=-10000, max_value=10000))
            else:
                row[col.name] = draw(
                    st.floats(
                        min_value=-10000,
                        max_value=10000,
                        allow_nan=False,
                        allow_infinity=False,
                    )
                )
        data.append(row)

    return ExecuteResult(data=data, columns=columns, row_count=num_rows)


# ═══════════════════════════════════════════════════════════════════════════
# 测试辅助
# ═══════════════════════════════════════════════════════════════════════════

_TEMP_DIR = "analytics_assistant/data/temp_pbt"
_store_counter = 0


def _make_store(memory_threshold: int) -> DataStore:
    """创建带指定阈值的 DataStore 实例。"""
    global _store_counter
    _store_counter += 1
    with patch(
        "analytics_assistant.src.agents.insight.components.data_store.get_config",
        return_value={
            "agents": {
                "data_store": {
                    "memory_threshold": memory_threshold,
                    "temp_dir": _TEMP_DIR,
                }
            }
        },
    ):
        return DataStore(f"pbt_{_store_counter}")


@pytest.fixture(autouse=True)
def cleanup_temp_dir():
    """每个测试后清理临时目录。"""
    yield
    temp_path = Path(_TEMP_DIR)
    if temp_path.exists():
        shutil.rmtree(temp_path, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════════
# Property 1: 保存/读取往返一致性
# Validates: Requirements 1.1, 1.4
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty1SaveReadRoundtrip:
    """Property 1: 保存/读取往返一致性。

    **Validates: Requirements 1.1, 1.4**

    对于任意有效的 ExecuteResult，保存到 DataStore 后，
    通过 read_batch(0, row_count) 读取全部数据，
    返回的数据行应与原始 ExecuteResult.data 等价。
    """

    @given(er=execute_result_strategy())
    @settings(max_examples=100, deadline=5000)
    def test_roundtrip_memory_mode(self, er: ExecuteResult) -> None:
        """内存模式下保存/读取往返一致。"""
        # 阈值设为极大值，确保内存模式
        store = _make_store(memory_threshold=99999)
        store.save(er)

        result = store.read_batch(0, er.row_count)
        assert result == er.data
        assert store.row_count == er.row_count
        assert len(store.columns) == len(er.columns)

    @given(er=execute_result_strategy())
    @settings(max_examples=100, deadline=5000)
    def test_roundtrip_file_mode(self, er: ExecuteResult) -> None:
        """文件模式下保存/读取往返一致。"""
        # 阈值设为 0，确保文件模式（除非 row_count=0）
        assume(er.row_count > 0)
        store = _make_store(memory_threshold=0)
        store.save(er)

        result = store.read_batch(0, er.row_count)
        assert result == er.data
        assert store.row_count == er.row_count
        assert len(store.columns) == len(er.columns)

        store.cleanup()



# ═══════════════════════════════════════════════════════════════════════════
# Property 2: 存储策略选择正确性
# Validates: Requirements 1.2, 1.3
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty2StorageStrategy:
    """Property 2: 存储策略选择正确性。

    **Validates: Requirements 1.2, 1.3**

    对于任意有效的 ExecuteResult 和给定的 memory_threshold：
    - row_count > memory_threshold → 文件模式（临时文件存在）
    - row_count <= memory_threshold → 内存模式（无临时文件）
    """

    @given(
        er=execute_result_strategy(),
        threshold=st.integers(min_value=0, max_value=100),
    )
    @settings(max_examples=100, deadline=5000)
    def test_storage_strategy_selection(
        self, er: ExecuteResult, threshold: int
    ) -> None:
        """存储策略应根据 row_count 与 threshold 的关系正确选择。"""
        store = _make_store(memory_threshold=threshold)
        store.save(er)

        if er.row_count > threshold:
            # 应使用文件模式
            assert store._is_file_mode, (
                f"row_count={er.row_count} > threshold={threshold}，"
                f"应使用文件模式"
            )
            assert store._file_path is not None
            assert store._file_path.exists()
        else:
            # 应使用内存模式
            assert not store._is_file_mode, (
                f"row_count={er.row_count} <= threshold={threshold}，"
                f"应使用内存模式"
            )

        # 无论哪种模式，数据都应可读
        result = store.read_batch(0, er.row_count)
        assert result == er.data

        store.cleanup()


# ═══════════════════════════════════════════════════════════════════════════
# Property 3: 筛选读取正确性
# Validates: Requirements 1.5
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty3FilteredRead:
    """Property 3: 筛选读取正确性。

    **Validates: Requirements 1.5**

    对于任意已保存数据的 DataStore、任意列名和筛选值列表：
    - read_filtered 返回的每一行在指定列上的值都应在筛选值列表中
    - 原始数据中所有满足条件的行都应被返回（不遗漏）
    """

    @given(er=execute_result_strategy())
    @settings(max_examples=100, deadline=5000)
    def test_filtered_read_correctness(self, er: ExecuteResult) -> None:
        """筛选读取应返回且仅返回满足条件的行。"""
        assume(er.row_count > 0)
        assume(len(er.columns) > 0)

        store = _make_store(memory_threshold=99999)
        store.save(er)

        # 选择第一列作为筛选列
        filter_col = er.columns[0].name

        # 从实际数据中提取部分值作为筛选条件
        all_values = [str(row.get(filter_col, "")) for row in er.data]
        if not all_values:
            return

        # 取前半部分值作为筛选值（确保有匹配也可能有不匹配）
        unique_values = list(set(all_values))
        half = max(1, len(unique_values) // 2)
        filter_values = unique_values[:half]

        result = store.read_filtered(filter_col, filter_values)
        filter_set = set(filter_values)

        # 验证 1: 返回的每一行在指定列上的值都在筛选值列表中
        for row in result:
            assert str(row.get(filter_col, "")) in filter_set, (
                f"返回行的 {filter_col}={row.get(filter_col)} "
                f"不在筛选值 {filter_values} 中"
            )

        # 验证 2: 原始数据中所有满足条件的行都应被返回（不遗漏）
        expected = [
            row for row in er.data
            if str(row.get(filter_col, "")) in filter_set
        ]
        assert len(result) == len(expected), (
            f"筛选结果数量不一致: 返回 {len(result)} 行，"
            f"期望 {len(expected)} 行"
        )
