# -*- coding: utf-8 -*-
"""
Tableau Workflow Factory

Creates the main Tableau Assistant workflow with middleware support.

Refactored Architecture (3 Agent Nodes):
1. SemanticParser Agent (Subgraph) - Step1 → Step2 → QueryPipeline (MapFields → BuildQuery → Execute)
   - ReAct error handling for tool failures
2. Insight Agent (Subgraph) - Profiler → Director ⟷ Analyst (progressive accumulation)
   - Director handles final synthesis (no separate Synthesizer)
3. Replanner Agent (single LLM node) - Evaluates completeness, generates exploration questions
   - Supports parallel execution via Send() API

Parallel Execution:
- When Replanner generates N>1 questions, route_after_replanner returns List[Send]
- LangGraph automatically handles parallel branch execution and state merging
- accumulated_insights uses merge_insights reducer for automatic deduplication

Middleware stack (8 middleware):
- TodoListMiddleware (LangChain)
- SummarizationMiddleware (LangChain)
- ModelRetryMiddleware (LangChain)
- ToolRetryMiddleware (LangChain)
- HumanInTheLoopMiddleware (LangChain, optional)
- FilesystemMiddleware (custom)
- PatchToolCallsMiddleware (custom)
- OutputValidationMiddleware (custom)
"""

from typing import Dict, Optional, List, Union, Any
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.store.base import BaseStore
from langchain_core.language_models import BaseChatModel

# LangChain middleware imports
from langchain.agents.middleware import (
    TodoListMiddleware,
    SummarizationMiddleware,
    ModelRetryMiddleware,
    ToolRetryMiddleware,
    HumanInTheLoopMiddleware,
    AgentMiddleware,
)

# Custom middleware imports
from tableau_assistant.src.orchestration.middleware import (
    FilesystemMiddleware,
    PatchToolCallsMiddleware,
    OutputValidationMiddleware,
)
from tableau_assistant.src.orchestration.workflow.routes import (
    route_after_replanner,
    route_after_semantic_parser,
)

# Import Subgraph implementations
from tableau_assistant.src.agents.semantic_parser.subgraph import create_semantic_parser_subgraph
from tableau_assistant.src.agents.insight.subgraph import create_insight_subgraph


def get_default_config() -> Dict[str, Union[int, float, List[str], None]]:
    """
    Get default configuration from settings.
    
    All middleware config is managed via .env file through settings.
    """
    from tableau_assistant.src.infra.config.settings import settings
    
    return {
        # SummarizationMiddleware
        # Adjust based on model context length, reserve 30% for output
        # - Claude 3.5: 200K context -> threshold ~60K
        # - DeepSeek: 64K context -> threshold ~20K
        # - Qwen: 32K context -> threshold ~10K
        "summarization_token_threshold": settings.summarization_token_threshold,
        "messages_to_keep": settings.messages_to_keep,
        
        # RetryMiddleware - Exponential backoff: initial_delay * backoff_factor^n
        # Default: 1s, 2s, 4s (backoff_factor=2.0)
        "model_max_retries": settings.model_max_retries,
        "model_initial_delay": 1.0,  # Initial delay in seconds
        "model_backoff_factor": 2.0,  # Exponential backoff factor
        "model_max_delay": 60.0,  # Maximum delay cap
        "tool_max_retries": settings.tool_max_retries,
        "tool_initial_delay": 1.0,
        "tool_backoff_factor": 2.0,
        "tool_max_delay": 60.0,
        
        # FilesystemMiddleware
        "filesystem_token_limit": settings.filesystem_token_limit,
        
        # HumanInTheLoopMiddleware
        "interrupt_on": settings.interrupt_on,
        
        # Replanner
        "max_replan_rounds": settings.max_replan_rounds,
    }


