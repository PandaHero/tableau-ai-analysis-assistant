# -*- coding: utf-8 -*-
"""Step 2 Prompt - Computation reasoning and LLM self-validation.

Step 2 is the "Reasoning" phase of the LLM combination architecture.
It infers computation from restated_question and validates against Step 1 output.

IMPORTANT: Validation is done by LLM itself, NOT by code.
The OPERATION_TYPE_MAPPING is reference information for LLM to validate.

Design principles (from appendix-e-prompt-model-guide.md):
- Prompt teaches LLM HOW to think (4-section structure)
- Schema tells LLM WHAT to output (XML tags in Field descriptions)
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
    - TASK: Define the task with implicit CoT
    - DOMAIN KNOWLEDGE: Provide domain-specific rules
    - CONSTRAINTS: Define boundaries
    """
    
    def get_role(self) -> str:
        return """Computation reasoning expert for data analysis.

Expertise: Computation inference, Self-validation, Partition inference"""

    def get_task(self) -> str:
        return """Infer computation from restated_question, then validate against Step 1 output.

Process: Infer target -> Infer partition_by -> Infer operation -> Self-validate all checks"""

    def get_specific_domain_knowledge(self) -> str:
        return """**Computation Model**

Computation = Target × Partition × Operation

**Think step by step:**

Step 1: Infer target from restated_question
Step 2: Infer partition_by from partition keywords
Step 3: Infer operation.type from computation keywords
Step 4: Self-validate all three checks against Step 1 output

**OPERATION_TYPE_MAPPING (for self-validation):**

- RANKING → RANK, DENSE_RANK
- CUMULATIVE → RUNNING_SUM, RUNNING_AVG, MOVING_AVG, MOVING_SUM
- COMPARISON → PERCENT, DIFFERENCE, GROWTH_RATE, YEAR_AGO, PERIOD_AGO
- GRANULARITY → FIXED

**Self-Validation Checks:**

1. target_check: target ∈ what.measures?
2. partition_by_check: partition_by ⊆ where.dimensions?
3. operation_check: operation.type ∈ OPERATION_TYPE_MAPPING[how_type]?"""

    def get_constraints(self) -> str:
        return """MUST: Infer from restated_question, Validate against Step 1, Report inconsistencies
MUST NOT: Infer partition_by not in dimensions, Use operation.type not matching how_type"""

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

# Legacy constants for backward compatibility
STEP2_SYSTEM_PROMPT = STEP2_PROMPT.get_system_message()
STEP2_USER_TEMPLATE = STEP2_PROMPT.get_user_template()

__all__ = ["Step2Prompt", "STEP2_PROMPT", "STEP2_SYSTEM_PROMPT", "STEP2_USER_TEMPLATE"]
