# -*- coding: utf-8 -*-
"""复杂问题 / why 问题分析计划节点。"""

import logging
import time
from typing import Any, Optional

from ..node_utils import merge_metrics
from ..schemas.planner import (
    AnalysisMode,
    AnalysisPlan,
    AnalysisPlanStep,
    GlobalUnderstandingOutput,
    PlanMode,
    PlanStepType,
    QueryFeasibilityBlocker,
    parse_analysis_plan,
)
from ..schemas.prefilter import (
    ComplexityType,
    FeatureExtractionOutput,
    PrefilterResult,
)
from ..state import SemanticParserState

logger = logging.getLogger(__name__)

_WHY_KEYWORDS = (
    "为什么",
    "为何",
    "原因",
    "成因",
    "驱动因素",
    "根因",
    "背后",
    "怎么回事",
    "why",
    "reason",
    "root cause",
)

_DECOMPOSITION_KEYWORDS = (
    "分别",
    "各自",
    "同时",
    "并且",
    "以及",
    "拆解",
    "构成",
    "路径",
    "影响",
    "驱动",
    "对比",
    "比较",
    "先",
    "再",
)

# 明确暗示并行执行的关键词（子问题之间无依赖）
_PARALLEL_KEYWORDS = (
    "分别",
    "各自",
    "同时",
    "并且",
    "以及",
    "对比",
    "比较",
    "和",
    "与",
    "vs",
)

