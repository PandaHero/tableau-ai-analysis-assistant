"""Semantic Parser Node - LangGraph workflow node.

This node wraps the SemanticParser Subgraph for use in the main LangGraph workflow.
The Subgraph implements the LangGraph node routing loop architecture:
    START → step1 → (conditional) → step2 | pipeline | END
    step2 → (conditional) → pipeline | END
    pipeline → (conditional) → react_error_handler | END
    react_error_handler → (conditional) → step1 | step2 | pipeline | END

Node Functions:
- semantic_parser_node: Main node that invokes the SemanticParser Subgraph
"""

import logging
from typing import Any, Dict, List

from langgraph.types import RunnableConfig
from langchain_core.messages import BaseMessage

# Import from core layer only (correct dependency direction)
from ...core.models import IntentType
from .state import SemanticParserState
from .models import Step1Output
from .subgraph import create_semantic_parser_subgraph

logger = logging.getLogger(__name__)

# Create compiled subgraph (singleton)
_semantic_parser_subgraph = None


def _get_subgraph():
    """Get or create the compiled SemanticParser Subgraph."""
    global _semantic_parser_subgraph
    if _semantic_parser_subgraph is None:
        graph = create_semantic_parser_subgraph()
        _semantic_parser_subgraph = graph.compile()
    return _semantic_parser_subgraph


