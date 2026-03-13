# -*- coding: utf-8 -*-
"""workflow/root 共用的确定性 planner 辅助函数。"""

from __future__ import annotations

from typing import Any, Optional

from analytics_assistant.src.agents.semantic_parser.schemas.planner import (
    AnalysisPlan,
    AnalysisPlanStep,
    AxisEvidenceScore,
    EvidenceContext,
    PlanStepKind,
    PlanStepType,
    StepArtifact,
    parse_analysis_plan as resolve_analysis_plan,
)


def parse_analysis_plan(
    raw: Any,
    raw_global_understanding: Any = None,
) -> Optional[AnalysisPlan]:
    """把原始 analysis_plan 解析成强类型 schema。"""
    return resolve_analysis_plan(
        raw_analysis_plan=raw,
        raw_global_understanding=raw_global_understanding,
    )


def serialize_plan_step(
    step: AnalysisPlanStep,
    *,
    index: int,
    total: int,
) -> dict[str, Any]:
    """把 planner step 投影成 SSE 友好的 payload。"""
    return {
        "stepId": step.step_id or f"step-{index}",
        "index": index,
        "total": total,
        "title": step.title,
        "question": step.question,
        "purpose": step.purpose or "",
        "stepType": step.step_type.value,
        "stepKind": step.step_kind.value if step.step_kind else None,
        "usesPrimaryQuery": step.uses_primary_query,
        "dependsOn": step.depends_on,
        "semanticFocus": step.semantic_focus,
        "candidateAxes": step.candidate_axes,
        "expectedOutput": step.expected_output or "",
        "targetsAnomaly": step.targets_anomaly,
    }


def build_initial_evidence_context(original_question: str) -> EvidenceContext:
    """创建多步分析的初始证据上下文。"""
    return EvidenceContext(primary_question=original_question)


def append_step_artifact(
    evidence_context: EvidenceContext,
    *,
    step_payload: dict[str, Any],
    query_id: Optional[str] = None,
    restated_question: Optional[str] = None,
    table_data: Optional[dict[str, Any]] = None,
    summary_text: Optional[str] = None,
    blocked_reason: Optional[str] = None,
    semantic_summary: Optional[dict[str, Any]] = None,
    key_findings: Optional[list[str]] = None,
    entity_scope: Optional[list[str]] = None,
    validated_axes: Optional[list[str]] = None,
    evidence_context_before_step: Optional[EvidenceContext] = None,
    open_questions: Optional[list[str]] = None,
) -> EvidenceContext:
    """把一个已完成 step 沉淀到累计 evidence_context 中。"""
    updated_context = evidence_context.model_copy(deep=True)
    step_type = PlanStepType(step_payload.get("stepType", PlanStepType.QUERY.value))
    resolved_summary = summary_text or summarize_table_data(table_data or {})
    resolved_entity_scope = _dedupe_keep_order(
        list(entity_scope or _extract_entity_scope(table_data))
    )
    resolved_validated_axes = _dedupe_keep_order(
        list(
            validated_axes
            or resolve_step_validated_axes(
                step_payload,
                semantic_summary,
                evidence_context_before_step=evidence_context_before_step,
                table_data=table_data,
            )
        )
    )
    resolved_key_findings = _dedupe_keep_order(
        list(key_findings or ([resolved_summary] if resolved_summary else []))
    )
    resolved_open_questions = _dedupe_keep_order(list(open_questions or []))

    updated_context.step_artifacts.append(
        StepArtifact(
            step_id=str(step_payload.get("stepId") or f"step-{step_payload.get('index', '?')}"),
            title=step_payload.get("title", "Step"),
            step_type=step_type,
            step_kind=(
                PlanStepKind(step_payload["stepKind"])
                if step_payload.get("stepKind")
                else None
            ),
            query_id=query_id,
            restated_question=restated_question,
            table_summary=resolved_summary,
            key_findings=resolved_key_findings,
            entity_scope=resolved_entity_scope,
            targets_anomaly=bool(step_payload.get("targetsAnomaly")),
            validated_axes=resolved_validated_axes,
            blocked_reason=blocked_reason,
        )
    )
    updated_context.key_entities = _dedupe_keep_order(
        [*updated_context.key_entities, *resolved_entity_scope]
    )
    updated_context.validated_axes = _dedupe_keep_order(
        [*updated_context.validated_axes, *resolved_validated_axes]
    )
    updated_context.open_questions = _dedupe_keep_order(
        [*updated_context.open_questions, *resolved_open_questions]
    )
    if _step_targets_anomaly(step_payload):
        updated_context.anomalous_entities = _dedupe_keep_order(
            [*updated_context.anomalous_entities, *resolved_entity_scope]
        )
    updated_context.axis_scores = _merge_axis_scores(
        updated_context.axis_scores,
        _build_axis_scores(
            step_payload,
            resolved_validated_axes,
            evidence_context_before_step=evidence_context_before_step,
            semantic_summary=semantic_summary,
            table_data=table_data,
        ),
    )
    return updated_context


