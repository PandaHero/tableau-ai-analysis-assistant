"""Step 1 Component - Semantic understanding and question restatement.

Step 1 is the "Intuition" phase of the LLM combination architecture.

For deep thinking models (DeepSeek R1):
- Model has built-in thinking capability, outputs thinking process in <think>...</think> tags
- Thinking process is automatically extracted to AIMessage.additional_kwargs["thinking"]
- call_llm_with_tools returns complete AIMessage

Uses call_llm_with_tools pattern:
- call_llm_with_tools(): supports tool calls + middleware + streaming
- parse_json_response(): parses JSON response
- Does not use with_structured_output (unreliable for some models)

Key points:
- call_llm_with_tools(streaming=True) enables token streaming for frontend
- Middleware (from config) supports retry, summarization, etc.
- Currently no tools needed

Error handling:
- This component does NOT handle errors internally
- All errors (Pydantic or semantic) are propagated to the Agent
- Agent routes errors to Observer for correction
- ValidationError carries original LLM output for Observer to analyze
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from ....core.models import Step1Output
from ....core.models.data_model import DataModel
from ....core.exceptions import ValidationError
from ..prompts.step1 import STEP1_PROMPT
from tableau_assistant.src.agents.base import (
    get_llm,
    call_llm_with_tools,
    parse_json_response,
)

logger = logging.getLogger(__name__)


class Step1Component:
    """Step 1: Semantic understanding and question restatement.
    
    Responsibilities:
    - Understand user question
    - Merge with conversation history
    - Extract What/Where/How structure
    - Classify intent
    - Generate complete restatement
    
    Error Handling:
    - This component does NOT handle errors internally
    - All errors are propagated to the Agent for Observer-based correction
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
            self._llm = get_llm(agent_name="semantic_parser")
        return self._llm
    
    async def execute(
        self,
        question: str,
        history: list[dict[str, str]] | None = None,
        data_model: DataModel | None = None,
        state: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Step1Output, str]:
        """Execute Step 1: Semantic understanding and question restatement.
        
        Args:
            question: Current user question
            history: Conversation history (list of {"role": "user/assistant", "content": "..."})
            data_model: Data source model (DataModel object with fields, tables, relationships)
            state: Current workflow state (for middleware)
            config: LangGraph RunnableConfig (contains middleware)
            
        Returns:
            Tuple of (Step1Output, thinking_process)
            - Step1Output: restated_question, what, where, how_type, intent
            - thinking_process: R1 model's thinking process (if available)
            
        Raises:
            ValueError: When Pydantic validation fails (handled by Agent via Observer)
        """
        # Format history for prompt
        history_str = self._format_history(history)
        
        # Format data model for prompt
        data_model_str = self._format_data_model(data_model)
        
        # Get current time for date-related questions
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Use STEP1_PROMPT to format messages (auto-injects JSON Schema)
        messages = STEP1_PROMPT.format_messages(
            question=question,
            history=history_str,
            data_model=data_model_str,
            current_time=current_time,
        )
        
        # Get middleware from config
        middleware = None
        if config and "configurable" in config:
            middleware = config["configurable"].get("middleware")
        
        llm = self._get_llm()
        
        # Call LLM
        response = await call_llm_with_tools(
            llm=llm,
            messages=messages,
            tools=[],
            streaming=True,
            middleware=middleware,
            state=state or {},
            config=config,
        )
        
        # Extract thinking process (R1 model specific)
        thinking = response.additional_kwargs.get("thinking", "")
        
        # Parse and validate JSON response
        # If validation fails, wrap in ValidationError with original output
        try:
            result = parse_json_response(response.content, Step1Output)
        except ValueError as e:
            # Wrap error with original output for Observer
            raise ValidationError(
                message=str(e),
                original_output=response.content,
                step="step1",
            ) from e
        
        return result, thinking
    
    def _format_history(self, history: list[dict[str, str]] | None) -> str:
        """Format conversation history for prompt.
        
        Note: History message count is NOT limited here.
        History management is handled by SummarizationMiddleware:
        - Auto-summarize when token count exceeds threshold
        - Keep recent N messages (configured by messages_to_keep)
        """
        if not history:
            return "(No previous conversation)"
        
        formatted = []
        for msg in history:  # No limit, managed by SummarizationMiddleware
            role = msg.get("role", "user")
            content = msg.get("content", "")
            formatted.append(f"[{role}]: {content}")
        
        return "\n".join(formatted)
    
    def _format_data_model(self, data_model: DataModel | None) -> str:
        """Format data model for prompt.
        
        Args:
            data_model: DataModel object containing fields, tables, relationships
            
        Returns:
            Formatted string describing available fields for LLM reference
        """
        if not data_model:
            return "(No data model available)"
        
        if not data_model.fields:
            return "(No fields available)"
        
        result = []
        
        # Add data source info
        result.append(f"Data Source: {data_model.datasource_name}")
        
        # For multi-table data model, show table structure
        if data_model.is_multi_table:
            result.append(f"Tables: {len(data_model.logical_tables)}")
            for table in data_model.logical_tables:
                table_fields = data_model.get_fields_by_table(table.logicalTableId)
                dims = [f.fieldCaption or f.name for f in table_fields if f.role == "dimension"]
                meas = [f.fieldCaption or f.name for f in table_fields if f.role == "measure"]
                result.append(f"  [{table.caption}]")
                if dims:
                    result.append(f"    Dimensions: {', '.join(dims)}")
                if meas:
                    result.append(f"    Measures: {', '.join(meas)}")
        else:
            # Single table: just list dimensions and measures
            dimensions = [f.fieldCaption or f.name for f in data_model.get_dimensions()]
            measures = [f.fieldCaption or f.name for f in data_model.get_measures()]
            
            if dimensions:
                result.append(f"Dimensions: {', '.join(dimensions)}")
            if measures:
                result.append(f"Measures: {', '.join(measures)}")
        
        return "\n".join(result) if result else "(No fields available)"
