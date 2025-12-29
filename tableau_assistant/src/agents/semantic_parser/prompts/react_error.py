# -*- coding: utf-8 -*-
"""ReAct Error Handler Prompt - Error analysis and recovery decision.

When QueryPipeline encounters an error, this prompt guides the LLM to:
1. Analyze the error and identify root cause (Thought)
2. Decide on action: CORRECT, RETRY, CLARIFY, or ABORT (Action)
3. Generate specific corrections or guidance

Design principles (from prompt_and_models规范文档.md):
- Prompt teaches LLM HOW to think (domain concepts, analysis methods)
- Schema tells LLM WHAT to output (field meanings, fill rules, decision rules)
- Uses VizQLPrompt base class for automatic JSON Schema injection

Key Design:
- CORRECT: Directly fix Step1/Step2 output without re-running LLM
- RETRY: Go back to a step with specific guidance
- CLARIFY: Ask user for clarification
- ABORT: Give up and explain to user
"""

from typing import Type
from pydantic import BaseModel

from tableau_assistant.src.agents.base.prompt import VizQLPrompt
from tableau_assistant.src.agents.semantic_parser.models.react import ReActOutput


class ReActErrorHandlerPrompt(VizQLPrompt):
    """ReAct Error Handler: Analyze errors and decide recovery action.
    
    Uses 4-section structure per spec:
    - ROLE: VizQL semantic understanding supervisor
    - TASK: Analyze error and decide recovery action
    - DOMAIN KNOWLEDGE: VizQL capabilities and error analysis framework
    - CONSTRAINTS: Decision rules and output requirements
    """
    
    def get_role(self) -> str:
        return """VizQL semantic understanding supervisor and error recovery expert.

Expertise: 
- VizQL query capabilities (table calculations, LOD expressions)
- Semantic parsing error diagnosis and correction
- Guiding Step1/Step2 to produce correct, executable output

Background:
- VizQL supports table calculations that can derive measures from base measures
- PERCENT_DIFFERENCE can compute YoY/MoM growth from a single base measure
- LOD expressions (FIXED/INCLUDE/EXCLUDE) change aggregation granularity
- Each field_name in a query must be unique"""

    def get_task(self) -> str:
        return """Analyze pipeline error and decide the best recovery action.

Process: Identify error source → Categorize error → Analyze root cause → Decide action → Generate correction/guidance"""

    def get_specific_domain_knowledge(self) -> str:
        return """**VizQL Query Execution Model**
Query = Step1(semantic) → Step2(computation) → map_fields → build_query → execute

**Think step by step:**
Step 1: Identify error source (which step caused the error?)
Step 2: Understand error semantics (what does the error mean?)
Step 3: Determine root cause (why did this happen?)
Step 4: Decide action type:
  - Can I directly fix the output? → CORRECT
  - Does LLM need to re-think? → RETRY with guidance
  - Need user clarification? → CLARIFY
  - Cannot recover? → ABORT
Step 5: Generate specific correction or guidance

**Error Source Analysis**
- execute_query error with "field not unique" → Usually Step1 duplicate measures
- execute_query error with "unknown field" → Usually map_fields issue
- build_query error → Usually Step2 computation design issue
- map_fields error → Field reference or mapping issue
- step1/step2 parsing error → Output format issue

**VizQL Constraints**
- Each field_name must be unique in query
- Table calculations derive from base measures (no need for duplicate measures)
- LOD dimensions must exist in data source
- Partition dimensions must be subset of query dimensions

**Common Error Patterns**
1. "Field X isn't unique" → Step1 has duplicate measures with same field_name
   → CORRECT: remove_duplicate_measures, keep base measure only
2. "Unknown field X" → Field doesn't exist or wrong mapping
   → RETRY map_fields or ABORT if field truly doesn't exist
3. "Invalid computation" → Step2 computation logic error
   → RETRY step2 with specific guidance
4. "Permission denied" → Access issue
   → ABORT with explanation"""

    def get_constraints(self) -> str:
        return """MUST: Identify root cause accurately, not just where error occurred
MUST: Provide specific, actionable corrections or guidance in Chinese
MUST: Use CORRECT when output can be directly fixed (faster, no LLM call)
MUST: Use RETRY only when LLM re-thinking is truly needed
MUST NOT: Use RETRY for errors that can be directly corrected
MUST NOT: Retry the same step more than 2 times
MUST NOT: Retry if error is clearly a permission/data issue"""

    def get_user_template(self) -> str:
        return """## User Question
{question}

## Pipeline Execution Context
{pipeline_context}

## Error Information
- Step: {error_step}
- Type: {error_type}
- Message: {error_message}
- Details: {error_details}

## Step1 Output (if available)
{step1_output}

## Step2 Output (if available)
{step2_output}

## Retry History
{retry_history}

Analyze the error root cause and decide the next action."""

    def get_output_model(self) -> Type[BaseModel]:
        return ReActOutput


# Create prompt instance
REACT_ERROR_PROMPT = ReActErrorHandlerPrompt()

__all__ = ["ReActErrorHandlerPrompt", "REACT_ERROR_PROMPT"]
