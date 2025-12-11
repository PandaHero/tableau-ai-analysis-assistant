"""
VizQL workflow state definition

Uses LangGraph 1.0 state_schema feature

Architecture (refactored):
- Understanding Agent → SemanticQuery (pure semantic, no VizQL concepts)
- FieldMapper Node → MappedQuery (business terms mapped to technical fields)
- QueryBuilder Node → VizQLQuery (technical query)
- Execute Node → QueryResult
- Insight Agent → insights
- Replanner Agent → ReplanDecision

Note: Boost Agent has been REMOVED, its functionality merged into Understanding Agent.
"""
from __future__ import annotations

from typing import TypedDict, Annotated, List, Dict, Any, Optional
import operator

# 运行时导入类型（LangGraph StateGraph 需要在运行时解析类型）
from tableau_assistant.src.models.semantic.query import SemanticQuery, MappedQuery
from tableau_assistant.src.models.vizql.types import VizQLQuery
from tableau_assistant.src.models.replanner.replan_decision import ReplanDecision


class VizQLState(TypedDict):
    """
    VizQL workflow state (refactored version with pure semantic layer)
    
    Contains all necessary data to ensure workflow completeness and traceability.
    Uses Annotated + operator.add for automatic accumulation.
    
    Architecture:
    - Understanding Agent outputs SemanticQuery (pure semantic)
    - FieldMapper Node outputs MappedQuery (technical field mapping)
    - QueryBuilder Node outputs VizQLQuery (technical query)
    - Execute Node outputs QueryResult
    
    Note:
    - Context information (datasource_luid, user_id, etc.) is passed through Runtime
    - Boost Agent has been REMOVED, functionality merged into Understanding Agent
    """
    
    # ═══════════════════════════════════════════════════════════════════════
    # User Input
    # ═══════════════════════════════════════════════════════════════════════
    question: str                          # User's original question
    
    # ═══════════════════════════════════════════════════════════════════════
    # Question Classification (Understanding Agent output)
    # Used for routing decision: is_analysis_question=False → END
    # ═══════════════════════════════════════════════════════════════════════
    is_analysis_question: bool             # Whether this is an analysis question (for routing)
    
    # ═══════════════════════════════════════════════════════════════════════
    # Pure Semantic Layer (new architecture)
    # All fields are Pydantic objects, NOT dicts
    # ═══════════════════════════════════════════════════════════════════════
    # Understanding Agent output (pure semantic, no VizQL concepts)
    semantic_query: Optional[SemanticQuery]  # SemanticQuery Pydantic object
    
    # FieldMapper Node output (business terms → technical fields)
    mapped_query: Optional[MappedQuery]      # MappedQuery Pydantic object
    
    # QueryBuilder Node output (technical VizQL query)
    vizql_query: Optional[VizQLQuery]        # VizQLQuery Pydantic object
    
    # Execute Node output
    query_result: Optional[Dict[str, Any]]   # QueryResult dict
    
    # ═══════════════════════════════════════════════════════════════════════
    # Insight Agent Output (progressive accumulation)
    # All insights are Pydantic objects
    # ═══════════════════════════════════════════════════════════════════════
    insights: Annotated[List[Any], operator.add]      # Current round insights (Pydantic objects)
    all_insights: Annotated[List[Any], operator.add]  # All accumulated insights (Pydantic objects)
    
    # ═══════════════════════════════════════════════════════════════════════
    # Replanner Agent Output (smart replanning)
    # ═══════════════════════════════════════════════════════════════════════
    replan_decision: Optional[ReplanDecision]  # ReplanDecision Pydantic object
    replan_count: int                          # Current replan count
    max_replan_rounds: int                     # Maximum replan rounds (default: 3)
    replan_history: Annotated[List[Dict[str, Any]], operator.add]  # Replan history
    
    # Final report
    final_report: Optional[Dict[str, Any]]
    
    # ═══════════════════════════════════════════════════════════════════════
    # Control Flow
    # ═══════════════════════════════════════════════════════════════════════
    current_stage: str                         # Current execution stage
    execution_path: Annotated[List[str], operator.add]  # Execution path
    
    # Node completion flags
    understanding_complete: bool
    field_mapper_complete: bool
    query_builder_complete: bool
    execute_complete: bool
    insight_complete: bool
    replanner_complete: bool
    
    # ═══════════════════════════════════════════════════════════════════════
    # Metadata
    # ═══════════════════════════════════════════════════════════════════════
    datasource: Optional[str]                  # Datasource name/LUID
    metadata: Optional[Dict[str, Any]]         # Datasource metadata
    dimension_hierarchy: Optional[Dict[str, Any]]  # Dimension hierarchy
    
    # ═══════════════════════════════════════════════════════════════════════
    # Error Handling
    # ═══════════════════════════════════════════════════════════════════════
    errors: Annotated[List[Dict[str, Any]], operator.add]    # Error records
    warnings: Annotated[List[Dict[str, Any]], operator.add]  # Warning records
    
    # ═══════════════════════════════════════════════════════════════════════
    # Performance Monitoring
    # ═══════════════════════════════════════════════════════════════════════
    performance: Optional[Dict[str, Any]]      # Performance metrics
    
    # ═══════════════════════════════════════════════════════════════════════
    # Visualization Data
    # ═══════════════════════════════════════════════════════════════════════
    visualizations: Annotated[List[Dict[str, Any]], operator.add]


class VizQLInput(TypedDict):
    """
    VizQL workflow input
    
    Defined using input_schema, provides type checking
    """
    question: str  # User question


class VizQLOutput(TypedDict):
    """
    VizQL workflow output
    
    Defined using output_schema, provides type checking
    """
    final_report: Dict[str, Any]       # Final report
    executive_summary: str             # Executive summary
    key_findings: List[str]            # Key findings
    analysis_path: List[Dict[str, Any]]  # Analysis path
    recommendations: List[str]         # Follow-up recommendations
    visualizations: List[Dict[str, Any]]  # Visualization data


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
    
    return VizQLState(
        # User input
        question=question,
        
        # Question classification (for routing)
        is_analysis_question=True,  # Default to True, Understanding Agent will update
        
        # Pure semantic layer
        semantic_query=None,   # Understanding Agent output
        mapped_query=None,     # FieldMapper Node output
        vizql_query=None,      # QueryBuilder Node output
        query_result=None,     # Execute Node output
        
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
        current_stage="understanding",
        execution_path=[],
        
        # Node completion flags
        understanding_complete=False,
        field_mapper_complete=False,
        query_builder_complete=False,
        execute_complete=False,
        insight_complete=False,
        replanner_complete=False,
        
        # Metadata
        datasource=datasource,
        metadata=None,
        dimension_hierarchy=None,
        
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
