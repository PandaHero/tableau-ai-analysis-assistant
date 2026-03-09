# -*- coding: utf-8 -*-
"""缓存节点辅助逻辑测试"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from analytics_assistant.src.agents.semantic_parser.nodes.cache import (
    _is_feature_cache_compatible,
    feature_cache_node,
    query_cache_node,
)
from analytics_assistant.src.agents.semantic_parser.nodes.execution import feedback_learner_node
from analytics_assistant.src.agents.semantic_parser.schemas.output import (
    SemanticOutput,
    SelfCheck,
)
from analytics_assistant.src.agents.semantic_parser.schemas.planner import StepIntent
from analytics_assistant.src.agents.semantic_parser.schemas.prefilter import (
    ComplexityType,
    MatchedComputation,
    PrefilterResult,
)


class TestFeatureCacheCompatibility:
    """特征缓存兼容性回归测试。"""

    def test_simple_prefilter_rejects_cached_computation(self):
        """当前规则为简单查询时，应忽略带计算种子的旧缓存。"""
        prefilter_result = PrefilterResult(
            detected_complexity=[ComplexityType.SIMPLE],
            detected_language="zh",
        )

        compatible = _is_feature_cache_compatible(
            {
                "confirmed_computations": ["profit"],
            },
            prefilter_result,
        )

        assert compatible is False

    def test_matching_computation_cache_is_compatible(self):
        """当前规则与缓存计算种子一致时，可以复用缓存。"""
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

        compatible = _is_feature_cache_compatible(
            {
                "confirmed_computations": ["profit_rate"],
            },
            prefilter_result,
        )

        assert compatible is True

    def test_mismatched_computation_cache_is_rejected(self):
        """缓存计算种子与当前规则结果不一致时，应强制失效。"""
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

        compatible = _is_feature_cache_compatible(
            {
                "confirmed_computations": ["running_total"],
            },
            prefilter_result,
        )

        assert compatible is False


class TestFeatureCacheNode:
    """特征缓存节点回归测试。"""

    @pytest.mark.asyncio
    async def test_contextual_step_bypasses_feature_cache_lookup(self):
        """带 current_step_intent 的 follow-up step 不应复用旧特征缓存。"""
        state = {
            "question": "看下这个省份里的销售额",
            "datasource_luid": "ds-1",
            "current_step_intent": StepIntent(
                step_id="step-2",
                title="继续按产品拆分",
                question="在异常省份内继续看产品",
                depends_on=["step-1"],
                semantic_focus=["异常归因"],
                candidate_axes=["产品"],
            ).model_dump(),
        }

        mock_cache = MagicMock()

        with patch(
            "analytics_assistant.src.agents.semantic_parser.nodes.cache.get_feature_cache",
            return_value=mock_cache,
        ):
            result = await feature_cache_node(state)

        mock_cache.get.assert_not_called()
        assert result["optimization_metrics"]["feature_cache_hit"] is False
        assert result["optimization_metrics"]["feature_cache_context_bypass"] is True


class TestQueryCacheContract:
    """查询缓存应保留完整 parse contract。"""

    @pytest.mark.asyncio
    async def test_query_cache_hit_restores_planner_context(self):
        """缓存命中时应恢复 semantic_query、analysis_plan、global_understanding。"""
        state = {
            "question": "为什么华东区销售额下降了？",
            "datasource_luid": "ds-1",
        }
        analysis_plan = {
            "plan_mode": "why_analysis",
            "needs_planning": True,
            "sub_questions": [{"title": "验证现象", "question": "为什么华东区销售额下降了？"}],
        }
        global_understanding = {
            "analysis_mode": "why_analysis",
            "single_query_feasible": False,
            "analysis_plan": analysis_plan,
        }
        cached = SimpleNamespace(
            semantic_output={"restated_question": "为什么华东区销售额下降了"},
            query={"query": "cached-vizql", "kind": "vizql"},
            analysis_plan=analysis_plan,
            global_understanding=global_understanding,
            hit_count=3,
        )
        mock_cache = MagicMock()
        mock_cache.get.return_value = cached

        with patch(
            "analytics_assistant.src.agents.semantic_parser.nodes.cache.get_query_cache",
            return_value=mock_cache,
        ):
            result = await query_cache_node(state)

        assert result["cache_hit"] is True
        assert result["semantic_query"] == {"query": "cached-vizql", "kind": "vizql"}
        assert result["analysis_plan"] == analysis_plan
        assert result["global_understanding"] == global_understanding
        assert result["optimization_metrics"]["query_cache_hit"] is True

    @pytest.mark.asyncio
    async def test_feedback_learner_writes_full_parse_contract_to_query_cache(self):
        """写 QueryCache 时应带上 planner 上下文，避免复杂问题缓存后退化。"""
        semantic_output = SemanticOutput(
            query_id="q-cache",
            restated_question="为什么华东区销售额下降了",
            self_check=SelfCheck(
                field_mapping_confidence=0.92,
                time_range_confidence=0.91,
                computation_confidence=0.9,
                overall_confidence=0.91,
            ),
        ).model_dump()
        analysis_plan = {
            "plan_mode": "why_analysis",
            "needs_planning": True,
            "sub_questions": [{"title": "验证现象", "question": "为什么华东区销售额下降了？"}],
        }
        global_understanding = {
            "analysis_mode": "why_analysis",
            "single_query_feasible": False,
            "analysis_plan": analysis_plan,
        }
        state = {
            "question": "为什么华东区销售额下降了？",
            "semantic_output": semantic_output,
            "semantic_query": {"query": "cached-vizql", "kind": "vizql"},
            "datasource_luid": "ds-1",
            "analysis_plan": analysis_plan,
            "global_understanding": global_understanding,
            "optimization_metrics": {},
        }
        mock_cache = MagicMock()

        with patch(
            "analytics_assistant.src.agents.semantic_parser.nodes.execution.get_query_cache",
            return_value=mock_cache,
        ), patch(
            "analytics_assistant.src.agents.semantic_parser.nodes.execution.get_context",
            return_value=SimpleNamespace(schema_hash="schema-1"),
        ):
            result = await feedback_learner_node(state, config={"configurable": {}})

        mock_cache.set.assert_called_once_with(
            question="为什么华东区销售额下降了？",
            datasource_luid="ds-1",
            schema_hash="schema-1",
            semantic_output=semantic_output,
            query={"query": "cached-vizql", "kind": "vizql"},
            analysis_plan=analysis_plan,
            global_understanding=global_understanding,
            include_embedding=False,
        )
        assert result["parse_result"]["analysis_plan"] == analysis_plan
        assert result["parse_result"]["global_understanding"] == global_understanding
