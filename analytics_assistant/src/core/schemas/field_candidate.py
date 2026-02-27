# -*- coding: utf-8 -*-
"""
字段候选模型

跨模块共享的字段检索候选结果模型。
用于 FieldRetriever、FieldMapper 等模块。
"""
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

class FieldCandidate(BaseModel):
    """字段检索候选结果
    
    RAG 检索返回的 Top-K 字段候选，包含字段元数据和检索置信度。
    
    用于：
    - semantic_parser: FieldRetriever 返回的候选
    - field_mapper: RAG 检索的候选字段
    
    示例：
    - field_name: "Sales"
    - field_caption: "销售额"
    - role: "measure"
    - confidence: 0.95
    """
    model_config = ConfigDict(extra="ignore")
    
    # 基础字段信息
    field_name: str = Field(
        description="字段技术名称"
    )
    field_caption: str = Field(
        default="",
        description="字段显示名称"
    )
    role: str = Field(
        default="",
        description="字段角色：dimension / measure"
    )
    data_type: str = Field(
        default="",
        description="数据类型：string / number / date / datetime / boolean"
    )
    description: Optional[str] = Field(
        default=None,
        description="字段描述"
    )
    sample_values: Optional[list[str]] = Field(
        default=None,
        description="样例值列表（用于 Prompt）"
    )
    
    # 检索分数
    confidence: float = Field(
        ge=0.0, le=1.0,
        default=1.0,
        description="检索置信度：精确匹配 > 语义匹配"
    )
    
    # 检索来源信息
    source: str = Field(
        default="full_schema",
        description="检索来源：full_schema / rule_match / embedding / hierarchy_expand"
    )
    rank: int = Field(
        default=1,
        description="排名位置"
    )
    match_type: str = Field(
        default="semantic",
        description="匹配类型：exact / semantic"
    )
    
    # 维度类别和层级
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
    
    # 额外元数据
    formula: Optional[str] = Field(
        default=None,
        description="计算公式（度量字段）"
    )
    logical_table_caption: Optional[str] = Field(
        default=None,
        description="逻辑表名称"
    )
    drill_down_options: Optional[list[str]] = Field(
        default=None,
        description="下钻选项列表"
    )
    
    # 维度层级扩展字段
    hierarchy_level: Optional[int] = Field(
        default=None,
        description="层级级别（1-5，1最粗，5最细）"
    )
    hierarchy_category: Optional[str] = Field(
        default=None,
        description="维度类别（geography/time/product/organization/other）"
    )
    parent_dimension: Optional[str] = Field(
        default=None,
        description="父维度字段名"
    )
    child_dimension: Optional[str] = Field(
        default=None,
        description="子维度字段名"
    )
    
    # 字段语义信息（来自 FieldSemantic 推断）
    business_description: Optional[str] = Field(
        default=None,
        description="业务描述，一句话说明字段的业务含义"
    )
    aliases: Optional[list[str]] = Field(
        default=None,
        description="别名列表，用户可能使用的其他名称"
    )
    measure_category: Optional[str] = Field(
        default=None,
        description="度量类别：revenue/cost/profit/quantity/ratio/count/average/other"
    )

__all__ = [
    "FieldCandidate",
]
