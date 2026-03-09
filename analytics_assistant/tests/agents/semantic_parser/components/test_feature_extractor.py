# -*- coding: utf-8 -*-
"""
FeatureExtractor 单元测试

验证规则快路径与 LLM 回退的核心行为。
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from analytics_assistant.src.agents.semantic_parser.components.feature_extractor import (
    FeatureExtractor,
)
from analytics_assistant.src.agents.semantic_parser.schemas.prefilter import (
    ComplexityType,
    MatchedComputation,
    PrefilterResult,
)
from analytics_assistant.src.agents.semantic_parser.schemas.planner import StepIntent


class _DummyConfig:
    """最小配置桩，仅提供 FeatureExtractor 所需接口。"""

    def get_semantic_parser_optimization_config(self):
        return {
            "feature_extractor": {
                "timeout_ms": 0,
            }
        }


class TestFeatureExtractor:
    """FeatureExtractor 行为测试。"""

    @pytest.mark.asyncio
    async def test_rule_fast_path_skips_llm_for_clear_simple_query(self):
        """简单且信号明确的问题优先走规则快路径。"""
        with patch(
            "analytics_assistant.src.agents.semantic_parser.components.feature_extractor.get_config",
            return_value=_DummyConfig(),
        ), patch(
            "analytics_assistant.src.agents.semantic_parser.components.feature_extractor.get_llm",
        ) as mock_get_llm:
            extractor = FeatureExtractor()
            prefilter_result = PrefilterResult(
                detected_complexity=[ComplexityType.SIMPLE],
                detected_language="zh",
            )

            result = await extractor.extract("各地区的订单数量", prefilter_result)

            assert result.is_degraded is False
            assert result.confirmation_confidence >= 0.7
            assert any(term in result.required_measures for term in ("订单数", "数量"))
            assert any(term in result.required_dimensions for term in ("地区", "区域"))
            mock_get_llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_rule_fast_path_prefers_user_facing_terms_over_seed_internal_names(self):
        """规则快路径应尽量输出用户问题中的业务词，而不是英文种子内部名。"""
        with patch(
            "analytics_assistant.src.agents.semantic_parser.components.feature_extractor.get_config",
            return_value=_DummyConfig(),
        ), patch(
            "analytics_assistant.src.agents.semantic_parser.components.feature_extractor.get_llm",
        ) as mock_get_llm:
            extractor = FeatureExtractor()
            prefilter_result = PrefilterResult(
                detected_complexity=[ComplexityType.SIMPLE],
                detected_language="zh",
            )

            result = await extractor.extract("各事业部在各省份的销售数量", prefilter_result)

            assert result.is_degraded is False
            assert "事业部" in result.required_dimensions
            assert "省份" in result.required_dimensions
            assert "division" not in result.required_dimensions
            assert "Division" not in result.required_dimensions
            assert any(term in result.required_measures for term in ("数量", "销售数量"))
            assert "Quantity" not in result.required_measures
            assert "units_sold" not in result.required_measures
            mock_get_llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_complex_query_falls_back_to_llm(self):
        """复杂查询不走规则快路径，仍会调用 LLM。"""
        fake_llm = MagicMock()
        fake_llm.ainvoke = AsyncMock(
            return_value=SimpleNamespace(
                content=(
                    '{"required_measures":["利润"],'
                    '"required_dimensions":["地区"],'
                    '"confirmed_time_hints":[],'
                    '"confirmed_computations":["profit_rate"],'
                    '"confirmation_confidence":0.9}'
                )
            )
        )

        with patch(
            "analytics_assistant.src.agents.semantic_parser.components.feature_extractor.get_config",
            return_value=_DummyConfig(),
        ), patch(
            "analytics_assistant.src.agents.semantic_parser.components.feature_extractor.get_llm",
            return_value=fake_llm,
        ) as mock_get_llm:
            extractor = FeatureExtractor()
            prefilter_result = PrefilterResult(
                detected_complexity=[ComplexityType.RATIO],
                matched_computations=[
                    MatchedComputation(
                        seed_name="profit_rate",
                        display_name="利润率",
                        calc_type="RATIO",
                        formula="{profit}/{revenue}",
                    )
                ],
                detected_language="zh",
            )

            result = await extractor.extract("各地区的利润率", prefilter_result)

            assert result.required_measures == ["利润"]
            assert result.required_dimensions == ["地区"]
            assert result.confirmed_computations == ["profit_rate"]
            mock_get_llm.assert_called_once()
            fake_llm.ainvoke.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_step_intent_skips_rule_fast_path_and_merges_candidate_axes(self):
        """follow-up step 应强制走 LLM，并把 candidate_axes 合并回字段需求。"""
        fake_llm = MagicMock()
        fake_llm.ainvoke = AsyncMock(
            return_value=SimpleNamespace(
                content=(
                    '{"required_measures":["销售额"],'
                    '"required_dimensions":["异常省份"],'
                    '"confirmed_time_hints":[],'
                    '"confirmed_computations":[],'
                    '"confirmation_confidence":0.88}'
                )
            )
        )

        with patch(
            "analytics_assistant.src.agents.semantic_parser.components.feature_extractor.get_config",
            return_value=_DummyConfig(),
        ), patch(
            "analytics_assistant.src.agents.semantic_parser.components.feature_extractor.get_llm",
            return_value=fake_llm,
        ) as mock_get_llm:
            extractor = FeatureExtractor()
            prefilter_result = PrefilterResult(
                detected_complexity=[ComplexityType.SIMPLE],
                detected_language="zh",
            )

            result = await extractor.extract(
                "看下华东区销售额",
                prefilter_result,
                current_step_intent=StepIntent(
                    step_id="step-2",
                    title="按产品拆异常省份",
                    question="在异常省份内继续看产品结构",
                    depends_on=["step-1"],
                    semantic_focus=["异常定位", "分解归因"],
                    candidate_axes=["产品", "渠道"],
                ),
            )

            assert result.is_degraded is False
            assert "异常省份" in result.required_dimensions
            assert "产品" in result.required_dimensions
            assert "渠道" in result.required_dimensions
            mock_get_llm.assert_called_once()
            fake_llm.ainvoke.assert_awaited_once()
