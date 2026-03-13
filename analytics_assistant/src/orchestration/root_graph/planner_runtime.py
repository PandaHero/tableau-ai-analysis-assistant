# -*- coding: utf-8 -*-
"""root_graph 内部使用的 planner 执行控制流。

这里专门承接复杂问题的多步规划执行：
- planner 的运行状态由 root_graph 持有并进入 checkpoint
- step 级语义解析仍复用 semantic_graph
- query 与 answer 阶段继续复用已有 query_graph / answer_graph

该模块故意不暴露独立的公共 API；它只是 root_graph 的内部执行器。
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Awaitable, Callable, Optional

from langgraph.types import Command

from analytics_assistant.src.agents.semantic_parser.schemas.planner import (
    AnalysisPlan,
    AnalysisPlanStep,
    EvidenceContext,
    PlanStepType,
)
from analytics_assistant.src.infra.config import get_config
from analytics_assistant.src.orchestration.answer_graph import (
    invoke_insight_agent,
    invoke_replanner_agent,
    serialize_insight_payload,
)
from analytics_assistant.src.orchestration.query_graph import (
    QueryGraphRunner,
    build_high_risk_interrupt_payload,
    execute_semantic_query,
)
from analytics_assistant.src.orchestration.semantic_graph.service import (
    build_semantic_summary,
)
from analytics_assistant.src.orchestration.workflow.context import PreparedContextSnapshot
from analytics_assistant.src.orchestration.workflow.planner_support import (
    append_step_artifact,
    build_evidence_bundle_dict,
    build_followup_history,
    build_initial_evidence_context,
    build_query_step_summary,
    build_step_insight_output,
    build_synthesis_step_summary,
    extract_insight_key_findings,
    get_primary_plan_step,
    hydrate_step_intent_with_evidence,
    serialize_plan_step,
)
from analytics_assistant.src.orchestration.workflow.semantic_guard import (
    resolve_compiler_semantic_input,
)
from analytics_assistant.src.platform.tableau.adapter import TableauAdapter
from analytics_assistant.src.platform.tableau.client import VizQLClient

logger = logging.getLogger(__name__)

_ROOT_SEMANTIC_INTERRUPT_TYPES = {
    "missing_slot",
    "value_confirm",
}
_DEFAULT_MAX_PARALLEL_STEPS = 2
_DEFAULT_MAX_TOTAL_STEPS = 8
_DEFAULT_MAX_QUERY_STEPS = 6
_DEFAULT_MAX_RUNTIME_MS = 45000
_DEFAULT_SCREENING_TOP_K = 2


def _get_planner_runtime_limits() -> dict[str, int]:
    """读取 planner 运行时限制，避免复杂问题在单轮内无界并行。"""
    try:
        planner_config = (
            get_config()
            .get("root_graph", {})
            .get("planner", {})
        )
    except Exception as exc:
        logger.warning("加载 root_graph planner 配置失败，回退默认限制: %s", exc)
        planner_config = {}

    try:
        max_parallel_steps = int(
            planner_config.get("max_parallel_steps", _DEFAULT_MAX_PARALLEL_STEPS)
        )
    except (TypeError, ValueError):
        max_parallel_steps = _DEFAULT_MAX_PARALLEL_STEPS
    try:
        max_total_steps = int(
            planner_config.get("max_total_steps", _DEFAULT_MAX_TOTAL_STEPS)
        )
    except (TypeError, ValueError):
        max_total_steps = _DEFAULT_MAX_TOTAL_STEPS
    try:
        max_query_steps = int(
            planner_config.get("max_query_steps", _DEFAULT_MAX_QUERY_STEPS)
        )
    except (TypeError, ValueError):
        max_query_steps = _DEFAULT_MAX_QUERY_STEPS
    try:
        max_runtime_ms = int(
            planner_config.get("max_runtime_ms", _DEFAULT_MAX_RUNTIME_MS)
        )
    except (TypeError, ValueError):
        max_runtime_ms = _DEFAULT_MAX_RUNTIME_MS
    try:
        screening_top_k = int(
            planner_config.get("screening_top_k", _DEFAULT_SCREENING_TOP_K)
        )
    except (TypeError, ValueError):
        screening_top_k = _DEFAULT_SCREENING_TOP_K

    return {
        "max_parallel_steps": max(1, max_parallel_steps),
        "max_total_steps": max(1, max_total_steps),
        "max_query_steps": max(1, max_query_steps),
        "max_runtime_ms": max(1, max_runtime_ms),
        "screening_top_k": max(1, screening_top_k),
    }


def _build_planner_stop_state(
    round_projection: dict[str, Any],
    *,
    complete_payload: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """统一 planner 提前结束时的 root state 落盘结构。"""
    return {
        **round_projection,
        "planner_state": None,
        "pending_interrupt_type": None,
        "pending_interrupt_payload": None,
        "root_resume_value": None,
        "semantic_resume_value": None,
        "resume_target": None,
        "continue_with_question": None,
        "complete_payload": complete_payload,
    }


def _build_planner_state(
    *,
    analysis_plan: AnalysisPlan,
    current_question: str,
) -> dict[str, Any]:
    """初始化可 checkpoint 的 planner 进度状态。"""
    return {
        "analysis_plan": analysis_plan.model_dump(mode="json"),
        "planner_event_emitted": False,
        "initial_parse_emitted": False,
        "evidence_context": build_initial_evidence_context(
            current_question
        ).model_dump(mode="json"),
        "completed_steps": [],
        "completed_step_ids": [],
        "pending_step": None,
        "pending_step_parse_result": None,
    }


def _load_planner_state(
    *,
    state: dict[str, Any],
    analysis_plan: AnalysisPlan,
    current_question: str,
) -> dict[str, Any]:
    """恢复 planner 状态；首次进入时创建新状态。"""
    raw = state.get("planner_state")
    if not isinstance(raw, dict):
        return _build_planner_state(
            analysis_plan=analysis_plan,
            current_question=current_question,
        )

    planner_state = dict(raw)
    planner_state.setdefault(
        "analysis_plan",
        analysis_plan.model_dump(mode="json"),
    )
    planner_state.setdefault("planner_event_emitted", False)
    planner_state.setdefault("initial_parse_emitted", False)
    planner_state.setdefault(
        "evidence_context",
        build_initial_evidence_context(current_question).model_dump(mode="json"),
    )
    planner_state.setdefault("completed_steps", [])
    planner_state.setdefault("completed_step_ids", [])
    planner_state.setdefault("pending_step", None)
    planner_state.setdefault("pending_step_parse_result", None)
    return planner_state


def _build_planner_event(analysis_plan: AnalysisPlan) -> dict[str, Any]:
    total_steps = len(analysis_plan.sub_questions)
    return {
        "type": "planner",
        "planMode": analysis_plan.plan_mode.value,
        "goal": analysis_plan.goal or "",
        "executionStrategy": analysis_plan.execution_strategy,
        "reasoningFocus": list(analysis_plan.reasoning_focus or []),
        "steps": [
            serialize_plan_step(step, index=index, total=total_steps)
            for index, step in enumerate(analysis_plan.sub_questions, start=1)
        ],
    }


def _build_plan_step_clarification_event(
    *,
    interrupt_type: str,
    interrupt_payload: dict[str, Any],
    step_payload: dict[str, Any],
) -> dict[str, Any]:
    """把 planner step 中断投影成稳定事件，便于前端直接展示。"""
    event: dict[str, Any] = {
        "type": "plan_step",
        "status": "clarification",
        "step": step_payload,
        "interrupt_type": interrupt_type,
        "message": interrupt_payload.get("message", ""),
        "source": interrupt_payload.get("source", ""),
    }
    if interrupt_type == "value_confirm":
        event["field"] = interrupt_payload.get("field")
        event["requested_value"] = interrupt_payload.get("requested_value")
        event["candidates"] = interrupt_payload.get("candidates", [])
        event["options"] = interrupt_payload.get("candidates", [])
    elif interrupt_type == "missing_slot":
        event["slot_name"] = interrupt_payload.get("slot_name")
        event["options"] = interrupt_payload.get("options", [])
    elif interrupt_type == "high_risk_query_confirm":
        event["summary"] = interrupt_payload.get("summary", "")
    return event


async def _run_plan_step_insight(
    *,
    semantic_raw: dict[str, Any],
    step_payload: dict[str, Any],
    result_manifest_ref: Optional[str],
    table_data: Optional[dict[str, Any]],
    semantic_summary: Optional[dict[str, Any]],
    session_id: Optional[str],
    analysis_depth: str,
    on_token: Callable[[str], Awaitable[None]],
    on_thinking: Callable[[str], Awaitable[None]],
) -> dict[str, Any]:
    """优先复用真实 InsightAgent；失败时退回确定性摘要。"""
    summary_text = build_query_step_summary(
        step_payload,
        semantic_summary or {},
        table_data or {},
    )
    fallback_output = build_step_insight_output(
        step_payload,
        summary_text,
        semantic_summary,
        table_data,
    )
    normalized_manifest_ref = str(result_manifest_ref or "").strip() or None
    try:
        insight_output = await invoke_insight_agent(
            result_manifest_ref=normalized_manifest_ref,
            semantic_output_dict=semantic_raw,
            analysis_depth=analysis_depth,
            session_id=session_id,
            on_token=on_token,
            on_thinking=on_thinking,
        )
        if hasattr(insight_output, "model_dump"):
            return insight_output.model_dump()
        return dict(insight_output or {})
    except Exception as exc:
        logger.warning("planner step 洞察生成失败，退回确定性摘要: %s", exc)
        return fallback_output


async def execute_planner_round(
    runner: Any,
    *,
    state: dict[str, Any],
    writer: Callable[[dict[str, Any]], None],
    analysis_plan: AnalysisPlan,
    parse_result: dict[str, Any],
    current_question: str,
) -> dict[str, Any]:
    """在 root_graph 内部执行复杂问题 planner，统一中断与恢复。"""
    query_graph_runner = QueryGraphRunner(
        risk_evaluator=build_high_risk_interrupt_payload,
        query_executor=execute_semantic_query,
        request_id=state.get("request_id") or None,
    )
    round_projection = runner._empty_round_projection()
    language = str(state.get("language") or "zh")
    planner_state = _load_planner_state(
        state=state,
        analysis_plan=analysis_plan,
        current_question=current_question,
    )
    completed_steps = list(planner_state.get("completed_steps") or [])
    completed_step_ids = {
        str(step_id)
        for step_id in (planner_state.get("completed_step_ids") or [])
        if str(step_id).strip()
    }
    planner_limits = _get_planner_runtime_limits()
    planner_started_at = time.perf_counter()
    evidence_context = EvidenceContext.model_validate(
        planner_state.get("evidence_context")
        or build_initial_evidence_context(current_question).model_dump(mode="json")
    )
    total_steps = len(analysis_plan.sub_questions)
    query_steps_total = sum(
        1 for step in analysis_plan.sub_questions
        if step.step_type != PlanStepType.SYNTHESIS
    )
    # planner 路径恢复后仍应先投影统一 stage 事件，保证复杂问题与单查询路径的展示语义一致。
    runner._emit_stage_event(
        writer,
        stage="executing",
        language=language,
        status="running",
    )

    def _fail_planner_run(*, code: str, message: str) -> dict[str, Any]:
        writer({
            "type": "error",
            "error": message,
            "error_code": code,
        })
        runner._emit_projected_event(
            writer,
            round_projection,
            runner._build_complete_event(state, status="error", reason=code),
        )
        return _build_planner_stop_state(
            round_projection,
            complete_payload={
                "status": "error",
                "reason": code,
            },
        )

    def _check_runtime_budget() -> Optional[dict[str, Any]]:
        elapsed_ms = int((time.perf_counter() - planner_started_at) * 1000)
        if elapsed_ms <= planner_limits["max_runtime_ms"]:
            return None
        return _fail_planner_run(
            code="planner_runtime_budget_exceeded",
            message=(
                "planner exceeded runtime budget: "
                f"{elapsed_ms}ms > {planner_limits['max_runtime_ms']}ms"
            ),
        )

    if total_steps > planner_limits["max_total_steps"]:
        return _fail_planner_run(
            code="planner_step_limit_exceeded",
            message=(
                "planner exceeds max_total_steps: "
                f"{total_steps} > {planner_limits['max_total_steps']}"
            ),
        )
    if query_steps_total > planner_limits["max_query_steps"]:
        return _fail_planner_run(
            code="planner_query_step_limit_exceeded",
            message=(
                "planner exceeds max_query_steps: "
                f"{query_steps_total} > {planner_limits['max_query_steps']}"
            ),
        )

    if not planner_state.get("planner_event_emitted"):
        writer(_build_planner_event(analysis_plan))
        planner_state["planner_event_emitted"] = True

    pending_step_raw = planner_state.get("pending_step")
    pending_step = dict(pending_step_raw) if isinstance(pending_step_raw, dict) else None

    primary_index, primary_step = get_primary_plan_step(analysis_plan)
    primary_step_payload: Optional[dict[str, Any]] = None
    if primary_index is not None and primary_step is not None:
        primary_step_payload = serialize_plan_step(
            primary_step,
            index=primary_index,
            total=total_steps,
        )

    if not planner_state.get("initial_parse_emitted"):
        runner._emit_projected_event(
            writer,
            round_projection,
            runner._build_parse_result_event(
                parse_result,
                state=state,
                plan_step=primary_step_payload,
            ),
        )
        planner_state["initial_parse_emitted"] = True

    prepared_context_snapshot = state.get("prepared_context_snapshot")
    if prepared_context_snapshot is None:
        raise ValueError("planner 执行前缺少 prepared_context_snapshot")

    datasource_luid = str(
        state.get("datasource_luid")
        or PreparedContextSnapshot.model_validate(prepared_context_snapshot).datasource_luid
        or ""
    ).strip()
    if not datasource_luid:
        raise ValueError("planner 执行前 datasource_luid 不能为空")

    async def _emit_token(token: str) -> None:
        writer({"type": "token", "content": token})

    async def _emit_thinking(thinking: str) -> None:
        writer({"type": "thinking_token", "content": thinking})

    async with VizQLClient() as vizql_client:
        ctx = await runner._build_runtime_context(
            prepared_context_snapshot,
            platform_adapter=TableauAdapter(vizql_client=vizql_client),
        )
        graph = await runner._semantic_graph_runner.acompile_graph()

        def _persist_step_result(step_result: dict[str, Any]) -> None:
            nonlocal evidence_context
            completed_steps.append({
                "step": step_result["step_payload"],
                "summary_text": step_result["summary_text"],
            })
            step_id = step_result["step"].step_id or step_result["step_payload"]["stepId"]
            completed_step_ids.add(step_id)
            evidence_context = append_step_artifact(
                evidence_context,
                step_payload=step_result["step_payload"],
                query_id=step_result["parse_result"].get("query_id"),
                restated_question=(
                    step_result["parse_result"].get("semantic_output") or {}
                ).get("restated_question"),
                table_data=step_result.get("table_data"),
                summary_text=step_result["summary_text"],
                semantic_summary=step_result.get("semantic_summary"),
                key_findings=extract_insight_key_findings(
                    step_result.get("insight_output")
                ),
                evidence_context_before_step=step_result.get(
                    "evidence_context_before_step"
                ),
            )

        async def _run_planner_step_semantic(
            *,
            step: AnalysisPlanStep,
            step_index: int,
            resume_value: Any = None,
            snapshot_completed_steps: Optional[list[dict[str, Any]]] = None,
            snapshot_evidence_context: Optional[EvidenceContext] = None,
        ) -> dict[str, Any]:
            effective_evidence_context = snapshot_evidence_context or evidence_context
            effective_step = hydrate_step_intent_with_evidence(
                step,
                effective_evidence_context,
                screening_top_k=planner_limits.get(
                    "screening_top_k",
                    _DEFAULT_SCREENING_TOP_K,
                ),
            )
            step_payload = serialize_plan_step(
                effective_step,
                index=step_index,
                total=total_steps,
            )
            writer({
                "type": "plan_step",
                "status": "running",
                "step": step_payload,
                "message": f"正在执行规划步骤 {step_index}/{total_steps}",
            })

            config = runner._semantic_graph_runner.build_config(
                ctx=ctx,
                datasource_luid=datasource_luid,
                session_id=state.get("session_id"),
                request_id=state.get("request_id"),
                run_id=state.get("request_id"),
                on_token=_emit_token,
                on_thinking=_emit_thinking,
                thread_suffix=f":plan-step-{step_index}",
            )

            if resume_value is not None:
                graph_input: Any = Command(resume=resume_value)
            else:
                followup_history = build_followup_history(
                    state.get("history"),
                    current_question,
                    list(snapshot_completed_steps or completed_steps),
                )
                graph_input = {
                    "question": effective_step.question,
                    "datasource_luid": datasource_luid,
                    "history": followup_history,
                    "chat_history": followup_history,
                    "current_step_intent": {
                        **effective_step.model_dump(mode="json"),
                        "step_id": effective_step.step_id or f"step-{step_index}",
                        "goal": effective_step.goal or effective_step.purpose,
                    },
                    "evidence_context": (
                        effective_evidence_context
                    ).model_dump(mode="json"),
                    "current_time": ctx.current_time,
                    "language": str(state.get("language") or "zh"),
                    "analysis_depth": str(state.get("analysis_depth") or "detailed"),
                }

            async for event in runner._semantic_graph_runner.astream(
                graph=graph,
                graph_input=graph_input,
                config=config,
            ):
                if "__interrupt__" in event:
                    interrupt_event = runner._build_langgraph_interrupt_event(
                        event.get("__interrupt__"),
                    )
                    interrupt_type = str(interrupt_event.get("interrupt_type") or "").strip()
                    if interrupt_type in _ROOT_SEMANTIC_INTERRUPT_TYPES:
                        interrupt_payload = dict(interrupt_event.get("payload") or {})
                        interrupt_payload["resume_strategy"] = "root_graph_native"
                        writer(_build_plan_step_clarification_event(
                            interrupt_type=interrupt_type,
                            interrupt_payload=interrupt_payload,
                            step_payload=step_payload,
                        ))
                        return {
                            "status": "interrupt",
                            "state_update": {
                                **round_projection,
                                "planner_state": {
                                    "pending_step": {
                                        "index": step_index,
                                        "step": effective_step.model_dump(mode="json"),
                                        "phase": "semantic",
                                    },
                                    "pending_step_parse_result": None,
                                },
                                "pending_interrupt_type": interrupt_type,
                                "pending_interrupt_payload": interrupt_payload,
                                "resume_target": "execute_round",
                                "root_resume_value": None,
                                "continue_with_question": None,
                            },
                        }
                    raise ValueError(
                        f"unsupported planner semantic interrupt_type: {interrupt_type}"
                    )

                for node_output in event.values():
                    if not isinstance(node_output, dict):
                        continue
                    if node_output.get("needs_clarification"):
                        raise ValueError(
                            "planner step emitted legacy clarification output; "
                            "use native LangGraph interrupt() instead"
                        )
                    step_parse_result = node_output.get("parse_result")
                    if isinstance(step_parse_result, dict) and step_parse_result.get("success"):
                        runner._emit_projected_event(
                            writer,
                            round_projection,
                            runner._build_parse_result_event(
                                step_parse_result,
                                state=state,
                                plan_step=step_payload,
                            ),
                        )
                        return {
                            "status": "success",
                            "step": effective_step,
                            "step_payload": step_payload,
                            "parse_result": step_parse_result,
                        }

            writer({
                "type": "plan_step",
                "status": "error",
                "step": step_payload,
                "error": "planner step did not produce an executable parse result",
            })
            return {"status": "error"}

        async def _execute_planner_step_from_parse_result(
            *,
            step: AnalysisPlanStep,
            step_index: int,
            step_parse_result: dict[str, Any],
            evidence_context_before_step: Optional[EvidenceContext] = None,
        ) -> dict[str, Any]:
            effective_step = hydrate_step_intent_with_evidence(
                step,
                evidence_context_before_step or evidence_context,
                screening_top_k=planner_limits.get(
                    "screening_top_k",
                    _DEFAULT_SCREENING_TOP_K,
                ),
            )
            step_payload = serialize_plan_step(
                effective_step,
                index=step_index,
                total=total_steps,
            )
            semantic_raw, compiler_error = resolve_compiler_semantic_input(step_parse_result)
            if compiler_error:
                writer({
                    "type": "plan_step",
                    "status": "error",
                    "step": step_payload,
                    "error": compiler_error,
                })
                return {"status": "error"}
            semantic_summary = build_semantic_summary(semantic_raw)

            query_state = await query_graph_runner.run(
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
                high_risk_payload = {
                    **dict(high_risk_payload),
                    "resume_strategy": "root_graph_native",
                }
                writer(_build_plan_step_clarification_event(
                    interrupt_type="high_risk_query_confirm",
                    interrupt_payload=high_risk_payload,
                    step_payload=step_payload,
                ))
                return {
                    "status": "interrupt",
                    "state_update": {
                        **round_projection,
                        "planner_state": {
                            "pending_step": {
                                "index": step_index,
                                "step": effective_step.model_dump(mode="json"),
                                "phase": "query",
                            },
                            "pending_step_parse_result": step_parse_result,
                        },
                        "pending_interrupt_type": "high_risk_query_confirm",
                        "pending_interrupt_payload": high_risk_payload,
                        "resume_target": "execute_round",
                        "root_resume_value": None,
                        "continue_with_question": None,
                    },
                }

            if bool(query_state.get("query_failed")):
                writer({
                    "type": "plan_step",
                    "status": "error",
                    "step": step_payload,
                    "error": str(query_state.get("query_error") or "query execution failed"),
                })
                return {"status": "error"}

            summary_text = build_query_step_summary(
                step_payload,
                semantic_summary or {},
                query_state.get("table_data") or {},
            )
            writer({
                "type": "plan_step",
                "status": "completed",
                "step": step_payload,
                "queryId": step_parse_result.get("query_id", ""),
                "semanticSummary": semantic_summary or {},
                "summary": summary_text,
            })
            runner._emit_projected_event(
                writer,
                round_projection,
                {
                    "type": "data",
                    "tableData": query_state.get("table_data"),
                    "truncated": bool(
                        query_state.get("query_execution", {}).get("truncated", False)
                    ),
                    "result_manifest_ref": query_state.get("result_manifest_ref"),
                    "profiles_ref": query_state.get("profiles_ref"),
                    "chunks_ref": query_state.get("chunks_ref"),
                    "planStep": step_payload,
                    "summary": summary_text,
                },
            )

            insight_output_dict = await _run_plan_step_insight(
                semantic_raw=semantic_raw,
                step_payload=step_payload,
                result_manifest_ref=query_state.get("result_manifest_ref"),
                table_data=query_state.get("table_data"),
                semantic_summary=semantic_summary,
                session_id=state.get("session_id"),
                analysis_depth=str(state.get("analysis_depth") or "detailed"),
                on_token=_emit_token,
                on_thinking=_emit_thinking,
            )
            runner._emit_projected_event(
                writer,
                round_projection,
                {
                    "type": "insight",
                    "source": "plan_step",
                    **serialize_insight_payload(insight_output_dict),
                    "planStep": step_payload,
                },
            )

            return {
                "status": "success",
                "step": effective_step,
                "step_payload": step_payload,
                "parse_result": step_parse_result,
                "summary_text": summary_text,
                "table_data": query_state.get("table_data"),
                "semantic_summary": semantic_summary,
                "insight_output": insight_output_dict,
                "evidence_context_before_step": (
                    evidence_context_before_step or evidence_context
                ),
            }

        async def _run_followup_query_step(
            index: int,
            step: AnalysisPlanStep,
            *,
            resume_value: Any = None,
            existing_parse_result: Optional[dict[str, Any]] = None,
            snapshot_completed_steps: Optional[list[dict[str, Any]]] = None,
            snapshot_evidence_context: Optional[EvidenceContext] = None,
        ) -> dict[str, Any]:
            effective_evidence_context = snapshot_evidence_context or evidence_context
            step_parse_result = existing_parse_result
            if step_parse_result is None:
                semantic_result = await _run_planner_step_semantic(
                    step=step,
                    step_index=index,
                    resume_value=resume_value,
                    snapshot_completed_steps=snapshot_completed_steps,
                    snapshot_evidence_context=effective_evidence_context,
                )
                if semantic_result.get("status") != "success":
                    return semantic_result
                step_parse_result = semantic_result.get("parse_result")
                step = semantic_result.get("step", step)

            if not isinstance(step_parse_result, dict) or not step_parse_result.get("success"):
                return {"status": "error"}

            return await _execute_planner_step_from_parse_result(
                step=step,
                step_index=index,
                step_parse_result=step_parse_result,
                evidence_context_before_step=effective_evidence_context,
            )

        budget_state = _check_runtime_budget()
        if budget_state is not None:
            return budget_state

        if pending_step is not None:
            pending_index = int(pending_step.get("index") or 0)
            pending_step_model = AnalysisPlanStep.model_validate(
                pending_step.get("step") or {}
            )
            pending_parse_result = planner_state.get("pending_step_parse_result")
            pending_phase = str(pending_step.get("phase") or "semantic")
            resume_value = (
                state.get("semantic_resume_value")
                if pending_phase == "semantic"
                else None
            )
            pending_result = await _run_followup_query_step(
                pending_index,
                pending_step_model,
                resume_value=resume_value,
                existing_parse_result=(
                    pending_parse_result if pending_phase == "query" else None
                ),
            )
            if pending_result.get("status") == "interrupt":
                next_planner_state = {
                    **planner_state,
                    **dict(pending_result["state_update"].pop("planner_state")),
                    "completed_steps": completed_steps,
                    "completed_step_ids": sorted(completed_step_ids),
                    "evidence_context": evidence_context.model_dump(mode="json"),
                }
                return {
                    **pending_result["state_update"],
                    "planner_state": next_planner_state,
                    "semantic_resume_value": None,
                }
            if pending_result.get("status") != "success":
                runner._emit_projected_event(
                    writer,
                    round_projection,
                    runner._build_complete_event(state, status="ok"),
                )
                return {
                    **round_projection,
                    "planner_state": None,
                    "pending_interrupt_type": None,
                    "pending_interrupt_payload": None,
                    "root_resume_value": None,
                    "semantic_resume_value": None,
                    "resume_target": None,
                    "continue_with_question": None,
                }
            _persist_step_result(pending_result)
            planner_state["pending_step"] = None
            planner_state["pending_step_parse_result"] = None
        elif primary_index is not None and primary_step is not None:
            primary_step_id = primary_step.step_id or f"step-{primary_index}"
            if primary_step_id not in completed_step_ids:
                writer({
                    "type": "plan_step",
                    "status": "running",
                    "step": primary_step_payload,
                    "message": f"正在执行规划步骤 {primary_index}/{total_steps}",
                })
                primary_result = await _execute_planner_step_from_parse_result(
                    step=primary_step,
                    step_index=primary_index,
                    step_parse_result=parse_result,
                    evidence_context_before_step=evidence_context.model_copy(deep=True),
                )
                if primary_result.get("status") == "interrupt":
                    next_planner_state = {
                        **planner_state,
                        **dict(primary_result["state_update"].pop("planner_state")),
                        "completed_steps": completed_steps,
                        "completed_step_ids": sorted(completed_step_ids),
                        "evidence_context": evidence_context.model_dump(mode="json"),
                    }
                    return {
                        **primary_result["state_update"],
                        "planner_state": next_planner_state,
                        "semantic_resume_value": None,
                    }
                if primary_result.get("status") != "success":
                    runner._emit_projected_event(
                        writer,
                        round_projection,
                        runner._build_complete_event(state, status="ok"),
                    )
                    return _build_planner_stop_state(round_projection)
                _persist_step_result(primary_result)

        remaining_steps: list[tuple[int, AnalysisPlanStep]] = [
            (index, step)
            for index, step in enumerate(analysis_plan.sub_questions, start=1)
            if (step.step_id or f"step-{index}") not in completed_step_ids
        ]

        while remaining_steps:
            budget_state = _check_runtime_budget()
            if budget_state is not None:
                return budget_state
            ready_steps: list[tuple[int, AnalysisPlanStep]] = []
            blocked_steps: list[tuple[int, AnalysisPlanStep]] = []
            for index, step in remaining_steps:
                required_ids = set(step.depends_on or [])
                if required_ids.issubset(completed_step_ids):
                    ready_steps.append((index, step))
                else:
                    blocked_steps.append((index, step))

            if not ready_steps:
                logger.warning("planner 依赖无法继续推进，剩余步骤=%s", len(remaining_steps))
                break

            query_ready = [
                (index, step)
                for index, step in ready_steps
                if step.step_type != PlanStepType.SYNTHESIS
            ]
            synthesis_ready = [
                (index, step)
                for index, step in ready_steps
                if step.step_type == PlanStepType.SYNTHESIS
            ]

            if query_ready:
                should_parallel = (
                    analysis_plan.execution_strategy == "parallel"
                    and len(query_ready) > 1
                )
                if should_parallel:
                    max_parallel_steps = planner_limits["max_parallel_steps"]
                    for wave_start in range(0, len(query_ready), max_parallel_steps):
                        query_wave = query_ready[wave_start: wave_start + max_parallel_steps]
                        snapshot_completed = list(completed_steps)
                        snapshot_evidence = evidence_context.model_copy(deep=True)
                        task_results = await asyncio.gather(
                            *[
                                _run_followup_query_step(
                                    index,
                                    step,
                                    snapshot_completed_steps=snapshot_completed,
                                    snapshot_evidence_context=snapshot_evidence,
                                )
                                for index, step in query_wave
                            ],
                            return_exceptions=True,
                        )
                        pending_interrupt_update: Optional[dict[str, Any]] = None
                        for (index, step), task_result in zip(query_wave, task_results):
                            if isinstance(task_result, Exception):
                                logger.warning(
                                    "planner 并行步骤执行失败: step=%s, error=%s",
                                    step.step_id or f"step-{index}",
                                    task_result,
                                )
                                continue
                            if task_result.get("status") == "success":
                                _persist_step_result(task_result)
                                continue
                            if (
                                task_result.get("status") == "interrupt"
                                and pending_interrupt_update is None
                            ):
                                pending_interrupt_update = dict(task_result["state_update"])
                        if pending_interrupt_update is not None:
                            next_planner_state = {
                                **planner_state,
                                **dict(pending_interrupt_update.pop("planner_state")),
                                "completed_steps": completed_steps,
                                "completed_step_ids": sorted(completed_step_ids),
                                "evidence_context": evidence_context.model_dump(mode="json"),
                            }
                            return {
                                **pending_interrupt_update,
                                "planner_state": next_planner_state,
                                "semantic_resume_value": None,
                            }
                else:
                    for index, step in query_ready:
                        task_result = await _run_followup_query_step(index, step)
                        if task_result.get("status") == "interrupt":
                            next_planner_state = {
                                **planner_state,
                                **dict(task_result["state_update"].pop("planner_state")),
                                "completed_steps": completed_steps,
                                "completed_step_ids": sorted(completed_step_ids),
                                "evidence_context": evidence_context.model_dump(mode="json"),
                            }
                            return {
                                **task_result["state_update"],
                                "planner_state": next_planner_state,
                                "semantic_resume_value": None,
                            }
                        if task_result.get("status") != "success":
                            runner._emit_projected_event(
                                writer,
                                round_projection,
                                runner._build_complete_event(state, status="ok"),
                            )
                            return _build_planner_stop_state(round_projection)
                        _persist_step_result(task_result)

            for index, step in synthesis_ready:
                budget_state = _check_runtime_budget()
                if budget_state is not None:
                    return budget_state
                step_payload = serialize_plan_step(step, index=index, total=total_steps)
                synthesis_summary = build_synthesis_step_summary(
                    current_question,
                    completed_steps,
                )
                writer({
                    "type": "plan_step",
                    "status": "completed",
                    "step": step_payload,
                    "summary": synthesis_summary,
                    "evidenceCount": len(completed_steps),
                })
                completed_steps.append({
                    "step": step_payload,
                    "summary_text": synthesis_summary,
                })
                completed_step_ids.add(step.step_id or f"step-{index}")
                evidence_context = append_step_artifact(
                    evidence_context,
                    step_payload=step_payload,
                    summary_text=synthesis_summary,
                    key_findings=[synthesis_summary],
                    open_questions=analysis_plan.risk_flags,
                )

            remaining_steps = blocked_steps

        budget_state = _check_runtime_budget()
        if budget_state is not None:
            return budget_state

        planner_history = build_followup_history(
            state.get("history"),
            current_question,
            completed_steps,
        )
        answer_update = await runner._run_answer_graph_round(
            state=state,
            writer=writer,
            round_projection=round_projection,
                source="planner_synthesis",
                question=current_question,
                semantic_raw=parse_result.get("semantic_output") or {},
                result_manifest_ref=None,
                evidence_bundle_dict=build_evidence_bundle_dict(
                current_question,
                evidence_context,
                source="planner_synthesis",
                query_id=str(parse_result.get("query_id") or "").strip() or None,
                ),
                field_semantic=ctx.field_semantic,
                query_id=str(parse_result.get("query_id") or "").strip() or None,
                conversation_history=planner_history,
            )
        if isinstance(answer_update, dict):
            answer_update["planner_state"] = None
            answer_update["resume_target"] = None
            answer_update["semantic_resume_value"] = None
            answer_update["root_resume_value"] = None
            answer_update["continue_with_question"] = answer_update.get(
                "continue_with_question",
                None,
            )
            return answer_update

        runner._emit_projected_event(
            writer,
            round_projection,
            runner._build_complete_event(state, status="ok"),
        )

    return _build_planner_stop_state(round_projection)
