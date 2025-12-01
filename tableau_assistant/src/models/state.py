"""
VizQL workflow state definition

Uses LangGraph 1.0 state_schema feature
"""
from typing import TypedDict, Annotated, List, Dict, Any, Optional
import operator

# Import Pydantic models
from tableau_assistant.src.models.question import QuestionUnderstanding
from tableau_assistant.src.models.query_plan import QueryPlanningResult
from tableau_assistant.src.models.boost import QuestionBoost


class VizQLState(TypedDict):
    """
    VizQL workflow state (full version - production grade)
    
    Contains all necessary data to ensure workflow completeness and traceability
    Uses Annotated + operator.add for automatic accumulation
    
    Note:
    - Context information (datasource_luid, user_id, etc.) is passed through Runtime, not in State
    - Uses Pydantic objects to maintain type safety, avoiding dictionary conversion
    """
    
    # ========== User Input ==========
    question: str  # User's original question
    boosted_question: Optional[str]  # Optimized question (if using question boost)
    
    # ========== Agent Outputs ==========
    # Question Boost Agent
    boost: Optional[QuestionBoost]  # Question optimization result (Pydantic object)
    
    # Question Understanding Agent
    understanding: Optional[QuestionUnderstanding]  # Question understanding result (Pydantic object)
    
    # Query Planning Agent
    query_plan: Optional[QueryPlanningResult]  # Query planning result (Pydantic object, contains all subtasks)
    
    # Task execution results
    subtask_results: Annotated[List[Dict[str, Any]], operator.add]  # Subtask results (auto-accumulate)
    all_query_results: Annotated[List[Dict[str, Any]], operator.add]  # All query results (for dynamic planning)
    
    # Insight Agent
    insights: Annotated[List[Dict[str, Any]], operator.add]  # Insight results (auto-accumulate)
    all_insights: Annotated[List[Dict[str, Any]], operator.add]  # All insights (for dynamic planning)
    
    # Data merge results
    merged_data: Optional[Dict[str, Any]]  # Merged data
    
    # Replan Agent
    replan_decision: Optional[Dict[str, Any]]  # Replan decision
    replan_history: Annotated[List[Dict[str, Any]], operator.add]  # Replan history (auto-accumulate)
    
    # Summary Agent
    final_report: Optional[Dict[str, Any]]  # Final report
    
    # ========== Control Flow ==========
    replan_count: int  # Current replan count
    current_stage: str  # Current execution stage
    execution_path: Annotated[List[str], operator.add]  # Execution path (auto-accumulate)
    
    # ========== Metadata ==========
    metadata: Optional[Dict[str, Any]]  # Datasource metadata (from Store)
    dimension_hierarchy: Optional[Dict[str, Any]]  # Dimension hierarchy (from Store)
    
    # ========== Statistics ==========
    statistics: Optional[Dict[str, Any]]  # Statistics detection results
    
    # ========== Error Handling ==========
    errors: Annotated[List[Dict[str, Any]], operator.add]  # Error records (auto-accumulate)
    warnings: Annotated[List[Dict[str, Any]], operator.add]  # Warning records (auto-accumulate)
    
    # ========== Performance Monitoring ==========
    performance: Optional[Dict[str, Any]]  # Performance metrics (response time, token consumption, etc.)
    
    # ========== Visualization Data ==========
    visualizations: Annotated[List[Dict[str, Any]], operator.add]  # Visualization data (auto-accumulate)


class VizQLInput(TypedDict):
    """
    VizQL workflow input
    
    Defined using input_schema, provides type checking
    """
    question: str  # User question
    boost_question: bool  # Whether to use question boost (optional, default False)


class VizQLOutput(TypedDict):
    """
    VizQL workflow output
    
    Defined using output_schema, provides type checking
    """
    final_report: Dict[str, Any]  # Final report
    executive_summary: str  # Executive summary
    key_findings: List[str]  # Key findings
    analysis_path: List[Dict[str, Any]]  # Analysis path
    recommendations: List[str]  # Follow-up recommendations
    visualizations: List[Dict[str, Any]]  # Visualization data


# Initial state factory function
def create_initial_state(question: str, boost_question: bool = False) -> VizQLState:
    """
    Create initial state (full version - production grade)
    
    Args:
        question: User question
        boost_question: Whether to use question boost
    
    Returns:
        Initialized VizQLState (contains all necessary fields)
    """
    import time
    
    return VizQLState(
        # User input
        question=question,
        boosted_question=None,
        
        # Agent outputs (initially None or empty list)
        boost=None,  # Question boost result
        understanding=None,
        query_plan=None,
        subtask_results=[],
        all_query_results=[],
        insights=[],
        all_insights=[],
        merged_data=None,
        replan_decision=None,
        replan_history=[],
        final_report=None,
        
        # Control flow
        replan_count=0,
        current_stage="boost" if boost_question else "understanding",
        execution_path=[],
        
        # Metadata
        metadata=None,
        dimension_hierarchy=None,
        
        # Statistics
        statistics=None,
        
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


# Example usage
if __name__ == "__main__":
    # Create initial state
    state = create_initial_state(
        question="Sales by region in 2016",
        boost_question=False
    )
    
    print("Initial state created successfully:")
    print(f"  Question: {state['question']}")
    print(f"  Current stage: {state['current_stage']}")
    print(f"  Replan count: {state['replan_count']}")
    
    # Simulate state update
    state["understanding"] = {
        "question_type": ["comparison"],
        "complexity": "Simple"
    }
    state["current_stage"] = "planning"
    
    print("\nAfter state update:")
    print(f"  Current stage: {state['current_stage']}")
    print(f"  Understanding: {state['understanding']}")
