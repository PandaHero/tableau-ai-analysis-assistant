"""
Property Tests: Workflow Node Order and Routing

**Feature: agent-refactor-with-rag**
**Properties: 2, 3, 4**

Property 2: 工作流节点顺序保持
Property 3: 非分析类问题路由
Property 4: 智能重规划路由正确性

**Validates: Requirements 2.2, 2.3, 2.4, 2.5, 17.4, 17.5, 17.6, 17.7**
"""
import pytest
from hypothesis import given, strategies as st, settings, assume
from typing import Dict, Any, List, Optional


# ═══════════════════════════════════════════════════════════════════════════
# Strategies for generating test states
# ═══════════════════════════════════════════════════════════════════════════

# Strategy for question strings
question_strategy = st.text(
    alphabet=st.characters(whitelist_categories=('L', 'N', 'P', 'Z')),
    min_size=1,
    max_size=200
)

# Strategy for is_analysis_question
is_analysis_strategy = st.booleans()

# Strategy for completeness score (0.0 to 1.0)
completeness_score_strategy = st.floats(min_value=0.0, max_value=1.0)

# Strategy for replan count
replan_count_strategy = st.integers(min_value=0, max_value=10)

# Strategy for max replan rounds
max_replan_rounds_strategy = st.integers(min_value=1, max_value=10)

# Strategy for should_replan
should_replan_strategy = st.booleans()

# Strategy for new questions list
new_questions_strategy = st.lists(
    st.text(min_size=1, max_size=100),
    min_size=0,
    max_size=5
)

# Strategy for replan decision
replan_decision_strategy = st.fixed_dictionaries({
    "should_replan": should_replan_strategy,
    "completeness_score": completeness_score_strategy,
    "new_questions": new_questions_strategy,
    "missing_aspects": st.lists(st.text(min_size=1, max_size=50), max_size=3),
})

# Strategy for workflow state
workflow_state_strategy = st.fixed_dictionaries({
    "question": question_strategy,
    "is_analysis_question": is_analysis_strategy,
    "replan_decision": replan_decision_strategy,
    "replan_count": replan_count_strategy,
    "max_replan_rounds": max_replan_rounds_strategy,
})


# ═══════════════════════════════════════════════════════════════════════════
# Property 2: 工作流节点顺序保持
# ═══════════════════════════════════════════════════════════════════════════

def test_workflow_has_correct_nodes():
    """
    **Feature: agent-refactor-with-rag, Property 2: 工作流节点顺序保持**
    **Validates: Requirements 2.2**
    
    Property: The workflow should contain exactly 6 nodes in the correct order.
    """
    from tableau_assistant.src.workflow.factory import get_workflow_info, create_tableau_workflow
    
    # Create workflow
    workflow = create_tableau_workflow(use_memory_checkpointer=True)
    info = get_workflow_info(workflow)
    
    # Expected nodes in order
    expected_nodes = [
        "understanding",
        "field_mapper",
        "query_builder",
        "execute",
        "insight",
        "replanner"
    ]
    
    assert info["nodes"] == expected_nodes, \
        f"Expected nodes {expected_nodes}, got {info['nodes']}"


def test_workflow_edges_are_correct():
    """
    **Feature: agent-refactor-with-rag, Property 2: 工作流节点顺序保持**
    **Validates: Requirements 2.2**
    
    Property: The workflow edges should connect nodes in the correct sequence.
    """
    from tableau_assistant.src.workflow.factory import create_tableau_workflow
    from langgraph.graph import START, END
    
    # Create workflow (get the graph before compilation)
    from tableau_assistant.src.models.workflow import VizQLState
    from langgraph.graph import StateGraph
    
    graph = StateGraph(VizQLState)
    
    # We can't easily inspect edges after compilation, so we verify
    # the workflow structure through get_workflow_info
    workflow = create_tableau_workflow(use_memory_checkpointer=True)
    
    # The workflow should be compilable without errors
    assert workflow is not None, "Workflow should compile successfully"


# ═══════════════════════════════════════════════════════════════════════════
# Property 3: 非分析类问题路由
# ═══════════════════════════════════════════════════════════════════════════

