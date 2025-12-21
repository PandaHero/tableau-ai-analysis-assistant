"""
维度层级推断 Prompt

设计原则：
- Prompt 教 LLM 如何思考
- Schema 告诉 LLM 输出什么
"""
from typing import Type
from pydantic import BaseModel

from tableau_assistant.src.agents.base.prompt import VizQLPrompt
from tableau_assistant.src.core.models import DimensionHierarchyResult


class DimensionHierarchyPrompt(VizQLPrompt):
    """维度层级推断 Prompt"""
    
    def get_role(self) -> str:
        return """Dimension hierarchy expert who infers hierarchical attributes for dimension fields.

Expertise: data granularity analysis, category classification, parent-child relationship identification"""
    
    def get_task(self) -> str:
        return """Infer hierarchical attributes for each dimension field.

Process: Analyze semantics → Classify category → Determine level → Identify relationships → Score confidence"""
    
    def get_specific_domain_knowledge(self) -> str:
        return """**Think step by step:**

Step 1: Analyze field semantics
- What does the field name suggest?
- What do the sample values indicate?
- What is the unique count telling us about granularity?

Step 2: Classify into semantic category
- Consider the business domain of the field
- Look for semantic indicators in name and values

Step 3: Determine hierarchical level
- Compare unique counts across fields
- Identify coarse-to-fine relationships
- Consider typical business hierarchies

Step 4: Identify parent-child relationships
- Parent: coarser dimension (lower unique count, broader semantics)
- Child: finer dimension (higher unique count, narrower semantics)
- If uncertain, leave as null (DO NOT GUESS)

Step 5: Score confidence based on evidence strength
- Clear semantic indicators increase confidence
- Ambiguous signals decrease confidence"""
    
    def get_constraints(self) -> str:
        return """MUST: assign level 1-5 for every dimension, provide reasoning
MUST NOT: guess parent-child relationships when uncertain"""
    
    def get_user_template(self) -> str:
        return """Analyze these dimensions and return dimension_hierarchy:

{dimensions}

Output JSON with dimension_hierarchy dictionary."""
    
    def get_output_model(self) -> Type[BaseModel]:
        return DimensionHierarchyResult


# 创建 prompt 实例
DIMENSION_HIERARCHY_PROMPT = DimensionHierarchyPrompt()

__all__ = ["DimensionHierarchyPrompt", "DIMENSION_HIERARCHY_PROMPT"]
