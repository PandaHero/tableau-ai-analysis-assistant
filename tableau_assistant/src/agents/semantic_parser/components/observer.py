"""Observer Component - Consistency checking (Metacognition).

Observer is the "Metacognition" phase of the LLM combination architecture.
Only triggered when step2.validation.all_valid == False.

使用 call_llm_with_tools 模式（与 Step1/Step2 保持一致）：
- call_llm_with_tools(): 支持工具调用 + 中间件 + 流式输出
- parse_json_response(): 解析 JSON 响应
- 不使用 with_structured_output（对某些模型不可靠）
"""

import logging
from typing import Any, Dict, Optional

from ....core.models import ObserverOutput, Step1Output, Step2Output
from ..prompts.observer import OBSERVER_PROMPT
from tableau_assistant.src.agents.base import (
    get_llm,
    call_llm_with_tools,
    parse_json_response,
)

logger = logging.getLogger(__name__)


class ObserverComponent:
    """Observer: Consistency checking.
    
    Responsibilities:
    - Check restatement completeness
    - Review Step 2's validation results
    - Check semantic consistency
    - Make decision (ACCEPT / CORRECT / RETRY / CLARIFY)
    
    Only triggered when step2.validation.all_valid == False.
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
    
    async def execute(
        self,
        original_question: str,
        step1_output: Step1Output,
        step2_output: Step2Output,
        state: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> ObserverOutput:
        """Execute Observer: Consistency checking.
        
        Only called when step2_output.validation.all_valid == False.
        
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
                "operation": {"type": c.operation.type.value}
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
        operation_check_str = str({
            "inferred": validation.operation_check.inferred_value,
            "reference": validation.operation_check.reference_value,
            "is_match": validation.operation_check.is_match,
            "note": validation.operation_check.note
        })
        
        # Use OBSERVER_PROMPT to format messages (auto-injects JSON Schema)
        messages = OBSERVER_PROMPT.format_messages(
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
            operation_check=operation_check_str,
            all_valid=validation.all_valid,
            inconsistencies=validation.inconsistencies,
        )
        
        # Get middleware from config
        middleware = None
        if config and "configurable" in config:
            middleware = config["configurable"].get("middleware")
        
        # Call LLM using call_llm_with_tools (supports middleware + streaming)
        # 与 Step1/Step2 保持一致的调用模式
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
        
        # Parse JSON response
        result = parse_json_response(response, ObserverOutput)
        return result
