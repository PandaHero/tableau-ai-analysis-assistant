# -*- coding: utf-8 -*-
"""answer_graph 的确定性服务。"""

from typing import Any, Optional

from analytics_assistant.src.infra.config import get_config


_DEFAULT_MAX_REPLAN_ROUNDS = 10


def _get_max_replan_rounds() -> int:
    """读取重规划轮数上限，保证投影层有确定性硬限制。"""
    config = get_config()
    raw_config = getattr(config, "config", config)
    agents_config = raw_config.get("agents", {})
    replanner_config = agents_config.get("replanner", {})
    value = replanner_config.get("max_replan_rounds", _DEFAULT_MAX_REPLAN_ROUNDS)
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return _DEFAULT_MAX_REPLAN_ROUNDS


def build_result_evidence_bundle(
    *,
    source: str,
    question: str,
    semantic_raw: Optional[dict[str, Any]],
    result_manifest_ref: Optional[str],
    data_profile_dict: Optional[dict[str, Any]],
    query_id: Optional[str] = None,
) -> dict[str, Any]:
    """为单查询结果构造正式 evidence bundle。

    这里不再把结果伪装成 replanner 专用的轻量 data profile，而是显式保留：
    - 来源与问题
    - 结果画像
    - 当前语义摘要
    - 可供 answer/replan 共用的稳定输入结构
    """

    semantic_raw = dict(semantic_raw or {})
    result_profile = _normalize_result_profile(data_profile_dict)
    return {
        "bundle_version": "1.0",
        "source": str(source or "single_query").strip() or "single_query",
        "question": str(question or "").strip(),
        "query_id": str(query_id or "").strip() or None,
        "result_manifest_ref": str(result_manifest_ref or "").strip() or None,
        "semantic_summary": {
            "restated_question": str(
                semantic_raw.get("restated_question") or ""
            ).strip(),
            "intent": str(semantic_raw.get("intent") or "").strip(),
        },
        "result_profile": result_profile,
        "step_count": 0,
        "step_artifacts": [],
        "validated_axes": [],
        "axis_scores": [],
        "anomalous_entities": [],
        "key_entities": [],
        "open_questions": [],
    }


