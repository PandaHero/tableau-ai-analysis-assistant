"""
Field Mapper Models

Models for FieldMapper Node:
- SingleSelectionResult / BatchSelectionResult: LLM candidate selection output
- FieldMapping / MappedQuery: FieldMapper Node final output
"""

from typing import List, Dict, Optional, TYPE_CHECKING
from typing_extensions import TypedDict
from pydantic import BaseModel, Field, ConfigDict, model_validator

from tableau_assistant.src.models.semantic.enums import (
    MappingSource,
    DimensionCategory,
    DimensionLevel,
)

if TYPE_CHECKING:
    from tableau_assistant.src.models.semantic.query import SemanticQuery


class SingleSelectionResult(BaseModel):
    """LLM field selection output model"""

    business_term: str = Field(description="Business term being mapped")
    selected_field: Optional[str] = Field(default=None, description="Best matching technical field name")
    confidence: float = Field(ge=0.0, le=1.0, description="Selection confidence score")
    reasoning: str = Field(description="Selection reasoning")


class BatchSelectionResult(BaseModel):
    """Batch field selection result"""

    mappings: List[SingleSelectionResult] = Field(description="Mapping results for each business term")


class AlternativeMapping(TypedDict, total=False):
    """Alternative mapping structure"""

    technical_field: str
    confidence: float
    reason: str


class FieldMapping(BaseModel):
    """Single field mapping result"""

    model_config = ConfigDict(extra="forbid")

    business_term: str = Field(min_length=1, description="Business term from SemanticQuery")
    technical_field: str = Field(min_length=1, description="Technical field name in datasource")
    confidence: float = Field(ge=0.0, le=1.0, description="Mapping confidence (0-1)")
    mapping_source: MappingSource = Field(description="Mapping source")
    data_type: Optional[str] = Field(default=None, description="Field data type from metadata")
    date_format: Optional[str] = Field(default=None, description="Date format for STRING date fields")
    category: Optional[DimensionCategory] = Field(default=None, description="Dimension category")
    level: Optional[DimensionLevel] = Field(default=None, description="Hierarchy level")
    granularity: Optional[str] = Field(default=None, description="Granularity description")
    alternatives: Optional[List[AlternativeMapping]] = Field(default=None, description="Alternative mappings")


class MappedQuery(BaseModel):
    """Mapped query - FieldMapper Node output"""

    model_config = ConfigDict(extra="forbid")

    semantic_query: "SemanticQuery" = Field(description="Original semantic query")
    field_mappings: Dict[str, FieldMapping] = Field(description="Field mappings dictionary")
    overall_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Overall confidence")
    low_confidence_fields: List[str] = Field(default_factory=list, description="Low confidence field list")

    @model_validator(mode="after")
    def compute_overall_confidence(self) -> "MappedQuery":
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
        mapping = self.field_mappings.get(business_term)
        return mapping.technical_field if mapping else None

    def get_confidence(self, business_term: str) -> Optional[float]:
        mapping = self.field_mappings.get(business_term)
        return mapping.confidence if mapping else None


__all__ = [
    "SingleSelectionResult",
    "BatchSelectionResult",
    "AlternativeMapping",
    "FieldMapping",
    "MappedQuery",
]


# 解析前向引用 - MappedQuery 引用了 SemanticQuery
def _rebuild_models():
    """重建 Pydantic 模型以解析前向引用"""
    from tableau_assistant.src.models.semantic.query import SemanticQuery  # noqa: F401
    MappedQuery.model_rebuild()

_rebuild_models()