def create_middleware_stack(
    model_name: Optional[str] = None,
    config: Optional[Dict[str, Union[int, float, List[str], None]]] = None,
    chat_model: Optional[BaseChatModel] = None,
) -> List[AgentMiddleware]:
    """
    Create the middleware stack for the workflow.
    
    Args:
        model_name: LLM model name for SummarizationMiddleware (used if chat_model is None)
        config: Middleware configuration dictionary (overrides settings from .env)
        chat_model: Pre-initialized ChatModel instance (preferred over model_name)
    
    Returns:
        List of configured middleware instances
    """
    # Load defaults from settings, then override with provided config
    config = {**get_default_config(), **(config or {})}
    
    middleware: List[AgentMiddleware] = []
    
    # 1. TodoListMiddleware - Task queue management
    middleware.append(TodoListMiddleware())
    
    # 2. SummarizationMiddleware - Auto-summarize conversation history
    summarization_model = chat_model
    if summarization_model is None and model_name:
        summarization_model = model_name
    
    # If no model provided, use model manager to get default model
    if summarization_model is None:
        try:
            from tableau_assistant.src.infra.ai import get_llm
            summarization_model = get_llm(temperature=0)
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to create default model for SummarizationMiddleware: {e}")
    
    if summarization_model is not None:
        middleware.append(SummarizationMiddleware(
            model=summarization_model,
            trigger=("tokens", config["summarization_token_threshold"]),
            keep=("messages", config["messages_to_keep"]),
        ))
    
    # 3. ModelRetryMiddleware - Auto-retry LLM calls with exponential backoff
    middleware.append(ModelRetryMiddleware(
        max_retries=config["model_max_retries"],
        initial_delay=config.get("model_initial_delay", 1.0),
        backoff_factor=config.get("model_backoff_factor", 2.0),
        max_delay=config.get("model_max_delay", 60.0),
        jitter=True,
    ))
    
    # 4. ToolRetryMiddleware - Auto-retry tool calls with exponential backoff
    middleware.append(ToolRetryMiddleware(
        max_retries=config["tool_max_retries"],
        initial_delay=config.get("tool_initial_delay", 1.0),
        backoff_factor=config.get("tool_backoff_factor", 2.0),
        max_delay=config.get("tool_max_delay", 60.0),
        jitter=True,
    ))
    
    # 5. FilesystemMiddleware - Large result auto-save (custom)
    middleware.append(FilesystemMiddleware(
        tool_token_limit_before_evict=config["filesystem_token_limit"],
    ))
    
    # 6. PatchToolCallsMiddleware - Fix dangling tool calls (custom)
    middleware.append(PatchToolCallsMiddleware())
    
    # 7. HumanInTheLoopMiddleware - Human confirmation (optional)
    interrupt_on = config.get("interrupt_on")
    if interrupt_on:
        if isinstance(interrupt_on, list):
            interrupt_on = {tool_name: True for tool_name in interrupt_on}
        elif not isinstance(interrupt_on, dict):
            raise ValueError(
                "interrupt_on must be a list of tool names or a dict, "
                "e.g. ['write_todos'] or {'tool_name': True}"
            )
        middleware.append(HumanInTheLoopMiddleware(
            interrupt_on=interrupt_on
        ))
    
    # 8. OutputValidationMiddleware - Validate LLM output format (custom)
    # Note (Requirements 0.6): This is a FINAL QUALITY GATE, not a retry trigger
    # Format errors are handled by component-level retry (Step1/Step2)
    # Semantic errors are handled by ReAct
    # This middleware only logs and alerts, does NOT trigger retries
    #
    # Configuration:
    # - expected_schema: Not set (format validation is done at component level)
    # - required_state_fields: Final state fields that must be present
    # - strict=False: Log warnings instead of raising exceptions
    # - retry_on_failure=False: Quality gate mode, no retry trigger
    middleware.append(OutputValidationMiddleware(
        expected_schema=None,  # Format validation at component level
        required_state_fields=[
            "intent_type",  # Must have intent classification
        ],
        strict=False,
        retry_on_failure=False,  # Quality gate mode: log + alert only
    ))
    
    return middleware


