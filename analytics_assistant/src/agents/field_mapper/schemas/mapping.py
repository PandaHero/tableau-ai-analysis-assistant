# -*- coding: utf-8 -*-
"""
FieldMapper 数据模型

包含：
- SingleSelectionResult: LLM 单字段选择结果
- AlternativeMapping: 备选映射
- FieldMapping: 单字段映射结果
- MappedQuery: 映射后的查询
"""
from typing import List, Dict, Optional
from typing_extensions import TypedDict
from pydantic import BaseModel, Field, ConfigDict, model_validator

from analytics_assistant.src.core.schemas import SemanticQuery


class SingleSelectionResult(BaseModel):
    """LLM 字段选择输出模型
    
    单个业务术语到技术字段的映射结果。
    
    填充顺序：
    1. business_term (必填)
    2. selected_field (必填，可为 null)
    3. confidence (必填)
    4. reasoning (必填)
    
    示例：
    - 匹配成功: {"business_term": "销售额", "selected_field": "SUM(Sales)", "confidence": 0.95, "reasoning": "语义精确匹配"}
    - 无匹配: {"business_term": "利润率", "selected_field": null, "confidence": 0.0, "reasoning": "候选中无利润率相关字段"}
    """
    
    business_term: str = Field(
        description="被映射的业务术语"
    )
    selected_field: Optional[str] = Field(
        default=None,
        description="最佳匹配的技术字段名，必须从候选列表中选择，无匹配时为 null"
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="选择置信度：0.9-1.0=高匹配, 0.7-0.9=中等, <0.7=低匹配, 0=无匹配"
    )
    reasoning: str = Field(
        description="选择理由，解释为什么选择此字段或为什么无匹配"
    )


class AlternativeMapping(TypedDict, total=False):
    """备选映射结果"""
    
    technical_field: str
    confidence: float
    reason: str


class FieldMapping(BaseModel):
    """单字段映射结果"""
    
    model_config = ConfigDict(extra="forbid")
    
    business_term: str = Field(min_length=1, description="SemanticQuery 中的业务术语")
    technical_field: str = Field(min_length=1, description="数据源中的技术字段名")
    confidence: float = Field(ge=0.0, le=1.0, description="映射置信度(0-1)")
    mapping_source: str = Field(description="映射来源")
    data_type: Optional[str] = Field(default=None, description="字段数据类型")
    date_format: Optional[str] = Field(default=None, description="STRING 类型日期字段的日期格式")
    category: Optional[str] = Field(default=None, description="维度类别")
    level: Optional[int] = Field(default=None, description="层级级别")
    granularity: Optional[str] = Field(default=None, description="粒度描述")
    alternatives: Optional[List[AlternativeMapping]] = Field(default=None, description="备选映射")


class MappedQuery(BaseModel):
    """映射后的查询 - FieldMapper 节点输出"""
    
    model_config = ConfigDict(extra="forbid")
    
    semantic_query: SemanticQuery = Field(description="原始语义查询")
    field_mappings: Dict[str, FieldMapping] = Field(description="字段映射字典")
    overall_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="整体置信度")
    low_confidence_fields: List[str] = Field(default_factory=list, description="低置信度字段列表")
    
    @model_validator(mode="after")
    def compute_overall_confidence(self) -> "MappedQuery":
        """计算整体置信度和低置信度字段"""
        if self.field_mappings:
            confidences = [m.confidence for m in self.field_mappings.values()]
            if self.overall_confidence is None:
                self.overall_confidence = min(confidences) if confidences else 1.0
            if not self.low_confidence_fields:
                self.low_confidence_fields = [
                    term for term, m in self.field_mappings.items() if m.confidence < 0.7
                ]
        elif self.overall_confidence is None:
            self.overall_confidence = 1.0
        return self
    
    def get_technical_field(self, business_term: str) -> Optional[str]:
        """获取业务术语对应的技术字段"""
        mapping = self.field_mappings.get(business_term)
        return mapping.technical_field if mapping else None
    
    def get_confidence(self, business_term: str) -> Optional[float]:
        """获取业务术语的映射置信度"""
        mapping = self.field_mappings.get(business_term)
        return mapping.confidence if mapping else None


__all__ = [
    "SingleSelectionResult",
    "AlternativeMapping",
    "FieldMapping",
    "MappedQuery",
]