def build_evidence_insight_output(
    original_question: str,
    evidence_context: EvidenceContext,
    completed_steps: list[dict[str, Any]],
) -> dict[str, Any]:
    """把累计 evidence_context 投影成最终 insight payload。"""
    summary = ""
    for artifact in reversed(evidence_context.step_artifacts):
        if artifact.step_type == PlanStepType.SYNTHESIS and artifact.table_summary:
            summary = artifact.table_summary
            break
    if not summary:
        summary = build_synthesis_step_summary(original_question, completed_steps)

    findings: list[dict[str, Any]] = []
    if evidence_context.validated_axes:
        findings.append({
            "finding_type": "comparison",
            "analysis_level": "diagnostic",
            "description": "当前已完成初步筛查的解释轴为：" + "、".join(evidence_context.validated_axes[:3]),
            "supporting_data": {"validated_axes": evidence_context.validated_axes[:5]},
            "confidence": 0.7,
        })
    if evidence_context.anomalous_entities:
        findings.append({
            "finding_type": "comparison",
            "analysis_level": "diagnostic",
            "description": "当前已定位的异常对象包括：" + "、".join(evidence_context.anomalous_entities[:3]),
            "supporting_data": {"anomalous_entities": evidence_context.anomalous_entities[:5]},
            "confidence": 0.72,
        })
    if evidence_context.axis_scores:
        findings.append({
            "finding_type": "comparison",
            "analysis_level": "diagnostic",
            "description": "当前解释轴优先级为："
            + "、".join(
                f"{score.axis}({score.explained_share:.0%})"
                for score in evidence_context.axis_scores[:3]
            ),
            "supporting_data": {
                "axis_scores": [
                    score.model_dump(mode="json")
                    for score in evidence_context.axis_scores[:5]
                ],
            },
            "confidence": min(
                0.82,
                max((score.confidence for score in evidence_context.axis_scores[:3]), default=0.7),
            ),
        })

    for artifact in evidence_context.step_artifacts:
        descriptions = artifact.key_findings or (
            [artifact.table_summary] if artifact.table_summary else []
        )
        for description in descriptions[:2]:
            normalized = str(description or "").strip()
            if not normalized:
                continue
            findings.append({
                "finding_type": "comparison",
                "analysis_level": "diagnostic",
                "description": normalized,
                "supporting_data": {
                    "step_id": artifact.step_id,
                    "title": artifact.title,
                    "step_kind": artifact.step_kind.value if artifact.step_kind else None,
                    "query_id": artifact.query_id,
                    "entity_scope": artifact.entity_scope,
                    "validated_axes": artifact.validated_axes,
                },
                "confidence": 0.72,
            })
        if len(findings) >= 6:
            break

    if not findings:
        findings.append({
            "finding_type": "comparison",
            "analysis_level": "diagnostic",
            "description": summary,
            "supporting_data": {"step_count": len(evidence_context.step_artifacts)},
            "confidence": 0.65,
        })

    overall_confidence = min(0.9, 0.55 + 0.05 * len(findings))
    return {
        "summary": summary,
        "overall_confidence": overall_confidence,
        "findings": findings,
    }


