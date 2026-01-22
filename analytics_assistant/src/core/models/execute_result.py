# -*- coding: utf-8 -*-
"""执行结果数据模型。

平台无关的查询执行结果。
这是从任何数据服务 API 调用返回的结果。
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


# 类型别名
RowValue = Union[str, int, float, bool, None]
RowData = Dict[str, RowValue]


class ColumnInfo(BaseModel):
    """查询结果中的列信息。
    
    提供结果集中每列的语义信息。
    """
    model_config = ConfigDict(extra="forbid")
    
    name: str = Field(description="列名")
    data_type: str = Field(default="STRING", description="列的数据类型")
    is_dimension: bool = Field(default=False, description="是否为维度列")
    is_measure: bool = Field(default=False, description="是否为度量列")
    is_computation: bool = Field(default=False, description="是否为计算列")


class ExecuteResult(BaseModel):
    """执行结果 - 平台无关的 Pydantic 模型。
    
    包含数据服务 API 调用的结果。
    
    属性：
        data: 行字典列表（原始 API 响应格式）
        columns: 带语义元数据的列信息
        row_count: 返回的行数
        execution_time_ms: 查询执行时间（毫秒）
        error: 查询失败时的错误消息
        query_id: API 响应中的查询 ID
        timestamp: 执行时间戳
    """
    model_config = ConfigDict(extra="forbid")
    
    data: List[RowData] = Field(
        default_factory=list,
        description="查询结果数据（行字典列表）"
    )
    columns: List[ColumnInfo] = Field(
        default_factory=list,
        description="带语义元数据的列信息"
    )
    row_count: int = Field(
        default=0,
        ge=0,
        description="返回的行数"
    )
    execution_time_ms: int = Field(
        default=0,
        ge=0,
        description="查询执行时间（毫秒）"
    )
    error: Optional[str] = Field(
        default=None,
        description="查询失败时的错误消息"
    )
    query_id: Optional[str] = Field(
        default=None,
        description="API 响应中的查询 ID"
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="执行时间戳（ISO 格式）"
    )
    
    def is_success(self) -> bool:
        """检查查询是否成功。"""
        return self.error is None
    
    def is_empty(self) -> bool:
        """检查结果是否为空。"""
        return self.row_count == 0 or not self.data
    
    def get_column_names(self) -> List[str]:
        """提取列名列表。"""
        return [col.name for col in self.columns]
    
    @property
    def rows(self) -> List[Dict[str, Any]]:
        """data 的别名（向后兼容）。"""
        return self.data


__all__ = [
    "ExecuteResult",
    "ColumnInfo",
    "RowData",
    "RowValue",
]
