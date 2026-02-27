# -*- coding: utf-8 -*-
"""
Semantic Parser Intermediate Models

中间数据模型定义：
- TimeHint: 时间提示数据类
- FieldCandidate: 从 core/schemas 导入的共享模型
- FewShotExample: Few-shot 示例
"""
from dataclasses import dataclass
from typing import Any, Optional
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# 从 core 导入共享的 FieldCandidate
from analytics_assistant.src.core.schemas.field_candidate import FieldCandidate

# ══════════════════════════════════════════════════════════════════════════════
# 时间提示
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class TimeHint:
    """时间提示数据类
    
    用于 TimeHintGenerator 生成的时间范围提示。
    """
    expression: str  # 原始时间表达式
    start: str       # 开始日期 (ISO 格式)
    end: str         # 结束日期 (ISO 格式)

# FieldCandidate 已从 core/schemas 导入，不再在此定义

class FewShotExample(BaseModel):
    """Few-shot 示例
    
    用于指导 LLM 生成的示例，包含完整的问题-输出映射。
    优先选择用户接受过的查询作为示例。
    
    示例：
    - question: "上个月各地区的销售额是多少？"
    - restated_question: "查询上个月（2024年12月）各地区的销售额"
    - what: {"measures": [{"field_name": "销售额", "aggregation": "SUM"}]}
    - where: {"dimensions": [{"field_name": "地区"}], "filters": [...]}
    """
    model_config = ConfigDict(extra="forbid")
    
    id: str = Field(
        description="示例唯一标识"
    )
    question: str = Field(
        description="用户原始问题"
    )
    restated_question: str = Field(
        description="完整独立的问题描述"
    )
    what: dict[str, Any] = Field(
        description="目标度量（序列化的 What 对象）"
    )
    where: dict[str, Any] = Field(
        description="维度和筛选器（序列化的 Where 对象）"
    )
    how: str = Field(
        description="计算复杂度：SIMPLE / COMPLEX"
    )
    computations: Optional[list[dict[str, Any]]] = Field(
        default=None,
        description="派生度量计算逻辑列表"
    )
    query: str = Field(
        description="生成的查询语句（VizQL/SQL）"
    )
    datasource_luid: str = Field(
        description="数据源 LUID"
    )
    accepted_count: int = Field(
        default=0,
        ge=0,
        description="用户接受次数（用于优先排序）"
    )
    created_at: datetime = Field(
        default_factory=datetime.now,
        description="创建时间"
    )
    updated_at: datetime = Field(
        default_factory=datetime.now,
        description="更新时间"
    )
    
    # 向量检索相关
    question_embedding: Optional[list[float]] = Field(
        default=None,
        description="问题的向量表示（用于语义检索）"
    )

__all__ = [
    "TimeHint",
    "FieldCandidate",
    "FewShotExample",
]