def build_evidence_bundle_dict(
    original_question: str,
    evidence_context: EvidenceContext,
    *,
    source: str = "planner_synthesis",
    query_id: Optional[str] = None,
) -> dict[str, Any]:
    """把 planner/why 的证据链收口成正式 evidence bundle。"""
    return {
        "bundle_version": "1.0",
        "source": str(source or "planner_synthesis").strip() or "planner_synthesis",
        "question": str(original_question or "").strip(),
        "query_id": str(query_id or "").strip() or None,
        "semantic_summary": {},
        "result_manifest_ref": None,
        "result_profile": {},
        "step_count": len(evidence_context.step_artifacts),
        "latest_summary": _extract_latest_evidence_summary(evidence_context),
        "step_artifacts": [artifact.model_dump(mode="json") for artifact in evidence_context.step_artifacts],
        "validated_axes": list(evidence_context.validated_axes),
        "axis_scores": [score.model_dump(mode="json") for score in evidence_context.axis_scores],
        "anomalous_entities": list(evidence_context.anomalous_entities),
        "key_entities": list(evidence_context.key_entities),
        "open_questions": list(evidence_context.open_questions),
    }


def build_step_insight_output(
    step_payload: dict[str, Any],
    summary_text: str,
    semantic_summary: Optional[dict[str, Any]],
    table_data: Optional[dict[str, Any]],
) -> dict[str, Any]:
    """为单个 query step 构造轻量结构化 insight。"""
    semantic_summary = semantic_summary or {}
    entity_scope = _extract_entity_scope(table_data)
    validated_axes = resolve_step_validated_axes(step_payload, semantic_summary)
    return {
        "summary": summary_text,
        "overall_confidence": 0.66,
        "findings": [{
            "finding_type": "comparison",
            "analysis_level": "diagnostic",
            "description": summary_text,
            "supporting_data": {
                "step_id": step_payload.get("stepId"),
                "title": step_payload.get("title"),
                "step_kind": step_payload.get("stepKind"),
                "entity_scope": entity_scope,
                "validated_axes": validated_axes,
            },
            "confidence": 0.66,
        }],
    }


def extract_insight_key_findings(insight_output_dict: Optional[dict[str, Any]]) -> list[str]:
    """从 insight payload 中提取可继续积累的关键发现。"""
    if not isinstance(insight_output_dict, dict):
        return []
    findings: list[str] = []
    for raw_finding in insight_output_dict.get("findings") or []:
        if not isinstance(raw_finding, dict):
            continue
        description = str(raw_finding.get("description") or "").strip()
        if description:
            findings.append(description)
    if findings:
        return _dedupe_keep_order(findings)
    summary = str(insight_output_dict.get("summary") or "").strip()
    return [summary] if summary else []


def _extract_latest_evidence_summary(evidence_context: EvidenceContext) -> str:
    """提取最后一条可供最终洞察和重规划复用的证据摘要。"""
    for artifact in reversed(evidence_context.step_artifacts):
        summary = str(artifact.table_summary or "").strip()
        if summary:
            return summary
    return ""


def get_primary_plan_step(
    analysis_plan: AnalysisPlan,
) -> tuple[Optional[int], Optional[AnalysisPlanStep]]:
    """找到最适合优先复用主问题的 query step。"""
    for index, step in enumerate(analysis_plan.sub_questions, start=1):
        if step.step_type == PlanStepType.QUERY and step.uses_primary_query:
            return index, step
    for index, step in enumerate(analysis_plan.sub_questions, start=1):
        if step.step_type == PlanStepType.QUERY:
            return index, step
    return None, None


def summarize_table_data(table_data: dict[str, Any]) -> str:
    """把结果表概括成可直接面向用户的简短摘要。"""
    if not isinstance(table_data, dict):
        return "未返回可展示的结果行。"
    row_count = int(table_data.get("rowCount") or 0)
    columns = table_data.get("columns") or []
    column_names = [
        str(column.get("name", ""))
        for column in columns
        if isinstance(column, dict) and column.get("name")
    ]
    preview_columns = "、".join(column_names[:3]) if column_names else "无字段信息"
    return f"返回 {row_count} 行数据，主要字段包括 {preview_columns}。"


