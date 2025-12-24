# -*- coding: utf-8 -*-
"""Field Mapping Models.

Data models for field mapping.

Contains:
- SingleSelectionResult: LLM single field selection result
- BatchSelectionResult: Batch field selection result
- AlternativeMapping: Alternative mapping
- FieldMapping: Single field mapping result
- MappedQuery: Mapped query
"""
from typing import List, Dict, Optional
from typing_extensions import TypedDict
from pydantic import BaseModel, Field, ConfigDict, model_validator

from .enums import MappingSource, DimensionCategory, DimensionLevel
from .query import SemanticQuery


class SingleSelectionResult(BaseModel):
    """LLM field selection output model.
    
    <what>Single business term to technical field mapping result</what>
    
    <fill_order>
    1. business_term (ALWAYS)
    2. selected_field (ALWAYS, can be null)
    3. confidence (ALWAYS)
    4. reasoning (ALWAYS)
    </fill_order>
    
    <examples>
    Match found: {"business_term": "Sales", "selected_field": "SUM(Sales)", "confidence": 0.95, "reasoning": "Exact semantic match"}
    No match: {"business_term": "Profit Rate", "selected_field": null, "confidence": 0.0, "reasoning": "No profit rate related field in candidates"}
    </examples>
    
    <anti_patterns>
    X selected_field not in candidate list
    X High confidence but selected_field is null
    </anti_patterns>
    """
    
    business_term: str = Field(
        description="""<what>Business term being mapped</what>
<when>ALWAYS required</when>"""
    )
    selected_field: Optional[str] = Field(
        default=None,
        description="""<what>Best matching technical field name</what>
<when>ALWAYS fill (null if no match)</when>
<rule>Must select from candidate fields, null if no match</rule>
<must_not>Select field not in candidate list</must_not>"""
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="""<what>Selection confidence</what>
<when>ALWAYS required</when>
<rule>0.9-1.0=high match, 0.7-0.9=medium, <0.7=low match, 0=no match</rule>"""
    )
    reasoning: str = Field(
        description="""<what>Selection reasoning</what>
<when>ALWAYS required</when>
<rule>Explain why this field was selected or why no match</rule>"""
    )


class BatchSelectionResult(BaseModel):
    """Batch field selection result."""
    
    mappings: List[SingleSelectionResult] = Field(description="Mapping result for each business term")


class AlternativeMapping(TypedDict, total=False):
    """Alternative mapping structure."""
    
    technical_field: str
    confidence: float
    reason: str


class FieldMapping(BaseModel):
    """Single field mapping result."""
    
    model_config = ConfigDict(extra="forbid")
    
    business_term: str = Field(min_length=1, description="Business term from SemanticQuery")
    technical_field: str = Field(min_length=1, description="Technical field name in data source")
    confidence: float = Field(ge=0.0, le=1.0, description="Mapping confidence (0-1)")
    mapping_source: MappingSource = Field(description="Mapping source")
    data_type: Optional[str] = Field(default=None, description="Field data type")
    date_format: Optional[str] = Field(default=None, description="Date format for STRING type date fields")
    category: Optional[DimensionCategory] = Field(default=None, description="Dimension category")
    level: Optional[DimensionLevel] = Field(default=None, description="Hierarchy level")
    granularity: Optional[str] = Field(default=None, description="Granularity description")
    alternatives: Optional[List[AlternativeMapping]] = Field(default=None, description="Alternative mappings")


class MappedQuery(BaseModel):
    """Mapped query - FieldMapper Node output."""
    
    model_config = ConfigDict(extra="forbid")
    
    semantic_query: SemanticQuery = Field(description="Original semantic query")
    field_mappings: Dict[str, FieldMapping] = Field(description="Field mapping dictionary")
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
        """Get technical field for business term."""
        mapping = self.field_mappings.get(business_term)
        return mapping.technical_field if mapping else None
    
    def get_confidence(self, business_term: str) -> Optional[float]:
        """Get mapping confidence for business term."""
        mapping = self.field_mappings.get(business_term)
        return mapping.confidence if mapping else None


__all__ = [
    "SingleSelectionResult",
    "BatchSelectionResult",
    "AlternativeMapping",
    "FieldMapping",
    "MappedQuery",
]


# 解析前向引用
def _rebuild_models():
    """Rebuild Pydantic models to resolve forward references."""
    from .query import SemanticQuery  # noqa: F401
    MappedQuery.model_rebuild()

_rebuild_models()
