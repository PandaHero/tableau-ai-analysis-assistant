"""
SemanticParser Internal State Definition

Defines SemanticParserState for the SemanticParser Subgraph internal use.
This state extends VizQLState with SemanticParser-specific fields.

Architecture (Pyramid Structure):
- VizQLState (orchestration): Workflow state with all node outputs
- SemanticParserState (agent): Extends VizQLState with Subgraph internal fields:
  - step1_output: Step1Output (intent + what/where/how)
  - step2_output: Step2Output (computations)
  - pipeline_success: Whether pipeline execution succeeded
  - needs_clarification: Whether user clarification is needed
  - pipeline_aborted: Whether pipeline was aborted
  - retry_history: History of retry attempts

LangGraph Node Routing Loop:
- retry_from: Which step to retry from (set by react_error_handler_node)
- error_feedback: Feedback to pass to retry step
- react_action: ReAct action type (RETRY/CLARIFY/ABORT)
- pipeline_error: Error from pipeline execution
- retry_count: Number of retries attempted

Why separate?
- VizQLState contains final outputs visible to all nodes
- SemanticParserState adds internal fields only used within the Subgraph
- This allows Subgraph nodes to pass intermediate data without polluting main state
"""
from typing import Any, Dict, List, Optional

# Import from orchestration layer (correct dependency direction)
from ...orchestration.workflow.state import VizQLState
from .models import Step1Output, Step2Output
from .models.pipeline import QueryError
from .models.react import ReActActionType


class SemanticParserState(VizQLState):
    """
    SemanticParser Subgraph internal state.
    
    Extends VizQLState with Subgraph intermediate outputs:
    - step1_output: Step1Output (intent + what/where/how)
    - step2_output: Step2Output (computations)
    - pipeline_success: Whether pipeline execution succeeded
    - needs_clarification: Whether user clarification is needed
    - pipeline_aborted: Whether pipeline was aborted
    - retry_history: History of retry attempts
    
    LangGraph Node Routing Loop fields:
    - retry_from: Which step to retry from (set by react_error_handler_node)
    - error_feedback: Feedback to pass to retry step
    - react_action: ReAct action type (CORRECT/RETRY/CLARIFY/ABORT)
    - pipeline_error: Error from pipeline execution
    - retry_count: Number of retries attempted
    
    Used by:
    - step1_node: Writes step1_output
    - step2_node: Reads step1_output, writes step2_output
    - pipeline_node: Reads step1/step2 outputs, writes pipeline results
    - react_error_handler_node: Analyzes error, sets retry_from/error_feedback
    - SemanticParser Subgraph: Uses full SemanticParserState
    
    Note:
    - VizQLState contains flattened fields (intent_type, semantic_query, etc.)
    - These fields are for internal Subgraph communication only
    """
    
    # SemanticParser Subgraph intermediate outputs
    step1_output: Optional[Step1Output]  # Step1 output (intent + what/where/how)
    step2_output: Optional[Step2Output]  # Step2 output (computations)
    
    # Pipeline execution status
    pipeline_success: Optional[bool]  # Whether pipeline succeeded
    needs_clarification: Optional[bool]  # Whether clarification is needed
    pipeline_aborted: Optional[bool]  # Whether pipeline was aborted
    
    # ReAct error handling - LangGraph node routing loop
    retry_from: Optional[str]  # Which step to retry from (step1, step2, map_fields, build_query)
    error_feedback: Optional[str]  # Feedback to pass to retry step
    react_action: Optional[ReActActionType]  # ReAct action type (CORRECT/RETRY/CLARIFY/ABORT)
    pipeline_error: Optional[QueryError]  # Error from pipeline execution
    retry_count: Optional[int]  # Number of retries attempted
    retry_history: Optional[List[Dict[str, Any]]]  # History of retry attempts (RetryRecord dicts)
    
    # User-facing messages (from ReAct)
    clarification_question: Optional[str]  # Question to ask user (CLARIFY)
    user_message: Optional[str]  # Message to show user (ABORT)
    
    # Pipeline outputs (when successful)
    columns: Optional[List[Dict[str, Any]]]  # Column metadata
    row_count: Optional[int]  # Number of rows returned
    file_path: Optional[str]  # Path to large result file
    is_large_result: Optional[bool]  # Whether result was saved to file
    mapped_query: Optional[Dict[str, Any]]  # Mapped query
    vizql_query: Optional[Dict[str, Any]]  # VizQL query
    execution_time_ms: Optional[int]  # Execution time in milliseconds
    
    # Thinking process (from R1 model)
    thinking: Optional[str]  # R1 model thinking process


__all__ = ["SemanticParserState"]