def build_query_step_summary(
    step_payload: dict[str, Any],
    semantic_summary: dict[str, Any],
    table_data: dict[str, Any],
) -> str:
    """构造 query step 的可读摘要。"""
    measures = _coerce_text_list(semantic_summary.get("measures") or [])
    dimensions = _coerce_text_list(semantic_summary.get("dimensions") or [])
    filters = _coerce_text_list(semantic_summary.get("filters") or [])
    step_kind = str(step_payload.get("stepKind") or "").strip()
    candidate_axes = _dedupe_keep_order([
        str(item)
        for item in (step_payload.get("candidateAxes") or [])
        if str(item or "").strip()
    ])
    measure_text = "、".join(measures[:3]) if measures else "核心指标"
    dimension_text = "、".join(dimensions[:3]) if dimensions else "整体"
    filter_text = f"，筛选字段：{'、'.join(filters[:2])}" if filters else ""
    result_summary = summarize_table_data(table_data)

    if step_kind == PlanStepKind.VERIFY_ANOMALY.value:
        return (
            f"{step_payload['title']}已完成：已对异常现象进行验证，围绕 {measure_text} 按 "
            f"{dimension_text} 完成基线校验{filter_text}。{result_summary}"
        )
    if step_kind == PlanStepKind.RANK_EXPLANATORY_AXES.value:
        axis_text = "、".join(candidate_axes[:3]) if candidate_axes else dimension_text
        return (
            f"{step_payload['title']}已完成：已围绕 {axis_text} 给出解释轴优先级，"
            f"当前结果可用于决定后续 screening 先查哪条线。{result_summary}"
        )
    if step_kind == PlanStepKind.SCREEN_TOP_AXES.value:
        axis_text = "、".join(candidate_axes[:3]) if candidate_axes else dimension_text
        return (
            f"{step_payload['title']}已完成：已对 {axis_text} 做一轮高层级筛查，"
            f"当前结果可用于判断哪条解释轴最值得继续深挖。{result_summary}"
        )
    if step_kind == PlanStepKind.LOCATE_ANOMALOUS_SLICE.value:
        axis_text = "、".join(candidate_axes[:3]) if candidate_axes else dimension_text
        return (
            f"{step_payload['title']}已完成：已围绕 {axis_text} 定位异常切片，"
            f"当前结果可用于收紧 why 问题的重点排查范围。{result_summary}"
        )

    return (
        f"{step_payload['title']}已完成：围绕 {measure_text} 按 {dimension_text} 进行查询"
        f"{filter_text}。{result_summary}"
    )


def build_synthesis_step_summary(
    original_question: str,
    completed_steps: list[dict[str, Any]],
) -> str:
    """把已完成的 query steps 汇总成 synthesis 文本。"""
    query_steps = [step for step in completed_steps if step.get("summary_text")]
    if not query_steps:
        return f"围绕“{original_question}”已生成分析计划，但暂时还没有足够的查询结果用于汇总。"

    lines = [f"围绕“{original_question}”已完成 {len(query_steps)} 个分析步骤："]
    for item in query_steps:
        payload = item.get("step") or {}
        summary_text = item.get("summary_text", "")
        lines.append(f"{payload.get('index', '?')}. {payload.get('title', '步骤')}: {summary_text}")
    lines.append("当前已形成逐步积累的证据链，可继续基于这些结果输出最终洞察。")
    return "\n".join(lines)


