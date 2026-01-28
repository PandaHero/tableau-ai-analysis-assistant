# -*- coding: utf-8 -*-
"""
FieldMapper 数据模型

包含：
- FieldCandidate: 从 core/schemas 导入的共享模型
- SingleSelectionResult: LLM 单字段选择结果
- AlternativeMapping: 备选映射
- FieldMapping: 单字段映射结果
- MappedQuery: 映射后的查询
"""
from typing import List, Dict, Optional, Any
from typing_extensions import TypedDict
from pydantic import BaseModel, Field as PydanticField, ConfigDict, model_validator

from analytics_assistant.src.agents.semantic_parser.schemas.output import SemanticOutput
# 从 core 导入共享的 FieldCandidate
from analytics_assistant.src.core.schemas.field_candidate import FieldCandidate


# ══════════════════════════════════════════════════════════════════════════════
# LLM 输出模型
# ══════════════════════════════════════════════════════════════════════════════

class SingleSelectionResult(BaseModel):
    """LLM 字段选择输出模型
    
    用于 stream_llm_structured 的输出 schema。
    """
    
    business_term: str = PydanticField(
        description="被映射的业务术语"
    )
    selected_field: Optional[str] = PydanticField(
        default=None,
        description="最佳匹配的技术字段名，必须从候选列表中选择，无匹配时为 null"
    )
    confidence: float = PydanticField(
        ge=0.0,
        le=1.0,
        description="选择置信度：0.9-1.0=高匹配, 0.7-0.9=中等, <0.7=低匹配, 0=无匹配"
    )
    reasoning: str = PydanticField(
        description="选择理由，解释为什么选择此字段或为什么无匹配"
    )


# ══════════════════════════════════════════════════════════════════════════════
# 映射结果模型
# ══════════════════════════════════════════════════════════════════════════════

class AlternativeMapping(TypedDict, total=False):
    """备选映射结果"""
    technical_field: str
    confidence: float
    reason: str


class FieldMapping(BaseModel):
    """单字段映射结果
    
    用于：
    1. map_field() 方法的返回值
    2. MappedQuery 中的字段映射
    
    Attributes:
        business_term: 原始业务术语
        technical_field: 映射到的技术字段名（None 表示未找到）
        confidence: 映射置信度 (0-1)
        mapping_source: 映射来源
            - "rag_direct": RAG 高置信度直接匹配
            - "rag_llm_fallback": RAG + LLM 回退
            - "cache_hit": 缓存命中
            - "llm_only": 仅 LLM 匹配
            - "error": 映射失败
        reasoning: 映射理由
        alternatives: 备选映射列表
        category: 维度类别
        level: 层级级别
        granularity: 粒度描述
        latency_ms: 映射耗时（毫秒）
    """
    
    model_config = ConfigDict(extra="ignore")
    
    business_term: str = PydanticField(description="业务术语")
    technical_field: Optional[str] = PydanticField(default=None, description="技术字段名，None 表示未找到")
    confidence: float = PydanticField(ge=0.0, le=1.0, description="映射置信度(0-1)")
    mapping_source: str = PydanticField(description="映射来源")
    reasoning: Optional[str] = PydanticField(default=None, description="映射理由")
    alternatives: Optional[List[AlternativeMapping]] = PydanticField(default=None, description="备选映射")
    data_type: Optional[str] = PydanticField(default=None, description="字段数据类型")
    date_format: Optional[str] = PydanticField(default=None, description="日期格式")
    category: Optional[str] = PydanticField(default=None, description="维度类别")
    level: Optional[int] = PydanticField(default=None, description="层级级别")
    granularity: Optional[str] = PydanticField(default=None, description="粒度描述")
    latency_ms: int = PydanticField(default=0, description="映射耗时（毫秒）")


class MappedQuery(BaseModel):
    """映射后的查询 - FieldMapper 节点输出"""
    
    model_config = ConfigDict(extra="forbid")
    
    semantic_output: SemanticOutput = PydanticField(description="原始语义输出")
    field_mappings: Dict[str, FieldMapping] = PydanticField(description="字段映射字典")
    overall_confidence: Optional[float] = PydanticField(default=None, ge=0.0, le=1.0, description="整体置信度")
    low_confidence_fields: List[str] = PydanticField(default_factory=list, description="低置信度字段列表")
    
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
    "FieldCandidate",
    "SingleSelectionResult",
    "AlternativeMapping",
    "FieldMapping",
    "MappedQuery",
]
