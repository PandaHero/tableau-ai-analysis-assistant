# -*- coding: utf-8 -*-
"""验证相关节点：输出验证、筛选值验证"""
import logging
import time
from datetime import datetime
from typing import Any, Optional

from langgraph.types import interrupt, RunnableConfig

from ..state import SemanticParserState
from ..components import FilterValueValidator, FieldValueCache, OutputValidator
from ..schemas.output import SemanticOutput, ClarificationSource
from ..schemas.prefilter import FieldRAGResult
from ..node_utils import parse_field_candidates, classify_fields, merge_metrics
from analytics_assistant.src.agents.base.context import get_context

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


async def output_validator_node(state: SemanticParserState) -> dict[str, Any]:
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
        output["needs_clarification"] = True
        output["clarification_question"] = result.clarification_message
        output["clarification_source"] = ClarificationSource.SEMANTIC_UNDERSTANDING.value

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

    # 检查是否有需要用户确认的筛选值
    pending_confirmations = [
        r for r in summary.results
        if r.needs_confirmation and len(r.similar_values) > 0
    ]

    if pending_confirmations:
        confirmation_request = {
            "type": "filter_value_confirmation",
            "pending": [
                {
                    "field_name": r.field_name,
                    "requested_value": r.requested_value,
                    "similar_values": r.similar_values,
                    "message": r.message,
                }
                for r in pending_confirmations
            ],
        }

        user_response = interrupt(confirmation_request)

        if user_response and "confirmations" in user_response:
            new_confirmations = []
            for field_name, confirmed_value in user_response["confirmations"].items():
                original_value = next(
                    (r.requested_value for r in pending_confirmations
                     if r.field_name == field_name),
                    None
                )
                if original_value:
                    new_confirmations.append({
                        "field_name": field_name,
                        "original_value": original_value,
                        "confirmed_value": confirmed_value,
                        "confirmed_at": datetime.now().isoformat(),
                    })

            all_confirmations = existing_confirmations + new_confirmations

            # 逐字段应用确认（避免不同字段相同 original_value 时互相覆盖）
            updated_output = semantic_output
            for conf in new_confirmations:
                updated_output = validator.apply_single_confirmation(
                    updated_output,
                    conf["field_name"],
                    conf["original_value"],
                    conf["confirmed_value"],
                )
            return {
                "semantic_output": updated_output.model_dump(),
                "filter_validation_result": summary.model_dump(),
                "confirmed_filters": all_confirmations,
            }

    # 检查是否有无法解决的筛选值
    if summary.has_unresolvable_filters:
        unresolvable = [
            r for r in summary.results
            if r.is_unresolvable
        ]
        messages = [r.message for r in unresolvable if r.message]

        return {
            "semantic_output": semantic_output.model_dump(),
            "filter_validation_result": summary.model_dump(),
            "confirmed_filters": existing_confirmations,
            "needs_clarification": True,
            "clarification_question": "\n".join(messages) if messages else "筛选值无法匹配，请检查输入",
            "clarification_source": ClarificationSource.FILTER_VALIDATOR.value,
        }

    logger.info(
        f"filter_validator_node: 验证完成, all_valid={summary.all_valid}"
    )

    return {
        "semantic_output": semantic_output.model_dump(),
        "filter_validation_result": summary.model_dump(),
        "confirmed_filters": existing_confirmations,
    }