def build_followup_history(
    history: Optional[list[dict[str, str]]],
    original_question: str,
    completed_steps: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """把最近完成的分析步骤压缩进后续 follow-up 历史。"""
    base_history = list(history or [])
    if not completed_steps:
        return base_history

    lines = [f"原始问题：{original_question}"]
    for item in completed_steps[-2:]:
        payload = item.get("step") or {}
        summary_text = item.get("summary_text")
        if summary_text:
            lines.append(f"步骤{payload.get('index', '?')} {payload.get('title', '步骤')}：{summary_text}")

    base_history.append({
        "role": "assistant",
        "content": "以下是已完成的分析上下文：\n" + "\n".join(lines),
    })
    return base_history


def hydrate_step_intent_with_evidence(
    step: AnalysisPlanStep,
    evidence_context: EvidenceContext,
    *,
    screening_top_k: Optional[int] = None,
) -> AnalysisPlanStep:
    """用累计 evidence 收紧下一步的执行意图。"""
    if step.step_kind == PlanStepKind.SCREEN_TOP_AXES:
        screened_axes = _dedupe_keep_order([
            *list(_get_screening_axes(evidence_context, limit=screening_top_k)),
            *list(step.candidate_axes),
        ])
        semantic_focus = _dedupe_keep_order([
            *list(step.semantic_focus),
            *screened_axes[:2],
        ])
        return step.model_copy(update={"candidate_axes": screened_axes, "semantic_focus": semantic_focus})

    if step.step_kind == PlanStepKind.LOCATE_ANOMALOUS_SLICE:
        ranked_axes = _dedupe_keep_order([
            *list(_get_screening_axes(evidence_context, limit=screening_top_k)),
            *list(step.candidate_axes),
        ])
        semantic_focus = _dedupe_keep_order([
            *list(step.semantic_focus),
            *ranked_axes[:2],
            *list(evidence_context.anomalous_entities[:2]),
        ])
        return step.model_copy(update={"candidate_axes": ranked_axes, "semantic_focus": semantic_focus})

    if step.step_kind == PlanStepKind.SYNTHESIZE_CAUSE:
        semantic_focus = _dedupe_keep_order([
            *list(step.semantic_focus),
            *list(_get_screening_axes(evidence_context, limit=screening_top_k)[:2]),
            *list(evidence_context.anomalous_entities[:2]),
        ])
        return step.model_copy(update={"semantic_focus": semantic_focus})

    return step


def _dedupe_keep_order(values: list[str]) -> list[str]:
    """按原顺序去重。"""
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value or "").strip()
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


def _coerce_text_list(values: list[Any]) -> list[str]:
    """把混合列表稳定转换成字符串列表。"""
    result: list[str] = []
    for value in values:
        if isinstance(value, dict):
            candidate = value.get("field_name") or value.get("name") or value.get("value")
        else:
            candidate = value
        normalized = str(candidate or "").strip()
        if normalized:
            result.append(normalized)
    return _dedupe_keep_order(result)


def _extract_entity_scope(
    table_data: Optional[dict[str, Any]],
    *,
    limit: int = 5,
) -> list[str]:
    """从结果预览里提取可复用的实体范围。"""
    if not isinstance(table_data, dict):
        return []
    columns = table_data.get("columns") or []
    rows = table_data.get("rows") or []
    if not isinstance(columns, list) or not isinstance(rows, list):
        return []

    column_names = [
        str(column.get("name"))
        for column in columns
        if isinstance(column, dict) and column.get("name")
    ]
    dimension_names = [
        str(column.get("name"))
        for column in columns
        if isinstance(column, dict)
        and column.get("name")
        and (bool(column.get("isDimension")) or not bool(column.get("isMeasure")))
    ]

    values: list[str] = []
    for raw_row in rows[:20]:
        if isinstance(raw_row, dict):
            row = {str(key): value for key, value in raw_row.items()}
        elif isinstance(raw_row, (list, tuple)) and column_names:
            row = {
                name: raw_row[index] if index < len(raw_row) else None
                for index, name in enumerate(column_names)
            }
        else:
            continue

        for name in dimension_names[:2]:
            value = row.get(name)
            if value is None:
                continue
            values.append(str(value))
    return _dedupe_keep_order(values)[:limit]


def _extract_validated_axes(
    step_payload: dict[str, Any],
    semantic_summary: Optional[dict[str, Any]] = None,
) -> list[str]:
    """提取当前 step 已经显式落地的解释轴。"""
    semantic_summary = semantic_summary or {}
    dimensions = semantic_summary.get("dimensions") or []
    semantic_focus = step_payload.get("semanticFocus") or []
    return _dedupe_keep_order([
        *[str(item) for item in dimensions if item],
        *[str(item) for item in semantic_focus if item],
    ])


