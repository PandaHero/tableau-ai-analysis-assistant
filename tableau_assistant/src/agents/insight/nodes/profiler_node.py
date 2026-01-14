# -*- coding: utf-8 -*-
"""
Profiler Node - InsightAgent Subgraph Phase 1

Implements profiler_node(state: InsightState) -> Dict for the InsightAgent Subgraph.

Responsibilities:
- Extract query_result data from state
- Call EnhancedDataProfiler to generate data profile
- Call SemanticChunker to create priority chunks based on profile
- Return enhanced_profile and chunks to state

Architecture:
- This is a LangGraph node function, not a class
- Uses EnhancedDataProfiler as single entry point (Task 3.3.1)
- Uses SemanticChunker.chunk_by_strategy() for intelligent chunking

Requirements:
- Task 3.4: Implement Profiler Node
- R8.1: Generate data profile
- R8.3: Semantic chunking based on profile
"""

import logging
import json
import re
from typing import Dict, Any, List, Optional

from tableau_assistant.src.agents.insight.state import InsightState
from tableau_assistant.src.agents.insight.components.profiler import EnhancedDataProfiler
from tableau_assistant.src.agents.insight.components.chunker import SemanticChunker
from tableau_assistant.src.agents.insight.models.profile import ChunkingStrategy

logger = logging.getLogger(__name__)


def profiler_node(state: InsightState) -> Dict[str, Any]:
    """
    Profiler node for InsightAgent Subgraph.
    
    Phase 1 of insight analysis:
    1. Extract data from query_result or files
    2. Generate enhanced data profile (Tableau Pulse style)
    3. Create priority chunks based on recommended strategy
    
    Args:
        state: InsightState containing query_result and optional files
        
    Returns:
        Dict with:
        - enhanced_profile: EnhancedDataProfile
        - chunks: List[PriorityChunk]
        - error_message: Optional error message
    """
    logger.info("Profiler node started")
    
    try:
        # 1. Extract data from state
        data = _extract_data(state)
        
        if data is None or (isinstance(data, list) and len(data) == 0):
            logger.warning("No data available for profiling")
            return {
                "enhanced_profile": None,
                "chunks": [],
                "error_message": "No data available for profiling",
            }
        
        # 2. Get dimension hierarchy from state (if available)
        dimension_hierarchy = state.get("dimension_hierarchy") or {}
        
        # 3. Create profiler and generate profile
        profiler = EnhancedDataProfiler(dimension_hierarchy=dimension_hierarchy)
        enhanced_profile = profiler.profile(data)
        
        logger.info(
            f"Profile generated: {enhanced_profile.row_count} rows, "
            f"strategy={enhanced_profile.recommended_strategy}"
        )
        
        # 4. Get insight profile for chunking strategy
        insight_profile = profiler.get_insight_profile(data)
        
        # 5. Create chunker and generate priority chunks
        chunker = SemanticChunker(dimension_hierarchy=dimension_hierarchy)
        
        # Map ChunkingStrategy enum to string for chunk_by_strategy
        strategy_map = {
            ChunkingStrategy.BY_ANOMALY: "by_anomaly",
            ChunkingStrategy.BY_CHANGE_POINT: "by_change_point",
            ChunkingStrategy.BY_PARETO: "by_pareto",
            ChunkingStrategy.BY_SEMANTIC: "by_semantic",
            ChunkingStrategy.BY_STATISTICS: "by_statistics",
            ChunkingStrategy.BY_POSITION: "by_position",
        }
        strategy_str = strategy_map.get(
            enhanced_profile.recommended_strategy, 
            "by_position"
        )
        
        # Get semantic groups from profile (DataInsightProfile doesn't have semantic_groups,
        # but EnhancedDataProfile does - use getattr for safety)
        semantic_groups = None
        if insight_profile:
            semantic_groups = getattr(insight_profile, 'semantic_groups', None)
        
        chunks = chunker.chunk_by_strategy(
            data=data,
            strategy=strategy_str,
            insight_profile=insight_profile,
            semantic_groups=semantic_groups,
        )
        
        logger.info(f"Chunking complete: {len(chunks)} chunks created")
        
        # ⚠️ State 序列化：将 Pydantic 对象转换为 dict 后存入 state
        return {
            "enhanced_profile": enhanced_profile.model_dump() if enhanced_profile else None,
            "insight_profile": insight_profile,  # Store for analyzer_node to use
            "chunks": [chunk.model_dump() for chunk in chunks] if chunks else [],
            "error_message": None,
        }
        
    except Exception as e:
        logger.error(f"Profiler node failed: {e}", exc_info=True)
        return {
            "enhanced_profile": None,
            "chunks": [],
            "error_message": f"Profiler failed: {str(e)}",
        }


def _extract_data(state: InsightState) -> Optional[List[Dict[str, Any]]]:
    """
    Extract data from state.
    
    Priority:
    1. Check for large data reference, read from SqliteStore
    2. Use query_result.data directly
    
    Args:
        state: InsightState
        
    Returns:
        List of row dictionaries, or None if no data
    """
    query_result = state.get("query_result")
    if query_result is None:
        logger.warning("No query_result in state")
        return None
    
    # 1. Check if query_result contains a file reference (large data in SqliteStore)
    file_path = _extract_file_path_from_result(query_result)
    if file_path:
        from tableau_assistant.src.infra.storage.langgraph_store import get_langgraph_store
        
        store = get_langgraph_store()
        config = state.get("config") or {}
        thread_id = config.get("configurable", {}).get("thread_id", "default") if isinstance(config, dict) else "default"
        
        item = store.get(namespace=("large_results", thread_id), key=file_path)
        if item is not None and hasattr(item, "value"):
            value = item.value
            if isinstance(value, dict) and "content" in value:
                content = value["content"]
                data = json.loads(content) if isinstance(content, str) else content
                logger.info(f"Extracted {len(data)} rows from SqliteStore: {file_path}")
                return data
    
    # 2. Use query_result.data directly
    if hasattr(query_result, "data"):
        data = query_result.data
    elif isinstance(query_result, dict):
        data = query_result.get("data", [])
    else:
        logger.warning(f"Unknown query_result type: {type(query_result)}")
        return None
    
    if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
        return data
    
    logger.warning("No valid data found in query_result")
    return None


def _extract_file_path_from_result(query_result: Any) -> Optional[str]:
    """
    Extract file path from query_result if it contains a large data reference.
    
    FilesystemMiddleware stores large results with message:
    "Tool result too large, saved at: /large_tool_results/{id}"
    """
    if hasattr(query_result, "data"):
        data = query_result.data
    elif isinstance(query_result, dict):
        data = query_result.get("data")
    else:
        return None
    
    if isinstance(data, str):
        match = re.search(r"saved at: (/large_tool_results/[^\s]+)", data)
        if match:
            return match.group(1)
    return None


__all__ = ["profiler_node"]
