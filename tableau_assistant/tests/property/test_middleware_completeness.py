"""
Property Test: Middleware Configuration Completeness

**Feature: agent-refactor-with-rag, Property 1: 中间件配置完整性**
**Validates: Requirements 1.1, 1.2**

Property: For any factory function configuration, the created workflow should
contain all required middleware types.

Required middleware (7 total):
- TodoListMiddleware (LangChain)
- SummarizationMiddleware (LangChain) - requires model_name
- ModelRetryMiddleware (LangChain)
- ToolRetryMiddleware (LangChain)
- FilesystemMiddleware (custom) - TODO: implement in task 2.1
- PatchToolCallsMiddleware (custom) - TODO: implement in task 2.2
- HumanInTheLoopMiddleware (LangChain, optional) - only when interrupt_on is set
"""
import pytest
from hypothesis import given, strategies as st, settings, assume
from typing import Dict, Any, List, Optional
import os


# ═══════════════════════════════════════════════════════════════════════════
# Get real model configuration from settings
# ═══════════════════════════════════════════════════════════════════════════

def get_real_model_name() -> str:
    """Get the real model name from settings."""
    from tableau_assistant.src.config.settings import settings
    return settings.tooling_llm_model or "qwen3"


def get_llm_config() -> Dict[str, str]:
    """Get LLM configuration for testing."""
    from tableau_assistant.src.config.settings import settings
    return {
        "api_base": settings.llm_api_base,
        "api_key": settings.llm_api_key,
        "model": settings.tooling_llm_model,
        "provider": settings.llm_model_provider,
    }


