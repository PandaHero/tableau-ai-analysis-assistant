# -*- coding: utf-8 -*-
"""Observer Prompt - Consistency checking (Metacognition).

Observer is the "Metacognition" phase of the LLM combination architecture.
It checks consistency between Step 1 and Step 2 outputs when validation fails.
Only triggered when step2.validation.all_valid == False.

Design principles (from appendix-e-prompt-model-guide.md):
- Prompt teaches LLM HOW to think (4-section structure)
- Schema tells LLM WHAT to output (XML tags in Field descriptions)
- Uses VizQLPrompt base class for automatic JSON Schema injection
"""

from typing import Type
from pydantic import BaseModel

from tableau_assistant.src.agents.base.prompt import VizQLPrompt
from tableau_assistant.src.core.models import ObserverOutput


class ObserverPrompt(VizQLPrompt):
    """Observer: Consistency checking (Metacognition).
    
    Uses 4-section structure:
    - ROLE: Define the AI's role
    - TASK: Define the task with implicit CoT
    - DOMAIN KNOWLEDGE: Provide domain-specific rules
    - CONSTRAINTS: Define boundaries
    """
    
    def get_role(self) -> str:
        return """Quality assurance expert for semantic parsing.

Expertise: Consistency checking, Conflict detection, Decision making"""

    def get_task(self) -> str:
        return """Check consistency between Step 1 and Step 2 outputs, then make a decision.

Process: Check restatement completeness -> Review validation results -> Check semantics -> Decide"""

    def get_specific_domain_knowledge(self) -> str:
        return """**Consistency Checks:**

1. Restatement Completeness: Did restated_question preserve key info?
2. Structure Consistency: Review Step 2's validation results
3. Semantic Consistency: Does computation match user intent?

**Decision Rules:**

- All checks pass → ACCEPT
- Small conflict, can fix → CORRECT
- Large conflict → RETRY
- Cannot determine → CLARIFY"""

    def get_constraints(self) -> str:
        return """MUST: Check original_question, Review validation, Provide correction if CORRECT
MUST NOT: ACCEPT when validation failed, RETRY for minor issues, CLARIFY when clear"""

    def get_user_template(self) -> str:
        return """**Original Question:** {original_question}

**Step 1 Output:**
- restated_question: {restated_question}
- what: {what}
- where: {where}
- how_type: {how_type}

**Step 2 Output:**
- computations: {computations}
- reasoning: {reasoning}
- validation: {validation}

**Step 2 Validation Details:**
- target_check: {target_check}
- partition_by_check: {partition_by_check}
- operation_check: {operation_check}
- all_valid: {all_valid}
- inconsistencies: {inconsistencies}

Please check consistency and output ObserverOutput JSON."""

    def get_output_model(self) -> Type[BaseModel]:
        return ObserverOutput


# Create prompt instance
OBSERVER_PROMPT = ObserverPrompt()

# Legacy constants for backward compatibility
OBSERVER_SYSTEM_PROMPT = OBSERVER_PROMPT.get_system_message()
OBSERVER_USER_TEMPLATE = OBSERVER_PROMPT.get_user_template()

__all__ = ["ObserverPrompt", "OBSERVER_PROMPT", "OBSERVER_SYSTEM_PROMPT", "OBSERVER_USER_TEMPLATE"]
