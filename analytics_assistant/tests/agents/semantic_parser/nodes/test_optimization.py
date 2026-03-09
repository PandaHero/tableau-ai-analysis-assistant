# -*- coding: utf-8 -*-
"""optimization 节点回归测试"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from analytics_assistant.src.agents.semantic_parser.nodes.optimization import (
    feature_extractor_node,
)
from analytics_assistant.src.agents.semantic_parser.schemas.planner import StepIntent
from analytics_assistant.src.agents.semantic_parser.schemas.prefilter import (
    ComplexityType,
    FeatureExtractionOutput,
    PrefilterResult,
)


class TestFeatureExtractorNode:
    """feature_extractor_node 回归测试。"""

    @pytest.mark.asyncio
    async def test_contextual_step_does_not_write_feature_cache(self):
        """带 step intent 的 follow-up step 不应写入旧的 feature cache。"""
        state = {
            "question": "看下这个省份里的销售额",
            "datasource_luid": "ds-1",
            "prefilter_result": PrefilterResult(
                detected_complexity=[ComplexityType.SIMPLE],
                detected_language="zh",
            ).model_dump(),
            "current_step_intent": StepIntent(
                step_id="step-2",
                title="继续按产品拆分",
                question="在异常省份内继续看产品",
                depends_on=["step-1"],
                semantic_focus=["异常归因"],
                candidate_axes=["产品"],
            ).model_dump(),
        }

        fake_result = FeatureExtractionOutput(
            required_measures=["销售额"],
            required_dimensions=["产品"],
            confirmation_confidence=0.9,
            is_degraded=False,
        )
        mock_cache = MagicMock()
        mock_extractor = MagicMock()
        mock_extractor.extract = AsyncMock(return_value=fake_result)

        with patch(
            "analytics_assistant.src.agents.semantic_parser.nodes.optimization.FeatureExtractor",
            return_value=mock_extractor,
        ), patch(
            "analytics_assistant.src.agents.semantic_parser.nodes.optimization.get_feature_cache",
            return_value=mock_cache,
        ):
            result = await feature_extractor_node(state)

        mock_extractor.extract.assert_awaited_once()
        mock_cache.set.assert_not_called()
        assert result["optimization_metrics"]["feature_cache_context_bypass"] is True
        assert result["optimization_metrics"]["feature_extractor_step_intent"] is True
