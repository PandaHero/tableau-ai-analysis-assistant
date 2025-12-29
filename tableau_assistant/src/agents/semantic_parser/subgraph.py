"""SemanticParser Subgraph - LangGraph Subgraph implementation.

This module creates a LangGraph StateGraph that implements the SemanticParser
as a Subgraph. The Subgraph can be used as a node in the main workflow.

Architecture (LangGraph Node Routing Loop):
    START → step1 → (conditional) → step2 | pipeline | END
    step2 → pipeline
    pipeline → (conditional) → react_error_handler | END
    react_error_handler → (conditional) → step1 | step2 | pipeline | END

Flow:
1. Step1: Semantic understanding (always runs)
2. Step2: Computation reasoning (only for non-SIMPLE queries)
3. Pipeline: MapFields → BuildQuery → ExecuteQuery (single execution)
4. ReAct Error Handler: Analyze error and decide RETRY/CLARIFY/ABORT
5. If RETRY: Loop back to appropriate step via LangGraph routing

Key Design:
- ReAct error handling is a separate LangGraph node
- Retry loop is implemented via LangGraph conditional edges
- State carries error_feedback and retry_from for retry logic
"""

import logging
from typing import Any, Dict, List, Literal, Optional

from langgraph.graph import StateGraph, START, END
from langgraph.types import RunnableConfig

from .state import SemanticParserState
from .models import Step1Output, Step2Output
from .models.pipeline import QueryResult, QueryError, QueryErrorType
from .models.react import ReActActionType, ReActOutput
from .components import (
    QueryPipeline,
    ReActErrorHandler,
    Step1Component,
    Step2Component,
)
from .components.react_error_handler import RetryRecord
from ...core.models import IntentType, HowType
from ...infra.config.settings import settings

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Node Functions
# ═══════════════════════════════════════════════════════════════════════════

async def step1_node(
    state: SemanticParserState,
    config: RunnableConfig | None = None,
) -> Dict[str, Any]:
    """Step 1 node: Semantic understanding.
    
    Extracts What/Where/How from user question and classifies intent.
    """
    logger.info("Subgraph Step1 node started")
    
    question = state.get("question", "")
    messages = state.get("messages", [])
    data_model = state.get("data_model")
    error_feedback = state.get("error_feedback")
    retry_from = state.get("retry_from")
    
    if not question:
        logger.warning("No question provided to Step 1")
        return {
            "step1_output": None,
            "current_stage": "semantic_parser.step1",
            "error": "No question provided",
        }
    
    # Convert messages to history format
    history = _convert_messages_to_history(messages)
    
    # Execute Step1
    component = Step1Component()
    
    try:
        step1_output, thinking = await component.execute(
            question=question,
            history=history if history else None,
            data_model=data_model,
            state=dict(state),
            config=config,
            error_feedback=error_feedback if retry_from == "step1" else None,
        )
        
        logger.info(
            f"Step 1 completed: intent={step1_output.intent.type}, "
            f"how_type={step1_output.how_type}"
        )
        
        return {
            "step1_output": step1_output,
            "restated_question": step1_output.restated_question,
            "current_stage": "semantic_parser.step1",
            "thinking": thinking,
            # Clear retry state after successful execution
            "retry_from": None,
            "error_feedback": None,
        }
        
    except Exception as e:
        logger.error(f"Step 1 failed: {e}", exc_info=True)
        return {
            "step1_output": None,
            "current_stage": "semantic_parser.step1",
            "pipeline_error": QueryError(
                type=QueryErrorType.STEP1_FAILED,
                message=str(e),
                step="step1",
                can_retry=True,
            ),
        }


async def step2_node(
    state: SemanticParserState,
    config: RunnableConfig | None = None,
) -> Dict[str, Any]:
    """Step 2 node: Computation reasoning.
    
    Designs complex calculations (LOD, ranking, YoY, etc.).
    Only called when step1_output.how_type != SIMPLE.
    """
    logger.info("Subgraph Step2 node started")
    
    step1_output: Step1Output | None = state.get("step1_output")
    error_feedback = state.get("error_feedback")
    retry_from = state.get("retry_from")
    
    if not step1_output:
        logger.error("Step 2 called without step1_output")
        return {
            "step2_output": None,
            "current_stage": "semantic_parser.step2",
            "pipeline_error": QueryError(
                type=QueryErrorType.STEP2_FAILED,
                message="step1_output is required for Step 2",
                step="step2",
                can_retry=False,
            ),
        }
    
    # Execute Step2
    component = Step2Component()
    
    try:
        step2_output = await component.execute(
            step1_output=step1_output,
            state=dict(state),
            config=config,
            error_feedback=error_feedback if retry_from == "step2" else None,
        )
        
        logger.info(
            f"Step 2 completed: computations={len(step2_output.computations)}, "
            f"all_valid={step2_output.validation.all_valid}"
        )
        
        return {
            "step2_output": step2_output,
            "current_stage": "semantic_parser.step2",
            # Clear retry state after successful execution
            "retry_from": None,
            "error_feedback": None,
        }
        
    except Exception as e:
        logger.error(f"Step 2 failed: {e}", exc_info=True)
        return {
            "step2_output": None,
            "current_stage": "semantic_parser.step2",
            "pipeline_error": QueryError(
                type=QueryErrorType.STEP2_FAILED,
                message=str(e),
                step="step2",
                can_retry=True,
            ),
        }


