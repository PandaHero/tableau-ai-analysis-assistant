# -*- coding: utf-8 -*-
"""全局语义理解节点。"""

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
    PlanStepType,
    QueryFeasibilityBlocker,
)
from ..schemas.prefilter import FeatureExtractionOutput, PrefilterResult
from ..state import SemanticParserState
from .planner import build_analysis_plan, build_global_understanding_fallback

logger = logging.getLogger(__name__)


def _dedupe_strings(items: list[str]) -> list[str]:
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
            "先验证现象、比较基线和指标口径",
            f"再围绕 {focus_subject} 定位异常切片和潜在解释轴",
            "最后汇总证据链，形成原因总结并暴露剩余不确定性",
        ]
    if analysis_mode == AnalysisMode.MULTI_STEP_ANALYSIS:
        return [
            "先拿到主问题首跳结果",
            f"再围绕 {focus_subject} 补充依赖的基线、切片或对象范围",
            "最后合并前序证据并生成最终回答",
        ]
    if analysis_mode == AnalysisMode.COMPLEX_SINGLE_QUERY:
        return [
            "保持单条查询表达，但保留复杂推理路径",
            f"重点确认 {focus_subject} 的筛选、比较与聚合口径",
        ]
    return ["直接解析问题并进入单查询 grounding"]


def _default_decomposition_reason(
    analysis_mode: AnalysisMode,
    *,
    needs_clarification: bool,
) -> str:
    if analysis_mode == AnalysisMode.WHY_ANALYSIS:
        return "当前问题是 why/原因分析，需要先验证现象，再逐步构建证据链"
    if analysis_mode == AnalysisMode.MULTI_STEP_ANALYSIS:
        return "当前问题存在明显的结果依赖或动态下钻关系，需要多步分析"
    if analysis_mode == AnalysisMode.COMPLEX_SINGLE_QUERY:
        return "当前问题语义复杂，但仍可由一条查询表达，保留单查路径"
    if needs_clarification:
        return "当前问题主范围或业务口径仍不充分，需要先澄清后再决定执行路径"
    return "当前问题可沿单步语义理解路径直接落成查询"


def _default_goal_for_mode(
    analysis_mode: AnalysisMode,
    question: str,
) -> str:
    normalized_question = question.strip()
    if analysis_mode == AnalysisMode.WHY_ANALYSIS:
        return f"解释并验证问题背后的原因：{normalized_question}" if normalized_question else "解释并验证问题背后的原因"
    if analysis_mode == AnalysisMode.MULTI_STEP_ANALYSIS:
        return f"拆解复杂问题并形成多步分析：{normalized_question}" if normalized_question else "拆解复杂问题并形成多步分析"
    return f"直接解析用户查询：{normalized_question}" if normalized_question else "直接解析用户查询"


def _default_risk_flags(
    blockers: list[QueryFeasibilityBlocker],
    *,
    needs_clarification: bool,
) -> list[str]:
    flags: list[str] = []
    if QueryFeasibilityBlocker.MISSING_BASELINE in blockers:
        flags.append("比较基线可能缺失或未明确")
    if QueryFeasibilityBlocker.DYNAMIC_AXIS_SELECTION in blockers:
        flags.append("解释轴需要结合前序结果动态选择")
    if QueryFeasibilityBlocker.RESULT_SET_DEPENDENCY in blockers:
        flags.append("后续步骤依赖前序结果集，无法一次完成")
    if needs_clarification:
        flags.append("业务范围或口径可能仍需用户确认")
    return flags


def _build_generic_plan_steps(
    analysis_mode: AnalysisMode,
    question: str,
    *,
    focus_terms: list[str],
) -> list[AnalysisPlanStep]:
    step_focus = focus_terms or ["现象验证", "指标口径", "关键维度"]
    candidate_axes = _dedupe_strings(
        [
            term
            for term in focus_terms
            if term not in {"销售额", "利润", "利润率", "数量", "订单数"}
        ]
    )
    if analysis_mode == AnalysisMode.WHY_ANALYSIS:
        return [
            AnalysisPlanStep(
                step_id="step-1",
                title="验证现象",
                goal="确认用户想解释的现象是否真实存在",
                question=question,
                purpose="先确认现象是否成立，并明确差异方向与幅度",
                step_type=PlanStepType.QUERY,
                uses_primary_query=True,
                semantic_focus=step_focus,
                expected_output="确认现象是否成立，并明确差异方向与幅度",
            ),
            AnalysisPlanStep(
                step_id="step-2",
                title="定位异常切片",
                goal="定位最异常的对象或切片",
                question=f"围绕“{question}”继续按关键维度切片比较，找出异常最明显的切片。",
                purpose="找到最可能承载原因的证据切片",
                step_type=PlanStepType.QUERY,
                depends_on=["step-1"],
                semantic_focus=_dedupe_strings(["异常定位", *step_focus]),
                expected_output="定位异常对象集合或关键切片",
                candidate_axes=candidate_axes or ["时间", "地区", "产品", "组织"],
            ),
            AnalysisPlanStep(
                step_id="step-3",
                title="归因总结",
                goal="汇总证据链并输出原因总结",
                question=f"基于前两步结果，总结“{question}”最可能的原因。",
                purpose="把数据现象和解释链条连接起来",
                step_type=PlanStepType.SYNTHESIS,
                depends_on=["step-1", "step-2"],
                semantic_focus=_dedupe_strings(["证据汇总", "原因归纳", *step_focus[:2]]),
                expected_output="形成结论、证据摘要和待确认口径",
            ),
        ]

    if analysis_mode == AnalysisMode.MULTI_STEP_ANALYSIS:
        return [
            AnalysisPlanStep(
                step_id="step-1",
                title="主问题首跳",
                goal="先生成覆盖主问题核心目标的首个关键查询",
                question=question,
                purpose="先得到主问题首跳结果",
                step_type=PlanStepType.QUERY,
                uses_primary_query=True,
                semantic_focus=_dedupe_strings(["主问题", *step_focus[:3]]),
                expected_output="得到主问题首跳结果",
            ),
            AnalysisPlanStep(
                step_id="step-2",
                title="补充验证",
                goal="补充验证后续逻辑依赖的基线或切片",
                question=f"围绕“{question}”补充验证后续分析所需的基线、维度或依赖信息。",
                purpose="为最终回答补齐依赖证据",
                step_type=PlanStepType.QUERY,
                depends_on=["step-1"],
                semantic_focus=_dedupe_strings(["补充验证", "依赖补齐", *step_focus[:3]]),
                expected_output="补齐复杂逻辑所需的依赖信息",
                candidate_axes=candidate_axes,
            ),
            AnalysisPlanStep(
                step_id="step-3",
                title="结果合并",
                goal="合并前序结果并输出最终回答",
                question=f"结合前面步骤结果，整理“{question}”的最终回答。",
                purpose="把前序证据合并成最终回答",
                step_type=PlanStepType.SYNTHESIS,
                depends_on=["step-1", "step-2"],
                semantic_focus=_dedupe_strings(["结果汇总", "风险提示", *step_focus[:2]]),
                expected_output="形成最终回答及剩余风险点",
            ),
        ]

    return []


