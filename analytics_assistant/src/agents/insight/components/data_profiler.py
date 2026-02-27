# -*- coding: utf-8 -*-
"""
DataProfiler - 数据画像生成器

纯计算组件，从 ExecuteResult 生成 DataProfile。
为每列计算统计信息，帮助 LLM 了解数据整体特征。
"""
import logging
import statistics
from collections import Counter
from typing import Any

from analytics_assistant.src.core.schemas.execute_result import (
    ColumnInfo,
    ExecuteResult,
)
from analytics_assistant.src.infra.config import get_config

from ..schemas.output import (
    CategoricalStats,
    ColumnProfile,
    DataProfile,
    NumericStats,
)

logger = logging.getLogger(__name__)

# 数值类型集合（大写，用于忽略大小写比较）
_NUMERIC_TYPES: set[str] = {
    "INTEGER", "INT", "REAL", "FLOAT",
    "DOUBLE", "DECIMAL", "NUMBER", "NUMERIC",
}

class DataProfiler:
    """数据画像生成器。

    为每列计算统计信息，帮助 LLM 了解数据整体特征。
    """

    _DEFAULT_TOP_VALUES_COUNT = 10

    def __init__(self) -> None:
        """初始化 DataProfiler，从 app.yaml 读取配置。"""
        self._load_config()

    def _load_config(self) -> None:
        """从 YAML 配置加载参数。"""
        try:
            config = get_config()
            dp_config = config.get("agents", {}).get("data_profiler", {})
            self._top_values_count = dp_config.get(
                "top_values_count", self._DEFAULT_TOP_VALUES_COUNT
            )
        except Exception as e:
            logger.warning(f"加载 DataProfiler 配置失败，使用默认值: {e}")
            self._top_values_count = self._DEFAULT_TOP_VALUES_COUNT

    def generate(self, execute_result: ExecuteResult) -> DataProfile:
        """生成数据画像。

        Args:
            execute_result: 查询执行结果

        Returns:
            DataProfile 对象
        """
        if execute_result.row_count == 0 or not execute_result.data:
            return DataProfile(
                row_count=0,
                column_count=len(execute_result.columns),
                columns_profile=[],
            )

        columns_profile: list[ColumnProfile] = []
        for col_info in execute_result.columns:
            try:
                # 提取该列的所有值
                values = [
                    row.get(col_info.name) for row in execute_result.data
                ]
                if self._is_numeric_column(col_info):
                    profile = self._profile_numeric_column(
                        values, col_info.name, col_info.data_type
                    )
                else:
                    profile = self._profile_categorical_column(
                        values, col_info.name, col_info.data_type
                    )
                columns_profile.append(profile)
            except Exception as e:
                # 单列计算失败时跳过并标记 error 字段
                logger.warning(
                    f"DataProfiler: 列 '{col_info.name}' 统计计算失败: {e}"
                )
                columns_profile.append(
                    ColumnProfile(
                        column_name=col_info.name,
                        data_type=col_info.data_type,
                        is_numeric=self._is_numeric_column(col_info),
                        error=str(e),
                    )
                )

        return DataProfile(
            row_count=execute_result.row_count,
            column_count=len(execute_result.columns),
            columns_profile=columns_profile,
        )

    def _is_numeric_column(self, column_info: ColumnInfo) -> bool:
        """判断列是否为数值列。

        基于 ColumnInfo.data_type 判断，而非 is_dimension/is_measure。
        数值类型包括：INTEGER、INT、REAL、FLOAT、DOUBLE、DECIMAL、NUMBER、NUMERIC。
        判断时忽略大小写。

        Args:
            column_info: 列信息

        Returns:
            是否为数值列
        """
        return column_info.data_type.upper() in _NUMERIC_TYPES

    def _profile_numeric_column(
        self,
        values: list[Any],
        column_name: str,
        data_type: str,
    ) -> ColumnProfile:
        """计算数值列统计信息。

        Args:
            values: 列值列表
            column_name: 列名
            data_type: 数据类型

        Returns:
            ColumnProfile 对象
        """
        # 过滤 None 值，统计空值数量
        null_count = sum(1 for v in values if v is None)
        numeric_values = []
        for v in values:
            if v is not None:
                try:
                    numeric_values.append(float(v))
                except (ValueError, TypeError):
                    null_count += 1

        if not numeric_values:
            return ColumnProfile(
                column_name=column_name,
                data_type=data_type,
                is_numeric=True,
                null_count=null_count,
                numeric_stats=NumericStats(),
            )

        sorted_values = sorted(numeric_values)
        return ColumnProfile(
            column_name=column_name,
            data_type=data_type,
            is_numeric=True,
            null_count=null_count,
            numeric_stats=NumericStats(
                min=sorted_values[0],
                max=sorted_values[-1],
                avg=statistics.mean(numeric_values),
                median=statistics.median(numeric_values),
                std=statistics.stdev(numeric_values) if len(numeric_values) > 1 else 0.0,
            ),
        )

    def _profile_categorical_column(
        self,
        values: list[Any],
        column_name: str,
        data_type: str,
    ) -> ColumnProfile:
        """计算分类列统计信息。

        Args:
            values: 列值列表
            column_name: 列名
            data_type: 数据类型

        Returns:
            ColumnProfile 对象
        """
        null_count = sum(1 for v in values if v is None)
        non_null_values = [v for v in values if v is not None]

        # 去重计数
        unique_count = len(set(non_null_values))

        # Top values 按频率降序
        counter = Counter(non_null_values)
        top_values = [
            {"value": value, "count": count}
            for value, count in counter.most_common(self._top_values_count)
        ]

        return ColumnProfile(
            column_name=column_name,
            data_type=data_type,
            is_numeric=False,
            null_count=null_count,
            categorical_stats=CategoricalStats(
                unique_count=unique_count,
                top_values=top_values,
            ),
        )
