"""
Workflow State Definition

Core state types used by the workflow orchestration layer.
This module is placed in core/ to avoid circular imports between
nodes/ and orchestration/ packages.

Architecture:
- SemanticParser Agent → SemanticParseResult, SemanticQuery (pure semantic)
- FieldMapper Node → MappedQuery (business terms mapped to technical fields)
- QueryBuilder Node → QueryRequest (technical query)
- Execute Node → ExecuteResult
- Insight Agent → insights
- Replanner Agent → ReplanDecision
"""
from __future__ import annotations

from typing import TypedDict, Annotated, List, Dict, Optional, Any
import operator

# LangChain message types for conversation history
from langchain_core.messages import BaseMessage

# Core models (platform-agnostic)
from tableau_assistant.src.core.models import SemanticQuery
from tableau_assistant.src.core.models import SemanticParseResult
from tableau_assistant.src.core.models import MappedQuery, ReplanDecision, Insight
from tableau_assistant.src.core.models.execute_result import ExecuteResult
from tableau_assistant.src.core.models.query_request import QueryRequest


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
    Workflow state (refactored version with pure semantic layer)
    
    Contains all necessary data to ensure workflow completeness and traceability.
    Uses Annotated + operator.add for automatic accumulation.
    
    Architecture:
    - SemanticParser Agent outputs SemanticParseResult, SemanticQuery (pure semantic)
    - FieldMapper Node outputs MappedQuery (technical field mapping)
    - QueryBuilder Node outputs query request (technical query)
    - Execute Node outputs ExecuteResult
    
    Note:
    - Context information (datasource_luid, user_id, etc.) is passed through Runtime
    - Platform-specific query types (e.g., VizQLQuery) are stored as Any
    """
    
    # ═══════════════════════════════════════════════════════════════════════
    # Conversation History (for LLM context and SummarizationMiddleware)
    # ═══════════════════════════════════════════════════════════════════════
    # LangChain message list, auto-accumulates via operator.add
    # Format: [HumanMessage(question), AIMessage(structured_summary), ...]
    messages: Annotated[List[BaseMessage], operator.add]
    
    # List of answered questions (for Replanner deduplication)
    # Used by Replanner to avoid generating duplicate exploration questions
    answered_questions: Annotated[List[str], operator.add]
    
    # ═══════════════════════════════════════════════════════════════════════
    # User Input
    # ═══════════════════════════════════════════════════════════════════════
    question: str                          # User's original question
    
    # ═══════════════════════════════════════════════════════════════════════
    # Intent Classification (SemanticParser Agent output)
    # Used for routing: intent.type == DATA_QUERY → field_mapper, else → END
    # ═══════════════════════════════════════════════════════════════════════
    is_analysis_question: bool             # intent.type == DATA_QUERY (for routing)
    
    # Non-analysis responses (when is_analysis_question=False)
    clarification: Optional[str]           # Clarification question for user
    general_response: Optional[str]        # General response (non-data questions)
    non_analysis_response: Optional[str]   # Combined non-analysis response
    
    # ═══════════════════════════════════════════════════════════════════════
    # Pure Semantic Layer (new architecture - using core/models)
    # All fields are Pydantic objects, NOT dicts
    # ═══════════════════════════════════════════════════════════════════════
    # SemanticParserAgent output (LLM combination: Step1 + Step2 + Observer)
    semantic_parse_result: Optional[SemanticParseResult]  # Full parse result
    semantic_query: Optional[SemanticQuery]  # SemanticQuery (extracted from parse result)
    restated_question: Optional[str]         # Restated question from Step 1
    
    # FieldMapper Node output (business terms → technical fields)
    mapped_query: Optional[MappedQuery]      # MappedQuery Pydantic object
    
    # QueryBuilder Node output (platform-specific query)
    # Uses QueryRequest base type - actual instance will be platform-specific (e.g., VizQLQueryRequest)
    vizql_query: Optional[QueryRequest]      # Platform-specific query object
    
    # Execute Node output
    query_result: Optional[ExecuteResult]   # ExecuteResult Pydantic object
    
    # ═══════════════════════════════════════════════════════════════════════
    # Insight Agent Output (progressive accumulation)
    # All insights are Pydantic objects
    # ═══════════════════════════════════════════════════════════════════════
    insights: Annotated[List[Insight], operator.add]      # Current round insights
    all_insights: Annotated[List[Insight], operator.add]  # All accumulated insights
    
    # ═══════════════════════════════════════════════════════════════════════
    # Replanner Agent Output (smart replanning)
    # ═══════════════════════════════════════════════════════════════════════
    replan_decision: Optional[ReplanDecision]  # ReplanDecision Pydantic object
    replan_count: int                          # Current replan count
    max_replan_rounds: int                     # Maximum replan rounds (default: 3)
    replan_history: Annotated[List[ReplanHistoryRecord], operator.add]  # Replan history
    
    # Final report
    final_report: Optional[Dict[str, str]]
    
    # ═══════════════════════════════════════════════════════════════════════
    # Control Flow
    # ═══════════════════════════════════════════════════════════════════════
    current_stage: str                         # Current execution stage
    execution_path: Annotated[List[str], operator.add]  # Execution path
    
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
    datasource: Optional[str]                  # Datasource name/LUID
    data_model: Optional[Dict[str, str]]       # Full data model (DataModel serialized)
    dimension_hierarchy: Optional[Dict[str, Dict[str, str]]]  # Dimension hierarchy
    
    # Additional data for Replanner (filled by Insight node)
    data_insight_profile: Optional[Dict[str, Any]]  # Data insight profile
    current_dimensions: List[str]              # Currently analyzed dimensions
    pending_questions: List[Dict[str, Any]]    # Pending exploration questions queue
    
    # ═══════════════════════════════════════════════════════════════════════
    # Error Handling
    # ═══════════════════════════════════════════════════════════════════════
    errors: Annotated[List[ErrorRecord], operator.add]    # Error records
    warnings: Annotated[List[WarningRecord], operator.add]  # Warning records
    
    # ═══════════════════════════════════════════════════════════════════════
    # Performance Monitoring
    # ═══════════════════════════════════════════════════════════════════════
    performance: Optional[PerformanceMetrics]      # Performance metrics
    
    # ═══════════════════════════════════════════════════════════════════════
    # Visualization Data
    # ═══════════════════════════════════════════════════════════════════════
    visualizations: Annotated[List[VisualizationData], operator.add]



class VizQLInput(TypedDict):
    """
    Workflow input
    
    Defined using input_schema, provides type checking
    """
    question: str  # User question


class AnalysisPathStep(TypedDict):
    """Analysis path step structure"""
    step: int
    node: str
    action: str
    result: str


class VizQLOutput(TypedDict):
    """
    Workflow output
    
    Defined using output_schema, provides type checking
    """
    final_report: Dict[str, str]       # Final report
    executive_summary: str             # Executive summary
    key_findings: List[str]            # Key findings
    analysis_path: List[AnalysisPathStep]  # Analysis path
    recommendations: List[str]         # Follow-up recommendations
    visualizations: List[VisualizationData]  # Visualization data


def create_initial_state(
    question: str,
    max_replan_rounds: int = 3,
    datasource: Optional[str] = None,
) -> VizQLState:
    """
    Create initial state (refactored version with pure semantic layer)
    
    Args:
        question: User question
        max_replan_rounds: Maximum number of replan rounds (default: 3)
        datasource: Datasource name/LUID
    
    Returns:
        Initialized VizQLState (contains all necessary fields)
    """
    import time
    from langchain_core.messages import HumanMessage
    
    # Create initial user message with source marking
    # This enables tracking message origin (user vs replanner vs insight)
    initial_message = HumanMessage(
        content=question,
        additional_kwargs={"source": "user"}
    )
    
    return VizQLState(
        # Conversation history (for LLM context)
        # Initialize with user's question marked with source
        messages=[initial_message],
        answered_questions=[],
        
        # User input
        question=question,
        
        # Intent classification (for routing)
        is_analysis_question=True,  # Default to True, SemanticParser will update based on intent.type
        
        # Non-analysis responses (when is_analysis_question=False)
        clarification=None,
        general_response=None,
        non_analysis_response=None,
        
        # Pure semantic layer (using core/models)
        semantic_parse_result=None,  # SemanticParserAgent output
        semantic_query=None,         # SemanticQuery (from parse result)
        restated_question=None,      # Restated question from Step 1
        mapped_query=None,           # FieldMapper Node output
        vizql_query=None,            # QueryBuilder Node output
        query_result=None,           # Execute Node output
        
        # Insight Agent output
        insights=[],
        all_insights=[],
        
        # Replanner Agent output
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
        
        # Metadata (data model)
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
    "VizQLInput",
    "VizQLOutput",
    "create_initial_state",
    # Helper types
    "ErrorRecord",
    "WarningRecord",
    "ReplanHistoryRecord",
    "PerformanceMetrics",
    "VisualizationData",
    "AnalysisPathStep",
]
