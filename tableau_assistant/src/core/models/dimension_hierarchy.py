# -*- coding: utf-8 -*-
"""
Dimension Hierarchy Models

维度层级相关的数据模型。

包含:
- DimensionAttributes: 单个维度的层级属性
- DimensionHierarchyResult: 维度层级推断结果
"""
from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


class DimensionAttributes(BaseModel):
    """单个维度的层级属性
    
    <what>维度的层级属性，包含类别、级别、父子关系</what>
    
    <fill_order>
    1. category (ALWAYS)
    2. category_detail (ALWAYS)
    3. level (ALWAYS)
    4. granularity (ALWAYS, auto-match level)
    5. unique_count (ALWAYS)
    6. sample_values (ALWAYS)
    7. level_confidence (ALWAYS)
    8. reasoning (ALWAYS)
    9. parent_dimension (if certain)
    10. child_dimension (if certain)
    </fill_order>
    
    <examples>
    省份: {"category": "geography", "level": 2, "granularity": "coarse", "parent_dimension": null, "child_dimension": "城市"}
    月份: {"category": "time", "level": 3, "granularity": "medium", "parent_dimension": "季度", "child_dimension": "日期"}
    </examples>
    
    <anti_patterns>
    ❌ level 和 granularity 不匹配: level=2 但 granularity="finest"
    ❌ 不确定时猜测 parent/child: 应设为 null
    </anti_patterns>
    """
    
    category: Literal["geography", "time", "product", "customer", "organization", "financial", "other"] = Field(
        description="""<what>维度类别</what>
<when>ALWAYS required</when>
<rule>
- geography: 地理位置（省份、城市、区县）
- time: 时间（年、月、日、季度）
- product: 产品（产品、类别、品牌）
- customer: 客户（客户、客户类型）
- organization: 组织（部门、团队）
- financial: 财务（科目、成本中心）
- other: 其他
</rule>"""
    )
    
    category_detail: str = Field(
        description="""<what>详细类别描述</what>
<when>ALWAYS required</when>
<rule>格式: 'category-subcategory'，如 'geography-province'</rule>"""
    )
    
    level: int = Field(
        ge=1,
        le=5,
        description="""<what>层级级别</what>
<when>ALWAYS required</when>
<rule>
- Level 1 (coarsest): 国家、年、顶级类别
- Level 2 (coarse): 省份、季度、类别
- Level 3 (medium): 城市、月、子类别
- Level 4 (fine): 区县、周、品牌
- Level 5 (finest): 地址、日期、SKU
</rule>"""
    )
    
    granularity: Literal["coarsest", "coarse", "medium", "fine", "finest"] = Field(
        description="""<what>粒度描述</what>
<when>ALWAYS required</when>
<rule>必须与 level 匹配: 1=coarsest, 2=coarse, 3=medium, 4=fine, 5=finest</rule>
<dependency>与 level 一一对应</dependency>"""
    )
    
    unique_count: int = Field(
        description="""<what>唯一值数量</what>
<when>ALWAYS required</when>"""
    )
    
    parent_dimension: Optional[str] = Field(
        default=None,
        description="""<what>父维度字段名（更粗粒度）</what>
<when>确定时填写，不确定时为 null</when>
<rule>父维度 unique_count 更小，语义更宽泛</rule>
<must_not>不确定时猜测（应设为 null）</must_not>"""
    )
    
    child_dimension: Optional[str] = Field(
        default=None,
        description="""<what>子维度字段名（更细粒度）</what>
<when>确定时填写，不确定时为 null</when>
<rule>子维度 unique_count 更大，语义更具体</rule>
<must_not>不确定时猜测（应设为 null）</must_not>"""
    )
    
    sample_values: List[str] = Field(
        description="""<what>样本值列表</what>
<when>ALWAYS required</when>
<rule>最多 10 个</rule>"""
    )
    
    level_confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="""<what>层级判断置信度</what>
<when>ALWAYS required</when>
<rule>0.9-1.0=明确语义, 0.7-0.9=较好匹配, 0.5-0.7=模糊, <0.5=非常不确定</rule>"""
    )
    
    reasoning: str = Field(
        description="""<what>推理说明</what>
<when>ALWAYS required</when>
<rule>解释为什么分配此层级/类别</rule>"""
    )
    
    @field_validator('level')
    @classmethod
    def validate_level(cls, v):
        """确保 level 在 1-5 之间"""
        if v > 5:
            return 5
        elif v < 1:
            return 1
        return v
    
    @model_validator(mode='after')
    def validate_level_granularity_match(self) -> 'DimensionAttributes':
        """确保 level 和 granularity 一致"""
        level_to_granularity = {
            1: "coarsest",
            2: "coarse",
            3: "medium",
            4: "fine",
            5: "finest"
        }
        expected = level_to_granularity.get(self.level)
        if expected and self.granularity != expected:
            object.__setattr__(self, 'granularity', expected)
        return self


class DimensionHierarchyResult(BaseModel):
    """维度层级推断结果
    
    <what>所有维度的层级属性字典</what>
    
    <fill_order>
    1. dimension_hierarchy (ALWAYS)
    </fill_order>
    
    <examples>
    {"dimension_hierarchy": {"省份": {"category": "geography", "level": 2, ...}, "城市": {"category": "geography", "level": 3, "parent_dimension": "省份", ...}}}
    </examples>
    """
    
    dimension_hierarchy: Dict[str, DimensionAttributes] = Field(
        description="""<what>维度层级字典</what>
<when>ALWAYS required</when>
<rule>key 为字段名，value 为 DimensionAttributes</rule>"""
    )


__all__ = [
    "DimensionAttributes",
    "DimensionHierarchyResult",
]
