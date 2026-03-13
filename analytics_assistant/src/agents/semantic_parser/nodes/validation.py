# -*- coding: utf-8 -*-
"""验证相关节点：输出验证、筛选值验证"""
import logging
import time
from typing import Any, Optional

from langgraph.types import interrupt
from langgraph.types import RunnableConfig

from ..state import SemanticParserState
from ..components import FilterValueValidator, FieldValueCache, OutputValidator
from ..schemas.output import SemanticOutput, ClarificationSource
from ..schemas.prefilter import FieldRAGResult
from ..node_utils import parse_field_candidates, classify_fields, merge_metrics
from analytics_assistant.src.agents.base.context import get_context
from .understanding import semantic_understanding_node

logger = logging.getLogger(__name__)

_field_value_cache: Optional[FieldValueCache] = None
_output_validator: Optional[OutputValidator] = None


def _get_field_value_cache() -> FieldValueCache:
    """惰性获取 FieldValueCache 单例，使缓存跨调用复用。"""
    global _field_value_cache
    if _field_value_cache is None:
        _field_value_cache = FieldValueCache()
    return _field_value_cache


def _get_output_validator() -> OutputValidator:
    """惰性获取 OutputValidator 单例，避免重复加载配置。"""
    global _output_validator
    if _output_validator is None:
        _output_validator = OutputValidator()
    return _output_validator


def _resolve_resumed_text(value: Any, *, label: str) -> str:
    resolved = str(value or "").strip()
    if not resolved:
        raise ValueError(f"{label} resume value must not be empty")
    return resolved


def _append_clarification_turn(
    history: Any,
    *,
    assistant_message: str,
    slot_name: str,
    user_value: str,
) -> list[dict[str, str]]:
    updated_history = list(history or [])
    normalized_assistant_message = str(assistant_message or "").strip()
    normalized_slot_name = str(slot_name or "").strip() or "field"
    normalized_user_value = str(user_value or "").strip()

    if normalized_assistant_message:
        updated_history.append({
            "role": "assistant",
            "content": normalized_assistant_message,
        })
    if normalized_user_value:
        updated_history.append({
            "role": "user",
            "content": f"{normalized_slot_name}: {normalized_user_value}",
        })
    return updated_history


async def output_validator_node(
    state: SemanticParserState,
    config: Optional[RunnableConfig] = None,
) -> dict[str, Any]:
    """输出验证节点

    验证 SemanticUnderstanding 输出，自动修正简单错误。

    输入：
    - state["semantic_output"]: 语义输出
    - state["field_candidates"]: 字段候选列表

    输出：
    - semantic_output: 验证/修正后的语义输出
    - validation_result: 验证结果
    - needs_clarification: 是否需要澄清
    - clarification_question: 澄清问题
    """
    start_time = time.time()

    semantic_output_raw = state.get("semantic_output")
    field_candidates_raw = state.get("field_candidates", [])

    if not semantic_output_raw:
        logger.warning("output_validator_node: 缺少 semantic_output")
        return {}

    field_candidates = parse_field_candidates(field_candidates_raw)
    classified = classify_fields(field_candidates)

    field_rag_result = FieldRAGResult(
        measures=classified["measures"],
        dimensions=classified["dimensions"],
        time_fields=classified["time_fields"],
    )

    validator = _get_output_validator()
    result = validator.validate(
        semantic_output=semantic_output_raw,
        field_rag_result=field_rag_result,
    )

    elapsed_ms = (time.time() - start_time) * 1000
    logger.info(
        f"output_validator_node: 完成, "
        f"is_valid={result.is_valid}, "
        f"errors={len(result.errors)}, "
        f"elapsed={elapsed_ms:.1f}ms"
    )

    output: dict[str, Any] = {
        "validation_result": result.model_dump(),
        "optimization_metrics": merge_metrics(state, output_validator_ms=elapsed_ms),
    }

    if result.corrected_output:
        output["semantic_output"] = result.corrected_output

    if result.needs_clarification:
        clarification_message = str(result.clarification_message or "").strip()
        clarified_value = _resolve_resumed_text(
            interrupt({
                "interrupt_type": "missing_slot",
                "message": clarification_message,
                "source": ClarificationSource.SEMANTIC_UNDERSTANDING.value,
                "slot_name": "field",
                "options": [],
                "resume_strategy": "langgraph_native",
            }),
            label="missing_slot",
        )

        resumed_state = dict(state)
        resumed_state.pop("modular_prompt", None)
        resumed_state["chat_history"] = _append_clarification_turn(
            state.get("chat_history"),
            assistant_message=clarification_message,
            slot_name="field",
            user_value=clarified_value,
        )

        semantic_retry_output = await semantic_understanding_node(resumed_state, config)
        validated_retry_output = await output_validator_node(
            {
                **resumed_state,
                **semantic_retry_output,
            },
            config,
        )
        for carried_key in ("semantic_output", "thinking", "global_understanding", "analysis_plan"):
            if carried_key in semantic_retry_output and carried_key not in validated_retry_output:
                validated_retry_output[carried_key] = semantic_retry_output[carried_key]
        validated_retry_output["chat_history"] = list(
            semantic_retry_output.get("chat_history")
            or resumed_state.get("chat_history")
            or []
        )
        combined_retry_metrics = dict(
            semantic_retry_output.get("optimization_metrics") or {}
        )
        combined_retry_metrics.update(
            validated_retry_output.get("optimization_metrics") or {}
        )
        validated_retry_output["optimization_metrics"] = combined_retry_metrics
        return validated_retry_output

    return output

