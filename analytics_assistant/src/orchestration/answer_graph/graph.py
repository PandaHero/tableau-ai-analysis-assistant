# -*- coding: utf-8 -*-
"""LangGraph answer_graph 运行器。"""

from __future__ import annotations

import asyncio
from contextvars import ContextVar
import logging
from typing import Any, Awaitable, Callable, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from analytics_assistant.src.orchestration.query_graph import load_json_artifact

from .service import (
    build_bundle_insight_output,
    build_replan_projection,
    build_result_evidence_bundle,
)
from .workspace import InsightWorkspace, prepare_insight_workspace

logger = logging.getLogger(__name__)
_stage_callback_var: ContextVar[Any] = ContextVar(
    "answer_graph_stage_callback",
    default=None,
)


class AnswerGraphState(TypedDict, total=False):
    request_id: Optional[str]
    source: str
    question: str
    semantic_raw: dict[str, Any]
    result_manifest_ref: Optional[str]
    artifact_root_dir: Optional[str]
    session_id: Optional[str]
    workspace: Optional[InsightWorkspace]
    evidence_bundle_dict: Optional[dict[str, Any]]
    conversation_history: list[dict[str, str]]
    replan_history: list[dict[str, Any]]
    analysis_depth: str
    replan_mode: str
    field_semantic: Optional[dict[str, Any]]
    query_id: Optional[str]
    on_token: Any
    on_thinking: Any
    insight_output_dict: Optional[dict[str, Any]]
    replan_decision: Optional[dict[str, Any]]
    replan_projection: Optional[dict[str, Any]]
    insight_skipped: bool
    insight_failed: bool
    replanner_failed: bool
    insight_ms: Optional[float]
    replanner_ms: Optional[float]
    insight_findings_count: int
    replanner_should_replan: Optional[bool]
    replanner_suggested_questions_count: int
    replanner_candidate_questions_count: int