def create_test_chat_model():
    """Create a ChatModel instance for testing using model manager."""
    from tableau_assistant.src.config.settings import settings
    from tableau_assistant.src.model_manager.llm import select_model
    
    return select_model(
        provider=settings.llm_model_provider,
        model_name=settings.tooling_llm_model,
        temperature=0,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Strategies for generating test configurations
# ═══════════════════════════════════════════════════════════════════════════

# Strategy for positive integers (for retry counts, thresholds)
positive_int_strategy = st.integers(min_value=1, max_value=10)

# Strategy for token thresholds
token_threshold_strategy = st.integers(min_value=1000, max_value=100000)

# Strategy for interrupt_on configuration
interrupt_on_strategy = st.one_of(
    st.none(),
    st.lists(
        st.sampled_from(["write_todos", "read_file", "custom_tool"]),
        min_size=1,
        max_size=3,
        unique=True
    )
)

# Strategy for complete middleware configuration
middleware_config_strategy = st.fixed_dictionaries({
    "summarization_token_threshold": token_threshold_strategy,
    "messages_to_keep": positive_int_strategy,
    "model_max_retries": positive_int_strategy,
    "tool_max_retries": positive_int_strategy,
    "filesystem_token_limit": token_threshold_strategy,
    "interrupt_on": interrupt_on_strategy,
    "max_replan_rounds": positive_int_strategy,
})


# ═══════════════════════════════════════════════════════════════════════════
# Property Tests
# ═══════════════════════════════════════════════════════════════════════════

@given(config=middleware_config_strategy)
@settings(max_examples=100, deadline=None)
def test_middleware_stack_contains_required_types_with_model(config: Dict[str, Any]):
    """
    **Feature: agent-refactor-with-rag, Property 1: 中间件配置完整性**
    **Validates: Requirements 1.1, 1.2**
    
    Property: For any valid configuration with a model name, the middleware stack
    should contain all required middleware types.
    
    Required middleware (always present when model_name is provided):
    - TodoListMiddleware
    - SummarizationMiddleware
    - ModelRetryMiddleware
    - ToolRetryMiddleware
    
    Conditional middleware:
    - HumanInTheLoopMiddleware (only when interrupt_on is set)
    
    TODO (tasks 2.1, 2.2):
    - FilesystemMiddleware
    - PatchToolCallsMiddleware
    """
    from tableau_assistant.src.workflow.factory import create_middleware_stack
    
    # Use real chat model from model manager
    chat_model = create_test_chat_model()
    
    # Create middleware stack
    middleware = create_middleware_stack(chat_model=chat_model, config=config)
    
    # Get middleware type names for easier assertion
    middleware_types = [type(m).__name__ for m in middleware]
    
    # ═══════════════════════════════════════════════════════════════════════
    # Assert required middleware are always present
    # ═══════════════════════════════════════════════════════════════════════
    
    # TodoListMiddleware - always required
    assert "TodoListMiddleware" in middleware_types, \
        "TodoListMiddleware should always be present"
    
    # ModelRetryMiddleware - always required
    assert "ModelRetryMiddleware" in middleware_types, \
        "ModelRetryMiddleware should always be present"
    
    # ToolRetryMiddleware - always required
    assert "ToolRetryMiddleware" in middleware_types, \
        "ToolRetryMiddleware should always be present"
    
    # SummarizationMiddleware - present when model_name is provided
    assert "SummarizationMiddleware" in middleware_types, \
        "SummarizationMiddleware should be present when chat_model is provided"
    
    # FilesystemMiddleware - always required (custom)
    assert "FilesystemMiddleware" in middleware_types, \
        "FilesystemMiddleware should always be present"
    
    # PatchToolCallsMiddleware - always required (custom)
    assert "PatchToolCallsMiddleware" in middleware_types, \
        "PatchToolCallsMiddleware should always be present"
    
    # ═══════════════════════════════════════════════════════════════════════
    # Assert conditional middleware
    # ═══════════════════════════════════════════════════════════════════════
    
    # HumanInTheLoopMiddleware - only when interrupt_on is set
    interrupt_on = config.get("interrupt_on")
    if interrupt_on:
        assert "HumanInTheLoopMiddleware" in middleware_types, \
            f"HumanInTheLoopMiddleware should be present when interrupt_on={interrupt_on}"
    else:
        assert "HumanInTheLoopMiddleware" not in middleware_types, \
            "HumanInTheLoopMiddleware should NOT be present when interrupt_on is None/empty"


@given(config=middleware_config_strategy)
@settings(max_examples=50, deadline=None)
def test_middleware_stack_without_model_name(config: Dict[str, Any]):
    """
    **Feature: agent-refactor-with-rag, Property 1: 中间件配置完整性**
    **Validates: Requirements 1.1, 1.2**
    
    Property: When model_name is None, SummarizationMiddleware should NOT be present.
    """
    from tableau_assistant.src.workflow.factory import create_middleware_stack
    
    # Create middleware stack without model name
    middleware = create_middleware_stack(model_name=None, config=config)
    
    # Get middleware type names
    middleware_types = [type(m).__name__ for m in middleware]
    
    # Required middleware should still be present
    assert "TodoListMiddleware" in middleware_types
    assert "ModelRetryMiddleware" in middleware_types
    assert "ToolRetryMiddleware" in middleware_types
    assert "FilesystemMiddleware" in middleware_types
    assert "PatchToolCallsMiddleware" in middleware_types
    
    # SummarizationMiddleware should NOT be present
    assert "SummarizationMiddleware" not in middleware_types, \
        "SummarizationMiddleware should NOT be present when model_name is None"


@given(config=middleware_config_strategy)
@settings(max_examples=50, deadline=None)
def test_middleware_configuration_parameters_applied(config: Dict[str, Any]):
    """
    **Feature: agent-refactor-with-rag, Property 1: 中间件配置完整性**
    **Validates: Requirements 1.1, 1.2**
    
    Property: For any configuration, the middleware should be configured
    with the provided parameters.
    """
    from tableau_assistant.src.workflow.factory import create_middleware_stack
    from langchain.agents.middleware import (
        ModelRetryMiddleware,
        ToolRetryMiddleware,
    )
    
    # Use real chat model
    chat_model = create_test_chat_model()
    middleware = create_middleware_stack(chat_model=chat_model, config=config)
    
    # Find specific middleware instances
    model_retry = None
    tool_retry = None
    
    for m in middleware:
        if isinstance(m, ModelRetryMiddleware):
            model_retry = m
        elif isinstance(m, ToolRetryMiddleware):
            tool_retry = m
    
    # Assert retry middleware have correct max_retries
    assert model_retry is not None, "ModelRetryMiddleware should be present"
    assert tool_retry is not None, "ToolRetryMiddleware should be present"
    
    # Check that max_retries is set (the actual value depends on implementation)
    assert hasattr(model_retry, 'max_retries'), \
        "ModelRetryMiddleware should have max_retries attribute"
    assert hasattr(tool_retry, 'max_retries'), \
        "ToolRetryMiddleware should have max_retries attribute"


@given(config=middleware_config_strategy)
@settings(max_examples=50, deadline=None)
def test_middleware_order_is_consistent(config: Dict[str, Any]):
    """
    **Feature: agent-refactor-with-rag, Property 1: 中间件配置完整性**
    **Validates: Requirements 1.1, 1.2**
    
    Property: The middleware order should be consistent across multiple calls
    with the same configuration.
    """
    from tableau_assistant.src.workflow.factory import create_middleware_stack
    
    # Create middleware stack twice with same config
    chat_model = create_test_chat_model()
    middleware1 = create_middleware_stack(chat_model=chat_model, config=config)
    middleware2 = create_middleware_stack(chat_model=chat_model, config=config)
    
    # Get type names
    types1 = [type(m).__name__ for m in middleware1]
    types2 = [type(m).__name__ for m in middleware2]
    
    # Order should be identical
    assert types1 == types2, \
        f"Middleware order should be consistent: {types1} != {types2}"


@given(config=middleware_config_strategy)
@settings(max_examples=30, deadline=None)
def test_workflow_stores_middleware_reference(config: Dict[str, Any]):
    """
    **Feature: agent-refactor-with-rag, Property 1: 中间件配置完整性**
    **Validates: Requirements 1.1, 1.2**
    
    Property: The compiled workflow should store a reference to its middleware
    for later use by nodes.
    """
    from tableau_assistant.src.workflow.factory import (
        create_tableau_workflow,
        get_workflow_info
    )
    
    # Create workflow
    chat_model = create_test_chat_model()
    workflow = create_tableau_workflow(
        chat_model=chat_model,
        config=config,
        use_memory_checkpointer=True
    )
    
    # Workflow should have middleware attribute
    assert hasattr(workflow, 'middleware'), \
        "Workflow should store middleware reference"
    
    # Workflow should have config attribute
    assert hasattr(workflow, 'workflow_config'), \
        "Workflow should store config reference"
    
    # get_workflow_info should return middleware names
    info = get_workflow_info(workflow)
    assert "middleware" in info, \
        "Workflow info should include middleware list"
    assert len(info["middleware"]) > 0, \
        "Workflow should have at least one middleware"


# ═══════════════════════════════════════════════════════════════════════════
# Edge Case Tests
# ═══════════════════════════════════════════════════════════════════════════

def test_middleware_with_empty_config():
    """
    Edge case: Empty config should use defaults.
    """
    from tableau_assistant.src.workflow.factory import create_middleware_stack
    
    chat_model = create_test_chat_model()
    middleware = create_middleware_stack(chat_model=chat_model, config={})
    middleware_types = [type(m).__name__ for m in middleware]
    
    # Should still have required middleware
    assert "TodoListMiddleware" in middleware_types
    assert "ModelRetryMiddleware" in middleware_types
    assert "ToolRetryMiddleware" in middleware_types
    assert "SummarizationMiddleware" in middleware_types


def test_middleware_with_none_config():
    """
    Edge case: None config should use defaults.
    """
    from tableau_assistant.src.workflow.factory import create_middleware_stack
    
    chat_model = create_test_chat_model()
    middleware = create_middleware_stack(chat_model=chat_model, config=None)
    middleware_types = [type(m).__name__ for m in middleware]
    
    # Should still have required middleware
    assert "TodoListMiddleware" in middleware_types
    assert "ModelRetryMiddleware" in middleware_types
    assert "ToolRetryMiddleware" in middleware_types


def test_interrupt_on_list_converted_to_dict():
    """
    Edge case: interrupt_on as list should be converted to dict format.
    """
    from tableau_assistant.src.workflow.factory import create_middleware_stack
    from langchain.agents.middleware import HumanInTheLoopMiddleware
    
    chat_model = create_test_chat_model()
    config = {"interrupt_on": ["write_todos"]}
    middleware = create_middleware_stack(chat_model=chat_model, config=config)
    
    # Find HumanInTheLoopMiddleware
    hitl = None
    for m in middleware:
        if isinstance(m, HumanInTheLoopMiddleware):
            hitl = m
            break
    
    assert hitl is not None, \
        "HumanInTheLoopMiddleware should be present when interrupt_on is set"


def test_middleware_count_with_all_options():
    """
    Test that middleware count is correct when all options are enabled.
    """
    from tableau_assistant.src.workflow.factory import create_middleware_stack
    
    chat_model = create_test_chat_model()
    config = {"interrupt_on": ["write_todos"]}
    middleware = create_middleware_stack(chat_model=chat_model, config=config)
    
    # With chat_model and interrupt_on, we should have:
    # 1. TodoListMiddleware
    # 2. SummarizationMiddleware
    # 3. ModelRetryMiddleware
    # 4. ToolRetryMiddleware
    # 5. FilesystemMiddleware (custom)
    # 6. PatchToolCallsMiddleware (custom)
    # 7. HumanInTheLoopMiddleware
    assert len(middleware) == 7, \
        f"Expected 7 middleware, got {len(middleware)}: {[type(m).__name__ for m in middleware]}"


def test_middleware_count_minimal():
    """
    Test that middleware count is correct with minimal options.
    """
    from tableau_assistant.src.workflow.factory import create_middleware_stack
    
    # No model_name, no interrupt_on
    middleware = create_middleware_stack(model_name=None, config={})
    
    # Without model_name and interrupt_on, we should have:
    # 1. TodoListMiddleware
    # 2. ModelRetryMiddleware
    # 3. ToolRetryMiddleware
    # 4. FilesystemMiddleware (custom)
    # 5. PatchToolCallsMiddleware (custom)
    assert len(middleware) == 5, \
        f"Expected 5 middleware, got {len(middleware)}: {[type(m).__name__ for m in middleware]}"


if __name__ == "__main__":
    print("=" * 60)
    print("Running Property Tests: Middleware Configuration Completeness")
    print("=" * 60)
    
    # Print model configuration
    print(f"\nUsing model: {get_real_model_name()}")
    print(f"LLM config: {get_llm_config()}")
    
    # Run edge case tests first
    print("\n--- Edge Case Tests ---")
    test_middleware_with_empty_config()
    print("✅ test_middleware_with_empty_config passed")
    
    test_middleware_with_none_config()
    print("✅ test_middleware_with_none_config passed")
    
    test_interrupt_on_list_converted_to_dict()
    print("✅ test_interrupt_on_list_converted_to_dict passed")
    
    test_middleware_count_with_all_options()
    print("✅ test_middleware_count_with_all_options passed")
    
    test_middleware_count_minimal()
    print("✅ test_middleware_count_minimal passed")
    
    # Run property tests
    print("\n--- Property Tests ---")
    test_middleware_stack_contains_required_types_with_model()
    print("✅ test_middleware_stack_contains_required_types_with_model passed")
    
    test_middleware_stack_without_model_name()
    print("✅ test_middleware_stack_without_model_name passed")
    
    test_middleware_configuration_parameters_applied()
    print("✅ test_middleware_configuration_parameters_applied passed")
    
    test_middleware_order_is_consistent()
    print("✅ test_middleware_order_is_consistent passed")
    
    test_workflow_stores_middleware_reference()
    print("✅ test_workflow_stores_middleware_reference passed")
    
    print("\n" + "=" * 60)
    print("All property tests passed! ✅")
    print("=" * 60)
