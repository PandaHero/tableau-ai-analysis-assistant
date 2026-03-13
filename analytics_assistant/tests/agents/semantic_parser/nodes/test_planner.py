# -*- coding: utf-8 -*-
"""Regression tests for strict planner and global understanding nodes."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from analytics_assistant.src.agents.semantic_parser.nodes.global_understanding import (
    global_understanding_node,
)
from analytics_assistant.src.agents.semantic_parser.nodes.parallel import (
    unified_feature_and_understanding_node,
)
from analytics_assistant.src.agents.semantic_parser.nodes.planner import (
    analysis_planner_node,
)
from analytics_assistant.src.agents.semantic_parser.prompts.global_understanding_prompt import (
    build_global_understanding_prompt,
)
from analytics_assistant.src.agents.semantic_parser.prompts.prompt_builder import (
    DynamicPromptBuilder,
)
from analytics_assistant.src.agents.semantic_parser.schemas.config import SemanticConfig
from analytics_assistant.src.agents.semantic_parser.schemas.planner import (
    AnalysisMode,
    AnalysisPlan,
    AxisEvidenceScore,
    EvidenceContext,
    GlobalUnderstandingOutput,
    PlanMode,
    QueryFeasibilityBlocker,
    StepArtifact,
    StepIntent,
)
from analytics_assistant.src.agents.semantic_parser.schemas.prefilter import (
    ComplexityType,
    FeatureExtractionOutput,
    PrefilterResult,
)
from analytics_assistant.src.core.schemas.field_candidate import FieldCandidate


class TestAnalysisPlanner:
    @staticmethod
    def _make_why_plan() -> AnalysisPlan:
        return AnalysisPlan(
            plan_mode=PlanMode.WHY_ANALYSIS,
            single_query_feasible=False,
            needs_planning=True,
            requires_llm_reasoning=True,
            goal="Explain why East region sales dropped",
            execution_strategy="sequential",
            reasoning_focus=[
                "Validate the observed change",
                "Locate the abnormal slice",
                "Synthesize the likely cause",
            ],
            sub_questions=[
                {
                    "step_id": "step-1",
                    "title": "Validate change",
                    "goal": "Confirm the drop exists",
                    "question": "Did East region sales decline?",
                    "purpose": "Validate the observed change",
                    "step_type": "query",
                    "uses_primary_query": True,
                    "semantic_focus": ["sales", "east region"],
                    "expected_output": "A confirmed decline",
                },
                {
                    "step_id": "step-2",
                    "title": "Rank explanatory axes",
                    "goal": "Prioritize the explanatory axes for screening",
                    "question": "Rank the most likely explanatory axes for the decline",
                    "purpose": "Identify the best axes to screen first",
                    "step_type": "query",
                    "depends_on": ["step-1"],
                    "semantic_focus": ["screening priority", "product", "city"],
                    "candidate_axes": ["product", "city"],
                    "expected_output": "Ranked axis candidates",
                },
                {
                    "step_id": "step-3",
                    "title": "Screen top axes",
                    "goal": "Screen the top-ranked axes with real data",
                    "question": "Screen the top-ranked axes to see which one best explains the decline",
                    "purpose": "Use real data to narrow the best axis before locating the slice",
                    "step_type": "query",
                    "depends_on": ["step-2"],
                    "semantic_focus": ["screening", "product", "city"],
                    "candidate_axes": ["product", "city"],
                    "targets_anomaly": True,
                    "expected_output": "Screened axis candidates",
                },
                {
                    "step_id": "step-4",
                    "title": "Find abnormal slice",
                    "goal": "Locate the slice with the largest anomaly",
                    "question": "Break down the decline under the best axis",
                    "purpose": "Identify the main contributing slice",
                    "step_type": "query",
                    "depends_on": ["step-2", "step-3"],
                    "semantic_focus": ["anomaly", "product", "city"],
                    "candidate_axes": ["product", "city"],
                    "targets_anomaly": True,
                    "expected_output": "Abnormal slice candidates",
                },
                {
                    "step_id": "step-5",
                    "title": "Synthesize cause",
                    "goal": "Summarize the likely cause",
                    "question": "Summarize the likely cause from prior evidence",
                    "purpose": "Produce the final explanation",
                    "step_type": "synthesis",
                    "depends_on": ["step-1", "step-2", "step-3", "step-4"],
                    "semantic_focus": ["evidence", "cause"],
                    "expected_output": "Root cause summary",
                },
            ],
            retrieval_focus_terms=["sales", "east region"],
            planner_confidence=0.86,
        )

    @staticmethod
    def _make_prefilter_result() -> PrefilterResult:
        return PrefilterResult(
            detected_complexity=[ComplexityType.TIME_COMPARE],
            detected_language="en",
        )

    @staticmethod
    def _make_feature_output() -> FeatureExtractionOutput:
        return FeatureExtractionOutput(
            required_measures=["sales"],
            required_dimensions=["region"],
            confirmation_confidence=0.92,
            is_degraded=False,
        )

    @pytest.mark.asyncio
    async def test_global_understanding_node_serializes_output(self):
        llm_output = GlobalUnderstandingOutput(
            analysis_mode=AnalysisMode.WHY_ANALYSIS,
            single_query_feasible=False,
            single_query_blockers=[
                QueryFeasibilityBlocker.MULTI_HOP_REASONING,
                QueryFeasibilityBlocker.DYNAMIC_AXIS_SELECTION,
            ],
            decomposition_reason="Need to validate the change before explaining it",
            primary_restated_question="Why did East region sales drop?",
            llm_confidence=0.9,
            analysis_plan=self._make_why_plan(),
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
                    "question": "Why did East region sales drop?",
                    "prefilter_result": self._make_prefilter_result().model_dump(),
                    "feature_extraction_output": self._make_feature_output().model_dump(),
                }
            )

        assert result["global_understanding"]["analysis_mode"] == AnalysisMode.WHY_ANALYSIS.value
        assert result["global_understanding"]["single_query_feasible"] is False
        assert result["analysis_plan"]["plan_mode"] == PlanMode.WHY_ANALYSIS.value
        assert result["optimization_metrics"]["global_understanding_llm_used"] is True
        assert result["optimization_metrics"]["global_understanding_fallback_used"] is False

    @pytest.mark.asyncio
    async def test_global_understanding_node_backfills_plan_when_llm_omits_steps(self):
        llm_output = GlobalUnderstandingOutput(
            analysis_mode=AnalysisMode.WHY_ANALYSIS,
            single_query_feasible=False,
            decomposition_reason="Need a why-analysis workflow",
            primary_restated_question="Why did East region sales drop?",
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
                    "question": "Why did East region sales drop?",
                    "prefilter_result": self._make_prefilter_result().model_dump(),
                    "feature_extraction_output": self._make_feature_output().model_dump(),
                }
        )

        assert result["analysis_plan"]["plan_mode"] == PlanMode.WHY_ANALYSIS.value
        assert len(result["analysis_plan"]["sub_questions"]) >= 5
        assert result["global_understanding"]["analysis_plan"] is not None

    @pytest.mark.asyncio
    async def test_global_understanding_node_backfills_candidate_axes_from_field_semantic(self):
        llm_output = GlobalUnderstandingOutput(
            analysis_mode=AnalysisMode.WHY_ANALYSIS,
            single_query_feasible=False,
            decomposition_reason="Need a why-analysis workflow",
            primary_restated_question="Why did East region sales drop?",
            llm_confidence=0.82,
        )

        field_semantic = {
            "region": {
                "role": "dimension",
                "hierarchy_category": "geography",
                "hierarchy_level": "region",
                "child_dimension": "city",
            },
            "channel": {
                "role": "dimension",
                "category": "channel",
            },
            "sales": {
                "role": "measure",
                "category": "sales_metric",
            },
        }

        with patch(
            "analytics_assistant.src.agents.semantic_parser.nodes.global_understanding.get_llm",
            return_value=MagicMock(),
        ), patch(
            "analytics_assistant.src.agents.semantic_parser.nodes.global_understanding.stream_llm_structured",
            new=AsyncMock(return_value=llm_output),
        ):
            result = await global_understanding_node(
                {
                    "question": "Why did East region sales drop?",
                    "prefilter_result": self._make_prefilter_result().model_dump(),
                    "feature_extraction_output": self._make_feature_output().model_dump(),
                    "field_semantic": field_semantic,
                }
            )

        step_two = result["analysis_plan"]["sub_questions"][1]
        assert step_two["candidate_axes"] == ["geography", "channel"]
        assert step_two["step_kind"] == "rank_explanatory_axes"

        step_three = result["analysis_plan"]["sub_questions"][2]
        assert step_three["step_kind"] == "screen_top_axes"
        assert step_three["targets_anomaly"] is True

        step_four = result["analysis_plan"]["sub_questions"][3]
        assert step_four["step_kind"] == "locate_anomalous_slice"
        assert step_four["targets_anomaly"] is True

    @pytest.mark.asyncio
    async def test_global_understanding_node_can_disable_why_screening_wave(self):
        llm_output = GlobalUnderstandingOutput(
            analysis_mode=AnalysisMode.WHY_ANALYSIS,
            single_query_feasible=False,
            decomposition_reason="Need a why-analysis workflow",
            primary_restated_question="Why did East region sales drop?",
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
                    "question": "Why did East region sales drop?",
                    "prefilter_result": self._make_prefilter_result().model_dump(),
                    "feature_extraction_output": self._make_feature_output().model_dump(),
                    "feature_flags": {"why_screening_wave": False},
                }
            )

        step_kinds = [
            step["step_kind"]
            for step in result["analysis_plan"]["sub_questions"]
        ]
        assert step_kinds == [
            "verify_anomaly",
            "rank_explanatory_axes",
            "locate_anomalous_slice",
            "synthesize_cause",
        ]

    @pytest.mark.asyncio
    async def test_global_understanding_node_supports_complex_single_query_mode(self):
        llm_output = GlobalUnderstandingOutput(
            analysis_mode=AnalysisMode.COMPLEX_SINGLE_QUERY,
            single_query_feasible=True,
            decomposition_reason="This is complex but still expressible in one query",
            primary_restated_question="Compare profit margin by region year over year",
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
                    "question": "Compare profit margin by region year over year",
                    "prefilter_result": self._make_prefilter_result().model_dump(),
                    "feature_extraction_output": FeatureExtractionOutput(
                        required_measures=["profit margin"],
                        required_dimensions=["region"],
                        confirmation_confidence=0.9,
                        is_degraded=False,
                    ).model_dump(),
                }
            )

        plan = result["analysis_plan"]
        assert result["global_understanding"]["analysis_mode"] == AnalysisMode.COMPLEX_SINGLE_QUERY.value
        assert result["global_understanding"]["single_query_blockers"] == []
        assert plan["plan_mode"] == PlanMode.DIRECT_QUERY.value
        assert plan["needs_planning"] is False
        assert plan["requires_llm_reasoning"] is True

    @pytest.mark.asyncio
    async def test_global_understanding_node_requires_explicit_clarification_flag(self):
        llm_output = GlobalUnderstandingOutput(
            analysis_mode=AnalysisMode.SINGLE_QUERY,
            single_query_feasible=True,
            needs_clarification=False,
            clarification_question="Please confirm the time range",
            clarification_options=["This month", "Last month"],
            primary_restated_question="What is sales this month?",
            llm_confidence=0.81,
        )

        with patch(
            "analytics_assistant.src.agents.semantic_parser.nodes.global_understanding.get_llm",
            return_value=MagicMock(),
        ), patch(
            "analytics_assistant.src.agents.semantic_parser.nodes.global_understanding.stream_llm_structured",
            new=AsyncMock(return_value=llm_output),
        ):
            result = await global_understanding_node({"question": "What is sales this month?"})

        assert result["global_understanding"]["needs_clarification"] is False
        assert result["global_understanding"]["clarification_question"] is None
        assert result["global_understanding"]["clarification_options"] == []

    @pytest.mark.asyncio
    async def test_analysis_planner_node_serializes_plan(self):
        result = await analysis_planner_node(
            {
                "question": "Why did East region sales drop?",
                "global_understanding": GlobalUnderstandingOutput(
                    analysis_mode=AnalysisMode.WHY_ANALYSIS,
                    single_query_feasible=False,
                    single_query_blockers=[
                        QueryFeasibilityBlocker.MULTI_HOP_REASONING,
                        QueryFeasibilityBlocker.DYNAMIC_AXIS_SELECTION,
                    ],
                    primary_restated_question="Why did East region sales drop?",
                    llm_confidence=0.9,
                    analysis_plan=self._make_why_plan(),
                ).model_dump(),
            }
        )

        assert result["analysis_plan"]["plan_mode"] == PlanMode.WHY_ANALYSIS.value
        assert result["global_understanding"]["analysis_mode"] == AnalysisMode.WHY_ANALYSIS.value
        assert result["optimization_metrics"]["analysis_planner_triggered"] is True

    @pytest.mark.asyncio
    async def test_analysis_planner_node_prefers_existing_global_understanding_plan(self):
        existing_plan = AnalysisPlan(
            plan_mode=PlanMode.DECOMPOSED_QUERY,
            single_query_feasible=False,
            needs_planning=True,
            requires_llm_reasoning=True,
            goal="Existing decomposed plan",
            sub_questions=[
                {
                    "title": "Existing step",
                    "question": "Use existing plan",
                    "step_type": "query",
                }
            ],
        )

        result = await analysis_planner_node(
            {
                "question": "What changed?",
                "global_understanding": GlobalUnderstandingOutput(
                    analysis_mode=AnalysisMode.MULTI_STEP_ANALYSIS,
                    single_query_feasible=False,
                    single_query_blockers=[QueryFeasibilityBlocker.RESULT_SET_DEPENDENCY],
                    primary_restated_question="Existing decomposed plan",
                    llm_confidence=0.84,
                    analysis_plan=existing_plan,
                ).model_dump(),
            }
        )

        assert result["analysis_plan"]["goal"] == "Existing decomposed plan"
        assert result["analysis_plan"]["plan_mode"] == PlanMode.DECOMPOSED_QUERY.value

    @pytest.mark.asyncio
    async def test_analysis_planner_node_requires_global_understanding(self):
        with pytest.raises(ValueError, match="requires global_understanding"):
            await analysis_planner_node({"question": "What is sales this month?"})

    @pytest.mark.asyncio
    async def test_analysis_planner_node_backfills_embedded_plan_from_explicit_state_plan(self):
        explicit_plan = AnalysisPlan(
            plan_mode=PlanMode.DIRECT_QUERY,
            single_query_feasible=True,
            needs_planning=False,
            requires_llm_reasoning=True,
            goal="What is sales this month?",
            execution_strategy="single_query",
            planner_confidence=0.91,
        )

        result = await analysis_planner_node(
            {
                "question": "What is sales this month?",
                "analysis_plan": explicit_plan.model_dump(),
                "global_understanding": GlobalUnderstandingOutput(
                    analysis_mode=AnalysisMode.SINGLE_QUERY,
                    single_query_feasible=True,
                    primary_restated_question="What is sales this month?",
                    llm_confidence=0.91,
                ).model_dump(),
            }
        )

        assert result["analysis_plan"]["goal"] == "What is sales this month?"
        assert result["global_understanding"]["analysis_plan"]["goal"] == "What is sales this month?"

    @pytest.mark.asyncio
    async def test_unified_feature_and_understanding_node_uses_llm_global_understanding(self):
        feature_output = self._make_feature_output()
        llm_output = GlobalUnderstandingOutput(
            analysis_mode=AnalysisMode.SINGLE_QUERY,
            single_query_feasible=True,
            primary_restated_question="Sales by region this month",
            llm_confidence=0.88,
            analysis_plan=AnalysisPlan(
                plan_mode=PlanMode.DIRECT_QUERY,
                single_query_feasible=True,
                needs_planning=False,
                requires_llm_reasoning=False,
                goal="Sales by region this month",
                execution_strategy="single_query",
            ),
        )

        with patch(
            "analytics_assistant.src.agents.semantic_parser.nodes.parallel.feature_extractor_node",
            new=AsyncMock(
                return_value={
                    "feature_extraction_output": feature_output.model_dump(),
                    "is_degraded": False,
                }
            ),
        ), patch(
            "analytics_assistant.src.agents.semantic_parser.nodes.parallel.run_global_understanding",
            new=AsyncMock(return_value=llm_output),
        ):
            result = await unified_feature_and_understanding_node(
                {"question": "Sales by region this month"}
            )

        assert result["global_understanding"]["analysis_mode"] == AnalysisMode.SINGLE_QUERY.value
        assert result["analysis_plan"]["plan_mode"] == PlanMode.DIRECT_QUERY.value
        assert result["optimization_metrics"]["global_understanding_llm_used"] is True
        assert result["optimization_metrics"]["global_understanding_fallback_used"] is False
        assert result["optimization_metrics"]["global_understanding_rule_only"] is False

    @pytest.mark.asyncio
    async def test_global_understanding_node_raises_when_llm_errors(self):
        with patch(
            "analytics_assistant.src.agents.semantic_parser.nodes.global_understanding.get_llm",
            return_value=MagicMock(),
        ), patch(
            "analytics_assistant.src.agents.semantic_parser.nodes.global_understanding.stream_llm_structured",
            new=AsyncMock(side_effect=RuntimeError("llm boom")),
        ):
            with pytest.raises(RuntimeError, match="llm boom"):
                await global_understanding_node(
                    {
                        "question": "Why did East region sales drop?",
                        "prefilter_result": self._make_prefilter_result().model_dump(),
                        "feature_extraction_output": self._make_feature_output().model_dump(),
                    }
                )

    def test_global_understanding_prompt_includes_dimension_semantics(self):
        prompt = build_global_understanding_prompt(
            question="Why did East region sales drop?",
            field_semantic={
                "region": {
                    "role": "dimension",
                    "hierarchy_category": "geography",
                    "hierarchy_level": "region",
                    "child_dimension": "city",
                    "business_description": "Region hierarchy",
                },
                "sales": {
                    "role": "measure",
                    "category": "sales_metric",
                },
            },
        )

        assert "[Available Dimension Semantics]" in prompt
        assert "region; category=geography; level=region; child=city" in prompt
        assert "candidate_axes" in prompt

    def test_prompt_builder_includes_analysis_plan_section(self):
        prompt_builder = DynamicPromptBuilder(low_confidence_threshold=0.7)
        prompt = prompt_builder.build(
            question="Why did East region sales drop?",
            config=SemanticConfig(current_date=date(2026, 3, 6)),
            field_candidates=[
                FieldCandidate(
                    field_name="Sales",
                    field_caption="Sales",
                    role="measure",
                    data_type="float",
                    confidence=0.95,
                ),
            ],
            detected_complexity=[ComplexityType.SIMPLE],
            analysis_plan=self._make_why_plan(),
            current_step_intent=StepIntent(
                step_id="step-2",
                title="Find abnormal slice",
                goal="Locate the slice with the largest anomaly",
                question="Break down the decline by product and city",
                semantic_focus=["anomaly", "product", "city"],
                expected_output="Abnormal slice candidates",
                candidate_axes=["product", "city"],
                depends_on=["step-1"],
            ),
            evidence_context=EvidenceContext(
                primary_question="Why did East region sales drop?",
                anomalous_entities=["Jiangsu"],
                validated_axes=["channel", "product_line"],
                axis_scores=[
                    AxisEvidenceScore(
                        axis="channel",
                        explained_share=0.62,
                        confidence=0.86,
                        reason="Direct channel contributes most of the drop",
                    ),
                    AxisEvidenceScore(
                        axis="product_line",
                        explained_share=0.31,
                        confidence=0.73,
                        reason="Office category declines materially",
                    ),
                ],
                step_artifacts=[
                    StepArtifact(
                        step_id="step-1",
                        title="Validate change",
                        table_summary="East region sales declined 12% in March",
                    )
                ],
            ),
        )

        assert "<analysis_plan>" in prompt
        assert "<current_step_intent>" in prompt
        assert "<evidence_context>" in prompt
        assert "Find abnormal slice" in prompt
        assert "East region sales declined 12% in March" in prompt
        assert "解释轴优先级" in prompt
        assert "channel(解释占比 62%, 置信度 86%" in prompt
