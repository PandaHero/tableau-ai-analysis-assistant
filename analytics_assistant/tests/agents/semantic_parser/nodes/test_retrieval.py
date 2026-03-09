# -*- coding: utf-8 -*-
"""
检索节点与 StepIntent 集成测试
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from analytics_assistant.src.agents.semantic_parser.nodes.retrieval import (
    _apply_step_intent_hints,
    field_retriever_node,
    few_shot_manager_node,
)
from analytics_assistant.src.agents.semantic_parser.schemas.planner import StepIntent
from analytics_assistant.src.agents.semantic_parser.schemas.prefilter import (
    FeatureExtractionOutput,
    FieldRAGResult,
)


def test_apply_step_intent_hints_merges_candidate_axes_into_dimensions():
    """follow-up step 的 candidate axes 应作为维度 hint 注入检索输入。"""
    feature_output = FeatureExtractionOutput(
        required_measures=["销售额"],
        required_dimensions=["地区"],
        confirmation_confidence=0.92,
        is_degraded=False,
    )
    step_intent = StepIntent(
        step_id="step-2",
        title="定位异常切片",
        question="按地区和产品找出异常切片",
        candidate_axes=["产品", "地区"],
    )

    merged = _apply_step_intent_hints(feature_output, step_intent)

    assert merged.required_dimensions == ["地区", "产品"]


@pytest.mark.asyncio
async def test_field_retriever_enables_rerank_for_step_intent_context():
    """即使是 simple query，只要存在 step intent 上下文也应启用 rerank。"""
    state = {
        "question": "按地区和产品找出异常切片",
        "feature_extraction_output": FeatureExtractionOutput(
            required_measures=["销售额"],
            required_dimensions=[],
            confirmation_confidence=0.95,
            is_degraded=False,
        ).model_dump(),
        "current_step_intent": StepIntent(
            step_id="step-2",
            title="定位异常切片",
            question="按地区和产品找出异常切片",
            candidate_axes=["产品"],
            depends_on=["step-1"],
            semantic_focus=["异常定位"],
        ).model_dump(),
    }

    fake_ctx = SimpleNamespace(
        data_model=None,
        datasource_luid="ds-test",
        field_semantic=None,
    )
    fake_rag_result = FieldRAGResult(measures=[], dimensions=[], time_fields=[])
    fake_retrieve = AsyncMock(return_value=fake_rag_result)

    with patch(
        "analytics_assistant.src.agents.semantic_parser.nodes.retrieval.get_context",
        return_value=fake_ctx,
    ), patch(
        "analytics_assistant.src.agents.semantic_parser.nodes.retrieval.FieldRetriever"
    ) as mock_retriever_cls:
        mock_retriever = mock_retriever_cls.return_value
        mock_retriever.retrieve = fake_retrieve

        result = await field_retriever_node(state, config={})

    assert mock_retriever_cls.call_args.kwargs["enable_rerank"] is True
    assert result["optimization_metrics"]["field_retriever_step_intent_focus"] is True


@pytest.mark.asyncio
async def test_few_shot_manager_does_not_skip_when_step_intent_exists():
    """follow-up step 即使 complexity=simple 也不应直接跳过 few-shot。"""
    state = {
        "question": "按地区和产品找出异常切片",
        "datasource_luid": "ds-test",
        "dynamic_schema_result": {"detected_complexity": ["simple"]},
        "current_step_intent": StepIntent(
            step_id="step-2",
            title="定位异常切片",
            question="按地区和产品找出异常切片",
            depends_on=["step-1"],
            semantic_focus=["异常定位", "产品"],
        ).model_dump(),
    }

    with patch(
        "analytics_assistant.src.agents.semantic_parser.nodes.retrieval.FewShotManager.retrieve",
        new=AsyncMock(return_value=[]),
    ):
        result = await few_shot_manager_node(state)

    assert result["optimization_metrics"]["few_shot_skipped"] is False
    assert result["optimization_metrics"]["few_shot_step_intent_focus"] is True
