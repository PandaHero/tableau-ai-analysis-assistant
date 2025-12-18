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

Step 1: Classify category
- geographic: locations, addresses, regions (省份、城市、区县)
- time: dates, periods (年、月、日、季度)
- product: items, categories, brands (产品、类别、品牌)
- customer: segments, types (客户、客户类型)
- organization: departments, teams (部门、团队)
- financial: accounts, cost centers (科目、成本中心)
- other: none of the above

Step 2: Determine level (1-5 scale)
- Level 1 (coarsest): Country, Year, Top Category
- Level 2 (coarse): Province, Quarter, Category
- Level 3 (medium): City, Month, Subcategory
- Level 4 (fine): District, Week, Brand
- Level 5 (finest): Address, Date, SKU

Step 3: Identify parent-child relationships
- Parent: coarser dimension (lower unique count, broader semantics)
- Child: finer dimension (higher unique count, narrower semantics)
- If uncertain, leave as null (DO NOT GUESS)

Step 4: Score confidence (0.0-1.0)
- 0.9-1.0: Clear semantics, explicit indicators
- 0.7-0.9: Good semantic match
- 0.5-0.7: Ambiguous signals
- 0.0-0.5: Very uncertain"""
    
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