def resolve_step_validated_axes(
    step_payload: dict[str, Any],
    semantic_summary: Optional[dict[str, Any]] = None,
    *,
    evidence_context_before_step: Optional[EvidenceContext] = None,
    table_data: Optional[dict[str, Any]] = None,
) -> list[str]:
    """决定当前 step 完成后，后续 why 步骤应继承哪些轴。"""
    semantic_axes = _extract_validated_axes(step_payload, semantic_summary)
    candidate_axes = _dedupe_keep_order([
        str(item)
        for item in (step_payload.get("candidateAxes") or [])
        if str(item or "").strip()
    ])
    prior_context = evidence_context_before_step or EvidenceContext(primary_question="")
    prior_axes = list(prior_context.validated_axes)
    step_kind = str(step_payload.get("stepKind") or "").strip()
    ranked_reference_axes = _dedupe_keep_order([
        *_get_latest_ranked_axes(prior_context),
        *candidate_axes,
    ])
    aligned_semantic_axes = _align_axes_to_reference_labels(
        semantic_axes,
        reference_axes=ranked_reference_axes,
    )

    if step_kind == PlanStepKind.RANK_EXPLANATORY_AXES.value:
        return _dedupe_keep_order([*candidate_axes, *aligned_semantic_axes, *prior_axes])
    if step_kind == PlanStepKind.SCREEN_TOP_AXES.value:
        return _reorder_axes_for_screening(
            _dedupe_keep_order([*ranked_reference_axes, *aligned_semantic_axes]),
            semantic_summary=semantic_summary,
            table_data=table_data,
        )
    if step_kind == PlanStepKind.LOCATE_ANOMALOUS_SLICE.value:
        return _dedupe_keep_order([
            *_get_screening_axes(prior_context),
            *candidate_axes,
            *aligned_semantic_axes,
        ])
    if step_kind in {PlanStepKind.SYNTHESIZE_CAUSE.value, PlanStepKind.RESULT_SYNTHESIS.value}:
        return _dedupe_keep_order([*prior_axes, *aligned_semantic_axes])
    return _dedupe_keep_order([*aligned_semantic_axes, *candidate_axes])


def _step_targets_anomaly(step_payload: dict[str, Any]) -> bool:
    """只有显式 metadata 才能驱动 anomalous_entities。"""
    return bool(step_payload.get("targetsAnomaly"))


def _get_latest_ranked_axes(evidence_context: EvidenceContext) -> list[str]:
    """优先读取最近一次解释轴排序的结果。"""
    for artifact in reversed(evidence_context.step_artifacts):
        if artifact.step_kind == PlanStepKind.RANK_EXPLANATORY_AXES and artifact.validated_axes:
            return list(artifact.validated_axes)
    return list(evidence_context.validated_axes)


def _get_latest_screened_axes(evidence_context: EvidenceContext) -> list[str]:
    """优先读取最近一次 screening 的结果。"""
    for artifact in reversed(evidence_context.step_artifacts):
        if artifact.step_kind == PlanStepKind.SCREEN_TOP_AXES and artifact.validated_axes:
            return list(artifact.validated_axes)
    return []


def _get_screening_axes(
    evidence_context: EvidenceContext,
    *,
    limit: Optional[int] = None,
) -> list[str]:
    """返回下一步 why 流程应继续使用的筛查后解释轴。"""
    ranked_axes = _dedupe_axes_by_key(
        _get_latest_screened_axes(evidence_context) or _get_latest_ranked_axes(evidence_context)
    )
    if limit is None:
        return ranked_axes
    return ranked_axes[: max(1, int(limit))]


def _normalize_axis_key(value: Any) -> str:
    """统一轴名称比较口径，兼容空格、下划线和大小写差异。"""
    normalized = str(value or "").strip().casefold()
    if not normalized:
        return ""
    return "".join(char for char in normalized if char.isalnum())


def _align_axes_to_reference_labels(
    axes: list[str],
    *,
    reference_axes: list[str],
) -> list[str]:
    """把语义维度名映射回已有候选轴标签，避免同轴多种写法并存。"""
    reference_by_key = {
        _normalize_axis_key(item): item
        for item in reference_axes
        if _normalize_axis_key(item)
    }
    aligned: list[str] = []
    for axis in axes:
        axis_key = _normalize_axis_key(axis)
        aligned.append(reference_by_key.get(axis_key, axis))
    return _dedupe_keep_order(aligned)


def _dedupe_axes_by_key(axes: list[str]) -> list[str]:
    """按归一化轴名去重，保留最先出现的标签写法。"""
    result: list[str] = []
    seen: set[str] = set()
    for axis in axes:
        axis_key = _normalize_axis_key(axis)
        if not axis_key or axis_key in seen:
            continue
        seen.add(axis_key)
        result.append(str(axis))
    return result


