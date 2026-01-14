# -*- coding: utf-8 -*-
"""ReAct Error Handler - LLM-based error analysis for QueryPipeline.

When QueryPipeline encounters an error, this handler uses LLM to:
1. Analyze the error and identify root cause (Thought)
2. Decide on action: CORRECT, RETRY, CLARIFY, or ABORT (Action)
3. Generate appropriate corrections or guidance

Key Design:
- CORRECT: Directly fix Step1/Step2 output without re-running LLM
- RETRY: Go back to a step with specific guidance
- CLARIFY: Ask user for clarification
- ABORT: Give up and explain to user

Uses call_llm_with_tools pattern (same as step1.py):
- call_llm_with_tools(): supports tool calls + middleware + streaming
- parse_json_response(): parses JSON response
- Does not use with_structured_output (not supported by DeepSeek R1)
"""

import copy
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.language_models import BaseChatModel
from langgraph.types import RunnableConfig

from ..models.pipeline import QueryError
from ..models.react import (
    ReActActionType,
    ErrorCategory,
    CorrectionOperation,
    Correction,
    ReActThought,
    ReActAction,
    ReActOutput,
)
from ..prompts.react_error import REACT_ERROR_PROMPT
from tableau_assistant.src.agents.base import (
    get_llm,
    call_llm_with_tools,
    parse_json_response,
)
from ....infra.observability import get_metrics_from_config
from ....infra.config.settings import settings

logger = logging.getLogger(__name__)


class RetryRecord:
    """Record of a retry attempt for tracking history."""
    
    def __init__(
        self,
        step: str,
        error_message: str,
        action_taken: str,
        success: bool = False,
    ):
        self.step = step
        self.error_message = error_message
        self.action_taken = action_taken
        self.success = success
    
    def __str__(self) -> str:
        status = "✓" if self.success else "✗"
        return f"[{status}] {self.step}: {self.error_message} → {self.action_taken}"


