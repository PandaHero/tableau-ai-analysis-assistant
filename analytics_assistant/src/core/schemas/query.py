# -*- coding: utf-8 -*-
"""SemanticQuery - 语义层的核心输出模型。

SemanticQuery 是平台无关的，表示用户意图。
平台适配器将其转换为平台特定的查询。
"""

from typing import List, Tuple
from pydantic import BaseModel, ConfigDict, Field

from analytics_assistant.src.core.schemas.computations import Computation
from analytics_assistant.src.core.schemas.fields import DimensionField, MeasureField, SortSpec
from analytics_assistant.src.core.schemas.filters import (
    DateRangeFilter,
    NumericRangeFilter,
    SetFilter,
    TextMatchFilter,
    TopNFilter,
)


class SemanticQuery(BaseModel):
    """核心语义查询（平台无关）。
    
    这是语义解析器 Agent 对 DATA_QUERY 意图的最终输出。
    此模型以平台无关的方式表示用户意图。
    平台适配器（Tableau、Power BI、SQL）将其转换为平台特定的查询。
    
    排序说明：
    - 排序嵌入在 DimensionField.sort 和 MeasureField.sort 中
    - 使用 get_sorts() 方法获取所有排序字段
    """
    model_config = ConfigDict(extra="forbid")
    
    dimensions: list[DimensionField] | None = Field(
        default=None,
        description="查询中的维度字段"
    )
    
    measures: list[MeasureField] | None = Field(
        default=None,
        description="查询中的度量字段"
    )
    
    computations: list[Computation] | None = Field(
        default=None,
        description="复杂计算（当 how_type != SIMPLE 时）"
    )
    
    filters: list[
        SetFilter | DateRangeFilter | NumericRangeFilter | TextMatchFilter | TopNFilter
    ] | None = Field(
        default=None,
        description="筛选条件"
    )
    
    row_limit: int | None = Field(
        default=None,
        description="返回的最大行数"
    )
    
    def get_sorts(self) -> List[Tuple[str, SortSpec]]:
        """获取所有排序字段，按 priority 排序。
        
        Returns:
            (字段名, SortSpec) 元组列表，按优先级排序
        """
        sorts = []
        
        # 收集维度排序
        for dim in self.dimensions or []:
            if dim.sort:
                sorts.append((dim.field_name, dim.sort))
        
        # 收集度量排序
        for measure in self.measures or []:
            if measure.sort:
                sorts.append((measure.field_name, measure.sort))
        
        # 按 priority 排序
        sorts.sort(key=lambda x: x[1].priority)
        return sorts
