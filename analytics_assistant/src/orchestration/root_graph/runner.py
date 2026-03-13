from __future__ import annotations
import logging
from datetime import datetime
from typing import Any, AsyncIterator, Awaitable, Callable, Optional, TypedDict

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from analytics_assistant.src.agents.semantic_parser.graph import (
    compile_semantic_parser_graph,
)
from analytics_assistant.src.agents.semantic_parser.schemas.planner import (
    AnalysisPlan,
)
from analytics_assistant.src.orchestration.answer_graph import (
    AnswerGraphRunner,
    build_result_evidence_bundle,
    build_replan_followup_history,
    invoke_insight_agent,
    invoke_replanner_agent,
    serialize_insight_payload,
)
from analytics_assistant.src.orchestration.context_graph import ContextGraphRunner
from analytics_assistant.src.orchestration.query_graph import (
    QueryGraphRunner,
    build_high_risk_interrupt_payload,
    execute_semantic_query,
)
from analytics_assistant.src.orchestration.semantic_graph import SemanticGraphRunner
from analytics_assistant.src.orchestration.semantic_graph.service import (
    build_semantic_summary,
)
from analytics_assistant.src.orchestration.workflow.planner_support import (
    parse_analysis_plan,
)
from analytics_assistant.src.orchestration.workflow.semantic_guard import (
    resolve_compiler_semantic_input,
)
from analytics_assistant.src.orchestration.workflow.callbacks import (
    get_processing_stage,
    get_stage_display_name,
)
from analytics_assistant.src.orchestration.workflow.checkpoint import (
    get_root_graph_checkpointer,
    get_semantic_parser_checkpointer,
)
from analytics_assistant.src.orchestration.workflow.context import (
    PreparedContextSnapshot,
    WorkflowContext,
)
from analytics_assistant.src.platform.tableau.adapter import TableauAdapter
from analytics_assistant.src.platform.tableau.auth import get_tableau_auth_async
from analytics_assistant.src.platform.tableau.client import VizQLClient

from .feature_flags import resolve_root_graph_feature_flags
from .planner_runtime import execute_planner_round
from .schemas import (
    ArtifactState,
    ConversationState,
    DatasourceState,
    RequestState,
    RootGraphRequest,
    RunState,
    TenantState,
)

logger = logging.getLogger(__name__)

_ROOT_NATIVE_INTERRUPT_TYPES = {
    "datasource_disambiguation",
    "followup_select",
    "high_risk_query_confirm",
}
_ROOT_SEMANTIC_INTERRUPT_TYPES = {
    "missing_slot",
    "value_confirm",
}


class RootGraphState(TypedDict, total=False):
    """Minimal runtime state for the root graph transition layer."""

    request_id: str
    session_id: str
    question: str
    active_question: str
    history: list[dict[str, str]]
    replan_history: list[dict[str, Any]]
    datasource_name: Optional[str]
    datasource_luid: Optional[str]
    project_name: Optional[str]
    language: str
    analysis_depth: str
    replan_mode: str
    feature_flags: dict[str, bool]
    prepared_context_snapshot: Optional[dict[str, Any]]
    semantic_parse_result: Optional[dict[str, Any]]
    semantic_resume_value: Any
    pending_interrupt_type: Optional[str]
    pending_interrupt_payload: Optional[dict[str, Any]]
    root_resume_value: Any
    approved_high_risk_signatures: list[str]
    tenant_domain: Optional[str]
    tenant_site: Optional[str]
    tenant_auth_method: Optional[str]
    artifact_freshness_report: dict[str, dict[str, Any]]
    artifact_refresh_request: Optional[dict[str, Any]]
    artifact_refresh_scheduled: bool
    degrade_flags: list[str]
    degrade_details: list[dict[str, Any]]
    memory_invalidation_report: dict[str, Any]
    candidate_fields_ref: Optional[str]
    candidate_values_ref: Optional[str]
    fewshot_examples_ref: Optional[str]
    retrieval_trace_ref: Optional[str]
    memory_write_refs: list[str]
    planner_state: Optional[dict[str, Any]]
    resume_target: Optional[str]
    semantic_summary: Any
    semantic_confidence: Optional[float]
    query_status: Optional[str]
    row_count: Optional[int]
    truncated: Optional[bool]
    result_manifest_ref: Optional[str]
    answer_summary: Optional[str]
    followup_candidates: list[dict[str, Any]]
    continue_with_question: Optional[str]
    complete_payload: Optional[dict[str, Any]]


