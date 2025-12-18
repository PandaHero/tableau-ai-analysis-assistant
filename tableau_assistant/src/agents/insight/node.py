# -*- coding: utf-8 -*-
"""
Insight Agent Node

LLM Agent that analyzes query results and generates insights.

Architecture:
- Receives ExecuteResult from Execute Node
- Calls AnalysisCoordinator for progressive analysis
- Returns accumulated insights

Requirements:
- R8.1: Progressive insight analysis
- R8.7: Streaming output support
"""

import logging
from typing import Dict, Optional, List, AsyncGenerator

from langgraph.types import RunnableConfig

# 直接从具体模块导入，避免循环依赖
# components/__init__.py 导入 analyzer.py
# analyzer.py 导入 agents/insight/prompt.py
# 如果这里从 components 包导入，会触发循环
from tableau_assistant.src.agents.insight.components.coordinator import AnalysisCoordinator
from tableau_assistant.src.core.models import InsightResult
from tableau_assistant.src.platforms.tableau.models import ExecuteResult
from tableau_assistant.src.orchestration.workflow.state import VizQLState

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
        dimension_hierarchy: Optional[Dict[str, List[str]]] = None
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
    
    def set_dimension_hierarchy(self, hierarchy: Dict[str, List[str]]) -> None:
        """Set dimension hierarchy for analysis."""
        self._dimension_hierarchy = hierarchy or {}
        self.coordinator.set_dimension_hierarchy(self._dimension_hierarchy)
    
    async def analyze(
        self,
        query_result: ExecuteResult,
        context: Dict[str, object]
    ) -> InsightResult:
        """
        Analyze query result and generate insights.
        
        Args:
            query_result: ExecuteResult from Execute Node
            context: Analysis context (question, dimensions, measures)
            
        Returns:
            InsightResult with findings
        """
        # Extract data from ExecuteResult
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
        query_result: ExecuteResult,
        context: Dict[str, object]
    ) -> AsyncGenerator[Dict[str, object], None]:
        """
        Analyze with streaming progress updates.
        
        Args:
            query_result: ExecuteResult from Execute Node
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


async def insight_node(state: VizQLState, config: RunnableConfig | None = None) -> Dict[str, object]:
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
    
    # Extract dimensions and measures from semantic_query (SemanticQuery Pydantic object)
    semantic_query = state.get("semantic_query")
    if semantic_query:
        # semantic_query 是 SemanticQuery Pydantic 对象，直接访问属性
        context["dimensions"] = [
            {"name": d.name} for d in (semantic_query.dimensions or [])
        ]
        context["measures"] = [
            {"name": m.name} for m in (semantic_query.measures or [])
        ]
    
    try:
        # Get dimension_hierarchy from state (from metadata)
        dimension_hierarchy = state.get("dimension_hierarchy", {})
        
        # Run analysis with dimension_hierarchy
        agent = InsightAgent(dimension_hierarchy=dimension_hierarchy)
        result = await agent.analyze(query_result, context)
        
        # findings 保持为 Pydantic 对象列表
        findings = result.findings if result.findings else []
        
        # 提取当前分析的维度列表
        current_dimensions = state.get("current_dimensions", [])
        if context.get("dimensions"):
            new_dims = [d.get("name") for d in context["dimensions"] if d.get("name")]
            # 合并去重
            current_dimensions = list(set(current_dimensions + new_dims))
        
        # 提取 data_insight_profile（用于 Replanner）
        # DataInsightProfile 是 Pydantic 模型，转换为字典以便在 State 中传递
        # Replanner._format_data_insight_profile() 使用 .get() 方法访问字段
        data_insight_profile = None
        if result.data_insight_profile:
            data_insight_profile = result.data_insight_profile.model_dump()
        
        logger.info(f"Insight node completed: {len(findings)} insights, {len(current_dimensions)} dimensions analyzed")
        
        # Generate structured summary message for conversation history
        # This enables LLM to see previous Q&A context and SummarizationMiddleware to work
        from langchain_core.messages import HumanMessage, AIMessage
        
        question = state.get("question", "")
        
        # Build structured summary
        summary_parts = [
            "【分析完成】",
            f"原始问题：{question}",
        ]
        
        # Add dimensions
        dim_names = [d.get("name") for d in context.get("dimensions", []) if d.get("name")]
        if dim_names:
            summary_parts.append(f"分析维度：{', '.join(dim_names)}")
        else:
            summary_parts.append("分析维度：无")
        
        # Add measures
        measure_names = [m.get("name") for m in context.get("measures", []) if m.get("name")]
        if measure_names:
            summary_parts.append(f"分析指标：{', '.join(measure_names)}")
        else:
            summary_parts.append("分析指标：无")
        
        # Add query result summary (first few rows)
        if query_result and hasattr(query_result, 'data') and query_result.data:
            data = query_result.data
            row_count = len(data)
            if row_count <= 3:
                summary_parts.append(f"查询结果摘要：共 {row_count} 行数据")
            else:
                summary_parts.append(f"查询结果摘要：共 {row_count} 行数据（显示前3行）")
            # Show first 3 rows as summary
            for i, row in enumerate(data[:3]):
                row_str = ", ".join(f"{k}={v}" for k, v in row.items())
                summary_parts.append(f"  - {row_str}")
        
        # Add insight summary
        if result.summary:
            summary_parts.append(f"\n回答：{result.summary}")
        elif findings:
            # Use first finding as summary
            first_finding = findings[0]
            summary_parts.append(f"\n回答：{first_finding.title} - {first_finding.description or ''}")
        
        summary_content = "\n".join(summary_parts)
        
        # Create messages for conversation history
        # Add source marking via additional_kwargs for message tracking
        new_messages = [
            HumanMessage(
                content=question,
                additional_kwargs={"source": "insight_input"}
            ),
            AIMessage(
                content=summary_content,
                additional_kwargs={"source": "insight"}
            ),
        ]
        
        return {
            "insights": findings,
            "insight_result": result,
            "all_insights": state.get("all_insights", []) + findings,
            "data_insight_profile": data_insight_profile,
            "current_dimensions": current_dimensions,
            "insight_complete": True,
            # Add to conversation history
            "messages": new_messages,
            # Record answered question for Replanner deduplication
            # Note: trim_answered_questions is applied at Replanner to limit list length
            "answered_questions": [question],
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
    state: VizQLState,
    config: RunnableConfig | None = None
) -> AsyncGenerator[Dict[str, object], None]:
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
    
    # semantic_query 是 SemanticQuery Pydantic 对象
    semantic_query = state.get("semantic_query")
    if semantic_query:
        context["dimensions"] = [{"name": d.name} for d in (semantic_query.dimensions or [])]
        context["measures"] = [{"name": m.name} for m in (semantic_query.measures or [])]
    
    try:
        # Get dimension_hierarchy from state
        dimension_hierarchy = state.get("dimension_hierarchy", {})
        agent = InsightAgent(dimension_hierarchy=dimension_hierarchy)
        
        async for event in agent.analyze_streaming(query_result, context):
            yield event
            
            # If complete, also yield state update
            if event.get("event") == "complete":
                result = event.get("result")
                if result:
                    # findings 保持为 Pydantic 对象列表
                    findings = result.findings if result.findings else []
                    
                    # 提取当前分析的维度列表
                    current_dimensions = state.get("current_dimensions", [])
                    if context.get("dimensions"):
                        new_dims = [d.get("name") for d in context["dimensions"] if d.get("name")]
                        current_dimensions = list(set(current_dimensions + new_dims))
                    
                    # 提取 data_insight_profile（Pydantic -> dict）
                    data_insight_profile = None
                    if result.data_insight_profile:
                        data_insight_profile = result.data_insight_profile.model_dump()
                    
                    # Generate structured summary message for conversation history
                    from langchain_core.messages import HumanMessage, AIMessage
                    
                    question = state.get("question", "")
                    
                    # Build structured summary
                    summary_parts = [
                        "【分析完成】",
                        f"原始问题：{question}",
                    ]
                    
                    dim_names = [d.get("name") for d in context.get("dimensions", []) if d.get("name")]
                    summary_parts.append(f"分析维度：{', '.join(dim_names) if dim_names else '无'}")
                    
                    measure_names = [m.get("name") for m in context.get("measures", []) if m.get("name")]
                    summary_parts.append(f"分析指标：{', '.join(measure_names) if measure_names else '无'}")
                    
                    if result.summary:
                        summary_parts.append(f"\n回答：{result.summary}")
                    
                    summary_content = "\n".join(summary_parts)
                    
                    new_messages = [
                        HumanMessage(
                            content=question,
                            additional_kwargs={"source": "insight_input"}
                        ),
                        AIMessage(
                            content=summary_content,
                            additional_kwargs={"source": "insight"}
                        ),
                    ]
                    
                    yield {
                        "event": "state_update",
                        "state": {
                            "insights": findings,
                            "insight_result": result,
                            "all_insights": state.get("all_insights", []) + findings,
                            "data_insight_profile": data_insight_profile,
                            "current_dimensions": current_dimensions,
                            "insight_complete": True,
                            "messages": new_messages,
                            "answered_questions": [question],
                        }
                    }
    
    except Exception as e:
        logger.exception(f"Insight node (streaming) failed: {e}")
        yield {
            "event": "error",
            "error": str(e),
        }
