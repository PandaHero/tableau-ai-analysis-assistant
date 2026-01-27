# -*- coding: utf-8 -*-
"""
Semantic Parser Intermediate Models

中间数据模型定义：
- FieldCandidate: 字段检索候选结果
- FewShotExample: Few-shot 示例
"""
from typing import List, Dict, Any, Optional
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FieldCandidate(BaseModel):
    """字段检索候选结果
    
    FieldRetriever 返回的 Top-K 字段候选，包含字段元数据和检索置信度。
    
    示例：
    - field_name: "Sales"
    - field_caption: "销售额"
    - field_type: "measure"
    - confidence: 0.95
    """
    model_config = ConfigDict(extra="forbid")
    
    field_name: str = Field(
        description="字段技术名称"
    )
    field_caption: str = Field(
        description="字段显示名称"
    )
    field_type: str = Field(
        description="字段类型：dimension / measure"
    )
    data_type: str = Field(
        description="数据类型：string / number / date / datetime / boolean"
    )
    description: Optional[str] = Field(
        default=None,
        description="字段描述"
    )
    sample_values: Optional[List[str]] = Field(
        default=None,
        description="样例值列表（用于 Prompt）"
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="检索置信度：精确匹配 > 语义匹配"
    )
    match_type: str = Field(
        default="semantic",
        description="匹配类型：exact / semantic"
    )
    
    # 维度层级信息（可选）
    category: Optional[str] = Field(
        default=None,
        description="维度类别：time / geography / product / customer / organization / other"
    )
    level: Optional[int] = Field(
        default=None,
        description="层级级别：1=顶层, 2=高层, 3=中层, 4=低层, 5=明细"
    )
    granularity: Optional[str] = Field(
        default=None,
        description="粒度描述，如 '年' / '季度' / '月'"
    )
    drill_down_options: Optional[List[str]] = Field(
        default=None,
        description="下钻选项列表"
    )


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
    what: Dict[str, Any] = Field(
        description="目标度量（序列化的 What 对象）"
    )
    where: Dict[str, Any] = Field(
        description="维度和筛选器（序列化的 Where 对象）"
    )
    how: str = Field(
        description="计算复杂度：SIMPLE / COMPLEX"
    )
    computations: Optional[List[Dict[str, Any]]] = Field(
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
    question_embedding: Optional[List[float]] = Field(
        default=None,
        description="问题的向量表示（用于语义检索）"
    )


__all__ = [
    "FieldCandidate",
    "FewShotExample",
]