async def pipeline_node(
    state: SemanticParserState,
    config: RunnableConfig | None = None,
) -> Dict[str, Any]:
    """Pipeline node: Execute MapFields → BuildQuery → ExecuteQuery.
    
    This node executes the remaining pipeline steps after Step1/Step2.
    Single execution - no retry loop here. Errors are handled by react_error_handler_node.
    """
    logger.info("Subgraph Pipeline node started")
    
    step1_output: Step1Output | None = state.get("step1_output")
    step2_output: Step2Output | None = state.get("step2_output")
    question = state.get("question", "")
    data_model = state.get("data_model")
    datasource_luid = state.get("datasource_luid", "default")
    error_feedback = state.get("error_feedback")
    retry_from = state.get("retry_from")
    
    if not step1_output:
        logger.error("Pipeline called without step1_output")
        return {
            "pipeline_success": False,
            "current_stage": "semantic_parser.pipeline",
            "pipeline_error": QueryError(
                type=QueryErrorType.BUILD_FAILED,
                message="step1_output is required for Pipeline",
                step="pipeline",
                can_retry=False,
            ),
        }
    
    # Build state for QueryPipeline (include existing outputs for retry skip logic)
    pipeline_state: Dict[str, Any] = {
        "mapped_query": state.get("mapped_query"),
        "vizql_query": state.get("vizql_query"),
    }
    
    # Add error feedback if retrying from map_fields or build_query
    if retry_from in ("map_fields", "build_query") and error_feedback:
        pipeline_state["error_feedback"] = {
            "step": retry_from,
            "feedback": error_feedback,
        }
    
    # Execute QueryPipeline with new signature
    pipeline = QueryPipeline()
    
    try:
        result = await pipeline.execute(
            question=question,
            step1_output=step1_output,
            step2_output=step2_output,
            data_model=data_model,
            datasource_luid=datasource_luid,
            state=pipeline_state,
            config=config,
        )
        
        if result.success:
            logger.info(
                f"Pipeline completed successfully: "
                f"row_count={result.row_count}, "
                f"execution_time_ms={result.execution_time_ms}"
            )
            
            # Check if clarification is needed (filter value not found)
            if result.needs_clarification and result.clarification:
                logger.info(
                    f"Pipeline needs clarification: {result.clarification.get('type')}"
                )
                
                # Build clarification question from clarification info
                clarification = result.clarification
                available_values = clarification.get("available_values", [])
                user_values = clarification.get("user_values", [])
                
                clarification_question = (
                    f"{clarification.get('message', 'Filter value not found')}\n"
                    f"Your input: {', '.join(user_values)}\n"
                )
                if available_values:
                    clarification_question += f"Available values include: {', '.join(available_values[:10])}"
                    if len(available_values) > 10:
                        clarification_question += f" and {len(available_values) - 10} more"
                
                return {
                    "pipeline_success": True,  # Query executed successfully, just no results
                    "current_stage": "semantic_parser.pipeline",
                    "semantic_query": result.semantic_query,
                    "mapped_query": result.mapped_query,
                    "vizql_query": result.vizql_query,
                    "query_result": result.data,
                    "columns": result.columns,
                    "row_count": result.row_count,
                    "execution_time_ms": result.execution_time_ms,
                    # Clarification info
                    "needs_clarification": True,
                    "clarification_question": clarification_question,
                    # Clear retry state
                    "retry_from": None,
                    "error_feedback": None,
                    "pipeline_error": None,
                }
            
            return {
                "pipeline_success": True,
                "current_stage": "semantic_parser.pipeline",
                "semantic_query": result.semantic_query,
                "mapped_query": result.mapped_query,
                "vizql_query": result.vizql_query,
                "query_result": result.data,
                "columns": result.columns,
                "row_count": result.row_count,
                "file_path": result.file_path,
                "is_large_result": result.is_large_result,
                "execution_time_ms": result.execution_time_ms,
                # Clear retry state
                "retry_from": None,
                "error_feedback": None,
                "pipeline_error": None,
            }
        else:
            logger.warning(f"Pipeline failed: {result.error}")
            
            return {
                "pipeline_success": False,
                "current_stage": "semantic_parser.pipeline",
                "pipeline_error": result.error,
                "semantic_query": result.semantic_query,
                "mapped_query": result.mapped_query,
                "vizql_query": result.vizql_query,
            }
            
    except Exception as e:
        logger.error(f"Pipeline execution failed: {e}", exc_info=True)
        return {
            "pipeline_success": False,
            "current_stage": "semantic_parser.pipeline",
            "pipeline_error": QueryError(
                type=QueryErrorType.BUILD_FAILED,
                message=str(e),
                step="pipeline",
                can_retry=False,
            ),
        }


