# -*- coding: utf-8 -*-
"""语义层计算模型。

包含 LOD 表达式和表计算的定义。
"""

from typing import Annotated, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

from analytics_assistant.src.core.schemas.enums import (
    AggregationType,
    RankStyle,
    RelativeTo,
    SortDirection,
)
from analytics_assistant.src.core.schemas.fields import DimensionField


# ═══════════════════════════════════════════════════════════════════════════
# LOD 表达式（详细级别）
# ═══════════════════════════════════════════════════════════════════════════

class LODFixed(BaseModel):
    """FIXED LOD - 在指定粒度计算指标，独立于查询。
    
    用于需要将指标"锚定"到特定维度的场景。
    示例：客户首次购买日期、客户生命周期价值
    """
    model_config = ConfigDict(extra="forbid")
    
    calc_type: Literal["LOD_FIXED"] = Field(default="LOD_FIXED")
    target: str = Field(description="要聚合的目标度量字段")
    dimensions: List[str] = Field(
        default_factory=list,
        description="定义固定聚合粒度的维度（空列表=全局聚合）"
    )
    aggregation: AggregationType = Field(description="聚合函数")
    alias: Optional[str] = Field(default=None, description="结果别名")
    
    @field_validator("target")
    @classmethod
    def target_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("target 不能为空")
        return v.strip()


