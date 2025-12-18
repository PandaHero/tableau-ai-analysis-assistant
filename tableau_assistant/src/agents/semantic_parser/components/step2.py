"""Step 2 Component - Computation reasoning and LLM self-validation.

Step 2 is the "Reasoning" phase of the LLM combination architecture.

IMPORTANT: validation is filled by LLM, not computed by code.
The component does NOT do additional validation - it trusts LLM's self-validation.
"""

import logging
from typing import Any

from ....core.models import Step1Output, Step2Output
from ..prompts.step2 import STEP2_PROMPT

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
            from tableau_assistant.src.agents.base import get_llm
            self._llm = get_llm(agent_name="semantic_parser")
        return self._llm
    
    async def execute(self, step1_output: Step1Output) -> Step2Output:
        """Execute Step 2: Computation reasoning and self-validation.
        
        Only called when step1_output.how_type != SIMPLE.
        
        Args:
            step1_output: Output from Step 1
            
        Returns:
            Step2Output with computations, reasoning, and LLM self-validation
        """
        # Extract measures and dimensions for validation reference
        measures = [m.field for m in step1_output.what.measures]
        dimensions = [d.field for d in step1_output.where.dimensions]
        
        # Use STEP2_PROMPT to format messages (auto-injects JSON Schema)
        messages = STEP2_PROMPT.format_messages(
            restated_question=step1_output.restated_question,
            measures=measures,
            dimensions=dimensions,
            how_type=step1_output.how_type.value,
        )
        
        # Call LLM with structured output
        # LLM will fill in validation fields itself
        llm = self._get_llm()
        if hasattr(llm, 'with_structured_output'):
            structured_llm = llm.with_structured_output(Step2Output)
            result = await structured_llm.ainvoke(messages)
        else:
            # Fallback: parse JSON from response
            from tableau_assistant.src.agents.base import invoke_llm, parse_json_response
            response = await invoke_llm(llm, messages)
            result = parse_json_response(response, Step2Output)
        
        # NOTE: We do NOT do additional validation here.
        # The validation field is filled by LLM's self-validation.
        # If validation.all_valid == False, Observer will be triggered.
        
        return result