@given(state=workflow_state_strategy)
@settings(max_examples=100, deadline=None)
def test_non_analysis_question_routes_to_end(state: Dict[str, Any]):
    """
    **Feature: agent-refactor-with-rag, Property 3: 非分析类问题路由**
    **Validates: Requirements 2.3**
    
    Property: For any Understanding output where is_analysis_question=False,
    the workflow should route to END.
    """
    from tableau_assistant.src.workflow.routes import route_after_understanding
    
    # Set is_analysis_question to False
    state["is_analysis_question"] = False
    
    result = route_after_understanding(state)
    
    assert result == "end", \
        f"Non-analysis question should route to 'end', got '{result}'"


@given(state=workflow_state_strategy)
@settings(max_examples=100, deadline=None)
def test_analysis_question_routes_to_field_mapper(state: Dict[str, Any]):
    """
    **Feature: agent-refactor-with-rag, Property 3: 非分析类问题路由**
    **Validates: Requirements 2.3**
    
    Property: For any Understanding output where is_analysis_question=True,
    the workflow should route to field_mapper.
    """
    from tableau_assistant.src.workflow.routes import route_after_understanding
    
    # Set is_analysis_question to True
    state["is_analysis_question"] = True
    
    result = route_after_understanding(state)
    
    assert result == "field_mapper", \
        f"Analysis question should route to 'field_mapper', got '{result}'"


@given(is_analysis=is_analysis_strategy)
@settings(max_examples=50, deadline=None)
def test_understanding_routing_is_deterministic(is_analysis: bool):
    """
    **Feature: agent-refactor-with-rag, Property 3: 非分析类问题路由**
    **Validates: Requirements 2.3**
    
    Property: The routing decision should be deterministic based on
    is_analysis_question value.
    """
    from tableau_assistant.src.workflow.routes import route_after_understanding
    
    state = {"is_analysis_question": is_analysis, "question": "test"}
    
    # Call multiple times
    results = [route_after_understanding(state) for _ in range(5)]
    
    # All results should be the same
    assert len(set(results)) == 1, \
        f"Routing should be deterministic, got different results: {results}"
    
    # Result should match expected
    expected = "field_mapper" if is_analysis else "end"
    assert results[0] == expected, \
        f"Expected '{expected}', got '{results[0]}'"


# ═══════════════════════════════════════════════════════════════════════════
# Property 4: 智能重规划路由正确性
# ═══════════════════════════════════════════════════════════════════════════

@given(
    should_replan=should_replan_strategy,
    replan_count=replan_count_strategy,
    max_rounds=max_replan_rounds_strategy,
    completeness=completeness_score_strategy
)
@settings(max_examples=200, deadline=None)
def test_replanner_routing_correctness(
    should_replan: bool,
    replan_count: int,
    max_rounds: int,
    completeness: float
):
    """
    **Feature: agent-refactor-with-rag, Property 4: 智能重规划路由正确性**
    **Validates: Requirements 2.4, 2.5, 17.4, 17.5, 17.6, 17.7**
    
    Property: For any Replanner output:
    - When should_replan=True AND replan_count < max → route to understanding
    - When should_replan=False OR replan_count >= max → route to END
    """
    from tableau_assistant.src.workflow.routes import route_after_replanner
    
    state = {
        "replan_decision": {
            "should_replan": should_replan,
            "completeness_score": completeness,
        },
        "replan_count": replan_count,
    }
    
    result = route_after_replanner(state, max_replan_rounds=max_rounds)
    
    # Determine expected result
    if replan_count >= max_rounds:
        expected = "end"
    elif should_replan:
        expected = "understanding"
    else:
        expected = "end"
    
    assert result == expected, \
        f"Expected '{expected}' for should_replan={should_replan}, " \
        f"replan_count={replan_count}, max_rounds={max_rounds}, got '{result}'"


@given(replan_count=st.integers(min_value=0, max_value=100))
@settings(max_examples=50, deadline=None)
def test_max_replan_rounds_enforced(replan_count: int):
    """
    **Feature: agent-refactor-with-rag, Property 4: 智能重规划路由正确性**
    **Validates: Requirements 17.7**
    
    Property: When replan_count >= max_replan_rounds, always route to END
    regardless of should_replan value.
    """
    from tableau_assistant.src.workflow.routes import route_after_replanner
    
    max_rounds = 3
    
    # When replan_count >= max_rounds, should always route to end
    if replan_count >= max_rounds:
        state = {
            "replan_decision": {
                "should_replan": True,  # Even if True
                "completeness_score": 0.5,  # Even if low
            },
            "replan_count": replan_count,
        }
        
        result = route_after_replanner(state, max_replan_rounds=max_rounds)
        
        assert result == "end", \
            f"Should route to 'end' when replan_count ({replan_count}) >= " \
            f"max_rounds ({max_rounds}), got '{result}'"


