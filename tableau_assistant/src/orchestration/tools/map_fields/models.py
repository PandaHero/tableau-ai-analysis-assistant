"""
map_fields Tool 数据模型

定义 Tool 的输入、输出和错误模型。
"""
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field
from enum import Enum


class FieldMappingErrorType(str, Enum):
    """字段映射错误类型"""
    FIELD_NOT_FOUND = "field_not_found"
    AMBIGUOUS_FIELD = "ambiguous_field"
    NO_METADATA = "no_metadata"
    MAPPING_FAILED = "mapping_failed"


class FieldSuggestion(BaseModel):
    """字段建议"""
    field_name: str = Field(description="建议的字段名")
    confidence: float = Field(ge=0.0, le=1.0, description="匹配置信度")
    reason: Optional[str] = Field(default=None, description="建议原因")


class FieldMappingError(BaseModel):
    """字段映射错误
    
    当字段映射失败时返回此结构化错误。
    """
    type: FieldMappingErrorType = Field(description="错误类型")
    field: str = Field(description="出错的字段名")
    message: str = Field(description="用户友好的错误信息")
    suggestions: List[FieldSuggestion] = Field(
        default_factory=list,
        description="可能的字段建议（用于 field_not_found 和 ambiguous_field）"
    )
    
    def to_user_message(self) -> str:
        """生成用户友好的错误消息"""
        if self.type == FieldMappingErrorType.FIELD_NOT_FOUND:
            msg = f"字段 '{self.field}' 在数据源中不存在"
            if self.suggestions:
                suggestions_str = ", ".join([s.field_name for s in self.suggestions[:3]])
                msg += f"。您是否想查询: {suggestions_str}？"
            return msg
        elif self.type == FieldMappingErrorType.AMBIGUOUS_FIELD:
            msg = f"字段 '{self.field}' 存在多个匹配"
            if self.suggestions:
                suggestions_str = ", ".join([s.field_name for s in self.suggestions[:3]])
                msg += f": {suggestions_str}。请明确指定您要查询的字段。"
            return msg
        elif self.type == FieldMappingErrorType.NO_METADATA:
            return f"无法获取数据源元数据，无法映射字段 '{self.field}'"
        else:
            return self.message


class MapFieldsInput(BaseModel):
    """map_fields Tool 输入
    
    接收 SemanticQuery 并映射其中的业务术语到技术字段名。
    """
    semantic_query: Dict[str, Any] = Field(
        description="SemanticQuery 的字典表示（包含 measures, dimensions, filters 等）"
    )
    datasource_luid: str = Field(
        default="default",
        description="数据源标识符"
    )
    context: Optional[str] = Field(
        default=None,
        description="用户问题上下文（用于消歧）"
    )


class MappingResultItem(BaseModel):
    """单个字段的映射结果"""
    business_term: str = Field(description="业务术语")
    technical_field: str = Field(description="技术字段名")
    confidence: float = Field(ge=0.0, le=1.0, description="映射置信度")
    mapping_source: str = Field(description="映射来源: cache_hit, rag_direct, rag_llm_fallback, llm_only")
    category: Optional[str] = Field(default=None, description="维度类别")
    level: Optional[int] = Field(default=None, description="层级级别")
    granularity: Optional[str] = Field(default=None, description="粒度描述")


class MapFieldsOutput(BaseModel):
    """map_fields Tool 输出
    
    成功时返回 MappedQuery，失败时返回 FieldMappingError。
    """
    success: bool = Field(description="是否成功")
    mapped_query: Optional[Dict[str, Any]] = Field(
        default=None,
        description="MappedQuery 的字典表示（成功时）"
    )
    field_mappings: Dict[str, MappingResultItem] = Field(
        default_factory=dict,
        description="字段映射详情"
    )
    overall_confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="整体映射置信度"
    )
    low_confidence_fields: List[str] = Field(
        default_factory=list,
        description="低置信度字段列表"
    )
    error: Optional[FieldMappingError] = Field(
        default=None,
        description="错误信息（失败时）"
    )
    latency_ms: int = Field(
        default=0,
        description="映射耗时（毫秒）"
    )
    
    @classmethod
    def ok(
        cls,
        mapped_query: Dict[str, Any],
        field_mappings: Dict[str, MappingResultItem],
        overall_confidence: float,
        low_confidence_fields: List[str],
        latency_ms: int = 0
    ) -> "MapFieldsOutput":
        """创建成功响应"""
        return cls(
            success=True,
            mapped_query=mapped_query,
            field_mappings=field_mappings,
            overall_confidence=overall_confidence,
            low_confidence_fields=low_confidence_fields,
            latency_ms=latency_ms
        )
    
    @classmethod
    def fail(cls, error: FieldMappingError, latency_ms: int = 0) -> "MapFieldsOutput":
        """创建失败响应"""
        return cls(
            success=False,
            error=error,
            latency_ms=latency_ms
        )


__all__ = [
    "MapFieldsInput",
    "MapFieldsOutput",
    "FieldMappingError",
    "FieldMappingErrorType",
    "FieldSuggestion",
    "MappingResultItem",
]
