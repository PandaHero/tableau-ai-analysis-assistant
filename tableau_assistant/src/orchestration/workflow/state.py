"""
Workflow State Definition

State types used by the workflow orchestration layer.
This module is in orchestration/workflow/ because state is part of workflow orchestration,
not core domain models.

Architecture (Dependency Direction: orchestration → agents → core):
- orchestration/workflow/state.py can import from agents/ and core/
- agents/ can import from core/
- core/ has no external dependencies

Node Outputs:
- SemanticParser Agent → SemanticParseResult (agent layer), SemanticQuery (core layer)
- FieldMapper Node → MappedQuery (to be migrated to agents/)
- QueryBuilder Node → QueryRequest (core layer)
- Execute Node → ExecuteResult (core layer)
- Insight Agent → Insight (to be migrated to agents/)
- Replanner Agent → ReplanDecision (to be migrated to agents/)
"""
from __future__ import annotations

from typing import TypedDict, Annotated, List, Dict, Optional, Any
import operator

# LangChain message types for conversation history
from langchain_core.messages import BaseMessage

# Core models (platform-agnostic)
# Orchestration layer only imports from core layer - no agent layer imports
from tableau_assistant.src.core.models import SemanticQuery
from tableau_assistant.src.core.models import MappedQuery, ReplanDecision, Insight
from tableau_assistant.src.core.models.execute_result import ExecuteResult
from tableau_assistant.src.core.models.query_request import QueryRequest
from tableau_assistant.src.core.models.enums import IntentType


# ═══════════════════════════════════════════════════════════════════════════
# Type Definitions for State Fields
# ═══════════════════════════════════════════════════════════════════════════

class ErrorRecord(TypedDict):
    """Error record structure"""
    node: str
    error: str
    type: str


class WarningRecord(TypedDict):
    """Warning record structure"""
    node: str
    message: str
    type: str


class ReplanHistoryRecord(TypedDict):
    """Replan history record structure"""
    round: int
    decision: str
    reason: str
    questions: List[str]


class PerformanceMetrics(TypedDict, total=False):
    """Performance metrics structure"""
    start_time: float
    end_time: float
    token_count: int
    llm_calls: int
    vds_calls: int
    total_duration: float


class VisualizationData(TypedDict, total=False):
    """Visualization data structure"""
    type: str
    title: str
    data: List[Dict[str, str]]
    config: Dict[str, str]


class VizQLState(TypedDict):
    """
    Workflow state for VizQL analysis pipeline.
    
    Contains all necessary data to ensure workflow completeness and traceability.
    Uses Annotated + operator.add for automatic accumulation.
    
    Architecture:
    - SemanticParser Agent outputs SemanticParseResult (full result) and SemanticQuery (core)
    - FieldMapper Node outputs MappedQuery (technical field mapping)
    - QueryBuilder Node outputs QueryRequest (platform-specific query)
    - Execute Node outputs ExecuteResult
    
    Note:
    - Context information (datasource_luid, user_id, etc.) is passed through Runtime
    - Platform-specific query types (e.g., VizQLQuery) are stored as Any
    """
    
    # ═══════════════════════════════════════════════════════════════════════
    # Conversation History (for LLM context and SummarizationMiddleware)
    # ═══════════════════════════════════════════════════════════════════════
    messages: Annotated[List[BaseMessage], operator.add]
    answered_questions: Annotated[List[str], operator.add]
    
    # ═══════════════════════════════════════════════════════════════════════
    # User Input
    # ═══════════════════════════════════════════════════════════════════════
    question: str
    
    # ═══════════════════════════════════════════════════════════════════════
    # Intent Classification (SemanticParser Agent output - flattened)
    # ═══════════════════════════════════════════════════════════════════════
    is_analysis_question: bool
    intent_type: Optional[IntentType]        # Intent type (core enum)
    intent_reasoning: Optional[str]          # Intent classification reasoning
    general_response: Optional[str]
    non_analysis_response: Optional[str]
    
    # Clarification fields (flattened from ClarificationQuestion)
    clarification_question: Optional[str]    # Clarification question text
    clarification_options: Optional[List[str]]  # Possible options for user
    clarification_field: Optional[str]       # Related field that needs clarification
    
    # ═══════════════════════════════════════════════════════════════════════
    # SemanticParser Agent Output (core layer types only)
    # ═══════════════════════════════════════════════════════════════════════
    semantic_query: Optional[SemanticQuery]  # SemanticQuery (core layer)
    restated_question: Optional[str]         # Restated question from Step 1
    
    # ═══════════════════════════════════════════════════════════════════════
    # FieldMapper Node Output
    # ═══════════════════════════════════════════════════════════════════════
    mapped_query: Optional[MappedQuery]
    
    # ═══════════════════════════════════════════════════════════════════════
    # QueryBuilder Node Output
    # ═══════════════════════════════════════════════════════════════════════
    vizql_query: Optional[QueryRequest]
    
    # ═══════════════════════════════════════════════════════════════════════
    # Execute Node Output
    # ═══════════════════════════════════════════════════════════════════════
    query_result: Optional[ExecuteResult]
    
    # ═══════════════════════════════════════════════════════════════════════
    # Insight Agent Output (progressive accumulation)
    # ═══════════════════════════════════════════════════════════════════════
    insights: Annotated[List[Insight], operator.add]
    all_insights: Annotated[List[Insight], operator.add]
    
    # ═══════════════════════════════════════════════════════════════════════
    # Replanner Agent Output
    # ═══════════════════════════════════════════════════════════════════════
    replan_decision: Optional[ReplanDecision]
    replan_count: int
    max_replan_rounds: int
    replan_history: Annotated[List[ReplanHistoryRecord], operator.add]
    final_report: Optional[Dict[str, str]]
    
    # ═══════════════════════════════════════════════════════════════════════
    # Control Flow
    # ═══════════════════════════════════════════════════════════════════════
    current_stage: str
    execution_path: Annotated[List[str], operator.add]
    
    # Node completion flags
    semantic_parser_complete: bool
    field_mapper_complete: bool
    query_builder_complete: bool
    execute_complete: bool
    insight_complete: bool
    replanner_complete: bool
    
    # ═══════════════════════════════════════════════════════════════════════
    # Data Model (loaded at workflow startup)
    # ═══════════════════════════════════════════════════════════════════════
    datasource: Optional[str]
    data_model: Optional[Dict[str, str]]
    dimension_hierarchy: Optional[Dict[str, Dict[str, str]]]
    data_insight_profile: Optional[Dict[str, Any]]
    current_dimensions: List[str]
    pending_questions: List[Dict[str, Any]]
    
    # ═══════════════════════════════════════════════════════════════════════
    # Error Handling
    # ═══════════════════════════════════════════════════════════════════════
    errors: Annotated[List[ErrorRecord], operator.add]
    warnings: Annotated[List[WarningRecord], operator.add]
    
    # ═══════════════════════════════════════════════════════════════════════
    # Performance Monitoring
    # ═══════════════════════════════════════════════════════════════════════
    performance: Optional[PerformanceMetrics]
    
    # ═══════════════════════════════════════════════════════════════════════
    # Visualization Data
    # ═══════════════════════════════════════════════════════════════════════
    visualizations: Annotated[List[VisualizationData], operator.add]


