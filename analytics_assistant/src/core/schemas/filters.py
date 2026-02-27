# -*- coding: utf-8 -*-
"""语义层筛选器模型。平台无关的筛选器定义。"""

from datetime import date
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from analytics_assistant.src.core.schemas.enums import (
    FilterType,
    SortDirection,
    TextMatchType,
)

class Filter(BaseModel):
    """筛选器基类。"""
    model_config = ConfigDict(extra="forbid")
    
    field_name: str = Field(description="要筛选的字段名称")
    filter_type: FilterType = Field(description="筛选器类型")

class SetFilter(Filter):
    """集合筛选器 - 按特定值筛选。"""
    filter_type: FilterType = Field(default=FilterType.SET)
    
    values: list[Any] = Field(
        default_factory=list,
        description="要包含/排除的值列表"
    )
    exclude: bool = Field(
        default=False,
        description="是否排除模式（问题中包含'除了'、'不包括'等）"
    )
    include: bool = Field(
        default=True,
        description="是否包含模式（默认）"
    )
    
    def model_post_init(self, __context) -> None:
        """同步 include 和 exclude 字段。"""
        if not self.include:
            object.__setattr__(self, 'exclude', True)
        if self.exclude:
            object.__setattr__(self, 'include', False)

class DateRangeFilter(Filter):
    """日期范围筛选器。"""
    filter_type: FilterType = Field(default=FilterType.DATE_RANGE)
    
    start_date: Optional[date] = Field(
        default=None,
        description="开始日期（YYYY-MM-DD）"
    )
    end_date: Optional[date] = Field(
        default=None,
        description="结束日期（YYYY-MM-DD）"
    )

class NumericRangeFilter(Filter):
    """数值范围筛选器。"""
    filter_type: FilterType = Field(default=FilterType.NUMERIC_RANGE)
    
    min_value: Optional[float] = Field(default=None, description="最小值")
    max_value: Optional[float] = Field(default=None, description="最大值")
    include_min: bool = Field(default=True, description="是否包含最小值（>=）")
    include_max: bool = Field(default=True, description="是否包含最大值（<=）")

class TextMatchFilter(Filter):
    """文本匹配筛选器。"""
    filter_type: FilterType = Field(default=FilterType.TEXT_MATCH)
    
    pattern: str = Field(description="要匹配的文本模式")
    match_type: TextMatchType = Field(
        default=TextMatchType.CONTAINS,
        description="匹配类型"
    )

class TopNFilter(Filter):
    """Top N 筛选器 - 筛选前/后 N 条记录。"""
    filter_type: FilterType = Field(default=FilterType.TOP_N)
    
    n: int = Field(description="记录数量")
    by_field: str = Field(description="排序依据的度量字段")
    direction: SortDirection = Field(
        default=SortDirection.DESC,
        description="排序方向"
    )
