# -*- coding: utf-8 -*-
"""
Insight Agent Node

LLM Agent that analyzes query results and generates insights.

Architecture:
- Uses InsightAgent Subgraph for progressive analysis
- Subgraph: profiler_node → director_node ↔ analyzer_node (loop)
- Director LLM handles insight accumulation and final summary generation

Requirements:
- R8.1: Progressive insight analysis
- R8.7: Streaming output support
"""

import logging
from typing import Dict, Optional, List, AsyncGenerator

from langgraph.types import RunnableConfig

from tableau_assistant.src.agents.insight.models import InsightResult, Insight
from tableau_assistant.src.orchestration.workflow.state import VizQLState

logger = logging.getLogger(__name__)


def _get_user_friendly_error_message(error: str) -> str:
    """Convert technical error message to user-friendly message."""
    error_lower = error.lower() if error else ""
    
    if "validation error" in error_lower or "additional property" in error_lower:
        return "抱歉，当前查询涉及的计算类型暂不支持。请尝试简化您的问题，或者直接询问具体的数据指标。"
    elif "timeout" in error_lower:
        return "查询超时，数据量可能较大。请尝试缩小查询范围或添加筛选条件。"
    elif "connection" in error_lower:
        return "连接数据源时出现问题，请稍后重试。"
    elif "authentication" in error_lower or "auth" in error_lower:
        return "数据源认证失败，请检查您的访问权限。"
    elif "not found" in error_lower:
        return "未找到相关数据，请检查您查询的字段或维度是否存在。"
    else:
        return "查询执行遇到问题，请尝试换一种方式提问。如果问题持续，请联系管理员。"