def create_workflow(
    model_name: Optional[str] = None,
    store: Optional[BaseStore] = None,
    config: Optional[Dict[str, Union[int, float, List[str], None]]] = None,
    use_memory_checkpointer: bool = True,
    use_sqlite_checkpointer: bool = False,
    sqlite_db_path: Optional[str] = None,
    chat_model: Optional[BaseChatModel] = None,
) -> StateGraph:
    """
    Create the Tableau Assistant workflow.
    
    Refactored Architecture (3 Agent Nodes):
    - SemanticParser (Subgraph): Step1 → Step2 → QueryPipeline
    - Insight (Subgraph): Profiler → Director ⟷ Analyst
    - Replanner (single node): Evaluates completeness, generates exploration questions
    
    Parallel Execution:
    - When Replanner generates N>1 questions, route_after_replanner returns List[Send]
    - LangGraph automatically handles parallel branch execution and state merging
    
    Checkpointer options (mutually exclusive):
    - use_memory_checkpointer=True: In-memory checkpointer (default, for development)
    - use_sqlite_checkpointer=True: SQLite checkpointer (for production persistence)
    
    Args:
        model_name: LLM model name (used if chat_model is None)
        store: Persistent storage instance
        config: Middleware and workflow configuration
        use_memory_checkpointer: Whether to use in-memory checkpointer (default True)
        use_sqlite_checkpointer: Whether to use SQLite checkpointer (default False)
        sqlite_db_path: Path to SQLite database file (default: data/workflow_checkpoints.db)
        chat_model: Pre-initialized ChatModel instance (preferred over model_name)
    
    Returns:
        Compiled StateGraph workflow
    
    Example:
        >>> from tableau_assistant.src.infra.ai import get_llm
        >>> chat_model = get_llm(temperature=0)
        >>> # Development: in-memory checkpointer
        >>> workflow = create_workflow(
        ...     chat_model=chat_model,
        ...     config={"max_replan_rounds": 5}
        ... )
        >>> # Production: SQLite checkpointer for session persistence
        >>> workflow = create_workflow(
        ...     chat_model=chat_model,
        ...     use_memory_checkpointer=False,
        ...     use_sqlite_checkpointer=True,
        ...     sqlite_db_path="data/sessions.db"
        ... )
        >>> result = workflow.invoke({"question": "2024年各地区销售额"})
    """
    # Import state from orchestration layer
    from tableau_assistant.src.orchestration.workflow.state import VizQLState
    
    config = {**get_default_config(), **(config or {})}
    
    # Create middleware stack
    middleware = create_middleware_stack(model_name, config, chat_model)
    
    # Create StateGraph
    graph = StateGraph(VizQLState)
    
    # ========== Create Subgraphs ==========
    semantic_parser_subgraph = create_semantic_parser_subgraph()
    insight_subgraph = create_insight_subgraph()
    
    # ========== Replanner Node (single LLM node) ==========
    async def replanner_node(state: "VizQLState", runnable_config: Optional[Dict[str, Any]] = None) -> Dict[str, object]:
        """
        Replanner Agent node (LLM)
        
        - Evaluate completeness (completeness_score)
        - Identify missing aspects (missing_aspects)
        - Generate exploration questions (exploration_questions)
        - Route decision: should_replan=True -> SemanticParser, False -> END
        
        Parallel Execution Support:
        - When N>1 questions generated, sets parallel_questions for Send() API
        - Single question: sets question for serial execution
        
        Output: ReplanDecision Pydantic object
        """
        from tableau_assistant.src.agents.replanner import ReplannerAgent
        from tableau_assistant.src.agents.replanner.models import ReplanDecision
        
        replan_count = state.get("replan_count", 0)
        
        # Get current insights (use accumulated_insights from parallel execution if available)
        accumulated_insights = state.get("accumulated_insights", [])
        insights = accumulated_insights if accumulated_insights else state.get("insights", [])
        
        # Edge case: no insights
        if not insights:
            decision = ReplanDecision(
                should_replan=False,
                completeness_score=0.0,
                reason="No insights available, cannot evaluate completeness",
                missing_aspects=[],
                exploration_questions=[],
            )
            return {
                "replan_decision": decision,
                "replan_count": replan_count + 1,
                "current_stage": "replanner",
                "replanner_complete": True,
            }
        
        # Create ReplannerAgent instance
        replanner = ReplannerAgent(
            max_replan_rounds=config.get("max_replan_rounds", 3),
            max_questions_per_round=config.get("max_questions_per_round", 3),
        )
        
        # Get answered questions for deduplication
        answered_questions = state.get("answered_questions", [])
        
        # Execute replan decision
        decision = await replanner.replan(
            original_question=state.get("question", ""),
            insights=insights,
            data_insight_profile=state.get("data_insight_profile"),
            dimension_hierarchy=state.get("dimension_hierarchy"),
            current_dimensions=state.get("current_dimensions", []),
            current_round=replan_count + 1,
            answered_questions=answered_questions,
            state=dict(state),
            config=runnable_config,
        )
        
        # Record replan history
        replan_history_entry = {
            "round": replan_count + 1,
            "completeness_score": decision.completeness_score,
            "should_replan": decision.should_replan,
            "reason": decision.reason,
            "questions_count": len(decision.exploration_questions),
        }
        
        # Build result
        result = {
            "replan_decision": decision,
            "replan_count": replan_count + 1,
            "replan_history": [replan_history_entry],
            "current_stage": "replanner",
            "replanner_complete": True,
        }
        
        # Handle exploration questions for parallel/serial execution
        if decision.should_replan and decision.exploration_questions:
            from langchain_core.messages import HumanMessage
            
            original_question = state.get("question", "")
            
            # Extract question texts
            question_texts = []
            for q in decision.exploration_questions:
                if hasattr(q, "question"):
                    question_texts.append(q.question)
                elif isinstance(q, dict):
                    question_texts.append(q.get("question", str(q)))
                else:
                    question_texts.append(str(q))
            
            if len(question_texts) == 1:
                # Single question: serial execution
                next_question = question_texts[0]
                result["question"] = next_question
                result["parallel_questions"] = []
                
                # Add to conversation history
                replanner_message = HumanMessage(
                    content=next_question,
                    additional_kwargs={
                        "source": "replanner",
                        "parent_question": original_question,
                    }
                )
                result["messages"] = [replanner_message]
            else:
                # Multiple questions: parallel execution via Send() API
                # route_after_replanner will handle creating Send() objects
                result["parallel_questions"] = question_texts
                result["question"] = question_texts[0]  # First question for logging
                
                # Add all questions to conversation history
                messages = []
                for q_text in question_texts:
                    messages.append(HumanMessage(
                        content=q_text,
                        additional_kwargs={
                            "source": "replanner",
                            "parent_question": original_question,
                            "parallel": True,
                        }
                    ))
                result["messages"] = messages
        
        return result
    
    # ========== Add nodes to graph (3 nodes) ==========
    graph.add_node("semantic_parser", semantic_parser_subgraph)
    graph.add_node("insight", insight_subgraph)
    graph.add_node("replanner", replanner_node)
    
    # ========== Add edges ==========
    
    # START -> SemanticParser
    graph.add_edge(START, "semantic_parser")
    
    # SemanticParser -> Insight or END (conditional)
    # If intent.type != DATA_QUERY or query failed, route to END
    graph.add_conditional_edges(
        "semantic_parser",
        route_after_semantic_parser,
        {
            "insight": "insight",
            "end": END,
        }
    )
    
    # Insight -> Replanner
    graph.add_edge("insight", "replanner")
    
    # Replanner -> SemanticParser or END (conditional)
    # Supports parallel execution via Send() API
    graph.add_conditional_edges(
        "replanner",
        lambda state: route_after_replanner(state, config.get("max_replan_rounds", 3)),
        {
            "semantic_parser": "semantic_parser",
            "end": END,
        }
    )
    
    # ========== Compile graph ==========
    compile_kwargs = {}
    
    # Checkpointer selection (mutually exclusive)
    if use_sqlite_checkpointer:
        from pathlib import Path
        import sqlite3
        db_path = sqlite_db_path or "data/workflow_checkpoints.db"
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path, check_same_thread=False)
        compile_kwargs["checkpointer"] = SqliteSaver(conn)
    elif use_memory_checkpointer:
        compile_kwargs["checkpointer"] = MemorySaver()
    
    if store:
        compile_kwargs["store"] = store
    
    compiled_graph = graph.compile(**compile_kwargs)
    
    # Store middleware and config for later use by nodes
    compiled_graph.middleware = middleware  # type: ignore
    compiled_graph.workflow_config = config  # type: ignore
    
    return compiled_graph


