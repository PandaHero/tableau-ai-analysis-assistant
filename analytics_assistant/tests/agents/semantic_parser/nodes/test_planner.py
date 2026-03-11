# -*- coding: utf-8 -*-
"""
Analysis planner 节点回归测试
"""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from analytics_assistant.src.core.schemas.field_candidate import FieldCandidate
from analytics_assistant.src.agents.semantic_parser.nodes.global_understanding import (
    global_understanding_node,
)
from analytics_assistant.src.agents.semantic_parser.nodes.planner import (
    analysis_planner_node,
    build_analysis_plan,
    build_global_understanding_fallback,
)
from analytics_assistant.src.agents.semantic_parser.prompts.prompt_builder import (
    DynamicPromptBuilder,
)
from analytics_assistant.src.agents.semantic_parser.schemas.config import SemanticConfig
from analytics_assistant.src.agents.semantic_parser.schemas.planner import (
    AnalysisMode,
    AnalysisPlan,
    EvidenceContext,
    GlobalUnderstandingOutput,
    PlanMode,
    PlanStepType,
    QueryFeasibilityBlocker,
    StepIntent,
    StepArtifact,
)
from analytics_assistant.src.agents.semantic_parser.schemas.prefilter import (
    ComplexityType,
    FeatureExtractionOutput,
    PrefilterResult,
)


