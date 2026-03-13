# -*- coding: utf-8 -*-
"""全局理解节点。

这个阶段只负责回答三件事：
1. 当前问题能否单查。
2. 如果不能，为什么不能。
3. 如果需要多步，应该形成怎样的分析计划。

它不负责字段 grounding，也不直接生成可执行查询。
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from analytics_assistant.src.agents.base.node import get_llm, stream_llm_structured
from analytics_assistant.src.infra.ai.models import TaskType

from ..node_utils import merge_metrics
from ..prompts.global_understanding_prompt import (
    GLOBAL_UNDERSTANDING_SYSTEM_PROMPT,
    build_global_understanding_prompt,
)
from ..schemas.planner import (
    AnalysisMode,
    AnalysisPlan,
    AnalysisPlanStep,
    GlobalUnderstandingOutput,
    PlanMode,
    PlanStepKind,
    PlanStepType,
    QueryFeasibilityBlocker,
)
from ..schemas.prefilter import FeatureExtractionOutput, PrefilterResult
from ..state import SemanticParserState

logger = logging.getLogger(__name__)

_WHY_SCREENING_WAVE_FLAG = "why_screening_wave"


def _dedupe_strings(items: list[str]) -> list[str]:
    """去重并保留原始顺序。"""
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        normalized = str(item or "").strip()
        if not normalized:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


def _extract_focus_terms(
    prefilter_result: Optional[PrefilterResult],
    feature_output: Optional[FeatureExtractionOutput],
) -> list[str]:
    """从规则信号中提取全局理解阶段可复用的关注词。"""
    terms: list[str] = []
    if feature_output is not None:
        terms.extend(feature_output.required_measures)
        terms.extend(feature_output.required_dimensions)
        terms.extend(feature_output.confirmed_time_hints)
        terms.extend(feature_output.confirmed_computations)
    if prefilter_result is not None:
        terms.extend(
            matched.display_name or matched.seed_name
            for matched in prefilter_result.matched_computations
            if matched.display_name or matched.seed_name
        )
    return _dedupe_strings(terms)[:6]


def _dedupe_blockers(
    blockers: list[QueryFeasibilityBlocker],
) -> list[QueryFeasibilityBlocker]:
    seen: set[QueryFeasibilityBlocker] = set()
    result: list[QueryFeasibilityBlocker] = []
    for blocker in blockers:
        if blocker in seen:
            continue
        seen.add(blocker)
        result.append(blocker)
    return result


def _default_blockers_for_mode(
    analysis_mode: AnalysisMode,
    *,
    needs_clarification: bool = False,
) -> list[QueryFeasibilityBlocker]:
    if analysis_mode == AnalysisMode.WHY_ANALYSIS:
        return [
            QueryFeasibilityBlocker.MULTI_HOP_REASONING,
            QueryFeasibilityBlocker.DYNAMIC_AXIS_SELECTION,
        ]
    if analysis_mode == AnalysisMode.MULTI_STEP_ANALYSIS:
        return [QueryFeasibilityBlocker.RESULT_SET_DEPENDENCY]
    if needs_clarification:
        return [QueryFeasibilityBlocker.OPEN_BUSINESS_SCOPE]
    return []


def _plan_mode_from_analysis_mode(analysis_mode: AnalysisMode) -> PlanMode:
    if analysis_mode == AnalysisMode.WHY_ANALYSIS:
        return PlanMode.WHY_ANALYSIS
    if analysis_mode == AnalysisMode.MULTI_STEP_ANALYSIS:
        return PlanMode.DECOMPOSED_QUERY
    return PlanMode.DIRECT_QUERY


def _default_reasoning_focus_for_mode(
    analysis_mode: AnalysisMode,
    focus_terms: list[str],
) -> list[str]:
    focus_subject = "、".join(focus_terms[:3]) if focus_terms else "核心指标与关键维度"
    if analysis_mode == AnalysisMode.WHY_ANALYSIS:
        return [
            "先验证异常是否真实存在，并明确比较基线和口径。",
            f"再围绕 {focus_subject} 排序解释轴，并完成第一轮 screening。",
            "最后合并证据链，输出原因、证据与剩余不确定性。",
        ]
    if analysis_mode == AnalysisMode.MULTI_STEP_ANALYSIS:
        return [
            "先拿到主问题首跳结果。",
            f"再围绕 {focus_subject} 补齐后续步骤需要的基线、切片或对象范围。",
            "最后合并前序证据并生成最终回答。",
        ]
    if analysis_mode == AnalysisMode.COMPLEX_SINGLE_QUERY:
        return [
            "保持单条查询表达，但保留复杂推理语义。",
            f"重点确认 {focus_subject} 的筛选、比较与聚合口径。",
        ]
    return ["直接完成全局理解，并进入单查询 grounding。"]


def _default_decomposition_reason(
    analysis_mode: AnalysisMode,
    *,
    needs_clarification: bool,
) -> str:
    if analysis_mode == AnalysisMode.WHY_ANALYSIS:
        return "当前问题属于 why / 原因分析，需要先验证异常，再构造证据链。"
    if analysis_mode == AnalysisMode.MULTI_STEP_ANALYSIS:
        return "当前问题存在明显的结果依赖或多跳拆解关系，需要分步执行。"
    if analysis_mode == AnalysisMode.COMPLEX_SINGLE_QUERY:
        return "当前问题语义复杂，但仍可以由一条查询表达。"
    if needs_clarification:
        return "当前问题的业务范围或口径仍不完整，需要先澄清。"
    return "当前问题可直接进入单查询语义理解。"


def _default_goal_for_mode(
    analysis_mode: AnalysisMode,
    question: str,
) -> str:
    normalized_question = question.strip()
    if analysis_mode == AnalysisMode.WHY_ANALYSIS:
        return (
            f"解释并验证这个问题背后的原因：{normalized_question}"
            if normalized_question
            else "解释并验证这个问题背后的原因"
        )
    if analysis_mode == AnalysisMode.MULTI_STEP_ANALYSIS:
        return (
            f"拆解复杂问题并形成多步分析：{normalized_question}"
            if normalized_question
            else "拆解复杂问题并形成多步分析"
        )
    return (
        f"直接解析并执行用户查询：{normalized_question}"
        if normalized_question
        else "直接解析并执行用户查询"
    )


def _default_risk_flags(
    blockers: list[QueryFeasibilityBlocker],
    *,
    needs_clarification: bool,
) -> list[str]:
    flags: list[str] = []
    if QueryFeasibilityBlocker.MISSING_BASELINE in blockers:
        flags.append("比较基线可能缺失或未明确。")
    if QueryFeasibilityBlocker.DYNAMIC_AXIS_SELECTION in blockers:
        flags.append("解释轴需要结合前序结果动态选择。")
    if QueryFeasibilityBlocker.RESULT_SET_DEPENDENCY in blockers:
        flags.append("后续步骤依赖前序结果集，无法一次完成。")
    if needs_clarification:
        flags.append("业务范围或分析口径仍需用户确认。")
    return flags


def _extract_candidate_axes_from_field_semantic(
    field_semantic: Optional[dict[str, Any]],
) -> list[str]:
    """从真实字段语义中提取可用解释轴，不做硬编码兜底。"""
    if not field_semantic:
        return []

    axes: list[str] = []
    seen: set[str] = set()
    for field_name, raw_info in field_semantic.items():
        if not isinstance(raw_info, dict):
            continue
        if str(raw_info.get("role") or "").strip().lower() != "dimension":
            continue

        axis_name = str(
            raw_info.get("hierarchy_category")
            or raw_info.get("category")
            or field_name
        ).strip()
        if not axis_name:
            continue

        axis_key = axis_name.casefold()
        if axis_key in seen:
            continue
        seen.add(axis_key)
        axes.append(axis_name)
        if len(axes) >= 6:
            break

    return axes


def _is_why_screening_wave_enabled(feature_flags: Optional[dict[str, Any]]) -> bool:
    if not isinstance(feature_flags, dict):
        return True
    raw_value = feature_flags.get(_WHY_SCREENING_WAVE_FLAG)
    return True if raw_value is None else bool(raw_value)


def _apply_why_screening_wave_flag(
    steps: list[AnalysisPlanStep],
    *,
    enabled: bool,
) -> list[AnalysisPlanStep]:
    """关闭 screening wave 时，why 计划仍保留 root-native planner，只移除该独立步骤。"""
    if enabled:
        return list(steps)

    filtered_steps = [
        step for step in steps
        if step.step_kind != PlanStepKind.SCREEN_TOP_AXES
    ]
    removed_step_ids = {
        str(step.step_id or "").strip()
        for step in steps
        if step.step_kind == PlanStepKind.SCREEN_TOP_AXES
    }
    if not removed_step_ids:
        return filtered_steps

    rewritten: list[AnalysisPlanStep] = []
    for step in filtered_steps:
        kept_dependencies = [
            dep for dep in (step.depends_on or [])
            if dep not in removed_step_ids
        ]
        rewritten.append(
            step.model_copy(update={"depends_on": kept_dependencies})
        )
    return rewritten


def _build_generic_plan_steps(
    analysis_mode: AnalysisMode,
    question: str,
    *,
    focus_terms: list[str],
    field_semantic: Optional[dict[str, Any]] = None,
    enable_why_screening_wave: bool = True,
) -> list[AnalysisPlanStep]:
    """在 LLM 未提供完整步骤时，补齐一套可执行的默认计划。"""
    step_focus = focus_terms or ["异常验证", "指标口径", "关键维度"]
    candidate_axes = _extract_candidate_axes_from_field_semantic(field_semantic)

    if analysis_mode == AnalysisMode.WHY_ANALYSIS:
        why_steps = [
            AnalysisPlanStep(
                step_id="step-1",
                title="验证异常",
                goal="确认用户要解释的异常现象是否真实存在，并明确比较口径。",
                question=question,
                purpose="先确认异常成立，再继续 why 诊断。",
                step_type=PlanStepType.QUERY,
                step_kind=PlanStepKind.VERIFY_ANOMALY,
                uses_primary_query=True,
                semantic_focus=step_focus,
                expected_output="确认异常是否成立，并明确差异方向、幅度和比较基线。",
            ),
            AnalysisPlanStep(
                step_id="step-2",
                title="解释轴排序",
                goal="从真实可用的解释轴中，先确定最值得筛查的方向。",
                question=(
                    f"围绕“{question}”，先比较可用解释轴的优先级，并给出后续 "
                    "screening 的轴顺序。"
                ),
                purpose="先排出优先级，而不是无序展开所有维度。",
                step_type=PlanStepType.QUERY,
                step_kind=PlanStepKind.RANK_EXPLANATORY_AXES,
                depends_on=["step-1"],
                semantic_focus=_dedupe_strings(["解释轴排序", "优先级判断", *step_focus]),
                expected_output="得到后续 screening 需要使用的解释轴顺序。",
                candidate_axes=candidate_axes,
            ),
            AnalysisPlanStep(
                step_id="step-3" if not enable_why_screening_wave else "step-4",
                title="定位异常切片",
                goal="围绕筛查后的高优先解释轴，定位最异常的对象或切片。",
                question=(
                    f"基于筛查后保留下来的高优先解释轴，继续围绕“{question}”定位异常"
                    "最明显的对象或切片。"
                ),
                purpose="把解释轴筛查结果收敛到具体异常对象或异常切片。",
                step_type=PlanStepType.QUERY,
                step_kind=PlanStepKind.LOCATE_ANOMALOUS_SLICE,
                depends_on=["step-2"] if not enable_why_screening_wave else ["step-2", "step-3"],
                semantic_focus=_dedupe_strings(["异常定位", "切片收敛", *step_focus]),
                expected_output="定位异常对象集合或关键异常切片。",
                candidate_axes=candidate_axes,
                targets_anomaly=True,
            ),
            AnalysisPlanStep(
                step_id="step-4" if not enable_why_screening_wave else "step-5",
                title="归因总结",
                goal="汇总证据链并输出原因总结。",
                question=f"基于前面步骤结果，总结“{question}”最可能的原因。",
                purpose="把异常验证、轴筛查和异常定位串成原因链。",
                step_type=PlanStepType.SYNTHESIS,
                step_kind=PlanStepKind.SYNTHESIZE_CAUSE,
                depends_on=(
                    ["step-1", "step-2", "step-3"]
                    if not enable_why_screening_wave
                    else ["step-1", "step-2", "step-3", "step-4"]
                ),
                semantic_focus=_dedupe_strings(["证据汇总", "原因归纳", *step_focus[:2]]),
                expected_output="形成结论、证据摘要和待确认口径。",
            ),
        ]
        if enable_why_screening_wave:
            why_steps.insert(
                2,
                AnalysisPlanStep(
                    step_id="step-3",
                    title="筛查高优先解释轴",
                    goal="对优先级最高的解释轴做一轮高层级筛查，确认最值得深挖的方向。",
                    question=(
                        f"基于前一步的解释轴排序，对最优先的解释轴做一轮高层级 "
                        f"screening，比较哪条轴最能解释“{question}”。"
                    ),
                    purpose="先用真实数据筛掉低价值方向，再进入精确定位。",
                    step_type=PlanStepType.QUERY,
                    step_kind=PlanStepKind.SCREEN_TOP_AXES,
                    depends_on=["step-2"],
                    semantic_focus=_dedupe_strings(["top-k screening", "解释力比较", *step_focus]),
                    expected_output="确认本轮最值得继续深挖的解释轴，并保留筛查证据。",
                    candidate_axes=candidate_axes,
                    targets_anomaly=True,
                ),
            )
        return why_steps

    if analysis_mode == AnalysisMode.MULTI_STEP_ANALYSIS:
        return [
            AnalysisPlanStep(
                step_id="step-1",
                title="主问题首跳",
                goal="先生成覆盖主问题核心目标的第一跳查询。",
                question=question,
                purpose="先得到主问题首跳结果。",
                step_type=PlanStepType.QUERY,
                step_kind=PlanStepKind.PRIMARY_QUERY,
                uses_primary_query=True,
                semantic_focus=_dedupe_strings(["主问题", *step_focus[:3]]),
                expected_output="得到主问题首跳结果。",
            ),
            AnalysisPlanStep(
                step_id="step-2",
                title="补充验证",
                goal="补充后续分析需要的基线、切片或依赖信息。",
                question=f"围绕“{question}”补充验证后续分析所需的基线、维度或依赖信息。",
                purpose="为最终回答补齐依赖证据。",
                step_type=PlanStepType.QUERY,
                step_kind=PlanStepKind.SUPPLEMENTAL_QUERY,
                depends_on=["step-1"],
                semantic_focus=_dedupe_strings(["补充验证", "依赖补齐", *step_focus[:3]]),
                expected_output="补齐复杂逻辑所需的依赖信息。",
                candidate_axes=candidate_axes,
            ),
            AnalysisPlanStep(
                step_id="step-3",
                title="结果合并",
                goal="合并前序结果并输出最终回答。",
                question=f"结合前面步骤结果，整理“{question}”的最终回答。",
                purpose="把前序证据合并成最终回答。",
                step_type=PlanStepType.SYNTHESIS,
                step_kind=PlanStepKind.RESULT_SYNTHESIS,
                depends_on=["step-1", "step-2"],
                semantic_focus=_dedupe_strings(["结果汇总", "风险提示", *step_focus[:2]]),
                expected_output="形成最终回答及剩余风险点。",
            ),
        ]

    return []


def _normalize_plan_steps(
    steps: list[AnalysisPlanStep],
    *,
    analysis_mode: AnalysisMode,
    question: str,
) -> list[AnalysisPlanStep]:
    """把 LLM 输出或默认步骤归一化成稳定的 planner step。"""
    normalized_steps: list[AnalysisPlanStep] = []
    for index, step in enumerate(steps, start=1):
        step_id = step.step_id or f"step-{index}"
        title = (step.title or f"步骤 {index}").strip()
        step_type = step.step_type
        question_text = (step.question or step.goal or title).strip()
        goal = (step.goal or step.purpose or question_text).strip()
        purpose = (step.purpose or step.goal or question_text).strip()
        depends_on = _dedupe_strings(step.depends_on)

        if index == 1 and step_type == PlanStepType.QUERY:
            uses_primary_query = (
                True
                if analysis_mode != AnalysisMode.COMPLEX_SINGLE_QUERY
                else step.uses_primary_query
            )
        else:
            uses_primary_query = step.uses_primary_query

        if not depends_on and index > 1:
            if step_type == PlanStepType.SYNTHESIS:
                depends_on = [
                    prior.step_id or f"step-{idx}"
                    for idx, prior in enumerate(normalized_steps, start=1)
                ]
            else:
                depends_on = [normalized_steps[-1].step_id or f"step-{index - 1}"]

        normalized_steps.append(
            AnalysisPlanStep(
                step_id=step_id,
                title=title,
                goal=goal,
                question=question_text or question,
                purpose=purpose,
                step_type=step_type,
                step_kind=step.step_kind,
                uses_primary_query=uses_primary_query,
                depends_on=depends_on,
                semantic_focus=_dedupe_strings(step.semantic_focus),
                expected_output=(step.expected_output or goal or purpose).strip(),
                candidate_axes=_dedupe_strings(step.candidate_axes),
                targets_anomaly=bool(step.targets_anomaly),
                clarification_if_missing=_dedupe_strings(step.clarification_if_missing),
            )
        )
    return normalized_steps


def _normalize_global_understanding_output(
    output: GlobalUnderstandingOutput,
    *,
    question: str,
    prefilter_result: Optional[PrefilterResult],
    feature_output: Optional[FeatureExtractionOutput],
    field_semantic: Optional[dict[str, Any]] = None,
    feature_flags: Optional[dict[str, Any]] = None,
) -> GlobalUnderstandingOutput:
    """把 LLM 输出修正成稳定的全局理解契约。"""
    analysis_mode = output.analysis_mode
    focus_terms = _extract_focus_terms(prefilter_result, feature_output)
    enable_why_screening_wave = _is_why_screening_wave_enabled(feature_flags)

    if analysis_mode in {AnalysisMode.WHY_ANALYSIS, AnalysisMode.MULTI_STEP_ANALYSIS}:
        single_query_feasible = False
    elif analysis_mode == AnalysisMode.COMPLEX_SINGLE_QUERY:
        single_query_feasible = True
    else:
        single_query_feasible = output.single_query_feasible

    blockers = _dedupe_blockers(output.single_query_blockers)
    needs_clarification = bool(output.needs_clarification)
    if single_query_feasible:
        blockers = []
    elif not blockers:
        blockers = _default_blockers_for_mode(
            analysis_mode,
            needs_clarification=needs_clarification,
        )

    plan_mode = _plan_mode_from_analysis_mode(analysis_mode)
    base_plan = output.analysis_plan or AnalysisPlan()
    normalized_steps = list(base_plan.sub_questions)
    if not normalized_steps and analysis_mode in {
        AnalysisMode.WHY_ANALYSIS,
        AnalysisMode.MULTI_STEP_ANALYSIS,
    }:
        normalized_steps = _build_generic_plan_steps(
            analysis_mode,
            question,
            focus_terms=focus_terms,
            field_semantic=field_semantic,
            enable_why_screening_wave=enable_why_screening_wave,
        )
    normalized_steps = _apply_why_screening_wave_flag(
        normalized_steps,
        enabled=enable_why_screening_wave,
    )
    normalized_steps = _normalize_plan_steps(
        normalized_steps,
        analysis_mode=analysis_mode,
        question=question,
    )

    normalized_plan = AnalysisPlan(
        plan_mode=plan_mode,
        single_query_feasible=single_query_feasible,
        needs_planning=plan_mode != PlanMode.DIRECT_QUERY,
        requires_llm_reasoning=(
            analysis_mode != AnalysisMode.SINGLE_QUERY
            or base_plan.requires_llm_reasoning
        ),
        decomposition_reason=(
            output.decomposition_reason
            or base_plan.decomposition_reason
            or _default_decomposition_reason(
                analysis_mode,
                needs_clarification=needs_clarification,
            )
        ),
        goal=(
            base_plan.goal
            or output.primary_restated_question
            or question.strip()
            or _default_goal_for_mode(analysis_mode, question)
        ),
        execution_strategy=(
            "single_query"
            if plan_mode == PlanMode.DIRECT_QUERY
            else (base_plan.execution_strategy or "sequential")
        ),
        reasoning_focus=_dedupe_strings(
            base_plan.reasoning_focus
            or _default_reasoning_focus_for_mode(analysis_mode, focus_terms)
        ),
        sub_questions=normalized_steps,
        risk_flags=_dedupe_strings(
            output.risk_flags
            or base_plan.risk_flags
            or _default_risk_flags(
                blockers,
                needs_clarification=needs_clarification,
            )
        ),
        needs_clarification=needs_clarification,
        clarification_question=(
            (output.clarification_question or base_plan.clarification_question)
            if needs_clarification
            else None
        ),
        clarification_options=(
            _dedupe_strings(output.clarification_options or base_plan.clarification_options)
            if needs_clarification
            else []
        ),
        retrieval_focus_terms=_dedupe_strings(
            base_plan.retrieval_focus_terms or focus_terms
        ),
        planner_confidence=output.llm_confidence,
    )

    return GlobalUnderstandingOutput(
        analysis_mode=analysis_mode,
        single_query_feasible=single_query_feasible,
        single_query_blockers=blockers,
        decomposition_reason=normalized_plan.decomposition_reason,
        needs_clarification=needs_clarification,
        clarification_question=normalized_plan.clarification_question,
        clarification_options=normalized_plan.clarification_options,
        primary_restated_question=(
            (output.primary_restated_question or question).strip() or None
        ),
        risk_flags=normalized_plan.risk_flags,
        llm_confidence=output.llm_confidence,
        analysis_plan=normalized_plan,
    )


async def _run_llm_global_understanding(
    question: str,
    *,
    prefilter_result: Optional[PrefilterResult],
    feature_output: Optional[FeatureExtractionOutput],
    field_semantic: Optional[dict[str, Any]] = None,
) -> GlobalUnderstandingOutput:
    """调用推理模型执行全局理解。"""
    llm = get_llm(
        agent_name="semantic_parser",
        task_type=TaskType.REASONING,
        enable_json_mode=True,
    )
    messages: list[BaseMessage] = [
        SystemMessage(content=GLOBAL_UNDERSTANDING_SYSTEM_PROMPT),
        HumanMessage(
            content=build_global_understanding_prompt(
                question=question,
                prefilter_result=prefilter_result,
                feature_output=feature_output,
                field_semantic=field_semantic,
            )
        ),
    ]
    return await stream_llm_structured(
        llm=llm,
        messages=messages,
        output_model=GlobalUnderstandingOutput,
    )


async def run_global_understanding(
    question: str,
    *,
    prefilter_result: Optional[PrefilterResult],
    feature_output: Optional[FeatureExtractionOutput],
    field_semantic: Optional[dict[str, Any]] = None,
    feature_flags: Optional[dict[str, Any]] = None,
) -> GlobalUnderstandingOutput:
    """执行全局理解并输出归一化后的稳定契约。"""
    normalized_question = str(question or "").strip()
    if not normalized_question:
        raise ValueError("question must not be empty")

    llm_output = await _run_llm_global_understanding(
        normalized_question,
        prefilter_result=prefilter_result,
        feature_output=feature_output,
        field_semantic=field_semantic,
    )
    return _normalize_global_understanding_output(
        llm_output,
        question=normalized_question,
        prefilter_result=prefilter_result,
        feature_output=feature_output,
        field_semantic=field_semantic,
        feature_flags=feature_flags,
    )


async def global_understanding_node(state: SemanticParserState) -> dict[str, Any]:
    """生成统一的全局理解结果。

    这一步由 LLM 主导判断是否单查、是否拆步以及初始 plan，
    但返回值会被严格归一化，避免后续节点消费不稳定结构。
    """
    start_time = time.time()
    question = state.get("question", "")

    prefilter_result_raw = state.get("prefilter_result")
    prefilter_result = (
        PrefilterResult.model_validate(prefilter_result_raw)
        if prefilter_result_raw
        else None
    )

    feature_output_raw = state.get("feature_extraction_output")
    feature_output = (
        FeatureExtractionOutput.model_validate(feature_output_raw)
        if feature_output_raw
        else None
    )

    field_semantic = state.get("field_semantic")
    if not isinstance(field_semantic, dict):
        field_semantic = None
    feature_flags = state.get("feature_flags")
    if not isinstance(feature_flags, dict):
        feature_flags = None

    global_understanding = await run_global_understanding(
        question,
        prefilter_result=prefilter_result,
        feature_output=feature_output,
        field_semantic=field_semantic,
        feature_flags=feature_flags,
    )

    elapsed_ms = (time.time() - start_time) * 1000
    logger.info(
        "global_understanding_node: mode=%s, single_query_feasible=%s, llm_used=%s, elapsed=%.1fms",
        global_understanding.analysis_mode.value,
        global_understanding.single_query_feasible,
        True,
        elapsed_ms,
    )

    return {
        "analysis_plan": (
            global_understanding.analysis_plan.model_dump()
            if global_understanding.analysis_plan is not None
            else None
        ),
        "global_understanding": global_understanding.model_dump(),
        "optimization_metrics": merge_metrics(
            state,
            global_understanding_ms=elapsed_ms,
            global_understanding_mode=global_understanding.analysis_mode.value,
            global_understanding_single_query_feasible=global_understanding.single_query_feasible,
            global_understanding_llm_used=True,
            global_understanding_fallback_used=False,
        ),
    }


__all__ = ["global_understanding_node", "run_global_understanding"]
