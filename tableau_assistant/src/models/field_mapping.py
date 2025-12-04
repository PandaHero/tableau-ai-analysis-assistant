"""
Field mapping data models

Contains:
- FieldMapping: Single field mapping result
- FieldMappingResult: Complete mapping result
- MappingHistory: Mapping history record
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Dict, Any, Optional
from datetime import datetime


class FieldMapping(BaseModel):
    """
    Single field mapping result for a business term
    
    Contains the matched technical field, confidence score, reasoning, and alternatives.
    """
    model_config = ConfigDict(extra="forbid")
    
    business_term: str = Field(
        description="""Business term to be mapped.

Usage:
- Store the original business term from user query
- Used as key for mapping lookup

Values: Business term string (e.g., 'sales', 'revenue', 'region')"""
    )
    
    technical_field: str = Field(
        description="""Matched technical field name.

Usage:
- Store the exact field name from metadata
- Used in VizQL query generation

Values: Field name string in Tableau format (e.g., '[Sales].[Sales Amount]', '[Geography].[Region]')"""
    )
    
    confidence: float = Field(
        ge=0.0, 
        le=1.0,
        description="""Mapping confidence score.

Usage:
- Indicate confidence in the mapping quality
- Used to filter low-quality mappings

Values: Float between 0 and 1
- 0.9-1.0: Perfect match (exact semantic match)
- 0.7-0.9: Good match (strong semantic similarity)
- 0.5-0.7: Acceptable match (reasonable similarity)
- 0.0-0.5: Poor match (weak similarity)"""
    )
    
    alternatives: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="""Alternative field matches.

Usage:
- Include when confidence < 0.9
- Provide fallback options for user selection
- Empty list if no alternatives found

Values: List of dictionaries with keys:
- 'field': Alternative field name
- 'confidence': Alternative confidence score
- 'reasoning': Why this is an alternative"""
    )
    
    reasoning: str = Field(
        description="""LLM reasoning for the mapping decision.

Usage:
- Explain why this field was selected
- Provide transparency for debugging
- Help users understand the mapping

Values: Natural language explanation string"""
    )
    
    field_data_type: Optional[str] = Field(
        default=None,
        description="""Field data type.

Usage:
- Include if available from metadata
- null if data type unknown

Values: Data type string or null
- 'string': Text data
- 'integer': Whole numbers
- 'real': Decimal numbers
- 'boolean': True/false values
- 'date': Date values
- 'datetime': Date and time values"""
    )
    
    field_role: Optional[str] = Field(
        default=None,
        description="""Field role in Tableau.

Usage:
- Include if available from metadata
- Used to match dimension vs measure
- null if role unknown

Values: Role string or null
- 'dimension': Categorical field for grouping
- 'measure': Numeric field for aggregation"""
    )


class FieldMappingResult(BaseModel):
    """
    Complete field mapping result for multiple business terms
    
    Contains mappings for all business terms, overall confidence, and data source identifier.
    """
    model_config = ConfigDict(extra="forbid")
    
    mappings: Dict[str, FieldMapping] = Field(
        description="""Business term to mapping result dictionary.

Usage:
- Store all field mappings for a query
- Key is business term, value is FieldMapping

Values: Dictionary with business terms as keys and FieldMapping objects as values"""
    )
    
    overall_confidence: float = Field(
        ge=0.0, 
        le=1.0,
        description="""Overall mapping confidence.

Usage:
- Aggregate confidence across all mappings
- Used to determine if query can proceed

Values: Float between 0 and 1
- Typically average or minimum of individual confidences
- High value (>0.8) indicates reliable mappings"""
    )
    
    datasource_luid: str = Field(
        description="""Data source unique identifier.

Usage:
- Link mappings to specific data source
- Used for caching and history lookup

Values: LUID string (e.g., 'abc123-def456-ghi789')"""
    )


class MappingHistory(BaseModel):
    """
    Mapping history record for learning and optimization
    
    Tracks historical mappings with usage statistics and success rates.
    """
    model_config = ConfigDict(extra="forbid")
    
    business_term: str = Field(
        description="""Business term that was mapped.

Usage:
- Store the original business term
- Used for history lookup

Values: Business term string"""
    )
    
    technical_field: str = Field(
        description="""Technical field that was mapped to.

Usage:
- Store the selected technical field
- Used for learning from past mappings

Values: Field name string in Tableau format"""
    )
    
    datasource_luid: str = Field(
        description="""Data source unique identifier.

Usage:
- Link history to specific data source
- Mappings are data source specific

Values: LUID string"""
    )
    
    question_context: str = Field(
        description="""Question context when mapping occurred.

Usage:
- Store the full question for context-aware learning
- Used to understand mapping context

