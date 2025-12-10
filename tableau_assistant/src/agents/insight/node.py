"""
Insight Agent Node

LLM Agent that analyzes query results and generates insights.

Architecture:
- Receives QueryResult from Execute Node
- Calls AnalysisCoordinator for progressive analysis
- Returns accumulated insights

Requirements:
- R8.1: Progressive insight analysis
- R8.7: Streaming output support
"""

import logging
from typing import Dict, Any, Optional, List, AsyncGenerator

from langgraph.types import RunnableConfig

from tableau_assistant.src.components.insight import (
    AnalysisCoordinator,
    InsightResult,
)

logger = logging.getLogger(__name__)


class InsightAgent:
    """
    Insight Agent - analyzes query results and generates insights.
    
    Uses AnalysisCoordinator for progressive analysis with:
    - Data profiling
    - Anomaly detection
    - Semantic chunking
    - LLM-based analysis
    - Insight accumulation and synthesis
    """
    
    def __init__(
        self,
        coordinator: Optional[AnalysisCoordinator] = None,
        dimension_hierarchy: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize Insight Agent.
        
        Args:
            coordinator: AnalysisCoordinator instance (created if not provided)
            dimension_hierarchy: Dimension hierarchy from metadata.dimension_hierarchy
        """
        self._dimension_hierarchy = dimension_hierarchy or {}
        self.coordinator = coordinator or AnalysisCoordinator(
            dimension_hierarchy=self._dimension_hierarchy
        )
    
    def set_dimension_hierarchy(self, hierarchy: Dict[str, Any]):
        """Set dimension hierarchy for analysis."""
        self._dimension_hierarchy = hierarchy or {}
        self.coordinator.set_dimension_hierarchy(self._dimension_hierarchy)
    
    async def analyze(
        self,
        query_result: Any,
        context: Dict[str, Any]
    ) -> InsightResult:
        """
        Analyze query result and generate insights.
        
        Args:
            query_result: QueryResult from Execute Node
            context: Analysis context (question, dimensions, measures)
            
        Returns:
            InsightResult with findings
        """
        # Extract data from QueryResult
        if hasattr(query_result, 'data'):
            data = query_result.data
        elif isinstance(query_result, dict):
            data = query_result.get('data', [])
        elif isinstance(query_result, list):
            data = query_result
        else:
            logger.warning(f"Unknown query_result type: {type(query_result)}")
            return InsightResult(summary="无法解析查询结果")
        
        if not data:
            return InsightResult(summary="查询结果为空，无数据可分析")
        
        logger.info(f"Starting insight analysis: {len(data)} rows")
        
        # Run analysis
        result = await self.coordinator.analyze(data, context)
        
        logger.info(f"Insight analysis complete: {len(result.findings)} insights")
        
        return result
    
    async def analyze_streaming(
        self,
        query_result: Any,
        context: Dict[str, Any]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Analyze with streaming progress updates.
        
        Args:
            query_result: QueryResult from Execute Node
            context: Analysis context
            
        Yields:
            Progress events
        """
        # Extract data
        if hasattr(query_result, 'data'):
            data = query_result.data
        elif isinstance(query_result, dict):
            data = query_result.get('data', [])
        elif isinstance(query_result, list):
            data = query_result
        else:
            yield {"event": "error", "message": "无法解析查询结果"}
            return
        
        if not data:
            yield {"event": "complete", "result": InsightResult(summary="查询结果为空")}
            return
        
        # Stream analysis
        async for event in self.coordinator.analyze_streaming(data, context):
            yield event


async def insight_node(state: Dict[str, Any], config: RunnableConfig | None = None) -> Dict[str, Any]:
    """
    Insight node entry point for LangGraph.
    
    Args:
        state: VizQLState containing query_result
        config: Optional configuration
        
    Returns:
        Updated state with insights
    """
    logger.info("Insight node started")
    
    query_result = state.get("query_result")
    
    if not query_result:
        logger.warning("No query_result in state")
        return {
            "errors": state.get("errors", []) + [{
                "node": "insight",
                "error": "No query_result provided",
                "type": "missing_input",
            }],
            "insight_complete": True,
        }
    
    # Check if query was successful
    if hasattr(query_result, 'is_success') and not query_result.is_success():
        logger.warning(f"Query failed, skipping insight analysis: {query_result.error}")
        return {
            "insights": [],
            "insight_result": InsightResult(
                summary=f"查询失败，无法进行洞察分析: {query_result.error}"
            ),
            "insight_complete": True,
        }
    
    # Build context
    context = {
        "question": state.get("question", ""),
        "dimensions": [],
        "measures": [],
    }
    
    # Extract dimensions and measures from semantic_query
    semantic_query = state.get("semantic_query")
    if semantic_query:
        if hasattr(semantic_query, 'dimensions'):
            context["dimensions"] = [
                {"name": d.name} if hasattr(d, 'name') else d
                for d in semantic_query.dimensions
            ]
        elif isinstance(semantic_query, dict):
            context["dimensions"] = semantic_query.get("dimensions", [])
        
        if hasattr(semantic_query, 'measures'):
            context["measures"] = [
                {"name": m.name} if hasattr(m, 'name') else m
                for m in semantic_query.measures
            ]
        elif isinstance(semantic_query, dict):
            context["measures"] = semantic_query.get("measures", [])
    
    try:
        # Get dimension_hierarchy from state (from metadata)
        dimension_hierarchy = state.get("dimension_hierarchy", {})
        
        # Run analysis with dimension_hierarchy
        agent = InsightAgent(dimension_hierarchy=dimension_hierarchy)
        result = await agent.analyze(query_result, context)
        
        # Extract findings for state (Pydantic models use model_dump())
        findings = [f.model_dump() for f in result.findings] if result.findings else []
        
        logger.info(f"Insight node completed: {len(findings)} insights")
        
        return {
            "insights": findings,
            "insight_result": result,
            "all_insights": state.get("all_insights", []) + findings,
            "insight_complete": True,
        }
    
    except Exception as e:
        logger.exception(f"Insight node failed: {e}")
        return {
            "errors": state.get("errors", []) + [{
                "node": "insight",
                "error": str(e),
                "type": "analysis_error",
            }],
            "insight_complete": True,
        }


async def insight_node_streaming(
    state: Dict[str, Any],
    config: RunnableConfig | None = None
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Streaming version of insight node.
    
    Yields progress events during analysis.
    """
    logger.info("Insight node (streaming) started")
    
    query_result = state.get("query_result")
    
    if not query_result:
        yield {
            "event": "error",
            "error": "No query_result provided",
        }
        return
    
    # Build context
    context = {
        "question": state.get("question", ""),
        "dimensions": [],
        "measures": [],
    }
    
    semantic_query = state.get("semantic_query")
    if semantic_query:
        if isinstance(semantic_query, dict):
            context["dimensions"] = semantic_query.get("dimensions", [])
            context["measures"] = semantic_query.get("measures", [])
    
    try:
        agent = InsightAgent()
        
        async for event in agent.analyze_streaming(query_result, context):
            yield event
            
            # If complete, also yield state update
            if event.get("event") == "complete":
                result = event.get("result")
                if result:
                    findings = [f.model_dump() for f in result.findings] if result.findings else []
                    yield {
                        "event": "state_update",
                        "state": {
                            "insights": findings,
                            "insight_result": result,
                            "all_insights": state.get("all_insights", []) + findings,
                            "insight_complete": True,
                        }
                    }
    
    except Exception as e:
        logger.exception(f"Insight node (streaming) failed: {e}")
        yield {
            "event": "error",
            "error": str(e),
        }
