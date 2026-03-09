# -*- coding: utf-8 -*-
"""
Planner V3 schema 回归测试
"""

from analytics_assistant.src.agents.semantic_parser.schemas.planner import (
    AnalysisMode,
    AnalysisPlan,
    AnalysisPlanStep,
    AxisEvidenceScore,
    EvidenceContext,
    GlobalUnderstandingOutput,
    PlanMode,
    PlanStepType,
    QueryFeasibilityBlocker,
    StepArtifact,
)


def test_analysis_plan_step_supports_v3_fields_and_legacy_fields():
    """旧字段与 V3 step intent 字段应能同时表达。"""
    step = AnalysisPlanStep(
        step_id="s1",
        title="验证现象",
        goal="确认下降是否真实存在",
        question="确认华东区 3 月销售额同比是否下降",
        purpose="建立 why 分析的第一条证据",
        step_type=PlanStepType.QUERY,
        uses_primary_query=True,
        depends_on=[],
        semantic_focus=["销售额", "同比", "3月", "华东区"],
        expected_output="得到同比结果与异常方向",
        candidate_axes=["省份", "渠道"],
        clarification_if_missing=["baseline"],
    )

    assert step.step_id == "s1"
    assert step.goal == "确认下降是否真实存在"
    assert step.uses_primary_query is True
    assert step.candidate_axes == ["省份", "渠道"]


def test_global_understanding_output_can_embed_analysis_plan():
    """全局理解输出应能安全承载 AnalysisPlan。"""
    plan = AnalysisPlan(
        plan_mode=PlanMode.WHY_ANALYSIS,
        single_query_feasible=False,
        needs_planning=True,
        requires_llm_reasoning=True,
        decomposition_reason="需要先验证现象，再按解释轴逐步求证",
        goal="解释华东区 3 月销售额同比下降的原因",
        sub_questions=[
            AnalysisPlanStep(
                step_id="s1",
                title="验证现象",
                question="确认华东区 3 月销售额同比是否下降",
                step_type=PlanStepType.QUERY,
                uses_primary_query=True,
            ),
            AnalysisPlanStep(
                step_id="s2",
                title="归因总结",
                question="基于已有证据汇总原因",
                step_type=PlanStepType.SYNTHESIS,
                depends_on=["s1"],
            ),
        ],
    )

    result = GlobalUnderstandingOutput(
        analysis_mode=AnalysisMode.WHY_ANALYSIS,
        single_query_feasible=False,
        single_query_blockers=[
            QueryFeasibilityBlocker.MISSING_BASELINE,
            QueryFeasibilityBlocker.DYNAMIC_AXIS_SELECTION,
        ],
        decomposition_reason="问题存在 why 推理与动态解释轴选择",
        primary_restated_question="解释华东区 3 月销售额同比下降的原因",
        llm_confidence=0.86,
        analysis_plan=plan,
    )

    roundtrip = GlobalUnderstandingOutput.model_validate(result.model_dump())

    assert roundtrip.analysis_mode == AnalysisMode.WHY_ANALYSIS
    assert roundtrip.analysis_plan is not None
    assert roundtrip.analysis_plan.sub_questions[0].title == "验证现象"
    assert roundtrip.analysis_plan.steps[1].step_type == PlanStepType.SYNTHESIS


def test_evidence_context_roundtrip_preserves_step_artifacts():
    """证据上下文应能稳定序列化/反序列化。"""
    context = EvidenceContext(
        primary_question="为什么华东区 3 月销售额同比下降？",
        baseline_type="yoy",
        anomalous_entities=["江苏"],
        validated_axes=["省份"],
        open_questions=["江苏是否集中在某些产品线"],
        step_artifacts=[
            StepArtifact(
                step_id="s1",
                title="验证现象",
                query_id="q-1",
                table_summary="华东区 3 月销售额同比下降 12%",
                key_findings=["现象成立"],
                entity_scope=["华东区"],
            )
        ],
        axis_scores=[
            AxisEvidenceScore(
                axis="省份",
                explained_share=0.72,
                confidence=0.83,
                reason="江苏和浙江贡献了主要降幅",
            )
        ],
    )

    restored = EvidenceContext.model_validate(context.model_dump())

    assert restored.primary_question.startswith("为什么华东区")
    assert restored.step_artifacts[0].title == "验证现象"
    assert restored.axis_scores[0].axis == "省份"
