"""DeepAgent Factory - Creates DeepAgent instances for Tableau Assistant."""
import os
import logging
from typing import List, Dict, Any, Optional

from langchain_core.tools import BaseTool
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.base import BaseStore

from tableau_assistant.src.config.settings import settings

logger = logging.getLogger(__name__)

DEEPAGENTS_AVAILABLE = False

try:
    from deepagents import create_deep_agent
    DEEPAGENTS_AVAILABLE = True
except ImportError:
    logger.warning("DeepAgents framework not available.")
    create_deep_agent = None

CLAUDE_MODEL_PREFIXES = ("claude-", "claude3", "anthropic")


def _is_claude_model(model_name: str) -> bool:
    """Check if model is a Claude model."""
    if not model_name:
        return False
    model_lower = model_name.lower()
    return any(model_lower.startswith(prefix) for prefix in CLAUDE_MODEL_PREFIXES)


def _get_model(provider: str, model_name: str, temperature: float = 0.0):
    """Get LLM model instance."""
    from tableau_assistant.src.model_manager import select_model
    return select_model(provider=provider, model_name=model_name, temperature=temperature)


def _get_middleware_config() -> Dict[str, Any]:
    """Get middleware configuration from environment variables."""
    return {
        "summarization_threshold": int(os.getenv("DEEPAGENT_SUMMARIZATION_THRESHOLD", "10")),
        "filesystem_size_threshold": int(os.getenv("DEEPAGENT_FILESYSTEM_SIZE_THRESHOLD", str(10 * 1024 * 1024))),
        "filesystem_base_path": os.getenv("DEEPAGENT_FILESYSTEM_BASE_PATH", "data/agent_files"),
        "todo_max_tasks": int(os.getenv("DEEPAGENT_TODO_MAX_TASKS", "10")),
        "hitl_timeout": int(os.getenv("DEEPAGENT_HITL_TIMEOUT", "300")),
        "patch_max_retries": int(os.getenv("DEEPAGENT_PATCH_MAX_RETRIES", "3")),
    }



def create_tableau_deep_agent(
    tools: List[BaseTool],
    model_name: Optional[str] = None,
    store: Optional[BaseStore] = None,
    system_prompt: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None
) -> CompiledStateGraph:
    """Create Tableau Assistant DeepAgent."""
    if not DEEPAGENTS_AVAILABLE:
        raise ImportError("DeepAgents framework is required. Install with: pip install deepagents")
    
    config = config or {}
    provider = config.get("provider") or os.getenv("MODEL_PROVIDER", "local")
    
    if model_name is None:
        model_name = os.getenv("MODEL_NAME") or settings.tooling_llm_model
        if not model_name:
            raise ValueError("model_name is required.")
    
    temperature = config.get("temperature", 0.0)
    model = _get_model(provider=provider, model_name=model_name, temperature=temperature)
    
    logger.info(f"Creating DeepAgent with model: {provider}/{model_name}")
    
    if _is_claude_model(model_name):
        logger.info("Claude model detected - Prompt caching will be enabled")
    
    agent = create_deep_agent(
        model=model,
        tools=tools,
        subagents=[],
        store=store,
        system_prompt=system_prompt,
        checkpointer=True,
        debug=settings.debug
    )
    
    logger.info(f"DeepAgent created successfully with {len(tools)} tools")
    return agent



def get_default_system_prompt() -> str:
    """Get default system prompt."""
    return """You are a Tableau data analysis assistant. Your role is to help users 
analyze data from Tableau datasources by:
1. Understanding user questions about their data
2. Building appropriate VizQL queries
3. Executing queries and processing results
4. Providing insights and recommendations
"""


def get_middleware_info(agent: CompiledStateGraph) -> Dict[str, Any]:
    """Get Agent middleware info for testing."""
    info = {
        "middleware_count": 0,
        "middleware_types": [],
        "has_caching": False,
        "has_summarization": False,
        "has_filesystem": False,
        "has_patch": False,
        "has_todo": False,
        "has_hitl": False,
        "has_subagent": False
    }
    
    if hasattr(agent, 'middleware'):
        middlewares = getattr(agent, 'middleware', [])
        info["middleware_count"] = len(middlewares)
        for mw in middlewares:
            mw_type = type(mw).__name__
            info["middleware_types"].append(mw_type)
            if "Caching" in mw_type:
                info["has_caching"] = True
            elif "Summarization" in mw_type:
                info["has_summarization"] = True
            elif "Filesystem" in mw_type:
                info["has_filesystem"] = True
            elif "Patch" in mw_type:
                info["has_patch"] = True
            elif "Todo" in mw_type:
                info["has_todo"] = True
            elif "HumanInTheLoop" in mw_type or "HITL" in mw_type:
                info["has_hitl"] = True
            elif "SubAgent" in mw_type:
                info["has_subagent"] = True
    return info


def create_agent_with_store(
    tools: List[BaseTool],
    db_path: str = "data/agent_store.db",
    model_name: Optional[str] = None,
    system_prompt: Optional[str] = None
) -> CompiledStateGraph:
    """Create DeepAgent with persistent store."""
    from tableau_assistant.src.capabilities.storage.persistent_store import PersistentStore
    store = PersistentStore(db_path)
    return create_tableau_deep_agent(
        tools=tools,
        model_name=model_name,
        store=store,
        system_prompt=system_prompt or get_default_system_prompt()
    )
