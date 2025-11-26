"""
Field Mapping Prompt (Structured Template)

Uses the structured template system for semantic field mapping with RAG+LLM.
"""
from typing import Type
from pydantic import BaseModel
from tableau_assistant.prompts.base import VizQLPrompt
from tableau_assistant.src.models.field_mapping import BatchFieldMappingResult


class FieldMappingPrompt(VizQLPrompt):
    """Prompt for semantic field mapping using RAG+LLM hybrid model"""
    
    def get_role(self) -> str:
        return """Field mapping expert who maps business terms to technical fields.

Expertise:
- Semantic understanding of business terminology
- Field metadata analysis (role, type, category, samples)
- Context-aware disambiguation
- Synonym and multi-language handling"""
    
    def get_task(self) -> str:
        return """Map business terms to technical fields using RAG candidates.

Process: Analyze term → Review candidates → Match semantics → Score confidence"""
    
    def get_specific_domain_knowledge(self) -> str:
        return """Question Context: {question_context}

Business Terms: {business_terms}

RAG Candidates (pre-filtered by vector similarity):
{candidates}

**Think step by step:**

Step 1: Analyze business term semantics
- What does this term mean in business context?
- Is it a dimension (categorical/grouping) or measure (numeric/aggregated)?
- What category does it belong to? (geographic/temporal/product/customer/financial/organizational)

Step 2: Review RAG candidate fields
- Examine each candidate's metadata: role, data_type, category, description, samples
- Note similarity scores (higher = better vector match)
- Identify semantic matches vs literal matches

Step 3: Match based on semantics
For each business term, determine best match:

| Criterion | Weight | Consideration |
|-----------|--------|---------------|
| Semantic meaning | High | Does field meaning match term meaning? |
| Role match | High | Dimension term → dimension field, Measure term → measure field |
| Category match | Medium | Does field category align with term category? |
| Context fit | Medium | Does field make sense in question context? |
| Vector similarity | Low | Use as tiebreaker, not primary criterion |

Step 4: Score confidence
- 0.9-1.0: Perfect match (exact synonym, correct role, clear context)
- 0.7-0.9: Good match (similar meaning, correct role)
- 0.5-0.7: Acceptable match (related meaning, may need verification)
- 0.0-0.5: Poor match (weak connection, consider alternatives)

Step 5: Handle special cases
- Synonyms: "sales" = "revenue" = "sales amount"
- Multi-language: "销售额" = "Sales Amount"
- Context-dependent: "30天销售额" → prefer fields with "30" in name
- No match: Set matched_field to null if no semantic fit

Mapping guidelines:
1. **Role matching**: Aggregation implies measure, grouping implies dimension
2. **Semantic priority**: Meaning > literal similarity
3. **Context consideration**: Use question context for disambiguation
4. **Confidence honesty**: Lower confidence if uncertain
5. **Alternative listing**: Provide alternatives when confidence < 0.9"""
    
    def get_constraints(self) -> str:
        return """Instructions (focus on positive actions):

DO:
- Select matched_field from provided candidates only
- Match field role (dimension vs measure) with business term
- Consider question context for disambiguation
- Provide confidence score between 0 and 1
- Give clear reasoning for your selection
- List alternatives when confidence is below 0.9
- Use semantic meaning as primary criterion

ENSURE:
- Every mapping references an actual candidate field
- Confidence reflects true certainty level
- Reasoning explains the semantic match"""
    
    def get_user_template(self) -> str:
        return """Map these business terms to technical fields:

Terms: {business_terms}
Context: {question_context}

Candidates:
{candidates}"""
    
    def get_output_model(self) -> Type[BaseModel]:
        return BatchFieldMappingResult


# Create prompt instance for easy import
FIELD_MAPPING_PROMPT = FieldMappingPrompt()


# ============= 导出 =============

__all__ = [
    "FieldMappingPrompt",
    "FIELD_MAPPING_PROMPT",
]
