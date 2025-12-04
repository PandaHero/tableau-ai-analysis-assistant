"""
Dimension Hierarchy Prompt (Structured Template)

Uses the structured template system for dimension hierarchy inference with RAG enhancement.
Follows the principle: Prompt teaches HOW to think, Schema defines WHAT to output.
"""
from typing import Type
from pydantic import BaseModel
from tableau_assistant.prompts.base import VizQLPrompt
from tableau_assistant.src.models.dimension_hierarchy import DimensionHierarchyResult


class DimensionHierarchyPrompt(VizQLPrompt):
    """Prompt for dimension hierarchy inference using RAG+LLM hybrid model.
    
    This prompt focuses on teaching LLM how to analyze dimension hierarchies.
    Field-specific rules are in the DimensionHierarchyResult model field descriptions.
    """
    
    def get_role(self) -> str:
        return """Dimension hierarchy expert who infers hierarchical attributes for dimension fields.

Expertise:
- Data granularity analysis (coarse to fine)
- Category classification (geographic/temporal/product/customer/organizational/financial)
- Parent-child relationship identification
- Level assignment based on semantic meaning"""
    
    def get_task(self) -> str:
        return """Infer hierarchical attributes for each dimension field.

Process: Analyze semantics -> Classify category -> Determine level -> Identify relationships -> Score confidence"""
    
    def get_specific_domain_knowledge(self) -> str:
        return """Dimension Fields to Analyze:
{dimensions}

{few_shot_section}

**Think step by step:**

Step 1: Analyze field semantics
- What does this field name mean?
- Look for explicit level indicators (Level 1/2/3, Primary/Secondary)
- Examine sample values for clues about granularity

Step 2: Classify category
Ask: What domain does this dimension belong to?
- Geographic: locations, addresses, regions
- Time: dates, periods, years, months
- Product: items, categories, brands
- Customer: segments, types, individuals
- Organization: departments, teams, employees
- Financial: accounts, cost centers, budgets

Step 3: Determine level (1-5 scale)
Ask: How granular is this dimension?
- Level 1 (coarsest): Highest aggregation (Country, Year, Top Category)
- Level 2 (coarse): Second level (Province, Quarter, Category)
- Level 3 (medium): Middle level (City, Month, Subcategory)
- Level 4 (fine): Detailed level (District, Week, Brand)
- Level 5 (finest): Most detailed (Address, Date, SKU)

Priority for level determination:
1. Explicit indicators in name (highest priority)
2. Semantic meaning of the field
3. Unique count (lower count = coarser, within same category)
4. Sample value analysis

Step 4: Identify parent-child relationships
Ask: Are there related dimensions with different granularity?
- Parent: coarser dimension (lower unique count, broader semantics)
- Child: finer dimension (higher unique count, narrower semantics)
- Common patterns: Province to City, Year to Month, Category to Subcategory
- If uncertain, leave as null (do not guess)

Step 5: Score confidence
Ask: How certain am I about this classification?
- High confidence: Clear semantics, explicit indicators
- Medium confidence: Good semantic match, consistent signals
- Low confidence: Ambiguous, conflicting signals"""
    
    def get_constraints(self) -> str:
        return """MUST: assign level 1-5 for every dimension, use semantic meaning as primary criterion, provide reasoning
MUST NOT: guess parent-child relationships when uncertain, assign levels outside 1-5 range"""
    
    def get_user_template(self) -> str:
        return """Dimensions to analyze:

{dimensions}

Return dimension_hierarchy dictionary with all dimensions."""
    
    def get_output_model(self) -> Type[BaseModel]:
        return DimensionHierarchyResult


# Create prompt instance for easy import
DIMENSION_HIERARCHY_PROMPT = DimensionHierarchyPrompt()


# ============= Exports =============

__all__ = [
    "DimensionHierarchyPrompt",
    "DIMENSION_HIERARCHY_PROMPT",
]
