# -*- coding: utf-8 -*-
"""
Analyzer Node - InsightAgent Subgraph Phase 3

Implements analyzer_node(state: InsightState) -> Dict for the InsightAgent Subgraph.

Responsibilities:
- Execute analysis based on director's decision (action + target)
- Support multiple analysis types: analyze_chunk, analyze_dimension, analyze_anomaly
- Call ChunkAnalyzer with historical insight processing
- Update state with analyst output

Architecture:
- This is a LangGraph node function, not a class
- Uses ChunkAnalyzer component for LLM-based analysis
- Supports precision targeting (dimension values, anomaly indices)

Requirements:
- Task 3.11: Implement Analyzer Node
- R8.3: Chunk analysis with historical insight processing
"""

import logging
import json
from typing import Dict, Any, Optional, List

import pandas as pd

from tableau_assistant.src.agents.insight.state import InsightState
from tableau_assistant.src.agents.insight.components.analyzer import ChunkAnalyzer
from tableau_assistant.src.agents.insight.components.accumulator import InsightAccumulator
from tableau_assistant.src.agents.insight.models import (
    Insight,
    PriorityChunk,
    DataInsightProfile,
    EnhancedDataProfile,
)
from tableau_assistant.src.agents.insight.models.director import DirectorAction

logger = logging.getLogger(__name__)


