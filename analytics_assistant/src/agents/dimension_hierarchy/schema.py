# -*- coding: utf-8 -*-
"""
维度层级 Schema 定义

包含：
- DimensionCategory: 维度类别枚举
- DimensionAttributes: 单个维度的层级属性
- DimensionHierarchyResult: 推断结果
- LLMDimensionOutput: LLM 输出 schema（用于 stream_llm_structured）
"""
from enum import Enum
from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field, model_validator


class DimensionCategory(str, Enum):
    """维度类别枚举"""
    TIME = "time"              # 时间维度
    GEOGRAPHY = "geography"    # 地理维度
    PRODUCT = "product"        # 产品维度
    CUSTOMER = "customer"      # 客户维度
    ORGANIZATION = "organization"  # 组织维度
    FINANCIAL = "financial"    # 财务维度
    CHANNEL = "channel"        # 渠道维度
    OTHER = "other"            # 其他


class DimensionAttributes(BaseModel):
    """
    单个维度的层级属性
    
    层级说明：
    - Level 1 (coarsest): 最粗粒度，如国家、年份、产品大类
    - Level 2 (coarse): 粗粒度，如省份、季度、产品类别
    - Level 3 (medium): 中等粒度，如城市、月份、子类别
    - Level 4 (fine): 细粒度，如区县、周、品牌
    - Level 5 (finest): 最细粒度，如地址、日期、SKU
    """
    
    category: DimensionCategory = Field(description="维度类别")
    category_detail: str = Field(description="详细类别，格式 'category-subcategory'")
    level: int = Field(ge=1, le=5, description="层级 1-5，1 最粗，5 最细")
    granularity: Literal["coarsest", "coarse", "medium", "fine", "finest"] = Field(
        description="粒度描述，与 level 对应"
    )
    unique_count: Optional[int] = Field(default=None, description="唯一值数量")
    sample_values: Optional[List[str]] = Field(default=None, description="样例值列表")
    level_confidence: float = Field(ge=0.0, le=1.0, description="推断置信度 0-1")
    reasoning: str = Field(description="推断理由")
    parent_dimension: Optional[str] = Field(default=None, description="父维度字段名")
    child_dimension: Optional[str] = Field(default=None, description="子维度字段名")
    
    @model_validator(mode='after')
    def validate_level_granularity(self) -> 'DimensionAttributes':
        """确保 level 和 granularity 一致"""
        level_to_granularity = {1: "coarsest", 2: "coarse", 3: "medium", 4: "fine", 5: "finest"}
        expected = level_to_granularity.get(self.level)
        if expected and self.granularity != expected:
            object.__setattr__(self, 'granularity', expected)
        return self


class DimensionHierarchyResult(BaseModel):
    """维度层级推断结果"""
    dimension_hierarchy: Dict[str, DimensionAttributes] = Field(
        description="维度层级字典，key 为字段名，value 为 DimensionAttributes"
    )


# ══════════════════════════════════════════════════════════════
# LLM 输出 Schema（用于 stream_llm_structured）
# ══════════════════════════════════════════════════════════════

class LLMDimensionItem(BaseModel):
    """LLM 输出的单个维度属性（简化版）"""
    category: str = Field(description="维度类别: time/geography/product/customer/organization/channel/financial/other")
    category_detail: str = Field(description="详细类别，格式 'category-subcategory'")
    level: int = Field(ge=1, le=5, description="层级 1-5，1 最粗，5 最细")
    granularity: str = Field(description="粒度: coarsest/coarse/medium/fine/finest")
    level_confidence: float = Field(ge=0.0, le=1.0, description="置信度 0-1")
    reasoning: Optional[str] = Field(default=None, description="推断理由")


class LLMDimensionOutput(BaseModel):
    """LLM 输出的维度层级结果（用于 stream_llm_structured）"""
    dimension_hierarchy: Dict[str, LLMDimensionItem] = Field(
        description="维度层级字典，key 为字段名"
    )
    
    def to_dimension_hierarchy_result(self) -> DimensionHierarchyResult:
        """转换为完整的 DimensionHierarchyResult"""
        result = {}
        for name, item in self.dimension_hierarchy.items():
            try:
                category = DimensionCategory(item.category)
            except ValueError:
                category = DimensionCategory.OTHER
            
            # 确保 granularity 有效
            valid_granularities = {"coarsest", "coarse", "medium", "fine", "finest"}
            granularity = item.granularity if item.granularity in valid_granularities else "medium"
            
            result[name] = DimensionAttributes(
                category=category,
                category_detail=item.category_detail,
                level=item.level,
                granularity=granularity,
                level_confidence=item.level_confidence,
                reasoning=item.reasoning or f"LLM 推断: {name}",
            )
        return DimensionHierarchyResult(dimension_hierarchy=result)


__all__ = [
    "DimensionCategory",
    "DimensionAttributes",
    "DimensionHierarchyResult",
    "LLMDimensionItem",
    "LLMDimensionOutput",
]