def build_bundle_insight_output(
    evidence_bundle_dict: Optional[dict[str, Any]],
) -> dict[str, Any]:
    """基于 evidence bundle 生成最终 insight 输出。

    这条路径用于 planner/why 的最终答案阶段。此时 answer_graph 已经拿到了
    完整证据包，不应该再要求外层额外预构建 `prebuilt_insight_output_dict`。
    """
    bundle = dict(evidence_bundle_dict or {})
    latest_summary = str(bundle.get("latest_summary") or "").strip()
    question = str(bundle.get("question") or "").strip()
    step_artifacts = bundle.get("step_artifacts") or []
    validated_axes = bundle.get("validated_axes") or []
    axis_scores = bundle.get("axis_scores") or []
    anomalous_entities = bundle.get("anomalous_entities") or []

    summary = latest_summary or (
        f"围绕“{question}”已完成 {len(step_artifacts)} 个分析步骤。"
        if question and step_artifacts
        else "已完成多步证据汇总。"
    )
    findings: list[dict[str, Any]] = []
    if validated_axes:
        findings.append({
            "finding_type": "comparison",
            "analysis_level": "diagnostic",
            "description": "当前已验证的解释轴包括："
            + "、".join(str(item) for item in validated_axes[:3]),
            "supporting_data": {
                "validated_axes": list(validated_axes[:5]),
            },
            "confidence": 0.72,
        })
    if anomalous_entities:
        findings.append({
            "finding_type": "comparison",
            "analysis_level": "diagnostic",
            "description": "当前已定位的异常对象包括："
            + "、".join(str(item) for item in anomalous_entities[:3]),
            "supporting_data": {
                "anomalous_entities": list(anomalous_entities[:5]),
            },
            "confidence": 0.74,
        })
    if axis_scores:
        findings.append({
            "finding_type": "comparison",
            "analysis_level": "diagnostic",
            "description": "当前解释轴优先级为："
            + "、".join(
                f"{str(item.get('axis') or '')}({float(item.get('explained_share') or 0.0):.0%})"
                for item in axis_scores[:3]
                if str(item.get("axis") or "").strip()
            ),
            "supporting_data": {
                "axis_scores": [
                    dict(item) for item in axis_scores[:5] if isinstance(item, dict)
                ],
            },
            "confidence": 0.78,
        })
    for artifact in step_artifacts[:4]:
        if not isinstance(artifact, dict):
            continue
        table_summary = str(artifact.get("table_summary") or "").strip()
        if not table_summary:
            continue
        findings.append({
            "finding_type": "comparison",
            "analysis_level": "diagnostic",
            "description": table_summary,
            "supporting_data": {
                "step_id": artifact.get("step_id"),
                "title": artifact.get("title"),
                "step_kind": artifact.get("step_kind"),
                "entity_scope": artifact.get("entity_scope") or [],
                "validated_axes": artifact.get("validated_axes") or [],
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
            "supporting_data": {
                "step_count": int(bundle.get("step_count") or len(step_artifacts)),
            },
            "confidence": 0.65,
        })

    overall_confidence = min(0.9, 0.55 + 0.05 * len(findings))
    return {
        "summary": summary,
        "overall_confidence": overall_confidence,
        "findings": findings,
    }


def normalize_candidate_questions(
    *,
    primary_question: Optional[str],
    suggested_questions: Optional[list[str]],
    candidate_questions: Optional[list[Any]],
) -> list[dict[str, Any]]:
    """把 replanner 输出的候选问题归一化为统一结构。"""
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _coerce_priority(value: Any, fallback: int) -> int:
        try:
            return max(1, min(int(value), 10))
        except (TypeError, ValueError):
            return fallback

    def _coerce_gain(value: Any, fallback: float = 0.5) -> float:
        try:
            return max(0.0, min(float(value), 1.0))
        except (TypeError, ValueError):
            return fallback

    def _append_candidate(
        question: Any,
        *,
        question_type: str = "followup",
        priority: int,
        expected_info_gain: float = 0.5,
        rationale: str = "",
        estimated_mode: str = "single_query",
    ) -> None:
        normalized_question = str(question or "").strip()
        if not normalized_question:
            return
        key = normalized_question.lower()
        if key in seen:
            return
        seen.add(key)
        normalized.append({
            "question": normalized_question,
            "questionType": str(question_type or "followup").strip() or "followup",
            "priority": priority,
            "expectedInfoGain": expected_info_gain,
            "rationale": str(rationale or "").strip(),
            "estimatedMode": str(estimated_mode or "single_query").strip() or "single_query",
        })

    for index, raw in enumerate(candidate_questions or [], start=1):
        if hasattr(raw, "model_dump"):
            raw = raw.model_dump()
        if isinstance(raw, dict):
            _append_candidate(
                raw.get("question"),
                question_type=str(raw.get("question_type") or "followup"),
                priority=_coerce_priority(raw.get("priority"), index),
                expected_info_gain=_coerce_gain(raw.get("expected_info_gain")),
                rationale=str(raw.get("rationale") or ""),
                estimated_mode=str(raw.get("estimated_mode") or "single_query"),
            )
        elif isinstance(raw, str):
            _append_candidate(raw, priority=index)

    if primary_question:
        _append_candidate(
            primary_question,
            question_type="primary_followup",
            priority=1,
        )

    for index, question in enumerate(
        suggested_questions or [],
        start=2 if primary_question else max(1, len(normalized) + 1),
    ):
        _append_candidate(question, priority=index)

    normalized.sort(key=lambda item: (item["priority"], item["question"].lower()))
    return normalized


def _normalize_result_profile(
    data_profile_dict: Optional[dict[str, Any]],
) -> dict[str, Any]:
    """把 data profile 规整成 evidence bundle 内部的稳定结构。"""
    raw_profile = dict(data_profile_dict or {})
    columns_profile = raw_profile.get("columns_profile") or []
    if not isinstance(columns_profile, list):
        columns_profile = []
    return {
        "row_count": _coerce_int(raw_profile.get("row_count")),
        "column_count": _coerce_int(raw_profile.get("column_count")),
        "columns_profile": [dict(item) for item in columns_profile if isinstance(item, dict)],
    }


def _coerce_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0



def serialize_insight_payload(insight_output_dict: dict[str, Any]) -> dict[str, Any]:
    """把 InsightOutput 转成稳定的 SSE 载荷。"""
    findings_payload: list[dict[str, Any]] = []
    for raw_finding in insight_output_dict.get("findings") or []:
        if not isinstance(raw_finding, dict):
            continue
        findings_payload.append({
            "findingType": raw_finding.get("finding_type", "comparison"),
            "analysisLevel": raw_finding.get("analysis_level", "descriptive"),
            "description": raw_finding.get("description", ""),
            "confidence": raw_finding.get("confidence", 0.0),
            "supportingData": raw_finding.get("supporting_data") or {},
        })

    return {
        "summary": str(insight_output_dict.get("summary") or ""),
        "overallConfidence": float(insight_output_dict.get("overall_confidence") or 0.0),
        "findings": findings_payload,
    }



def build_replan_followup_history(
    history: Optional[list[dict[str, str]]],
    *,
    previous_question: str,
    round_summary: str,
    replan_reason: str,
    next_question: str,
) -> list[dict[str, str]]:
    """为 auto-continue 构造下一轮 follow-up 的上下文。"""
    base_history = list(history or [])
    lines = [f"上一轮问题：{previous_question}"]
    if round_summary.strip():
        lines.append(f"上一轮结论：{round_summary.strip()}")
    if replan_reason.strip():
        lines.append(f"继续分析原因：{replan_reason.strip()}")
    lines.append(f"当前继续分析的问题：{next_question}")
    base_history.append({
        "role": "assistant",
        "content": "以下是上一轮分析上下文：\n" + "\n".join(lines),
    })
    return base_history



def build_replan_projection(
    *,
    replan_decision: Any,
    source: str,
    replan_mode: str,
    current_question: str,
    replan_history: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """把 replanner 输出投影成 answer 阶段可直接消费的结构。"""

    def _get(value: Any, key: str, default: Any = None) -> Any:
        if isinstance(value, dict):
            return value.get(key, default)
        return getattr(value, key, default)

    candidate_questions = normalize_candidate_questions(
        primary_question=_get(replan_decision, "new_question"),
        suggested_questions=_get(replan_decision, "suggested_questions", None),
        candidate_questions=_get(replan_decision, "candidate_questions", None),
    )
    max_replan_rounds = _get_max_replan_rounds()
    capped_by_max_rounds = len(replan_history or []) >= max_replan_rounds
    replan_reason = str(_get(replan_decision, "reason", "") or "")
    should_replan = bool(_get(replan_decision, "should_replan", False))
    if capped_by_max_rounds:
        candidate_questions = []
        replan_reason = f"已达到最大重规划轮数上限（{max_replan_rounds} 轮）"
        should_replan = False

    questions = [item["question"] for item in candidate_questions]

    selected_question: Optional[str] = None
    action = "stop"
    if capped_by_max_rounds:
        action = "stop"
    elif replan_mode == "user_select":
        action = "await_user_select" if candidate_questions else "stop"
    elif replan_mode == "auto_continue":
        if should_replan:
            selected_question = _select_auto_continue_question(
                current_question=current_question,
                candidate_questions=candidate_questions,
                replan_history=replan_history,
            )
        action = "auto_continue" if selected_question else "stop"

    interrupt_payload: Optional[dict[str, Any]] = None
    if action == "await_user_select" and candidate_questions:
        interrupt_payload = {
            "message": "请选择下一步分析方向。",
            "reason": replan_reason,
            "source": source,
            "candidates": candidate_questions,
        }

    return {
        "candidate_questions": candidate_questions,
        "questions": questions,
        "action": action,
        "selected_question": selected_question,
        "replan_event": {
            "type": "replan",
            "source": source,
            "mode": replan_mode,
            "action": action,
            "shouldReplan": should_replan,
            "reason": replan_reason,
            "replanRoundLimitReached": capped_by_max_rounds,
            "newQuestion": _get(replan_decision, "new_question"),
            "selectedQuestion": selected_question,
            "questions": questions,
            "candidateQuestions": candidate_questions,
        },
        "interrupt_payload": interrupt_payload,
    }



def _select_auto_continue_question(
    *,
    current_question: str,
    candidate_questions: list[dict[str, Any]],
    replan_history: Optional[list[dict[str, Any]]] = None,
) -> Optional[str]:
    """选择 auto-continue 下一轮问题，避免重复已分析路径。"""
    seen_questions = {str(current_question or "").strip().lower()}
    for decision in replan_history or []:
        for candidate in normalize_candidate_questions(
            primary_question=decision.get("new_question"),
            suggested_questions=decision.get("suggested_questions"),
            candidate_questions=decision.get("candidate_questions"),
        ):
            seen_questions.add(candidate["question"].lower())

    for candidate in candidate_questions:
        normalized = str(candidate.get("question") or "").strip()
        if normalized and normalized.lower() not in seen_questions:
            return normalized
    return None


__all__ = [
    "build_result_evidence_bundle",
    "build_replan_followup_history",
    "build_replan_projection",
    "normalize_candidate_questions",
    "serialize_insight_payload",
]
