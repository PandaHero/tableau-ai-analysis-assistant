# -*- coding: utf-8 -*-
"""Chat router with SSE v2 and interrupt/resume contract."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from analytics_assistant.src.api.dependencies import (
    get_settings_repository,
    get_tableau_username,
)
from analytics_assistant.src.api.models.chat import ChatRequest, ChatResumeRequest
from analytics_assistant.src.api.utils.sse import format_sse_event, format_sse_heartbeat
from analytics_assistant.src.infra.business_storage import SettingsRepository
from analytics_assistant.src.infra.config import get_config
from analytics_assistant.src.orchestration.workflow.history import get_history_manager
from analytics_assistant.src.orchestration.root_graph import RootGraphRunner
from analytics_assistant.src.orchestration.workflow.runtime import (
    get_interrupt_record,
    mark_interrupt_resolved,
    save_pending_interrupt,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])

_DEFAULT_SSE_KEEPALIVE = 120
_THINKING_MODES = {"off", "summary", "debug"}
_PUBLIC_ERROR_CODES = {
    "ARTIFACT_NOT_READY",
    "ARTIFACT_WRITE_ERROR",
    "CLIENT_VALIDATION_ERROR",
    "DATASOURCE_RESOLUTION_ERROR",
    "EMPTY_RESULT",
    "FIELD_RETRIEVAL_ERROR",
    "INSIGHT_GENERATION_ERROR",
    "INTERRUPT_ALREADY_RESOLVED",
    "INTERRUPT_NOT_FOUND",
    "INTERNAL_ERROR",
    "METADATA_NOT_READY",
    "NORMALIZATION_ERROR",
    "PERSIST_ERROR",
    "QUERY_EXECUTION_ERROR",
    "QUERY_PLAN_ERROR",
    "REPLAN_EXHAUSTED",
    "RESUME_VALIDATION_ERROR",
    "SEMANTIC_PARSE_ERROR",
    "SEMANTIC_VALIDATION_ERROR",
    "SESSION_NOT_FOUND",
    "TABLEAU_AUTH_ERROR",
    "TABLEAU_TIMEOUT",
    "TENANT_AUTH_ERROR",
    "WORKSPACE_INIT_ERROR",
}
_PUBLIC_ERROR_CODE_ALIASES = {code.lower(): code for code in _PUBLIC_ERROR_CODES}
_NODE_ERROR_CODE_TO_PUBLIC_ERROR_CODE = {
    "planner_query_step_limit_exceeded": "QUERY_PLAN_ERROR",
    "planner_runtime_budget_exceeded": "QUERY_EXECUTION_ERROR",
    "planner_step_limit_exceeded": "QUERY_PLAN_ERROR",
}


def _sse_headers() -> dict[str, str]:
    return {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }


def _get_sse_keepalive() -> int:
    try:
        config = get_config()
        return config.get("api", {}).get("timeout", {}).get(
            "sse_keepalive",
            _DEFAULT_SSE_KEEPALIVE,
        )
    except Exception:
        return _DEFAULT_SSE_KEEPALIVE


def _estimate_history_tokens(
    history_manager: object,
    history: list[dict[str, str]],
) -> int:
    check_tokens = getattr(history_manager, "check_history_tokens", None)
    if callable(check_tokens):
        try:
            result = check_tokens(history)
            if isinstance(result, tuple) and result:
                return int(result[0])
            if isinstance(result, list) and result:
                return int(result[0])
            if isinstance(result, int):
                return result
        except Exception:
            pass

    estimate_tokens = getattr(history_manager, "estimate_history_tokens", None)
    if callable(estimate_tokens):
        try:
            return int(estimate_tokens(history))
        except Exception:
            pass

    return 0


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sse_v2_envelope(
    *,
    event_type: str,
    data: dict[str, Any],
    request_id: str,
    session_id: Optional[str],
    thread_id: str,
    run_id: str,
) -> dict[str, Any]:
    return {
        "type": event_type,
        "request_id": request_id,
        "session_id": session_id or "",
        "thread_id": thread_id,
        "run_id": run_id,
        "timestamp": _utc_now_iso(),
        "data": data,
    }


def _error_event(
    *,
    request_id: str,
    session_id: str,
    thread_id: str,
    run_id: str,
    error_code: str,
    message: str,
    retryable: bool = False,
    node_error_code: Optional[str] = None,
) -> dict[str, Any]:
    data = {
        "error_code": error_code,
        "message": message,
        "retryable": retryable,
    }
    if node_error_code:
        data["node_error_code"] = node_error_code
    return _sse_v2_envelope(
        event_type="error",
        data=data,
        request_id=request_id,
        session_id=session_id,
        thread_id=thread_id,
        run_id=run_id,
    )


def _normalize_error_code(raw_code: Any) -> tuple[str, Optional[str]]:
    """把内部节点错误码映射成稳定 API 错误码，同时保留内部错误码。"""
    normalized = str(raw_code or "").strip()
    if not normalized:
        return "INTERNAL_ERROR", None

    public_code = _PUBLIC_ERROR_CODE_ALIASES.get(normalized.lower())
    if public_code:
        return public_code, None

    mapped_public_code = _NODE_ERROR_CODE_TO_PUBLIC_ERROR_CODE.get(normalized.lower())
    if mapped_public_code:
        return mapped_public_code, normalized

    return "INTERNAL_ERROR", normalized


def _build_workflow_context_payload(
    *,
    request: ChatRequest,
    truncated_history: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "question": request.messages[-1].content,
        "history": truncated_history,
        "datasource_name": request.datasource_name,
        "datasource_luid": request.datasource_luid,
        "project_name": request.project_name,
        "language": request.language,
        "analysis_depth": request.analysis_depth,
        "replan_mode": request.replan_mode,
        "thinking_mode": request.thinking_mode,
        "feature_flags": dict(request.feature_flags or {}),
    }


def _resolve_thinking_mode(
    *,
    requested_mode: Any,
    settings_repo: Optional[SettingsRepository],
    tableau_username: str,
) -> str:
    """解析思考过程展示模式。

    优先级：
    1. 请求显式传入 thinking_mode
    2. 用户设置 show_thinking_process
    3. 默认 summary
    """
    normalized_requested_mode = str(requested_mode or "").strip().lower()
    if normalized_requested_mode in _THINKING_MODES:
        return normalized_requested_mode

    if settings_repo is not None:
        try:
            settings = settings_repo.find_by_id(tableau_username)
        except Exception:
            settings = None
        if isinstance(settings, dict):
            return "summary" if bool(settings.get("show_thinking_process", True)) else "off"

    return "summary"


def _build_display_payload(
    *,
    channel: str,
    title: Optional[str] = None,
    message: Optional[str] = None,
    summary: Optional[str] = None,
    tone: str = "info",
    mode: Optional[str] = None,
) -> dict[str, Any]:
    """构建前端直接可消费的展示元数据。"""
    display = {
        "channel": channel,
        "tone": tone,
    }
    if title:
        display["title"] = title
    if message:
        display["message"] = message
    if summary:
        display["summary"] = summary
    if mode:
        display["mode"] = mode
    return display


def _format_semantic_summary_text(summary: Any) -> str:
    """将 parse_result 的结构化摘要压缩成一段用户可见说明。"""
    if not isinstance(summary, dict):
        return "已完成语义解析"

    parts: list[str] = []
    measures = [str(item) for item in (summary.get("measures") or []) if item]
    dimensions = [str(item) for item in (summary.get("dimensions") or []) if item]
    filters = [str(item) for item in (summary.get("filters") or []) if item]
    if measures:
        parts.append("指标: " + "、".join(measures[:3]))
    if dimensions:
        parts.append("维度: " + "、".join(dimensions[:3]))
    if filters:
        parts.append("筛选: " + "、".join(filters[:3]))
    if not parts:
        restated_question = str(summary.get("restated_question") or "").strip()
        if restated_question:
            return f"已完成语义解析: {restated_question}"
        return "已完成语义解析"
    return "；".join(parts)


def _build_stage_reasoning_summary(*, title: str, status: str) -> str:
    """将节点阶段状态压缩为简短的思考摘要。"""
    if status == "running":
        return f"正在{title}"
    if status == "completed":
        return f"已完成{title}"
    return title


def _resolve_followup_question(
    *,
    resume_payload: dict[str, Any],
    interrupt_payload: dict[str, Any],
) -> Optional[str]:
    direct = str(
        resume_payload.get("selected_question")
        or resume_payload.get("selected_candidate_question")
        or resume_payload.get("question")
        or ""
    ).strip()
    if direct:
        return direct

    selected_id = str(
        resume_payload.get("selected_question_id")
        or resume_payload.get("selected_candidate_id")
        or ""
    ).strip()
    if not selected_id:
        return None

    candidates = interrupt_payload.get("candidates") or []
    if not isinstance(candidates, list):
        return None
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        cid = str(candidate.get("id") or "").strip()
        if cid and cid == selected_id:
            question = str(candidate.get("question") or "").strip()
            return question or None
    return None


def _complete_event(
    *,
    request_id: str,
    session_id: str,
    thread_id: str,
    run_id: str,
    data: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    return _sse_v2_envelope(
        event_type="complete",
        data=data or {"status": "ok"},
        request_id=request_id,
        session_id=session_id,
        thread_id=thread_id,
        run_id=run_id,
    )


class ResumeValidationError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "CLIENT_VALIDATION_ERROR",
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _normalize_history(raw_history: Any) -> list[dict[str, str]]:
    if not isinstance(raw_history, list):
        return []

    normalized: list[dict[str, str]] = []
    for item in raw_history:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip()
        content = str(item.get("content") or "").strip()
        if role not in {"user", "assistant", "system"} or not content:
            continue
        normalized.append({
            "role": role,
            "content": content,
        })
    return normalized


def _append_history_message(
    history: list[dict[str, str]],
    *,
    role: str,
    content: Any,
) -> list[dict[str, str]]:
    normalized_content = str(content or "").strip()
    if not normalized_content:
        return list(history)
    return [
        *list(history),
        {
            "role": role,
            "content": normalized_content,
        },
    ]


def _append_interrupt_turn(
    *,
    history: list[dict[str, str]],
    interrupt_payload: dict[str, Any],
    user_message: str,
) -> list[dict[str, str]]:
    updated = list(history)
    assistant_message = str(interrupt_payload.get("message") or "").strip()
    if assistant_message:
        updated = _append_history_message(
            updated,
            role="assistant",
            content=assistant_message,
        )
    return _append_history_message(updated, role="user", content=user_message)


def _normalize_locale(value: Any) -> str:
    locale = str(value or "zh").strip().lower()
    if locale in {"zh", "en"}:
        return locale
    return "zh"


def _normalize_analysis_depth(value: Any) -> str:
    analysis_depth = str(value or "detailed").strip().lower()
    if analysis_depth in {"detailed", "comprehensive"}:
        return analysis_depth
    return "detailed"


def _normalize_replan_mode(value: Any) -> str:
    replan_mode = str(value or "user_select").strip().lower()
    if replan_mode in {"user_select", "auto_continue", "stop"}:
        return replan_mode
    return "user_select"


def _resolve_datasource_choice(
    *,
    resume_payload: dict[str, Any],
    interrupt_payload: dict[str, Any],
) -> dict[str, Optional[str]]:
    selection_type = str(resume_payload.get("selection_type") or "").strip()
    if selection_type and selection_type != "datasource":
        raise ResumeValidationError("selection_type must be datasource")

    datasource_luid = str(resume_payload.get("datasource_luid") or "").strip()
    if not datasource_luid:
        raise ResumeValidationError("missing datasource_luid in resume_payload")

    selected_choice: dict[str, Any] | None = None
    raw_choices = interrupt_payload.get("choices") or []
    if isinstance(raw_choices, list):
        for choice in raw_choices:
            if not isinstance(choice, dict):
                continue
            candidate_luid = str(choice.get("datasource_luid") or "").strip()
            if candidate_luid and candidate_luid == datasource_luid:
                selected_choice = choice
                break
        if raw_choices and selected_choice is None:
            raise ResumeValidationError("datasource_luid is not in interrupt choices")

    datasource_name = str(
        resume_payload.get("datasource_name")
        or (selected_choice or {}).get("name")
        or ""
    ).strip() or None
    project_name = str(
        resume_payload.get("project_name")
        or (selected_choice or {}).get("project_name")
        or (selected_choice or {}).get("project")
        or ""
    ).strip() or None
    return {
        "datasource_luid": datasource_luid,
        "datasource_name": datasource_name,
        "project_name": project_name,
    }


def _resolve_missing_slot(
    *,
    resume_payload: dict[str, Any],
    interrupt_payload: dict[str, Any],
) -> str:
    selection_type = str(resume_payload.get("selection_type") or "").strip()
    if selection_type and selection_type != "slot_fill":
        raise ResumeValidationError("selection_type must be slot_fill")

    expected_slot = str(interrupt_payload.get("slot_name") or "").strip()
    slot_name = str(resume_payload.get("slot_name") or expected_slot or "").strip()
    if not slot_name:
        raise ResumeValidationError("missing slot_name in resume_payload")
    if expected_slot and slot_name != expected_slot:
        raise ResumeValidationError("slot_name does not match interrupt payload")

    value = str(resume_payload.get("value") or "").strip()
    if not value:
        raise ResumeValidationError("missing slot value in resume_payload")
    return f"{slot_name}: {value}"


def _resolve_missing_slot_value(
    *,
    resume_payload: dict[str, Any],
    interrupt_payload: dict[str, Any],
) -> str:
    selection_type = str(resume_payload.get("selection_type") or "").strip()
    if selection_type and selection_type != "slot_fill":
        raise ResumeValidationError("selection_type must be slot_fill")

    expected_slot = str(interrupt_payload.get("slot_name") or "").strip()
    slot_name = str(resume_payload.get("slot_name") or expected_slot or "").strip()
    if not slot_name:
        raise ResumeValidationError("missing slot_name in resume_payload")
    if expected_slot and slot_name != expected_slot:
        raise ResumeValidationError("slot_name does not match interrupt payload")

    value = str(resume_payload.get("value") or "").strip()
    if not value:
        raise ResumeValidationError("missing slot value in resume_payload")
    return value


def _resolve_value_confirmation(
    *,
    resume_payload: dict[str, Any],
    interrupt_payload: dict[str, Any],
) -> str:
    selection_type = str(resume_payload.get("selection_type") or "").strip()
    if selection_type and selection_type != "value_confirm":
        raise ResumeValidationError("selection_type must be value_confirm")

    expected_field = str(interrupt_payload.get("field") or "").strip()
    field = str(resume_payload.get("field") or expected_field or "").strip()
    if not field:
        raise ResumeValidationError("missing field in resume_payload")
    if expected_field and field != expected_field:
        raise ResumeValidationError("field does not match interrupt payload")

    value = str(resume_payload.get("value") or "").strip()
    if not value:
        raise ResumeValidationError("missing value in resume_payload")
    return f"{field}: {value}"


def _resolve_value_confirmation_value(
    *,
    resume_payload: dict[str, Any],
    interrupt_payload: dict[str, Any],
) -> str:
    selection_type = str(resume_payload.get("selection_type") or "").strip()
    if selection_type and selection_type != "value_confirm":
        raise ResumeValidationError("selection_type must be value_confirm")

    expected_field = str(interrupt_payload.get("field") or "").strip()
    field = str(resume_payload.get("field") or expected_field or "").strip()
    if not field:
        raise ResumeValidationError("missing field in resume_payload")
    if expected_field and field != expected_field:
        raise ResumeValidationError("field does not match interrupt payload")

    value = str(resume_payload.get("value") or "").strip()
    if not value:
        raise ResumeValidationError("missing value in resume_payload")
    return value


def _resolve_high_risk_confirmation(
    *,
    resume_payload: dict[str, Any],
) -> bool:
    selection_type = str(resume_payload.get("selection_type") or "").strip()
    if selection_type and selection_type != "high_risk_query":
        raise ResumeValidationError("selection_type must be high_risk_query")

    confirm = resume_payload.get("confirm")
    if isinstance(confirm, bool):
        return confirm

    normalized = str(confirm or "").strip().lower()
    if normalized in {"true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n"}:
        return False
    raise ResumeValidationError("missing boolean confirm in resume_payload")


def _build_resume_base(workflow_context: dict[str, Any]) -> dict[str, Any]:
    history = _normalize_history(workflow_context.get("history"))
    return {
        "history": history,
        "question": str(workflow_context.get("question") or "").strip(),
        "datasource_name": str(workflow_context.get("datasource_name") or "").strip() or None,
        "datasource_luid": str(workflow_context.get("datasource_luid") or "").strip() or None,
        "project_name": str(workflow_context.get("project_name") or "").strip() or None,
        "language": _normalize_locale(workflow_context.get("language")),
        "analysis_depth": _normalize_analysis_depth(workflow_context.get("analysis_depth")),
        "replan_mode": _normalize_replan_mode(workflow_context.get("replan_mode")),
        "feature_flags": dict(workflow_context.get("feature_flags") or {}),
        "workflow_context": dict(workflow_context),
    }


def _resolve_resume_execution(
    *,
    interrupt_type: str,
    resume_payload: dict[str, Any],
    interrupt_payload: dict[str, Any],
    workflow_context: dict[str, Any],
) -> dict[str, Any]:
    resume_base = _build_resume_base(workflow_context)
    history = list(resume_base["history"])
    base_question = str(resume_base["question"] or "").strip()
    datasource_name = resume_base["datasource_name"]
    datasource_luid = resume_base["datasource_luid"]
    project_name = resume_base["project_name"]
    language = str(resume_base["language"] or "zh")
    analysis_depth = str(resume_base["analysis_depth"] or "detailed")
    replan_mode = str(resume_base["replan_mode"] or "user_select")
    resumed_context = dict(resume_base["workflow_context"])

    if interrupt_type == "datasource_disambiguation":
        selection = _resolve_datasource_choice(
            resume_payload=resume_payload,
            interrupt_payload=interrupt_payload,
        )
        datasource_luid = selection["datasource_luid"] or datasource_luid
        datasource_name = selection["datasource_name"] or datasource_name
        project_name = selection["project_name"] or project_name
        if not datasource_name and not datasource_luid:
            raise ResumeValidationError(
                "interrupt context is no longer valid",
                code="INTERRUPT_NOT_FOUND",
            )
        if not base_question:
            raise ResumeValidationError(
                "interrupt context is no longer valid",
                code="INTERRUPT_NOT_FOUND",
            )

        resumed_context.update({
            "question": base_question,
            "history": history,
            "datasource_name": datasource_name,
            "datasource_luid": datasource_luid,
            "project_name": project_name,
            "language": language,
            "analysis_depth": analysis_depth,
            "replan_mode": replan_mode,
        })
        return {
            "mode": "execute",
            "question": base_question,
            "datasource_name": datasource_name,
            "datasource_luid": datasource_luid,
            "project_name": project_name,
            "history": history,
            "language": language,
            "analysis_depth": analysis_depth,
            "replan_mode": replan_mode,
            "selected_candidate_question": None,
            "workflow_context": resumed_context,
        }

    if not datasource_name and not datasource_luid:
        raise ResumeValidationError(
            "interrupt context is no longer valid",
            code="INTERRUPT_NOT_FOUND",
        )

    if interrupt_type == "followup_select":
        selected_question = _resolve_followup_question(
            resume_payload=resume_payload,
            interrupt_payload=interrupt_payload,
        )
        if not selected_question:
            raise ResumeValidationError(
                "missing selected_question or selected_question_id in resume_payload"
            )
        resumed_context.update({
            "question": selected_question,
            "history": history,
            "datasource_name": datasource_name,
            "datasource_luid": datasource_luid,
            "project_name": project_name,
            "language": language,
            "analysis_depth": analysis_depth,
            "replan_mode": replan_mode,
        })
        return {
            "mode": "execute",
            "question": base_question or selected_question,
            "datasource_name": datasource_name,
            "datasource_luid": datasource_luid,
            "project_name": project_name,
            "history": history,
            "language": language,
            "analysis_depth": analysis_depth,
            "replan_mode": replan_mode,
            "selected_candidate_question": selected_question,
            "workflow_context": resumed_context,
        }

    if not base_question:
        raise ResumeValidationError(
            "interrupt context is no longer valid",
            code="INTERRUPT_NOT_FOUND",
        )

    if interrupt_type == "missing_slot":
        user_message = _resolve_missing_slot(
            resume_payload=resume_payload,
            interrupt_payload=interrupt_payload,
        )
        updated_history = _append_interrupt_turn(
            history=history,
            interrupt_payload=interrupt_payload,
            user_message=user_message,
        )
        resumed_context.update({
            "question": base_question,
            "history": updated_history,
            "datasource_name": datasource_name,
            "datasource_luid": datasource_luid,
            "project_name": project_name,
            "language": language,
            "analysis_depth": analysis_depth,
            "replan_mode": replan_mode,
        })
        return {
            "mode": "execute",
            "question": base_question,
            "datasource_name": datasource_name,
            "datasource_luid": datasource_luid,
            "project_name": project_name,
            "history": updated_history,
            "language": language,
            "analysis_depth": analysis_depth,
            "replan_mode": replan_mode,
            "selected_candidate_question": None,
            "workflow_context": resumed_context,
        }

    if interrupt_type == "value_confirm":
        user_message = _resolve_value_confirmation(
            resume_payload=resume_payload,
            interrupt_payload=interrupt_payload,
        )
        updated_history = _append_interrupt_turn(
            history=history,
            interrupt_payload=interrupt_payload,
            user_message=user_message,
        )
        resumed_context.update({
            "question": base_question,
            "history": updated_history,
            "datasource_name": datasource_name,
            "datasource_luid": datasource_luid,
            "project_name": project_name,
            "language": language,
            "analysis_depth": analysis_depth,
            "replan_mode": replan_mode,
        })
        return {
            "mode": "execute",
            "question": base_question,
            "datasource_name": datasource_name,
            "datasource_luid": datasource_luid,
            "project_name": project_name,
            "history": updated_history,
            "language": language,
            "analysis_depth": analysis_depth,
            "replan_mode": replan_mode,
            "selected_candidate_question": None,
            "workflow_context": resumed_context,
        }

    if interrupt_type == "high_risk_query_confirm":
        confirmed = _resolve_high_risk_confirmation(resume_payload=resume_payload)
        if not confirmed:
            resumed_context.update({
                "question": base_question,
                "history": history,
                "datasource_name": datasource_name,
                "datasource_luid": datasource_luid,
                "project_name": project_name,
                "language": language,
                "analysis_depth": analysis_depth,
                "replan_mode": replan_mode,
            })
            return {
                "mode": "complete",
                "complete_data": {
                    "status": "cancelled",
                    "reason": "user_declined_high_risk_query",
                },
                "workflow_context": resumed_context,
            }

        updated_history = _append_interrupt_turn(
            history=history,
            interrupt_payload=interrupt_payload,
            user_message="确认继续执行高风险查询",
        )
        resumed_context.update({
            "question": base_question,
            "history": updated_history,
            "datasource_name": datasource_name,
            "datasource_luid": datasource_luid,
            "project_name": project_name,
            "language": language,
            "analysis_depth": analysis_depth,
            "replan_mode": replan_mode,
        })
        return {
            "mode": "execute",
            "question": base_question,
            "datasource_name": datasource_name,
            "datasource_luid": datasource_luid,
            "project_name": project_name,
            "history": updated_history,
            "language": language,
            "analysis_depth": analysis_depth,
            "replan_mode": replan_mode,
            "selected_candidate_question": None,
            "workflow_context": resumed_context,
        }

    raise ResumeValidationError(
        f"unsupported interrupt_type: {interrupt_type}",
        code="CLIENT_VALIDATION_ERROR",
    )


def _build_status_payload(
    raw_event: dict[str, Any],
    *,
    thinking_mode: str = "off",
) -> dict[str, Any]:
    """把工作流中的状态类事件规范化为 SSE `status` 负载。"""
    raw_type = str(raw_event.get("type") or "").strip()
    if raw_type == "thinking":
        stage = str(raw_event.get("stage") or "thinking")
        title = str(raw_event.get("name") or raw_event.get("status") or "过程更新")
        status = str(raw_event.get("status") or "running")
        reasoning_summary = _build_stage_reasoning_summary(
            title=title,
            status=status,
        )
        return {
            "stage": stage,
            "message": title,
            "status": status,
            "display": _build_display_payload(
                channel="activity_timeline",
                title=title,
                message=reasoning_summary,
                tone="info",
                mode="thinking_summary" if thinking_mode != "off" else "progress",
            ),
            "reasoning_summary": reasoning_summary if thinking_mode != "off" else None,
        }
    if raw_type == "heartbeat":
        return {
            "stage": "keepalive",
            "message": "heartbeat",
            "display": _build_display_payload(
                channel="system",
                message="heartbeat",
                tone="info",
            ),
        }
    raise ValueError(f"unsupported status event type: {raw_type or '<empty>'}")


def _require_interrupt_type(payload: dict[str, Any]) -> str:
    interrupt_type = str(payload.get("interrupt_type") or "").strip()
    if not interrupt_type:
        raise ValueError("interrupt event missing explicit interrupt_type")
    return interrupt_type


def _normalize_workflow_event_to_sse_v2(
    raw_event: Any,
    *,
    request_id: str,
    session_id: Optional[str],
    thread_id: str,
    run_id: str,
    thinking_mode: str = "off",
) -> Optional[dict[str, Any]]:
    """把内部 workflow 事件投影成稳定的 SSE v2 事件。"""
    if not isinstance(raw_event, dict):
        raise ValueError("workflow event must be a dict")

    payload = dict(raw_event)
    raw_type = str(payload.pop("type", "")).strip()
    payload.pop("requestId", None)
    payload.pop("request_id", None)

    if raw_type == "token":
        delta = str(payload.get("content") or "")
        return _sse_v2_envelope(
            event_type="answer_delta",
            data={
                "delta": delta,
                "display": _build_display_payload(
                    channel="main_answer",
                    mode="answer",
                ),
            },
            request_id=request_id,
            session_id=session_id,
            thread_id=thread_id,
            run_id=run_id,
        )

    if raw_type == "thinking_token":
        # 原始 thinking token 只在 debug 模式下透出，避免普通界面直接展示模型原始推理碎片。
        if thinking_mode != "debug":
            return None
        return _sse_v2_envelope(
            event_type="reasoning_delta",
            data={
                "delta": str(payload.get("content") or ""),
                "display": _build_display_payload(
                    channel="activity_timeline",
                    title="深度思考",
                    message="原始 reasoning token",
                    tone="info",
                    mode="debug",
                ),
            },
            request_id=request_id,
            session_id=session_id,
            thread_id=thread_id,
            run_id=run_id,
        )

    if raw_type in {"thinking", "heartbeat"}:
        return _sse_v2_envelope(
            event_type="status",
            data=_build_status_payload(
                {"type": raw_type, **payload},
                thinking_mode=thinking_mode,
            ),
            request_id=request_id,
            session_id=session_id,
            thread_id=thread_id,
            run_id=run_id,
        )

    if raw_type == "parse_result":
        summary_text = _format_semantic_summary_text(payload.get("summary"))
        return _sse_v2_envelope(
            event_type="parse_result",
            data={
                **payload,
                "display": _build_display_payload(
                    channel="activity_timeline",
                    title="解析完成",
                    message="已完成语义解析",
                    summary=summary_text,
                    tone="info",
                    mode="thinking_summary" if thinking_mode != "off" else "progress",
                ),
                "reasoning_summary": summary_text if thinking_mode != "off" else None,
            },
            request_id=request_id,
            session_id=session_id,
            thread_id=thread_id,
            run_id=run_id,
        )

    if raw_type == "interrupt":
        interrupt_type = _require_interrupt_type(payload)
        interrupt_id = str(payload.get("interrupt_id") or f"int_{uuid4().hex[:8]}")
        if isinstance(payload.get("payload"), dict):
            interrupt_payload = dict(payload.get("payload") or {})
        else:
            interrupt_payload = {
                key: value
                for key, value in payload.items()
                if key not in {"interrupt_id", "interrupt_type"}
            }
        return _sse_v2_envelope(
            event_type="interrupt",
            data={
                "interrupt_id": interrupt_id,
                "interrupt_type": interrupt_type,
                "payload": interrupt_payload,
                "display": _build_display_payload(
                    channel="decision_card",
                    title=str(interrupt_payload.get("title") or "需要你确认"),
                    message=str(
                        interrupt_payload.get("message") or "当前流程需要你的确认后继续"
                    ),
                    summary=str(interrupt_payload.get("summary") or ""),
                    tone=(
                        "warning"
                        if interrupt_type == "high_risk_query_confirm"
                        else "info"
                    ),
                ),
            },
            request_id=request_id,
            session_id=session_id,
            thread_id=thread_id,
            run_id=run_id,
        )

    if raw_type == "data":
        table_data = payload.get("tableData") or {}
        row_count = payload.get("row_count")
        if row_count is None and isinstance(table_data, dict):
            row_count = table_data.get("rowCount")
        is_truncated = bool(payload.get("truncated", False))
        return _sse_v2_envelope(
            event_type="table_result",
            data={
                "row_count": row_count,
                "truncated": is_truncated,
                "result_manifest_ref": payload.get("result_manifest_ref"),
                "profiles_ref": payload.get("profiles_ref"),
                "chunks_ref": payload.get("chunks_ref"),
                "table_data": table_data,
                "display": _build_display_payload(
                    channel="result_card",
                    title="查询结果",
                    message="已完成查询",
                    summary=(
                        "结果较大，当前展示的是预览和摘要"
                        if is_truncated
                        else "结果已准备好"
                    ),
                    tone="success",
                ),
            },
            request_id=request_id,
            session_id=session_id,
            thread_id=thread_id,
            run_id=run_id,
        )

    if raw_type == "insight":
        return _sse_v2_envelope(
            event_type="insight",
            data={
                **payload,
                "display": _build_display_payload(
                    channel="result_card",
                    title="关键发现",
                    message="已生成洞察结论",
                    summary=str(payload.get("summary") or ""),
                    tone="success",
                ),
            },
            request_id=request_id,
            session_id=session_id,
            thread_id=thread_id,
            run_id=run_id,
        )

    if raw_type == "replan":
        decision_message = str(
            payload.get("reason")
            or payload.get("message")
            or payload.get("newQuestion")
            or payload.get("selectedQuestion")
            or "已生成后续分析建议"
        )
        return _sse_v2_envelope(
            event_type="replan",
            data={
                "source_type": raw_type,
                **payload,
                "display": _build_display_payload(
                    channel="activity_timeline",
                    title="后续分析",
                    message=decision_message,
                    summary=str(payload.get("newQuestion") or ""),
                    tone="info",
                    mode="thinking_summary" if thinking_mode != "off" else "progress",
                ),
                "reasoning_summary": (
                    decision_message if thinking_mode != "off" else None
                ),
            },
            request_id=request_id,
            session_id=session_id,
            thread_id=thread_id,
            run_id=run_id,
        )

    if raw_type == "complete":
        complete_payload = payload or {"status": "ok"}
        return _sse_v2_envelope(
            event_type="complete",
            data={
                **complete_payload,
                "display": _build_display_payload(
                    channel="system",
                    message=str(complete_payload.get("status") or "ok"),
                    tone="success",
                ),
            },
            request_id=request_id,
            session_id=session_id,
            thread_id=thread_id,
            run_id=run_id,
        )

    if raw_type == "error":
        message = str(payload.get("message") or payload.get("error") or "unknown error")
        error_code, node_error_code = _normalize_error_code(
            payload.get("error_code") or "INTERNAL_ERROR"
        )
        retryable = bool(payload.get("retryable", False))
        extra = {
            key: value for key, value in payload.items()
            if key not in {"message", "error", "error_code", "retryable"}
        }
        if node_error_code:
            extra["node_error_code"] = node_error_code
        return _sse_v2_envelope(
            event_type="error",
            data={
                "error_code": error_code,
                "message": message,
                "retryable": retryable,
                "display": _build_display_payload(
                    channel="error_banner",
                    title="分析失败",
                    message=message,
                    tone="error",
                ),
                **extra,
            },
            request_id=request_id,
            session_id=session_id,
            thread_id=thread_id,
            run_id=run_id,
        )

    raise ValueError(f"unsupported workflow event type: {raw_type or '<empty>'}")


def _resolve_session_id(session_id: Optional[str]) -> str:
    normalized = str(session_id or "").strip()
    if normalized:
        return normalized
    return f"sess_{uuid4().hex[:12]}"


@router.post("/stream")
async def chat_stream(
    http_request: Request,
    request: ChatRequest,
    tableau_username: str = Depends(get_tableau_username),
    settings_repo: SettingsRepository = Depends(get_settings_repository),
) -> StreamingResponse:
    request_id = str(getattr(http_request.state, "request_id", "") or uuid4().hex)
    run_id = f"run_{uuid4().hex[:12]}"
    session_id = _resolve_session_id(request.session_id)
    thread_id = session_id
    datasource_ref = request.datasource_luid or request.datasource_name or ""
    logger.info(
        "receive chat stream request: request_id=%s, session_id=%s, user=%s, datasource=%s, messages=%s, language=%s",
        request_id,
        session_id,
        tableau_username,
        datasource_ref,
        len(request.messages),
        request.language,
    )

    try:
        thinking_mode = _resolve_thinking_mode(
            requested_mode=request.thinking_mode,
            settings_repo=settings_repo,
            tableau_username=tableau_username,
        )
        history_manager = get_history_manager()
        history = [{"role": msg.role, "content": msg.content} for msg in request.messages]
        truncated_history = history_manager.truncate_history(history)
        workflow_context_payload = _build_workflow_context_payload(
            request=request,
            truncated_history=truncated_history,
        )
        workflow_context_payload["thinking_mode"] = thinking_mode

        original_tokens = _estimate_history_tokens(history_manager, history)
        truncated_tokens = _estimate_history_tokens(history_manager, truncated_history)
        logger.info(
            "history truncated: %s -> %s messages, %s -> %s tokens, request_id=%s",
            len(history),
            len(truncated_history),
            original_tokens,
            truncated_tokens,
            request_id,
        )

        runner = RootGraphRunner(tableau_username, request_id=request_id or None)
        keepalive_seconds = _get_sse_keepalive()

        async def event_generator() -> AsyncIterator[str]:
            try:
                async for event in _stream_with_heartbeat(
                    runner.execute_stream(
                        question=request.messages[-1].content,
                        datasource_name=request.datasource_name,
                        datasource_luid=request.datasource_luid,
                        project_name=request.project_name,
                        history=truncated_history,
                        language=request.language,
                        analysis_depth=request.analysis_depth,
                        replan_mode=request.replan_mode,
                        selected_candidate_question=request.selected_candidate_question,
                        feature_flags=request.feature_flags,
                        session_id=session_id,
                    ),
                    keepalive_seconds=keepalive_seconds,
                    request_id=request_id,
                    session_id=session_id,
                    thread_id=thread_id,
                    run_id=run_id,
                    interrupt_persistence={
                        "session_id": session_id,
                        "tableau_username": tableau_username,
                        "workflow_context": workflow_context_payload,
                    },
                    thinking_mode=thinking_mode,
                ):
                    yield event
            except Exception as exc:
                logger.exception(
                    "stream generation failed: request_id=%s, error=%s",
                    request_id,
                    exc,
                )
                yield format_sse_event(_error_event(
                    request_id=request_id,
                    session_id=session_id,
                    thread_id=thread_id,
                    run_id=run_id,
                    error_code="INTERNAL_ERROR",
                    message="workflow execution failed",
                    retryable=True,
                ))

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers=_sse_headers(),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("chat request failed: request_id=%s, error=%s", request_id, exc)
        raise HTTPException(status_code=500, detail="internal server error") from exc


@router.post("/resume")
async def chat_resume(
    http_request: Request,
    request: ChatResumeRequest,
    tableau_username: str = Depends(get_tableau_username),
    settings_repo: SettingsRepository = Depends(get_settings_repository),
) -> StreamingResponse:
    request_id = str(getattr(http_request.state, "request_id", "") or uuid4().hex)
    run_id = f"run_{uuid4().hex[:12]}"
    thread_id = request.session_id
    thinking_mode = _resolve_thinking_mode(
        requested_mode=request.thinking_mode,
        settings_repo=settings_repo,
        tableau_username=tableau_username,
    )

    def _error_response(code: str, message: str, retryable: bool = False) -> StreamingResponse:
        public_code, node_error_code = _normalize_error_code(code)

        async def event_generator() -> AsyncIterator[str]:
            yield format_sse_event(_error_event(
                request_id=request_id,
                session_id=request.session_id,
                thread_id=thread_id,
                run_id=run_id,
                error_code=public_code,
                message=message,
                retryable=retryable,
                node_error_code=node_error_code,
            ))

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers=_sse_headers(),
        )

    interrupt_record = get_interrupt_record(request.session_id, request.interrupt_id)
    if not interrupt_record:
        return _error_response("INTERRUPT_NOT_FOUND", "interrupt not found or expired")

    record_username = str(interrupt_record.get("tableau_username") or "")
    if record_username and record_username != tableau_username:
        return _error_response("TENANT_AUTH_ERROR", "cannot resume this interrupt")

    if str(interrupt_record.get("status") or "") == "resolved":
        return _error_response(
            "INTERRUPT_ALREADY_RESOLVED",
            "interrupt already resolved",
        )

    interrupt_type = str(interrupt_record.get("interrupt_type") or "").strip()
    interrupt_payload = dict(interrupt_record.get("payload") or {})
    workflow_context = dict(interrupt_record.get("workflow_context") or {})

    native_resume_execution: Optional[dict[str, Any]] = None
    resume_execution: Optional[dict[str, Any]] = None
    resume_strategy = str(interrupt_payload.get("resume_strategy") or "").strip()

    if interrupt_type == "datasource_disambiguation":
        if resume_strategy != "root_graph_native":
            return _error_response(
                "RESUME_VALIDATION_ERROR",
                "datasource_disambiguation must use root_graph_native resume",
            )
        try:
            selection = _resolve_datasource_choice(
                resume_payload=request.resume_payload,
                interrupt_payload=interrupt_payload,
            )
        except ResumeValidationError as exc:
            return _error_response(exc.code, exc.message)

        native_resume_execution = {
            **_build_resume_base(workflow_context),
            "datasource_name": selection["datasource_name"],
            "datasource_luid": selection["datasource_luid"],
            "project_name": selection["project_name"],
            "resume_value": {
                "datasource_luid": selection["datasource_luid"],
                "datasource_name": selection["datasource_name"],
                "project_name": selection["project_name"],
            },
            "resume_strategy": "root_graph_native",
        }
        native_resume_execution["workflow_context"] = {
            **dict(native_resume_execution.get("workflow_context") or {}),
            "question": native_resume_execution.get("question"),
            "history": list(native_resume_execution.get("history") or []),
            "datasource_name": native_resume_execution.get("datasource_name"),
            "datasource_luid": native_resume_execution.get("datasource_luid"),
            "project_name": native_resume_execution.get("project_name"),
            "language": native_resume_execution.get("language"),
            "analysis_depth": native_resume_execution.get("analysis_depth"),
            "replan_mode": native_resume_execution.get("replan_mode"),
        }
        if not native_resume_execution.get("question"):
            return _error_response(
                "RESUME_VALIDATION_ERROR",
                "missing question in workflow_context",
            )
        if (
            not native_resume_execution.get("datasource_name")
            and not native_resume_execution.get("datasource_luid")
        ):
            return _error_response(
                "RESUME_VALIDATION_ERROR",
                "missing datasource in workflow_context",
            )
    elif interrupt_type == "value_confirm":
        if resume_strategy != "root_graph_native":
            return _error_response(
                "RESUME_VALIDATION_ERROR",
                "value_confirm must use root_graph_native resume",
            )
        try:
            native_resume_execution = {
                **_build_resume_base(workflow_context),
                "resume_value": _resolve_value_confirmation_value(
                    resume_payload=request.resume_payload,
                    interrupt_payload=interrupt_payload,
                ),
                "resume_strategy": "root_graph_native",
            }
        except ResumeValidationError as exc:
            return _error_response(exc.code, exc.message)
        if not native_resume_execution.get("question"):
            return _error_response("RESUME_VALIDATION_ERROR", "missing question in workflow_context")
        if not native_resume_execution.get("datasource_name") and not native_resume_execution.get("datasource_luid"):
            return _error_response(
                "RESUME_VALIDATION_ERROR",
                "missing datasource in workflow_context",
            )
    elif interrupt_type == "high_risk_query_confirm":
        try:
            confirmed = _resolve_high_risk_confirmation(
                resume_payload=request.resume_payload,
            )
        except ResumeValidationError as exc:
            return _error_response(exc.code, exc.message)
        if not confirmed:
            resume_execution = {
                "mode": "complete",
                "complete_data": {
                    "status": "cancelled",
                    "reason": "user_declined_high_risk_query",
                },
                "workflow_context": dict(workflow_context),
            }
        else:
            if resume_strategy != "root_graph_native":
                return _error_response(
                    "RESUME_VALIDATION_ERROR",
                    "high_risk_query_confirm must use root_graph_native resume",
                )
            native_resume_execution = {
                **_build_resume_base(workflow_context),
                "resume_value": True,
                "resume_strategy": "root_graph_native",
            }
            if not native_resume_execution.get("question"):
                return _error_response(
                    "RESUME_VALIDATION_ERROR",
                    "missing question in workflow_context",
                )
            if (
                not native_resume_execution.get("datasource_name")
                and not native_resume_execution.get("datasource_luid")
            ):
                return _error_response(
                    "RESUME_VALIDATION_ERROR",
                    "missing datasource in workflow_context",
                )
    elif interrupt_type == "followup_select":
        if resume_strategy != "root_graph_native":
            return _error_response(
                "RESUME_VALIDATION_ERROR",
                "followup_select must use root_graph_native resume",
            )
        try:
            selected_question = _resolve_followup_question(
                resume_payload=request.resume_payload,
                interrupt_payload=interrupt_payload,
            )
        except ResumeValidationError as exc:
            return _error_response(exc.code, exc.message)
        if not selected_question:
            return _error_response(
                "RESUME_VALIDATION_ERROR",
                "missing selected_question or selected_question_id in resume_payload",
            )

        native_resume_execution = {
            **_build_resume_base(workflow_context),
            "question": selected_question,
            "resume_value": selected_question,
            "resume_strategy": "root_graph_native",
        }
        native_resume_execution["workflow_context"] = {
            **dict(native_resume_execution.get("workflow_context") or {}),
            "question": selected_question,
            "history": list(native_resume_execution.get("history") or []),
            "datasource_name": native_resume_execution.get("datasource_name"),
            "datasource_luid": native_resume_execution.get("datasource_luid"),
            "project_name": native_resume_execution.get("project_name"),
            "language": native_resume_execution.get("language"),
            "analysis_depth": native_resume_execution.get("analysis_depth"),
            "replan_mode": native_resume_execution.get("replan_mode"),
        }
        if not native_resume_execution.get("datasource_name") and not native_resume_execution.get("datasource_luid"):
            return _error_response(
                "RESUME_VALIDATION_ERROR",
                "missing datasource in workflow_context",
            )
    elif interrupt_type == "missing_slot":
        if resume_strategy != "root_graph_native":
            return _error_response(
                "RESUME_VALIDATION_ERROR",
                "missing_slot must use root_graph_native resume",
            )
        try:
            native_resume_execution = {
                **_build_resume_base(workflow_context),
                "resume_value": _resolve_missing_slot_value(
                    resume_payload=request.resume_payload,
                    interrupt_payload=interrupt_payload,
                ),
                "resume_strategy": "root_graph_native",
            }
        except ResumeValidationError as exc:
            return _error_response(exc.code, exc.message)
        if not native_resume_execution.get("question"):
            return _error_response(
                "RESUME_VALIDATION_ERROR",
                "missing question in workflow_context",
            )
        if not native_resume_execution.get("datasource_name") and not native_resume_execution.get("datasource_luid"):
            return _error_response(
                "RESUME_VALIDATION_ERROR",
                "missing datasource in workflow_context",
            )

    if native_resume_execution is None and resume_execution is None:
        try:
            resume_execution = _resolve_resume_execution(
                interrupt_type=interrupt_type,
                resume_payload=request.resume_payload,
                interrupt_payload=interrupt_payload,
                workflow_context=workflow_context,
            )
        except ResumeValidationError as exc:
            return _error_response(exc.code, exc.message)
    elif native_resume_execution is not None:
        resume_execution = native_resume_execution

    resolved = mark_interrupt_resolved(
        session_id=request.session_id,
        interrupt_id=request.interrupt_id,
        resume_payload=request.resume_payload,
        request_id=request_id,
        run_id=run_id,
    )
    if resolved is None:
        return _error_response("INTERRUPT_NOT_FOUND", "interrupt not found or expired")

    if resume_execution.get("mode") == "complete":
        async def event_generator() -> AsyncIterator[str]:
            yield format_sse_event(_complete_event(
                request_id=request_id,
                session_id=request.session_id,
                thread_id=thread_id,
                run_id=run_id,
                data=dict(resume_execution.get("complete_data") or {"status": "ok"}),
            ))

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers=_sse_headers(),
        )

    runner = RootGraphRunner(tableau_username, request_id=request_id or None)
    keepalive_seconds = _get_sse_keepalive()

    async def event_generator() -> AsyncIterator[str]:
        try:
            if "resume_value" in resume_execution:
                stream = runner.resume_stream(
                    question=str(resume_execution.get("question") or ""),
                    resume_value=resume_execution.get("resume_value"),
                    datasource_name=resume_execution.get("datasource_name"),
                    datasource_luid=resume_execution.get("datasource_luid"),
                    project_name=resume_execution.get("project_name"),
                    history=list(resume_execution.get("history") or []),
                    language=str(resume_execution.get("language") or "zh"),
                    analysis_depth=str(
                        resume_execution.get("analysis_depth") or "detailed"
                    ),
                    replan_mode=str(
                        resume_execution.get("replan_mode") or "user_select"
                    ),
                    session_id=request.session_id,
                    resume_strategy=str(
                        resume_execution.get("resume_strategy") or "root_graph_native"
                    ),
                )
            else:
                stream = runner.execute_stream(
                    question=str(resume_execution.get("question") or ""),
                    datasource_name=resume_execution.get("datasource_name"),
                    datasource_luid=resume_execution.get("datasource_luid"),
                    project_name=resume_execution.get("project_name"),
                    history=list(resume_execution.get("history") or []),
                    language=str(resume_execution.get("language") or "zh"),
                    analysis_depth=str(
                        resume_execution.get("analysis_depth") or "detailed"
                    ),
                    replan_mode=str(
                        resume_execution.get("replan_mode") or "user_select"
                    ),
                    selected_candidate_question=resume_execution.get(
                        "selected_candidate_question"
                    ),
                    feature_flags=dict(resume_execution.get("feature_flags") or {}),
                    session_id=request.session_id,
                )

            async for event in _stream_with_heartbeat(
                stream,
                keepalive_seconds=keepalive_seconds,
                request_id=request_id,
                session_id=request.session_id,
                thread_id=thread_id,
                run_id=run_id,
                interrupt_persistence={
                    "session_id": request.session_id,
                    "tableau_username": tableau_username,
                    "workflow_context": {
                        **dict(resume_execution.get("workflow_context") or {}),
                        "thinking_mode": thinking_mode,
                    },
                },
                thinking_mode=thinking_mode,
            ):
                yield event
        except Exception as exc:
            logger.exception(
                "resume stream failed: request_id=%s, session_id=%s, interrupt_id=%s, error=%s",
                request_id,
                request.session_id,
                request.interrupt_id,
                exc,
            )
            yield format_sse_event(_error_event(
                request_id=request_id,
                session_id=request.session_id,
                thread_id=thread_id,
                run_id=run_id,
                error_code="INTERNAL_ERROR",
                message="resume execution failed",
                retryable=True,
            ))

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers=_sse_headers(),
    )


async def _stream_with_heartbeat(
    event_stream: AsyncIterator,
    keepalive_seconds: int = _DEFAULT_SSE_KEEPALIVE,
    request_id: str = "",
    session_id: Optional[str] = None,
    thread_id: str = "",
    run_id: str = "",
    interrupt_persistence: Optional[dict[str, Any]] = None,
    thinking_mode: str = "off",
) -> AsyncIterator[str]:
    aiter = event_stream.__aiter__()
    while True:
        try:
            event = await asyncio.wait_for(
                aiter.__anext__(),
                timeout=float(keepalive_seconds),
            )
            normalized = _normalize_workflow_event_to_sse_v2(
                event,
                request_id=request_id,
                session_id=session_id,
                thread_id=thread_id,
                run_id=run_id,
                thinking_mode=thinking_mode,
            )
            if normalized is None:
                continue
            if interrupt_persistence and normalized.get("type") == "interrupt":
                persist_session_id = str(interrupt_persistence.get("session_id") or "").strip()
                interrupt_data = normalized.get("data") or {}
                interrupt_id = str(interrupt_data.get("interrupt_id") or "").strip()
                if persist_session_id and interrupt_id:
                    try:
                        interrupt_type = str(
                            interrupt_data.get("interrupt_type") or ""
                        ).strip()
                        if not interrupt_type:
                            raise ValueError(
                                "persisted interrupt missing explicit interrupt_type"
                            )
                        save_pending_interrupt(
                            session_id=persist_session_id,
                            interrupt_id=interrupt_id,
                            tableau_username=str(
                                interrupt_persistence.get("tableau_username") or ""
                            ),
                            thread_id=thread_id,
                            run_id=run_id,
                            request_id=request_id,
                            interrupt_type=interrupt_type,
                            payload=dict(interrupt_data.get("payload") or {}),
                            workflow_context=dict(
                                interrupt_persistence.get("workflow_context") or {}
                            ),
                        )
                    except Exception as exc:
                        logger.warning(
                            "persist interrupt failed: session_id=%s, interrupt_id=%s, error=%s",
                            persist_session_id,
                            interrupt_id,
                            exc,
                        )
            yield format_sse_event(normalized)
        except asyncio.TimeoutError:
            yield format_sse_heartbeat()
        except StopAsyncIteration:
            break