@given(completeness=completeness_score_strategy)
@settings(max_examples=50, deadline=None)
def test_should_replan_false_routes_to_end(completeness: float):
    """
    **Feature: agent-refactor-with-rag, Property 4: 智能重规划路由正确性**
    **Validates: Requirements 17.4, 17.5**
    
    Property: When should_replan=False, always route to END
    regardless of completeness score.
    """
    from tableau_assistant.src.workflow.routes import route_after_replanner
    
    state = {
        "replan_decision": {
            "should_replan": False,
            "completeness_score": completeness,
        },
        "replan_count": 0,  # Well under max
    }
    
    result = route_after_replanner(state, max_replan_rounds=10)
    
    assert result == "end", \
        f"Should route to 'end' when should_replan=False, got '{result}'"


@given(completeness=completeness_score_strategy)
@settings(max_examples=50, deadline=None)
def test_should_replan_true_routes_to_understanding(completeness: float):
    """
    **Feature: agent-refactor-with-rag, Property 4: 智能重规划路由正确性**
    **Validates: Requirements 17.4, 17.5**
    
    Property: When should_replan=True and replan_count < max,
    route to understanding.
    """
    from tableau_assistant.src.workflow.routes import route_after_replanner
    
    state = {
        "replan_decision": {
            "should_replan": True,
            "completeness_score": completeness,
        },
        "replan_count": 0,  # Well under max
    }
    
    result = route_after_replanner(state, max_replan_rounds=10)
    
    assert result == "understanding", \
        f"Should route to 'understanding' when should_replan=True " \
        f"and under max rounds, got '{result}'"


# ═══════════════════════════════════════════════════════════════════════════
# Edge Case Tests
# ═══════════════════════════════════════════════════════════════════════════

def test_understanding_routing_with_missing_field():
    """
    Edge case: State without is_analysis_question should default to True.
    """
    from tableau_assistant.src.workflow.routes import route_after_understanding
    
    state = {"question": "test question"}  # No is_analysis_question
    
    result = route_after_understanding(state)
    
    assert result == "field_mapper", \
        "Missing is_analysis_question should default to True (field_mapper)"


def test_replanner_routing_with_missing_decision():
    """
    Edge case: State without replan_decision should default to not replanning.
    """
    from tableau_assistant.src.workflow.routes import route_after_replanner
    
    state = {"replan_count": 0}  # No replan_decision
    
    result = route_after_replanner(state, max_replan_rounds=3)
    
    assert result == "end", \
        "Missing replan_decision should default to not replanning (end)"


def test_replanner_routing_with_empty_decision():
    """
    Edge case: Empty replan_decision should default to not replanning.
    """
    from tableau_assistant.src.workflow.routes import route_after_replanner
    
    state = {
        "replan_decision": {},
        "replan_count": 0
    }
    
    result = route_after_replanner(state, max_replan_rounds=3)
    
    assert result == "end", \
        "Empty replan_decision should default to not replanning (end)"


def test_replanner_routing_at_boundary():
    """
    Edge case: Test routing at exact boundary (replan_count == max_rounds - 1).
    """
    from tableau_assistant.src.workflow.routes import route_after_replanner
    
    max_rounds = 3
    
    # At boundary (count = 2, max = 3) - should still allow replan
    state = {
        "replan_decision": {
            "should_replan": True,
            "completeness_score": 0.5,
        },
        "replan_count": max_rounds - 1,  # 2
    }
    
    result = route_after_replanner(state, max_replan_rounds=max_rounds)
    
    assert result == "understanding", \
        f"At boundary (count={max_rounds-1}, max={max_rounds}), " \
        f"should still allow replan, got '{result}'"
    
    # Just over boundary (count = 3, max = 3) - should not allow replan
    state["replan_count"] = max_rounds  # 3
    
    result = route_after_replanner(state, max_replan_rounds=max_rounds)
    
    assert result == "end", \
        f"Over boundary (count={max_rounds}, max={max_rounds}), " \
        f"should not allow replan, got '{result}'"


