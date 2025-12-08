"""
Tableau Workflow Factory

Creates the main Tableau Assistant workflow with middleware support.

Workflow nodes (6 nodes, Boost merged into Understanding):
1. Understanding Agent (LLM) - Question classification + semantic understanding
2. FieldMapper Node (RAG + LLM hybrid) - Semantic field mapping
3. QueryBuilder Node (pure code) - VizQL query generation
4. Execute Node (pure code) - VizQL API execution
5. Insight Agent (LLM) - Data insight analysis
6. Replanner Agent (LLM) - Replan decision

Middleware stack (7 middleware):
- TodoListMiddleware (LangChain)
- SummarizationMiddleware (LangChain)
- ModelRetryMiddleware (LangChain)
- ToolRetryMiddleware (LangChain)
- HumanInTheLoopMiddleware (LangChain, optional)
- FilesystemMiddleware (custom)
- PatchToolCallsMiddleware (custom)
"""

from typing import Dict, Any, Optional, List, Sequence
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.base import BaseStore

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
from tableau_assistant.src.middleware import (
    FilesystemMiddleware,
    PatchToolCallsMiddleware,
)
from tableau_assistant.src.workflow.routes import (
    route_after_replanner,
    route_after_understanding,
)

# Import Node implementations
from tableau_assistant.src.nodes.field_mapper import field_mapper_node as _field_mapper_node
from tableau_assistant.src.nodes.query_builder import query_builder_node as _query_builder_node
from tableau_assistant.src.nodes.execute import execute_node as _execute_node

# Import Agent implementations
from tableau_assistant.src.agents.understanding import understanding_node as _understanding_node


def get_default_config() -> Dict[str, Any]:
    """
    Get default configuration from settings.
    
    All middleware config is managed via .env file through settings.
    """
    from tableau_assistant.src.config.settings import settings
    
    return {
        # SummarizationMiddleware
        # Adjust based on model context length, reserve 30% for output
        # - Claude 3.5: 200K context → threshold ~60K
        # - DeepSeek: 64K context → threshold ~20K
        # - Qwen: 32K context → threshold ~10K
        "summarization_token_threshold": settings.summarization_token_threshold,
        "messages_to_keep": settings.messages_to_keep,
        
        # RetryMiddleware
        "model_max_retries": settings.model_max_retries,
        "tool_max_retries": settings.tool_max_retries,
        
        # FilesystemMiddleware
        "filesystem_token_limit": settings.filesystem_token_limit,
        
        # HumanInTheLoopMiddleware
        "interrupt_on": settings.interrupt_on,
        
        # Replanner
        "max_replan_rounds": settings.max_replan_rounds,
    }


# For backward compatibility - lazy loaded
DEFAULT_CONFIG: Dict[str, Any] = {}