# 明确暗示顺序执行的关键词（后步依赖前步结果）
_SEQUENTIAL_KEYWORDS = (
    "先",
    "再",
    "然后",
    "接着",
    "之后",
    "基于",
    "根据前面",
)


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _dedupe_terms(terms: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for term in terms:
        normalized = (term or "").strip()
        if not normalized:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


def _get_focus_terms(
    prefilter_result: Optional[PrefilterResult],
    feature_output: Optional[FeatureExtractionOutput],
) -> list[str]:
    terms: list[str] = []

    if feature_output:
        terms.extend(feature_output.required_measures)
        terms.extend(feature_output.required_dimensions)
        terms.extend(feature_output.confirmed_time_hints)

    if prefilter_result:
        terms.extend(
            matched.display_name
            for matched in prefilter_result.matched_computations
            if matched.display_name
        )

    return _dedupe_terms(terms)[:6]


def _get_focus_subject(focus_terms: list[str]) -> str:
    if not focus_terms:
        return "核心指标与关键维度"
    return "、".join(focus_terms[:3])


# ── field_semantic 维度提取 ────────────────────────────────────────────────

_CATEGORY_DISPLAY: dict[str, str] = {
    "time": "时间",
    "geography": "地区",
    "product": "产品",
    "product_line": "产品线",
    "channel": "渠道",
    "organization": "组织",
    "customer": "客户",
    "segment": "细分",
    "category": "类别",
}

_FALLBACK_CANDIDATE_AXES = ["时间", "地区", "产品", "组织"]


def _extract_dimension_axes(
    field_semantic: Optional[dict[str, Any]],
    *,
    max_axes: int = 6,
) -> list[str]:
    """从 field_semantic 提取可用维度类别作为 candidate_axes。

    遍历 field_semantic 中 role=dimension 的字段，收集其 category/
    hierarchy_category 并去重，映射为中文显示名。若 field_semantic
    为空则回退到默认硬编码列表。
    """
    if not field_semantic:
        return list(_FALLBACK_CANDIDATE_AXES)

    seen: set[str] = set()
    axes: list[str] = []

    for field_name, info in field_semantic.items():
        if not isinstance(info, dict):
            continue
        role = info.get("role", "")
        if role != "dimension":
            continue
        category = (
            info.get("hierarchy_category")
            or info.get("category")
            or ""
        ).strip().lower()
        if not category or category in seen:
            continue
        seen.add(category)
        display = _CATEGORY_DISPLAY.get(category, category)
        axes.append(display)
        if len(axes) >= max_axes:
            break

    return axes if axes else list(_FALLBACK_CANDIDATE_AXES)


def _build_axes_phrase(
    axes: list[str],
    *,
    conjunction: str = "、",
) -> str:
    """将 candidate_axes 列表拼接为自然语言片段。"""
    if not axes:
        return "各关键维度"
    return conjunction.join(axes[:4])


def _build_why_plan(
    question: str,
    focus_terms: list[str],
    field_semantic: Optional[dict[str, Any]] = None,
) -> AnalysisPlan:
    focus_subject = _get_focus_subject(focus_terms)
    candidate_axes = _extract_dimension_axes(field_semantic)
    axes_phrase = _build_axes_phrase(candidate_axes)
    return AnalysisPlan(
        plan_mode=PlanMode.WHY_ANALYSIS,
        needs_planning=True,
        requires_llm_reasoning=True,
        goal=f"解释并验证问题背后的原因：{question}",
        execution_strategy="sequential",
        reasoning_focus=[
            "先确认用户关心的现象、指标口径和时间范围",
            "再定位差异最大的切片和异常贡献来源",
            "最后基于证据归纳原因，不足时优先发起澄清",
        ],
        sub_questions=[
            AnalysisPlanStep(
                step_id="step-1",
                title="验证现象",
                goal="确认用户想解释的现象是否真实存在",
                question=question,
                purpose="先用首跳查询确认用户想解释的现象是否真实存在",
                step_type=PlanStepType.QUERY,
                uses_primary_query=True,
                semantic_focus=focus_terms or ["现象验证", "时间基线", "指标口径"],
                expected_output="确认现象是否成立，并明确差异方向与幅度",
                clarification_if_missing=["比较基线", "时间范围", "指标口径"],
            ),
            AnalysisPlanStep(
                step_id="step-2",
                title="定位异常切片",
                goal="定位最异常的对象或切片",
                question=(
                    f"围绕\u201c{question}\u201d，继续按{axes_phrase}切片比较 {focus_subject} 的变化，"
                    "找出贡献最大或异常最明显的切片。"
                ),
                purpose="找到最可能承载原因的证据切片",
                step_type=PlanStepType.QUERY,
                depends_on=["step-1"],
                semantic_focus=focus_terms or ["异常定位", "切片比较", "贡献分析"],
                expected_output="定位异常对象集合或关键切片",
                candidate_axes=_extract_dimension_axes(field_semantic),
            ),
            AnalysisPlanStep(
                step_id="step-3",
                title="归因总结",
                goal="汇总证据链并输出原因总结",
                question=f"基于前两步结果，总结“{question}”最可能的原因，并指出仍需澄清的口径。",
                purpose="把数据现象和解释链条连接起来",
                step_type=PlanStepType.SYNTHESIS,
                depends_on=["step-1", "step-2"],
                semantic_focus=["证据汇总", "原因归纳", "风险提示"],
                expected_output="形成结论、证据摘要和待确认口径",
            ),
        ],
        retrieval_focus_terms=focus_terms,
        planner_confidence=0.95,
    )


def _build_parallel_plan(
    question: str,
    focus_terms: list[str],
    field_semantic: Optional[dict[str, Any]] = None,
) -> AnalysisPlan:
    """构建并行子问题计划：子问题之间无依赖，可同时执行。"""
    focus_subject = _get_focus_subject(focus_terms)
    candidate_axes = _extract_dimension_axes(field_semantic)
    axes_phrase = _build_axes_phrase(candidate_axes)

    return AnalysisPlan(
        plan_mode=PlanMode.DECOMPOSED_QUERY,
        needs_planning=True,
        requires_llm_reasoning=True,
        goal=f"并行拆解并对比分析：{question}",
        execution_strategy="parallel",
        reasoning_focus=[
            "每个子问题独立生成完整查询骨架",
            "关注对比/并列的多个分析维度或对象",
            "最终汇总时进行跨子问题的对比与洞察",
        ],
        sub_questions=[
            AnalysisPlanStep(
                step_id="step-1",
                title="主视角查询",
                goal="覆盖主问题的核心查询",
                question=question,
                purpose="先产出覆盖主问题的核心查询骨架",
                step_type=PlanStepType.QUERY,
                uses_primary_query=True,
                semantic_focus=focus_terms or ["主问题", "首跳验证"],
                expected_output="主视角的核心查询结果",
            ),
            AnalysisPlanStep(
                step_id="step-2",
                title="补充视角查询",
                goal="覆盖对比或并列的补充视角",
                question=(
                    f"围绕\u201c{question}\u201d，从{axes_phrase}等视角补充查询 {focus_subject}，"
                    "与主查询形成对比或并列。"
                ),
                purpose="独立于主查询，提供补充视角",
                step_type=PlanStepType.QUERY,
                depends_on=[],
                semantic_focus=focus_terms or ["补充视角", "对比并列"],
                expected_output="补充视角的查询结果",
            ),
            AnalysisPlanStep(
                step_id="step-3",
                title="汇总对比",
                goal="合并并对比前序并行查询结果",
                question=f"结合前面各步骤的结果，对比分析\u201c{question}\u201d的完整回答。",
                purpose="跨子问题汇总与对比",
                step_type=PlanStepType.SYNTHESIS,
                depends_on=["step-1", "step-2"],
                semantic_focus=["对比汇总", "差异分析", "风险提示"],
                expected_output="完整的对比分析与风险点",
            ),
        ],
        retrieval_focus_terms=focus_terms,
        planner_confidence=0.85,
    )


def _build_complex_plan(
    question: str,
    complexities: list[ComplexityType],
    focus_terms: list[str],
    cue_driven: bool,
    field_semantic: Optional[dict[str, Any]] = None,
) -> AnalysisPlan:
    focus_subject = _get_focus_subject(focus_terms)
    candidate_axes = _extract_dimension_axes(field_semantic)
    complexity_names = [
        complexity.value if hasattr(complexity, "value") else str(complexity)
        for complexity in complexities
        if complexity != ComplexityType.SIMPLE
    ]
    complexity_desc = "、".join(complexity_names) if complexity_names else "多步拆解"

    reasoning_focus = [
        "先拆清指标、维度、筛选和时间口径",
        "再明确复杂计算或对比逻辑依赖哪些基础字段",
        "如果一个查询无法覆盖全部意图，优先输出首个关键查询骨架",
    ]
    if cue_driven and not complexity_names:
        reasoning_focus.append("问题存在明显多子任务信号，避免把多个目标压成一次简单聚合")

    return AnalysisPlan(
        plan_mode=PlanMode.DECOMPOSED_QUERY,
        needs_planning=True,
        requires_llm_reasoning=True,
        goal=f"拆解复杂查询并保留多步分析视角：{question}",
        execution_strategy="sequential",
        reasoning_focus=reasoning_focus,
        sub_questions=[
            AnalysisPlanStep(
                step_id="step-1",
                title="主问题首跳",
                goal="先生成覆盖主问题核心目标的首个关键查询",
                question=question,
                purpose="先产出覆盖主问题的首个关键查询骨架",
                step_type=PlanStepType.QUERY,
                uses_primary_query=True,
                semantic_focus=focus_terms or ["主问题", "首跳验证"],
                expected_output="得到主问题首跳查询的核心结果",
            ),
            AnalysisPlanStep(
                step_id="step-2",
                title="补充验证",
                goal="验证复杂逻辑依赖的基础字段、时间基线或补充维度",
                question=(
                    f"围绕“{question}”，补充验证 {focus_subject} 涉及的 {complexity_desc} 逻辑，"
                    "明确必要的基础度量、维度或时间基线。"
                ),
                purpose="明确复杂计算依赖的字段和顺序",
                step_type=PlanStepType.QUERY,
                depends_on=["step-1"],
                semantic_focus=focus_terms or ["补充验证", "复杂计算依赖"],
                expected_output="补齐复杂逻辑所需的口径或依赖字段",
                candidate_axes=candidate_axes or ["基础度量", "时间基线", "对比维度"],
            ),
            AnalysisPlanStep(
                step_id="step-3",
                title="结果合并",
                goal="合并前序查询结果并输出最终回答",
                question=f"结合前面步骤结果，整理“{question}”的最终回答和剩余风险点。",
                purpose="把复杂问题拆出来的证据重新合并",
                step_type=PlanStepType.SYNTHESIS,
                depends_on=["step-1", "step-2"],
                semantic_focus=["结果汇总", "风险提示"],
                expected_output="形成最终回答及剩余风险点",
            ),
        ],
        retrieval_focus_terms=focus_terms,
        planner_confidence=0.88 if complexity_names else 0.72,
    )


def build_analysis_plan(
    question: str,
    prefilter_result: Optional[PrefilterResult] = None,
    feature_output: Optional[FeatureExtractionOutput] = None,
    field_semantic: Optional[dict[str, Any]] = None,
) -> AnalysisPlan:
    """根据规则与特征输出构建分析计划。"""

    normalized_question = (question or "").strip()
    if not normalized_question:
        return AnalysisPlan(
            plan_mode=PlanMode.DIRECT_QUERY,
            needs_planning=False,
            requires_llm_reasoning=False,
            planner_confidence=0.0,
        )

    question_lower = normalized_question.casefold()
    focus_terms = _get_focus_terms(prefilter_result, feature_output)
    detected_complexity = (
        prefilter_result.detected_complexity
        if prefilter_result and prefilter_result.detected_complexity
        else [ComplexityType.SIMPLE]
    )
    non_simple_complexities = [
        complexity
        for complexity in detected_complexity
        if complexity != ComplexityType.SIMPLE
    ]

    why_detected = _contains_any(question_lower, _WHY_KEYWORDS)
    decomposition_cues = _contains_any(question_lower, _DECOMPOSITION_KEYWORDS)
    parallel_cues = _contains_any(question_lower, _PARALLEL_KEYWORDS)
    sequential_cues = _contains_any(question_lower, _SEQUENTIAL_KEYWORDS)
    cue_driven_planning = decomposition_cues and (
        len(focus_terms) >= 2 or len(normalized_question) >= 18
    )

    if why_detected:
        return _build_why_plan(normalized_question, focus_terms, field_semantic)

    # 并行场景：有并行关键词、无顺序关键词、问题足够有意义
    if (
        parallel_cues
        and not sequential_cues
        and not why_detected
        and len(normalized_question) >= 10
    ):
        return _build_parallel_plan(normalized_question, focus_terms, field_semantic)

    if non_simple_complexities or cue_driven_planning:
        return _build_complex_plan(
            normalized_question,
            detected_complexity,
            focus_terms,
            cue_driven=cue_driven_planning,
            field_semantic=field_semantic,
        )

    return AnalysisPlan(
        plan_mode=PlanMode.DIRECT_QUERY,
        single_query_feasible=True,
        needs_planning=False,
        requires_llm_reasoning=False,
        decomposition_reason="当前问题可沿单步语义理解路径直接落成查询",
        goal="直接解析用户查询并生成结构化查询骨架",
        execution_strategy="single_query",
        retrieval_focus_terms=focus_terms,
        planner_confidence=0.98,
    )


def build_global_understanding_fallback(
    question: str,
    plan: AnalysisPlan,
) -> GlobalUnderstandingOutput:
    """基于现有规则 planner 构建一个过渡期的全局理解结果。

    说明：
    - 当前实现仍然是 fallback，不替代后续真正的 LLM global understanding。
    - 这里的目标是把旧 planner 显式降级为过渡层，先统一输出契约。
    """

    normalized_question = (question or "").strip() or None
    blockers: list[QueryFeasibilityBlocker] = []

    if plan.plan_mode == PlanMode.WHY_ANALYSIS:
        analysis_mode = AnalysisMode.WHY_ANALYSIS
        blockers.extend(
            [
                QueryFeasibilityBlocker.MULTI_HOP_REASONING,
                QueryFeasibilityBlocker.DYNAMIC_AXIS_SELECTION,
            ]
        )
    elif plan.plan_mode == PlanMode.DECOMPOSED_QUERY:
        analysis_mode = AnalysisMode.MULTI_STEP_ANALYSIS
        blockers.append(QueryFeasibilityBlocker.RESULT_SET_DEPENDENCY)
    else:
        analysis_mode = AnalysisMode.SINGLE_QUERY

    single_query_feasible = (
        plan.plan_mode == PlanMode.DIRECT_QUERY and plan.single_query_feasible
    )

    return GlobalUnderstandingOutput(
        analysis_mode=analysis_mode,
        single_query_feasible=single_query_feasible,
        single_query_blockers=[] if single_query_feasible else blockers,
        decomposition_reason=plan.decomposition_reason,
        needs_clarification=plan.needs_clarification,
        clarification_question=plan.clarification_question,
        clarification_options=plan.clarification_options,
        primary_restated_question=normalized_question,
        risk_flags=plan.risk_flags,
        llm_confidence=plan.planner_confidence,
        analysis_plan=plan,
    )


def _build_analysis_planner_compat_fallback(question: str) -> AnalysisPlan:
    """analysis_planner 缺少上游结果时的最小兼容 fallback。"""
    normalized_question = (question or "").strip()
    return AnalysisPlan(
        plan_mode=PlanMode.DIRECT_QUERY,
        single_query_feasible=True,
        needs_planning=False,
        requires_llm_reasoning=False,
        decomposition_reason=(
            "analysis_planner 未收到 global_understanding，"
            "回退为最小 direct-query 兼容路径"
        ),
        goal=(
            f"直接解析用户查询：{normalized_question}"
            if normalized_question
            else "直接解析用户查询"
        ),
        execution_strategy="single_query",
        planner_confidence=0.2,
    )


async def analysis_planner_node(state: SemanticParserState) -> dict[str, object]:
    """分析计划节点。

    迁移期兼容层：
    - 优先消费 global_understanding.analysis_plan
    - 若不存在，仅回退到最小 direct-query 兼容计划
    """

    start_time = time.time()
    question = state.get("question", "")
    global_understanding_raw = state.get("global_understanding")
    compat_fallback_used = False

    plan = parse_analysis_plan(
        raw_analysis_plan=state.get("analysis_plan"),
        raw_global_understanding=global_understanding_raw,
    )
    global_understanding = None
    if global_understanding_raw:
        try:
            global_understanding = GlobalUnderstandingOutput.model_validate(
                global_understanding_raw
            )
        except Exception:
            global_understanding = None

    if plan is None:
        compat_fallback_used = True
        plan = _build_analysis_planner_compat_fallback(question)
        global_understanding = build_global_understanding_fallback(question, plan)
    elif global_understanding is None:
        global_understanding = build_global_understanding_fallback(question, plan)

    elapsed_ms = (time.time() - start_time) * 1000
    logger.info(
        "analysis_planner_node: mode=%s, needs_planning=%s, sub_questions=%s, elapsed=%.1fms",
        plan.plan_mode.value,
        plan.needs_planning,
        len(plan.sub_questions),
        elapsed_ms,
    )

    return {
        "analysis_plan": plan.model_dump(),
        "global_understanding": global_understanding.model_dump(),
        "optimization_metrics": merge_metrics(
            state,
            analysis_planner_ms=elapsed_ms,
            analysis_planner_mode=plan.plan_mode.value,
            analysis_planner_triggered=plan.needs_planning,
            analysis_planner_compat_fallback=compat_fallback_used,
        ),
    }


__all__ = [
    "build_analysis_plan",
    "_build_analysis_planner_compat_fallback",
    "build_global_understanding_fallback",
    "analysis_planner_node",
]