class TestAnalysisPlanner:
    """复杂问题 / why 问题的计划生成测试。"""

    @staticmethod
    def _make_llm_global_understanding_output() -> AnalysisPlan:
        return AnalysisPlan(
            plan_mode=PlanMode.WHY_ANALYSIS,
            single_query_feasible=False,
            needs_planning=True,
            requires_llm_reasoning=True,
            goal="解释为什么华东区销售额下降",
            execution_strategy="sequential",
            reasoning_focus=["先验证现象", "再定位异常切片", "最后汇总结论"],
            sub_questions=[
                {
                    "step_id": "step-1",
                    "title": "验证现象",
                    "goal": "确认现象成立",
                    "question": "确认华东区销售额是否下降",
                    "purpose": "先确认现象",
                    "step_type": "query",
                    "uses_primary_query": True,
                    "semantic_focus": ["现象验证"],
                    "expected_output": "确认降幅",
                },
                {
                    "step_id": "step-2",
                    "title": "定位异常切片",
                    "goal": "找出异常切片",
                    "question": "按地区和产品找出异常最大的切片",
                    "purpose": "定位关键异常切片",
                    "step_type": "query",
                    "depends_on": ["step-1"],
                    "semantic_focus": ["异常定位", "产品", "地区"],
                    "candidate_axes": ["地区", "产品"],
                    "expected_output": "定位异常切片",
                },
                {
                    "step_id": "step-3",
                    "title": "归因总结",
                    "goal": "汇总原因",
                    "question": "结合前序结果总结原因",
                    "purpose": "输出结论",
                    "step_type": "synthesis",
                    "depends_on": ["step-1", "step-2"],
                    "semantic_focus": ["证据汇总", "原因归纳"],
                    "expected_output": "形成原因总结",
                },
            ],
            planner_confidence=0.86,
        )

    def test_build_analysis_plan_for_why_question(self):
        """why 问题应进入原因分析模式，并生成多步子问题。"""
        prefilter_result = PrefilterResult(
            detected_complexity=[ComplexityType.SIMPLE],
            detected_language="zh",
        )
        feature_output = FeatureExtractionOutput(
            required_measures=["销售额"],
            required_dimensions=["地区"],
            confirmation_confidence=0.92,
            is_degraded=False,
        )

        plan = build_analysis_plan(
            "为什么华东区销售额下降了？",
            prefilter_result=prefilter_result,
            feature_output=feature_output,
        )

        assert plan.plan_mode == PlanMode.WHY_ANALYSIS
        assert plan.needs_planning is True
        assert plan.requires_llm_reasoning is True
        assert len(plan.sub_questions) >= 3
        assert plan.sub_questions[0].uses_primary_query is True
        assert plan.sub_questions[0].step_type == PlanStepType.QUERY
        assert plan.sub_questions[-1].step_type == PlanStepType.SYNTHESIS
        assert "销售额" in plan.retrieval_focus_terms

    def test_build_analysis_plan_for_complex_query(self):
        """复杂计算信号应进入拆解模式。"""
        prefilter_result = PrefilterResult(
            detected_complexity=[ComplexityType.TIME_COMPARE],
            detected_language="zh",
        )
        feature_output = FeatureExtractionOutput(
            required_measures=["利润率"],
            required_dimensions=["地区"],
            confirmation_confidence=0.9,
            is_degraded=False,
        )

        plan = build_analysis_plan(
            "比较今年和去年各地区利润率变化，并输出差异最大的地区",
            prefilter_result=prefilter_result,
            feature_output=feature_output,
        )

        assert plan.plan_mode == PlanMode.DECOMPOSED_QUERY
        assert plan.execution_strategy == "sequential"
        assert plan.sub_questions[0].uses_primary_query is True
        assert plan.sub_questions[1].step_type == PlanStepType.QUERY
        assert plan.sub_questions[-1].step_type == PlanStepType.SYNTHESIS

    @pytest.mark.asyncio
    async def test_global_understanding_node_serializes_output(self):
        """全局理解节点应优先返回 LLM 产出的统一契约。"""
        prefilter_result = PrefilterResult(
            detected_complexity=[ComplexityType.TIME_COMPARE],
            detected_language="zh",
        )
        feature_output = FeatureExtractionOutput(
            required_measures=["销售额"],
            required_dimensions=["地区"],
            confirmation_confidence=0.92,
            is_degraded=False,
        )
        llm_output = GlobalUnderstandingOutput(
            analysis_mode=AnalysisMode.WHY_ANALYSIS,
            single_query_feasible=False,
            single_query_blockers=[
                QueryFeasibilityBlocker.MULTI_HOP_REASONING,
                QueryFeasibilityBlocker.DYNAMIC_AXIS_SELECTION,
            ],
            decomposition_reason="需要先验证现象，再逐步归因",
            primary_restated_question="为什么华东区销售额下降了？",
            llm_confidence=0.9,
            analysis_plan=self._make_llm_global_understanding_output(),
        )

        with patch(
            "analytics_assistant.src.agents.semantic_parser.nodes.global_understanding.get_llm",
            return_value=MagicMock(),
        ), patch(
            "analytics_assistant.src.agents.semantic_parser.nodes.global_understanding.stream_llm_structured",
            new=AsyncMock(return_value=llm_output),
        ):
            result = await global_understanding_node(
                {
                    "question": "为什么华东区销售额下降了？",
                    "prefilter_result": prefilter_result.model_dump(),
                    "feature_extraction_output": feature_output.model_dump(),
                }
            )

        assert result["global_understanding"]["analysis_mode"] == AnalysisMode.WHY_ANALYSIS.value
        assert result["global_understanding"]["single_query_feasible"] is False
        assert result["optimization_metrics"]["global_understanding_mode"] == AnalysisMode.WHY_ANALYSIS.value
        assert result["optimization_metrics"]["global_understanding_llm_used"] is True
        assert result["optimization_metrics"]["global_understanding_fallback_used"] is False

    @pytest.mark.asyncio
    async def test_global_understanding_node_backfills_plan_when_llm_omits_steps(self):
        """如果 LLM 漏掉 analysis_plan，节点也应补出可用计划。"""
        prefilter_result = PrefilterResult(
            detected_complexity=[ComplexityType.TIME_COMPARE],
            detected_language="zh",
        )
        feature_output = FeatureExtractionOutput(
            required_measures=["销售额"],
            required_dimensions=["地区"],
            confirmation_confidence=0.92,
            is_degraded=False,
        )
        llm_output = GlobalUnderstandingOutput(
            analysis_mode=AnalysisMode.WHY_ANALYSIS,
            single_query_feasible=False,
            decomposition_reason="这是一个 why 问题，需要证据链",
            primary_restated_question="为什么华东区销售额下降了？",
            llm_confidence=0.82,
        )

        with patch(
            "analytics_assistant.src.agents.semantic_parser.nodes.global_understanding.get_llm",
            return_value=MagicMock(),
        ), patch(
            "analytics_assistant.src.agents.semantic_parser.nodes.global_understanding.stream_llm_structured",
            new=AsyncMock(return_value=llm_output),
        ):
            result = await global_understanding_node(
                {
                    "question": "为什么华东区销售额下降了？",
                    "prefilter_result": prefilter_result.model_dump(),
                    "feature_extraction_output": feature_output.model_dump(),
                }
            )

        assert result["analysis_plan"] is not None
        assert result["analysis_plan"]["plan_mode"] == PlanMode.WHY_ANALYSIS.value
        assert result["global_understanding"]["analysis_plan"] is not None
        assert result["global_understanding"]["analysis_plan"]["plan_mode"] == PlanMode.WHY_ANALYSIS.value
        assert len(result["global_understanding"]["analysis_plan"]["sub_questions"]) >= 3
        assert result["global_understanding"]["analysis_plan"]["reasoning_focus"][0].startswith(
            "先验证现象"
        )

    @pytest.mark.asyncio
    async def test_global_understanding_node_supports_complex_single_query_mode(self):
        """复杂但仍可单查的问题应保留 complex_single_query 模式。"""
        prefilter_result = PrefilterResult(
            detected_complexity=[ComplexityType.TIME_COMPARE],
            detected_language="zh",
        )
        feature_output = FeatureExtractionOutput(
            required_measures=["利润率"],
            required_dimensions=["地区"],
            confirmation_confidence=0.9,
            is_degraded=False,
        )
        llm_output = GlobalUnderstandingOutput(
            analysis_mode=AnalysisMode.COMPLEX_SINGLE_QUERY,
            single_query_feasible=True,
            decomposition_reason="虽然有时间对比，但 Tableau 仍可单查表达",
            primary_restated_question="比较今年和去年各地区利润率变化",
            llm_confidence=0.88,
        )

        with patch(
            "analytics_assistant.src.agents.semantic_parser.nodes.global_understanding.get_llm",
            return_value=MagicMock(),
        ), patch(
            "analytics_assistant.src.agents.semantic_parser.nodes.global_understanding.stream_llm_structured",
            new=AsyncMock(return_value=llm_output),
        ):
            result = await global_understanding_node(
                {
                    "question": "比较今年和去年各地区利润率变化",
                    "prefilter_result": prefilter_result.model_dump(),
                    "feature_extraction_output": feature_output.model_dump(),
                }
            )

        plan = result["analysis_plan"]
        assert result["global_understanding"]["analysis_mode"] == AnalysisMode.COMPLEX_SINGLE_QUERY.value
        assert result["global_understanding"]["single_query_feasible"] is True
        assert result["global_understanding"]["single_query_blockers"] == []
        assert plan["plan_mode"] == PlanMode.DIRECT_QUERY.value
        assert plan["needs_planning"] is False
        assert plan["requires_llm_reasoning"] is True
        assert plan["retrieval_focus_terms"] == ["利润率", "地区"]

    @pytest.mark.asyncio
    async def test_analysis_planner_node_serializes_plan(self):
        """planner 节点应优先消费已有 global_understanding 并回填 analysis_plan。"""
        prefilter_result = PrefilterResult(
            detected_complexity=[ComplexityType.SIMPLE],
            detected_language="zh",
        )
        feature_output = FeatureExtractionOutput(
            required_measures=["销售额"],
            required_dimensions=["地区"],
            confirmation_confidence=0.92,
            is_degraded=False,
        )
        llm_output = GlobalUnderstandingOutput(
            analysis_mode=AnalysisMode.WHY_ANALYSIS,
            single_query_feasible=False,
            single_query_blockers=[
                QueryFeasibilityBlocker.MULTI_HOP_REASONING,
                QueryFeasibilityBlocker.DYNAMIC_AXIS_SELECTION,
            ],
            decomposition_reason="需要先验证现象，再逐步归因",
            primary_restated_question="为什么华东区销售额下降了？",
            llm_confidence=0.9,
            analysis_plan=self._make_llm_global_understanding_output(),
        )
        with patch(
            "analytics_assistant.src.agents.semantic_parser.nodes.global_understanding.get_llm",
            return_value=MagicMock(),
        ), patch(
            "analytics_assistant.src.agents.semantic_parser.nodes.global_understanding.stream_llm_structured",
            new=AsyncMock(return_value=llm_output),
        ):
            global_understanding_result = await global_understanding_node(
                {
                    "question": "为什么华东区销售额下降了？",
                    "prefilter_result": prefilter_result.model_dump(),
                    "feature_extraction_output": feature_output.model_dump(),
                }
            )

        result = await analysis_planner_node(
            {
                "question": "为什么华东区销售额下降了？",
                "global_understanding": global_understanding_result["global_understanding"],
            }
        )

        assert result["analysis_plan"]["plan_mode"] == PlanMode.WHY_ANALYSIS.value
        assert result["global_understanding"]["analysis_mode"] == AnalysisMode.WHY_ANALYSIS.value
        assert result["global_understanding"]["single_query_feasible"] is False
        assert result["optimization_metrics"]["analysis_planner_triggered"] is True
        assert result["optimization_metrics"]["analysis_planner_compat_fallback"] is False

    @pytest.mark.asyncio
    async def test_analysis_planner_node_prefers_existing_global_understanding_plan(self):
        """analysis_planner 应优先回填 global_understanding 中已有的 analysis_plan。"""
        # 使用 dict 直写，避免遗漏全局理解字段。
        state = {
            "question": "本月销售额是多少",
            "global_understanding": build_global_understanding_fallback(
                "已有外部全局理解结果",
                AnalysisPlan(
                    plan_mode=PlanMode.DECOMPOSED_QUERY,
                    single_query_feasible=False,
                    needs_planning=True,
                    requires_llm_reasoning=True,
                    goal="已有外部全局理解结果",
                    sub_questions=[
                        {
                            "title": "已有步骤",
                            "question": "已有步骤问题",
                            "step_type": "query",
                        }
                    ],
                ),
            ).model_dump(),
        }

        result = await analysis_planner_node(state)

        assert result["analysis_plan"]["goal"] == "已有外部全局理解结果"
        assert result["analysis_plan"]["plan_mode"] == PlanMode.DECOMPOSED_QUERY.value

    @pytest.mark.asyncio
    async def test_analysis_planner_node_uses_minimal_direct_query_compat_fallback(self):
        """缺少 global_understanding 时，analysis_planner 只回退到最小 direct-query 兼容计划。"""
        result = await analysis_planner_node(
            {
                "question": "本月销售额是多少",
            }
        )

        assert result["analysis_plan"]["plan_mode"] == PlanMode.DIRECT_QUERY.value
        assert result["analysis_plan"]["needs_planning"] is False
        assert result["global_understanding"]["single_query_feasible"] is True
        assert result["optimization_metrics"]["analysis_planner_compat_fallback"] is True

    def test_global_understanding_fallback_maps_direct_query_to_single_query(self):
        """direct_query 应映射为单查询可行的 fallback 结果。"""
        plan = AnalysisPlan(
            plan_mode=PlanMode.DIRECT_QUERY,
            single_query_feasible=True,
            needs_planning=False,
            requires_llm_reasoning=False,
            decomposition_reason="当前问题可单查",
            planner_confidence=0.91,
        )

        result = build_global_understanding_fallback("本月销售额是多少", plan)

        assert result.analysis_mode == AnalysisMode.SINGLE_QUERY
        assert result.single_query_feasible is True
        assert result.single_query_blockers == []
        assert result.analysis_plan is not None

    def test_global_understanding_fallback_maps_why_plan_to_blocked_multihop(self):
        """why 模式的 fallback 结果应显式标记为非单查和多跳阻塞。"""
        prefilter_result = PrefilterResult(
            detected_complexity=[ComplexityType.SIMPLE],
            detected_language="zh",
        )
        feature_output = FeatureExtractionOutput(
            required_measures=["销售额"],
            required_dimensions=["地区"],
            confirmation_confidence=0.92,
            is_degraded=False,
        )

        plan = build_analysis_plan(
            "为什么华东区销售额下降了？",
            prefilter_result=prefilter_result,
            feature_output=feature_output,
        )
        result = build_global_understanding_fallback("为什么华东区销售额下降了？", plan)

        assert result.analysis_mode == AnalysisMode.WHY_ANALYSIS
        assert result.single_query_feasible is False
        assert QueryFeasibilityBlocker.MULTI_HOP_REASONING in result.single_query_blockers
        assert QueryFeasibilityBlocker.DYNAMIC_AXIS_SELECTION in result.single_query_blockers

    @pytest.mark.asyncio
    async def test_global_understanding_node_falls_back_to_rules_when_llm_errors(self):
        """LLM 失败时，global_understanding 应回退到规则 fallback。"""
        prefilter_result = PrefilterResult(
            detected_complexity=[ComplexityType.SIMPLE],
            detected_language="zh",
        )
        feature_output = FeatureExtractionOutput(
            required_measures=["销售额"],
            required_dimensions=["地区"],
            confirmation_confidence=0.92,
            is_degraded=False,
        )

        with patch(
            "analytics_assistant.src.agents.semantic_parser.nodes.global_understanding.get_llm",
            return_value=MagicMock(),
        ), patch(
            "analytics_assistant.src.agents.semantic_parser.nodes.global_understanding.stream_llm_structured",
            new=AsyncMock(side_effect=RuntimeError("llm boom")),
        ):
            result = await global_understanding_node(
                {
                    "question": "为什么华东区销售额下降了？",
                    "prefilter_result": prefilter_result.model_dump(),
                    "feature_extraction_output": feature_output.model_dump(),
                }
            )

        assert result["global_understanding"]["analysis_mode"] == AnalysisMode.WHY_ANALYSIS.value
        assert result["global_understanding"]["single_query_feasible"] is False
        assert result["optimization_metrics"]["global_understanding_llm_used"] is False
        assert result["optimization_metrics"]["global_understanding_fallback_used"] is True

    def test_prompt_builder_includes_analysis_plan_section(self):
        """planner 与 evidence_context 应被 prompt builder 注入到最终 prompt。"""
        prefilter_result = PrefilterResult(
            detected_complexity=[ComplexityType.SIMPLE],
            detected_language="zh",
        )
        feature_output = FeatureExtractionOutput(
            required_measures=["销售额"],
            required_dimensions=["地区"],
            confirmation_confidence=0.92,
            is_degraded=False,
        )
        plan = build_analysis_plan(
            "为什么华东区销售额下降了？",
            prefilter_result=prefilter_result,
            feature_output=feature_output,
        )
        prompt_builder = DynamicPromptBuilder(low_confidence_threshold=0.7)
        prompt = prompt_builder.build(
            question="为什么华东区销售额下降了？",
            config=SemanticConfig(current_date=date(2026, 3, 6)),
            field_candidates=[
                FieldCandidate(
                    field_name="Sale Amtws",
                    field_caption="销售额",
                    role="measure",
                    data_type="float",
                    confidence=0.95,
                ),
            ],
            detected_complexity=[ComplexityType.SIMPLE],
            analysis_plan=plan,
            current_step_intent=StepIntent(
                step_id="step-2",
                title="定位异常切片",
                goal="定位最异常的对象或切片",
                question="按地区和产品找出贡献最大的异常切片",
                semantic_focus=["异常定位", "产品", "地区"],
                expected_output="定位异常对象集合或关键切片",
                candidate_axes=["地区", "产品"],
                depends_on=["step-1"],
            ),
            evidence_context=EvidenceContext(
                primary_question="为什么华东区销售额下降了？",
                anomalous_entities=["江苏"],
                step_artifacts=[
                    StepArtifact(
                        step_id="step-1",
                        title="验证现象",
                        table_summary="华东区 3 月销售额同比下降 12%",
                    )
                ],
            ),
        )

        assert "<analysis_plan>" in prompt
        assert "<current_step_intent>" in prompt
        assert "<evidence_context>" in prompt
        assert "原因分析" in prompt
        assert "定位最异常的对象或切片" in prompt
        assert "华东区 3 月销售额同比下降 12%" in prompt