def get_workflow_info(workflow: StateGraph) -> Dict[str, object]:
    """
    Get information about the workflow configuration.
    
    Args:
        workflow: Compiled StateGraph workflow
    
    Returns:
        Dictionary containing workflow information
    """
    middleware_names = []
    if hasattr(workflow, 'middleware'):
        middleware_names = [type(m).__name__ for m in workflow.middleware]
    
    config = getattr(workflow, 'workflow_config', get_default_config())
    
    # Get checkpointer type
    checkpointer_type = "none"
    if hasattr(workflow, 'checkpointer') and workflow.checkpointer:
        checkpointer_type = type(workflow.checkpointer).__name__
    
    return {
        "nodes": ["semantic_parser", "insight", "replanner"],
        "middleware": middleware_names,
        "checkpointer": checkpointer_type,
        "config": config,
        "architecture": "subgraph_with_parallel",  # 3 nodes with Send() API support
    }


def create_sqlite_checkpointer(db_path: str = "data/workflow_checkpoints.db") -> SqliteSaver:
    """
    Create a SQLite checkpointer for session persistence.
    
    Args:
        db_path: Path to SQLite database file
    
    Returns:
        Configured SqliteSaver instance
    """
    from pathlib import Path
    import sqlite3
    
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    
    return SqliteSaver(conn)


def get_session_history(
    checkpointer: SqliteSaver,
    thread_id: str,
) -> List[Dict[str, object]]:
    """
    Get session history from SQLite checkpointer.
    
    Args:
        checkpointer: SqliteSaver instance
        thread_id: Thread/session ID
    
    Returns:
        List of checkpoint metadata
    """
    try:
        config = {"configurable": {"thread_id": thread_id}}
        checkpoint = checkpointer.get(config)
        if checkpoint:
            return [checkpoint.metadata] if checkpoint.metadata else []
        return []
    except Exception:
        return []


def inject_middleware_to_config(
    config: Optional[Dict[str, Any]],
    middleware: List[AgentMiddleware],
) -> Dict[str, Any]:
    """
    Inject middleware into config for node functions.
    
    Args:
        config: Original config (can be None)
        middleware: Middleware list
    
    Returns:
        New config containing middleware
    """
    config = config or {}
    configurable = config.get('configurable', {})
    configurable['middleware'] = middleware
    config['configurable'] = configurable
    return config