class ReActErrorHandler:
    """LLM-based error handler for QueryPipeline errors.
    
    This handler uses LLM to:
    1. Analyze error and identify root cause
    2. Decide action: CORRECT, RETRY, CLARIFY, or ABORT
    3. For CORRECT: Apply corrections directly to Step1/Step2 output
    4. For RETRY: Generate guidance for the step to retry
    
    Attributes:
        llm: Language model for error analysis
        max_retries_per_step: Maximum retries for each step
    """
    
    def __init__(
        self,
        llm: Optional[BaseChatModel] = None,
        max_retries_per_step: int = settings.semantic_parser_max_semantic_retries,
    ):
        """Initialize ReAct error handler.
        
        Args:
            llm: Language model for error analysis (uses default if None)
            max_retries_per_step: Maximum retries per step (default from config)
        """
        self._llm = llm
        self.max_retries_per_step = max_retries_per_step
    
    @property
    def llm(self) -> BaseChatModel:
        """Get LLM instance (lazy initialization)."""
        if self._llm is None:
            self._llm = get_llm(agent_name="semantic_parser")
        return self._llm
    
    async def handle_error(
        self,
        error: QueryError,
        question: str,
        step1_output: Optional[Any] = None,
        step2_output: Optional[Any] = None,
        pipeline_context: Optional[Dict[str, Any]] = None,
        retry_history: Optional[List[RetryRecord]] = None,
        config: Optional[RunnableConfig] = None,
    ) -> Tuple[ReActOutput, Optional[Any], Optional[Any]]:
        """Handle a QueryPipeline error using LLM.
        
        Args:
            error: QueryError from pipeline
            question: Original user question
            step1_output: Step1Output object (will be modified if CORRECT)
            step2_output: Step2Output object (will be modified if CORRECT)
            pipeline_context: Additional context from pipeline execution
            retry_history: History of previous retry attempts
            config: LangGraph config
        
        Returns:
            Tuple of (ReActOutput, corrected_step1_output, corrected_step2_output)
            - If action is CORRECT, returns corrected outputs
            - Otherwise, returns original outputs unchanged
        """
        retry_history = retry_history or []
        pipeline_context = pipeline_context or {}
        
        # 新增：处理解析失败错误
        from ..models.pipeline import QueryErrorType
        if error.type in (QueryErrorType.STEP1_PARSE_ERROR, QueryErrorType.STEP2_PARSE_ERROR):
            logger.info(f"处理解析失败错误: {error.type}")
            output = self._handle_parse_error(error, retry_history)
            return output, step1_output, step2_output
        
        # Check if max retries reached for this step
        step_retry_count = self._count_retries_for_step(retry_history, error.step)
        if step_retry_count >= self.max_retries_per_step:
            logger.info(f"Max retries ({self.max_retries_per_step}) reached for step {error.step}")
            output = self._create_max_retry_output(error, error.step)
            return output, step1_output, step2_output
        
        # Call LLM to analyze error
        try:
            output = await self._call_llm_for_analysis(
                error=error,
                question=question,
                step1_output=step1_output,
                step2_output=step2_output,
                pipeline_context=pipeline_context,
                retry_history=retry_history,
                config=config,
            )
            
            logger.info(
                f"ReAct decision: action={output.action.action_type}, "
                f"error_category={output.thought.error_category}, "
                f"can_correct={output.thought.can_correct}"
            )
            
            # If CORRECT action, apply corrections
            if output.action.action_type == ReActActionType.CORRECT:
                corrected_step1, corrected_step2 = self._apply_corrections(
                    corrections=output.action.corrections or [],
                    step1_output=step1_output,
                    step2_output=step2_output,
                )
                return output, corrected_step1, corrected_step2
            
            return output, step1_output, step2_output
            
        except Exception as e:
            logger.error(f"LLM error analysis failed: {e}", exc_info=True)
            output = self._create_fallback_output(error)
            return output, step1_output, step2_output

    async def _call_llm_for_analysis(
        self,
        error: QueryError,
        question: str,
        step1_output: Optional[Any],
        step2_output: Optional[Any],
        pipeline_context: Dict[str, Any],
        retry_history: List[RetryRecord],
        config: Optional[RunnableConfig],
    ) -> ReActOutput:
        """Call LLM to analyze error and generate response.
        
        Uses call_llm_with_tools + parse_json_response pattern
        (same as step1.py) for compatibility with DeepSeek R1 model.
        """
        # Format step1 output
        step1_str = "None"
        if step1_output:
            try:
                step1_str = step1_output.model_dump_json(indent=2)
            except Exception:
                step1_str = str(step1_output)
        
        # Format step2 output
        step2_str = "None"
        if step2_output:
            try:
                step2_str = step2_output.model_dump_json(indent=2)
            except Exception:
                step2_str = str(step2_output)
        
        # Format pipeline context
        context_str = self._format_pipeline_context(pipeline_context)
        
        # Format retry history
        history_str = self._format_retry_history(retry_history)
        
        # Format error details
        error_details = "None"
        if error.details:
            error_details = "\n".join(f"  - {k}: {v}" for k, v in error.details.items())
        if error.suggestion:
            error_details += f"\n  - Suggestion: {error.suggestion}"
        
        # Build prompt using format_messages
        messages = REACT_ERROR_PROMPT.format_messages(
            question=question,
            pipeline_context=context_str,
            error_step=error.step,
            error_type=error.type.value,
            error_message=error.message,
            error_details=error_details,
            step1_output=step1_str,
            step2_output=step2_str,
            retry_history=history_str or "无重试历史",
        )
        
        # Get middleware from config
        middleware = None
        if config and "configurable" in config:
            middleware = config["configurable"].get("middleware")
        
        # Call LLM using call_llm_with_tools (same pattern as step1.py)
        response = await call_llm_with_tools(
            llm=self.llm,
            messages=messages,
            tools=[],
            streaming=True,
            middleware=middleware,
            state={},
            config=config,
        )
        
        # Record react_call_count metric (Requirements 0.5)
        metrics = get_metrics_from_config(config)
        if metrics is not None:
            metrics.react_call_count += 1
        
        # Parse JSON response into ReActOutput
        try:
            result = parse_json_response(response.content, ReActOutput, metrics=metrics)
            return result
        except ValueError as e:
            logger.warning(f"Failed to parse ReAct output: {e}")
            raise
    
    def _apply_corrections(
        self,
        corrections: List[Correction],
        step1_output: Optional[Any],
        step2_output: Optional[Any],
    ) -> Tuple[Optional[Any], Optional[Any]]:
        """Apply corrections to Step1/Step2 outputs.
        
        Args:
            corrections: List of Correction objects from LLM
            step1_output: Original Step1Output
            step2_output: Original Step2Output
        
        Returns:
            Tuple of (corrected_step1, corrected_step2)
        """
        # Deep copy to avoid modifying originals
        corrected_step1 = copy.deepcopy(step1_output) if step1_output else None
        corrected_step2 = copy.deepcopy(step2_output) if step2_output else None
        
        for correction in corrections:
            try:
                if correction.target_step == "step1" and corrected_step1:
                    corrected_step1 = self._apply_single_correction(
                        correction, corrected_step1
                    )
                elif correction.target_step == "step2" and corrected_step2:
                    corrected_step2 = self._apply_single_correction(
                        correction, corrected_step2
                    )
                logger.info(
                    f"Applied correction: {correction.operation} on "
                    f"{correction.target_step}.{correction.target_path}"
                )
            except Exception as e:
                logger.warning(
                    f"Failed to apply correction {correction.operation} on "
                    f"{correction.target_path}: {e}"
                )
        
        return corrected_step1, corrected_step2
    
    def _apply_single_correction(
        self,
        correction: Correction,
        output: Any,
    ) -> Any:
        """Apply a single correction to an output object.
        
        Args:
            correction: Correction to apply
            output: Output object (Step1Output or Step2Output)
        
        Returns:
            Modified output object
        """
        operation = correction.operation
        path = correction.target_path
        value = correction.corrected_value
        
        # Convert value to proper type based on target path
        value = self._convert_value_for_path(path, value)
        
        if operation == CorrectionOperation.REMOVE_DUPLICATE_MEASURES:
            return self._remove_duplicate_measures(output, path)
        elif operation == CorrectionOperation.REPLACE_FIELD:
            return self._set_value_at_path(output, path, value)
        elif operation == CorrectionOperation.REMOVE_FIELD:
            return self._remove_field_at_path(output, path, value)
        elif operation == CorrectionOperation.ADD_FIELD:
            return self._add_field_at_path(output, path, value)
        elif operation == CorrectionOperation.UPDATE_VALUE:
            return self._set_value_at_path(output, path, value)
        else:
            logger.warning(f"Unknown correction operation: {operation}")
            return output
    
    def _convert_value_for_path(self, path: str, value: Any) -> Any:
        """Convert value to proper type based on target path.
        
        Handles type mismatches between LLM output and expected schema:
        - partition_by: List[str] -> List[DimensionField]
        - where.dimensions: List[str] -> List[DimensionField]
        - what.measures: List[str] -> List[MeasureField]
        
        Args:
            path: Target path (e.g., "computations[0].partition_by")
            value: Value from LLM (may be wrong type)
        
        Returns:
            Converted value with correct type
        """
        if value is None:
            return value
        
        # Import field models
        from tableau_assistant.src.core.models.fields import DimensionField, MeasureField
        
        # Check if path ends with partition_by or contains dimension-related fields
        path_lower = path.lower()
        
        if "partition_by" in path_lower:
            # partition_by expects List[DimensionField]
            return self._convert_to_dimension_fields(value, DimensionField)
        
        if path_lower.endswith("dimensions") or "where.dimensions" in path_lower:
            # dimensions expects List[DimensionField]
            return self._convert_to_dimension_fields(value, DimensionField)
        
        if path_lower.endswith("measures") or "what.measures" in path_lower:
            # measures expects List[MeasureField]
            return self._convert_to_measure_fields(value, MeasureField)
        
        return value
    
    def _convert_to_dimension_fields(self, value: Any, field_class: type) -> Any:
        """Convert value to List[DimensionField].
        
        Handles:
        - ["Category"] -> [DimensionField(field_name="Category")]
        - [{"field_name": "Category"}] -> [DimensionField(field_name="Category")]
        - Already DimensionField objects -> unchanged
        """
        if not isinstance(value, list):
            return value
        
        result = []
        for item in value:
            if isinstance(item, str):
                # String -> DimensionField
                result.append(field_class(field_name=item))
                logger.debug(f"Converted string '{item}' to DimensionField")
            elif isinstance(item, dict):
                # Dict -> DimensionField (if has field_name)
                if "field_name" in item:
                    try:
                        result.append(field_class(**item))
                    except Exception as e:
                        logger.warning(f"Failed to create DimensionField from dict: {e}")
                        result.append(item)
                else:
                    result.append(item)
            elif hasattr(item, "field_name"):
                # Already a field object
                result.append(item)
            else:
                result.append(item)
        
        return result
    
    def _convert_to_measure_fields(self, value: Any, field_class: type) -> Any:
        """Convert value to List[MeasureField].
        
        Handles:
        - ["Sales"] -> [MeasureField(field_name="Sales")]
        - [{"field_name": "Sales", "aggregation": "SUM"}] -> [MeasureField(...)]
        - Already MeasureField objects -> unchanged
        """
        if not isinstance(value, list):
            return value
        
        result = []
        for item in value:
            if isinstance(item, str):
                # String -> MeasureField with default aggregation
                result.append(field_class(field_name=item))
                logger.debug(f"Converted string '{item}' to MeasureField")
            elif isinstance(item, dict):
                # Dict -> MeasureField (if has field_name)
                if "field_name" in item:
                    try:
                        result.append(field_class(**item))
                    except Exception as e:
                        logger.warning(f"Failed to create MeasureField from dict: {e}")
                        result.append(item)
                else:
                    result.append(item)
            elif hasattr(item, "field_name"):
                # Already a field object
                result.append(item)
            else:
                result.append(item)
        
        return result
    
    def _remove_duplicate_measures(self, output: Any, path: str) -> Any:
        """Remove duplicate measures, keeping only base measures.
        
        For "Field X isn't unique" errors, this removes measures with
        the same field_name, keeping only the one without alias (base measure).
        """
        # Navigate to the measures list
        measures = self._get_value_at_path(output, path)
        if not measures or not isinstance(measures, list):
            return output
        
        # Group by field_name
        seen_fields: Dict[str, List[Any]] = {}
        for measure in measures:
            field_name = getattr(measure, 'field_name', None)
            if field_name:
                if field_name not in seen_fields:
                    seen_fields[field_name] = []
                seen_fields[field_name].append(measure)
        
        # Keep only base measures (no alias or first occurrence)
        unique_measures = []
        for field_name, field_measures in seen_fields.items():
            if len(field_measures) == 1:
                unique_measures.append(field_measures[0])
            else:
                # Prefer measure without alias
                base_measure = None
                for m in field_measures:
                    alias = getattr(m, 'alias', None)
                    if not alias:
                        base_measure = m
                        break
                if base_measure:
                    unique_measures.append(base_measure)
                else:
                    # If all have aliases, keep first one
                    unique_measures.append(field_measures[0])
                logger.info(
                    f"Removed duplicate measures for '{field_name}', "
                    f"kept {len(unique_measures)} of {len(field_measures)}"
                )
        
        # Set the deduplicated list back
        return self._set_value_at_path(output, path, unique_measures)

    def _get_value_at_path(self, obj: Any, path: str) -> Any:
        """Get value at a JSON-like path.
        
        Supports paths like: what.measures, computations[0].target
        """
        parts = self._parse_path(path)
        current = obj
        
        for part in parts:
            if isinstance(part, int):
                # Array index
                if isinstance(current, list) and 0 <= part < len(current):
                    current = current[part]
                else:
                    return None
            elif isinstance(part, str):
                # Object attribute
                if hasattr(current, part):
                    current = getattr(current, part)
                elif isinstance(current, dict) and part in current:
                    current = current[part]
                else:
                    return None
        
        return current
    
    def _set_value_at_path(self, obj: Any, path: str, value: Any) -> Any:
        """Set value at a JSON-like path.
        
        Supports paths like: what.measures, computations[0].target
        """
        parts = self._parse_path(path)
        if not parts:
            return obj
        
        # Navigate to parent
        current = obj
        for part in parts[:-1]:
            if isinstance(part, int):
                if isinstance(current, list) and 0 <= part < len(current):
                    current = current[part]
                else:
                    return obj
            elif isinstance(part, str):
                if hasattr(current, part):
                    current = getattr(current, part)
                elif isinstance(current, dict) and part in current:
                    current = current[part]
                else:
                    return obj
        
        # Set the final value
        final_part = parts[-1]
        if isinstance(final_part, int):
            if isinstance(current, list) and 0 <= final_part < len(current):
                current[final_part] = value
        elif isinstance(final_part, str):
            if hasattr(current, final_part):
                setattr(current, final_part, value)
            elif isinstance(current, dict):
                current[final_part] = value
        
        return obj
    
    def _remove_field_at_path(self, obj: Any, path: str, value: Any) -> Any:
        """Remove a value from a list at path."""
        target_list = self._get_value_at_path(obj, path)
        if isinstance(target_list, list) and value in target_list:
            target_list.remove(value)
        return obj
    
    def _add_field_at_path(self, obj: Any, path: str, value: Any) -> Any:
        """Add a value to a list at path."""
        target_list = self._get_value_at_path(obj, path)
        if isinstance(target_list, list):
            target_list.append(value)
        return obj
    
    def _parse_path(self, path: str) -> List[Any]:
        """Parse a JSON-like path into parts.
        
        Examples:
            "what.measures" -> ["what", "measures"]
            "computations[0].target" -> ["computations", 0, "target"]
        """
        import re
        parts = []
        # Split by dots, but handle array indices
        tokens = re.split(r'\.', path)
        for token in tokens:
            # Check for array index
            match = re.match(r'(\w+)\[(\d+)\]', token)
            if match:
                parts.append(match.group(1))
                parts.append(int(match.group(2)))
            else:
                parts.append(token)
        return parts
    
    def _format_pipeline_context(self, context: Dict[str, Any]) -> str:
        """Format pipeline context for prompt."""
        if not context:
            return "无上下文信息"
        
        lines = []
        
        if "semantic_query" in context and context["semantic_query"]:
            lines.append("### SemanticQuery:")
            lines.append(f"  {context['semantic_query']}")
        
        if "mapped_query" in context and context["mapped_query"]:
            lines.append("### MappedQuery:")
            lines.append(f"  {context['mapped_query']}")
        
        if "vizql_query" in context and context["vizql_query"]:
            lines.append("### VizQL Query:")
            lines.append(f"  {context['vizql_query']}")
        
        return "\n".join(lines) if lines else "无上下文信息"
    
    def _format_retry_history(self, history: List[RetryRecord]) -> str:
        """Format retry history for prompt."""
        if not history:
            return ""
        
        lines = []
        for i, record in enumerate(history, 1):
            lines.append(f"{i}. {record}")
        return "\n".join(lines)
    
    def _count_retries_for_step(self, history: List[RetryRecord], step: str) -> int:
        """Count how many times a step has been retried."""
        return sum(1 for record in history if record.step == step and not record.success)
    
    def _handle_parse_error(
        self,
        error: QueryError,
        retry_history: List[RetryRecord],
    ) -> ReActOutput:
        """处理 Step1/Step2 的解析失败错误。
        
        解析失败通常是由于：
        1. JSON 格式错误
        2. Pydantic 校验失败
        3. 枚举值不合法
        4. 必填字段缺失
        
        策略：
        - 如果重试次数 < max_retries：RETRY 并提供结构化错误反馈
        - 否则：ABORT
        
        Args:
            error: QueryError（type 为 STEP1_PARSE_ERROR 或 STEP2_PARSE_ERROR）
            retry_history: 重试历史
        
        Returns:
            ReActOutput
        """
        step = error.step
        step_retry_count = self._count_retries_for_step(retry_history, step)
        
        if step_retry_count >= self.max_retries_per_step:
            # 达到最大重试次数，放弃
            logger.info(f"解析失败已达最大重试次数 ({self.max_retries_per_step})，放弃")
            
            thought = ReActThought(
                error_source=step,
                error_category=ErrorCategory.FORMAT_ERROR,
                root_cause_analysis=f"{step} 输出解析失败，已重试 {step_retry_count} 次仍然失败",
                can_correct=False,
                can_retry=False,
                needs_clarification=False,
                reasoning=f"解析失败通常是模型输出格式问题，已重试多次仍失败，需要放弃",
            )
            
            action = ReActAction(
                action_type=ReActActionType.ABORT,
                user_message=f"抱歉，处理您的请求时遇到问题。请尝试换一种方式描述您的问题。",
            )
            
            return ReActOutput(thought=thought, action=action)
        
        # 构建重试指导
        error_details = error.details or {}
        original_error = error_details.get("original_error", error.message)
        
        # 根据错误类型提供具体指导
        retry_guidance = self._build_parse_error_guidance(original_error)
        
        thought = ReActThought(
            error_source=step,
            error_category=ErrorCategory.FORMAT_ERROR,
            root_cause_analysis=f"{step} 输出解析失败: {original_error}",
            can_correct=False,
            can_retry=True,
            needs_clarification=False,
            reasoning=f"解析失败可以通过重试并提供错误反馈来修复",
        )
        
        action = ReActAction(
            action_type=ReActActionType.RETRY,
            retry_from=step,
            retry_guidance=retry_guidance,
        )
        
        logger.info(f"解析失败处理: RETRY {step} with guidance")
        
        return ReActOutput(thought=thought, action=action)
    
    def _build_parse_error_guidance(self, error_message: str) -> str:
        """根据解析错误类型构建重试指导。
        
        Args:
            error_message: 原始错误信息
        
        Returns:
            结构化的重试指导
        """
        error_lower = error_message.lower()
        
        if "json" in error_lower and "decode" in error_lower:
            return (
                "解析失败：输出不是有效的 JSON 格式。\n"
                "请确保：\n"
                "1. 输出是完整的 JSON 对象（以 { 开始，以 } 结束）\n"
                "2. 所有字符串都用双引号包裹\n"
                "3. 没有多余的逗号或缺少逗号\n"
                "4. 布尔值使用 true/false（小写）\n"
                "请重新生成符合 JSON 格式的输出。"
            )
        
        if "validation" in error_lower or "pydantic" in error_lower:
            return (
                "解析失败：输出格式不符合预期的数据结构。\n"
                f"错误详情：{error_message}\n"
                "请检查：\n"
                "1. 所有必填字段都已提供\n"
                "2. 字段类型正确（字符串、数字、列表等）\n"
                "3. 枚举值使用正确的选项\n"
                "请根据错误提示修正后重新输出。"
            )
        
        if "enum" in error_lower or "not a valid" in error_lower:
            return (
                "解析失败：使用了不合法的枚举值。\n"
                f"错误详情：{error_message}\n"
                "请使用文档中定义的合法枚举值，并确保大小写完全匹配。"
            )
        
        # 通用指导
        return (
            f"解析失败：{error_message}\n"
            "请严格按照 JSON 格式输出，确保所有字段都符合预期的数据结构。"
        )
    
    def _create_max_retry_output(self, error: QueryError, step: str) -> ReActOutput:
        """Create output when max retries reached."""
        thought = ReActThought(
            error_source=step,
            error_category=ErrorCategory.UNKNOWN,
            root_cause_analysis=f"步骤 {step} 已达到最大重试次数 ({self.max_retries_per_step})，无法继续重试",
            can_correct=False,
            can_retry=False,
            needs_clarification=False,
            reasoning=f"已尝试 {self.max_retries_per_step} 次仍然失败，需要放弃并告知用户",
        )
        
        action = ReActAction(
            action_type=ReActActionType.ABORT,
            user_message=f"抱歉，处理您的请求时遇到问题：{error.message}。请尝试换一种方式描述您的问题，或者简化您的查询条件。",
        )
        
        return ReActOutput(thought=thought, action=action)
    
    def _create_fallback_output(self, error: QueryError) -> ReActOutput:
        """Create fallback output when LLM fails."""
        thought = ReActThought(
            error_source=error.step,
            error_category=ErrorCategory.UNKNOWN,
            root_cause_analysis=f"错误分析失败。原始错误: {error.message}",
            can_correct=False,
            can_retry=False,
            needs_clarification=False,
            reasoning="无法分析错误，返回原始错误信息给用户",
        )
        
        action = ReActAction(
            action_type=ReActActionType.ABORT,
            user_message=f"抱歉，处理您的请求时遇到问题。{error.message}",
        )
        
        return ReActOutput(thought=thought, action=action)
    
    def create_retry_record(
        self,
        step: str,
        error_message: str,
        action_taken: str,
        success: bool = False,
    ) -> RetryRecord:
        """Create a retry record for tracking history.
        
        Args:
            step: Which step was retried
            error_message: The error that triggered the retry
            action_taken: What action was taken (CORRECT/RETRY/etc.)
            success: Whether the retry was successful
        
        Returns:
            RetryRecord
        """
        return RetryRecord(
            step=step,
            error_message=error_message,
            action_taken=action_taken,
            success=success,
        )


__all__ = ["ReActErrorHandler", "RetryRecord"]
