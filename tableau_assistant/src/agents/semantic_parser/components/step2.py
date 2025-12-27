"""Step 2 Component - Computation reasoning and LLM self-validation.

Step 2 is the "Reasoning" phase of the LLM combination architecture.

IMPORTANT: validation is filled by LLM, not computed by code.
The component does NOT do additional validation - it trusts LLM's self-validation.

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

Architecture:
- Step2Component: Pure business logic, no VizQLState knowledge
- step2_node: State orchestration, defined in node.py to properly import VizQLState
- This separation avoids circular imports (core/state.py imports from agents/semantic_parser/models/)
"""

import logging
from typing import Any, Dict, Optional

from ..models import Step1Output, Step2Output
from ....core.exceptions import ValidationError
from ..prompts.step2 import STEP2_PROMPT
from tableau_assistant.src.agents.base import (
    get_llm,
    call_llm_with_tools,
    parse_json_response,
)

logger = logging.getLogger(__name__)


class Step2Component:
    """Step 2: Computation reasoning and LLM self-validation.
    
    Responsibilities:
    - Infer computation from restated_question
    - Self-validate against Step 1 output
    - Report inconsistencies
    
    NOTE: validation is done by LLM itself, not by this component.
    """
    
    def __init__(self, llm=None):
        """Initialize Step 2 component.
        
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
        step1_output: Step1Output,
        state: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None,
        error_feedback: Optional[str] = None,
    ) -> Step2Output:
        """Execute Step 2: Computation reasoning and self-validation.
        
        Only called when step1_output.how_type != SIMPLE.
        
        Args:
            step1_output: Output from Step 1
            state: Current workflow state (for middleware)
            config: LangGraph RunnableConfig (contains middleware)
            error_feedback: Feedback from previous error (for retry)
            
        Returns:
            Step2Output with computations, reasoning, and LLM self-validation
        """
        # Extract measures and dimensions for validation reference
        measures = [m.field_name for m in step1_output.what.measures]
        dimensions = [d.field_name for d in step1_output.where.dimensions]
        
        # Build restated question with error feedback if present
        restated_question = step1_output.restated_question
        if error_feedback:
            restated_question = f"{restated_question}\n\n[系统提示：上次计算推理出现问题，请注意：{error_feedback}]"
            logger.info(f"Step 2 retry with feedback: {error_feedback[:100]}...")
        
        # Use STEP2_PROMPT to format messages (auto-injects JSON Schema)
        messages = STEP2_PROMPT.format_messages(
            restated_question=restated_question,
            measures=measures,
            dimensions=dimensions,
            how_type=step1_output.how_type.value,
        )
        
        # Get middleware from config
        middleware = None
        if config and "configurable" in config:
            middleware = config["configurable"].get("middleware")
        
        # Call LLM using call_llm_with_tools (supports middleware + streaming)
        llm = self._get_llm()
        response = await call_llm_with_tools(
            llm=llm,
            messages=messages,
            tools=[],  # No tools needed
            streaming=True,
            middleware=middleware,
            state=state or {},
            config=config,
        )
        
        # Parse JSON response from AIMessage.content
        # If validation fails, wrap in ValidationError with original output
        try:
            result = parse_json_response(response.content, Step2Output)
        except ValueError as e:
            # Wrap error with original output for Observer
            raise ValidationError(
                message=str(e),
                original_output=response.content,
                step="step2",
            ) from e
        
        return result