def create_initial_state(
    question: str,
    max_replan_rounds: int = 3,
    datasource: Optional[str] = None,
) -> VizQLState:
    """
    Create initial workflow state.
    
    Args:
        question: User question
        max_replan_rounds: Maximum number of replan rounds (default: 3)
        datasource: Datasource name/LUID
    
    Returns:
        Initialized VizQLState
    """
    import time
    from langchain_core.messages import HumanMessage
    
    initial_message = HumanMessage(
        content=question,
        additional_kwargs={"source": "user"}
    )
    
    return VizQLState(
        # Conversation history
        messages=[initial_message],
        answered_questions=[],
        
        # User input
        question=question,
        
        # Intent classification (flattened)
        is_analysis_question=True,
        intent_type=None,
        intent_reasoning=None,
        general_response=None,
        non_analysis_response=None,
        
        # Clarification fields (flattened)
        clarification_question=None,
        clarification_options=None,
        clarification_field=None,
        
        # SemanticParser output (core layer types only)
        semantic_query=None,
        restated_question=None,
        
        # FieldMapper output
        mapped_query=None,
        
        # QueryBuilder output
        vizql_query=None,
        
        # Execute output
        query_result=None,
        
        # Insight output
        insights=[],
        all_insights=[],
        
        # Replanner output
        replan_decision=None,
        replan_count=0,
        max_replan_rounds=max_replan_rounds,
        replan_history=[],
        final_report=None,
        
        # Control flow
        current_stage="semantic_parser",
        execution_path=[],
        
        # Node completion flags
        semantic_parser_complete=False,
        field_mapper_complete=False,
        query_builder_complete=False,
        execute_complete=False,
        insight_complete=False,
        replanner_complete=False,
        
        # Data model
        datasource=datasource,
        data_model=None,
        dimension_hierarchy=None,
        data_insight_profile=None,
        current_dimensions=[],
        pending_questions=[],
        
        # Error handling
        errors=[],
        warnings=[],
        
        # Performance monitoring
        performance={
            "start_time": time.time(),
            "token_count": 0,
            "llm_calls": 0,
            "vds_calls": 0
        },
        
        # Visualization data
        visualizations=[]
    )


__all__ = [
    # State types
    "VizQLState",
    "create_initial_state",
    # Helper types
    "ErrorRecord",
    "WarningRecord",
    "ReplanHistoryRecord",
    "PerformanceMetrics",
    "VisualizationData",
]