async def insight_node(state: VizQLState, config: RunnableConfig | None = None) -> Dict[str, object]:
    """
    Insight node entry point for LangGraph.
    
    Calls the InsightAgent Subgraph for progressive analysis.
    
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
    # ⚠️ State 序列化：query_result 是 dict（ExecuteResult.model_dump()），非 Pydantic 对象
    # 需要通过 dict 键访问，而非对象属性
    is_success = True
    error_msg = None
    
    if isinstance(query_result, dict):
        # dict 访问方式（正确）
        is_success = query_result.get("success", True)
        error_msg = query_result.get("error")
    elif hasattr(query_result, 'is_success'):
        # 兼容旧的对象访问方式（向后兼容）
        is_success = query_result.is_success() if callable(getattr(query_result, 'is_success', None)) else query_result.is_success
        error_msg = getattr(query_result, 'error', None)
    
    if not is_success:
        error_msg = error_msg or "未知错误"
        logger.warning(f"Query failed, skipping insight analysis: {error_msg}")
        
        user_friendly_msg = _get_user_friendly_error_message(error_msg)
        
        from langchain_core.messages import HumanMessage, AIMessage
        question = state.get("question", "")
        new_messages = [
            HumanMessage(content=question, additional_kwargs={"source": "insight_input"}),
            AIMessage(content=user_friendly_msg, additional_kwargs={"source": "insight"}),
        ]
        
        return {
            "insights": [],
            "insight_complete": True,
            "messages": new_messages,
        }

    
    # Build context
    context = {
        "question": state.get("question", ""),
        "dimensions": [],
        "measures": [],
    }
    
    # Extract dimensions and measures from semantic_query
    # ⚠️ State 序列化：semantic_query 是 dict（SemanticQuery.model_dump()），非 Pydantic 对象
    semantic_query = state.get("semantic_query")
    if semantic_query and isinstance(semantic_query, dict):
        # dict 访问方式（正确）
        dimensions_list = semantic_query.get("dimensions") or []
        measures_list = semantic_query.get("measures") or []
        context["dimensions"] = [
            {"name": d.get("field_name") if isinstance(d, dict) else getattr(d, 'field_name', None)} 
            for d in dimensions_list
        ]
        context["measures"] = [
            {"name": m.get("field_name") if isinstance(m, dict) else getattr(m, 'field_name', None)} 
            for m in measures_list
        ]
    elif semantic_query:
        # 兼容旧的对象访问方式（向后兼容）
        context["dimensions"] = [
            {"name": d.field_name} for d in (getattr(semantic_query, 'dimensions', None) or [])
        ]
        context["measures"] = [
            {"name": m.field_name} for m in (getattr(semantic_query, 'measures', None) or [])
        ]
    
    try:
        # Run InsightAgent Subgraph
        result = await _run_insight_subgraph(state, context, config)
        
        findings = result.findings if result.findings else []
        
        # Extract current dimensions
        current_dimensions = state.get("current_dimensions", [])
        if context.get("dimensions"):
            new_dims = [d.get("name") for d in context["dimensions"] if d.get("name")]
            current_dimensions = list(set(current_dimensions + new_dims))
        
        # Extract data_insight_profile
        data_insight_profile = None
        if result.data_insight_profile:
            data_insight_profile = result.data_insight_profile.model_dump()
        
        logger.info(f"Insight node completed: {len(findings)} insights")
        
        # Generate structured summary message for conversation history
        from langchain_core.messages import HumanMessage, AIMessage
        
        question = state.get("question", "")
        summary_parts = ["【分析完成】", f"原始问题：{question}"]
        
        dim_names = [d.get("name") for d in context.get("dimensions", []) if d.get("name")]
        summary_parts.append(f"分析维度：{', '.join(dim_names) if dim_names else '无'}")
        
        measure_names = [m.get("name") for m in context.get("measures", []) if m.get("name")]
        summary_parts.append(f"分析指标：{', '.join(measure_names) if measure_names else '无'}")
        
        if result.summary:
            summary_parts.append(f"\n回答：{result.summary}")
        elif findings:
            first_finding = findings[0]
            summary_parts.append(f"\n回答：{first_finding.title} - {first_finding.description or ''}")
        
        summary_content = "\n".join(summary_parts)
        
        new_messages = [
            HumanMessage(content=question, additional_kwargs={"source": "insight_input"}),
            AIMessage(content=summary_content, additional_kwargs={"source": "insight"}),
        ]
        
        # ⚠️ State 序列化：insights / all_insights 存储为 dict 列表（.model_dump()），非 Pydantic 对象
        # ⚠️ reducer 语义：VizQLState.insights/all_insights 使用 operator.add
        # 因此这里必须返回“本轮新增”的洞察列表，而不是全量列表（否则会被重复累加）。
        serialized_findings = [
            ins.model_dump() if hasattr(ins, "model_dump") else ins
            for ins in findings
        ]

        return {
            "insights": serialized_findings,
            "all_insights": serialized_findings,
            "data_insight_profile": data_insight_profile,
            "current_dimensions": current_dimensions,
            "insight_complete": True,
            "messages": new_messages,
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



async def _run_insight_subgraph(
    state: VizQLState,
    context: Dict[str, object],
    config: RunnableConfig | None = None,
) -> InsightResult:
    """
    Run InsightAgent Subgraph for progressive analysis.
    
    Args:
        state: VizQLState containing query_result
        context: Analysis context (question, dimensions, measures)
        config: LangGraph RunnableConfig
        
    Returns:
        InsightResult with findings
    """
    from tableau_assistant.src.agents.insight.subgraph import create_insight_subgraph
    from tableau_assistant.src.agents.insight.models import DataInsightProfile
    
    # Create and compile subgraph
    subgraph = create_insight_subgraph()
    compiled = subgraph.compile()
    
    # Prepare input state for subgraph
    input_state = dict(state)
    input_state["context"] = context
    
    # Run subgraph
    result_state = await compiled.ainvoke(input_state, config)
    
    # Extract results from subgraph output
    # ⚠️ State 序列化：insights 是 dict 列表
    accumulated_insights = result_state.get("insights") or []
    final_summary = result_state.get("final_summary") or ""
    # ⚠️ State 序列化：enhanced_profile 是 dict
    enhanced_profile_dict = result_state.get("enhanced_profile")
    
    # Convert accumulated insights to Insight objects if needed
    findings = []
    for ins in accumulated_insights:
        if isinstance(ins, Insight):
            findings.append(ins)
        elif isinstance(ins, dict):
            findings.append(Insight.model_validate(ins))
    
    # ⚠️ State 序列化：chunks 是 dict 列表
    chunks_dicts = result_state.get("chunks") or []
    analyzed_chunk_ids = result_state.get("analyzed_chunk_ids") or []
    
    # Calculate total_rows_analyzed from dict chunks
    total_rows_analyzed = 0
    for c in chunks_dicts:
        if c and c.get("chunk_id") in analyzed_chunk_ids:
            total_rows_analyzed += c.get("row_count", 0)
    
    # Build InsightResult
    result = InsightResult(
        summary=final_summary if final_summary else (findings[0].title if findings else "分析完成"),
        findings=findings,
        confidence=0.8 if findings else 0.5,
        strategy_used="progressive",
        chunks_analyzed=len(analyzed_chunk_ids),
        total_rows_analyzed=total_rows_analyzed,
    )
    
    # Add data_insight_profile if available
    # ⚠️ State 序列化：enhanced_profile 是 dict，需要访问 dict 键
    if enhanced_profile_dict:
        result.data_insight_profile = DataInsightProfile(
            distribution_type="unknown",
            pareto_ratio=0.0,
            statistics=enhanced_profile_dict.get("statistics"),
        )
    
    return result


__all__ = ["insight_node"]
