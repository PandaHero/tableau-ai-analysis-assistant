"""
Property-based tests for PatchToolCallsMiddleware.

**Feature: agent-refactor-with-rag, Property 19: 悬空工具调用修复**
**Validates: Requirements 13.1**

Tests that dangling tool calls (AIMessage with tool_calls but no corresponding
ToolMessage) are automatically patched with placeholder responses.
"""

import pytest
from hypothesis import given, settings, strategies as st, assume
from typing import Any
import uuid

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    ToolMessage,
    BaseMessage,
)

from tableau_assistant.src.middleware.patch_tool_calls import (
    PatchToolCallsMiddleware,
    find_dangling_tool_calls,
    count_dangling_tool_calls,
)


# ═══════════════════════════════════════════════════════════════════════════
# Test Strategies
# ═══════════════════════════════════════════════════════════════════════════

# Strategy for tool names
tool_name_strategy = st.from_regex(r'[a-z_][a-z0-9_]{2,20}', fullmatch=True)

# Strategy for tool call IDs
tool_call_id_strategy = st.from_regex(r'call_[a-zA-Z0-9]{8,24}', fullmatch=True)

# Strategy for message content
content_strategy = st.text(min_size=1, max_size=200)


@st.composite
def tool_call_strategy(draw, unique_id: str = None):
    """Generate a tool call dict."""
    # Use provided unique_id or generate one
    tc_id = unique_id if unique_id else draw(tool_call_id_strategy)
    return {
        "id": tc_id,
        "name": draw(tool_name_strategy),
        "args": {"arg1": draw(st.text(min_size=0, max_size=50))},
    }


@st.composite
def ai_message_with_tool_calls_strategy(draw, num_calls: int = None):
    """Generate an AIMessage with tool calls (unique IDs guaranteed)."""
    if num_calls is None:
        num_calls = draw(st.integers(min_value=1, max_value=5))
    
    # Generate unique IDs for each tool call
    tool_calls = []
    for i in range(num_calls):
        unique_id = f"call_{uuid.uuid4().hex[:16]}"
        tc = draw(tool_call_strategy(unique_id=unique_id))
        tool_calls.append(tc)
    
    content = draw(content_strategy)
    
    return AIMessage(content=content, tool_calls=tool_calls)


@st.composite
def tool_message_strategy(draw, tool_call_id: str = None, tool_name: str = None):
    """Generate a ToolMessage."""
    if tool_call_id is None:
        tool_call_id = draw(tool_call_id_strategy)
    if tool_name is None:
        tool_name = draw(tool_name_strategy)
    
    content = draw(content_strategy)
    return ToolMessage(content=content, tool_call_id=tool_call_id, name=tool_name)


@st.composite
def message_sequence_with_dangling_strategy(draw):
    """Generate a message sequence with at least one dangling tool call."""
    # Generate an AIMessage with tool calls
    ai_msg = draw(ai_message_with_tool_calls_strategy())
    num_tool_calls = len(ai_msg.tool_calls)
    
    # Decide how many tool calls to leave dangling (at least 1)
    num_dangling = draw(st.integers(min_value=1, max_value=num_tool_calls))
    num_with_results = num_tool_calls - num_dangling
    
    # Create ToolMessages for some (but not all) tool calls
    messages: list[BaseMessage] = [
        HumanMessage(content=draw(content_strategy)),
        ai_msg,
    ]
    
    # Add ToolMessages for the first num_with_results tool calls
    for i in range(num_with_results):
        tc = ai_msg.tool_calls[i]
        messages.append(ToolMessage(
            content=draw(content_strategy),
            tool_call_id=tc["id"],
            name=tc["name"],
        ))
    
    # Optionally add more messages after
    if draw(st.booleans()):
        messages.append(HumanMessage(content=draw(content_strategy)))
    
    return messages, num_dangling


