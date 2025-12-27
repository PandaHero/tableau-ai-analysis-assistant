# -*- coding: utf-8 -*-
"""ReAct Error Handler Prompt - Error analysis and recovery decision.

When QueryPipeline encounters an error, this prompt guides the LLM to:
1. Analyze the error and identify root cause (Thought)
2. Decide on action: RETRY (from which step), CLARIFY, or ABORT (Action)
3. Generate appropriate feedback/message

Design principles (from appendix-e-prompt-model-guide.md):
- Prompt teaches LLM HOW to think (4-section structure)
- Schema tells LLM WHAT to output (XML tags in Field descriptions)
- Uses VizQLPrompt base class for automatic JSON Schema injection
"""

from typing import Type
from pydantic import BaseModel

from tableau_assistant.src.agents.base.prompt import VizQLPrompt
from tableau_assistant.src.agents.semantic_parser.models.react import ReActOutput


class ReActErrorHandlerPrompt(VizQLPrompt):
    """ReAct Error Handler: Analyze errors and decide recovery action.
    
    Uses 4-section structure:
    - ROLE: Define the AI's role
    - TASK: Define the task with implicit CoT
    - DOMAIN KNOWLEDGE: Provide domain-specific rules
    - CONSTRAINTS: Define boundaries
    """
    
    def get_role(self) -> str:
        return """Error analysis expert for data query pipeline.

Expertise: Root cause analysis, Error recovery strategy, User communication"""

    def get_task(self) -> str:
        return """Analyze pipeline error and decide the best recovery action.

**Pipeline Steps:**
- step1: Semantic understanding (extracts What/Where/How from user question)
- step2: Computation reasoning (designs complex calculations like LOD, ranking, YoY)
- map_fields: Field mapping (maps semantic fields to actual data source fields)
- build_query: Query building (converts to VizQL query)
- execute_query: Query execution (runs query on Tableau server)

**Available Actions:**
- RETRY: Go back to a specific step and retry with error feedback
- CLARIFY: Ask user for more information
- ABORT: Give up and explain the issue to user

**Think step by step:**
Step 1: Identify which step the error occurred in
Step 2: Analyze the error message to find root cause
Step 3: Determine if root cause is in current step or earlier step
Step 4: Decide action based on error type and recoverability
Step 5: Generate appropriate feedback/message in Chinese"""

    def get_specific_domain_knowledge(self) -> str:
        return """**Decision Guidelines:**

1. Error from execute_query (Tableau server error):
   - Query logic issue → RETRY from step1 or step2
   - Field reference issue → RETRY from map_fields
   - Server/permission issue → ABORT

2. Error from build_query:
   - Computation logic issue → RETRY from step2
   - If step2 output looks correct → RETRY from build_query with feedback

3. Error from map_fields:
   - Field not found after RAG+LLM fallback → ABORT (explain to user)
   - Ambiguous field → CLARIFY (ask user which field)

4. Error from step1/step2:
   - Output parsing error → RETRY same step
   - Logic error → RETRY with error feedback

**Common Error Patterns:**

1. LOD Expression Error:
   - Message: "FIXED requires at least one dimension"
   - Root cause: step2 computation design missing dimension
   - Action: RETRY from step2, feedback about dimension requirement

2. Invalid Field Reference:
   - Message: "Unknown field 'xxx'"
   - Root cause: map_fields mapped to wrong field
   - Action: RETRY from map_fields, or ABORT if field doesn't exist

3. Aggregation Mismatch:
   - Message: "Cannot mix aggregate and non-aggregate"
   - Root cause: step1 or step2 incorrectly classified aggregation
   - Action: RETRY from step1 with feedback

4. Field Not Found (from map_fields):
   - RAG+LLM both failed to find matching field
   - Action: ABORT with helpful user message

5. Computation Not Supported:
   - Query builder doesn't support the computation type
   - Action: RETRY from step2 with feedback about supported operations

**Error Feedback Guidelines:**
When setting error_feedback for RETRY, include:
- What went wrong (specific error)
- What the step should do differently (specific suggestion)
- Constraints to consider (if any)"""

    def get_constraints(self) -> str:
        return """MUST: Identify root cause step accurately
MUST: Provide clear error_feedback in Chinese when retrying
MUST: Generate user-friendly user_message in Chinese when aborting
MUST: Generate clear clarification_question in Chinese when clarifying
MUST NOT: Retry the same step more than 2 times
MUST NOT: Retry if error is clearly a data/permission issue"""

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

## Retry History
{retry_history}

Analyze the error root cause and decide the next action."""

    def get_output_model(self) -> Type[BaseModel]:
        return ReActOutput


# Create prompt instance
REACT_ERROR_PROMPT = ReActErrorHandlerPrompt()

__all__ = ["ReActErrorHandlerPrompt", "REACT_ERROR_PROMPT"]