async def react_error_handler_node(
    state: SemanticParserState,
    config: RunnableConfig | None = None,
) -> Dict[str, Any]:
    """ReAct error handler node: Analyze error and decide next action.
    
    This node is called when pipeline_node fails. It uses LLM to:
    1. Analyze the error and identify root cause
    2. Decide action: CORRECT, RETRY, CLARIFY, or ABORT
    3. For CORRECT: Apply corrections directly to Step1/Step2 output
    4. For RETRY: Generate error_feedback for retry step
    
    The routing function will use react_action and retry_from to route
    back to the appropriate step.
    """
    logger.info("Subgraph ReAct error handler node started")
    
    pipeline_error: QueryError | None = state.get("pipeline_error")
    question = state.get("question", "")
    step1_output = state.get("step1_output")
    step2_output = state.get("step2_output")
    retry_history = state.get("retry_history") or []
    retry_count = state.get("retry_count") or 0
    
    if not pipeline_error:
        logger.warning("ReAct handler called without pipeline_error")
        return {
            "react_action": ReActActionType.ABORT,
            "user_message": "An unknown error occurred. Please try again later.",
            "current_stage": "semantic_parser.react_error_handler",
        }
    
    # Build pipeline context for error analysis
    pipeline_context: Dict[str, Any] = {
        "semantic_query": state.get("semantic_query"),
        "mapped_query": state.get("mapped_query"),
        "vizql_query": state.get("vizql_query"),
    }
    
    # Convert retry history to RetryRecord objects (unified type handling)
    retry_records: List[RetryRecord] = []
    for record in retry_history:
        if isinstance(record, RetryRecord):
            retry_records.append(record)
        elif isinstance(record, dict):
            retry_records.append(RetryRecord(
                step=record.get("step", ""),
                error_message=record.get("error_message", ""),
                action_taken=record.get("action_taken", ""),
                success=record.get("success", False),
            ))
    
    # Call ReAct error handler with new signature
    handler = ReActErrorHandler()
    
    try:
        output, corrected_step1, corrected_step2 = await handler.handle_error(
            error=pipeline_error,
            question=question,
            step1_output=step1_output,
            step2_output=step2_output,
            pipeline_context=pipeline_context,
            retry_history=retry_records,
            config=config,
        )
        
        logger.info(
            f"ReAct decision: action={output.action.action_type}, "
            f"error_category={output.thought.error_category}, "
            f"can_correct={output.thought.can_correct}"
        )
        
        # Create retry record for history
        new_record = handler.create_retry_record(
            step=pipeline_error.step,
            error_message=pipeline_error.message,
            action_taken=output.action.action_type.value,
            success=False,
        )
        new_retry_history = retry_history + [{
            "step": new_record.step,
            "error_message": new_record.error_message,
            "action_taken": new_record.action_taken,
            "success": new_record.success,
        }]
        
        # Build result based on action type
        result: Dict[str, Any] = {
            "react_action": output.action.action_type,
            "retry_history": new_retry_history,
            "retry_count": retry_count + 1,
            "current_stage": "semantic_parser.react_error_handler",
        }
        
        if output.action.action_type == ReActActionType.CORRECT:
            # Apply corrections and continue to pipeline
            result["step1_output"] = corrected_step1
            result["step2_output"] = corrected_step2
            # Clear error state and retry from pipeline
            result["pipeline_error"] = None
            result["retry_from"] = "pipeline"  # Re-run pipeline with corrected outputs
            logger.info("CORRECT action: Applied corrections, will re-run pipeline")
            
        elif output.action.action_type == ReActActionType.RETRY:
            result["retry_from"] = output.action.retry_from
            result["error_feedback"] = output.action.retry_guidance
            
            # Clear outputs from retry_from step onwards
            if output.action.retry_from == "step1":
                result["step1_output"] = None
                result["step2_output"] = None
                result["semantic_query"] = None
                result["mapped_query"] = None
                result["vizql_query"] = None
            elif output.action.retry_from == "step2":
                result["step2_output"] = None
                result["semantic_query"] = None
                result["mapped_query"] = None
                result["vizql_query"] = None
            elif output.action.retry_from == "map_fields":
                result["mapped_query"] = None
                result["vizql_query"] = None
            elif output.action.retry_from == "build_query":
                result["vizql_query"] = None
                
        elif output.action.action_type == ReActActionType.CLARIFY:
            result["needs_clarification"] = True
            result["clarification_question"] = output.action.clarification_question
            
        elif output.action.action_type == ReActActionType.ABORT:
            result["pipeline_aborted"] = True
            result["user_message"] = output.action.user_message
        
        return result
        
    except Exception as e:
        logger.error(f"ReAct error handler failed: {e}", exc_info=True)
        return {
            "react_action": ReActActionType.ABORT,
            "pipeline_aborted": True,
            "user_message": f"Error occurred while processing: {pipeline_error.message}",
            "current_stage": "semantic_parser.react_error_handler",
        }