@st.composite
def message_sequence_complete_strategy(draw):
    """Generate a message sequence with NO dangling tool calls."""
    # Generate an AIMessage with tool calls
    ai_msg = draw(ai_message_with_tool_calls_strategy())
    
    messages: list[BaseMessage] = [
        HumanMessage(content=draw(content_strategy)),
        ai_msg,
    ]
    
    # Add ToolMessages for ALL tool calls
    for tc in ai_msg.tool_calls:
        messages.append(ToolMessage(
            content=draw(content_strategy),
            tool_call_id=tc["id"],
            name=tc["name"],
        ))
    
    return messages


# ═══════════════════════════════════════════════════════════════════════════
# Property Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestPatchToolCallsMiddlewareDanglingFix:
    """
    **Feature: agent-refactor-with-rag, Property 19: 悬空工具调用修复**
    **Validates: Requirements 13.1**
    
    Property: For any message sequence with dangling tool calls,
    PatchToolCallsMiddleware should add placeholder ToolMessages.
    """
    
    @given(data=message_sequence_with_dangling_strategy())
    @settings(max_examples=50, deadline=None)
    def test_dangling_tool_calls_are_patched(self, data):
        """
        **Feature: agent-refactor-with-rag, Property 19: 悬空工具调用修复**
        **Validates: Requirements 13.1**
        
        Property: All dangling tool calls get placeholder ToolMessages.
        """
        messages, expected_dangling = data
        
        # Arrange
        middleware = PatchToolCallsMiddleware()
        
        # Act
        patched = middleware._patch_messages_inline(messages)
        
        # Assert
        # After patching, there should be no dangling tool calls
        dangling_after = find_dangling_tool_calls(patched)
        assert len(dangling_after) == 0, \
            f"Expected 0 dangling calls after patch, got {len(dangling_after)}"
        
        # The patched list should have more messages than original
        assert len(patched) == len(messages) + expected_dangling, \
            f"Expected {len(messages) + expected_dangling} messages, got {len(patched)}"
    
    @given(messages=message_sequence_complete_strategy())
    @settings(max_examples=30, deadline=None)
    def test_complete_sequences_unchanged(self, messages):
        """
        **Feature: agent-refactor-with-rag, Property 19: 悬空工具调用修复**
        **Validates: Requirements 13.1**
        
        Property: Message sequences with no dangling calls are unchanged.
        """
        # Arrange
        middleware = PatchToolCallsMiddleware()
        
        # Act
        patched = middleware._patch_messages_inline(messages)
        
        # Assert
        assert len(patched) == len(messages), \
            "Complete sequences should not be modified"
        
        # Verify no dangling calls before or after
        assert count_dangling_tool_calls(messages) == 0
        assert count_dangling_tool_calls(patched) == 0
    
    @given(data=message_sequence_with_dangling_strategy())
    @settings(max_examples=30, deadline=None)
    def test_patch_messages_inserted_after_ai_message(self, data):
        """
        **Feature: agent-refactor-with-rag, Property 19: 悬空工具调用修复**
        **Validates: Requirements 13.1**
        
        Property: Patch ToolMessages are inserted immediately after the AIMessage.
        """
        messages, _ = data
        
        # Arrange
        middleware = PatchToolCallsMiddleware()
        
        # Act
        patched = middleware._patch_messages_inline(messages)
        
        # Assert
        # Find the AIMessage with tool calls
        ai_msg_idx = None
        for i, msg in enumerate(patched):
            if msg.type == "ai" and hasattr(msg, 'tool_calls') and msg.tool_calls:
                ai_msg_idx = i
                break
        
        assert ai_msg_idx is not None, "Should have AIMessage with tool calls"
        
        # All ToolMessages for this AIMessage should come after it
        ai_msg = patched[ai_msg_idx]
        for tc in ai_msg.tool_calls:
            tc_id = tc.get("id")
            # Find the corresponding ToolMessage
            tool_msg_idx = None
            for j, msg in enumerate(patched):
                if msg.type == "tool" and hasattr(msg, 'tool_call_id') and msg.tool_call_id == tc_id:
                    tool_msg_idx = j
                    break
            
            assert tool_msg_idx is not None, f"Should have ToolMessage for {tc_id}"
            assert tool_msg_idx > ai_msg_idx, \
                f"ToolMessage should come after AIMessage"


