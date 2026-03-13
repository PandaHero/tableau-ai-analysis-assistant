# -*- coding: utf-8 -*-
"""LangGraph query-stage runner."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from analytics_assistant.src.orchestration.workflow.context import WorkflowContext

from .service import build_high_risk_interrupt_payload, execute_semantic_query


class QueryGraphState(TypedDict, total=False):
    request_id: Optional[str]
    run_id: Optional[str]
    ctx: WorkflowContext
    datasource_luid: str
    semantic_raw: dict[str, Any]
    confirmed_high_risk_signatures: list[str]
    high_risk_payload: Optional[dict[str, Any]]
    query_execution: Optional[dict[str, Any]]
    execute_result_model: Any
    table_data: Optional[dict[str, Any]]
    query_execute_ms: Optional[float]
    query_failed: bool
    query_error: Optional[str]
    result_manifest_ref: Optional[str]
    profiles_ref: Optional[str]
    chunks_ref: Optional[str]
    artifact_root: Optional[str]
    allowed_files: Optional[list[str]]
    data_profile_dict: Optional[dict[str, Any]]


class QueryGraphRunner:
    """Minimal query-stage graph for risk guard -> execute query."""

    def __init__(
        self,
        *,
        risk_evaluator: Optional[Callable[..., Optional[dict[str, Any]]]] = None,
        query_executor: Optional[Callable[..., Awaitable[dict[str, Any]]]] = None,
        request_id: Optional[str] = None,
        artifact_root_dir: Optional[str] = None,
    ) -> None:
        self._risk_evaluator = risk_evaluator or build_high_risk_interrupt_payload
        self._query_executor = query_executor or execute_semantic_query
        self._request_id = request_id
        self._artifact_root_dir = artifact_root_dir
        self._compiled_graph = self._compile_graph()

    async def run(
        self,
        *,
        ctx: WorkflowContext,
        datasource_luid: str,
        semantic_raw: dict[str, Any],
        confirmed_high_risk_signatures: Optional[list[str]] = None,
        run_id: Optional[str] = None,
    ) -> QueryGraphState:
        # `WorkflowContext` 包含 auth / adapter 等运行时对象，不适合进入任何
        # checkpoint 或子图 state。这里保持 query_graph 的统一入口，但运行时按
        # 确定性顺序直接执行各阶段，避免把不可序列化对象塞进 LangGraph 状态。
        state: QueryGraphState = {
            "request_id": self._request_id,
            "run_id": run_id,
            "ctx": ctx,
            "datasource_luid": datasource_luid,
            "semantic_raw": semantic_raw,
            "confirmed_high_risk_signatures": list(
                confirmed_high_risk_signatures or []
            ),
            "high_risk_payload": None,
            "query_execution": None,
            "table_data": None,
            "query_execute_ms": None,
            "query_failed": False,
            "query_error": None,
            "result_manifest_ref": None,
            "profiles_ref": None,
            "chunks_ref": None,
            "artifact_root": None,
            "allowed_files": None,
            "data_profile_dict": None,
        }
        state.update(await self._prepare_node(state))
        state.update(await self._assess_risk_node(state))
        if state.get("high_risk_payload"):
            return state
        state.update(await self._execute_query_node(state))
        return state

    async def _prepare_node(self, state: QueryGraphState) -> dict[str, Any]:
        datasource_luid = str(state.get("datasource_luid") or "").strip()
        if not datasource_luid:
            raise ValueError("query_graph datasource_luid must not be empty")

        semantic_raw = state.get("semantic_raw")
        if not isinstance(semantic_raw, dict) or not semantic_raw:
            raise ValueError("query_graph semantic_raw must be a non-empty dict")

        if state.get("ctx") is None:
            raise ValueError("query_graph ctx must not be None")

        return {}

    async def _assess_risk_node(self, state: QueryGraphState) -> dict[str, Any]:
        payload = self._risk_evaluator(
            ctx=state["ctx"],
            datasource_luid=state["datasource_luid"],
            semantic_raw=state["semantic_raw"],
            confirmed_signatures=set(state.get("confirmed_high_risk_signatures") or []),
        )
        return {"high_risk_payload": payload}

    def _route_after_risk(self, state: QueryGraphState) -> str:
        if state.get("high_risk_payload"):
            return END
        return "execute_query"

    async def _execute_query_node(self, state: QueryGraphState) -> dict[str, Any]:
        query_execution = await self._query_executor(
            ctx=state["ctx"],
            datasource_luid=state["datasource_luid"],
            semantic_raw=state["semantic_raw"],
            request_id=state.get("request_id"),
            run_id=state.get("run_id"),
            artifact_root_dir=self._artifact_root_dir,
        )
        if not isinstance(query_execution, dict):
            raise ValueError("query_graph query_executor must return a dict payload")

        return {
            "query_execution": query_execution,
            "execute_result_model": query_execution.get("execute_result_model"),
            "table_data": query_execution.get("tableData"),
            "query_execute_ms": query_execution.get("query_execute_ms"),
            "query_failed": not bool(query_execution.get("success")),
            "query_error": query_execution.get("error"),
            "result_manifest_ref": query_execution.get("result_manifest_ref"),
            "profiles_ref": query_execution.get("profiles_ref"),
            "chunks_ref": query_execution.get("chunks_ref"),
            "artifact_root": query_execution.get("artifact_root"),
            "allowed_files": query_execution.get("allowed_files"),
            "data_profile_dict": query_execution.get("data_profile_dict"),
        }

    def _compile_graph(self) -> Any:
        graph = StateGraph(QueryGraphState)
        graph.add_node("prepare", self._prepare_node)
        graph.add_node("assess_risk", self._assess_risk_node)
        graph.add_node("execute_query", self._execute_query_node)
        graph.add_edge(START, "prepare")
        graph.add_edge("prepare", "assess_risk")
        graph.add_conditional_edges(
            "assess_risk",
            self._route_after_risk,
            {
                "execute_query": "execute_query",
                END: END,
            },
        )
        graph.add_edge("execute_query", END)
        return graph.compile()


__all__ = [
    "QueryGraphRunner",
    "QueryGraphState",
]
