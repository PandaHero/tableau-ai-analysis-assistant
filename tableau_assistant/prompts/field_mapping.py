"""
Field Mapping Prompt (Structured Template)

Uses the structured template system for semantic field mapping with RAG+LLM.
Follows the principle: Prompt teaches HOW to think, Schema defines WHAT to output.
"""
from typing import Type
from pydantic import BaseModel
from tableau_assistant.prompts.base import VizQLPrompt
from tableau_assistant.src.models.field_mapping import BatchFieldMappingResult


class FieldMappingPrompt(VizQLPrompt):
    """Prompt for semantic field mapping using RAG+LLM hybrid model.
    
    This prompt focuses on teaching LLM how to match business terms to fields.
    Field-specific rules are in the BatchFieldMappingResult model field descriptions.
    """
    
    def get_role(self) -> str:
        return """Field mapping expert who maps business terms to technical fields.

Expertise:
- Semantic understanding of business terminology
- Field metadata analysis (role, type, category, samples)
- Context-aware disambiguation
- Synonym and multi-language handling"""
    
    def get_task(self) -> str:
        return """Map business terms to technical fields using RAG candidates.

Process: Analyze term -> Review candidates -> Match semantics -> Score confidence"""
    
    def get_specific_domain_knowledge(self) -> str:
        return """Question Context: {question_context}

Business Terms: {business_terms}

RAG Candidates (pre-filtered by vector similarity):
{candidates}

**Think step by step:**

Step 1: Analyze business term semantics
- What does this term mean in business context?
- Is it a dimension (categorical/grouping) or measure (numeric/aggregated)?
- What category does it belong to? (geographic/temporal/product/customer/financial)

Step 2: Review RAG candidate fields
- Examine each candidate's metadata: role, data_type, category, samples
- Note similarity scores (higher = better vector match)
- Identify semantic matches vs literal matches

Step 3: Match based on semantics
Ask: Which candidate best matches the business term's meaning?
- Semantic meaning is the primary criterion
- Role match is critical (dimension term to dimension field)
- Category alignment provides additional confidence
- Vector similarity is a tiebreaker, not primary

Step 4: Score confidence
Ask: How certain am I about this match?
- Perfect match: exact synonym, correct role, clear context
- Good match: similar meaning, correct role
- Acceptable match: related meaning, may need verification
- Poor match: weak connection, consider alternatives

Step 5: Handle special cases
- Synonyms: different words with same meaning
- Multi-language: terms in different languages
- Context-dependent: meaning depends on question context
- No match: when no candidate fits semantically"""
    
    def get_constraints(self) -> str:
        return """MUST: select from candidates only, match field role with term type, provide reasoning
MUST NOT: invent fields not in candidates, ignore role mismatch, give high confidence without evidence"""
    
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


# ============= Exports =============

__all__ = [
    "FieldMappingPrompt",
    "FIELD_MAPPING_PROMPT",
]
