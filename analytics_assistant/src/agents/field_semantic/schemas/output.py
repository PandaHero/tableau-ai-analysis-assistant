# -*- coding: utf-8 -*-
"""
字段语义 Schema 定义

包含：
- FieldSemanticAttributes: 字段语义属性（统一维度和度量）
- FieldSemanticResult: 推断结果
- LLMFieldSemanticItem: LLM 输出的单个字段属性
- LLMFieldSemanticOutput: LLM 输出 schema（用于 stream_llm_structured）
"""
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

from analytics_assistant.src.core.schemas.enums import DimensionCategory, MeasureCategory

class FieldSemanticAttributes(BaseModel):
    """
    字段语义属性
    
    统一表示维度和度量字段的语义属性。根据 role 字段区分：
    - role="dimension": 维度字段，包含 category、level、granularity 等属性
    - role="measure": 度量字段，包含 measure_category 属性
    
    所有字段都包含 business_description 和 aliases，用于增强 RAG 检索。
    """
    
    # ─────────────────────────────────────────────────────────
    # 通用属性（所有字段）
    # ─────────────────────────────────────────────────────────
    
    role: Literal["dimension", "measure"] = Field(
        description="字段角色：dimension=维度，measure=度量"
    )
    business_description: str = Field(
        description="业务描述，一句话说明字段的业务含义"
    )
    aliases: list[str] = Field(
        default_factory=list,
        description="别名列表，用户可能使用的其他名称"
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="推断置信度 0-1"
    )
    reasoning: str = Field(
        description="推断理由"
    )
    
    # ─────────────────────────────────────────────────────────
    # 维度专属属性（role="dimension" 时有效）
    # ─────────────────────────────────────────────────────────
    
    category: Optional[DimensionCategory] = Field(
        default=None,
        description="维度类别：time/geography/product/customer/organization/channel/financial/other"
    )
    category_detail: Optional[str] = Field(
        default=None,
        description="详细类别，格式 'category-subcategory'"
    )
    level: Optional[int] = Field(
        default=None, ge=1, le=5,
        description="层级 1-5，1 最粗，5 最细"
    )
    granularity: Optional[Literal["coarsest", "coarse", "medium", "fine", "finest"]] = Field(
        default=None,
        description="粒度描述，与 level 对应"
    )
    parent_dimension: Optional[str] = Field(
        default=None,
        description="父维度字段名"
    )
    child_dimension: Optional[str] = Field(
        default=None,
        description="子维度字段名"
    )
    
    # ─────────────────────────────────────────────────────────
    # 度量专属属性（role="measure" 时有效）
    # ─────────────────────────────────────────────────────────
    
    measure_category: Optional[MeasureCategory] = Field(
        default=None,
        description="度量类别：revenue/cost/profit/quantity/ratio/count/average/other"
    )
    
    @model_validator(mode='after')
    def validate_role_specific_fields(self) -> 'FieldSemanticAttributes':
        """验证角色特定字段，确保必要字段有默认值"""
        if self.role == "dimension":
            # 维度字段：确保 category、level、granularity 有值
            if self.category is None:
                object.__setattr__(self, 'category', DimensionCategory.OTHER)
            if self.level is None:
                object.__setattr__(self, 'level', 3)
            if self.granularity is None:
                object.__setattr__(self, 'granularity', "medium")
            if self.category_detail is None:
                cat_value = self.category.value if self.category else "other"
                object.__setattr__(self, 'category_detail', f"{cat_value}-unknown")
            
            # 确保 level 和 granularity 一致
            level_to_granularity = {
                1: "coarsest", 2: "coarse", 3: "medium", 4: "fine", 5: "finest"
            }
            expected = level_to_granularity.get(self.level)
            if expected and self.granularity != expected:
                object.__setattr__(self, 'granularity', expected)
                
        elif self.role == "measure":
            # 度量字段：确保 measure_category 有值
            if self.measure_category is None:
                object.__setattr__(self, 'measure_category', MeasureCategory.OTHER)
        
        return self

class FieldSemanticResult(BaseModel):
    """字段语义推断结果"""
    field_semantic: dict[str, FieldSemanticAttributes] = Field(
        description="字段语义字典，key 为字段名，value 为 FieldSemanticAttributes"
    )

# ══════════════════════════════════════════════════════════════
# LLM 输出 Schema（用于 stream_llm_structured）
# ══════════════════════════════════════════════════════════════

class LLMFieldSemanticItem(BaseModel):
    """LLM 输出的单个字段语义属性（简化版，字符串类型）"""
    
    role: str = Field(description="字段角色: dimension/measure")
    business_description: str = Field(description="业务描述")
    aliases: list[str] = Field(default_factory=list, description="别名列表")
    confidence: float = Field(ge=0.0, le=1.0, description="置信度 0-1")
    reasoning: Optional[str] = Field(default=None, description="推断理由")
    
    # 维度属性（可选）
    category: Optional[str] = Field(default=None, description="维度类别")
    category_detail: Optional[str] = Field(default=None, description="详细类别")
    level: Optional[int] = Field(default=None, description="层级 1-5")
    granularity: Optional[str] = Field(default=None, description="粒度描述")
    
    # 度量属性（可选）
    measure_category: Optional[str] = Field(default=None, description="度量类别")

class LLMFieldSemanticOutput(BaseModel):
    """LLM 输出的字段语义结果（用于 stream_llm_structured）"""
    
    field_semantic: dict[str, LLMFieldSemanticItem] = Field(
        description="字段语义字典，key 为字段名"
    )
    
    def to_field_semantic_result(self) -> FieldSemanticResult:
        """转换为 FieldSemanticResult
        
        将 LLM 输出的字符串类型转换为枚举类型，并应用默认值。
        """
        result = {}
        
        for name, item in self.field_semantic.items():
            # 解析 role
            role = item.role.lower() if item.role else "dimension"
            if role not in ("dimension", "measure"):
                role = "dimension"
            
            # 构建基础属性
            attrs_dict = {
                "role": role,
                "business_description": item.business_description or name,
                "aliases": item.aliases or [],
                "confidence": item.confidence,
                "reasoning": item.reasoning or f"LLM 推断: {name}",
            }
            
            # 维度属性
            if role == "dimension":
                # 解析 category
                try:
                    category = DimensionCategory(item.category) if item.category else None
                except ValueError:
                    category = DimensionCategory.OTHER
                
                attrs_dict.update({
                    "category": category,
                    "category_detail": item.category_detail,
                    "level": item.level,
                    "granularity": item.granularity,
                })
            
            # 度量属性
            elif role == "measure":
                # 解析 measure_category
                try:
                    measure_category = MeasureCategory(item.measure_category) if item.measure_category else None
                except ValueError:
                    measure_category = MeasureCategory.OTHER
                
                attrs_dict["measure_category"] = measure_category
            
            # 创建 FieldSemanticAttributes（会自动应用默认值）
            result[name] = FieldSemanticAttributes(**attrs_dict)
        
        return FieldSemanticResult(field_semantic=result)

__all__ = [
    "FieldSemanticAttributes",
    "FieldSemanticResult",
    "LLMFieldSemanticItem",
    "LLMFieldSemanticOutput",
]