def _extract_semantic_dimension_names(
    semantic_summary: Optional[dict[str, Any]],
) -> list[str]:
    """提取 screening step 真正落地到的语义维度。"""
    if not isinstance(semantic_summary, dict):
        return []
    return _dedupe_keep_order([
        str(item)
        for item in (semantic_summary.get("dimensions") or [])
        if str(item or "").strip()
    ])


def _reorder_axes_for_screening(
    ordered_axes: list[str],
    *,
    semantic_summary: Optional[dict[str, Any]],
    table_data: Optional[dict[str, Any]],
) -> list[str]:
    """把 screening 真实查到的轴提到前面，避免 locate 继续沿用旧排序。"""
    if not ordered_axes:
        return []
    row_count = 0
    if isinstance(table_data, dict):
        row_count = int(table_data.get("rowCount") or len(table_data.get("rows") or []))
    if row_count <= 0:
        return ordered_axes

    semantic_dimensions = _extract_semantic_dimension_names(semantic_summary)
    if not semantic_dimensions:
        return ordered_axes
    dimension_key_order = [
        _normalize_axis_key(item)
        for item in semantic_dimensions
        if _normalize_axis_key(item)
    ]
    if not dimension_key_order:
        return ordered_axes

    dimension_rank = {dimension_key: index for index, dimension_key in enumerate(dimension_key_order)}
    matched_axes = [axis for axis in ordered_axes if _normalize_axis_key(axis) in dimension_rank]
    if not matched_axes:
        return ordered_axes
    matched_axes.sort(key=lambda axis: dimension_rank[_normalize_axis_key(axis)])
    unmatched_axes = [axis for axis in ordered_axes if _normalize_axis_key(axis) not in dimension_rank]
    return matched_axes + unmatched_axes


def _extract_measure_contributions(table_data: Optional[dict[str, Any]]) -> list[float]:
    """从 screening 结果中提取按分组聚合后的 measure 贡献值。"""
    if not isinstance(table_data, dict):
        return []
    columns = table_data.get("columns") or []
    rows = table_data.get("rows") or []
    if not isinstance(columns, list) or not isinstance(rows, list):
        return []

    column_names = [
        str(column.get("name"))
        for column in columns
        if isinstance(column, dict) and column.get("name")
    ]
    measure_names = [
        str(column.get("name"))
        for column in columns
        if isinstance(column, dict) and column.get("name") and bool(column.get("isMeasure"))
    ]
    if not measure_names:
        return []

    contributions: list[float] = []
    for raw_row in rows[:50]:
        if isinstance(raw_row, dict):
            row = {str(key): value for key, value in raw_row.items()}
        elif isinstance(raw_row, (list, tuple)) and column_names:
            row = {
                name: raw_row[index] if index < len(raw_row) else None
                for index, name in enumerate(column_names)
            }
        else:
            continue

        row_total = 0.0
        for measure_name in measure_names[:3]:
            raw_value = row.get(measure_name)
            if raw_value in (None, ""):
                continue
            try:
                row_total += abs(float(raw_value))
            except (TypeError, ValueError):
                continue
        if row_total > 0:
            contributions.append(row_total)
    return contributions


def _estimate_screening_share(table_data: Optional[dict[str, Any]]) -> float:
    """估算 screening 查询里头部分组对异常的解释占比。"""
    contributions = _extract_measure_contributions(table_data)
    if not contributions:
        return 0.0
    total = sum(contributions)
    if total <= 0:
        return 0.0
    top_share = max(contributions) / total
    return min(0.92, max(0.45, top_share))


