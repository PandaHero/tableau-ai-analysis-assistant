"""Semantic Parser Node - LangGraph workflow node.

This node wraps SemanticParserAgent for use in LangGraph workflows.
Implements the LLM combination architecture (Step1 + Step2 + Observer).
"""

import logging
from typing import Any, Dict, List

from langgraph.types import RunnableConfig
from langchain_core.messages import BaseMessage

from ...core.models import SemanticParseResult, IntentType
from .agent import SemanticParserAgent

logger = logging.getLogger(__name__)


async def semantic_parser_node(
    state: Dict[str, Any],
    config: RunnableConfig | None = None
) -> Dict[str, Any]:
    """
    Semantic Parser Agent node (LLM combination: Step1 + Step2 + Observer).
    
    Implements the LLM combination architecture:
    - Step 1: Semantic understanding + question restatement + intent classification
    - Step 2: Computation reasoning + self-validation (only for complex queries)
    - Observer: Consistency check (only when validation fails)
    
    Args:
        state: Current state containing:
            - question: User's original question
            - messages: Conversation history (LangChain messages)
            - metadata: Data source metadata
        config: Runtime configuration
    
    Returns:
        Updated state with:
            - semantic_parse_result: Full SemanticParseResult
            - semantic_query: SemanticQuery (for DATA_QUERY intent)
            - restated_question: Restated question from Step 1
            - is_analysis_question: True if DATA_QUERY intent
            - semantic_parser_complete: Always True after completion
            - clarification: Clarification question (for CLARIFICATION intent)
            - general_response: General response (for GENERAL intent)
    """
    logger.info("SemanticParser node started")
    
    # Get question
    question = state.get("question", "")
    if not question:
        logger.warning("No question provided")
        return {
            "semantic_parse_result": None,
            "semantic_query": None,
            "is_analysis_question": False,
            "semantic_parser_complete": True,
            "error": "No question provided",
        }
    
    # Convert messages to history format
    messages: List[BaseMessage] = state.get("messages", [])
    history = _convert_messages_to_history(messages)
    
    # Get data_model
    data_model = state.get("data_model")
    
    try:
        # Create and run SemanticParserAgent
        agent = SemanticParserAgent()
        result = await agent.parse(
            question=question,
            history=history,
            data_model=data_model,
            state=state,
            config=config,
        )
        
        # 获取 R1 模型的思考过程
        thinking = getattr(agent, '_last_thinking', '')
        
        # Build return state
        return_state: Dict[str, Any] = {
            "semantic_parse_result": result,
            "restated_question": result.restated_question,
            "semantic_parser_complete": True,
            "current_stage": "semantic_parser",
            "thinking": thinking,  # R1 模型的思考过程
        }
        
        # Route based on intent type
        intent_type = result.intent.type
        
        if intent_type == IntentType.DATA_QUERY:
            return_state["semantic_query"] = result.semantic_query
            return_state["is_analysis_question"] = True
            
            # 生成用户友好的消息
            user_message = f"🔍 理解您的问题：{result.restated_question}"
            if result.semantic_query:
                dims = [d.field_name for d in (result.semantic_query.dimensions or [])]
                measures = [m.field_name for m in (result.semantic_query.measures or [])]
                if dims:
                    user_message += f"\n📊 分析维度：{', '.join(dims)}"
                if measures:
                    user_message += f"\n📈 分析指标：{', '.join(measures)}"
            
            # 如果有思考过程，添加简短摘要
            if thinking:
                # 取思考过程的前 100 个字符作为摘要
                thinking_summary = thinking[:100] + "..." if len(thinking) > 100 else thinking
                return_state["thinking_summary"] = thinking_summary
            
            return_state["user_message"] = user_message
            
            logger.info(
                f"SemanticParser complete (DATA_QUERY): "
                f"restated='{result.restated_question[:50]}...'"
            )
        
        elif intent_type == IntentType.CLARIFICATION:
            return_state["clarification"] = result.clarification
            return_state["is_analysis_question"] = False
            clarification_msg = (
                result.clarification.question if result.clarification else
                "请提供更多信息以便我理解您的问题。"
            )
            return_state["non_analysis_response"] = clarification_msg
            return_state["user_message"] = f"❓ {clarification_msg}"
            logger.info(f"SemanticParser complete (CLARIFICATION)")
        
        elif intent_type == IntentType.GENERAL:
            return_state["general_response"] = result.general_response
            return_state["is_analysis_question"] = False
            general_msg = (
                result.general_response or
                "您好！我是数据分析助手，可以帮您分析数据。请问您想了解什么？"
            )
            return_state["non_analysis_response"] = general_msg
            return_state["user_message"] = general_msg
            logger.info(f"SemanticParser complete (GENERAL)")
        
        else:  # IRRELEVANT
            return_state["is_analysis_question"] = False
            irrelevant_msg = "抱歉，这个问题超出了我的能力范围。我是数据分析助手，可以帮您分析数据、查看趋势等。"
            return_state["non_analysis_response"] = irrelevant_msg
            return_state["user_message"] = irrelevant_msg
            logger.info(f"SemanticParser complete (IRRELEVANT)")
        
        return return_state
        
    except Exception as e:
        logger.error(f"SemanticParser node failed: {e}", exc_info=True)
        return {
            "semantic_parse_result": None,
            "semantic_query": None,
            "is_analysis_question": False,
            "semantic_parser_complete": False,
            "error": str(e),
        }


def _convert_messages_to_history(messages: List[BaseMessage]) -> List[Dict[str, str]]:
    """Convert LangChain messages to history format.
    
    Args:
        messages: LangChain BaseMessage list
    
    Returns:
        List of {"role": "user/assistant", "content": "..."} dicts
    
    注意：不在这里限制历史消息数量。
    历史消息的管理由 SummarizationMiddleware 负责：
    - 当 token 超过阈值时自动摘要
    - 保留最近 N 条消息（由 messages_to_keep 配置）
    """
    from langchain_core.messages import HumanMessage, AIMessage
    
    history = []
    for msg in messages:  # 不限制数量，由 SummarizationMiddleware 管理
        if isinstance(msg, HumanMessage):
            history.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AIMessage):
            history.append({"role": "assistant", "content": msg.content})
    return history


class SemanticParserNode:
    """LangGraph node class for Semantic Parser Agent.
    
    Alternative class-based interface for more control.
    """
    
    def __init__(self, max_retries: int = 2):
        """Initialize Semantic Parser Node.
        
        Args:
            max_retries: Maximum retries when Observer returns RETRY
        """
        self.max_retries = max_retries
    
    async def __call__(self, state: Dict[str, Any], config: RunnableConfig | None = None) -> Dict[str, Any]:
        """Execute the node."""
        return await semantic_parser_node(state, config)
    
    async def run(
        self,
        question: str,
        history: List[Dict[str, str]] | None = None,
        data_model: Any | None = None,
    ) -> SemanticParseResult:
        """Run the agent directly (without LangGraph state).
        
        Args:
            question: Current user question
            history: Conversation history
            data_model: Data source model (DataModel object)
            
        Returns:
            SemanticParseResult
        """
        agent = SemanticParserAgent(max_retries=self.max_retries)
        return await agent.parse(question, history, data_model)