def _normalize_plan_steps(
    steps: list[AnalysisPlanStep],
    *,
    analysis_mode: AnalysisMode,
    question: str,
) -> list[AnalysisPlanStep]:
    normalized_steps: list[AnalysisPlanStep] = []
    for index, step in enumerate(steps, start=1):
        step_id = step.step_id or f"step-{index}"
        title = step.title.strip() or f"步骤 {index}"
        step_type = step.step_type
        question_text = (step.question or step.goal or title).strip()
        goal = (step.goal or step.purpose or question_text).strip()
        purpose = (step.purpose or step.goal or question_text).strip()
        depends_on = _dedupe_strings(step.depends_on)

        if index == 1 and step_type == PlanStepType.QUERY:
            uses_primary_query = True if analysis_mode != AnalysisMode.COMPLEX_SINGLE_QUERY else step.uses_primary_query
        else:
            uses_primary_query = step.uses_primary_query

        if not depends_on and index > 1:
            if step_type == PlanStepType.SYNTHESIS:
                depends_on = [prior.step_id or f"step-{idx}" for idx, prior in enumerate(normalized_steps, start=1)]
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
                uses_primary_query=uses_primary_query,
                depends_on=depends_on,
                semantic_focus=_dedupe_strings(step.semantic_focus),
                expected_output=(step.expected_output or goal or purpose).strip(),
                candidate_axes=_dedupe_strings(step.candidate_axes),
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
) -> GlobalUnderstandingOutput:
    analysis_mode = output.analysis_mode
    focus_terms = _extract_focus_terms(prefilter_result, feature_output)
    if analysis_mode in {AnalysisMode.WHY_ANALYSIS, AnalysisMode.MULTI_STEP_ANALYSIS}:
        single_query_feasible = False
    elif analysis_mode == AnalysisMode.COMPLEX_SINGLE_QUERY:
        single_query_feasible = True
    else:
        single_query_feasible = output.single_query_feasible

    blockers = _dedupe_blockers(output.single_query_blockers)
    needs_clarification = bool(
        output.needs_clarification or (output.clarification_question or "").strip()
    )
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
        clarification_question=(output.clarification_question or base_plan.clarification_question),
        clarification_options=_dedupe_strings(
            output.clarification_options or base_plan.clarification_options
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
) -> GlobalUnderstandingOutput:
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
            )
        ),
    ]
    return await stream_llm_structured(
        llm=llm,
        messages=messages,
        output_model=GlobalUnderstandingOutput,
    )


async def global_understanding_node(state: SemanticParserState) -> dict[str, Any]:
    """生成统一的全局理解结果。

    当前实现：
    - LLM 主导判断是否单查、是否拆步以及初始 plan
    - 规则 planner 仅作为失败兜底与结构补全来源
    - 不直接负责字段 grounding，仅负责全局结构理解契约
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
    global_understanding = None
    llm_used = False
    fallback_used = False

    if question.strip():
        try:
            llm_output = await _run_llm_global_understanding(
                question,
                prefilter_result=prefilter_result,
                feature_output=feature_output,
            )
            global_understanding = _normalize_global_understanding_output(
                llm_output,
                question=question,
                prefilter_result=prefilter_result,
                feature_output=feature_output,
            )
            llm_used = True
        except Exception as exc:
            logger.warning(
                "global_understanding_node: LLM 路径失败，回退规则 fallback: %s",
                exc,
            )

    if global_understanding is None:
        fallback_plan = build_analysis_plan(
            question=question,
            prefilter_result=prefilter_result,
            feature_output=feature_output,
        )
        global_understanding = build_global_understanding_fallback(question, fallback_plan)
        fallback_used = True

    elapsed_ms = (time.time() - start_time) * 1000
    logger.info(
        "global_understanding_node: mode=%s, single_query_feasible=%s, llm_used=%s, elapsed=%.1fms",
        global_understanding.analysis_mode.value,
        global_understanding.single_query_feasible,
        llm_used,
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
            global_understanding_llm_used=llm_used,
            global_understanding_fallback_used=fallback_used,
        ),
    }


__all__ = ["global_understanding_node"]