class TestPatchToolCallsMiddlewareErrorMessage:
    """Tests for error message formatting."""
    
    def test_default_error_message_format(self):
        """Default error message should contain tool name and ID."""
        # Arrange
        middleware = PatchToolCallsMiddleware()
        
        # Act
        error_msg = middleware._format_error_message("test_tool", "call_123")
        
        # Assert
        assert "test_tool" in error_msg
        assert "call_123" in error_msg
    
    def test_custom_error_message(self):
        """Custom error message should be used."""
        # Arrange
        custom_msg = "Custom error: {tool_name} ({tool_call_id})"
        middleware = PatchToolCallsMiddleware(error_message=custom_msg)
        
        # Act
        error_msg = middleware._format_error_message("my_tool", "call_456")
        
        # Assert
        assert error_msg == "Custom error: my_tool (call_456)"


class TestPatchToolCallsMiddlewareUtilityFunctions:
    """Tests for utility functions."""
    
    @given(data=message_sequence_with_dangling_strategy())
    @settings(max_examples=20, deadline=None)
    def test_find_dangling_tool_calls_returns_correct_count(self, data):
        """find_dangling_tool_calls should return correct tool calls."""
        messages, expected_dangling = data
        
        # Act
        dangling = find_dangling_tool_calls(messages)
        
        # Assert
        assert len(dangling) == expected_dangling
    
    @given(data=message_sequence_with_dangling_strategy())
    @settings(max_examples=20, deadline=None)
    def test_count_dangling_tool_calls_matches_find(self, data):
        """count_dangling_tool_calls should match len(find_dangling_tool_calls)."""
        messages, _ = data
        
        # Act
        count = count_dangling_tool_calls(messages)
        found = find_dangling_tool_calls(messages)
        
        # Assert
        assert count == len(found)
    
    def test_empty_messages_no_dangling(self):
        """Empty message list should have no dangling calls."""
        assert find_dangling_tool_calls([]) == []
        assert count_dangling_tool_calls([]) == 0


class TestPatchToolCallsMiddlewareEdgeCases:
    """Edge case tests."""
    
    def test_ai_message_without_tool_calls(self):
        """AIMessage without tool_calls should not cause issues."""
        # Arrange
        middleware = PatchToolCallsMiddleware()
        messages = [
            HumanMessage(content="Hello"),
            AIMessage(content="Hi there!"),  # No tool_calls
        ]
        
        # Act
        patched = middleware._patch_messages_inline(messages)
        
        # Assert
        assert len(patched) == len(messages)
    
    def test_multiple_ai_messages_with_tool_calls(self):
        """Multiple AIMessages with tool calls should all be handled."""
        # Arrange
        middleware = PatchToolCallsMiddleware()
        
        ai_msg1 = AIMessage(content="First", tool_calls=[
            {"id": "call_1", "name": "tool_a", "args": {}},
        ])
        ai_msg2 = AIMessage(content="Second", tool_calls=[
            {"id": "call_2", "name": "tool_b", "args": {}},
        ])
        
        messages = [
            HumanMessage(content="Start"),
            ai_msg1,
            # No ToolMessage for call_1
            HumanMessage(content="Continue"),
            ai_msg2,
            # No ToolMessage for call_2
        ]
        
        # Act
        patched = middleware._patch_messages_inline(messages)
        
        # Assert
        assert count_dangling_tool_calls(patched) == 0
        # Should have 2 extra messages (one for each dangling call)
        assert len(patched) == len(messages) + 2
    
    def test_tool_message_before_ai_message(self):
        """ToolMessage appearing before AIMessage should not match."""
        # Arrange
        middleware = PatchToolCallsMiddleware()
        
        # This is an unusual but valid scenario
        messages = [
            ToolMessage(content="Orphan", tool_call_id="call_orphan", name="orphan_tool"),
            HumanMessage(content="Hello"),
            AIMessage(content="Response", tool_calls=[
                {"id": "call_new", "name": "new_tool", "args": {}},
            ]),
        ]
        
        # Act
        patched = middleware._patch_messages_inline(messages)
        
        # Assert
        # call_new should be patched (no ToolMessage after it)
        assert count_dangling_tool_calls(patched) == 0
        assert len(patched) == len(messages) + 1
