"""Step 1 Component - Semantic understanding and question restatement.

Step 1 is the "Intuition" phase of the LLM combination architecture.
"""

import logging
from typing import Any

from ....core.models import Step1Output
from ..prompts.step1 import STEP1_PROMPT

logger = logging.getLogger(__name__)


class Step1Component:
    """Step 1: Semantic understanding and question restatement.
    
    Responsibilities:
    - Understand user question
    - Merge with conversation history
    - Extract What/Where/How structure
    - Classify intent
    - Generate complete restatement
    """
    
    def __init__(self, llm=None):
        """Initialize Step 1 component.
        
        Args:
            llm: LangChain LLM instance (lazy loaded if None)
        """
        self._llm = llm
    
    def _get_llm(self):
        """Get or create LLM instance."""
        if self._llm is None:
            from tableau_assistant.src.agents.base import get_llm
            self._llm = get_llm(agent_name="semantic_parser")
        return self._llm
    
    async def execute(
        self,
        question: str,
        history: list[dict[str, str]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Step1Output:
        """Execute Step 1: Semantic understanding and question restatement.
        
        Args:
            question: Current user question
            history: Conversation history (list of {"role": "user/assistant", "content": "..."})
            metadata: Data source metadata (available fields, etc.)
            
        Returns:
            Step1Output with restated_question, what, where, how_type, intent
        """
        # Format history for prompt
        history_str = self._format_history(history)
        
        # Format metadata for prompt
        metadata_str = self._format_metadata(metadata)
        
        # Use STEP1_PROMPT to format messages (auto-injects JSON Schema)
        messages = STEP1_PROMPT.format_messages(
            question=question,
            history=history_str,
            metadata=metadata_str,
        )
        
        # Call LLM with structured output
        llm = self._get_llm()
        if hasattr(llm, 'with_structured_output'):
            structured_llm = llm.with_structured_output(Step1Output)
            result = await structured_llm.ainvoke(messages)
        else:
            # Fallback: parse JSON from response
            from tableau_assistant.src.agents.base import invoke_llm, parse_json_response
            response = await invoke_llm(llm, messages)
            result = parse_json_response(response, Step1Output)
        
        return result
    
    def _format_history(self, history: list[dict[str, str]] | None) -> str:
        """Format conversation history for prompt."""
        if not history:
            return "(No previous conversation)"
        
        formatted = []
        for msg in history[-5:]:  # Keep last 5 messages
            role = msg.get("role", "user")
            content = msg.get("content", "")
            formatted.append(f"[{role}]: {content}")
        
        return "\n".join(formatted)
    
    def _format_metadata(self, metadata: dict[str, Any] | None) -> str:
        """Format metadata for prompt."""
        if not metadata:
            return "(No metadata available)"
        
        # Extract field information
        fields = metadata.get("fields", [])
        if not fields:
            return "(No fields available)"
        
        # Format as simple list - check both 'role' and 'type' for compatibility
        dimensions = [
            f.get("name") or f.get("fieldCaption", "")
            for f in fields 
            if (f.get("role", "").upper() == "DIMENSION" or f.get("type") == "dimension")
        ]
        measures = [
            f.get("name") or f.get("fieldCaption", "")
            for f in fields 
            if (f.get("role", "").upper() == "MEASURE" or f.get("type") == "measure")
        ]
        
        result = []
        if dimensions:
            result.append(f"维度字段: {', '.join(dimensions[:20])}")  # Limit to 20
        if measures:
            result.append(f"度量字段: {', '.join(measures[:20])}")
        
        return "\n".join(result) if result else "(No fields available)"