# ═══════════════════════════════════════════════════════════════════════════
# Routing Functions
# ═══════════════════════════════════════════════════════════════════════════

def route_after_step1(state: SemanticParserState) -> Literal["step2", "pipeline", "__end__"]:
    """Route after Step 1 node.
    
    Routing logic:
    - If step1 failed (pipeline_error set): END (error will be in state)
    - If intent is not DATA_QUERY: END (no further processing needed)
    - If how_type is SIMPLE: pipeline (skip step2)
    - Otherwise: step2 (need computation reasoning)
    """
    pipeline_error = state.get("pipeline_error")
    if pipeline_error:
        logger.info("Route after step1: END (error)")
        return "__end__"
    
    step1_output: Step1Output | None = state.get("step1_output")
    if not step1_output:
        logger.warning("Route after step1: END (no output)")
        return "__end__"
    
    # Check intent type
    if step1_output.intent.type != IntentType.DATA_QUERY:
        logger.info(f"Route after step1: END (intent={step1_output.intent.type})")
        return "__end__"
    
    # Check how_type
    if step1_output.how_type == HowType.SIMPLE:
        logger.info("Route after step1: pipeline (SIMPLE query)")
        return "pipeline"
    else:
        logger.info(f"Route after step1: step2 (how_type={step1_output.how_type})")
        return "step2"


def route_after_step2(state: SemanticParserState) -> Literal["pipeline", "__end__"]:
    """Route after Step 2 node.
    
    Routing logic:
    - If step2 failed (pipeline_error set): END
    - Otherwise: pipeline
    """
    pipeline_error = state.get("pipeline_error")
    if pipeline_error:
        logger.info("Route after step2: END (error)")
        return "__end__"
    
    logger.info("Route after step2: pipeline")
    return "pipeline"


def route_after_pipeline(state: SemanticParserState) -> Literal["react_error_handler", "__end__"]:
    """Route after Pipeline node.
    
    Routing logic:
    - If pipeline succeeded: END
    - If pipeline needs clarification: END (return clarification to user)
    - If pipeline failed: react_error_handler
    """
    pipeline_success = state.get("pipeline_success")
    needs_clarification = state.get("needs_clarification")
    
    if pipeline_success:
        if needs_clarification:
            logger.info("Route after pipeline: END (needs clarification)")
        else:
            logger.info("Route after pipeline: END (success)")
        return "__end__"
    else:
        logger.info("Route after pipeline: react_error_handler")
        return "react_error_handler"


