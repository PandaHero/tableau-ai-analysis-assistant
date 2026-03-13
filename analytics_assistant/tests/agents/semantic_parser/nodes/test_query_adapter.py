# -*- coding: utf-8 -*-
"""query_adapter 节点契约测试。"""

import pytest

from analytics_assistant.src.agents.semantic_parser.nodes.query_adapter import (
    query_adapter_node,
)
from analytics_assistant.src.agents.semantic_parser.schemas.output import (
    SemanticOutput,
    SelfCheck,
)


def _build_semantic_output() -> dict:
    return SemanticOutput(
        query_id="q-query-adapter",
        restated_question="show revenue",
        self_check=SelfCheck(
            field_mapping_confidence=0.92,
            time_range_confidence=0.91,
            computation_confidence=0.9,
            overall_confidence=0.91,
        ),
    ).model_dump()


@pytest.mark.asyncio
async def test_query_adapter_returns_compiler_input_contract_without_platform_adapter():
    state = {
        "semantic_output": _build_semantic_output(),
    }

    result = await query_adapter_node(state, config={})

    assert result["semantic_query"] == {
        "mode": "compiler_input",
        "source": "semantic_output",
        "query_id": "q-query-adapter",
        "restated_question": "show revenue",
    }


@pytest.mark.asyncio
async def test_query_adapter_keeps_compiler_contract_even_when_adapter_available():
    state = {
        "semantic_output": _build_semantic_output(),
    }

    result = await query_adapter_node(state, config={"configurable": {"unused": True}})

    assert result["semantic_query"] == {
        "mode": "compiler_input",
        "source": "semantic_output",
        "query_id": "q-query-adapter",
        "restated_question": "show revenue",
    }