def create_middleware_stack(
    model_name: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
    chat_model: Optional[Any] = None,
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
    # Prefer chat_model if provided, otherwise use model_name string
    if chat_model is not None:
        middleware.append(SummarizationMiddleware(
            model=chat_model,
            trigger=("tokens", config["summarization_token_threshold"]),
            keep=("messages", config["messages_to_keep"]),
        ))
    elif model_name:
        middleware.append(SummarizationMiddleware(
            model=model_name,
            trigger=("tokens", config["summarization_token_threshold"]),
            keep=("messages", config["messages_to_keep"]),
        ))
    
    # 3. ModelRetryMiddleware - Auto-retry LLM calls
    middleware.append(ModelRetryMiddleware(
        max_retries=config["model_max_retries"]
    ))
    
    # 4. ToolRetryMiddleware - Auto-retry tool calls
    middleware.append(ToolRetryMiddleware(
        max_retries=config["tool_max_retries"]
    ))
    
    # 5. FilesystemMiddleware - Large result auto-save (custom)
    middleware.append(FilesystemMiddleware(
        tool_token_limit_before_evict=config["filesystem_token_limit"],
    ))
    
    # 6. PatchToolCallsMiddleware - Fix dangling tool calls (custom)
    middleware.append(PatchToolCallsMiddleware())
    
    # 7. HumanInTheLoopMiddleware - Human confirmation (optional)
    # interrupt_on should be a dict like {"write_todos": True} or {"tool_name": InterruptOnConfig(...)}
    interrupt_on = config.get("interrupt_on")
    if interrupt_on:
        # Convert list to dict if needed (for backward compatibility)
        if isinstance(interrupt_on, list):
            interrupt_on = {tool_name: True for tool_name in interrupt_on}
        middleware.append(HumanInTheLoopMiddleware(
            interrupt_on=interrupt_on
        ))
    
    return middleware


def create_tableau_workflow(
    model_name: Optional[str] = None,
    store: Optional[BaseStore] = None,
    config: Optional[Dict[str, Any]] = None,
    use_memory_checkpointer: bool = True,
    chat_model: Optional[Any] = None,
) -> StateGraph:
    """
    Create the Tableau Assistant workflow.
    
    The workflow contains 6 nodes:
    Understanding → FieldMapper → QueryBuilder → Execute → Insight → Replanner
    
    Note: Boost Agent has been removed, its functionality merged into Understanding Agent.
    
    All LLM nodes share the same middleware stack.
    
    Args:
        model_name: LLM model name (used if chat_model is None)
        store: Persistent storage instance
        config: Middleware and workflow configuration
        use_memory_checkpointer: Whether to use in-memory checkpointer (default True)
        chat_model: Pre-initialized ChatModel instance (preferred over model_name)
    
    Returns:
        Compiled StateGraph workflow
    
    Example:
        >>> from tableau_assistant.src.model_manager.llm import select_model
        >>> chat_model = select_model("qwen", "qwen3", temperature=0)
        >>> workflow = create_tableau_workflow(
        ...     chat_model=chat_model,
        ...     config={"max_replan_rounds": 5}
        ... )
        >>> result = workflow.invoke({"question": "2024年各地区销售额"})
    """
    # Import state from workflow models subpackage
    from tableau_assistant.src.models.workflow import VizQLState
    
    config = {**get_default_config(), **(config or {})}
    
    # Create middleware stack
    middleware = create_middleware_stack(model_name, config, chat_model)
    
    # Create StateGraph
    graph = StateGraph(VizQLState)
    
    # ========== Define placeholder node functions ==========
    # These will be replaced with actual implementations in subsequent tasks
    
    # Understanding Agent node uses actual implementation
    # imported from tableau_assistant.src.agents.understanding
    
    # Use the actual FieldMapper Node implementation
    # The _field_mapper_node is imported from tableau_assistant.src.nodes.field_mapper
    
    # QueryBuilder and Execute nodes use actual implementations
    # imported from tableau_assistant.src.nodes
    
    async def insight_node(state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Insight Agent node (LLM)
        
        - Call AnalysisCoordinator for progressive analysis
        - Generate final insight report
        
        Output: accumulated_insights
        """
        # TODO: Implement in task 18.1
        return {
            "current_stage": "insight",
        }
    
    async def replanner_node(state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Replanner Agent node (LLM)
        
        - Evaluate completeness (completeness_score)
        - Identify missing aspects (missing_aspects)
        - Generate new questions (new_questions)
        - Route decision: should_replan=True → Understanding, False → END
        
        Output: ReplanDecision
        """
        # TODO: Implement in task 19.1
        replan_count = state.get("replan_count", 0)
        return {
            "replan_decision": {
                "should_replan": False,
                "completeness_score": 1.0,
            },
            "replan_count": replan_count + 1,
            "current_stage": "replanner",
        }
    
    # ========== Add nodes to graph (6 nodes) ==========
    graph.add_node("understanding", _understanding_node)  # Use actual implementation
    graph.add_node("field_mapper", _field_mapper_node)  # Use actual implementation
    graph.add_node("query_builder", _query_builder_node)  # Use actual implementation
    graph.add_node("execute", _execute_node)  # Use actual implementation
    graph.add_node("insight", insight_node)
    graph.add_node("replanner", replanner_node)
    
    # ========== Add edges ==========
    
    # START → Understanding
    graph.add_edge(START, "understanding")
    
    # Understanding → FieldMapper or END (conditional)
    # If is_analysis_question=False, route to END
    graph.add_conditional_edges(
        "understanding",
        route_after_understanding,
        {
            "field_mapper": "field_mapper",
            "end": END,
        }
    )
    
    # FieldMapper → QueryBuilder
    graph.add_edge("field_mapper", "query_builder")
    
    # QueryBuilder → Execute
    graph.add_edge("query_builder", "execute")
    
    # Execute → Insight
    graph.add_edge("execute", "insight")
    
    # Insight → Replanner
    graph.add_edge("insight", "replanner")
    
    # Replanner → Understanding or END (conditional)
    graph.add_conditional_edges(
        "replanner",
        lambda state: route_after_replanner(state, config.get("max_replan_rounds", 3)),
        {
            "understanding": "understanding",
            "end": END,
        }
    )
    
    # ========== Compile graph ==========
    compile_kwargs = {}
    
    if use_memory_checkpointer:
        compile_kwargs["checkpointer"] = MemorySaver()
    
    if store:
        compile_kwargs["store"] = store
    
    # Note: LangGraph StateGraph.compile() doesn't directly support middleware parameter
    # Middleware is applied through langchain.agents.create_agent() for individual agents
    # For our custom workflow, we'll apply middleware at the node level in subsequent tasks
    
    compiled_graph = graph.compile(**compile_kwargs)
    
    # Store middleware and config for later use by nodes
    compiled_graph.middleware = middleware  # type: ignore
    compiled_graph.workflow_config = config  # type: ignore
    
    return compiled_graph


def get_workflow_info(workflow) -> Dict[str, Any]:
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
    
    return {
        "nodes": ["understanding", "field_mapper", "query_builder", "execute", "insight", "replanner"],
        "middleware": middleware_names,
        "config": config,
    }
