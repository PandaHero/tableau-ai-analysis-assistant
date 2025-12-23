"""Observer Component - Validation and correction (Metacognition).

Observer is the "Metacognition" phase of the LLM combination architecture.
It handles two scenarios:
1. Step 1 validation failed - correct filter issues (missing dates, etc.)
2. Step 2 validation failed - check consistency between Step 1 and Step 2

Uses call_llm_with_tools pattern (consistent with Step1/Step2):
- call_llm_with_tools(): supports tool calls + middleware + streaming
- parse_json_response(): parses JSON response
- Does not use with_structured_output (unreliable for some models)
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from ....core.models import ObserverOutput, Step1Output, Step2Output
from ..prompts.observer import STEP1_OBSERVER_PROMPT, STEP2_OBSERVER_PROMPT
from tableau_assistant.src.agents.base import (
    get_llm,
    call_llm_with_tools,
    parse_json_response,
)

logger = logging.getLogger(__name__)


class ObserverComponent:
    """Observer: Validation and correction.
    
    Responsibilities:
    - For Step 1 failures: Correct filter issues (missing dates, values, etc.)
    - For Step 2 failures: Check consistency between Step 1 and Step 2
    - Make decision (ACCEPT / CORRECT / RETRY / CLARIFY)
    
    Triggered when:
    - step1.validation.all_valid == False
    - step2.validation.all_valid == False
    """
    
    def __init__(self, llm=None):
        """Initialize Observer component.
        
        Args:
            llm: LangChain LLM instance (lazy loaded if None)
        """
        self._llm = llm
    
    def _get_llm(self):
        """Get or create LLM instance."""
        if self._llm is None:
            self._llm = get_llm(agent_name="semantic_parser")
        return self._llm
    
    async def execute_for_step1(
        self,
        original_question: str,
        step1_output: Step1Output,
        current_time: str | None = None,
        state: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> ObserverOutput:
        """Execute Observer for Step 1 validation failures.
        
        Called when step1_output.validation.all_valid == False.
        
        Args:
            original_question: Original user question
            step1_output: Output from Step 1 with validation failures
            current_time: Current time string for date calculation
            state: Current workflow state (for middleware)
            config: LangGraph RunnableConfig (contains middleware)
            
        Returns:
            ObserverOutput with corrected filters
        """
        if current_time is None:
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Format filters for prompt
        filters_str = str([
            {
                "field": f.field,
                "type": f.type.value,
                "values": f.values,
                "start_date": f.start_date,
                "end_date": f.end_date,
                "n": f.n,
                "by_field": f.by_field,
                "direction": f.direction.value if f.direction else None,
            }
            for f in step1_output.where.filters
        ])
        
        # Format validation for prompt
        validation = step1_output.validation
        filter_checks_str = str([
            {
                "filter_field": fc.filter_field,
                "filter_type": fc.filter_type.value,
                "is_complete": fc.is_complete,
                "missing_fields": fc.missing_fields,
                "note": fc.note,
            }
            for fc in validation.filter_checks
        ])
        
        # Use STEP1_OBSERVER_PROMPT to format messages
        messages = STEP1_OBSERVER_PROMPT.format_messages(
            original_question=original_question,
            current_time=current_time,
            restated_question=step1_output.restated_question,
            filters=filters_str,
            all_valid=validation.all_valid,
            issues=validation.issues,
            filter_checks=filter_checks_str,
        )
        
        # Get middleware from config
        middleware = None
        if config and "configurable" in config:
            middleware = config["configurable"].get("middleware")
        
        # Call LLM
        llm = self._get_llm()
        response = await call_llm_with_tools(
            llm=llm,
            messages=messages,
            tools=[],
            streaming=True,
            middleware=middleware,
            state=state or {},
            config=config,
        )
        
        # Parse JSON response
        result = parse_json_response(response.content, ObserverOutput)
        return result
    
    async def execute(
        self,
        original_question: str,
        step1_output: Step1Output,
        step2_output: Step2Output,
        state: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> ObserverOutput:
        """Execute Observer for Step 2 consistency checking.
        
        Called when step2_output.validation.all_valid == False.
        
        Args:
            original_question: Original user question (before restatement)
            step1_output: Output from Step 1
            step2_output: Output from Step 2
            state: Current workflow state (for middleware)
            config: LangGraph RunnableConfig (contains middleware)
            
        Returns:
            ObserverOutput with decision and optional correction
        """
        # Format Step 1 output for prompt
        what_str = str({
            "measures": [m.field for m in step1_output.what.measures]
        })
        where_str = str({
            "dimensions": [d.field for d in step1_output.where.dimensions],
            "filters": [f.field for f in step1_output.where.filters]
        })
        
        # Format Step 2 output for prompt
        computations_str = str([
            {
                "target": c.target,
                "partition_by": c.partition_by,
                "calc_type": c.calc_type.value
            }
            for c in step2_output.computations
        ])
        
        # Format validation details
        validation = step2_output.validation
        target_check_str = str({
            "inferred": validation.target_check.inferred_value,
            "reference": validation.target_check.reference_value,
            "is_match": validation.target_check.is_match,
            "note": validation.target_check.note
        })
        partition_by_check_str = str({
            "inferred": validation.partition_by_check.inferred_value,
            "reference": validation.partition_by_check.reference_value,
            "is_match": validation.partition_by_check.is_match,
            "note": validation.partition_by_check.note
        })
        calc_type_check_str = str({
            "inferred": validation.calc_type_check.inferred_value,
            "reference": validation.calc_type_check.reference_value,
            "is_match": validation.calc_type_check.is_match,
            "note": validation.calc_type_check.note
        })
        
        # Use STEP2_OBSERVER_PROMPT to format messages
        messages = STEP2_OBSERVER_PROMPT.format_messages(
            original_question=original_question,
            restated_question=step1_output.restated_question,
            what=what_str,
            where=where_str,
            how_type=step1_output.how_type.value,
            computations=computations_str,
            reasoning=step2_output.reasoning,
            validation=str(validation.model_dump()),
            target_check=target_check_str,
            partition_by_check=partition_by_check_str,
            calc_type_check=calc_type_check_str,
            all_valid=validation.all_valid,
            inconsistencies=validation.inconsistencies,
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
            tools=[],
            streaming=True,
            middleware=middleware,
            state=state or {},
            config=config,
        )
        
        # Parse JSON response from AIMessage.content
        result = parse_json_response(response.content, ObserverOutput)
        return result
