# -*- coding: utf-8 -*-
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from analytics_assistant.src.agents.semantic_parser.components.filter_validator import (
    FilterValueValidator,
)
from analytics_assistant.src.agents.semantic_parser.nodes.validation import (
    filter_validator_node,
    output_validator_node,
)
from analytics_assistant.src.agents.semantic_parser.schemas.filters import (
    FilterValidationResult,
    FilterValidationSummary,
    FilterValidationType,
)
from analytics_assistant.src.agents.semantic_parser.schemas.prefilter import (
    OutputValidationError,
    ValidationErrorType,
    ValidationResult,
)
from analytics_assistant.src.agents.semantic_parser.schemas.output import (
    SemanticOutput,
    SelfCheck,
    What,
    Where,
)
from analytics_assistant.src.core.schemas.filters import SetFilter


def _make_semantic_output() -> dict:
    return SemanticOutput(
        restated_question="按地区查看销售额",
        what=What(measures=["Sales"]),
        where=Where(
            dimensions=["Region"],
            filters=[SetFilter(field_name="Region", values=["Eest"])],
        ),
        self_check=SelfCheck(
            field_mapping_confidence=0.9,
            time_range_confidence=0.9,
            computation_confidence=0.9,
            overall_confidence=0.9,
        ),
    ).model_dump()


@pytest.mark.asyncio
async def test_filter_validator_node_resumes_unresolvable_filter_with_native_interrupt():
    unresolved = FilterValidationSummary.from_results([
        FilterValidationResult(
            is_valid=False,
            field_name="Region",
            requested_value="Eest",
            validation_type=FilterValidationType.NOT_FOUND,
            is_unresolvable=True,
            message="未找到 Eest，请补充正确的地区值",
        )
    ])
    resolved = FilterValidationSummary.from_results([
        FilterValidationResult(
            is_valid=True,
            field_name="Region",
            requested_value="East",
            matched_values=["East"],
            validation_type=FilterValidationType.EXACT_MATCH,
        )
    ])

    validator = MagicMock()
    validator.validate = AsyncMock(side_effect=[unresolved, resolved])
    validator.apply_single_confirmation.side_effect = (
        lambda semantic_output, field_name, original_value, confirmed_value: (
            FilterValueValidator.apply_single_confirmation(
                validator,
                semantic_output,
                field_name,
                original_value,
                confirmed_value,
            )
        )
    )

    ctx = SimpleNamespace(
        platform_adapter=object(),
        data_model=object(),
        datasource_luid="ds_test",
        auth=None,
    )

    with patch(
        "analytics_assistant.src.agents.semantic_parser.nodes.validation.FilterValueValidator",
        return_value=validator,
    ), patch(
        "analytics_assistant.src.agents.semantic_parser.nodes.validation.interrupt",
        return_value="East",
    ) as mock_interrupt:
        result = await filter_validator_node(
            {
                "semantic_output": _make_semantic_output(),
                "confirmed_filters": [],
            },
            config={"configurable": {"workflow_context": ctx}},
        )

    assert result["confirmed_filters"] == [
        {
            "field_name": "Region",
            "original_value": "Eest",
            "confirmed_value": "East",
        }
    ]
    assert result["semantic_output"]["where"]["filters"][0]["values"] == ["East"]
    assert validator.validate.await_count == 2

    interrupt_payload = mock_interrupt.call_args.args[0]
    assert interrupt_payload["interrupt_type"] == "missing_slot"
    assert interrupt_payload["slot_name"] == "filter_value"
    assert interrupt_payload["field"] == "Region"
    assert interrupt_payload["requested_value"] == "Eest"
    assert interrupt_payload["resume_strategy"] == "langgraph_native"


@pytest.mark.asyncio
async def test_output_validator_node_resumes_missing_slot_with_native_interrupt():
    validator = MagicMock()
    validator.validate.side_effect = [
        ValidationResult(
            is_valid=False,
            errors=[
                OutputValidationError(
                    error_type=ValidationErrorType.INVALID_FIELD,
                    field_name="Regon",
                    message="Unknown field Regon",
                    auto_correctable=False,
                )
            ],
            needs_clarification=True,
            clarification_message="Please specify the correct field",
        ),
        ValidationResult(
            is_valid=True,
            errors=[],
        ),
    ]

    semantic_retry_output = {
        "semantic_output": SemanticOutput(
            restated_question="show sales by region",
            what=What(measures=["Sales"]),
            where=Where(dimensions=["Region"]),
            self_check=SelfCheck(
                field_mapping_confidence=0.9,
                time_range_confidence=0.9,
                computation_confidence=0.9,
                overall_confidence=0.9,
            ),
        ).model_dump(),
        "chat_history": [
            {"role": "user", "content": "show sales"},
            {"role": "assistant", "content": "Please specify the correct field"},
            {"role": "user", "content": "field: Region"},
        ],
        "optimization_metrics": {"semantic_understanding_ms": 9.5},
    }

    with patch(
        "analytics_assistant.src.agents.semantic_parser.nodes.validation._get_output_validator",
        return_value=validator,
    ), patch(
        "analytics_assistant.src.agents.semantic_parser.nodes.validation.interrupt",
        return_value="Region",
    ) as mock_interrupt, patch(
        "analytics_assistant.src.agents.semantic_parser.nodes.validation.semantic_understanding_node",
        new=AsyncMock(return_value=semantic_retry_output),
    ) as mock_semantic_retry:
        result = await output_validator_node(
            {
                "semantic_output": _make_semantic_output(),
                "field_candidates": [],
                "chat_history": [{"role": "user", "content": "show sales"}],
            }
        )

    assert result["validation_result"]["is_valid"] is True
    assert result["semantic_output"]["where"]["dimensions"][0]["field_name"] == "Region"
    assert result["chat_history"][-2:] == [
        {"role": "assistant", "content": "Please specify the correct field"},
        {"role": "user", "content": "field: Region"},
    ]
    assert result["optimization_metrics"]["semantic_understanding_ms"] == 9.5
    assert "output_validator_ms" in result["optimization_metrics"]

    interrupt_payload = mock_interrupt.call_args.args[0]
    assert interrupt_payload["interrupt_type"] == "missing_slot"
    assert interrupt_payload["slot_name"] == "field"
    assert interrupt_payload["resume_strategy"] == "langgraph_native"

    resumed_state = mock_semantic_retry.await_args.args[0]
    assert resumed_state["chat_history"][-2:] == [
        {"role": "assistant", "content": "Please specify the correct field"},
        {"role": "user", "content": "field: Region"},
    ]
