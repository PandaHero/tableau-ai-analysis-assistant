"""
Dimension Hierarchy Prompt (Structured Template)

Uses the structured template system for dimension hierarchy inference.
"""
from typing import Type
from pydantic import BaseModel
from tableau_assistant.prompts.base import DataAnalysisPrompt
from tableau_assistant.src.models.dimension_hierarchy import DimensionHierarchyResult


class DimensionHierarchyPrompt(DataAnalysisPrompt):
    """Structured prompt for dimension hierarchy inference"""
    
    def get_role(self) -> str:
        return """You are a data modeling expert who infers hierarchical attributes for dimension fields.

Your expertise includes understanding data granularity, category classification, and parent-child relationships in dimensional data."""
    
    def get_task(self) -> str:
        return """For each dimension field, infer hierarchical attributes:

1. **Category**: Classify into geographic, temporal, product, customer, organizational, financial, or other
2. **Level**: Determine granularity level (1=coarsest to 5=finest)
3. **Parent-Child Relationships**: Identify hierarchical relationships between dimensions
4. **Confidence**: Assess confidence level for each inference

Expected outcome: Complete hierarchical structure for all dimensions with justified level assignments."""
    
    def get_specific_context(self) -> str:
        return """## Available Information
- Dimension fields: {dimensions}
- Each field includes:
  * name: Field name
  * caption: Display name
  * dataType: Data type
  * unique_count: Number of unique values
  * sample_values: Example values (up to 5)

## Level Scale (1-5)
- **Level 1**: Highest aggregation (e.g., Country, Year, Top Category)
- **Level 5**: Lowest aggregation (e.g., Transaction ID, Timestamp, SKU)
- **Levels 2-4**: Intermediate granularities"""
    
    def get_principles(self) -> str:
        return """## Core Inference Principles

### 1. Semantic Analysis First
**Analyze field name and sample values to understand meaning**:
- Look for explicit level indicators (一级/二级/三级, Level 1/2/3, Primary/Secondary)
- Identify domain type (geographic, temporal, product, organizational)
- Understand business context from sample values

### 2. Granularity Assessment
**Determine relative coarseness using multiple signals**:
- **Unique Count**: Lower count suggests coarser granularity
- **Field Name**: Explicit hierarchy indicators (省/市/区, Year/Month/Day)
- **Sample Values**: Content reveals aggregation level
- **Naming Patterns**: Codes vs Names (codes often finer), IDs (usually finest)

### 3. Relative Positioning
**Assign levels based on relative granularity within same category**:
- Identify dimensions in same category (e.g., all geographic fields)
- Order by granularity (coarsest to finest)
- Distribute across 1-5 scale based on relative positions
- Maintain logical spacing (parent should be 1-2 levels coarser than child)

### 4. Category Classification
**Classify into broad categories for context**:
- **Geographic**: Location-based (country, province, city, store)
- **Temporal**: Time-based (year, quarter, month, week, date)
- **Product**: Product hierarchy (category, subcategory, brand, SKU)
- **Organizational**: Organization structure (department, team, employee)
- **Customer**: Customer segmentation (type, segment, individual)
- **Financial**: Financial structure (cost center, account)
- **Other**: Doesn't fit above categories

### 5. Parent-Child Inference
**Identify hierarchical relationships**:
- Parent has lower unique_count and coarser semantics
- Child has higher unique_count and finer semantics
- Common naming patterns (一级→二级, Province→City)
- Only specify if confident (set null if uncertain)

## Decision Priority
When signals conflict:
1. **Explicit hierarchy indicators** (一级/二级/Level 1/2) - Highest priority
2. **Semantic meaning** (Year vs Date, Province vs City)
3. **Unique count** (relative within category)
4. **Sample values** (content analysis)

## Granularity Mapping
- level=1 → "最粗粒度"
- level=2 → "粗粒度"
- level=3 → "中粒度"
- level=4 → "细粒度"
- level=5 → "最细粒度"""
    
    def get_constraints(self) -> str:
        return """## Must NOT
- Assign level outside 1-5 range
- Use unique_count as sole criterion (consider semantics first)
- Create circular parent-child relationships
- Assign same level to clear parent-child pairs
- Over-complicate with excessive detail

## Edge Cases
- **Ambiguous Names**: Analyze sample_values for clues
- **Missing Sample Values**: Rely on name semantics and unique_count
- **Conflicting Signals**: Prioritize explicit hierarchy indicators
- **Single Dimension in Category**: Still assign appropriate level based on semantics
- **Multiple Hierarchies**: Identify separate category hierarchies independently

## Validation Requirements
- All levels must be 1-5
- Parent dimension must have lower level number than child (parent=1, child=2)
- Confidence must be 0.0-1.0
- Reasoning must be concise and explain key decision factors"""
    
    def get_output_requirements(self) -> str:
        return """## Quality Standards
Before outputting, verify:
- [ ] All dimensions have assigned levels (1-5)
- [ ] Level assignments are semantically justified
- [ ] Parent-child relationships are logical (if specified)
- [ ] Confidence scores reflect certainty
- [ ] Reasoning is concise (1-2 sentences per dimension)

## Output Format
Return pure JSON object (no markdown code blocks).

## Common Mistakes to Avoid
- Overly detailed reasoning (keep it concise)
- Ignoring explicit hierarchy indicators in field names
- Using unique_count alone without semantic analysis
- Inconsistent level spacing within same hierarchy
- Specifying uncertain parent-child relationships (use null if unsure)"""
    
    def get_user_template(self) -> str:
        return """Please infer hierarchical attributes for the following dimensions:

{dimensions}

Infer all dimensions at once and return the dimension_hierarchy dictionary."""
    
    def get_output_model(self) -> Type[BaseModel]:
        return DimensionHierarchyResult


# Create prompt instance for easy import
DIMENSION_HIERARCHY_PROMPT = DimensionHierarchyPrompt()


# ============= 导出 =============

__all__ = [
    "DimensionHierarchyPrompt",
    "DIMENSION_HIERARCHY_PROMPT",
]