async def filter_validator_node(
    state: SemanticParserState,
    config: Optional[RunnableConfig] = None,
) -> dict[str, Any]:
    """筛选值验证节点

    验证筛选条件的值是否存在于数据源中。
    当需要用户确认时，使用 LangGraph interrupt() 暂停执行。

    输入：
    - state["semantic_output"]: 语义输出
    - state["confirmed_filters"]: 已确认的筛选值（多轮累积）
    - config: RunnableConfig，包含 WorkflowContext

    输出：
    - semantic_output: 更新后的语义输出
    - filter_validation_result: 验证结果
    - confirmed_filters: 累积的确认结果
    - needs_clarification: 是否需要澄清（无相似值时）
    - clarification_question: 澄清问题
    - clarification_source: 澄清来源
    """
    semantic_output_raw = state.get("semantic_output")

    if not semantic_output_raw:
        logger.warning("filter_validator_node: 缺少 semantic_output")
        return {}

    semantic_output = SemanticOutput.model_validate(semantic_output_raw)
    existing_confirmations = state.get("confirmed_filters", [])

    ctx = get_context(config) if config else None

    if ctx is None:
        logger.warning(
            "filter_validator_node: 未提供 WorkflowContext，跳过筛选值验证。"
        )
        return {
            "semantic_output": semantic_output.model_dump(),
            "filter_validation_result": {
                "results": [],
                "all_valid": True,
                "has_unresolvable_filters": False,
                "needs_confirmation": False,
            },
            "confirmed_filters": existing_confirmations,
        }

    platform_adapter = ctx.platform_adapter
    data_model = ctx.data_model
    datasource_id = ctx.datasource_luid

    if platform_adapter is None or data_model is None:
        logger.warning(
            "filter_validator_node: 缺少 platform_adapter 或 data_model，跳过验证。"
        )
        return {
            "semantic_output": semantic_output.model_dump(),
            "filter_validation_result": {
                "results": [],
                "all_valid": True,
                "has_unresolvable_filters": False,
                "needs_confirmation": False,
            },
            "confirmed_filters": existing_confirmations,
        }

    validator = FilterValueValidator(
        platform_adapter=platform_adapter,
        field_value_cache=_get_field_value_cache(),
    )

    # 应用已有的确认到 semantic_output
    if existing_confirmations:
        for conf in existing_confirmations:
            semantic_output = validator.apply_single_confirmation(
                semantic_output,
                conf["field_name"],
                conf["original_value"],
                conf["confirmed_value"],
            )

    # 准备平台特定参数
    platform_kwargs = {}
    if ctx.auth is not None:
        if hasattr(ctx.auth, 'api_key'):
            platform_kwargs['api_key'] = ctx.auth.api_key
        if hasattr(ctx.auth, 'site'):
            platform_kwargs['site'] = ctx.auth.site

    try:
        summary = await validator.validate(
            semantic_output=semantic_output,
            data_model=data_model,
            datasource_id=datasource_id,
            **platform_kwargs,
        )
    except Exception as e:
        logger.error(f"filter_validator_node: 验证失败: {e}")
        return {
            "semantic_output": semantic_output.model_dump(),
            "filter_validation_result": {
                "results": [],
                "all_valid": True,
                "has_unresolvable_filters": False,
                "needs_confirmation": False,
            },
            "confirmed_filters": existing_confirmations,
        }
    confirmed_filters = list(existing_confirmations)

    while True:
        pending_confirmations = [
            r for r in summary.results
            if r.needs_confirmation and len(r.similar_values) > 0
        ]

        if pending_confirmations:
            first_pending = pending_confirmations[0]
            confirmed_value = str(
                interrupt({
                    "interrupt_type": "value_confirm",
                    "message": (
                        first_pending.message
                        or f"Please confirm the filter value for {first_pending.field_name}"
                    ),
                    "source": ClarificationSource.FILTER_VALIDATOR.value,
                    "field": first_pending.field_name,
                    "requested_value": first_pending.requested_value,
                    "candidates": list(first_pending.similar_values),
                    "resume_strategy": "langgraph_native",
                })
                or ""
            ).strip()
            if not confirmed_value:
                raise ValueError("value_confirm resume value must not be empty")

            confirmed_filters.append({
                "field_name": first_pending.field_name,
                "original_value": first_pending.requested_value,
                "confirmed_value": confirmed_value,
            })
            semantic_output = validator.apply_single_confirmation(
                semantic_output,
                first_pending.field_name,
                first_pending.requested_value,
                confirmed_value,
            )
            summary = await validator.validate(
                semantic_output=semantic_output,
                data_model=data_model,
                datasource_id=datasource_id,
                **platform_kwargs,
            )
            continue

        if summary.has_unresolvable_filters:
            unresolvable = [r for r in summary.results if r.is_unresolvable]
            first_unresolvable = unresolvable[0] if unresolvable else None
            if first_unresolvable is None:
                raise ValueError("unresolvable filter summary is missing result details")

            messages = [r.message for r in unresolvable if r.message]
            replacement_value = _resolve_resumed_text(
                interrupt({
                    "interrupt_type": "missing_slot",
                    "message": (
                        "\n".join(messages)
                        if messages
                        else "Filter value could not be resolved"
                    ),
                    "source": ClarificationSource.FILTER_VALIDATOR.value,
                    "slot_name": "filter_value",
                    "field": first_unresolvable.field_name,
                    "requested_value": first_unresolvable.requested_value,
                    "options": [],
                    "resume_strategy": "langgraph_native",
                }),
                label="missing_slot",
            )

            confirmed_filters.append({
                "field_name": first_unresolvable.field_name,
                "original_value": first_unresolvable.requested_value,
                "confirmed_value": replacement_value,
            })
            semantic_output = validator.apply_single_confirmation(
                semantic_output,
                first_unresolvable.field_name,
                first_unresolvable.requested_value,
                replacement_value,
            )
            summary = await validator.validate(
                semantic_output=semantic_output,
                data_model=data_model,
                datasource_id=datasource_id,
                **platform_kwargs,
            )
            continue
        break

    logger.info(
        f"filter_validator_node: validation complete, all_valid={summary.all_valid}"
    )

    return {
        "semantic_output": semantic_output.model_dump(),
        "filter_validation_result": summary.model_dump(),
        "confirmed_filters": confirmed_filters,
    }
