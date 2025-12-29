# -*- coding: utf-8 -*-
"""Director Models.

Data models for the Analysis Director (总监) LLM.

Contains:
- DirectorAction: Actions the director can take
- DirectorInput: Input to the director
- DirectorDecision: Director's decision on next action
- InsightAction: Action to take on accumulated insights
- DirectorOutputWithAccumulation: Director output with insight accumulation
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Dict, List, Any, Optional, Literal
from enum import Enum

from .insight import Insight, InsightQuality


class DirectorAction(str, Enum):
    """Actions the director can take.
    
    <rule>
    - analyze_chunk: Analyze a specific data chunk
    - analyze_dimension: Analyze data for a specific dimension value
    - analyze_anomaly: Analyze specific anomalies
    - stop: Stop analysis and generate final summary
    </rule>
    """
    ANALYZE_CHUNK = "analyze_chunk"
    ANALYZE_DIMENSION = "analyze_dimension"
    ANALYZE_ANOMALY = "analyze_anomaly"
    STOP = "stop"


class InsightAction(str, Enum):
    """Action to take on an accumulated insight.
    
    <rule>
    - KEEP: Keep the insight as-is
    - MERGE: Merge with another insight (specify target index)
    - REPLACE: Replace with a new/updated insight
    - DISCARD: Discard the insight (duplicate or low value)
    </rule>
    """
    KEEP = "KEEP"
    MERGE = "MERGE"
    REPLACE = "REPLACE"
    DISCARD = "DISCARD"


class DirectorInput(BaseModel):
    """Input to the Director LLM.
    
    <what>All information the Director needs to make decisions</what>
    
    <fill_order>
    1. user_question (ALWAYS)
    2. profile_summary (ALWAYS)
    3. available_chunks (ALWAYS)
    4. analyzed_chunks (ALWAYS)
    5. current_insights (ALWAYS)
    6. iteration_count (ALWAYS)
    </fill_order>
    """
    model_config = ConfigDict(extra="forbid")
    
    user_question: str = Field(
        description="""<what>Original user question</what>
<when>ALWAYS required</when>"""
    )
    profile_summary: str = Field(
        description="""<what>Summary of enhanced data profile</what>
<when>ALWAYS required</when>
<rule>Include key findings from Tableau Pulse analyses</rule>"""
    )
    available_chunks: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="""<what>List of available chunks with metadata</what>
<when>ALWAYS required</when>
<rule>Format: [{"chunk_id": 1, "type": "top_data", "row_count": 100, "estimated_value": "high"}, ...]</rule>"""
    )
    analyzed_chunks: List[int] = Field(
        default_factory=list,
        description="""<what>IDs of already analyzed chunks</what>
<when>ALWAYS required</when>"""
    )
    current_insights: List[Insight] = Field(
        default_factory=list,
        description="""<what>Currently accumulated insights</what>
<when>ALWAYS required</when>"""
    )
    iteration_count: int = Field(
        default=0,
        description="""<what>Current iteration count</what>
<when>ALWAYS required</when>"""
    )
    max_iterations: int = Field(
        default=5,
        description="""<what>Maximum allowed iterations</what>
<when>ALWAYS required</when>"""
    )


class DirectorDecision(BaseModel):
    """Director's decision on next action.
    
    <what>Director decides what to analyze next or whether to stop</what>
    
    <fill_order>
    1. action (ALWAYS)
    2. should_continue (ALWAYS)
    3. reason (ALWAYS)
    4. target_chunk_id (if action = analyze_chunk)
    5. target_dimension (if action = analyze_dimension)
    6. target_dimension_value (if action = analyze_dimension)
    7. target_anomaly_indices (if action = analyze_anomaly)
    8. quality_assessment (ALWAYS)
    </fill_order>
    
    <examples>
    Analyze chunk: {"action": "analyze_chunk", "should_continue": true, "target_chunk_id": 2, "reason": "Top data chunk has high value"}
    Analyze dimension: {"action": "analyze_dimension", "should_continue": true, "target_dimension": "Region", "target_dimension_value": "West", "reason": "West region shows anomaly"}
    Stop: {"action": "stop", "should_continue": false, "reason": "Core question answered with high confidence"}
    </examples>
    
    <anti_patterns>
    X action=analyze_chunk but target_chunk_id is null
    X action=analyze_dimension but target_dimension is null
    X should_continue=true but action=stop
    </anti_patterns>
    """
    model_config = ConfigDict(extra="forbid")
    
    action: DirectorAction = Field(
        description="""<what>Action to take</what>
<when>ALWAYS required</when>"""
    )
    should_continue: bool = Field(
        description="""<what>Whether to continue analysis</what>
