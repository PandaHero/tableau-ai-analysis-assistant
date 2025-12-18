# -*- coding: utf-8 -*-
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
    route_after_understanding,
)

# Import Node implementations
from tableau_assistant.src.agents.field_mapper import field_mapper_node as _field_mapper_node
from tableau_assistant.src.nodes.query_builder import query_builder_node as _query_builder_node
from tableau_assistant.src.nodes.execute import execute_node as _execute_node

# Import Agent implementations
# Use new SemanticParserAgent instead of old UnderstandingAgent
from tableau_assistant.src.agents.semantic_parser.node import semantic_parser_node as _semantic_parser_node
from tableau_assistant.src.agents.insight.node import insight_node as _insight_node


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
    # 必须创建 SummarizationMiddleware，使用模型管理器获取默认模型
    # Prefer chat_model if provided, otherwise use model_name, otherwise use model manager
    summarization_model = chat_model
    if summarization_model is None and model_name:
        summarization_model = model_name
    
    # 如果没有提供模型，使用模型管理器获取默认模型
    if summarization_model is None:
        try:
            from tableau_assistant.src.infra.ai.llm import select_model
            from tableau_assistant.src.infra.config.settings import settings
            # 使用配置中的模型提供商和模型名称
            summarization_model = select_model(
                provider=settings.llm_model_provider,
                model_name=settings.tooling_llm_model,
                temperature=0,
            )
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
    # Backoff strategy: 1s, 2s, 4s (initial_delay * backoff_factor^n)
    # **Property 17: LLM 重试指数退避**
    # **Validates: Requirements 9.1, 9.2, 9.3, 9.4**
    middleware.append(ModelRetryMiddleware(
        max_retries=config["model_max_retries"],
        initial_delay=config.get("model_initial_delay", 1.0),
        backoff_factor=config.get("model_backoff_factor", 2.0),
        max_delay=config.get("model_max_delay", 60.0),
        jitter=True,  # Add randomness to prevent thundering herd
    ))
    
    # 4. ToolRetryMiddleware - Auto-retry tool calls with exponential backoff
    # **Validates: Requirements 10.1, 10.2, 10.3, 10.4**
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
    # **Validates: Requirements 15.1, 15.2, 15.3, 15.4, 15.5**
    # interrupt_on should be a dict like {"write_todos": True} or {"tool_name": InterruptOnConfig(...)}
    interrupt_on = config.get("interrupt_on")
    if interrupt_on:
        # Convert list of tool names to dict format if needed
        # Settings returns list[str] like ["write_todos", "execute_query"]
        # HumanInTheLoopMiddleware expects dict[str, bool | InterruptOnConfig]
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
    # **Validates: Requirements 15.1, 15.2, 15.3, 15.4, 15.5, 15.6**
    # Note: expected_schema is set per-node, not globally
    # This middleware validates JSON format and triggers retry on failure
    middleware.append(OutputValidationMiddleware(
        strict=False,  # Non-strict mode: log warnings instead of raising
        retry_on_failure=True,  # Trigger ModelRetryMiddleware on validation failure
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
    
    The workflow contains 6 nodes:
    Understanding -> FieldMapper -> QueryBuilder -> Execute -> Insight -> Replanner
    
    Note: Boost Agent has been removed, its functionality merged into Understanding Agent.
    
    All LLM nodes share the same middleware stack.
    
    Checkpointer options (mutually exclusive):
    - use_memory_checkpointer=True: In-memory checkpointer (default, for development)
    - use_sqlite_checkpointer=True: SQLite checkpointer (for production persistence)
    
    **Validates: Requirements 18.4, 18.5**
    
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
        >>> from tableau_assistant.src.infra.ai.llm import select_model
        >>> chat_model = select_model("qwen", "qwen3", temperature=0)
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
    # Import state from orchestration workflow
    from tableau_assistant.src.orchestration.workflow.state import VizQLState
    
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
    # The _field_mapper_node is imported from tableau_assistant.src.agents.field_mapper
    
    # QueryBuilder and Execute nodes use actual implementations
    # imported from tableau_assistant.src.nodes
    
    # insight_node 使用实际实现（从 tableau_assistant.src.agents.insight.node 导入）
    
    async def replanner_node(state: "VizQLState") -> Dict[str, object]:
        """
        Replanner Agent node (LLM)
        
        - Evaluate completeness (completeness_score)
        - Identify missing aspects (missing_aspects)
        - Generate new questions (new_questions)
        - Route decision: should_replan=True -> Understanding, False -> END
        
        Output: ReplanDecision Pydantic object
        
        **Validates: Requirements 17.1, 17.2, 17.3, 17.4, 17.5, 17.6, 17.8**
        """
        from tableau_assistant.src.agents.replanner import ReplannerAgent
        from tableau_assistant.src.core.models import ReplanDecision
        
        replan_count = state.get("replan_count", 0)
        
        # 获取当前洞察 (insights 是 Pydantic 对象列表)
        insights = state.get("insights", [])
        
        # 边界处理：没有洞察结果
        # **Validates: Requirements 17.8**
        if not insights:
            # 返回 ReplanDecision Pydantic 对象
            decision = ReplanDecision(
                should_replan=False,
                completeness_score=0.0,
                reason="没有洞察结果，无法评估完成度",
                missing_aspects=[],
                exploration_questions=[],
            )
            return {
                "replan_decision": decision,
                "replan_count": replan_count + 1,
                "current_stage": "replanner",
            }
        
        # 创建 ReplannerAgent 实例
        replanner = ReplannerAgent(
            max_replan_rounds=config.get("max_replan_rounds", 3),
            max_questions_per_round=config.get("max_questions_per_round", 3),
        )
        
        # 获取已回答问题列表（用于去重）
        # **Validates: Requirements 14.3, 14.4, 14.5**
        answered_questions = state.get("answered_questions", [])
        
        # 使用 trim_answered_questions 限制长度
        from tableau_assistant.src.infra.utils.conversation import trim_answered_questions
        trimmed_questions = trim_answered_questions(answered_questions)
        
        # 执行重规划决策 - insights 是 Pydantic 对象列表
        decision = await replanner.replan(
            original_question=state.get("question", ""),
            insights=insights,  # 直接传递 Pydantic 对象列表
            data_insight_profile=state.get("data_insight_profile"),
            dimension_hierarchy=state.get("dimension_hierarchy"),
            current_dimensions=state.get("current_dimensions", []),
            current_round=replan_count + 1,
            answered_questions=trimmed_questions,  # 传递已回答问题用于去重
        )
        
        # 记录重规划历史
        # **Validates: Requirements 17.9**
        replan_history = state.get("replan_history", [])
        replan_history.append({
            "round": replan_count + 1,
            "completeness_score": decision.completeness_score,
            "should_replan": decision.should_replan,
            "reason": decision.reason,
            "questions_count": len(decision.exploration_questions),
        })
        
        # 构建返回结果
        result = {
            "replan_decision": decision,
            "replan_count": replan_count + 1,
            "replan_history": replan_history,
            "current_stage": "replanner",
        }
        
        # 如果需要重规划，将探索问题添加到待处理队列
        # TodoListMiddleware 会管理这些问题的执行
        if decision.should_replan and decision.exploration_questions:
            from langchain_core.messages import HumanMessage
            
            # 获取原始问题用于标记 parent_question
            original_question = state.get("question", "")
            
            # 将探索问题转换为待处理问题列表
            pending_questions = []
            for q in decision.exploration_questions:
                if hasattr(q, "question"):
                    pending_questions.append({
                        "question": q.question,
                        "priority": getattr(q, "priority", 5),
                        "exploration_type": getattr(q, "exploration_type", "drill_down"),
                        "target_dimension": getattr(q, "target_dimension", ""),
                    })
                elif isinstance(q, dict):
                    pending_questions.append(q)
            
            # 更新 question 为第一个探索问题（当前轮次处理）
            if pending_questions:
                next_question = pending_questions[0]["question"]
                result["question"] = next_question
                
                # 创建带来源标记的消息，添加到对话历史
                # 标记 replanner 生成的问题，并关联原始问题
                replanner_message = HumanMessage(
                    content=next_question,
                    additional_kwargs={
                        "source": "replanner",
                        "parent_question": original_question,
                    }
                )
                result["messages"] = [replanner_message]
                
                # 剩余问题存入队列，供后续轮次处理
                result["pending_questions"] = pending_questions[1:] if len(pending_questions) > 1 else []
        
        return result
    
    # ========== Add nodes to graph (6 nodes) ==========
    # Use new SemanticParserAgent (LLM combination: Step1 + Step2 + Observer)
    graph.add_node("understanding", _semantic_parser_node)  # Renamed from understanding to semantic_parser
    graph.add_node("field_mapper", _field_mapper_node)  # Use actual implementation
    graph.add_node("query_builder", _query_builder_node)  # Use actual implementation
    graph.add_node("execute", _execute_node)  # Use actual implementation
    graph.add_node("insight", _insight_node)  # Use actual implementation
    graph.add_node("replanner", replanner_node)
    
    # ========== Add edges ==========
    
    # START -> Understanding
    graph.add_edge(START, "understanding")
    
    # Understanding -> FieldMapper or END (conditional)
    # If is_analysis_question=False, route to END
    graph.add_conditional_edges(
        "understanding",
        route_after_understanding,
        {
            "field_mapper": "field_mapper",
            "end": END,
        }
    )
    
    # FieldMapper -> QueryBuilder
    graph.add_edge("field_mapper", "query_builder")
    
    # QueryBuilder -> Execute
    graph.add_edge("query_builder", "execute")
    
    # Execute -> Insight
    graph.add_edge("execute", "insight")
    
    # Insight -> Replanner
    graph.add_edge("insight", "replanner")
    
    # Replanner -> Understanding or END (conditional)
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
    
    # Checkpointer selection (mutually exclusive)
    # **Validates: Requirements 18.4, 18.5**
    if use_sqlite_checkpointer:
        # SQLite checkpointer for production persistence
        # Supports session save/restore across restarts
        from pathlib import Path
        import sqlite3
        db_path = sqlite_db_path or "data/workflow_checkpoints.db"
        # Ensure directory exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        # Create SQLite connection and checkpointer
        conn = sqlite3.connect(db_path, check_same_thread=False)
        compile_kwargs["checkpointer"] = SqliteSaver(conn)
    elif use_memory_checkpointer:
        # In-memory checkpointer for development
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
        "nodes": ["understanding", "field_mapper", "query_builder", "execute", "insight", "replanner"],
        "middleware": middleware_names,
        "checkpointer": checkpointer_type,
        "config": config,
        "architecture": "semantic_parser_agent",  # New LLM combination architecture
    }


def create_sqlite_checkpointer(db_path: str = "data/workflow_checkpoints.db") -> SqliteSaver:
    """
    Create a SQLite checkpointer for session persistence.
    
    The SQLite checkpointer enables:
    - Session save: Automatically saves workflow state after each step
    - Session restore: Resume workflow from last checkpoint
    - Cross-restart persistence: State survives application restarts
    
    **Validates: Requirements 18.4, 18.5**
    
    Args:
        db_path: Path to SQLite database file
    
    Returns:
        Configured SqliteSaver instance
    
    Example:
        >>> checkpointer = create_sqlite_checkpointer("data/sessions.db")
        >>> workflow = create_workflow(
        ...     use_memory_checkpointer=False,
        ...     use_sqlite_checkpointer=False,  # We'll pass checkpointer directly
        ... )
        >>> # Or use the built-in parameter:
        >>> workflow = create_workflow(
        ...     use_sqlite_checkpointer=True,
        ...     sqlite_db_path="data/sessions.db"
        ... )
    """
    from pathlib import Path
    import sqlite3
    
    # Ensure directory exists
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    
    # Create SQLite connection with check_same_thread=False for async support
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
    # Note: This is a simplified implementation
    # Full implementation would use checkpointer.list() method
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
    将 middleware 注入到 config 中。
    
    用于在调用 workflow 时传递 middleware 给节点函数。
    
    Args:
        config: 原始 config（可以为 None）
        middleware: Middleware 列表
    
    Returns:
        包含 middleware 的新 config
    
    Example:
        workflow = create_workflow()
        config = inject_middleware_to_config(
            {"configurable": {"thread_id": "123"}},
            workflow.middleware
        )
        result = await workflow.ainvoke(state, config)
    """
    config = config or {}
    configurable = config.get('configurable', {})
    configurable['middleware'] = middleware
    config['configurable'] = configurable
    return config
