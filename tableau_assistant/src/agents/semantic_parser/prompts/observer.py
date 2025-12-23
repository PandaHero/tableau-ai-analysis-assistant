# -*- coding: utf-8 -*-
"""Observer Prompts - Validation and correction (Metacognition).

Observer is the "Metacognition" phase of the LLM combination architecture.
It handles two scenarios:
1. Step 1 validation failed - correct filter issues (missing dates, etc.)
2. Step 2 validation failed - check consistency between Step 1 and Step 2

Design principles (from appendix-e-prompt-model-guide.md):
- Prompt teaches LLM HOW to think
- Schema tells LLM WHAT to output
- Uses VizQLPrompt base class for automatic JSON Schema injection
"""

from typing import Type
from pydantic import BaseModel

from tableau_assistant.src.agents.base.prompt import VizQLPrompt
from tableau_assistant.src.core.models import ObserverOutput


class Step1ObserverPrompt(VizQLPrompt):
    """Observer for Step 1 filter validation failures.
    
    Triggered when step1.validation.all_valid == False.
    Corrects filter issues like missing dates, missing values, etc.
    """
    
    def get_role(self) -> str:
        return """Quality assurance expert for semantic parsing.
You review Step 1 output to detect and correct filter validation issues.

Expertise: Filter validation, Date calculation, Correction decision making"""

    def get_task(self) -> str:
        return """Review Step 1 filter validation failures and correct them.

Process: Analyze validation issues → Calculate missing values → Output corrected filters"""

    def get_specific_domain_knowledge(self) -> str:
        return """**Filter Validation Rules**

1. DATE_RANGE Filter
   - MUST have at least one of start_date or end_date
   - Dates must be in YYYY-MM-DD format
   - Calculate dates based on user intent and current_time

2. TOP_N Filter
   - MUST have n (number of items)
   - MUST have by_field (measure to rank by)
   - direction defaults to DESC for "top", ASC for "bottom"

3. SET Filter
   - MUST have values (non-empty list)
   - Extract values from user question

**Date Calculation Examples**

Based on current_time, calculate concrete dates:
- "this year" (current_time: 2024-06-15) → start: 2024-01-01, end: 2024-12-31
- "last month" (current_time: 2024-06-15) → start: 2024-05-01, end: 2024-05-31
- "2024" → start: 2024-01-01, end: 2024-12-31
- "Q1 2024" → start: 2024-01-01, end: 2024-03-31
- "last year" (current_time: 2024-06-15) → start: 2023-01-01, end: 2023-12-31

**Correction Strategy**

1. Identify missing fields from validation.issues
2. Infer values from original_question and current_time
3. Output complete corrected_filters list (ALL filters, not just corrected ones)"""

    def get_constraints(self) -> str:
        return """MUST: Calculate concrete dates based on user intent, Output ALL filters in corrected_filters
MUST NOT: Leave any filter incomplete, Use placeholder values"""

    def get_user_template(self) -> str:
        return """**Original Question:** {original_question}

**Current Time:** {current_time}

**Step 1 Output:**
- restated_question: {restated_question}
- filters: {filters}

**Step 1 Validation:**
- all_valid: {all_valid}
- issues: {issues}
- filter_checks: {filter_checks}

Please analyze the validation issues and output ObserverOutput JSON with corrected filters."""

    def get_output_model(self) -> Type[BaseModel]:
        return ObserverOutput


class Step2ObserverPrompt(VizQLPrompt):
    """Observer for Step 2 consistency checking (original Observer).
    
    Triggered when step2.validation.all_valid == False.
    Checks consistency between Step 1 and Step 2 outputs.
    """
    
    def get_role(self) -> str:
        return """Quality assurance expert for semantic parsing.
You review Step 1 and Step 2 outputs to detect inconsistencies and make correction decisions.

Expertise: Consistency checking, Conflict detection, Decision making"""

    def get_task(self) -> str:
        return """Check consistency between Step 1 and Step 2 outputs, then make a decision.

Process: Check restatement → Review validation → Analyze conflicts → Decide action"""

    def get_specific_domain_knowledge(self) -> str:
        return """**Consistency Check Dimensions**

1. Restatement Completeness
   - Did restated_question preserve all key information from original_question?
   - Were scope modifiers preserved?

2. Structure Consistency
   - Review Step 2's self-validation results (target_check, partition_by_check, calc_type_check)
   - Identify which checks failed and why

3. Semantic Consistency
   - Does the inferred computation match the user's actual intent?
   - Is the computation logic reasonable for the question asked?

**Conflict Severity**

Conflicts can be classified by severity:
- Minor conflicts: Can be fixed by adjusting one field value
- Major conflicts: Require re-analysis from the beginning
- Ambiguous situations: Need user clarification"""

    def get_constraints(self) -> str:
        return """MUST: Check original_question, Review all validation results, Provide correction if fixable
MUST NOT: Accept when validation failed, Retry for minor fixable issues"""

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
- calc_type_check: {calc_type_check}
- all_valid: {all_valid}
- inconsistencies: {inconsistencies}

Please check consistency and output ObserverOutput JSON."""

    def get_output_model(self) -> Type[BaseModel]:
        return ObserverOutput


# Create prompt instances
STEP1_OBSERVER_PROMPT = Step1ObserverPrompt()
STEP2_OBSERVER_PROMPT = Step2ObserverPrompt()

# Keep backward compatibility
OBSERVER_PROMPT = STEP2_OBSERVER_PROMPT

__all__ = ["Step1ObserverPrompt", "Step2ObserverPrompt", "STEP1_OBSERVER_PROMPT", "STEP2_OBSERVER_PROMPT", "OBSERVER_PROMPT"]