async def semantic_parser_node(
    state: Dict[str, Any],
    config: RunnableConfig | None = None
) -> Dict[str, Any]:
    """
    Semantic Parser Agent node - invokes the SemanticParser Subgraph.
    
    The Subgraph implements the LangGraph node routing loop architecture:
    - step1: Semantic understanding (intent + what/where/how)
    - step2: Computation reasoning (only for non-SIMPLE queries)
    - pipeline: MapFields → BuildQuery → ExecuteQuery
    - react_error_handler: Analyze error and decide RETRY/CLARIFY/ABORT
    
    Args:
        state: Current state containing:
            - question: User's original question
            - messages: Conversation history (LangChain messages)
            - data_model: Data source metadata
        config: Runtime configuration
    
    Returns:
        Updated state with flattened fields (core layer types only):
            - intent_type: IntentType (core enum)
            - intent_reasoning: str
            - semantic_query: SemanticQuery (for DATA_QUERY intent)
            - restated_question: Restated question from Step 1
            - is_analysis_question: True if DATA_QUERY intent
            - semantic_parser_complete: Always True after completion
            - query_result: Query execution result (if pipeline succeeded)
            - clarification_question: Clarification question (for CLARIFY action)
            - user_message: User-facing message (for ABORT action)
            - pipeline_success: Whether pipeline execution succeeded
    """
    logger.info("SemanticParser node started")
    
    # Get question
    question = state.get("question", "")
    if not question:
        logger.warning("No question provided")
        return {
            "intent_type": None,
            "intent_reasoning": None,
            "semantic_query": None,
            "is_analysis_question": False,
            "semantic_parser_complete": True,
            "error": "No question provided",
        }
    
    # Build input state for Subgraph
    subgraph_input: Dict[str, Any] = {
        "question": question,
        "messages": state.get("messages", []),
        "data_model": state.get("data_model"),
        "datasource_luid": state.get("datasource_luid", "default"),
    }
    
    try:
        # Get compiled subgraph and invoke
        subgraph = _get_subgraph()
        result = await subgraph.ainvoke(subgraph_input, config=config)
        
        # Extract outputs from Subgraph result
        step1_output: Step1Output | None = result.get("step1_output")
        pipeline_success = result.get("pipeline_success", False)
        needs_clarification = result.get("needs_clarification", False)
        pipeline_aborted = result.get("pipeline_aborted", False)
        
        # Build return state with flattened fields (core layer types only)
        return_state: Dict[str, Any] = {
            "semantic_parser_complete": True,
            "current_stage": "semantic_parser",
        }
        
        # Handle case where step1 failed or returned non-DATA_QUERY intent
        if not step1_output:
            logger.warning("Subgraph returned no step1_output")
            return_state["intent_type"] = None
            return_state["intent_reasoning"] = None
            return_state["semantic_query"] = None
            return_state["is_analysis_question"] = False
            return_state["error"] = result.get("error", "Step 1 failed")
            return return_state
        
        # Extract intent information
        intent_type = step1_output.intent.type
        return_state["intent_type"] = intent_type
        return_state["intent_reasoning"] = step1_output.intent.reasoning
        return_state["restated_question"] = result.get("restated_question", step1_output.restated_question)
        return_state["thinking"] = result.get("thinking", "")
        
        # Route based on intent type
        if intent_type == IntentType.DATA_QUERY:
            return_state["is_analysis_question"] = True
            return_state["semantic_query"] = result.get("semantic_query")
            return_state["pipeline_success"] = pipeline_success
            
            if pipeline_success:
                # Pipeline succeeded - include query results
                return_state["query_result"] = result.get("query_result")
                return_state["columns"] = result.get("columns")
                return_state["row_count"] = result.get("row_count")
                return_state["file_path"] = result.get("file_path")
                return_state["is_large_result"] = result.get("is_large_result")
                return_state["mapped_query"] = result.get("mapped_query")
                return_state["vizql_query"] = result.get("vizql_query")
                return_state["execution_time_ms"] = result.get("execution_time_ms")
                
                # Build user message
                user_message = f"🔍 理解您的问题：{step1_output.restated_question}"
                row_count = result.get("row_count", 0)
                if row_count:
                    user_message += f"\n📊 查询完成，返回 {row_count} 条记录"
                return_state["user_message"] = user_message
                
                logger.info(
                    f"SemanticParser complete (DATA_QUERY, pipeline success): "
                    f"row_count={row_count}"
                )
                
            elif needs_clarification:
                # ReAct decided CLARIFY
                return_state["clarification_question"] = result.get("clarification_question")
                return_state["user_message"] = f"❓ {result.get('clarification_question', '请提供更多信息')}"
                logger.info("SemanticParser complete (DATA_QUERY, needs clarification)")
                
            elif pipeline_aborted:
                # ReAct decided ABORT
                return_state["user_message"] = result.get("user_message", "抱歉，无法处理您的请求。")
                return_state["pipeline_error"] = result.get("pipeline_error")
                logger.info("SemanticParser complete (DATA_QUERY, pipeline aborted)")
                
            else:
                # Pipeline failed but not handled by ReAct (shouldn't happen normally)
                return_state["pipeline_error"] = result.get("pipeline_error")
                return_state["user_message"] = "抱歉，查询执行失败，请稍后重试。"
                logger.warning("SemanticParser complete (DATA_QUERY, pipeline failed)")
        
        elif intent_type == IntentType.CLARIFICATION:
            return_state["is_analysis_question"] = False
            # Build clarification from step1 intent reasoning
            clarification_msg = f"请问您能具体说明一下吗？{step1_output.intent.reasoning}"
            return_state["clarification_question"] = clarification_msg
            return_state["non_analysis_response"] = clarification_msg
            return_state["user_message"] = f"❓ {clarification_msg}"
            logger.info("SemanticParser complete (CLARIFICATION)")
        
        elif intent_type == IntentType.GENERAL:
            return_state["is_analysis_question"] = False
            general_msg = step1_output.intent.reasoning or "您好！我是数据分析助手，可以帮您分析数据。请问您想了解什么？"
            return_state["general_response"] = general_msg
            return_state["non_analysis_response"] = general_msg
            return_state["user_message"] = general_msg
            logger.info("SemanticParser complete (GENERAL)")
        
        else:  # IRRELEVANT
            return_state["is_analysis_question"] = False
            irrelevant_msg = "抱歉，这个问题超出了我的能力范围。我是数据分析助手，可以帮您分析数据、查看趋势等。"
            return_state["non_analysis_response"] = irrelevant_msg
            return_state["user_message"] = irrelevant_msg
            logger.info("SemanticParser complete (IRRELEVANT)")
        
        return return_state
        
    except Exception as e:
        logger.error(f"SemanticParser node failed: {e}", exc_info=True)
        return {
            "intent_type": None,
            "intent_reasoning": None,
            "semantic_query": None,
            "is_analysis_question": False,
            "semantic_parser_complete": False,
            "error": str(e),
        }


__all__ = ["semantic_parser_node"]