class LODInclude(BaseModel):
    """INCLUDE LOD - 在比查询更细的粒度计算（添加维度）。
    
    用于查询粒度太粗，需要先下钻的场景。
    示例：按区域查询时计算订单平均金额
    """
    model_config = ConfigDict(extra="forbid")
    
    calc_type: Literal["LOD_INCLUDE"] = Field(default="LOD_INCLUDE")
    target: str = Field(description="要聚合的目标度量字段")
    dimensions: List[str] = Field(description="要添加到查询粒度的维度（至少一个）")
    aggregation: AggregationType = Field(description="聚合函数")
    alias: Optional[str] = Field(default=None, description="结果别名")
    
    @field_validator("target")
    @classmethod
    def target_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("target 不能为空")
        return v.strip()
    
    @field_validator("dimensions")
    @classmethod
    def dimensions_not_empty(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("LOD_INCLUDE 的 dimensions 不能为空")
        return [s.strip() for s in v if s and s.strip()]


class LODExclude(BaseModel):
    """EXCLUDE LOD - 在比查询更粗的粒度计算（移除维度）。
    
    用于查询粒度太细，需要上卷的场景。
    示例：按子类别查询时计算类别总计
    """
    model_config = ConfigDict(extra="forbid")
    
    calc_type: Literal["LOD_EXCLUDE"] = Field(default="LOD_EXCLUDE")
    target: str = Field(description="要聚合的目标度量字段")
    dimensions: List[str] = Field(description="要从查询粒度移除的维度（至少一个）")
    aggregation: AggregationType = Field(description="聚合函数")
    alias: Optional[str] = Field(default=None, description="结果别名")
    
    @field_validator("target")
    @classmethod
    def target_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("target 不能为空")
        return v.strip()
    
    @field_validator("dimensions")
    @classmethod
    def dimensions_not_empty(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("LOD_EXCLUDE 的 dimensions 不能为空")
        return [s.strip() for s in v if s and s.strip()]


# ═══════════════════════════════════════════════════════════════════════════
# 表计算 - 排名
# ═══════════════════════════════════════════════════════════════════════════

class RankCalc(BaseModel):
    """RANK - 对查询结果排名（可能有间隙：1,2,2,4）。"""
    model_config = ConfigDict(extra="forbid")
    
    calc_type: Literal["RANK"] = Field(default="RANK")
    target: str = Field(description="排名依据的度量字段")
    partition_by: List[DimensionField] = Field(
        default_factory=list,
        description="定义排名范围的维度（空=全局排名）"
    )
    direction: SortDirection = Field(
        default=SortDirection.DESC,
        description="排名方向（DESC=最高值排第1）"
    )
    rank_style: Optional[RankStyle] = Field(
        default=None,
        description="排名样式（默认：COMPETITION=1,2,2,4）"
    )
    top_n: Optional[int] = Field(default=None, description="排名后筛选前/后 N 名")
    alias: Optional[str] = Field(default=None, description="结果别名")
    
    @field_validator("target")
    @classmethod
    def target_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("target 不能为空")
        return v.strip()


class DenseRankCalc(BaseModel):
    """DENSE_RANK - 对查询结果排名（无间隙：1,2,2,3）。"""
    model_config = ConfigDict(extra="forbid")
    
    calc_type: Literal["DENSE_RANK"] = Field(default="DENSE_RANK")
    target: str = Field(description="排名依据的度量字段")
    partition_by: List[DimensionField] = Field(
        default_factory=list,
        description="定义排名范围的维度"
    )
    direction: SortDirection = Field(default=SortDirection.DESC, description="排名方向")
    top_n: Optional[int] = Field(default=None, description="筛选前/后 N 名")
    alias: Optional[str] = Field(default=None, description="结果别名")
    
    @field_validator("target")
    @classmethod
    def target_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("target 不能为空")
        return v.strip()


class PercentileCalc(BaseModel):
    """PERCENTILE - 查询结果的百分位排名（0-100%）。"""
    model_config = ConfigDict(extra="forbid")
    
    calc_type: Literal["PERCENTILE"] = Field(default="PERCENTILE")
    target: str = Field(description="目标度量字段")
    partition_by: List[DimensionField] = Field(
        default_factory=list,
        description="定义百分位范围的维度"
    )
    direction: SortDirection = Field(default=SortDirection.DESC, description="排序方向")
    alias: Optional[str] = Field(default=None, description="结果别名")
    
    @field_validator("target")
    @classmethod
    def target_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("target 不能为空")
        return v.strip()


# ═══════════════════════════════════════════════════════════════════════════
# 表计算 - 差异/比较
# ═══════════════════════════════════════════════════════════════════════════

class DifferenceCalc(BaseModel):
    """DIFFERENCE - 查询结果行之间的绝对差异。"""
    model_config = ConfigDict(extra="forbid")
    
    calc_type: Literal["DIFFERENCE"] = Field(default="DIFFERENCE")
    target: str = Field(description="目标度量字段")
    partition_by: List[DimensionField] = Field(
        default_factory=list,
        description="定义比较范围的维度"
    )
    relative_to: RelativeTo = Field(description="差异参考点")
    alias: Optional[str] = Field(default=None, description="结果别名")
    
    @field_validator("target")
    @classmethod
    def target_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("target 不能为空")
        return v.strip()


class PercentDifferenceCalc(BaseModel):
    """PERCENT_DIFFERENCE - 查询结果行之间的百分比变化。
    
    用于增长率、同比/环比等场景。
    """
    model_config = ConfigDict(extra="forbid")
    
    calc_type: Literal["PERCENT_DIFFERENCE"] = Field(default="PERCENT_DIFFERENCE")
    target: str = Field(description="目标度量字段")
    partition_by: List[DimensionField] = Field(
        default_factory=list,
        description="定义比较范围的维度"
    )
    relative_to: RelativeTo = Field(description="百分比变化参考点")
    alias: Optional[str] = Field(default=None, description="结果别名")
    
    @field_validator("target")
    @classmethod
    def target_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("target 不能为空")
        return v.strip()


# ═══════════════════════════════════════════════════════════════════════════
# 表计算 - 累计/运行
# ═══════════════════════════════════════════════════════════════════════════

class RunningTotalCalc(BaseModel):
    """RUNNING_TOTAL - 查询结果的累计聚合。
    
    用于累计总计、年初至今（YTD）等场景。
    """
    model_config = ConfigDict(extra="forbid")
    
    calc_type: Literal["RUNNING_TOTAL"] = Field(default="RUNNING_TOTAL")
    target: str = Field(description="目标度量字段")
    partition_by: List[DimensionField] = Field(
        default_factory=list,
        description="定义累计范围的维度"
    )
    aggregation: AggregationType = Field(
        default=AggregationType.SUM,
        description="累计聚合函数（仅支持 SUM/AVG/MIN/MAX/COUNT）"
    )
    restart_every: Optional[str] = Field(
        default=None,
        description="重新开始累计的维度（如 YTD 设为 'Year'）"
    )
    alias: Optional[str] = Field(default=None, description="结果别名")
    
    @field_validator("target")
    @classmethod
    def target_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("target 不能为空")
        return v.strip()


# ═══════════════════════════════════════════════════════════════════════════
# 表计算 - 移动窗口
# ═══════════════════════════════════════════════════════════════════════════

class MovingCalc(BaseModel):
    """MOVING_CALC - 查询结果的滑动窗口聚合。
    
    用于移动平均、滚动求和等场景。
    """
    model_config = ConfigDict(extra="forbid")
    
    calc_type: Literal["MOVING_CALC"] = Field(default="MOVING_CALC")
    target: str = Field(description="目标度量字段")
    partition_by: List[DimensionField] = Field(
        default_factory=list,
        description="定义窗口范围的维度"
    )
    aggregation: AggregationType = Field(
        default=AggregationType.AVG,
        description="窗口聚合函数（仅支持 SUM/AVG/MIN/MAX/COUNT）"
    )
    window_previous: int = Field(default=2, description="窗口中前面的行数")
    window_next: int = Field(default=0, description="窗口中后面的行数")
    include_current: bool = Field(default=True, description="是否包含当前行")
    alias: Optional[str] = Field(default=None, description="结果别名")
    
    @field_validator("target")
    @classmethod
    def target_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("target 不能为空")
        return v.strip()


# ═══════════════════════════════════════════════════════════════════════════
# 表计算 - 占比
# ═══════════════════════════════════════════════════════════════════════════

class PercentOfTotalCalc(BaseModel):
    """PERCENT_OF_TOTAL - 计算查询结果的占比。
    
    用于份额、占比、百分比等场景。
    """
    model_config = ConfigDict(extra="forbid")
    
    calc_type: Literal["PERCENT_OF_TOTAL"] = Field(default="PERCENT_OF_TOTAL")
    target: str = Field(description="目标度量字段")
    partition_by: List[DimensionField] = Field(
        default_factory=list,
        description="定义总计范围的维度（空=全局总计占比）"
    )
    level_of: Optional[str] = Field(default=None, description="特定聚合级别")
    alias: Optional[str] = Field(default=None, description="结果别名")
    
    @field_validator("target")
    @classmethod
    def target_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("target 不能为空")
        return v.strip()


# ═══════════════════════════════════════════════════════════════════════════
# 联合类型
# ═══════════════════════════════════════════════════════════════════════════

# LOD 表达式联合类型
LODExpression = Annotated[
    Union[LODFixed, LODInclude, LODExclude],
    Field(discriminator="calc_type")
]
"""所有 LOD 表达式类型的联合，通过 calc_type 区分。"""

# 表计算联合类型
TableCalc = Annotated[
    Union[
        RankCalc, DenseRankCalc, PercentileCalc,
        DifferenceCalc, PercentDifferenceCalc,
        RunningTotalCalc, MovingCalc, PercentOfTotalCalc
    ],
    Field(discriminator="calc_type")
]
"""所有表计算类型的联合，通过 calc_type 区分。"""

# 顶层计算联合类型（LOD + 表计算）
Computation = Annotated[
    Union[
        # LOD 类型
        LODFixed, LODInclude, LODExclude,
        # 表计算类型
        RankCalc, DenseRankCalc, PercentileCalc,
        DifferenceCalc, PercentDifferenceCalc,
        RunningTotalCalc, MovingCalc, PercentOfTotalCalc
    ],
    Field(discriminator="calc_type")
]
"""所有计算类型的联合（LOD + 表计算），通过 calc_type 区分。"""