def route_after_react(
    state: SemanticParserState,
) -> Literal["step1", "step2", "pipeline", "__end__"]:
    """Route after ReAct error handler node.
    
    Routing logic based on react_action:
    - CORRECT: Route to pipeline (re-run with corrected outputs)
    - RETRY: Route to retry_from step (step1, step2, or pipeline for map_fields/build_query)
    - CLARIFY: END (return clarification question to user)
    - ABORT: END (return error message to user)
    
    Max retry check:
    - If retry_count >= max_retries (from settings): END (abort)
    """
    max_retries = settings.semantic_parser_max_retries
    
    react_action = state.get("react_action")
    retry_from = state.get("retry_from")
    retry_count = state.get("retry_count") or 0
    
    # Check max retries
    if retry_count >= max_retries:
        logger.warning(f"Route after react: END (max retries {max_retries} reached)")
        return "__end__"
    
    if react_action == ReActActionType.CORRECT:
        # CORRECT action: re-run pipeline with corrected outputs
        logger.info("Route after react: pipeline (CORRECT)")
        return "pipeline"
    
    if react_action == ReActActionType.RETRY:
        if retry_from == "step1":
            logger.info("Route after react: step1 (RETRY)")
            return "step1"
        elif retry_from == "step2":
            logger.info("Route after react: step2 (RETRY)")
            return "step2"
        elif retry_from in ("map_fields", "build_query", "pipeline"):
            # map_fields and build_query are inside pipeline_node
            logger.info(f"Route after react: pipeline (RETRY from {retry_from})")
            return "pipeline"
        else:
            logger.warning(f"Route after react: END (unknown retry_from: {retry_from})")
            return "__end__"
            
    elif react_action == ReActActionType.CLARIFY:
        logger.info("Route after react: END (CLARIFY)")
        return "__end__"
        
    elif react_action == ReActActionType.ABORT:
        logger.info("Route after react: END (ABORT)")
        return "__end__"
        
    else:
        logger.warning(f"Route after react: END (unknown action: {react_action})")
        return "__end__"


# ═══════════════════════════════════════════════════════════════════════════
# Helper Functions
# ═══════════════════════════════════════════════════════════════════════════

def _convert_messages_to_history(
    messages: List[Any],
) -> Optional[List[Dict[str, str]]]:
    """Convert LangChain messages to history format.
    
    Args:
        messages: List of LangChain messages
    
    Returns:
        List of dicts with 'role' and 'content' keys, or None if empty
    """
    if not messages:
        return None
    
    history = []
    for msg in messages:
        if hasattr(msg, "type") and hasattr(msg, "content"):
            role = "user" if msg.type == "human" else "assistant"
            history.append({"role": role, "content": msg.content})
    
    return history if history else None


# ═══════════════════════════════════════════════════════════════════════════
# Subgraph Factory
# ═══════════════════════════════════════════════════════════════════════════

def create_semantic_parser_subgraph() -> StateGraph:
    """Create the SemanticParser Subgraph.
    
    Architecture (LangGraph Node Routing Loop):
        START → step1 → (conditional) → step2 | pipeline | END
        step2 → (conditional) → pipeline | END
        pipeline → (conditional) → react_error_handler | END
        react_error_handler → (conditional) → step1 | step2 | pipeline | END
    
    Nodes:
    - step1: Semantic understanding (intent + what/where/how)
    - step2: Computation reasoning (LOD, ranking, etc.)
    - pipeline: MapFields → BuildQuery → ExecuteQuery
    - react_error_handler: Analyze error and decide RETRY/CLARIFY/ABORT
    
    Returns:
        Compiled StateGraph for SemanticParser
    """
    # Create graph with SemanticParserState
    graph = StateGraph(SemanticParserState)
    
    # Add nodes
    graph.add_node("step1", step1_node)
    graph.add_node("step2", step2_node)
    graph.add_node("pipeline", pipeline_node)
    graph.add_node("react_error_handler", react_error_handler_node)
    
    # Add edges
    # START → step1
    graph.add_edge(START, "step1")
    
    # step1 → (conditional) → step2 | pipeline | END
    graph.add_conditional_edges(
        "step1",
        route_after_step1,
        {
            "step2": "step2",
            "pipeline": "pipeline",
            "__end__": END,
        },
    )
    
    # step2 → (conditional) → pipeline | END
    graph.add_conditional_edges(
        "step2",
        route_after_step2,
        {
            "pipeline": "pipeline",
            "__end__": END,
        },
    )
    
    # pipeline → (conditional) → react_error_handler | END
    graph.add_conditional_edges(
        "pipeline",
        route_after_pipeline,
        {
            "react_error_handler": "react_error_handler",
            "__end__": END,
        },
    )
    
    # react_error_handler → (conditional) → step1 | step2 | pipeline | END
    graph.add_conditional_edges(
        "react_error_handler",
        route_after_react,
        {
            "step1": "step1",
            "step2": "step2",
            "pipeline": "pipeline",
            "__end__": END,
        },
    )
    
    logger.info("SemanticParser Subgraph created with LangGraph node routing loop")
    
    return graph


__all__ = [
    "create_semantic_parser_subgraph",
    "step1_node",
    "step2_node",
    "pipeline_node",
    "react_error_handler_node",
]
