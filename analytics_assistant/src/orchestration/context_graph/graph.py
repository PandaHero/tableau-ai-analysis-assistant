# -*- coding: utf-8 -*-
"""LangGraph context 阶段运行器。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Awaitable, Callable, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from analytics_assistant.src.orchestration.workflow.context import (
    PreparedContextSnapshot,
    WorkflowContext,
)
from analytics_assistant.src.orchestration.retrieval_memory import (
    MemoryInvalidationService,
)
from analytics_assistant.src.platform.tableau.auth import get_tableau_auth_async
from analytics_assistant.src.platform.tableau.artifact_keys import (
    build_field_artifact_key,
    build_metadata_snapshot_cache_key,
)
from analytics_assistant.src.platform.tableau.client import (
    TableauDatasourceAmbiguityError,
    VizQLClient,
)
from analytics_assistant.src.platform.tableau.data_loader import (
    TableauDataLoader,
)
from analytics_assistant.src.platform.tableau.prewarm_runtime import (
    schedule_datasource_artifact_preparation,
)

from .refresh import build_artifact_refresh_request


class ContextGraphState(TypedDict, total=False):
    request_id: Optional[str]
    user_id: str
    datasource_name: Optional[str]
    datasource_luid: Optional[str]
    project_name: Optional[str]
    previous_schema_hash: Optional[str]
    auth: Any
    prepared_context_snapshot: Optional[dict[str, Any]]
    tenant_domain: Optional[str]
    tenant_site: Optional[str]
    tenant_auth_method: Optional[str]
    field_semantic_available: bool
    field_samples_available: bool
    datasource_prewarm_scheduled: bool
    artifact_refresh_scheduled: bool
    artifact_freshness_report: dict[str, dict[str, Any]]
    artifact_refresh_request: Optional[dict[str, Any]]
    degrade_flags: list[str]
    degrade_details: list[dict[str, Any]]
    memory_invalidation_report: dict[str, Any]
    pending_interrupt_type: Optional[str]
    pending_interrupt_payload: Optional[dict[str, Any]]


class ContextGraphRunner:
    """负责认证、数据源解析、数据模型准备和字段语义就绪状态。"""

    def __init__(
        self,
        *,
        tableau_username: str,
        request_id: Optional[str] = None,
        auth_getter: Optional[Callable[[], Awaitable[Any]]] = None,
        vizql_client_factory: Optional[Callable[[], Any]] = None,
        data_loader_factory: Optional[Callable[[Any], Any]] = None,
        prewarm_scheduler: Optional[Callable[..., bool]] = None,
        memory_invalidation_service: Optional[MemoryInvalidationService] = None,
    ) -> None:
        self._tableau_username = tableau_username
        self._request_id = request_id
        self._auth_getter = auth_getter or get_tableau_auth_async
        self._vizql_client_factory = vizql_client_factory or VizQLClient
        self._data_loader_factory = (
            data_loader_factory or (lambda client: TableauDataLoader(client=client))
        )
        self._prewarm_scheduler = prewarm_scheduler or schedule_datasource_artifact_preparation
        self._memory_invalidation_service = (
            memory_invalidation_service or MemoryInvalidationService()
        )
        self._compiled_graph = self._compile_graph()

    async def run(
        self,
        *,
        datasource_name: Optional[str] = None,
        datasource_luid: Optional[str] = None,
        project_name: Optional[str] = None,
        previous_schema_hash: Optional[str] = None,
    ) -> ContextGraphState:
        """执行 context 阶段并返回可序列化状态。"""
        return await self._compiled_graph.ainvoke(
            {
                "request_id": self._request_id,
                "user_id": self._tableau_username,
                "datasource_name": str(datasource_name or "").strip() or None,
                "datasource_luid": str(datasource_luid or "").strip() or None,
                "project_name": str(project_name or "").strip() or None,
                "previous_schema_hash": str(previous_schema_hash or "").strip() or None,
                "auth": None,
                "prepared_context_snapshot": None,
                "tenant_domain": None,
                "tenant_site": None,
                "tenant_auth_method": None,
                "field_semantic_available": False,
                "field_samples_available": False,
                "datasource_prewarm_scheduled": False,
                "artifact_refresh_scheduled": False,
                "artifact_freshness_report": {},
                "artifact_refresh_request": None,
                "degrade_flags": [],
                "degrade_details": [],
                "memory_invalidation_report": {},
                "pending_interrupt_type": None,
                "pending_interrupt_payload": None,
            }
        )

    def _resolve_optional_artifact_status(
        self,
        *,
        available: bool,
        schema_changed: bool,
        prewarm_scheduled: bool,
    ) -> str:
        if available and schema_changed:
            return "stale"
        if available:
            return "ready"
        if prewarm_scheduled:
            return "building"
        return "missing"

    def _build_optional_artifact_state(
        self,
        *,
        artifact_name: str,
        datasource_luid: str,
        tenant_site: Optional[str],
        schema_hash: Optional[str],
        available: bool,
        schema_changed: bool,
        artifact_refresh_request: Optional[dict[str, Any]],
        artifact_refresh_scheduled: bool,
    ) -> dict[str, Any]:
        requested_artifacts = set(
            (artifact_refresh_request or {}).get("requested_artifacts") or []
        )
        refresh_requested = artifact_name in requested_artifacts
        refresh_trigger = (
            str((artifact_refresh_request or {}).get("trigger") or "").strip() or None
        )
        refresh_scheduled = refresh_requested and artifact_refresh_scheduled

        status = self._resolve_optional_artifact_status(
            available=available,
            schema_changed=schema_changed,
            prewarm_scheduled=refresh_scheduled,
        )
        if status == "ready":
            reason = "artifact_ready"
            degrade_mode = "none"
        elif status == "stale":
            reason = "schema_changed"
            degrade_mode = "read_stale"
        elif refresh_requested and refresh_scheduled:
            reason = "refresh_scheduled"
            degrade_mode = "fallback_retrieval"
        elif refresh_requested:
            reason = "refresh_not_scheduled"
            degrade_mode = "fallback_retrieval"
        else:
            reason = "artifact_missing"
            degrade_mode = "fallback_retrieval"

        return {
            "artifact_key": build_field_artifact_key(
                datasource_id=datasource_luid,
                site=tenant_site,
                artifact_type=artifact_name,
                schema_hash=schema_hash,
            ),
            "status": status,
            "required": False,
            "degraded": status != "ready",
            "reason": reason,
            "degrade_mode": degrade_mode,
            "refresh_requested": refresh_requested,
            "refresh_scheduled": refresh_scheduled,
            "refresh_trigger": refresh_trigger if refresh_requested else None,
            "alert_required": bool(
                refresh_requested and not refresh_scheduled and not available
            ),
        }

    def _build_artifact_freshness_report(
        self,
        *,
        datasource_luid: str,
        tenant_site: Optional[str],
        schema_hash: Optional[str],
        schema_changed: bool,
        field_semantic_available: bool,
        field_samples_available: bool,
        artifact_refresh_request: Optional[dict[str, Any]],
        artifact_refresh_scheduled: bool,
    ) -> dict[str, dict[str, Any]]:
        return {
            "metadata_snapshot": {
                "artifact_key": build_metadata_snapshot_cache_key(
                    datasource_id=datasource_luid,
                    site=tenant_site,
                    schema_hash=schema_hash,
                ),
                "status": "ready",
                "required": True,
                "degraded": False,
                "reason": "metadata_ready",
                "degrade_mode": "none",
                "refresh_requested": False,
                "refresh_scheduled": False,
                "refresh_trigger": None,
                "alert_required": False,
            },
            "field_semantic_index": self._build_optional_artifact_state(
                artifact_name="field_semantic_index",
                datasource_luid=datasource_luid,
                tenant_site=tenant_site,
                schema_hash=schema_hash,
                available=field_semantic_available,
                schema_changed=schema_changed,
                artifact_refresh_request=artifact_refresh_request,
                artifact_refresh_scheduled=artifact_refresh_scheduled,
            ),
            "field_values_index": self._build_optional_artifact_state(
                artifact_name="field_values_index",
                datasource_luid=datasource_luid,
                tenant_site=tenant_site,
                schema_hash=schema_hash,
                available=field_samples_available,
                schema_changed=schema_changed,
                artifact_refresh_request=artifact_refresh_request,
                artifact_refresh_scheduled=artifact_refresh_scheduled,
            ),
        }

    def _build_degrade_flags(
        self,
        freshness_report: dict[str, dict[str, Any]],
    ) -> list[str]:
        flags: list[str] = []
        if freshness_report.get("field_semantic_index", {}).get("degraded"):
            flags.append("semantic_retrieval_degraded")
        if freshness_report.get("field_values_index", {}).get("degraded"):
            flags.append("value_retrieval_degraded")
        return flags

    def _build_degrade_details(
        self,
        freshness_report: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """把降级状态转换成稳定的 detail 列表，便于 root/API 投影。"""
        degrade_details: list[dict[str, Any]] = []
        artifact_flag_map = {
            "field_semantic_index": "semantic_retrieval_degraded",
            "field_values_index": "value_retrieval_degraded",
        }
        for artifact_name, degrade_flag in artifact_flag_map.items():
            artifact_state = dict(freshness_report.get(artifact_name) or {})
            if not artifact_state.get("degraded"):
                continue
            degrade_details.append({
                "artifact": artifact_name,
                "degrade_flag": degrade_flag,
                "status": artifact_state.get("status"),
                "reason": artifact_state.get("reason"),
                "degrade_mode": artifact_state.get("degrade_mode"),
                "refresh_requested": bool(artifact_state.get("refresh_requested")),
                "refresh_scheduled": bool(artifact_state.get("refresh_scheduled")),
                "refresh_trigger": artifact_state.get("refresh_trigger"),
                "alert_required": bool(artifact_state.get("alert_required")),
            })
        return degrade_details

    async def _prepare_node(self, state: ContextGraphState) -> dict[str, Any]:
        if not state.get("datasource_name") and not state.get("datasource_luid"):
            raise ValueError("context_graph requires datasource_name or datasource_luid")
        return {}

    async def _authenticate_node(self, _state: ContextGraphState) -> dict[str, Any]:
        auth = await self._auth_getter()
        return {
            "auth": auth,
            "tenant_domain": getattr(auth, "domain", None),
            "tenant_site": getattr(auth, "site", None),
            "tenant_auth_method": getattr(auth, "auth_method", None),
        }

    async def _load_context_node(self, state: ContextGraphState) -> dict[str, Any]:
        auth = state.get("auth")
        if auth is None:
            raise ValueError("context_graph auth must not be None")

        async with self._vizql_client_factory() as vizql_client:
            loader = self._data_loader_factory(vizql_client)
            try:
                data_model = await loader.load_data_model(
                    datasource_id=state.get("datasource_luid"),
                    datasource_name=state.get("datasource_name"),
                    project_name=state.get("project_name"),
                    auth=auth,
                    skip_index_creation=True,
                )
            except TableauDatasourceAmbiguityError as exc:
                return {
                    "prepared_context_snapshot": None,
                    "pending_interrupt_type": "datasource_disambiguation",
                    "pending_interrupt_payload": {
                        "message": str(exc) or "找到多个同名数据源，请先选择具体数据源。",
                        "choices": list(exc.choices or []),
                        "datasource_name": exc.datasource_name,
                        "project_name": exc.project_name,
                        "resume_strategy": "root_graph_native",
                    },
                }

        prepared_context = WorkflowContext(
            auth=auth,
            datasource_luid=data_model.datasource_id,
            data_model=data_model,
            field_samples=getattr(data_model, "_field_samples_cache", None),
            current_time=datetime.now().isoformat(),
            user_id=state.get("user_id"),
            previous_schema_hash=state.get("previous_schema_hash"),
        )
        prepared_context = await prepared_context.load_field_semantic(
            allow_online_inference=False,
        )
        schema_changed = prepared_context.has_schema_changed()
        current_schema_hash = prepared_context.schema_hash
        memory_invalidation_report = prepared_context.invalidate_cache_if_schema_changed(
            self._memory_invalidation_service,
        )
        field_semantic_available = bool(prepared_context.field_semantic)
        field_samples_available = bool(prepared_context.field_samples)
        artifact_refresh_request = build_artifact_refresh_request(
            datasource_luid=data_model.datasource_id,
            schema_changed=schema_changed,
            previous_schema_hash=state.get("previous_schema_hash"),
            schema_hash=current_schema_hash,
            field_semantic_available=field_semantic_available,
            field_samples_available=field_samples_available,
        )
        datasource_prewarm_scheduled = False
        if artifact_refresh_request is not None:
            datasource_prewarm_scheduled = bool(
                self._prewarm_scheduler(
                    datasource_id=data_model.datasource_id,
                    auth=auth,
                    refresh_request=artifact_refresh_request.model_dump(mode="json"),
                )
            )
        prepared_context = prepared_context.update_current_time()
        freshness_report = self._build_artifact_freshness_report(
            datasource_luid=data_model.datasource_id,
            tenant_site=getattr(auth, "site", None),
            schema_hash=current_schema_hash,
            schema_changed=schema_changed,
            field_semantic_available=field_semantic_available,
            field_samples_available=field_samples_available,
            artifact_refresh_request=(
                artifact_refresh_request.model_dump(mode="json")
                if artifact_refresh_request is not None
                else None
            ),
            artifact_refresh_scheduled=datasource_prewarm_scheduled,
        )
        degrade_details = self._build_degrade_details(freshness_report)

        return {
            "prepared_context_snapshot": prepared_context.to_snapshot().model_dump(
                mode="json"
            ),
            "datasource_luid": data_model.datasource_id,
            "field_semantic_available": field_semantic_available,
            "field_samples_available": field_samples_available,
            "datasource_prewarm_scheduled": datasource_prewarm_scheduled,
            "artifact_refresh_scheduled": datasource_prewarm_scheduled,
            "artifact_freshness_report": freshness_report,
            "artifact_refresh_request": (
                artifact_refresh_request.model_dump(mode="json")
                if artifact_refresh_request is not None
                else None
            ),
            "degrade_flags": self._build_degrade_flags(freshness_report),
            "degrade_details": degrade_details,
            "memory_invalidation_report": memory_invalidation_report,
            "pending_interrupt_type": None,
            "pending_interrupt_payload": None,
        }

    def _compile_graph(self) -> Any:
        graph = StateGraph(ContextGraphState)
        graph.add_node("prepare", self._prepare_node)
        graph.add_node("authenticate", self._authenticate_node)
        graph.add_node("load_context", self._load_context_node)
        graph.add_edge(START, "prepare")
        graph.add_edge("prepare", "authenticate")
        graph.add_edge("authenticate", "load_context")
        graph.add_edge("load_context", END)
        return graph.compile()


__all__ = ["ContextGraphRunner", "ContextGraphState"]
