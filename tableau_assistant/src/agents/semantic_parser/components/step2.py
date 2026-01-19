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

Error handling (Requirements 0.6):
- Format errors (JSON parse, Pydantic validation) are retried within component
- Max MAX_FORMAT_RETRIES attempts before propagating to ReAct
- Semantic errors are NOT retried here, they go to ReAct

Architecture:
- Step2Component: Pure business logic, no VizQLState knowledge
- step2_node: State orchestration, defined in node.py to properly import VizQLState
- This separation avoids circular imports (core/state.py imports from agents/semantic_parser/models/)
"""

import logging
import time
from typing import Any, Dict, Optional

from pydantic import ValidationError as PydanticValidationError

from tableau_assistant.src.agents.semantic_parser.models import Step1Output, Step2Output
from tableau_assistant.src.core.exceptions import ValidationError
from tableau_assistant.src.infra.observability import get_metrics_from_config, SemanticParserMetrics
from tableau_assistant.src.agents.semantic_parser.prompts.step2 import STEP2_PROMPT

from tableau_assistant.src.agents.base import (
    get_llm,
    call_llm_with_tools,
    parse_json_response,
    JSONParseError,
)
from tableau_assistant.src.infra.config.settings import settings

logger = logging.getLogger(__name__)

# Format retry limit (Requirements 0.6)
# Format errors (JSON parse, Pydantic validation) are retried within component
# Semantic errors are handled by ReAct
# 从配置文件读取，支持环境变量覆盖
MAX_FORMAT_RETRIES = settings.semantic_parser_max_format_retries


class Step2Component:
    """Step 2: Computation reasoning and LLM self-validation.
    
    Responsibilities:
    - Infer computation from restated_question
    - Self-validate against Step 1 output
    - Report inconsistencies
    
    NOTE: validation is done by LLM itself, not by this component.
    
    Error Handling (Requirements 0.6):
    - Format errors are retried within component (max MAX_FORMAT_RETRIES)
    - Semantic errors are propagated to ReAct
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
            # 启用 JSON Mode（Requirements 0.7）
            self._llm = get_llm(agent_name="semantic_parser", enable_json_mode=True)
        return self._llm
    
    def _get_metrics_from_config(self, config: Optional[Dict[str, Any]]) -> Optional[SemanticParserMetrics]:
        """Get metrics object from config if available.
        
        Args:
            config: LangGraph RunnableConfig
            
        Returns:
            SemanticParserMetrics object or None
        """
        if config is None:
            return None
        return get_metrics_from_config(config)
    
    async def execute(
        self,
        step1_output: Step1Output,
        state: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None,
        error_feedback: Optional[str] = None,
    ) -> Step2Output:
        """Execute Step 2: Computation reasoning and self-validation.
        
        Implements format retry loop (Requirements 0.6):
        - Format errors (JSON parse, Pydantic validation) are retried within component
        - Max MAX_FORMAT_RETRIES attempts before propagating to ReAct
        - Semantic errors are NOT retried here, they go to ReAct
        
        Only called when step1_output.how_type != SIMPLE.
        
        Args:
            step1_output: Output from Step 1
            state: Current workflow state (for middleware)
            config: LangGraph RunnableConfig (contains middleware)
            error_feedback: Feedback from previous error (for retry from ReAct)
            
        Returns:
            Step2Output with computations, reasoning, and LLM self-validation
            
        Raises:
            ValidationError: When format retry exhausted (handled by Agent via ReAct)
        """
        # Get metrics for observability (Requirements 0.5)
        metrics = self._get_metrics_from_config(config)
        start_time = time.monotonic()
        
        # Extract measures and dimensions for validation reference
        measures = [m.field_name for m in step1_output.what.measures]
        dimensions = [d.field_name for d in step1_output.where.dimensions]
        
        # Get middleware from config
        middleware = None
        if config and "configurable" in config:
            middleware = config["configurable"].get("middleware")
        
        llm = self._get_llm()
        
        # Format retry loop (Requirements 0.6)
        format_error_feedback: str | None = None
        last_response_content: str = ""
        
        for attempt in range(MAX_FORMAT_RETRIES + 1):
            # Build restated question with error feedback if present
            # Priority: format_error_feedback (from retry) > error_feedback (from ReAct)
            restated_question = step1_output.restated_question
            current_feedback = format_error_feedback or error_feedback
            if current_feedback:
                restated_question = f"{restated_question}\n\n[系统提示：上次计算推理出现问题，请注意：{current_feedback}]"
                if attempt > 0:
                    logger.info(f"Step 2 format retry {attempt}/{MAX_FORMAT_RETRIES} with feedback: {current_feedback[:100]}...")
                else:
                    logger.info(f"Step 2 retry with feedback: {current_feedback[:100]}...")
            
            # Use STEP2_PROMPT to format messages (auto-injects JSON Schema)
            messages = STEP2_PROMPT.format_messages(
                restated_question=restated_question,
                measures=measures,
                dimensions=dimensions,
                how_type=step1_output.how_type.value,
            )
            
            try:
                # Call LLM using call_llm_with_tools (supports middleware + streaming)
                response = await call_llm_with_tools(
                    llm=llm,
                    messages=messages,
                    tools=[],  # No tools needed
                    streaming=True,
                    middleware=middleware,
                    state=state or {},
                    config=config,
                )
                
                # Store for error reporting
                last_response_content = response.content
                
                # Record metrics (Requirements 0.5)
                if metrics is not None:
                    # Record token usage if available
                    usage = getattr(response, 'usage_metadata', None) or {}
                    if usage:
                        prompt_tokens = usage.get('input_tokens', 0)
                        completion_tokens = usage.get('output_tokens', 0)
                        metrics.record_step2_tokens(prompt_tokens, completion_tokens)
                    else:
                        # Just increment call count if no usage info
                        metrics.step2_call_count += 1
                
                # Parse JSON response from AIMessage.content
                result = parse_json_response(
                    response.content,
                    Step2Output,
                    metrics=metrics,
                    provider=getattr(llm, "_provider", None),
                )

                
                # Success! Record timing and return
                if metrics is not None:
                    metrics.record_step2_timing(start_time)
                
                if attempt > 0:
                    logger.info(f"Step 2 format retry succeeded after {attempt} retries")
                
                return result
                
            except (ValueError, PydanticValidationError, JSONParseError) as e:
                # Format error - retry within component
                # Note: JSONParseError is thrown by parse_json_response() for JSON format errors
                # PydanticValidationError is thrown for schema validation errors
                if attempt < MAX_FORMAT_RETRIES:
                    logger.warning(
                        f"Step 2 format error, retry {attempt + 1}/{MAX_FORMAT_RETRIES}: {e}"
                    )
                    
                    # Record retry metric
                    if metrics is not None:
                        metrics.step2_parse_retry_count += 1
                        # 记录重试触发原因（Requirements 0.6）
                        reason = (
                            "json_parse" if isinstance(e, JSONParseError)
                            else "pydantic_validation" if isinstance(e, PydanticValidationError)
                            else "value_error"
                        )
                        if hasattr(metrics, "step2_parse_retry_reason_counts"):
                            metrics.step2_parse_retry_reason_counts[reason] = (
                                metrics.step2_parse_retry_reason_counts.get(reason, 0) + 1
                            )

                    
                    # Build structured error feedback for next attempt
                    format_error_feedback = self._build_error_feedback(e)
                    continue
                
                # Format retry exhausted - propagate to ReAct
                logger.error(
                    f"Step 2 format retry exhausted after {MAX_FORMAT_RETRIES} retries: {e}"
                )
                
                # Record final timing
                if metrics is not None:
                    metrics.record_step2_timing(start_time)
                
                # Wrap error with original output for Observer/ReAct
                raise ValidationError(
                    message=str(e),
                    original_output=last_response_content,
                    step="step2",
                ) from e
    
    def _build_error_feedback(self, error: Exception) -> str:
        """Build structured error feedback for format retry.
        
        Extracts specific field errors from Pydantic ValidationError
        or formats JSON parse errors for LLM to understand.
        
        Args:
            error: The exception that occurred (ValueError or PydanticValidationError)
            
        Returns:
            Structured error feedback string for LLM
            
        Requirements: 0.6 - 组件级解析重试
        """
        if isinstance(error, PydanticValidationError):
            # Pydantic validation error - extract specific field errors
            error_details = []
            for err in error.errors():
                field = ".".join(str(loc) for loc in err["loc"])
                msg = err["msg"]
                error_details.append(f"- 字段 '{field}': {msg}")
            
            return (
                f"解析失败：Pydantic 校验错误\n"
                f"{''.join(error_details)}\n"
                f"请修正上述字段后重新输出完整的 JSON。"
            )
        else:
            # JSON parse error or other ValueError
            error_str = str(error)[:300]  # Limit error message length
            return (
                f"解析失败：{error_str}\n"
                f"请确保输出是有效的 JSON 格式，包含所有必需字段。"
            )