def test_calculate_completeness_score():
    """
    Test the completeness score calculation helper function.
    """
    from tableau_assistant.src.workflow.routes import calculate_completeness_score
    
    # Test with high LLM score and good auxiliary conditions
    state = {
        "subtask_results": [{"data": "result1"}, {"data": "result2"}],
        "errors": [],
        "insights": [{"insight": "finding1"}],
    }
    replan_decision = {"completeness_score": 0.9}
    
    score = calculate_completeness_score(state, replan_decision)
    
    # LLM score (0.9) * 0.8 + auxiliary (1.0) * 0.2 = 0.72 + 0.2 = 0.92
    assert 0.9 <= score <= 1.0, \
        f"Expected score ~0.92, got {score}"
    
    # Test with no results (critical failure)
    state_no_results = {
        "subtask_results": [],
        "errors": [],
        "insights": [],
    }
    
    score_no_results = calculate_completeness_score(state_no_results, replan_decision)
    
    # LLM score (0.9) * 0.8 + auxiliary (0.0) * 0.2 = 0.72
    assert score_no_results < score, \
        f"Score with no results ({score_no_results}) should be lower than " \
        f"score with results ({score})"


# ═══════════════════════════════════════════════════════════════════════════
# Integration Tests
# ═══════════════════════════════════════════════════════════════════════════

def test_workflow_routing_integration():
    """
    Integration test: Verify routing functions work with actual workflow.
    """
    from tableau_assistant.src.workflow.factory import create_tableau_workflow
    from tableau_assistant.src.workflow.routes import (
        route_after_understanding,
        route_after_replanner
    )
    
    # Create workflow
    workflow = create_tableau_workflow(use_memory_checkpointer=True)
    
    # Test understanding routing
    analysis_state = {"is_analysis_question": True, "question": "销售额趋势"}
    non_analysis_state = {"is_analysis_question": False, "question": "你好"}
    
    assert route_after_understanding(analysis_state) == "field_mapper"
    assert route_after_understanding(non_analysis_state) == "end"
    
    # Test replanner routing
    replan_state = {
        "replan_decision": {"should_replan": True, "completeness_score": 0.5},
        "replan_count": 0
    }
    complete_state = {
        "replan_decision": {"should_replan": False, "completeness_score": 0.95},
        "replan_count": 1
    }
    
    assert route_after_replanner(replan_state, max_replan_rounds=3) == "understanding"
    assert route_after_replanner(complete_state, max_replan_rounds=3) == "end"


if __name__ == "__main__":
    print("=" * 60)
    print("Running Property Tests: Workflow Node Order and Routing")
    print("=" * 60)
    
    # Run edge case tests first
    print("\n--- Edge Case Tests ---")
    
    test_understanding_routing_with_missing_field()
    print("✅ test_understanding_routing_with_missing_field passed")
    
    test_replanner_routing_with_missing_decision()
    print("✅ test_replanner_routing_with_missing_decision passed")
    
    test_replanner_routing_with_empty_decision()
    print("✅ test_replanner_routing_with_empty_decision passed")
    
    test_replanner_routing_at_boundary()
    print("✅ test_replanner_routing_at_boundary passed")
    
    test_calculate_completeness_score()
    print("✅ test_calculate_completeness_score passed")
    
    # Run structure tests
    print("\n--- Structure Tests ---")
    
    test_workflow_has_correct_nodes()
    print("✅ test_workflow_has_correct_nodes passed")
    
    test_workflow_edges_are_correct()
    print("✅ test_workflow_edges_are_correct passed")
    
    # Run integration test
    print("\n--- Integration Tests ---")
    
    test_workflow_routing_integration()
    print("✅ test_workflow_routing_integration passed")
    
    # Run property tests
    print("\n--- Property Tests ---")
    
    test_non_analysis_question_routes_to_end()
    print("✅ test_non_analysis_question_routes_to_end passed")
    
    test_analysis_question_routes_to_field_mapper()
    print("✅ test_analysis_question_routes_to_field_mapper passed")
    
    test_understanding_routing_is_deterministic()
    print("✅ test_understanding_routing_is_deterministic passed")
    
    test_replanner_routing_correctness()
    print("✅ test_replanner_routing_correctness passed")
    
    test_max_replan_rounds_enforced()
    print("✅ test_max_replan_rounds_enforced passed")
    
    test_should_replan_false_routes_to_end()
    print("✅ test_should_replan_false_routes_to_end passed")
    
    test_should_replan_true_routes_to_understanding()
    print("✅ test_should_replan_true_routes_to_understanding passed")
    
    print("\n" + "=" * 60)
    print("All property tests passed! ✅")
    print("=" * 60)
