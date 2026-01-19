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

Architecture:
- Step1Component: Pure business logic, no VizQLState knowledge
- step1_node: State orchestration, defined in node.py to properly import VizQLState
- This separation avoids circular imports (core/state.py imports from agents/semantic_parser/models/)

Token Limit Protection (Requirements 0.4):
- History: MAX_HISTORY_TOKENS = 2000 tokens
- Schema: MAX_SCHEMA_TOKENS = 3000 tokens
- Truncation preserves most recent/relevant content
- Truncation frequency is logged for monitoring
"""

import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import tiktoken
from pydantic import ValidationError as PydanticValidationError

from tableau_assistant.src.agents.semantic_parser.models import Step1Output
from tableau_assistant.src.infra.storage.data_model import DataModel
from tableau_assistant.src.infra.observability import get_metrics_from_config, SemanticParserMetrics
from tableau_assistant.src.core.exceptions import ValidationError
from tableau_assistant.src.agents.semantic_parser.prompts.step1 import STEP1_PROMPT

from tableau_assistant.src.agents.base import (
    get_llm,
    call_llm_with_tools,
    parse_json_response,
    JSONParseError,
)
from tableau_assistant.src.infra.config.settings import settings

logger = logging.getLogger(__name__)

# Token limits for prompt components (Requirements 0.4)
# 从配置文件读取，支持环境变量覆盖
MAX_HISTORY_TOKENS = settings.semantic_parser_max_history_tokens
MAX_SCHEMA_TOKENS = settings.semantic_parser_max_schema_tokens

# Format retry limit (Requirements 0.6)
# Format errors (JSON parse, Pydantic validation) are retried within component
# Semantic errors are handled by ReAct
# 从配置文件读取，支持环境变量覆盖
MAX_FORMAT_RETRIES = settings.semantic_parser_max_format_retries

# Default encoding for token counting (cl100k_base is used by GPT-4, Claude, etc.)
_ENCODING: tiktoken.Encoding | None = None


def _get_encoding() -> tiktoken.Encoding:
    """Get or create tiktoken encoding (lazy initialization)."""
    global _ENCODING
    if _ENCODING is None:
        _ENCODING = tiktoken.get_encoding("cl100k_base")
    return _ENCODING


def count_tokens(text: str) -> int:
    """Count tokens in text using tiktoken.
    
    Args:
        text: Text to count tokens for
        
    Returns:
        Number of tokens
    """
    if not text:
        return 0
    encoding = _get_encoding()
    return len(encoding.encode(text))


def truncate_to_tokens(text: str, max_tokens: int, keep_end: bool = True) -> str:
    """Truncate text to fit within token limit.
    
    Args:
        text: Text to truncate
        max_tokens: Maximum number of tokens
        keep_end: If True, keep the end of text (most recent); if False, keep the start
        
    Returns:
        Truncated text
    """
    if not text:
        return text
    
    encoding = _get_encoding()
    tokens = encoding.encode(text)
    
    if len(tokens) <= max_tokens:
        return text
    
    # Reserve some tokens for the truncation marker
    marker = "... [truncated] ...\n" if keep_end else "\n... [truncated] ..."
    marker_tokens = len(encoding.encode(marker))
    available_tokens = max_tokens - marker_tokens
    
    if available_tokens <= 0:
        # Edge case: max_tokens is too small
        return marker.strip()
    
    if keep_end:
        # Keep the end (most recent content)
        truncated_tokens = tokens[-available_tokens:]
        truncated_text = encoding.decode(truncated_tokens)
        return marker + truncated_text
    else:
        # Keep the start
        truncated_tokens = tokens[:available_tokens]
        truncated_text = encoding.decode(truncated_tokens)
        return truncated_text + marker


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
            # 启用 JSON Mode（Requirements 0.7）
            self._llm = get_llm(agent_name="semantic_parser", enable_json_mode=True)
        return self._llm
    
    def _get_metrics_from_config(self, config: Optional[Dict[str, Any]]) -> Optional[SemanticParserMetrics]:
        """Get metrics object from config if available.
        
        Uses the centralized get_metrics_from_config from observability module.
        
        Args:
            config: LangGraph RunnableConfig
            
        Returns:
            SemanticParserMetrics object or None
        """
        if config is None:
            return None
        return get_metrics_from_config(config)
    
    def _get_effective_history(
        self,
        history: list[dict[str, str]] | None,
        state: Optional[Dict[str, Any]],
        config: Optional[Dict[str, Any]] = None,
    ) -> list[dict[str, str]] | None:
        """Determine effective history source (Requirements 0.10).
        
        Priority:
        1. state["messages"] - SummarizationMiddleware processed
        2. history parameter - fallback
        
        This ensures SummarizationMiddleware's processing is respected.
        
        Args:
            history: Direct history parameter (deprecated, fallback only)
            state: Current workflow state containing messages
            config: LangGraph RunnableConfig (for metrics)
            
        Returns:
            Effective history list or None
        """
        # Try to get history from state["messages"] first
        if state is not None:
            messages = state.get("messages")
            if messages:
                converted = self._convert_messages_to_history(messages)
                if converted:
                    # Log history source for debugging
                    history_tokens = count_tokens(
                        self._do_format_history(converted) if converted else ""
                    )
                    logger.debug(
                        f"Step1 history: source=state['messages'], "
                        f"message_count={len(messages)}, "
                        f"tokens={history_tokens}"
                    )
                    return converted
        
        # Fallback to history parameter
        if history:
            history_tokens = count_tokens(
                self._do_format_history(history) if history else ""
            )
            logger.debug(
                f"Step1 history: source=history_param, "
                f"message_count={len(history)}, "
                f"tokens={history_tokens}"
            )
        
        return history
    
    def _convert_messages_to_history(
        self,
        messages: List[Any],
    ) -> list[dict[str, str]] | None:
        """Convert LangGraph BaseMessage objects to history format.
        
        Converts LangGraph message objects (HumanMessage, AIMessage) to
        simple dict format {"role": "user/assistant", "content": "..."}.
        
        Args:
            messages: List of LangGraph BaseMessage objects
            
        Returns:
            List of history dicts or None if empty
        """
        if not messages:
            return None
        
        history = []
        for msg in messages:
            # Handle LangGraph BaseMessage objects
            if hasattr(msg, "type") and hasattr(msg, "content"):
                role = "user" if msg.type == "human" else "assistant"
                history.append({"role": role, "content": msg.content})
            # Handle dict format (already converted)
            elif isinstance(msg, dict) and "role" in msg and "content" in msg:
                history.append(msg)
        
        return history if history else None
    
    async def execute(
        self,
        question: str,
        history: list[dict[str, str]] | None = None,
        data_model: DataModel | None = None,
        state: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None,
        error_feedback: Optional[str] = None,
        time_context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Step1Output, str]:
        """Execute Step 1: Semantic understanding and question restatement.
        
        Implements format retry loop (Requirements 0.6):
        - Format errors (JSON parse, Pydantic validation) are retried within component
        - Max MAX_FORMAT_RETRIES attempts before propagating to ReAct
        - Semantic errors are NOT retried here, they go to ReAct
        
        History Source (Requirements 0.10):
        - If state["messages"] is available, use it (SummarizationMiddleware processed)
        - Otherwise, fall back to the history parameter
        - Hard truncation is applied as a safety net (Requirements 0.4)
        
        Time Context (Requirements 1 - Phase 1):
        - If time_context is provided (from Preprocess), use its date range
        - Otherwise, fall back to today's date
        - Uses date-level granularity (not second-level) for cache stability
        
        Args:
            question: Current user question
            history: Conversation history (list of {"role": "user/assistant", "content": "..."})
                     DEPRECATED: Prefer using state["messages"] for SummarizationMiddleware support
            data_model: Data source model (DataModel object with fields, tables, relationships)
            state: Current workflow state (for middleware and history)
            config: LangGraph RunnableConfig (contains middleware)
            error_feedback: Feedback from previous error (for retry from ReAct)
            time_context: Time context from Preprocess (contains start_date, end_date, grain_hint)
            
        Returns:
            Tuple of (Step1Output, thinking_process)
            - Step1Output: restated_question, what, where, how_type, intent
            - thinking_process: R1 model's thinking process (if available)
            
        Raises:
            ValidationError: When format retry exhausted (handled by Agent via ReAct)
        """
        # Get metrics for observability (Requirements 0.5)
        metrics = self._get_metrics_from_config(config)
        start_time = time.monotonic()
        
        # Determine history source (Requirements 0.10)
        # Priority: state["messages"] > history parameter
        # This ensures SummarizationMiddleware's processing is respected
        effective_history = self._get_effective_history(history, state, config)
        
        # Format history for prompt (with token limit, Requirements 0.4)
        history_str = self._format_history(effective_history, config)
        
        # Format data model for prompt (with token limit, Requirements 0.4)
        data_model_str = self._format_data_model(data_model, config)
        
        # Get current date for date-related questions (Requirements 1 - Phase 1)
        # Use date-level granularity (not second-level) for cache stability
        # Priority: time_context from Preprocess > today's date
        current_date = self._get_current_date(time_context)
        
        # Get middleware from config
        middleware = None
        if config and "configurable" in config:
            middleware = config["configurable"].get("middleware")
        
        llm = self._get_llm()
        
        # Format retry loop (Requirements 0.6)
        # Format errors are retried within component, semantic errors go to ReAct
        format_error_feedback: str | None = None
        last_response_content: str = ""
        last_thinking: str = ""
        
        for attempt in range(MAX_FORMAT_RETRIES + 1):
            # Build question with error feedback if present
            # Priority: format_error_feedback (from retry) > error_feedback (from ReAct)
            effective_question = question
            current_feedback = format_error_feedback or error_feedback
            if current_feedback:
                effective_question = f"{question}\n\n[系统提示：上次语义理解出现问题，请注意：{current_feedback}]"
                if attempt > 0:
                    logger.info(f"Step 1 format retry {attempt}/{MAX_FORMAT_RETRIES} with feedback: {current_feedback[:100]}...")
                else:
                    logger.info(f"Step 1 retry with feedback: {current_feedback[:100]}...")
            
            # Use STEP1_PROMPT to format messages (auto-injects JSON Schema)
            messages = STEP1_PROMPT.format_messages(
                question=effective_question,
                history=history_str,
                data_model=data_model_str,
                current_time=current_date,  # 使用日期级别时间（Requirements 1 - Phase 1）
            )
            
            try:
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
                
                # Store for error reporting
                last_response_content = response.content
                last_thinking = response.additional_kwargs.get("thinking", "")
                
                # Record metrics (Requirements 0.5)
                if metrics is not None:
                    # Record token usage if available
                    usage = getattr(response, 'usage_metadata', None) or {}
                    if usage:
                        prompt_tokens = usage.get('input_tokens', 0)
                        completion_tokens = usage.get('output_tokens', 0)
                        metrics.record_step1_tokens(prompt_tokens, completion_tokens)
                    else:
                        # Just increment call count if no usage info
                        metrics.step1_call_count += 1
                
                # Parse and validate JSON response
                result = parse_json_response(
                    response.content,
                    Step1Output,
                    metrics=metrics,
                    provider=getattr(llm, "_provider", None),
                )

                
                # Success! Record timing and return
                if metrics is not None:
                    metrics.record_step1_timing(start_time)
                
                if attempt > 0:
                    logger.info(f"Step 1 format retry succeeded after {attempt} retries")
                
                return result, last_thinking
                
            except (ValueError, PydanticValidationError, JSONParseError) as e:
                # Format error - retry within component
                # Note: JSONParseError is thrown by parse_json_response() for JSON format errors
                # PydanticValidationError is thrown for schema validation errors
                if attempt < MAX_FORMAT_RETRIES:
                    logger.warning(
                        f"Step 1 format error, retry {attempt + 1}/{MAX_FORMAT_RETRIES}: {e}"
                    )
                    
                    # Record retry metric
                    if metrics is not None:
                        metrics.step1_parse_retry_count += 1
                        # 记录重试触发原因（Requirements 0.6）
                        reason = (
                            "json_parse" if isinstance(e, JSONParseError)
                            else "pydantic_validation" if isinstance(e, PydanticValidationError)
                            else "value_error"
                        )
                        if hasattr(metrics, "step1_parse_retry_reason_counts"):
                            metrics.step1_parse_retry_reason_counts[reason] = (
                                metrics.step1_parse_retry_reason_counts.get(reason, 0) + 1
                            )

                    
                    # Build structured error feedback for next attempt
                    format_error_feedback = self._build_error_feedback(e)
                    continue
                
                # Format retry exhausted - propagate to ReAct
                logger.error(
                    f"Step 1 format retry exhausted after {MAX_FORMAT_RETRIES} retries: {e}"
                )
                
                # Record final timing
                if metrics is not None:
                    metrics.record_step1_timing(start_time)
                
                # Wrap error with original output for Observer/ReAct
                raise ValidationError(
                    message=str(e),
                    original_output=last_response_content,
                    step="step1",
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
    
    def _format_history(
        self,
        history: list[dict[str, str]] | None,
        config: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Format conversation history for prompt with token limit.
        
        Note: History is now limited by MAX_HISTORY_TOKENS (Requirements 0.4).
        This is a hard limit to prevent token overflow and hallucination.
        SummarizationMiddleware may still be used for semantic compression.
        
        Args:
            history: Conversation history (list of {"role": "user/assistant", "content": "..."})
            config: LangGraph RunnableConfig (for metrics)
            
        Returns:
            Formatted history string, truncated if necessary
        """
        if not history:
            return "(No previous conversation)"
        
        # First, format all history
        formatted = self._do_format_history(history)
        
        # Get metrics from config if available
        metrics = self._get_metrics_from_config(config)
        
        # Apply hard token limit (Requirements 0.4)
        return self._format_history_with_limit(formatted, MAX_HISTORY_TOKENS, metrics)
    
    def _do_format_history(self, history: list[dict[str, str]]) -> str:
        """Format history without token limit (internal helper).
        
        Args:
            history: Conversation history
            
        Returns:
            Formatted history string
        """
        formatted = []
        for msg in history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            formatted.append(f"[{role}]: {content}")
        
        return "\n".join(formatted)
    
    def _format_history_with_limit(
        self,
        formatted_history: str,
        max_tokens: int,
        metrics: Any = None,
    ) -> str:
        """Apply hard token limit to formatted history.
        
        Truncates from the beginning to keep most recent conversation.
        Logs truncation and updates metrics for monitoring (Requirements 0.4).
        
        Args:
            formatted_history: Already formatted history string
            max_tokens: Maximum tokens allowed
            metrics: Optional SemanticParserMetrics object for recording truncation
            
        Returns:
            Truncated history string if necessary
        """
        if not formatted_history:
            return formatted_history
        
        original_tokens = count_tokens(formatted_history)
        
        if original_tokens <= max_tokens:
            return formatted_history
        
        # Truncate, keeping the end (most recent)
        truncated = truncate_to_tokens(formatted_history, max_tokens, keep_end=True)
        truncated_tokens = count_tokens(truncated)
        
        # Log truncation for monitoring
        logger.warning(
            f"History truncated: {original_tokens} -> {truncated_tokens} tokens "
            f"(limit: {max_tokens})"
        )
        
        # Update metrics if available (Requirements 0.4)
        if metrics is not None:
            # Support both counter-style (.inc()) and simple increment
            if hasattr(metrics, 'history_truncation_count'):
                if hasattr(metrics.history_truncation_count, 'inc'):
                    metrics.history_truncation_count.inc()
                elif isinstance(metrics.history_truncation_count, int):
                    metrics.history_truncation_count += 1
            # Also set the truncated flag if available
            if hasattr(metrics, 'history_truncated'):
                metrics.history_truncated = True
        
        return truncated
    
    def _get_current_date(
        self,
        time_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Get current date for prompt (Requirements 1 - Phase 1).
        
        Uses date-level granularity (not second-level) for cache stability.
        If time_context is provided from Preprocess, uses its end_date.
        Otherwise, falls back to today's date.
        
        Args:
            time_context: Time context from Preprocess (contains start_date, end_date, grain_hint)
            
        Returns:
            Date string in YYYY-MM-DD format
        """
        from datetime import date
        
        if time_context:
            # Use end_date from time_context if available
            end_date = time_context.get("end_date")
            if end_date:
                # end_date might be a string (from JSON) or date object
                if isinstance(end_date, str):
                    return end_date
                elif hasattr(end_date, "isoformat"):
                    return end_date.isoformat()
        
        # Fallback to today's date
        return date.today().isoformat()
    
    def _format_data_model(
        self,
        data_model: DataModel | None,
        config: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Format data model for prompt with token limit.
        
        Args:
            data_model: DataModel object containing fields, tables, relationships
            config: LangGraph RunnableConfig (for metrics)
            
        Returns:
            Formatted string describing available fields for LLM reference,
            truncated if necessary (Requirements 0.4)
            
        Note:
            For measures, we indicate whether they are pre-aggregated (calculated fields
            with formulas containing aggregations like SUM, AVG). Pre-aggregated measures
            should NOT have aggregation specified in MeasureField.
        """
        if not data_model:
            return "(No data model available)"
        
        if not data_model.fields:
            return "(No fields available)"
        
        # Format the data model
        formatted = self._do_format_data_model(data_model)
        
        # Get metrics from config if available
        metrics = self._get_metrics_from_config(config)
        
        # Apply hard token limit (Requirements 0.4)
        return self._format_schema_with_limit(formatted, MAX_SCHEMA_TOKENS, metrics)
    
    def _do_format_data_model(self, data_model: DataModel) -> str:
        """Format data model without token limit (internal helper).
        
        Args:
            data_model: DataModel object
            
        Returns:
            Formatted data model string
        """
        result = []
        
        # Add data source info
        result.append(f"Data Source: {data_model.datasource_name}")
        
        # For multi-table data model, show table structure
        if data_model.is_multi_table:
            result.append(f"Tables: {len(data_model.logical_tables)}")
            for table in data_model.logical_tables:
                table_fields = data_model.get_fields_by_table(table.logicalTableId)
                dims = [f.fieldCaption or f.name for f in table_fields if f.role == "dimension"]
                meas = self._format_measures_with_aggregation_info(
                    [f for f in table_fields if f.role == "measure"]
                )
                result.append(f"  [{table.caption}]")
                if dims:
                    result.append(f"    Dimensions: {', '.join(dims)}")
                if meas:
                    result.append(f"    Measures: {meas}")
        else:
            # Single table: list dimensions and measures with aggregation info
            dimensions = [f.fieldCaption or f.name for f in data_model.get_dimensions()]
            measures = self._format_measures_with_aggregation_info(data_model.get_measures())
            
            if dimensions:
                result.append(f"Dimensions: {', '.join(dimensions)}")
            if measures:
                result.append(f"Measures: {measures}")
        
        return "\n".join(result) if result else "(No fields available)"
    
    def _format_schema_with_limit(
        self,
        formatted_schema: str,
        max_tokens: int,
        metrics: Any = None,
    ) -> str:
        """Apply hard token limit to formatted schema.
        
        Truncates from the end to keep most important fields (listed first).
        Logs truncation and updates metrics for monitoring (Requirements 0.4).
        
        Args:
            formatted_schema: Already formatted schema string
            max_tokens: Maximum tokens allowed
            metrics: Optional SemanticParserMetrics object for recording truncation
            
        Returns:
            Truncated schema string if necessary
        """
        if not formatted_schema:
            return formatted_schema
        
        original_tokens = count_tokens(formatted_schema)
        
        if original_tokens <= max_tokens:
            return formatted_schema
        
        # Truncate, keeping the start (most important fields)
        truncated = truncate_to_tokens(formatted_schema, max_tokens, keep_end=False)
        truncated_tokens = count_tokens(truncated)
        
        # Log truncation for monitoring
        logger.warning(
            f"Schema truncated: {original_tokens} -> {truncated_tokens} tokens "
            f"(limit: {max_tokens})"
        )
        
        # Update metrics if available (Requirements 0.4)
        if metrics is not None:
            # Support both counter-style (.inc()) and simple increment
            if hasattr(metrics, 'schema_truncation_count'):
                if hasattr(metrics.schema_truncation_count, 'inc'):
                    metrics.schema_truncation_count.inc()
                elif isinstance(metrics.schema_truncation_count, int):
                    metrics.schema_truncation_count += 1
            # Also set the truncated flag if available
            if hasattr(metrics, 'schema_truncated'):
                metrics.schema_truncated = True
        
        return truncated
    
    def _format_schema(
        self,
        schema_candidates: Any | None,
        max_tokens: int = MAX_SCHEMA_TOKENS,
        config: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Format schema candidates for prompt with token limit.
        
        This method is prepared for future Schema Linking integration.
        Currently falls back to data_model formatting.
        
        Args:
            schema_candidates: SchemaCandidates object (future)
            max_tokens: Maximum tokens allowed (default: MAX_SCHEMA_TOKENS)
            config: LangGraph RunnableConfig (for metrics)
            
        Returns:
            Formatted schema string, truncated if necessary
            
        Requirements: 0.4 - Schema token 硬性上限保护
        """
        if schema_candidates is None:
            return "(No schema candidates available)"
        
        # Future: Use schema_candidates.to_prompt_summary()
        # For now, if schema_candidates has a to_prompt_summary method, use it
        if hasattr(schema_candidates, 'to_prompt_summary'):
            formatted = schema_candidates.to_prompt_summary()
        else:
            # Fallback: convert to string
            formatted = str(schema_candidates)
        
        # Get metrics from config if available
        metrics = self._get_metrics_from_config(config)
        
        return self._format_schema_with_limit(formatted, max_tokens, metrics)
    
    def _format_measures_with_aggregation_info(self, measures: list) -> str:
        """Format measures with aggregation info.
        
        Indicates whether each measure is pre-aggregated (calculated field with
        aggregation in formula) or needs aggregation.
        
        Args:
            measures: List of FieldMetadata objects for measures
            
        Returns:
            Formatted string like: "Sales, Profit, Profit Ratio [pre-aggregated]"
        """
        if not measures:
            return ""
        
        formatted = []
        for f in measures:
            name = f.fieldCaption or f.name
            # Check if this is a pre-aggregated calculated field
            if self._is_pre_aggregated(f):
                formatted.append(f"{name} [pre-aggregated]")
            else:
                formatted.append(name)
        
        return ", ".join(formatted)
    
    def _is_pre_aggregated(self, field) -> bool:
        """Check if a measure field is pre-aggregated.
        
        A field is pre-aggregated if:
        1. It's a calculated field (columnClass == 'CALCULATION')
        2. Its formula contains aggregation functions (SUM, AVG, COUNT, etc.)
        
        Args:
            field: FieldMetadata object
            
        Returns:
            True if the field is pre-aggregated
        """
        # Check if it's a calculated field
        column_class = (field.columnClass or "").upper()
        if column_class not in ("CALCULATION", "TABLE_CALCULATION"):
            return False
        
        # Check if formula contains aggregation functions
        formula = (field.formula or "").upper()
        if not formula:
            return False
        
        # Common aggregation functions in Tableau
        agg_functions = ["SUM(", "AVG(", "COUNT(", "COUNTD(", "MIN(", "MAX(", 
                        "MEDIAN(", "STDEV(", "VAR(", "ATTR(", "TOTAL("]
        
        return any(agg in formula for agg in agg_functions)


__all__ = [
    "Step1Component",
    "MAX_HISTORY_TOKENS",
    "MAX_SCHEMA_TOKENS",
    "MAX_FORMAT_RETRIES",
    "count_tokens",
    "truncate_to_tokens",
]
