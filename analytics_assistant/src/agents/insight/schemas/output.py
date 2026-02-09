# -*- coding: utf-8 -*-
"""
Insight Agent 输出数据模型

定义洞察生成和数据画像相关的 Pydantic 模型。
所有模型支持 JSON 序列化往返一致性。
"""
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ═══════════════════════════════════════════════════════════════════════════
# 枚举类型
# ═══════════════════════════════════════════════════════════════════════════


class FindingType(str, Enum):
    """洞察发现类型。"""

    ANOMALY = "anomaly"
    TREND = "trend"
    COMPARISON = "comparison"
    DISTRIBUTION = "distribution"
    CORRELATION = "correlation"


class AnalysisLevel(str, Enum):
    """分析层级（参考 Fabric Copilot 分层洞察策略）。

    - DESCRIPTIVE: 描述性，发生了什么（统计摘要、排名、极值）
    - DIAGNOSTIC: 诊断性，为什么会这样（异常原因、趋势归因、交叉分析）
    """

    DESCRIPTIVE = "descriptive"
    DIAGNOSTIC = "diagnostic"


# ═══════════════════════════════════════════════════════════════════════════
# 洞察输出模型
# ═══════════════════════════════════════════════════════════════════════════


class Finding(BaseModel):
    """单条洞察发现。"""

    model_config = ConfigDict(extra="forbid")

    finding_type: FindingType = Field(description="发现类型")
    analysis_level: AnalysisLevel = Field(
        default=AnalysisLevel.DESCRIPTIVE,
        description="分析层级：descriptive（描述性）或 diagnostic（诊断性）",
    )
    description: str = Field(description="发现描述")
    supporting_data: Dict[str, Any] = Field(
        default_factory=dict, description="支撑数据"
    )
    confidence: float = Field(ge=0.0, le=1.0, description="置信度")


class InsightOutput(BaseModel):
    """洞察输出。"""

    model_config = ConfigDict(extra="forbid")

    findings: List[Finding] = Field(
        min_length=1, description="发现列表（至少一条）"
    )
    summary: str = Field(description="洞察摘要")
    overall_confidence: float = Field(
        ge=0.0, le=1.0, description="整体置信度"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 数据画像模型
# ═══════════════════════════════════════════════════════════════════════════


class NumericStats(BaseModel):
    """数值列统计信息。"""

    model_config = ConfigDict(extra="forbid")

    min: Optional[float] = None
    max: Optional[float] = None
    avg: Optional[float] = None
    median: Optional[float] = None
    std: Optional[float] = None


class CategoricalStats(BaseModel):
    """分类列统计信息。"""

    model_config = ConfigDict(extra="forbid")

    unique_count: int = 0
    top_values: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="按频率排序的 top 值，格式: [{'value': x, 'count': n}]",
    )


class ColumnProfile(BaseModel):
    """单列画像。"""

    model_config = ConfigDict(extra="forbid")

    column_name: str = Field(description="列名")
    data_type: str = Field(description="数据类型")
    is_numeric: bool = Field(default=False, description="是否为数值列")
    null_count: int = Field(default=0, description="空值数量")
    numeric_stats: Optional[NumericStats] = None
    categorical_stats: Optional[CategoricalStats] = None
    error: Optional[str] = Field(
        default=None, description="计算失败时的错误信息"
    )


class DataProfile(BaseModel):
    """数据画像。"""

    model_config = ConfigDict(extra="forbid")

    row_count: int = Field(ge=0, description="总行数")
    column_count: int = Field(ge=0, description="总列数")
    columns_profile: List[ColumnProfile] = Field(
        default_factory=list, description="各列画像"
    )
