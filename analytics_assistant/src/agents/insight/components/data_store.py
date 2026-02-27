# -*- coding: utf-8 -*-
"""
DataStore - 数据存储后端

将 ExecuteResult 数据持久化（大数据写文件，小数据留内存），
提供分批读取和按条件筛选接口。
"""
import json
import logging
from pathlib import Path
from typing import Any, Optional

from analytics_assistant.src.core.schemas.execute_result import (
    ColumnInfo,
    ExecuteResult,
    RowData,
)
from analytics_assistant.src.infra.config import get_config

logger = logging.getLogger(__name__)

class DataStore:
    """数据存储后端。

    根据数据量自动选择存储策略：
    - 行数 <= memory_threshold: 内存模式
    - 行数 > memory_threshold: 文件模式（JSON 临时文件）
    """

    # 配置默认值
    _DEFAULT_MEMORY_THRESHOLD = 1000
    _DEFAULT_TEMP_DIR = "analytics_assistant/data/temp"

    def __init__(self, store_id: str) -> None:
        """初始化 DataStore。

        Args:
            store_id: 存储标识（用于文件命名和清理）
        """
        self.store_id = store_id
        self._data: Optional[list[RowData]] = None
        self._columns: list[ColumnInfo] = []
        self._row_count: int = 0
        self._file_path: Optional[Path] = None
        self._is_file_mode: bool = False
        self._cached_file_data: Optional[list[RowData]] = None  # 文件模式缓存
        self._profile: Optional[Any] = None
        self._load_config()

    def _load_config(self) -> None:
        """从 YAML 配置加载参数。"""
        try:
            config = get_config()
            ds_config = config.get("agents", {}).get("data_store", {})
            self._memory_threshold = ds_config.get(
                "memory_threshold", self._DEFAULT_MEMORY_THRESHOLD
            )
            self._temp_dir = ds_config.get(
                "temp_dir", self._DEFAULT_TEMP_DIR
            )
        except Exception as e:
            logger.warning(f"加载 DataStore 配置失败，使用默认值: {e}")
            self._memory_threshold = self._DEFAULT_MEMORY_THRESHOLD
            self._temp_dir = self._DEFAULT_TEMP_DIR

    def save(self, execute_result: ExecuteResult) -> None:
        """保存 ExecuteResult 数据。

        根据 row_count 与 memory_threshold 比较，
        自动选择内存模式或文件模式。

        Args:
            execute_result: 查询执行结果
        """
        self._columns = list(execute_result.columns)
        self._row_count = execute_result.row_count
        self._cached_file_data = None  # 清除旧的文件缓存

        if self._row_count > self._memory_threshold:
            # 文件模式
            try:
                self._save_to_file(execute_result.data)
                self._is_file_mode = True
                self._data = None
                logger.info(
                    f"DataStore '{self.store_id}': 文件模式，"
                    f"row_count={self._row_count}, "
                    f"file={self._file_path}"
                )
            except (IOError, OSError) as e:
                # 文件写入失败，降级为内存模式
                logger.warning(
                    f"DataStore '{self.store_id}': 文件写入失败，"
                    f"降级为内存模式: {e}"
                )
                self._data = list(execute_result.data)
                self._is_file_mode = False
                self._file_path = None
        else:
            # 内存模式
            self._data = list(execute_result.data)
            self._is_file_mode = False
            logger.info(
                f"DataStore '{self.store_id}': 内存模式，"
                f"row_count={self._row_count}"
            )

    def _save_to_file(self, data: list[RowData]) -> None:
        """将数据写入 JSON 临时文件。

        Args:
            data: 数据行列表

        Raises:
            IOError: 文件写入失败
        """
        temp_dir = Path(self._temp_dir)
        temp_dir.mkdir(parents=True, exist_ok=True)
        self._file_path = temp_dir / f"data_store_{self.store_id}.json"
        self._file_path.write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )

    def _load_from_file(self) -> list[RowData]:
        """从 JSON 临时文件加载全部数据。

        Returns:
            数据行列表

        Raises:
            FileNotFoundError: 文件不存在
            json.JSONDecodeError: JSON 解析失败
        """
        if self._file_path is None:
            raise FileNotFoundError(
                f"DataStore '{self.store_id}': 文件路径未设置"
            )
        content = self._file_path.read_text(encoding="utf-8")
        return json.loads(content)

    def _get_all_data(self) -> list[RowData]:
        """获取全部数据（内存或文件）。

        文件模式下首次加载后缓存到内存，后续调用从缓存读取。

        Returns:
            数据行列表
        """
        if self._is_file_mode:
            if self._cached_file_data is not None:
                return self._cached_file_data
            try:
                self._cached_file_data = self._load_from_file()
                return self._cached_file_data
            except (FileNotFoundError, json.JSONDecodeError) as e:
                logger.error(
                    f"DataStore '{self.store_id}': 文件读取失败: {e}"
                )
                raise
        return self._data or []

    def read_batch(self, offset: int, limit: int) -> list[RowData]:
        """分批读取数据。

        Args:
            offset: 起始行偏移量
            limit: 读取行数

        Returns:
            数据行列表
        """
        data = self._get_all_data()
        return data[offset: offset + limit]

    def read_filtered(
        self, column: str, values: list[str]
    ) -> list[RowData]:
        """按列值筛选数据。

        Args:
            column: 列名
            values: 筛选值列表（OR 关系）

        Returns:
            满足条件的数据行列表
        """
        data = self._get_all_data()
        # 统一转字符串比较，避免类型不一致
        values_set = set(str(v) for v in values)
        return [
            row for row in data
            if column in row and str(row[column]) in values_set
        ]

    def get_column_stats(self, column: str) -> dict[str, Any]:
        """获取单列统计信息（委托 DataProfile）。

        从已注入的 DataProfile 中提取对应列的统计信息，
        避免重复计算。

        Args:
            column: 列名

        Returns:
            统计信息字典

        Raises:
            ValueError: DataProfile 未注入
            KeyError: 列名不存在
        """
        if self._profile is None:
            raise ValueError(
                f"DataStore '{self.store_id}': "
                "DataProfile 未注入，请先调用 set_profile()"
            )

        # 从 DataProfile 中查找对应列
        for col_profile in self._profile.columns_profile:
            if col_profile.column_name == column:
                return col_profile.model_dump()

        raise KeyError(
            f"DataStore '{self.store_id}': "
            f"列 '{column}' 不存在于 DataProfile 中"
        )

    def set_profile(self, profile: Any) -> None:
        """注入 DataProfile，供 get_column_stats 使用。

        Args:
            profile: 已生成的数据画像（DataProfile 实例）
        """
        self._profile = profile

    @property
    def columns(self) -> list[ColumnInfo]:
        """获取列信息列表。"""
        return self._columns

    @property
    def row_count(self) -> int:
        """获取总行数。"""
        return self._row_count

    @property
    def temp_dir(self) -> str:
        """获取临时文件目录。"""
        return self._temp_dir

    def cleanup(self) -> None:
        """清理临时文件。"""
        if self._file_path and self._file_path.exists():
            try:
                self._file_path.unlink()
                logger.info(
                    f"DataStore '{self.store_id}': 已清理临时文件 {self._file_path}"
                )
            except OSError as e:
                logger.warning(
                    f"DataStore '{self.store_id}': 清理临时文件失败: {e}"
                )
        self._data = None
        self._cached_file_data = None
        self._profile = None
