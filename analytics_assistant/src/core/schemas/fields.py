# -*- coding: utf-8 -*-
"""语义层字段模型。平台无关的字段定义。"""

from pydantic import BaseModel, ConfigDict, Field

from analytics_assistant.src.core.schemas.enums import (
    AggregationType,
    DateGranularity,
    SortDirection,
)


class SortSpec(BaseModel):
    """排序规格。"""
    model_config = ConfigDict(extra="forbid")
    
    direction: SortDirection = Field(default=SortDirection.DESC, description="排序方向")
    priority: int = Field(default=0, description="排序优先级（0=主排序）")


class DimensionField(BaseModel):
    """维度字段。"""
    model_config = ConfigDict(extra="forbid")
    
    field_name: str = Field(description="字段名称（业务术语）")
    date_granularity: DateGranularity | None = Field(
        default=None, 
        description="日期粒度：年/季度/月/周/日"
    )
    alias: str | None = Field(default=None, description="显示名称")
    sort: SortSpec | None = Field(default=None, description="排序规格")


class MeasureField(BaseModel):
    """度量字段。"""
    model_config = ConfigDict(extra="forbid")
    
    field_name: str = Field(description="字段名称（业务术语）")
    aggregation: AggregationType | None = Field(
        default=AggregationType.SUM, 
        description="聚合函数（预聚合度量设为 null）"
    )
    alias: str | None = Field(default=None, description="显示名称")
    sort: SortSpec | None = Field(default=None, description="排序规格")
