# -*- coding: utf-8 -*-
"""Step 2 Prompt - Computation reasoning and LLM self-validation.

Step 2 is the "Reasoning" phase of the LLM combination architecture.
It infers computation from restated_question and validates against Step 1 output.

IMPORTANT: Validation is done by LLM itself, NOT by code.

Design principles (from appendix-e-prompt-model-guide.md):
- Prompt teaches LLM HOW to think (领域概念、分析方法)
- Schema tells LLM WHAT to output (字段含义、填写规则、决策规则)
- Uses VizQLPrompt base class for automatic JSON Schema injection
"""

from typing import Type
from pydantic import BaseModel

from tableau_assistant.src.agents.base.prompt import VizQLPrompt
from tableau_assistant.src.core.models import Step2Output


class Step2Prompt(VizQLPrompt):
    """Step 2: Computation reasoning and LLM self-validation.
    
    Uses 4-section structure:
    - ROLE: Define the AI's role
    - TASK: Define the task
    - DOMAIN KNOWLEDGE: Provide domain concepts (not field-specific rules)
    - CONSTRAINTS: Define boundaries
    """
    
    def get_role(self) -> str:
        return """Computation reasoning expert for data analysis.
You infer computation definitions from restated questions and validate against Step 1 output.

Expertise: CalcType inference, Partition semantics, LOD vs Table Calc selection, Self-validation"""

    def get_task(self) -> str:
        return """Infer computation from restated_question, then validate against Step 1 output.

Process: Infer target → Select calc_type → Determine partition_by → Fill params → Self-validate"""

    def get_specific_domain_knowledge(self) -> str:
        return """**Computation Model**

Computation = Target × CalcType × Partition × Params

**Think step by step:**
1. Infer target from restated_question
2. Infer calc_type from question keywords
3. Infer partition_by from scope keywords
4. Fill params based on calc_type
5. Validate against Step 1 output

**Partition Semantics**

Partition defines the scope of computation:
- Empty [] = Global computation (across all data)
- Non-empty = Compute within each group independently

Keywords to partition mapping:
- "global/total/overall" → []
- "per month/within each month/monthly" → [time dimension]
- "per region/by region/within region" → [region dimension]

**LOD vs Table Calc Decision**

LOD (change aggregation granularity):
- Use when need atomic metric independent of view
- Example: "per customer first purchase date" → LOD_FIXED

Table Calc (operate on aggregated view data):
- Use when need to transform already aggregated data
- Example: "rank by sales" → RANK

**Combination Scenarios (LOD + Table Calc)**

When to use combination:
1. Need atomic metric independent of view, then transform it
   Example: "Rank customers by their first purchase date"
   → First LOD_FIXED to get first purchase date per customer
   → Then RANK to rank customers by that date

Output order for combinations:
- computations: [LOD first, then Table Calc]
- LOD creates the base metric, Table Calc transforms it

**Self-Validation**

After inference, validate your results against Step 1 output to ensure consistency."""

    def get_constraints(self) -> str:
        return """MUST: Infer from restated_question, Validate against Step 1, Report all inconsistencies
MUST: Output LOD computations before Table Calc computations in combination scenarios
MUST NOT: Skip validation, Mark as valid when any check fails
MUST NOT: Use partition_by dimensions not in Step 1's where.dimensions"""

    def get_user_template(self) -> str:
        return """**Restated Question:** {restated_question}

**Step 1 Output (for validation):**
- what.measures: {measures}
- where.dimensions: {dimensions}
- how_type: {how_type}

Please infer computation and self-validate, then output Step2Output JSON."""

    def get_output_model(self) -> Type[BaseModel]:
        return Step2Output


# Create prompt instance
STEP2_PROMPT = Step2Prompt()

__all__ = ["Step2Prompt", "STEP2_PROMPT"]