class AnswerGraphRunner:
    """负责 answer 阶段的洞察与重规划。"""

    def __init__(
        self,
        *,
        invoke_insight_agent: Callable[..., Awaitable[Any]],
        invoke_replanner_agent: Callable[..., Awaitable[Any]],
        request_id: Optional[str] = None,
    ) -> None:
        self._invoke_insight_agent = invoke_insight_agent
        self._invoke_replanner_agent = invoke_replanner_agent
        self._request_id = request_id
        self._compiled_graph = self._compile_graph()

    async def run(
        self,
        *,
        source: str,
        question: str,
        semantic_raw: dict[str, Any],
        result_manifest_ref: Optional[str] = None,
        artifact_root_dir: Optional[str] = None,
        session_id: Optional[str] = None,
        evidence_bundle_dict: Optional[dict[str, Any]] = None,
        conversation_history: Optional[list[dict[str, str]]] = None,
        replan_history: Optional[list[dict[str, Any]]] = None,
        analysis_depth: str = "detailed",
        replan_mode: str = "user_select",
        field_semantic: Optional[dict[str, Any]] = None,
        query_id: Optional[str] = None,
        on_token: Any = None,
        on_thinking: Any = None,
        on_stage: Any = None,
    ) -> AnswerGraphState:
        token = _stage_callback_var.set(on_stage)
        try:
            return await self._compiled_graph.ainvoke({
                "request_id": self._request_id,
                "source": source,
                "question": question,
                "semantic_raw": semantic_raw,
                "result_manifest_ref": result_manifest_ref,
                "artifact_root_dir": artifact_root_dir,
                "session_id": session_id,
                "workspace": None,
                "evidence_bundle_dict": evidence_bundle_dict,
                "conversation_history": list(conversation_history or []),
                "replan_history": list(replan_history or []),
                "analysis_depth": analysis_depth,
                "replan_mode": replan_mode,
                "field_semantic": field_semantic,
                "query_id": query_id,
                "on_token": on_token,
                "on_thinking": on_thinking,
                "insight_output_dict": None,
                "replan_decision": None,
                "replan_projection": None,
                "insight_skipped": False,
                "insight_failed": False,
                "replanner_failed": False,
                "insight_ms": None,
                "replanner_ms": None,
                "insight_findings_count": 0,
                "replanner_should_replan": None,
                "replanner_suggested_questions_count": 0,
                "replanner_candidate_questions_count": 0,
            })
        finally:
            _stage_callback_var.reset(token)

    async def _notify_stage(
        self,
        state: AnswerGraphState,
        *,
        stage: str,
        status: str,
    ) -> None:
        callback = _stage_callback_var.get()
        if not callable(callback):
            return
        maybe_awaitable = callback(stage, status)
        if asyncio.iscoroutine(maybe_awaitable):
            await maybe_awaitable

    async def _prepare_node(self, state: AnswerGraphState) -> dict[str, Any]:
        updates: dict[str, Any] = {}
        explicit_bundle = state.get("evidence_bundle_dict")
        if isinstance(explicit_bundle, dict):
            updates["evidence_bundle_dict"] = dict(explicit_bundle)

        result_manifest_ref = str(state.get("result_manifest_ref") or "").strip()
        if not result_manifest_ref:
            # 无 manifest 时也保持正式 bundle 契约，避免复杂问题最终 replan
            # 再退回旧的 data_profile 桥接层。
            updates.setdefault(
                "evidence_bundle_dict",
                build_result_evidence_bundle(
                    source=str(state.get("source") or "single_query"),
                    question=str(state.get("question") or ""),
                    semantic_raw=state.get("semantic_raw") or {},
                    result_manifest_ref=None,
                    data_profile_dict=None,
                    query_id=state.get("query_id"),
                ),
            )
            return updates

        try:
            workspace = prepare_insight_workspace(
                result_manifest_ref=result_manifest_ref,
                session_id=state.get("session_id"),
                artifact_root_dir=state.get("artifact_root_dir"),
            )
            manifest = workspace.manifest
            profile_ref = ""
            for profile in manifest.get("profiles") or []:
                if isinstance(profile, dict) and profile.get("name") == "data_profile":
                    profile_ref = str(profile.get("path") or "")
                    break
            if not profile_ref:
                raise ValueError("answer_graph workspace 缺少 data_profile 引用")

            data_profile_dict = load_json_artifact(
                profile_ref,
                artifact_root_dir=workspace.artifact_root_dir,
            )
            updates["workspace"] = workspace
            updates.setdefault(
                "evidence_bundle_dict",
                build_result_evidence_bundle(
                    source=str(state.get("source") or "single_query"),
                    question=str(state.get("question") or ""),
                    semantic_raw=state.get("semantic_raw") or {},
                    result_manifest_ref=result_manifest_ref,
                    data_profile_dict=data_profile_dict,
                    query_id=state.get("query_id"),
                ),
            )
            return updates
        except FileNotFoundError as exc:
            logger.warning("answer_graph artifact 缺失，回退注入式 answer 链路: %s", exc)
            updates.update({
                "result_manifest_ref": None,
                "workspace": None,
            })
            updates.setdefault(
                "evidence_bundle_dict",
                build_result_evidence_bundle(
                    source=str(state.get("source") or "single_query"),
                    question=str(state.get("question") or ""),
                    semantic_raw=state.get("semantic_raw") or {},
                    result_manifest_ref=None,
                    data_profile_dict=None,
                    query_id=state.get("query_id"),
                ),
            )
            return updates

    async def _run_insight_node(self, state: AnswerGraphState) -> dict[str, Any]:
        if state.get("insight_output_dict"):
            return {}

        workspace = state.get("workspace")
        result_manifest_ref = str(state.get("result_manifest_ref") or "").strip() or None
        evidence_bundle_dict = dict(state.get("evidence_bundle_dict") or {})

        await self._notify_stage(state, stage="generating", status="running")
        try:
            started = asyncio.get_running_loop().time()
            if (
                workspace is None
                and not result_manifest_ref
                and str(state.get("source") or "") != "single_query"
            ):
                bundle_insight_output = build_bundle_insight_output(evidence_bundle_dict)
                elapsed_ms = (asyncio.get_running_loop().time() - started) * 1000
                return {
                    "insight_output_dict": bundle_insight_output,
                    "insight_ms": elapsed_ms,
                    "insight_findings_count": len(
                        bundle_insight_output.get("findings") or []
                    ),
                }
            insight_output = await self._invoke_insight_agent(
                workspace=workspace,
                result_manifest_ref=result_manifest_ref,
                semantic_output_dict=state.get("semantic_raw") or {},
                analysis_depth=state.get("analysis_depth") or "detailed",
                session_id=state.get("session_id"),
                artifact_root_dir=state.get("artifact_root_dir"),
                on_token=state.get("on_token"),
                on_thinking=state.get("on_thinking"),
            )
            elapsed_ms = (asyncio.get_running_loop().time() - started) * 1000
            return {
                "insight_output_dict": insight_output.model_dump(),
                "insight_ms": elapsed_ms,
                "insight_findings_count": len(getattr(insight_output, "findings", []) or []),
            }
        except Exception as exc:
            logger.warning("answer_graph 洞察生成失败: %s", exc)
            return {"insight_failed": True}
        finally:
            await self._notify_stage(state, stage="generating", status="completed")

    def _route_after_insight(self, state: AnswerGraphState) -> str:
        if not state.get("insight_output_dict"):
            return END
        return "run_replanner"

    async def _run_replanner_node(self, state: AnswerGraphState) -> dict[str, Any]:
        await self._notify_stage(state, stage="replanning", status="running")
        try:
            started = asyncio.get_running_loop().time()
            evidence_bundle_dict = dict(state.get("evidence_bundle_dict") or {})
            insight_output_dict = dict(state.get("insight_output_dict") or {})
            if insight_output_dict:
                evidence_bundle_dict.update({
                    "insight_summary": str(insight_output_dict.get("summary") or "").strip(),
                    "insight_findings_count": len(insight_output_dict.get("findings") or []),
                })
            replan_decision = await self._invoke_replanner_agent(
                insight_output_dict=insight_output_dict,
                semantic_output_dict=state.get("semantic_raw") or {},
                evidence_bundle_dict=evidence_bundle_dict,
                conversation_history=state.get("conversation_history") or [],
                replan_history=state.get("replan_history") or [],
                analysis_depth=state.get("analysis_depth") or "detailed",
                field_semantic=state.get("field_semantic"),
                on_token=state.get("on_token"),
                on_thinking=state.get("on_thinking"),
            )
            elapsed_ms = (asyncio.get_running_loop().time() - started) * 1000
            decision_dump = (
                replan_decision.model_dump()
                if hasattr(replan_decision, "model_dump")
                else dict(replan_decision or {})
            )
            projection = build_replan_projection(
                replan_decision=decision_dump,
                source=state.get("source") or "single_query",
                replan_mode=state.get("replan_mode") or "user_select",
                current_question=state.get("question") or "",
                replan_history=state.get("replan_history") or [],
            )
            return {
                "evidence_bundle_dict": evidence_bundle_dict,
                "replan_decision": decision_dump,
                "replan_projection": projection,
                "replanner_ms": elapsed_ms,
                "replanner_should_replan": bool(decision_dump.get("should_replan", False)),
                "replanner_suggested_questions_count": len(
                    decision_dump.get("suggested_questions") or []
                ),
                "replanner_candidate_questions_count": len(
                    projection.get("candidate_questions") or []
                ),
            }
        except Exception as exc:
            logger.warning("answer_graph 重规划失败: %s", exc)
            return {"replanner_failed": True}
        finally:
            await self._notify_stage(state, stage="replanning", status="completed")

    def _compile_graph(self) -> Any:
        graph = StateGraph(AnswerGraphState)
        graph.add_node("prepare", self._prepare_node)
        graph.add_node("run_insight", self._run_insight_node)
        graph.add_node("run_replanner", self._run_replanner_node)
        graph.add_edge(START, "prepare")
        graph.add_edge("prepare", "run_insight")
        graph.add_conditional_edges(
            "run_insight",
            self._route_after_insight,
            {
                "run_replanner": "run_replanner",
                END: END,
            },
        )
        graph.add_edge("run_replanner", END)
        return graph.compile()


__all__ = [
    "AnswerGraphRunner",
    "AnswerGraphState",
]
