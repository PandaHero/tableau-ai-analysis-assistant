"""
PatchToolCallsMiddleware: Middleware for fixing dangling tool calls.

This middleware detects and fixes "dangling" tool calls - situations where
an LLM generates a tool_call but there's no corresponding tool_result in
the message history. This can happen due to:
1. Interrupted execution
2. Tool execution errors that weren't properly handled
3. Streaming issues
4. User interruption (new message before tool completion)

The middleware automatically patches these by inserting placeholder ToolMessages
immediately after the AIMessage containing the dangling tool call, maintaining
proper message ordering for LLM context.

Based on deepagents PatchToolCallsMiddleware design, adapted for production use.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware.types import (
    AgentMiddleware,
    AgentState,
    ModelRequest,
    ModelResponse,
)
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    ToolMessage,
)
from langgraph.runtime import Runtime
from langgraph.types import Overwrite


# Default error message for dangling tool calls
DANGLING_TOOL_CALL_ERROR = (
    "Tool call {tool_name} with id {tool_call_id} was cancelled - "
    "another message came in before it could be completed."
)


class PatchToolCallsMiddleware(AgentMiddleware):
    """Middleware for fixing dangling tool calls in message history.
    
    This middleware ensures message history consistency by detecting tool_calls
    in AIMessages that don't have corresponding ToolMessages, and automatically
    inserting placeholder error responses immediately after the AIMessage.
    
    Problem scenarios:
    - LLM generates a tool_call, but execution was interrupted
    - Tool execution failed without proper error handling
    - Streaming issues caused incomplete message history
    - User sent a new message before tool execution completed
    
    Solution:
    - Before each agent run, scan message history for dangling tool_calls
    - Insert placeholder ToolMessages immediately after the AIMessage containing them
    - Use Overwrite to replace the entire message list atomically
    - This prevents API errors and maintains conversation consistency
    
    Key differences from simple append approach:
    - Inserts patch messages in correct position (after AIMessage, not at end)
    - Uses Overwrite for atomic state update
    - Handles multiple dangling calls from same AIMessage
    
    Example:
        ```python
        from tableau_assistant.src.orchestration.middleware.patch_tool_calls import PatchToolCallsMiddleware
        
        middleware = PatchToolCallsMiddleware()
        
        # Use with agent
        agent = create_agent(
            model="gpt-4",
            middleware=[middleware],
        )
        ```
    
    Message ordering example:
        Before: [HumanMessage, AIMessage(tool_calls=[tc1, tc2]), HumanMessage]
        After:  [HumanMessage, AIMessage(tool_calls=[tc1, tc2]), 
                 ToolMessage(tc1, cancelled), ToolMessage(tc2, cancelled), HumanMessage]
    """
    
    def __init__(self, error_message: str | None = None) -> None:
        """Initialize the middleware.
        
        Args:
            error_message: Custom error message template for dangling tool calls.
                Can use {tool_name} and {tool_call_id} placeholders.
                Defaults to a standard cancellation message.
        """
        self.error_message = error_message or DANGLING_TOOL_CALL_ERROR
    
    def _format_error_message(self, tool_name: str, tool_call_id: str) -> str:
        """Format the error message with tool details.
        
        Args:
            tool_name: Name of the tool that was called
            tool_call_id: ID of the tool call
        
        Returns:
            Formatted error message
        """
        return self.error_message.format(
            tool_name=tool_name,
            tool_call_id=tool_call_id,
        )
    
    def _patch_messages_inline(
        self,
        messages: list[BaseMessage]
    ) -> list[BaseMessage]:
        """Patch message history by inserting missing tool results inline.
        
        This method iterates through messages and inserts placeholder ToolMessages
        immediately after any AIMessage with tool_calls that don't have
        corresponding ToolMessages later in the history.
        
        Args:
            messages: Original message list
        
        Returns:
            Patched message list with placeholder ToolMessages inserted
            in the correct positions
        """
        if not messages:
            return messages
        
        patched_messages: list[BaseMessage] = []
        
        for i, msg in enumerate(messages):
            patched_messages.append(msg)
            
            # Check if this is an AIMessage with tool_calls
            if msg.type == "ai" and hasattr(msg, 'tool_calls') and msg.tool_calls:
                # For each tool call, check if there's a corresponding ToolMessage
                for tool_call in msg.tool_calls:
                    tc_id = tool_call.get('id') or tool_call.get('tool_call_id')
                    if not tc_id:
                        continue
                    
                    # Look for corresponding ToolMessage in remaining messages
                    has_result = any(
                        m.type == "tool" and 
                        hasattr(m, 'tool_call_id') and 
                        m.tool_call_id == tc_id
                        for m in messages[i + 1:]
                    )
                    
                    if not has_result:
                        # Create placeholder ToolMessage
                        tool_name = tool_call.get('name', 'unknown')
                        error_content = self._format_error_message(tool_name, tc_id)
                        
                        patched_messages.append(ToolMessage(
                            content=error_content,
                            name=tool_name,
                            tool_call_id=tc_id,
                        ))
        
        return patched_messages
    
    def before_agent(
        self,
        state: AgentState,
        runtime: Runtime[Any],  # noqa: ARG002
    ) -> dict[str, Any] | None:
        """Before the agent runs, handle dangling tool calls from any AIMessage.
        
        This hook is called before each agent execution and patches the message
        history if any dangling tool calls are found.
        
        Args:
            state: Current agent state containing messages
            runtime: LangGraph runtime (unused but required by protocol)
        
        Returns:
            State update dict with Overwrite for messages, or None if no changes
        """
        messages = state.get("messages", [])
        if not messages:
            return None
        
        patched_messages = self._patch_messages_inline(messages)
        
        # Only return update if messages were actually patched
        if len(patched_messages) == len(messages):
            return None
        
        return {"messages": Overwrite(patched_messages)}
    
    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        """Patch dangling tool calls before model call.
        
        This is a fallback for cases where before_agent isn't called.
        The primary patching happens in before_agent.
        
        Args:
            request: The model request being processed.
            handler: The handler function to call with the modified request.
        
        Returns:
            The model response from the handler.
        """
        patched_messages = self._patch_messages_inline(request.messages)
        
        if len(patched_messages) != len(request.messages):
            request = request.override(messages=patched_messages)
        
        return handler(request)
    
    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        """(async) Patch dangling tool calls before model call.
        
        This is a fallback for cases where before_agent isn't called.
        The primary patching happens in before_agent.
        
        Args:
            request: The model request being processed.
            handler: The handler function to call with the modified request.
        
        Returns:
            The model response from the handler.
        """
        patched_messages = self._patch_messages_inline(request.messages)
        
        if len(patched_messages) != len(request.messages):
            request = request.override(messages=patched_messages)
        
        return await handler(request)


def find_dangling_tool_calls(messages: list[BaseMessage]) -> list[dict[str, Any]]:
    """Utility function to find dangling tool calls in a message list.
    
    This can be used for debugging, monitoring, or testing purposes.
    
    Args:
        messages: List of messages to scan
    
    Returns:
        List of tool_call dicts that don't have corresponding results.
        Each dict contains 'id', 'name', and 'args' keys.
    
    Example:
        ```python
        from tableau_assistant.src.orchestration.middleware.patch_tool_calls import find_dangling_tool_calls
        
        dangling = find_dangling_tool_calls(messages)
        for tc in dangling:
            print(f"Dangling: {tc['name']} (id={tc['id']})")
        ```
    """
    if not messages:
        return []
    
    # Collect all tool_call_ids that have results
    result_ids: set[str] = set()
    for msg in messages:
        if msg.type == "tool" and hasattr(msg, 'tool_call_id'):
            result_ids.add(msg.tool_call_id)
    
    # Find tool calls without results
    dangling: list[dict[str, Any]] = []
    for msg in messages:
        if msg.type == "ai" and hasattr(msg, 'tool_calls') and msg.tool_calls:
            for tc in msg.tool_calls:
                tc_id = tc.get('id') or tc.get('tool_call_id')
                if tc_id and tc_id not in result_ids:
                    dangling.append(tc)
    
    return dangling


def count_dangling_tool_calls(messages: list[BaseMessage]) -> int:
    """Count the number of dangling tool calls in a message list.
    
    Args:
        messages: List of messages to scan
    
    Returns:
        Number of tool calls without corresponding results
    """
    return len(find_dangling_tool_calls(messages))