class RootGraphRunner:
    """Minimal root_graph runner with root-owned native interrupt handling."""

    def __init__(
        self,
        tableau_username: str,
        request_id: Optional[str] = None,
        context_graph_runner: Optional[ContextGraphRunner] = None,
        semantic_graph_runner: Optional[SemanticGraphRunner] = None,
        context_resolver: Optional[
            Callable[[RootGraphState], Awaitable[dict[str, Any]]]
        ] = None,
        auth_getter: Optional[Callable[[], Awaitable[Any]]] = None,
    ) -> None:
        self._tableau_username = tableau_username
        self._request_id = request_id
        self._auth_getter = auth_getter or get_tableau_auth_async
        self._context_graph_runner = context_graph_runner or ContextGraphRunner(
            tableau_username=tableau_username,
            request_id=request_id,
        )
        self._semantic_graph_runner = semantic_graph_runner or SemanticGraphRunner(
            graph_compiler=compile_semantic_parser_graph,
            checkpointer_getter=get_semantic_parser_checkpointer,
        )
        # 查询阶段统一委托给 query_graph，避免 root_graph 与 planner 各自维护一套
        # 高风险闸门和查询执行分支。
        self._query_graph_runner = QueryGraphRunner(
            risk_evaluator=build_high_risk_interrupt_payload,
            query_executor=execute_semantic_query,
            request_id=request_id,
        )
        self._answer_graph_runner = AnswerGraphRunner(
            invoke_insight_agent=invoke_insight_agent,
            invoke_replanner_agent=invoke_replanner_agent,
            request_id=request_id,
        )
        self._uses_default_context_resolver = context_resolver is None
        self._context_resolver = context_resolver or self._default_context_resolver
        self._compiled_graph: Any | None = None

    def build_request(
        self,
        *,
        latest_user_message: str,
        recent_messages: Optional[list[dict[str, str]]] = None,
        datasource_luid: Optional[str] = None,
        datasource_name: Optional[str] = None,
        project_name: Optional[str] = None,
        locale: str = "zh",
        analysis_depth: str = "detailed",
        replan_mode: str = "user_select",
        selected_candidate_question: Optional[str] = None,
        feature_flags: Optional[dict[str, bool]] = None,
        session_id: Optional[str] = None,
    ) -> RootGraphRequest:
        return RootGraphRequest(
            request_id=self._request_id or "",
            session_id=session_id or "",
            user_id=self._tableau_username,
            latest_user_message=latest_user_message,
            recent_messages=list(recent_messages or []),
            datasource_luid=datasource_luid,
            datasource_name=datasource_name,
            project_name=project_name,
            locale=locale,
            analysis_depth=analysis_depth,
            replan_mode=replan_mode,
            selected_candidate_question=selected_candidate_question,
            feature_flags=dict(feature_flags or {}),
        )

    def build_run_state(self, request: RootGraphRequest) -> RunState:
        return RunState(
            request=RequestState(
                request_id=request.request_id,
                session_id=request.session_id,
                thread_id=request.thread_id or request.session_id,
                locale=request.locale,
                feature_flags=dict(request.feature_flags),
            ),
            tenant=TenantState(user_id=request.user_id),
            conversation=ConversationState(
                latest_user_message=request.latest_user_message,
            ),
            datasource=DatasourceState(
                datasource_luid=request.datasource_luid,
                datasource_name=request.datasource_name,
                project_name=request.project_name,
            ),
            artifacts=ArtifactState(),
        )

    def _build_initial_state(
        self,
        *,
        question: str,
        datasource_name: Optional[str],
        datasource_luid: Optional[str],
        project_name: Optional[str],
        history: Optional[list[dict[str, str]]],
        language: str,
        analysis_depth: str,
        replan_mode: str,
        selected_candidate_question: Optional[str],
        feature_flags: Optional[dict[str, bool]],
        session_id: Optional[str],
    ) -> RootGraphState:
        active_question = str(selected_candidate_question or question or "").strip()
        normalized_session_id = str(session_id or "").strip()
        return {
            "request_id": self._request_id or "",
            "session_id": normalized_session_id,
            "question": active_question,
            "active_question": active_question,
            "history": list(history or []),
            "replan_history": [],
            "datasource_name": datasource_name,
            "datasource_luid": datasource_luid,
            "project_name": project_name,
            "language": language,
            "analysis_depth": analysis_depth,
            "replan_mode": replan_mode,
            "feature_flags": resolve_root_graph_feature_flags(
                tableau_username=self._tableau_username,
                session_id=normalized_session_id,
                request_overrides=feature_flags,
            ),
            "semantic_parse_result": None,
            "semantic_resume_value": None,
            "pending_interrupt_type": None,
            "pending_interrupt_payload": None,
            "root_resume_value": None,
            "approved_high_risk_signatures": [],
            "tenant_domain": None,
            "tenant_site": None,
            "tenant_auth_method": None,
            "artifact_freshness_report": {},
            "artifact_refresh_request": None,
            "artifact_refresh_scheduled": False,
            "degrade_flags": [],
            "degrade_details": [],
            "memory_invalidation_report": {},
            "candidate_fields_ref": None,
            "candidate_values_ref": None,
            "fewshot_examples_ref": None,
            "retrieval_trace_ref": None,
            "memory_write_refs": [],
            "planner_state": None,
            "resume_target": None,
            "continue_with_question": None,
            **self._empty_round_projection(),
        }

    def _empty_round_projection(self) -> dict[str, Any]:
        """Root-owned round summary used by later graph splits.

        The goal is to let root_graph retain stable query/answer state instead of
        acting as a pure event relay. These fields are intentionally lightweight:
        enough to drive resume/follow-up decisions, but not large enough to store
        full table payloads in checkpoint state.
        """
        return {
            "semantic_summary": None,
            "semantic_confidence": None,
            "query_status": None,
            "row_count": None,
            "truncated": None,
            "result_manifest_ref": None,
            "answer_summary": None,
            "followup_candidates": [],
            "complete_payload": None,
        }

    def _normalize_followup_candidates(self, raw_candidates: Any) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        if not isinstance(raw_candidates, list):
            return normalized

        for index, raw_candidate in enumerate(raw_candidates, start=1):
            if isinstance(raw_candidate, dict):
                question = str(
                    raw_candidate.get("question")
                    or raw_candidate.get("text")
                    or raw_candidate.get("label")
                    or ""
                ).strip()
                if not question:
                    continue
                normalized.append({
                    "id": str(raw_candidate.get("id") or f"candidate_{index}"),
                    "question": question,
                })
                continue

            question = str(raw_candidate or "").strip()
            if not question:
                continue
            normalized.append({
                "id": f"candidate_{index}",
                "question": question,
            })

        return normalized

    def _coerce_float(self, value: Any) -> Optional[float]:
        try:
            if value is None or value == "":
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    def _coerce_int(self, value: Any) -> Optional[int]:
        try:
            if value is None or value == "":
                return None
            return int(value)
        except (TypeError, ValueError):
            return None

    def _project_round_event(self, raw_event: dict[str, Any]) -> dict[str, Any]:
        raw_type = str(raw_event.get("type") or "").strip()
        if raw_type == "parse_result":
            projection = {
                "semantic_summary": raw_event.get("summary"),
                "semantic_confidence": self._coerce_float(raw_event.get("confidence")),
                "query_status": "parsed",
            }
            if raw_event.get("candidate_fields_ref"):
                projection["candidate_fields_ref"] = raw_event.get("candidate_fields_ref")
            if raw_event.get("candidate_values_ref"):
                projection["candidate_values_ref"] = raw_event.get("candidate_values_ref")
            if raw_event.get("fewshot_examples_ref"):
                projection["fewshot_examples_ref"] = raw_event.get("fewshot_examples_ref")
            if raw_event.get("retrieval_trace_ref"):
                projection["retrieval_trace_ref"] = raw_event.get("retrieval_trace_ref")
            if "memory_write_refs" in raw_event:
                projection["memory_write_refs"] = list(raw_event.get("memory_write_refs") or [])
            return projection

        if raw_type in {"data", "table_result"}:
            table_data = raw_event.get("tableData") or raw_event.get("table_data") or {}
            row_count = self._coerce_int(raw_event.get("row_count"))
            if row_count is None and isinstance(table_data, dict):
                row_count = self._coerce_int(table_data.get("rowCount"))
            return {
                "query_status": "completed",
                "row_count": row_count,
                "truncated": bool(raw_event.get("truncated", False)),
                "result_manifest_ref": raw_event.get("result_manifest_ref"),
            }

        if raw_type == "insight":
            summary = str(raw_event.get("summary") or "").strip() or None
            return {
                "answer_summary": summary,
            }

        if raw_type == "replan":
            return {
                "followup_candidates": self._normalize_followup_candidates(
                    raw_event.get("candidateQuestions")
                ),
            }

        if raw_type == "interrupt":
            interrupt_type = str(raw_event.get("interrupt_type") or "").strip()
            if interrupt_type == "followup_select":
                payload = dict(raw_event.get("payload") or {})
                return {
                    "followup_candidates": self._normalize_followup_candidates(
                        payload.get("candidates")
                    ),
                }
            return {}

        if raw_type == "complete":
            return {
                "complete_payload": {
                    key: raw_event.get(key)
                    for key in ("status", "reason")
                    if key in raw_event
                },
            }

        return {}

    def _build_graph_config(self, *, session_id: str) -> dict[str, Any]:
        return {
            "configurable": {
                # session_id is the stable root-graph thread id.
                "thread_id": session_id,
            }
        }

    def _extract_previous_schema_hash(
        self,
        snapshot_payload: Any,
    ) -> Optional[str]:
        if not isinstance(snapshot_payload, dict):
            return None

        try:
            snapshot = PreparedContextSnapshot.model_validate(snapshot_payload)
        except Exception as exc:
            logger.debug("root_graph 无法解析旧 prepared_context_snapshot: %s", exc)
            return None

        if snapshot.previous_schema_hash:
            return snapshot.previous_schema_hash

        try:
            return snapshot.to_workflow_context().schema_hash
        except Exception as exc:
            logger.debug("root_graph 无法从旧 prepared_context_snapshot 提取 schema_hash: %s", exc)
            return None

    async def _default_context_resolver(self, state: RootGraphState) -> dict[str, Any]:
        """解析 root 持有的上下文，并只缓存可序列化快照。"""
        context_state = await self._context_graph_runner.run(
            datasource_name=state.get("datasource_name"),
            datasource_luid=state.get("datasource_luid"),
            project_name=state.get("project_name"),
            previous_schema_hash=self._extract_previous_schema_hash(
                state.get("prepared_context_snapshot")
            ),
        )
        return {
            "tenant_domain": context_state.get("tenant_domain"),
            "tenant_site": context_state.get("tenant_site"),
            "tenant_auth_method": context_state.get("tenant_auth_method"),
            "datasource_luid": context_state.get("datasource_luid"),
            "datasource_name": state.get("datasource_name"),
            "project_name": state.get("project_name"),
            "prepared_context_snapshot": context_state.get("prepared_context_snapshot"),
            "artifact_freshness_report": dict(
                context_state.get("artifact_freshness_report") or {}
            ),
            "artifact_refresh_request": dict(
                context_state.get("artifact_refresh_request") or {}
            ) or None,
            "artifact_refresh_scheduled": bool(
                context_state.get("artifact_refresh_scheduled", False)
            ),
            "degrade_flags": list(context_state.get("degrade_flags") or []),
            "degrade_details": list(context_state.get("degrade_details") or []),
            "memory_invalidation_report": dict(
                context_state.get("memory_invalidation_report") or {}
            ),
            "pending_interrupt_type": context_state.get("pending_interrupt_type"),
            "pending_interrupt_payload": context_state.get("pending_interrupt_payload"),
        }

    async def _build_runtime_context(
        self,
        snapshot_payload: dict[str, Any],
        *,
        platform_adapter: Any = None,
    ) -> WorkflowContext:
        """Rebuild runtime-only workflow objects from a checkpoint snapshot.

        root_graph only persists serializable snapshots. Auth clients and platform
        adapters are reconstructed at execution time.
        """
        snapshot = PreparedContextSnapshot.model_validate(snapshot_payload)
        auth = await self._auth_getter()
        return snapshot.to_workflow_context(
            auth=auth,
            platform_adapter=platform_adapter,
            current_time=datetime.now().isoformat(),
            user_id=self._tableau_username,
        )

    async def aget_state_snapshot(self, *, session_id: str) -> dict[str, Any]:
        if self._compiled_graph is None:
            raise ValueError("root_graph has not been compiled yet")
        snapshot = await self._compiled_graph.aget_state(
            self._build_graph_config(session_id=session_id),
        )
        values = getattr(snapshot, "values", None) or {}
        return dict(values)

    async def _resolve_context_node(self, state: RootGraphState) -> dict[str, Any]:
        return await self._context_resolver(state)

    def _route_after_context(self, state: RootGraphState) -> str:
        if state.get("pending_interrupt_type"):
            return "await_root_interrupt"
        return "run_semantic"

    def _build_langgraph_interrupt_event(self, raw_interrupts: Any) -> dict[str, Any]:
        interrupts = list(raw_interrupts or [])
        if not interrupts:
            raise ValueError("langgraph interrupt payload is empty")

        first_interrupt = interrupts[0]
        payload = getattr(first_interrupt, "value", None)
        if not isinstance(payload, dict):
            raise ValueError("langgraph interrupt payload must be a dict")

        interrupt_type = str(payload.get("interrupt_type") or "").strip()
        if not interrupt_type:
            raise ValueError("langgraph interrupt missing explicit interrupt_type")

        normalized_payload = dict(payload)
        normalized_payload.setdefault("resume_strategy", "root_graph_native")

        namespaces = getattr(first_interrupt, "ns", None) or []
        if namespaces:
            normalized_payload["interrupt_ns"] = list(namespaces)

        return {
            "type": "interrupt",
            "interrupt_type": interrupt_type,
            "interrupt_id": normalized_payload.pop("interrupt_id", None),
            "payload": normalized_payload,
        }

    def _emit_stage_event(
        self,
        writer: Callable[[dict[str, Any]], None],
        *,
        stage: str,
        language: str,
        status: str,
    ) -> None:
        """补齐 root_graph 各阶段的 thinking 事件。

        semantic_graph 原生会输出 `thinking` 事件，query/answer/planner 阶段
        也需要统一投影，前端才能稳定展示阶段切换。
        """
        writer({
            "type": "thinking",
            "stage": stage,
            "name": get_stage_display_name(stage, language),
            "status": status,
        })

    def _build_parse_result_event(
        self,
        parse_result: dict[str, Any],
        *,
        state: Optional[RootGraphState] = None,
        plan_step: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """构造稳定的 parse_result 业务事件。"""
        semantic_raw = parse_result.get("semantic_output") or {}
        event: dict[str, Any] = {
            "type": "parse_result",
            "success": True,
            "query_id": parse_result.get("query_id", ""),
            "summary": build_semantic_summary(semantic_raw),
            "confidence": (
                (semantic_raw.get("self_check") or {}).get("overall_confidence")
                or parse_result.get("confidence")
            ),
            "is_degraded": bool(parse_result.get("is_degraded", False)),
            "query_cache_hit": bool(parse_result.get("query_cache_hit", False)),
        }
        if state is not None:
            event.update(self._build_context_observability_payload(state))
        if parse_result.get("candidate_fields_ref"):
            event["candidate_fields_ref"] = parse_result.get("candidate_fields_ref")
        if parse_result.get("candidate_values_ref"):
            event["candidate_values_ref"] = parse_result.get("candidate_values_ref")
        if parse_result.get("fewshot_examples_ref"):
            event["fewshot_examples_ref"] = parse_result.get("fewshot_examples_ref")
        if parse_result.get("retrieval_trace_ref"):
            event["retrieval_trace_ref"] = parse_result.get("retrieval_trace_ref")
        if "memory_write_refs" in parse_result:
            event["memory_write_refs"] = list(parse_result.get("memory_write_refs") or [])
        if (
            parse_result.get("analysis_plan")
            and not parse_result.get("global_understanding")
        ):
            event["analysis_plan"] = parse_result.get("analysis_plan")
        if parse_result.get("global_understanding"):
            event["global_understanding"] = parse_result.get("global_understanding")
        if parse_result.get("semantic_guard"):
            event["semantic_guard"] = dict(parse_result.get("semantic_guard") or {})
        if plan_step is not None:
            event["planStep"] = plan_step
        return event

    def _build_context_observability_payload(
        self,
        state: RootGraphState,
    ) -> dict[str, Any]:
        """把 context 阶段的新鲜度与降级信息投影为稳定事件字段。"""
        artifact_freshness_report = dict(state.get("artifact_freshness_report") or {})
        artifact_refresh_request = (
            dict(state.get("artifact_refresh_request") or {}) or None
        )
        artifact_refresh_scheduled = bool(state.get("artifact_refresh_scheduled", False))
        degrade_flags = list(state.get("degrade_flags") or [])
        degrade_details = list(state.get("degrade_details") or [])
        memory_invalidation_report = dict(
            state.get("memory_invalidation_report") or {}
        )
        artifact_statuses = {
            artifact_name: str((artifact_state or {}).get("status") or "unknown")
            for artifact_name, artifact_state in artifact_freshness_report.items()
            if isinstance(artifact_state, dict)
        }
        return {
            "artifact_freshness_report": artifact_freshness_report,
            "artifact_refresh_request": artifact_refresh_request,
            "artifact_refresh_scheduled": artifact_refresh_scheduled,
            "degrade_flags": degrade_flags,
            "degrade_details": degrade_details,
            "memory_invalidation_report": memory_invalidation_report,
            "context_metrics": {
                "context_degraded": bool(degrade_flags),
                "artifact_refresh_requested": artifact_refresh_request is not None,
                "artifact_refresh_scheduled": artifact_refresh_scheduled,
                "artifact_refresh_schedule_failed": bool(
                    artifact_refresh_request is not None and not artifact_refresh_scheduled
                ),
                "refresh_trigger": (
                    str(artifact_refresh_request.get("trigger") or "").strip() or None
                    if artifact_refresh_request is not None
                    else None
                ),
                "refresh_requested_artifacts": list(
                    (artifact_refresh_request or {}).get("requested_artifacts") or []
                ),
                "schema_change_invalidated": (
                    str(memory_invalidation_report.get("trigger") or "").strip()
                    == "schema_change"
                ),
                "has_stale_artifacts": "stale" in artifact_statuses.values(),
                "has_missing_artifacts": "missing" in artifact_statuses.values(),
                "degraded_artifacts": [
                    str(detail.get("artifact") or "")
                    for detail in degrade_details
                    if str(detail.get("artifact") or "").strip()
                ],
                "degrade_reason_codes": [
                    str(detail.get("reason") or "")
                    for detail in degrade_details
                    if str(detail.get("reason") or "").strip()
                ],
                "requires_attention": any(
                    bool(detail.get("alert_required")) for detail in degrade_details
                ),
                "invalidation_trigger": (
                    str(memory_invalidation_report.get("trigger") or "").strip() or None
                ),
                "invalidation_total_deleted": int(
                    memory_invalidation_report.get("total_deleted") or 0
                ),
                "artifact_statuses": artifact_statuses,
            },
        }

    def _build_complete_event(
        self,
        state: RootGraphState,
        *,
        status: str,
        reason: Optional[str] = None,
    ) -> dict[str, Any]:
        """构造稳定的 complete 事件，并附带 context 可观测字段。"""
        event = {
            "type": "complete",
            "status": status,
            **self._build_context_observability_payload(state),
        }
        if reason:
            event["reason"] = reason
        return event

    def _emit_projected_event(
        self,
        writer: Callable[[dict[str, Any]], None],
        round_projection: dict[str, Any],
        event: Optional[dict[str, Any]],
    ) -> None:
        """发送事件并同步更新 root_graph 的轮次投影。"""
        if not isinstance(event, dict):
            return
        writer(event)
        projected = self._project_round_event(event)
        if projected:
            round_projection.update(projected)

    async def _run_answer_graph_round(
        self,
        *,
        state: RootGraphState,
        writer: Callable[[dict[str, Any]], None],
        round_projection: dict[str, Any],
        source: str,
        question: str,
        semantic_raw: dict[str, Any],
        result_manifest_ref: Optional[str],
        evidence_bundle_dict: Optional[dict[str, Any]],
        field_semantic: Optional[dict[str, Any]],
        query_id: Optional[str] = None,
        conversation_history: Optional[list[dict[str, str]]] = None,
    ) -> Optional[dict[str, Any]]:
        """统一运行 answer_graph，并把结果投影回 root_graph 状态机。"""
        language = str(state.get("language") or "zh")

        async def _emit_stage(stage: str, status: str) -> None:
            self._emit_stage_event(
                writer,
                stage=stage,
                language=language,
                status=status,
            )

        answer_state = await self._answer_graph_runner.run(
            source=source,
            question=question,
            semantic_raw=semantic_raw,
            result_manifest_ref=result_manifest_ref,
            session_id=state.get("session_id"),
            evidence_bundle_dict=evidence_bundle_dict,
            conversation_history=list(conversation_history or state.get("history") or []),
            replan_history=list(state.get("replan_history") or []),
            analysis_depth=str(state.get("analysis_depth") or "detailed"),
            replan_mode=str(state.get("replan_mode") or "user_select"),
            field_semantic=field_semantic,
            query_id=query_id,
            on_stage=_emit_stage,
        )

        insight_output_dict = answer_state.get("insight_output_dict")
        if isinstance(insight_output_dict, dict):
            self._emit_projected_event(
                writer,
                round_projection,
                {
                    "type": "insight",
                    "source": source,
                    **serialize_insight_payload(insight_output_dict),
                },
            )

        replan_decision = answer_state.get("replan_decision")
        projection = answer_state.get("replan_projection")
        if not isinstance(replan_decision, dict) or not isinstance(projection, dict):
            return None

        replan_event = projection.get("replan_event")
        if isinstance(replan_event, dict):
            self._emit_projected_event(writer, round_projection, replan_event)

        interrupt_payload = projection.get("interrupt_payload")
        if isinstance(interrupt_payload, dict):
            interrupt_payload = {
                **interrupt_payload,
                "resume_strategy": "root_graph_native",
            }
            replan_history = list(state.get("replan_history") or [])
            replan_history.append(dict(replan_decision))
            return {
                **round_projection,
                "planner_state": None,
                "replan_history": replan_history,
                "pending_interrupt_type": "followup_select",
                "pending_interrupt_payload": interrupt_payload,
                "resume_target": None,
            }

        selected_question = str(projection.get("selected_question") or "").strip()
        if projection.get("action") == "auto_continue" and selected_question:
            return self._build_followup_continue_state(
                state=state,
                selected_question=selected_question,
                round_summary=str(
                    (insight_output_dict or {}).get("summary")
                    or round_projection.get("answer_summary")
                    or ""
                ),
                replan_decision=replan_decision,
            )

        return None

    def _build_followup_continue_state(
        self,
        *,
        state: RootGraphState,
        selected_question: str,
        round_summary: str,
        replan_decision: dict[str, Any],
    ) -> dict[str, Any]:
        """把 auto_continue 决策转换成下一轮 root 状态。"""
        replan_history = list(state.get("replan_history") or [])
        replan_history.append(dict(replan_decision))
        followup_history = build_replan_followup_history(
            state.get("history"),
            previous_question=str(state.get("active_question") or state.get("question") or ""),
            round_summary=round_summary,
            replan_reason=str(replan_decision.get("reason") or ""),
            next_question=selected_question,
        )
        return {
            **self._empty_round_projection(),
            "question": selected_question,
            "active_question": selected_question,
            "history": followup_history,
            "replan_history": replan_history,
            "candidate_fields_ref": None,
            "candidate_values_ref": None,
            "fewshot_examples_ref": None,
            "retrieval_trace_ref": None,
            "memory_write_refs": [],
            "planner_state": None,
            "resume_target": None,
            "semantic_parse_result": None,
            "semantic_resume_value": None,
            "pending_interrupt_type": None,
            "pending_interrupt_payload": None,
            "root_resume_value": None,
            "continue_with_question": selected_question,
            "followup_candidates": [],
            "complete_payload": None,
        }

    async def _execute_round_node(self, state: RootGraphState) -> dict[str, Any]:
        writer = get_stream_writer()
        current_question = str(state.get("active_question") or state.get("question") or "").strip()
        if not current_question:
            raise ValueError("root_graph active_question must not be empty")
        prepared_context_snapshot = state.get("prepared_context_snapshot")
        if prepared_context_snapshot is None:
            raise ValueError(
                "root_graph prepared_context_snapshot must not be None before query stage"
            )
        parse_result = state.get("semantic_parse_result")
        if not isinstance(parse_result, dict) or not parse_result.get("success"):
            raise ValueError("root_graph semantic_parse_result must be a successful dict")

        analysis_plan = parse_analysis_plan(
            parse_result.get("analysis_plan"),
            parse_result.get("global_understanding"),
        )
        if (
            analysis_plan is not None
            and analysis_plan.needs_planning
            and analysis_plan.sub_questions
        ):
            return await execute_planner_round(
                self,
                state=state,
                writer=writer,
                analysis_plan=analysis_plan,
                parse_result=parse_result,
                current_question=current_question,
            )

        round_projection = self._empty_round_projection()
        parse_event = self._build_parse_result_event(parse_result, state=state)
        writer(parse_event)
        round_projection.update(self._project_round_event(parse_event))

        semantic_raw, compiler_error = resolve_compiler_semantic_input(parse_result)
        datasource_luid = str(
            state.get("datasource_luid")
            or PreparedContextSnapshot.model_validate(prepared_context_snapshot).datasource_luid
            or ""
        ).strip()
        if not datasource_luid:
            raise ValueError("root_graph datasource_luid must not be empty before query stage")

        if compiler_error:
            error_event = {
                "type": "error",
                "error": compiler_error,
            }
            writer(error_event)
            return {
                **round_projection,
                "planner_state": None,
                "pending_interrupt_type": None,
                "pending_interrupt_payload": None,
                "resume_target": None,
                "root_resume_value": None,
                "continue_with_question": None,
            }

        language = str(state.get("language") or "zh")

        async with VizQLClient() as vizql_client:
            ctx = await self._build_runtime_context(
                prepared_context_snapshot,
                platform_adapter=TableauAdapter(vizql_client=vizql_client),
            )

            self._emit_stage_event(writer, stage="executing", language=language, status="running")
            try:
                query_state = await self._query_graph_runner.run(
                    ctx=ctx,
                    datasource_luid=datasource_luid,
                    semantic_raw=semantic_raw,
                    confirmed_high_risk_signatures=list(
                        state.get("approved_high_risk_signatures") or []
                    ),
                    run_id=state.get("request_id") or None,
                )
                high_risk_payload = dict(query_state.get("high_risk_payload") or {})
                if high_risk_payload:
                    high_risk_payload["resume_strategy"] = "root_graph_native"
                    return {
                        **round_projection,
                        "planner_state": None,
                        "pending_interrupt_type": "high_risk_query_confirm",
                        "pending_interrupt_payload": high_risk_payload,
                        "resume_target": None,
                    }
            finally:
                self._emit_stage_event(writer, stage="executing", language=language, status="completed")

            if bool(query_state.get("query_failed")):
                error_event = {
                    "type": "error",
                    "error": str(query_state.get("query_error") or "query execution failed"),
                }
                writer(error_event)
                return {
                    **round_projection,
                    "planner_state": None,
                    "pending_interrupt_type": None,
                    "pending_interrupt_payload": None,
                    "resume_target": None,
                    "root_resume_value": None,
                    "continue_with_question": None,
                }

            data_event = {
                "type": "data",
                "tableData": query_state.get("table_data"),
                "truncated": bool(
                    query_state.get("query_execution", {}).get("truncated", False)
                ),
                "result_manifest_ref": query_state.get("result_manifest_ref"),
                "profiles_ref": query_state.get("profiles_ref"),
                "chunks_ref": query_state.get("chunks_ref"),
            }
            self._emit_projected_event(writer, round_projection, data_event)

            result_manifest_ref = str(query_state.get("result_manifest_ref") or "").strip()
            answer_update = await self._run_answer_graph_round(
                state=state,
                writer=writer,
                round_projection=round_projection,
                source="single_query",
                question=current_question,
                semantic_raw=semantic_raw,
                result_manifest_ref=result_manifest_ref or None,
                evidence_bundle_dict=build_result_evidence_bundle(
                    source="single_query",
                    question=current_question,
                    semantic_raw=semantic_raw,
                    result_manifest_ref=result_manifest_ref or None,
                    data_profile_dict=dict(query_state.get("data_profile_dict") or {}),
                    query_id=str(parse_result.get("query_id") or "").strip() or None,
                ),
                field_semantic=ctx.field_semantic,
                query_id=str(parse_result.get("query_id") or "").strip() or None,
            )
            if isinstance(answer_update, dict):
                return answer_update

            complete_event = self._build_complete_event(state, status="ok")
            writer(complete_event)
            round_projection.update(self._project_round_event(complete_event))

        return {
            **round_projection,
            "planner_state": None,
            "pending_interrupt_type": None,
            "pending_interrupt_payload": None,
            "resume_target": None,
            "root_resume_value": None,
            "continue_with_question": None,
        }

    async def _run_semantic_node(self, state: RootGraphState) -> dict[str, Any]:
        writer = get_stream_writer()
        prepared_context_snapshot = state.get("prepared_context_snapshot")
        if prepared_context_snapshot is None:
            raise ValueError(
                "root_graph prepared_context_snapshot must not be None before semantic stage"
            )

        snapshot_model = PreparedContextSnapshot.model_validate(prepared_context_snapshot)
        datasource_luid = str(
            state.get("datasource_luid") or snapshot_model.datasource_luid or ""
        ).strip()
        if not datasource_luid:
            raise ValueError("root_graph datasource_luid must not be empty before semantic stage")

        question = str(state.get("active_question") or state.get("question") or "").strip()
        if not question:
            raise ValueError("root_graph active_question must not be empty before semantic stage")

        language = str(state.get("language") or "zh")

        async def _emit_token(token: str) -> None:
            writer({"type": "token", "content": token})

        async def _emit_thinking(thinking: str) -> None:
            writer({"type": "thinking_token", "content": thinking})

        async def _emit_node_status(node_name: str, status: str) -> None:
            stage = get_processing_stage(node_name)
            if not stage:
                return
            writer({
                "type": "thinking",
                "stage": stage,
                "name": get_stage_display_name(stage, language),
                "status": status,
            })

        async with VizQLClient() as vizql_client:
            ctx = await self._build_runtime_context(
                prepared_context_snapshot,
                platform_adapter=TableauAdapter(vizql_client=vizql_client),
            )
            graph = await self._semantic_graph_runner.acompile_graph()
            config = self._semantic_graph_runner.build_config(
                ctx=ctx,
                datasource_luid=datasource_luid,
                session_id=state.get("session_id"),
                request_id=state.get("request_id"),
                run_id=state.get("request_id"),
                on_token=_emit_token,
                on_thinking=_emit_thinking,
            )
            graph_input = self._semantic_graph_runner.build_input(
                question=question,
                datasource_luid=datasource_luid,
                history=list(state.get("history") or []),
                current_time=ctx.current_time,
                language=language,
                analysis_depth=str(state.get("analysis_depth") or "detailed"),
                field_semantic=ctx.field_semantic,
                feature_flags=dict(state.get("feature_flags") or {}),
                resume=state.get("semantic_resume_value"),
            )

            async for event in self._semantic_graph_runner.astream(
                graph=graph,
                graph_input=graph_input,
                config=config,
            ):
                if "__interrupt__" in event:
                    interrupt_event = self._build_langgraph_interrupt_event(
                        event.get("__interrupt__"),
                    )
                    interrupt_type = str(interrupt_event.get("interrupt_type") or "").strip()
                    if interrupt_type in _ROOT_SEMANTIC_INTERRUPT_TYPES:
                        payload = dict(interrupt_event.get("payload") or {})
                        payload["resume_strategy"] = "root_graph_native"
                        return {
                            "pending_interrupt_type": interrupt_type,
                            "pending_interrupt_payload": payload,
                            "resume_target": "run_semantic",
                            "root_resume_value": None,
                            "semantic_resume_value": None,
                        }
                    raise ValueError(
                        f"unsupported semantic interrupt_type in root_graph: {interrupt_type}"
                    )

                for node_name, node_output in event.items():
                    await _emit_node_status(node_name, "running")
                    try:
                        if isinstance(node_output, dict):
                            if node_output.get("needs_clarification"):
                                raise ValueError(
                                    f"{node_name} emitted legacy clarification output; "
                                    "use native LangGraph interrupt() instead"
                                )
                            parse_result = node_output.get("parse_result")
                            if isinstance(parse_result, dict) and parse_result.get("success"):
                                return {
                                    "semantic_parse_result": parse_result,
                                    "candidate_fields_ref": parse_result.get(
                                        "candidate_fields_ref"
                                    ),
                                    "candidate_values_ref": parse_result.get(
                                        "candidate_values_ref"
                                    ),
                                    "fewshot_examples_ref": parse_result.get(
                                        "fewshot_examples_ref"
                                    ),
                                    "retrieval_trace_ref": parse_result.get(
                                        "retrieval_trace_ref"
                                    ),
                                    "memory_write_refs": list(
                                        parse_result.get("memory_write_refs") or []
                                    ),
                                    "planner_state": None,
                                    "resume_target": None,
                                    "semantic_resume_value": None,
                                    "pending_interrupt_type": None,
                                    "pending_interrupt_payload": None,
                                    "continue_with_question": None,
                                }
                    finally:
                        await _emit_node_status(node_name, "completed")

        writer(self._build_complete_event(state, status="ok"))
        return {
            "semantic_parse_result": None,
            "candidate_fields_ref": None,
            "candidate_values_ref": None,
            "fewshot_examples_ref": None,
            "retrieval_trace_ref": None,
            "memory_write_refs": [],
            "planner_state": None,
            "resume_target": None,
            "semantic_resume_value": None,
            "pending_interrupt_type": None,
            "pending_interrupt_payload": None,
            "continue_with_question": None,
            "complete_payload": {"status": "ok"},
        }

    def _route_after_semantic(self, state: RootGraphState) -> str:
        if state.get("pending_interrupt_type"):
            return "await_root_interrupt"
        if state.get("semantic_parse_result"):
            return "execute_round"
        return END

    def _route_after_execute_round(self, state: RootGraphState) -> str:
        if state.get("pending_interrupt_type"):
            return "await_root_interrupt"
        if state.get("continue_with_question"):
            return "run_semantic"
        return END

    async def _await_root_interrupt_node(self, state: RootGraphState) -> dict[str, Any]:
        interrupt_type = str(state.get("pending_interrupt_type") or "").strip()
        interrupt_payload = dict(state.get("pending_interrupt_payload") or {})
        if not interrupt_type:
            raise ValueError("root_graph pending_interrupt_type must not be empty")

        interrupt_payload["interrupt_type"] = interrupt_type
        interrupt_payload.setdefault("resume_strategy", "root_graph_native")

        return {
            "root_resume_value": interrupt(interrupt_payload),
        }

    def _route_after_root_interrupt(self, state: RootGraphState) -> str:
        interrupt_type = str(state.get("pending_interrupt_type") or "").strip()
        if interrupt_type == "datasource_disambiguation":
            return "apply_datasource_selection"
        if interrupt_type in _ROOT_SEMANTIC_INTERRUPT_TYPES:
            return "apply_semantic_resume"
        if interrupt_type == "followup_select":
            return "apply_followup_selection"
        if interrupt_type == "high_risk_query_confirm":
            return "apply_high_risk_confirmation"
        raise ValueError(f"unsupported root interrupt_type: {interrupt_type}")

    async def _apply_datasource_selection_node(self, state: RootGraphState) -> dict[str, Any]:
        resume_value = state.get("root_resume_value")
        if not isinstance(resume_value, dict):
            raise ValueError("datasource_disambiguation resume value must be a dict")

        datasource_luid = str(resume_value.get("datasource_luid") or "").strip()
        if not datasource_luid:
            raise ValueError("datasource_disambiguation resume missing datasource_luid")

        datasource_name = str(
            resume_value.get("datasource_name") or state.get("datasource_name") or ""
        ).strip() or None
        project_name = str(
            resume_value.get("project_name") or state.get("project_name") or ""
        ).strip() or None

        next_state = {
            "datasource_luid": datasource_luid,
            "datasource_name": datasource_name,
            "project_name": project_name,
            "prepared_context_snapshot": None,
            "replan_history": [],
            "semantic_parse_result": None,
            "candidate_fields_ref": None,
            "candidate_values_ref": None,
            "fewshot_examples_ref": None,
            "retrieval_trace_ref": None,
            "memory_write_refs": [],
            "planner_state": None,
            "resume_target": None,
            "semantic_resume_value": None,
            "pending_interrupt_type": None,
            "pending_interrupt_payload": None,
            "root_resume_value": None,
            "continue_with_question": None,
            "complete_payload": None,
            **self._empty_round_projection(),
        }
        return next_state

    async def _apply_semantic_resume_node(self, state: RootGraphState) -> dict[str, Any]:
        return {
            "pending_interrupt_type": None,
            "pending_interrupt_payload": None,
            "semantic_resume_value": state.get("root_resume_value"),
            "root_resume_value": None,
        }

    def _route_after_semantic_resume(self, state: RootGraphState) -> str:
        if state.get("resume_target") == "execute_round":
            return "execute_round"
        return "run_semantic"

    async def _apply_followup_selection_node(self, state: RootGraphState) -> dict[str, Any]:
        selected_question = str(state.get("root_resume_value") or "").strip()
        if not selected_question:
            raise ValueError("followup_select resume value must not be empty")

        # After the user picks a follow-up question, the next round becomes the new
        # active question. We intentionally keep history unchanged here to preserve
        # the current product contract.
        return {
            "question": selected_question,
            "active_question": selected_question,
            "semantic_parse_result": None,
            "candidate_fields_ref": None,
            "candidate_values_ref": None,
            "fewshot_examples_ref": None,
            "retrieval_trace_ref": None,
            "memory_write_refs": [],
            "planner_state": None,
            "resume_target": None,
            "semantic_resume_value": None,
            "pending_interrupt_type": None,
            "pending_interrupt_payload": None,
            "root_resume_value": None,
            "continue_with_question": None,
            "followup_candidates": [],
            "complete_payload": None,
            **self._empty_round_projection(),
        }

    async def _apply_high_risk_confirmation_node(self, state: RootGraphState) -> dict[str, Any]:
        resume_value = state.get("root_resume_value")
        confirmed = resume_value if isinstance(resume_value, bool) else bool(
            isinstance(resume_value, dict) and resume_value.get("confirm") is True
        )
        if not confirmed:
            raise ValueError("high_risk_query_confirm resume value must be true")

        pending_payload = dict(state.get("pending_interrupt_payload") or {})
        risk_signature = str(pending_payload.get("risk_signature") or "").strip()
        approved_signatures = list(state.get("approved_high_risk_signatures") or [])
        if risk_signature and risk_signature not in approved_signatures:
            approved_signatures.append(risk_signature)

        return {
            "pending_interrupt_type": None,
            "pending_interrupt_payload": None,
            "root_resume_value": None,
            "approved_high_risk_signatures": approved_signatures,
            "resume_target": None,
        }

    async def _get_compiled_graph(self) -> Any:
        if self._compiled_graph is not None:
            return self._compiled_graph

        graph = StateGraph(RootGraphState)
        graph.add_node("resolve_context", self._resolve_context_node)
        graph.add_node("run_semantic", self._run_semantic_node)
        graph.add_node("execute_round", self._execute_round_node)
        graph.add_node("await_root_interrupt", self._await_root_interrupt_node)
        graph.add_node(
            "apply_datasource_selection",
            self._apply_datasource_selection_node,
        )
        graph.add_node("apply_semantic_resume", self._apply_semantic_resume_node)
        graph.add_node("apply_followup_selection", self._apply_followup_selection_node)
        graph.add_node(
            "apply_high_risk_confirmation",
            self._apply_high_risk_confirmation_node,
        )

        graph.add_edge(START, "resolve_context")
        graph.add_conditional_edges(
            "resolve_context",
            self._route_after_context,
            {
                "run_semantic": "run_semantic",
                "await_root_interrupt": "await_root_interrupt",
            },
        )
        graph.add_conditional_edges(
            "run_semantic",
            self._route_after_semantic,
            {
                "execute_round": "execute_round",
                "await_root_interrupt": "await_root_interrupt",
                END: END,
            },
        )
        graph.add_conditional_edges(
            "execute_round",
            self._route_after_execute_round,
            {
                "run_semantic": "run_semantic",
                "await_root_interrupt": "await_root_interrupt",
                END: END,
            },
        )
        graph.add_conditional_edges(
            "await_root_interrupt",
            self._route_after_root_interrupt,
            {
                "apply_datasource_selection": "apply_datasource_selection",
                "apply_semantic_resume": "apply_semantic_resume",
                "apply_followup_selection": "apply_followup_selection",
                "apply_high_risk_confirmation": "apply_high_risk_confirmation",
            },
        )
        # Datasource selection changes the root context contract. Always rebuild
        # tenant/datasource/context snapshot through resolve_context instead of
        # trying to patch the semantic stage in place.
        graph.add_edge("apply_datasource_selection", "resolve_context")
        graph.add_conditional_edges(
            "apply_semantic_resume",
            self._route_after_semantic_resume,
            {
                "run_semantic": "run_semantic",
                "execute_round": "execute_round",
            },
        )
        graph.add_edge("apply_followup_selection", "run_semantic")
        graph.add_edge("apply_high_risk_confirmation", "execute_round")

        self._compiled_graph = graph.compile(
            checkpointer=await get_root_graph_checkpointer()
        )
        return self._compiled_graph

    async def _stream_compiled_graph(
        self,
        graph_input: Any,
        *,
        session_id: str,
    ) -> AsyncIterator[dict[str, Any]]:
        compiled_graph = await self._get_compiled_graph()
        async for mode, chunk in compiled_graph.astream(
            graph_input,
            self._build_graph_config(session_id=session_id),
            stream_mode=["custom", "updates"],
        ):
            if mode == "custom":
                if isinstance(chunk, dict):
                    yield dict(chunk)
                continue

            if mode == "updates" and isinstance(chunk, dict) and "__interrupt__" in chunk:
                yield self._build_langgraph_interrupt_event(chunk.get("__interrupt__"))

    async def run_stream(self, request: RootGraphRequest) -> AsyncIterator[dict[str, Any]]:
        self.build_run_state(request)
        async for event in self._stream_compiled_graph(
            {
                **self._build_initial_state(
                    question=request.latest_user_message,
                    datasource_name=request.datasource_name,
                    datasource_luid=request.datasource_luid,
                    project_name=request.project_name,
                    history=request.recent_messages,
                    language=request.locale,
                    analysis_depth=request.analysis_depth,
                    replan_mode=request.replan_mode,
                    selected_candidate_question=request.selected_candidate_question,
                    feature_flags=request.feature_flags,
                    session_id=request.session_id,
                ),
            },
            session_id=request.session_id,
        ):
            yield event

    async def execute_stream(
        self,
        question: str,
        datasource_name: Optional[str] = None,
        datasource_luid: Optional[str] = None,
        project_name: Optional[str] = None,
        history: Optional[list[dict[str, str]]] = None,
        language: str = "zh",
        analysis_depth: str = "detailed",
        replan_mode: str = "user_select",
        selected_candidate_question: Optional[str] = None,
        feature_flags: Optional[dict[str, bool]] = None,
        session_id: Optional[str] = None,
        _replan_history: Optional[list[dict[str, Any]]] = None,
        _emit_complete: bool = True,
    ) -> AsyncIterator[dict[str, Any]]:
        del _replan_history
        del _emit_complete

        request = self.build_request(
            latest_user_message=question,
            recent_messages=history,
            datasource_luid=datasource_luid,
            datasource_name=datasource_name,
            project_name=project_name,
            locale=language,
            analysis_depth=analysis_depth,
            replan_mode=replan_mode,
            selected_candidate_question=selected_candidate_question,
            feature_flags=feature_flags,
            session_id=session_id,
        )

        async for event in self.run_stream(request):
            yield event

    async def resume_stream(
        self,
        *,
        question: str,
        resume_value: Any,
        datasource_name: Optional[str] = None,
        datasource_luid: Optional[str] = None,
        project_name: Optional[str] = None,
        history: Optional[list[dict[str, str]]] = None,
        language: str = "zh",
        analysis_depth: str = "detailed",
        replan_mode: str = "user_select",
        session_id: Optional[str] = None,
        resume_strategy: str = "root_graph_native",
    ) -> AsyncIterator[dict[str, Any]]:
        del question
        del datasource_name
        del datasource_luid
        del project_name
        del history
        del language
        del analysis_depth
        del replan_mode

        if str(resume_strategy or "").strip() != "root_graph_native":
            raise ValueError("resume_strategy must be root_graph_native")

        normalized_session_id = str(session_id or "").strip()
        if not normalized_session_id:
            raise ValueError("session_id is required for root_graph_native resume")

        async for event in self._stream_compiled_graph(
            Command(resume=resume_value),
            session_id=normalized_session_id,
        ):
            yield event