<when>ALWAYS required</when>
<rule>False only when action=stop</rule>"""
    )
    reason: str = Field(
        description="""<what>Reason for the decision</what>
<when>ALWAYS required</when>"""
    )
    
    # Target for analyze_chunk
    target_chunk_id: Optional[int] = Field(
        default=None,
        description="""<what>Target chunk ID to analyze</what>
<when>action = analyze_chunk</when>
<dependency>action == analyze_chunk</dependency>"""
    )
    
    # Target for analyze_dimension
    target_dimension: Optional[str] = Field(
        default=None,
        description="""<what>Target dimension name</what>
<when>action = analyze_dimension</when>
<dependency>action == analyze_dimension</dependency>"""
    )
    target_dimension_value: Optional[str] = Field(
        default=None,
        description="""<what>Target dimension value</what>
<when>action = analyze_dimension</when>
<dependency>action == analyze_dimension</dependency>"""
    )
    
    # Target for analyze_anomaly
    target_anomaly_indices: Optional[List[int]] = Field(
        default=None,
        description="""<what>Target anomaly row indices</what>
<when>action = analyze_anomaly</when>
<dependency>action == analyze_anomaly</dependency>"""
    )
    
    # Quality assessment
    quality_assessment: Optional[InsightQuality] = Field(
        default=None,
        description="""<what>Current insight quality assessment</what>
<when>ALWAYS required</when>"""
    )


class InsightActionItem(BaseModel):
    """Action to take on a specific insight.
    
    <what>Specifies what action to take on an insight at a given index</what>
    """
    model_config = ConfigDict(extra="forbid")
    
    insight_index: int = Field(
        description="""<what>Index of the insight in accumulated list</what>
<when>ALWAYS required</when>"""
    )
    action: InsightAction = Field(
        description="""<what>Action to take on this insight</what>
<when>ALWAYS required</when>"""
    )
    merge_with_index: Optional[int] = Field(
        default=None,
        description="""<what>Index of insight to merge with</what>
<when>action = MERGE</when>
<dependency>action == MERGE</dependency>"""
    )
    replacement_insight: Optional[Insight] = Field(
        default=None,
        description="""<what>New insight to replace with</what>
<when>action = REPLACE</when>
<dependency>action == REPLACE</dependency>"""
    )
    reason: str = Field(
        default="",
        description="""<what>Reason for this action</what>
<when>Recommended</when>"""
    )


class DirectorOutputWithAccumulation(BaseModel):
    """Director output with insight accumulation and final summary.
    
    <what>Director output including insight processing and final summary generation</what>
    
    <fill_order>
    1. decision (ALWAYS)
    2. insight_actions (if processing analyst output)
    3. new_insights_to_add (if analyst provided new insights)
    4. accumulated_insights (ALWAYS)
    5. final_summary (if should_continue=False)
    </fill_order>
    
    <examples>
    Continue: {"decision": {...}, "insight_actions": [...], "new_insights_to_add": [...], "accumulated_insights": [...]}
    Stop: {"decision": {"action": "stop", ...}, "accumulated_insights": [...], "final_summary": "Analysis complete. Key findings: ..."}
    </examples>
    
    <anti_patterns>
    X should_continue=false but final_summary is empty
    X insight_actions contains invalid indices
    </anti_patterns>
    """
    model_config = ConfigDict(extra="forbid")
    
    decision: DirectorDecision = Field(
        description="""<what>Director's decision</what>
<when>ALWAYS required</when>"""
    )
    
    # Insight processing
    insight_actions: List[InsightActionItem] = Field(
        default_factory=list,
        description="""<what>Actions to take on existing insights</what>
<when>If processing analyst output</when>
<rule>Based on analyst's historical insight processing suggestions</rule>"""
    )
    new_insights_to_add: List[Insight] = Field(
        default_factory=list,
        description="""<what>New insights to add to accumulation</what>
<when>If analyst provided new insights</when>"""
    )
    
    # Accumulated insights (after processing)
    accumulated_insights: List[Insight] = Field(
        default_factory=list,
        description="""<what>All accumulated insights after processing</what>
<when>ALWAYS required</when>"""
    )
    
    # Final summary (when stopping)
    final_summary: Optional[str] = Field(
        default=None,
        description="""<what>Final natural language summary</what>
<when>decision.should_continue = False</when>
<dependency>decision.should_continue == False</dependency>
<rule>Comprehensive summary of all findings, answering user's question</rule>"""
    )


__all__ = [
    "DirectorAction",
    "InsightAction",
    "DirectorInput",
    "DirectorDecision",
    "InsightActionItem",
    "DirectorOutputWithAccumulation",
]