async def analyzer_node(state: InsightState, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Analyzer node for InsightAgent Subgraph.
    
    Phase 3 of insight analysis:
    1. Read director's decision (action + target) from state
    2. Execute appropriate analysis based on action type
    3. Call ChunkAnalyzer with historical insight processing
    4. Update state with analyst output
    
    Args:
        state: InsightState containing director_decision, chunks, insights
        config: LangGraph RunnableConfig (for middleware)
        
    Returns:
        Dict with:
        - analyst_output: Dict containing new_insights, historical_actions, etc.
        - analyzed_chunk_ids: Updated list of analyzed chunk IDs
        - data_coverage: Updated data coverage ratio
        - error_message: Optional[str]
    """
    logger.info("Analyzer node started")
    
    try:
        # 1. Extract required data from state
        # ⚠️ State 序列化：current_action 现在是字符串值，需要转换为枚举
        current_action_str = state.get("current_action")
        current_action = None
        if current_action_str:
            try:
                current_action = DirectorAction(current_action_str)
            except ValueError:
                logger.warning(f"Unknown action type: {current_action_str}")
        
        current_target = state.get("current_target") or {}
        
        # ⚠️ State 序列化：chunks 是 dict 列表，需要转换为 PriorityChunk 对象
        chunks_dicts = state.get("chunks") or []
        chunks = [PriorityChunk.model_validate(c) for c in chunks_dicts if c]
        
        # ⚠️ State 序列化：enhanced_profile 是 dict，需要转换为 EnhancedDataProfile 对象
        enhanced_profile_dict = state.get("enhanced_profile")
        enhanced_profile = None
        if enhanced_profile_dict:
            enhanced_profile = EnhancedDataProfile.model_validate(enhanced_profile_dict)
        
        analyzed_chunk_ids = list(state.get("analyzed_chunk_ids") or [])
        
        # ⚠️ State 序列化：insights 是 dict 列表，需要转换为 Insight 对象
        insights_dicts = state.get("insights") or []
        accumulated_insights = [Insight.model_validate(i) for i in insights_dicts if i]
        
        # Get context for analysis
        context = state.get("context") or {}
        user_question = context.get("question", "")
        if not user_question:
            user_question = state.get("restated_question") or ""
        
        # 2. Validate required data
        if current_action is None:
            logger.error("No current_action in state")
            return _create_error_response("No action specified by director")
        
        if not chunks:
            logger.warning("No chunks available for analysis")
            return _create_error_response("No data chunks available")
        
        # 3. Get or create insight profile for analyzer
        insight_profile = _get_insight_profile(enhanced_profile, state)
        if insight_profile is None:
            logger.error("Cannot create insight profile")
            return _create_error_response("Cannot create insight profile")
        
        # 4. Execute analysis based on action type
        analyzer = ChunkAnalyzer()
        
        # Calculate current data coverage
        total_rows = sum(c.row_count for c in chunks)
        analyzed_rows = sum(c.row_count for c in chunks if c.chunk_id in analyzed_chunk_ids)
        current_coverage = analyzed_rows / total_rows if total_rows > 0 else 0.0
        
        if current_action == DirectorAction.ANALYZE_CHUNK:
            result = await _analyze_chunk(
                analyzer=analyzer,
                target=current_target,
                chunks=chunks,
                context={"question": user_question},
                insight_profile=insight_profile,
                historical_insights=accumulated_insights,
                current_coverage=current_coverage,
                analyzed_chunk_ids=analyzed_chunk_ids,
                state=state,
                config=config,
            )
        elif current_action == DirectorAction.ANALYZE_DIMENSION:
            result = await _analyze_dimension(
                analyzer=analyzer,
                target=current_target,
                chunks=chunks,
                enhanced_profile=enhanced_profile,
                context={"question": user_question},
                insight_profile=insight_profile,
                historical_insights=accumulated_insights,
                current_coverage=current_coverage,
                analyzed_chunk_ids=analyzed_chunk_ids,
                state=state,
                config=config,
            )
        elif current_action == DirectorAction.ANALYZE_ANOMALY:
            result = await _analyze_anomaly(
                analyzer=analyzer,
                target=current_target,
                chunks=chunks,
                enhanced_profile=enhanced_profile,
                context={"question": user_question},
                insight_profile=insight_profile,
                historical_insights=accumulated_insights,
                current_coverage=current_coverage,
                analyzed_chunk_ids=analyzed_chunk_ids,
                state=state,
                config=config,
            )
        else:
            logger.warning(f"Unknown action type: {current_action}")
            return _create_error_response(f"Unknown action type: {current_action}")
        
        return result
        
    except Exception as e:
        logger.error(f"Analyzer node failed: {e}", exc_info=True)
        return _create_error_response(f"Analyzer failed: {str(e)}")


async def _analyze_chunk(
    analyzer: ChunkAnalyzer,
    target: Dict[str, Any],
    chunks: List[PriorityChunk],
    context: Dict[str, Any],
    insight_profile: DataInsightProfile,
    historical_insights: List[Insight],
    current_coverage: float,
    analyzed_chunk_ids: List[int],
    state: Dict[str, Any],
    config: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Analyze a specific data chunk."""
    chunk_id = target.get("chunk_id")
    
    if chunk_id is None:
        return _create_error_response("No chunk_id specified for analyze_chunk")
    
    # Find the target chunk
    target_chunk = None
    for chunk in chunks:
        if chunk.chunk_id == chunk_id:
            target_chunk = chunk
            break
    
    if target_chunk is None:
        return _create_error_response(f"Chunk {chunk_id} not found")
    
    logger.info(f"Analyzing chunk {chunk_id}: {target_chunk.chunk_type}")
    
    # Call analyzer with history
    analyst_output = await analyzer.analyze_chunk_with_history(
        chunk=target_chunk,
        context=context,
        insight_profile=insight_profile,
        historical_insights=historical_insights,
        current_coverage=current_coverage,
        state=state,
        config=config,
    )
    
    # Update analyzed chunk IDs
    if chunk_id not in analyzed_chunk_ids:
        analyzed_chunk_ids.append(chunk_id)
    
    # Calculate new coverage
    total_rows = sum(c.row_count for c in chunks)
    analyzed_rows = sum(c.row_count for c in chunks if c.chunk_id in analyzed_chunk_ids)
    new_coverage = analyzed_rows / total_rows if total_rows > 0 else 0.0
    
    return {
        "analyst_output": {
            "new_insights": [ins.model_dump() for ins in analyst_output.new_insights],
            "historical_actions": [
                {
                    "historical_index": a.historical_index,
                    "action": a.action.value,
                    "reason": a.reason,
                    "merged_insight": a.merged_insight.model_dump() if a.merged_insight else None,
                    "replacement_insight": a.replacement_insight.model_dump() if a.replacement_insight else None,
                }
                for a in analyst_output.historical_actions
            ],
            "analysis_summary": analyst_output.analysis_summary,
            "data_coverage": analyst_output.data_coverage,
            "confidence": analyst_output.confidence,
            "needs_further_analysis": analyst_output.needs_further_analysis,
            "suggested_next_focus": analyst_output.suggested_next_focus,
        },
        "analyzed_chunk_ids": analyzed_chunk_ids,
        "data_coverage": new_coverage,
        "error_message": None,
    }


async def _analyze_dimension(
    analyzer: ChunkAnalyzer,
    target: Dict[str, Any],
    chunks: List[PriorityChunk],
    enhanced_profile: EnhancedDataProfile,
    context: Dict[str, Any],
    insight_profile: DataInsightProfile,
    historical_insights: List[Insight],
    current_coverage: float,
    analyzed_chunk_ids: List[int],
    state: Dict[str, Any],
    config: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Analyze data for a specific dimension value."""
    dimension = target.get("dimension")
    dimension_value = target.get("dimension_value")
    
    if not dimension:
        return _create_error_response("No dimension specified for analyze_dimension")
    
    logger.info(f"Analyzing dimension {dimension}={dimension_value}")
    
    # Find dimension index to get row indices
    row_indices = None
    if enhanced_profile and enhanced_profile.dimension_indices:
        for di in enhanced_profile.dimension_indices:
            if di.dimension == dimension:
                if dimension_value and dimension_value in di.row_indices:
                    row_indices = di.row_indices[dimension_value]
                break
    
    # Create a virtual chunk from dimension data
    virtual_chunk = _create_dimension_chunk(
        dimension=dimension,
        dimension_value=dimension_value,
        row_indices=row_indices,
        chunks=chunks,
    )
    
    if virtual_chunk is None:
        return _create_error_response(f"Cannot create chunk for dimension {dimension}={dimension_value}")
    
    # Call analyzer with history
    analyst_output = await analyzer.analyze_chunk_with_history(
        chunk=virtual_chunk,
        context=context,
        insight_profile=insight_profile,
        historical_insights=historical_insights,
        current_coverage=current_coverage,
        state=state,
        config=config,
    )
    
    return {
        "analyst_output": {
            "new_insights": [ins.model_dump() for ins in analyst_output.new_insights],
            "historical_actions": [
                {
                    "historical_index": a.historical_index,
                    "action": a.action.value,
                    "reason": a.reason,
                    "merged_insight": a.merged_insight.model_dump() if a.merged_insight else None,
                    "replacement_insight": a.replacement_insight.model_dump() if a.replacement_insight else None,
                }
                for a in analyst_output.historical_actions
            ],
            "analysis_summary": analyst_output.analysis_summary,
            "data_coverage": analyst_output.data_coverage,
            "confidence": analyst_output.confidence,
            "needs_further_analysis": analyst_output.needs_further_analysis,
            "suggested_next_focus": analyst_output.suggested_next_focus,
        },
        "analyzed_chunk_ids": analyzed_chunk_ids,
        "data_coverage": current_coverage,  # Dimension analysis doesn't change coverage
        "error_message": None,
    }


async def _analyze_anomaly(
    analyzer: ChunkAnalyzer,
    target: Dict[str, Any],
    chunks: List[PriorityChunk],
    enhanced_profile: EnhancedDataProfile,
    context: Dict[str, Any],
    insight_profile: DataInsightProfile,
    historical_insights: List[Insight],
    current_coverage: float,
    analyzed_chunk_ids: List[int],
    state: Dict[str, Any],
    config: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Analyze specific anomalies by row indices."""
    anomaly_indices = target.get("anomaly_indices") or []
    
    if not anomaly_indices:
        return _create_error_response("No anomaly_indices specified for analyze_anomaly")
    
    logger.info(f"Analyzing {len(anomaly_indices)} anomalies")
    
    # Create a virtual chunk from anomaly data
    virtual_chunk = _create_anomaly_chunk(
        anomaly_indices=anomaly_indices,
        chunks=chunks,
    )
    
    if virtual_chunk is None:
        return _create_error_response("Cannot create chunk for anomaly analysis")
    
    # Call analyzer with history
    analyst_output = await analyzer.analyze_chunk_with_history(
        chunk=virtual_chunk,
        context=context,
        insight_profile=insight_profile,
        historical_insights=historical_insights,
        current_coverage=current_coverage,
        state=state,
        config=config,
    )
    
    return {
        "analyst_output": {
            "new_insights": [ins.model_dump() for ins in analyst_output.new_insights],
            "historical_actions": [
                {
                    "historical_index": a.historical_index,
                    "action": a.action.value,
                    "reason": a.reason,
                    "merged_insight": a.merged_insight.model_dump() if a.merged_insight else None,
                    "replacement_insight": a.replacement_insight.model_dump() if a.replacement_insight else None,
                }
                for a in analyst_output.historical_actions
            ],
            "analysis_summary": analyst_output.analysis_summary,
            "data_coverage": analyst_output.data_coverage,
            "confidence": analyst_output.confidence,
            "needs_further_analysis": analyst_output.needs_further_analysis,
            "suggested_next_focus": analyst_output.suggested_next_focus,
        },
        "analyzed_chunk_ids": analyzed_chunk_ids,
        "data_coverage": current_coverage,  # Anomaly analysis doesn't change coverage
        "error_message": None,
    }


def _get_insight_profile(
    enhanced_profile: Optional[EnhancedDataProfile],
    state: Dict[str, Any],
) -> Optional[DataInsightProfile]:
    """Get DataInsightProfile from state (created by profiler_node).
    
    Priority:
    1. Use insight_profile from state (created by profiler_node)
    2. Fallback: create minimal profile from enhanced_profile
    """
    # 1. Use insight_profile from state (preferred - created by profiler_node)
    insight_profile = state.get("insight_profile")
    if insight_profile:
        return insight_profile
    
    # 2. Fallback: create minimal profile from enhanced_profile
    # This should rarely happen if profiler_node runs correctly
    if enhanced_profile:
        logger.warning("insight_profile not in state, creating minimal profile from enhanced_profile")
        return DataInsightProfile(
            distribution_type="unknown",
            pareto_ratio=0.0,
            statistics=enhanced_profile.statistics,
            top_n_summary=[],
        )
    
    return None


def _create_dimension_chunk(
    dimension: str,
    dimension_value: Optional[str],
    row_indices: Optional[List[int]],
    chunks: List[PriorityChunk],
) -> Optional[PriorityChunk]:
    """Create a virtual chunk for dimension analysis."""
    # Collect data from all chunks
    all_data = []
    for chunk in chunks:
        if chunk.data:
            all_data.extend(chunk.data)
    
    if not all_data:
        return None
    
    # Filter by dimension value if specified
    if dimension_value and row_indices:
        # Use row indices for precise filtering
        filtered_data = [all_data[i] for i in row_indices if i < len(all_data)]
    elif dimension_value:
        # Filter by dimension value
        filtered_data = [
            row for row in all_data
            if row.get(dimension) == dimension_value
        ]
    else:
        # No specific value, use all data for this dimension
        filtered_data = all_data
    
    if not filtered_data:
        return None
    
    # Create virtual chunk
    description = f"Dimension analysis: {dimension}"
    if dimension_value:
        description += f" = {dimension_value}"
    
    return PriorityChunk(
        chunk_id=-1,  # Virtual chunk ID
        chunk_type="dimension_analysis",
        data=filtered_data[:500],  # Limit to 500 rows
        row_count=len(filtered_data),
        priority=1,
        estimated_value="high",
        description=description,
    )


def _create_anomaly_chunk(
    anomaly_indices: List[int],
    chunks: List[PriorityChunk],
) -> Optional[PriorityChunk]:
    """Create a virtual chunk for anomaly analysis."""
    # Collect data from all chunks
    all_data = []
    for chunk in chunks:
        if chunk.data:
            all_data.extend(chunk.data)
    
    if not all_data:
        return None
    
    # Extract anomaly rows
    anomaly_data = [
        all_data[i] for i in anomaly_indices
        if i < len(all_data)
    ]
    
    if not anomaly_data:
        return None
    
    return PriorityChunk(
        chunk_id=-2,  # Virtual chunk ID
        chunk_type="anomaly_analysis",
        data=anomaly_data,
        row_count=len(anomaly_data),
        priority=1,
        estimated_value="high",
        description=f"Anomaly analysis: {len(anomaly_data)} anomalous rows",
    )


def _create_error_response(error_message: str) -> Dict[str, Any]:
    """Create an error response."""
    return {
        "analyst_output": None,
        "analyzed_chunk_ids": None,
        "data_coverage": None,
        "error_message": error_message,
    }


__all__ = ["analyzer_node"]