Values: Question text string"""
    )
    
    confidence: float = Field(
        ge=0.0, 
        le=1.0,
        description="""Mapping confidence at creation time.

Usage:
- Store initial confidence score
- Used to track confidence trends

Values: Float between 0 and 1"""
    )
    
    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="""Creation timestamp.

Usage:
- Track when mapping was created
- Used for time-based analysis

Values: Datetime object"""
    )
    
    usage_count: int = Field(
        default=1,
        description="""Number of times this mapping was used.

Usage:
- Track mapping popularity
- Increment on each use

Values: Positive integer (starts at 1)"""
    )
    
    success_count: int = Field(
        default=0,
        description="""Number of successful query executions.

Usage:
- Track mapping effectiveness
- Increment when query succeeds

Values: Non-negative integer (starts at 0)"""
    )
    
    success_rate: float = Field(
        default=0.0, 
        ge=0.0, 
        le=1.0,
        description="""Success rate of this mapping.

Usage:
- Calculated as success_count / usage_count
- Used to rank mapping quality

Values: Float between 0 and 1
- 1.0: Always successful
- 0.5: 50% success rate
- 0.0: Never successful"""
    )
    
    def update_success(self, success: bool):
        """更新成功统计"""
        self.usage_count += 1
        if success:
            self.success_count += 1
        self.success_rate = self.success_count / self.usage_count if self.usage_count > 0 else 0.0
    
    def model_dump_for_store(self) -> Dict[str, Any]:
        """转换为适合存储的字典格式"""
        data = self.model_dump()
        # 转换 datetime 为 ISO 格式字符串
        data['timestamp'] = self.timestamp.isoformat()
        return data
    
    @classmethod
    def from_store_data(cls, data: Dict[str, Any]) -> 'MappingHistory':
        """从存储数据创建实例"""
        # 转换 ISO 格式字符串为 datetime
        if isinstance(data.get('timestamp'), str):
            data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls(**data)


class SingleFieldMappingResult(BaseModel):
    """Single field mapping result for LLM output.
    
    EXAMPLE:
    
    Input term: "销售额"
    Output: {
        "business_term": "销售额",
        "matched_field": "[Sales].[Sales Amount]",
        "confidence": 0.95,
        "reasoning": "Exact semantic match for sales amount",
        "alternatives": []
    }
    """
    model_config = ConfigDict(extra="forbid")
    
    business_term: str = Field(
        description="""Business term being mapped.

WHAT: The original business term from user query
WHEN: Always required
HOW: Copy from input"""
    )
    
    matched_field: Optional[str] = Field(
        None,
        description="""Matched technical field name.

WHAT: The technical field that best matches the business term
WHEN: Include if match found, null if no suitable match
HOW: Select from provided candidates only

VALUES: Field name string or null"""
    )
    
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="""Mapping confidence score.

WHAT: How confident in this mapping
WHEN: Always required
HOW: Float 0.0-1.0

VALUES:
- 0.9-1.0: Perfect match
- 0.7-0.9: Good match
- 0.5-0.7: Acceptable match
- 0.0-0.5: Poor match"""
    )
    
    reasoning: str = Field(
        description="""Reasoning for the mapping.

WHAT: Why this field was selected
WHEN: Always required
HOW: 1-2 sentences explaining the match"""
    )
    
    alternatives: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="""Alternative matches.

WHAT: Other possible field matches
WHEN: Include when confidence < 0.9
HOW: List of {field, confidence, reasoning}"""
    )


class BatchFieldMappingResult(BaseModel):
    """Batch field mapping result for multiple business terms.
    
    EXAMPLES:
    
    Input: ["省份", "销售额"]
    Output: {
        "mappings": [
            {
                "business_term": "省份",
                "matched_field": "[Geography].[Province]",
                "confidence": 0.95,
                "reasoning": "Exact match for province dimension",
                "alternatives": []
            },
            {
                "business_term": "销售额",
                "matched_field": "[Sales].[Sales Amount]",
                "confidence": 0.92,
                "reasoning": "Strong semantic match for sales measure",
                "alternatives": []
            }
        ]
    }
    
    ANTI-PATTERNS:
    - Inventing fields not in candidates
    - Mapping dimension term to measure field
    - High confidence without clear semantic match
    """
    model_config = ConfigDict(extra="forbid")
    
    mappings: List[SingleFieldMappingResult] = Field(
        description="""List of field mappings.

WHAT: Mapping result for each business term
WHEN: Always required
HOW: One entry per input business term"""
    )


# ============= Exports =============

__all__ = [
    "FieldMapping",
    "FieldMappingResult",
    "MappingHistory",
    "SingleFieldMappingResult",
    "BatchFieldMappingResult",
]
