"""SemanticQuery - The core output model of the semantic layer.

SemanticQuery is platform-agnostic and represents user intent.
Platform adapters convert it to platform-specific queries.
"""

from typing import List, Tuple
from pydantic import BaseModel, ConfigDict, Field

from .computations import Computation
from .fields import DimensionField, MeasureField, SortSpec
from .filters import (
    DateRangeFilter,
    Filter,
    NumericRangeFilter,
    SetFilter,
    TextMatchFilter,
    TopNFilter,
)


class SemanticQuery(BaseModel):
    """Core semantic query (platform-agnostic).
    
    <what>Final output of Semantic Parser Agent for DATA_QUERY intent</what>
    
    This model represents user intent in a platform-independent way.
    Platform adapters (Tableau, Power BI, SQL) convert this to platform-specific queries.
    
    排序说明：
    - 排序嵌入在 DimensionField.sort 和 MeasureField.sort 中
    - 使用 get_sorts() 方法获取所有排序字段
    """
    model_config = ConfigDict(extra="forbid")
    
    dimensions: list[DimensionField] | None = Field(
        default=None,
        description="Dimension fields in the query"
    )
    
    measures: list[MeasureField] | None = Field(
        default=None,
        description="Measure fields in the query"
    )
    
    computations: list[Computation] | None = Field(
        default=None,
        description="Complex computations (when how_type != SIMPLE)"
    )
    
    filters: list[
        SetFilter | DateRangeFilter | NumericRangeFilter | TextMatchFilter | TopNFilter
    ] | None = Field(
        default=None,
        description="Filter conditions"
    )
    
    row_limit: int | None = Field(
        default=None,
        description="Maximum number of rows to return"
    )
    
    def get_sorts(self) -> List[Tuple[str, SortSpec]]:
        """获取所有排序字段，按 priority 排序。
        
        Returns:
            List of (field_name, SortSpec) tuples, sorted by priority
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