def _build_axis_scores(
    step_payload: dict[str, Any],
    validated_axes: list[str],
    *,
    evidence_context_before_step: Optional[EvidenceContext] = None,
    semantic_summary: Optional[dict[str, Any]] = None,
    table_data: Optional[dict[str, Any]] = None,
) -> list[AxisEvidenceScore]:
    """根据排序或 screening 结果构造确定性的 axis_scores。"""
    step_kind = str(step_payload.get("stepKind") or "").strip()
    if step_kind not in {PlanStepKind.RANK_EXPLANATORY_AXES.value, PlanStepKind.SCREEN_TOP_AXES.value}:
        return []

    ordered_axes = _dedupe_keep_order([
        *list(validated_axes),
        *list((evidence_context_before_step or EvidenceContext(primary_question="")).validated_axes),
    ])
    if not ordered_axes:
        return []

    if step_kind == PlanStepKind.SCREEN_TOP_AXES.value:
        ordered_axes = _reorder_axes_for_screening(
            ordered_axes,
            semantic_summary=semantic_summary,
            table_data=table_data,
        )

    total_weight = sum(range(1, len(ordered_axes) + 1))
    matched_dimension_keys = {
        _normalize_axis_key(item)
        for item in _extract_semantic_dimension_names(semantic_summary)
        if _normalize_axis_key(item)
    }
    row_count = 0
    if isinstance(table_data, dict):
        row_count = int(table_data.get("rowCount") or len(table_data.get("rows") or []))

    screening_axes = [axis for axis in ordered_axes if _normalize_axis_key(axis) in matched_dimension_keys]
    screening_share = 0.0
    if step_kind == PlanStepKind.SCREEN_TOP_AXES.value and screening_axes and row_count > 0:
        screening_share = _estimate_screening_share(table_data)
        if screening_share <= 0:
            screening_share = 0.65

    reverse_ranks = {axis: len(ordered_axes) - index for index, axis in enumerate(ordered_axes)}
    screened_total_weight = sum(reverse_ranks[axis] for axis in screening_axes) or 1
    retained_axes = [axis for axis in ordered_axes if axis not in screening_axes]
    retained_total_weight = sum(reverse_ranks[axis] for axis in retained_axes) or 1

    scores: list[AxisEvidenceScore] = []
    for index, axis in enumerate(ordered_axes):
        reverse_rank = len(ordered_axes) - index
        explained_share = reverse_rank / total_weight
        confidence = min(0.92, 0.62 + reverse_rank * 0.08)
        reason = "Preserved from rank_explanatory_axes ordered axis screening."

        if step_kind == PlanStepKind.SCREEN_TOP_AXES.value:
            axis_key = _normalize_axis_key(axis)
            if axis_key in matched_dimension_keys and row_count > 0:
                explained_share = screening_share * reverse_rank / screened_total_weight
                confidence = min(0.97, 0.74 + screening_share * 0.2 + reverse_rank * 0.02)
                reason = (
                    "Confirmed by screen_top_axes with live query results; "
                    f"top grouped contribution reached {screening_share:.0%}."
                )
            else:
                explained_share = max(0.0, 1.0 - screening_share) * reverse_rank / retained_total_weight
                confidence = max(0.45, 0.56 + reverse_rank * 0.03 - screening_share * 0.08)
                reason = (
                    "Retained from prior axis ranking; "
                    "not directly confirmed in screen_top_axes."
                )

        scores.append(
            AxisEvidenceScore(
                axis=axis,
                explained_share=round(explained_share, 4),
                confidence=round(confidence, 4),
                reason=reason,
            )
        )
    return scores


def _merge_axis_scores(
    existing_scores: list[AxisEvidenceScore],
    new_scores: list[AxisEvidenceScore],
) -> list[AxisEvidenceScore]:
    """合并 axis_scores，并保持最新证据优先。"""
    if not new_scores:
        return list(existing_scores)
    merged: list[AxisEvidenceScore] = []
    seen: set[str] = set()
    for score in [*new_scores, *existing_scores]:
        axis_key = _normalize_axis_key(score.axis)
        if not axis_key or axis_key in seen:
            continue
        seen.add(axis_key)
        merged.append(score)
    return merged


__all__ = [
    "append_step_artifact",
    "build_evidence_bundle_dict",
    "build_evidence_insight_output",
    "build_followup_history",
    "build_initial_evidence_context",
    "build_query_step_summary",
    "build_step_insight_output",
    "build_synthesis_step_summary",
    "extract_insight_key_findings",
    "get_primary_plan_step",
    "hydrate_step_intent_with_evidence",
    "parse_analysis_plan",
    "resolve_step_validated_axes",
    "serialize_plan_step",
    "summarize_table_data",
]
