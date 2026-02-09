# -*- coding: utf-8 -*-
"""
Data Tools - Insight Agent 工具定义

定义 Insight Agent ReAct 循环中 LLM 可调用的工具集。
每个工具使用 @tool 装饰器定义，返回 JSON 格式字符串。
"""
import json
import logging
from typing import List

from langchain_core.tools import BaseTool, tool

from ..schemas.output import DataProfile
from .data_store import DataStore

logger = logging.getLogger(__name__)

# 停止信号常量
_FINISH_SIGNAL = "INSIGHT_ANALYSIS_COMPLETE"


def create_insight_tools(
    data_store: DataStore,
    data_profile: DataProfile,
) -> List[BaseTool]:
    """创建 Insight Agent 的工具集。

    工具列表：
    - read_data_batch: 分批读取数据（offset + limit）
    - read_filtered_data: 按列值筛选数据
    - get_column_stats: 获取单列统计
    - get_data_profile: 获取完整数据画像
    - finish_insight: 结束分析并输出洞察

    Args:
        data_store: 数据存储实例
        data_profile: 数据画像实例

    Returns:
        LangChain BaseTool 列表
    """

    @tool
    def read_data_batch(offset: int, limit: int) -> str:
        """分批读取数据。

        Args:
            offset: 起始行偏移量（从 0 开始）
            limit: 读取行数
        """
        try:
            rows = data_store.read_batch(offset, limit)
            return json.dumps(
                {"rows": rows, "count": len(rows), "offset": offset},
                ensure_ascii=False,
            )
        except Exception as e:
            logger.error(f"read_data_batch 失败: offset={offset}, limit={limit}, error={e}")
            return json.dumps({"error": str(e)}, ensure_ascii=False)

    @tool
    def read_filtered_data(column: str, values: List[str]) -> str:
        """按列值筛选数据。

        Args:
            column: 列名
            values: 筛选值列表（OR 关系）
        """
        try:
            rows = data_store.read_filtered(column, values)
            return json.dumps(
                {"rows": rows, "count": len(rows), "column": column, "values": values},
                ensure_ascii=False,
            )
        except Exception as e:
            logger.error(
                f"read_filtered_data 失败: column={column}, values={values}, error={e}"
            )
            return json.dumps({"error": str(e)}, ensure_ascii=False)

    @tool
    def get_column_stats(column: str) -> str:
        """获取单列统计信息（从 DataProfile 中提取）。

        Args:
            column: 列名
        """
        try:
            stats = data_store.get_column_stats(column)
            return json.dumps(stats, ensure_ascii=False)
        except (ValueError, KeyError) as e:
            logger.error(f"get_column_stats 失败: column={column}, error={e}")
            return json.dumps({"error": str(e)}, ensure_ascii=False)

    @tool
    def get_data_profile() -> str:
        """获取完整数据画像，包含所有列的统计信息。"""
        try:
            return data_profile.model_dump_json()
        except Exception as e:
            logger.error(f"get_data_profile 失败: error={e}")
            return json.dumps({"error": str(e)}, ensure_ascii=False)

    @tool
    def finish_insight() -> str:
        """结束数据分析。当你已经收集到足够的洞察信息时，调用此工具结束分析。"""
        return _FINISH_SIGNAL

    return [
        read_data_batch,
        read_filtered_data,
        get_column_stats,
        get_data_profile,
        finish_insight,
    ]
