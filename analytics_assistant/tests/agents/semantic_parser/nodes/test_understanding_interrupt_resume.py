# -*- coding: utf-8 -*-
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from analytics_assistant.src.agents.semantic_parser.nodes.understanding import (
    semantic_understanding_node,
)
from analytics_assistant.src.agents.semantic_parser.schemas.output import (
    SemanticOutput,
    SelfCheck,
    What,
    Where,
)
from analytics_assistant.src.agents.semantic_parser.schemas.prefilter import (
    ComplexityType,
    FeatureExtractionOutput,
    PrefilterResult,
)
from analytics_assistant.src.core.schemas.field_candidate import FieldCandidate


def _build_state() -> dict:
    return {
        "question": "show sales by region",
        "chat_history": [{"role": "user", "content": "show sales by region"}],
        "current_time": "2026-03-11T00:00:00",
        "prefilter_result": PrefilterResult(
            detected_complexity=[ComplexityType.SIMPLE],
            detected_language="en",
        ).model_dump(),
        "feature_extraction_output": FeatureExtractionOutput(
            required_measures=["sales"],
            required_dimensions=["date"],
            confirmed_time_hints=["last_30_days"],
            confirmation_confidence=0.95,
            is_degraded=False,
        ).model_dump(),
        "few_shot_examples": [],
        "field_candidates": [
            FieldCandidate(
                field_name="Sales",
                field_caption="Sales",
                role="measure",
                confidence=0.95,
                match_type="exact",
            ).model_dump(),
            FieldCandidate(
                field_name="Region",
                field_caption="Region",
                role="dimension",
                confidence=0.95,
                match_type="exact",
            ).model_dump(),
        ],
    }


@pytest.mark.asyncio
@patch(
    "analytics_assistant.src.agents.semantic_parser.nodes.understanding.get_llm",
    return_value=MagicMock(),
)
@patch(
    "analytics_assistant.src.agents.semantic_parser.nodes.understanding.interrupt",
    return_value="last_30_days",
)
@patch(
    "analytics_assistant.src.agents.semantic_parser.nodes.understanding.stream_llm_structured",
    new_callable=AsyncMock,
)
async def test_semantic_understanding_node_resumes_missing_slot_natively(
    mock_stream_llm,
    mock_interrupt,
    _mock_get_llm,
):
    mock_stream_llm.side_effect = [
        (
            SemanticOutput(
                restated_question="show sales by region",
                what=What(measures=["Sales"]),
                where=Where(dimensions=["Region"]),
                needs_clarification=True,
                clarification_question="Select timeframe",
                clarification_options=["last_7_days", "last_30_days"],
                self_check=SelfCheck(
                    field_mapping_confidence=0.6,
                    time_range_confidence=0.4,
                    computation_confidence=0.9,
                    overall_confidence=0.55,
                ),
            ),
            None,
        ),
        (
            SemanticOutput(
                restated_question="show sales by region for last 30 days",
                what=What(measures=["Sales"]),
                where=Where(dimensions=["Region"]),
                self_check=SelfCheck(
                    field_mapping_confidence=0.9,
                    time_range_confidence=0.9,
                    computation_confidence=0.9,
                    overall_confidence=0.9,
                ),
            ),
            None,
        ),
    ]

    result = await semantic_understanding_node(_build_state())

    assert "needs_clarification" not in result
    assert result["semantic_output"]["restated_question"] == (
        "show sales by region for last 30 days"
    )
    assert result["chat_history"][-2] == {
        "role": "assistant",
        "content": "Select timeframe",
    }
    assert result["chat_history"][-1] == {
        "role": "user",
        "content": "timeframe: last_30_days",
    }

    interrupt_payload = mock_interrupt.call_args.args[0]
    assert interrupt_payload["interrupt_type"] == "missing_slot"
    assert interrupt_payload["slot_name"] == "timeframe"
    assert interrupt_payload["resume_strategy"] == "langgraph_native"
    assert mock_stream_llm.await_count == 2


@pytest.mark.asyncio
@patch(
    "analytics_assistant.src.agents.semantic_parser.nodes.understanding.get_llm",
    return_value=MagicMock(),
)
@patch(
    "analytics_assistant.src.agents.semantic_parser.nodes.understanding.interrupt",
    return_value="show sales by region",
)
@patch(
    "analytics_assistant.src.agents.semantic_parser.nodes.understanding.stream_llm_structured",
    new_callable=AsyncMock,
)
async def test_semantic_understanding_node_resumes_missing_question_natively(
    mock_stream_llm,
    mock_interrupt,
    _mock_get_llm,
):
    mock_stream_llm.return_value = (
        SemanticOutput(
            restated_question="show sales by region",
            what=What(measures=["Sales"]),
            where=Where(dimensions=["Region"]),
            self_check=SelfCheck(
                field_mapping_confidence=0.9,
                time_range_confidence=0.9,
                computation_confidence=0.9,
                overall_confidence=0.9,
            ),
        ),
        None,
    )

    state = _build_state()
    state["question"] = ""
    state["chat_history"] = []

    result = await semantic_understanding_node(state)

    assert result["semantic_output"]["restated_question"] == "show sales by region"
    assert result["chat_history"] == [
        {"role": "assistant", "content": "请输入您的问题"},
        {"role": "user", "content": "show sales by region"},
    ]
    interrupt_payload = mock_interrupt.call_args.args[0]
    assert interrupt_payload["interrupt_type"] == "missing_slot"
    assert interrupt_payload["slot_name"] == "question"
    assert interrupt_payload["resume_strategy"] == "langgraph_native"
    assert mock_stream_llm.await_count == 1
