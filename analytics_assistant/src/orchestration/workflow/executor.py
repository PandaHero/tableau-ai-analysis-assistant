# -*- coding: utf-8 -*-
"""
WorkflowExecutor - 工作流执行器。

负责把语义解析、查询执行、答案生成串成一轮可流式输出的执行流程。
当前实现已经把 context/query/answer 的部分职责拆出，但这里仍是总编排器。
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, AsyncIterator, Optional
from uuid import uuid4

from analytics_assistant.src.agents.semantic_parser.graph import (
    compile_semantic_parser_graph,
)
from analytics_assistant.src.agents.semantic_parser.schemas.planner import (
    AnalysisPlan,
    AnalysisPlanStep,
    EvidenceContext,
    PlanStepType,
)
from analytics_assistant.src.infra.config import get_config
from analytics_assistant.src.infra.error_sanitizer import sanitize_error_message
from analytics_assistant.src.platform.tableau.auth import get_tableau_auth_async
from analytics_assistant.src.platform.tableau.adapter import TableauAdapter
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
from analytics_assistant.src.orchestration.query_graph import (
    QueryGraphRunner,
    build_high_risk_interrupt_payload,
    execute_semantic_query,
)
from analytics_assistant.src.orchestration.semantic_graph import (
    SemanticGraphRunner,
    build_semantic_summary,
)
from analytics_assistant.src.orchestration.answer_graph import (
    AnswerGraphRunner,
    build_result_evidence_bundle,
    build_replan_followup_history,
    build_replan_projection,
    invoke_insight_agent,
    invoke_replanner_agent,
    normalize_candidate_questions,
    serialize_insight_payload,
)

from .callbacks import SSECallbacks
from .checkpoint import get_semantic_parser_checkpointer
from .context import WorkflowContext
from .planner_support import (
    append_step_artifact,
    build_evidence_bundle_dict,
    build_followup_history,
    build_initial_evidence_context,
    build_query_step_summary,
    build_step_insight_output,
    build_synthesis_step_summary,
    extract_insight_key_findings,
    get_primary_plan_step,
    parse_analysis_plan,
    serialize_plan_step,
)
from .semantic_guard import resolve_compiler_semantic_input

logger = logging.getLogger(__name__)

# 默认超时（秒）。
_DEFAULT_WORKFLOW_TIMEOUT = 180  # 给字段语义加载和 LLM 调用留足缓冲。
# SSE 事件队列上限，避免无界队列导致内存增长。
_DEFAULT_EVENT_QUEUE_SIZE = 256
_HIGH_RISK_DIMENSION_ROWS_THRESHOLD = 5000
_HIGH_RISK_PARTIAL_FILTER_ROWS_THRESHOLD = 50000
_HIGH_RISK_DEFAULT_BROAD_ROWS = 1000000
_HIGH_RISK_DEFAULT_DIMENSION_CARDINALITY = 50
_HIGH_RISK_MAX_ESTIMATED_ROWS = 10000000

def _merge_metrics(*metric_groups: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Merge metric dictionaries in order, letting later values override earlier ones."""
    merged: dict[str, Any] = {}
    for metrics in metric_groups:
        if metrics:
            merged.update(metrics)
    return merged


class WorkflowExecutor:
    """工作流执行器。

    这里保留总编排职责：
    - 复用已准备好的 context 或现建 context
    - 驱动 semantic graph
    - 调用 query_graph / answer_graph
    - 统一向 SSE 队列发事件
    """

    def __init__(self, tableau_username: str, request_id: Optional[str] = None):
        """初始化 WorkflowExecutor。"""
        self._tableau_username = tableau_username
        self._request_id = request_id
        self._timeout = self._load_timeout()
        self._event_queue_maxsize = self._load_event_queue_maxsize()

    def _load_timeout(self) -> int:
        """从 app.yaml 读取工作流超时配置。

        Returns:
            超时秒数
        """
        try:
            config = get_config()
            return config.get("api", {}).get(
                "timeout", {},
            ).get("workflow_execution", _DEFAULT_WORKFLOW_TIMEOUT)
        except Exception as e:
            logger.warning(f"读取超时配置失败，使用默认值: {e}")
            return _DEFAULT_WORKFLOW_TIMEOUT

    def _load_event_queue_maxsize(self) -> int:
        """从 app.yaml 读取 SSE 事件队列上限。"""
        try:
            config = get_config()
            value = config.get("api", {}).get(
                "streaming", {},
            ).get("event_queue_maxsize", _DEFAULT_EVENT_QUEUE_SIZE)
            return max(1, int(value))
        except Exception as e:
            logger.warning(f"读取 SSE 队列配置失败，使用默认值: {e}")
            return _DEFAULT_EVENT_QUEUE_SIZE

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
        session_id: Optional[str] = None,
        _replan_history: Optional[list[dict[str, Any]]] = None,
        _emit_complete: bool = True,
        _semantic_resume: Any = None,
        _semantic_parse_result: Optional[dict[str, Any]] = None,
        _confirmed_high_risk_signatures: Optional[list[str]] = None,
        _prepared_context: Optional[WorkflowContext] = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """执行一轮工作流并返回 SSE 事件流。"""
        event_queue: asyncio.Queue[Optional[dict[str, Any]]] = asyncio.Queue(
            maxsize=self._event_queue_maxsize
        )
        callbacks = SSECallbacks(event_queue, language=language)
        loop = asyncio.get_running_loop()
        datasource_name = str(datasource_name or "").strip() or None
        datasource_luid = str(datasource_luid or "").strip() or None
        if not datasource_name and not datasource_luid:
            raise ValueError("datasource_name or datasource_luid is required")
        workflow_started_at = loop.time()
        stage_metrics: dict[str, Any] = {}
        collected_metrics: dict[str, Any] = {}
        question = selected_candidate_question or question
        history = list(history or [])
        replan_history_records: list[dict[str, Any]] = list(_replan_history or [])
        confirmed_high_risk_signatures = {
            str(signature).strip()
            for signature in (_confirmed_high_risk_signatures or [])
            if str(signature).strip()
        }
        stage_metrics["replan_mode"] = replan_mode
        if _semantic_resume is not None:
            stage_metrics["semantic_resume_requested"] = True
        if selected_candidate_question:
            stage_metrics["selected_candidate_question_used"] = True

        def _record_stage(metric_name: str, started_at: float) -> float:
            elapsed_ms = (loop.time() - started_at) * 1000
            stage_metrics[metric_name] = elapsed_ms
            return elapsed_ms

        def _collect_metrics(metrics: Optional[dict[str, Any]]) -> None:
            if metrics:
                collected_metrics.update(metrics)

        def _current_metrics(*metric_groups: Optional[dict[str, Any]]) -> dict[str, Any]:
            return _merge_metrics(
                collected_metrics,
                stage_metrics,
                *metric_groups,
            )

        def _build_interrupt_event(
            *,
            interrupt_type: str,
            payload: dict[str, Any],
            step_metrics: Optional[dict[str, Any]] = None,
        ) -> dict[str, Any]:
            normalized_interrupt_type = str(interrupt_type or "").strip()
            if not normalized_interrupt_type:
                raise ValueError("interrupt event missing explicit interrupt_type")
            interrupt_payload = dict(payload)
            interrupt_payload["optimization_metrics"] = _current_metrics(
                step_metrics,
                interrupt_payload.get("optimization_metrics"),
            )
            return {
                "type": "interrupt",
                "interrupt_id": f"int_{uuid4().hex[:8]}",
                "interrupt_type": normalized_interrupt_type,
                "payload": interrupt_payload,
            }

        def _build_langgraph_interrupt_event(
            raw_interrupts: Any,
            *,
            step_metrics: Optional[dict[str, Any]] = None,
        ) -> dict[str, Any]:
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
            normalized_payload.setdefault("resume_strategy", "langgraph_native")

            namespaces = getattr(first_interrupt, "ns", None) or []
            if namespaces:
                normalized_payload["interrupt_ns"] = list(namespaces)

            return _build_interrupt_event(
                interrupt_type=interrupt_type,
                payload=normalized_payload,
                step_metrics=step_metrics,
            )

        def _build_plan_step_clarification_event(
            interrupt_event: dict[str, Any],
            *,
            step_payload: dict[str, Any],
        ) -> dict[str, Any]:
            interrupt_payload = dict(interrupt_event["payload"])
            plan_step_event = {
                "type": "plan_step",
                "status": "clarification",
                "step": step_payload,
                "interrupt_id": interrupt_event["interrupt_id"],
                "interrupt_type": interrupt_event["interrupt_type"],
                "question": interrupt_payload.get("message", ""),
                "message": interrupt_payload.get("message", ""),
                "source": interrupt_payload.get("source", ""),
                "optimization_metrics": interrupt_payload["optimization_metrics"],
            }
            if interrupt_event["interrupt_type"] == "value_confirm":
                plan_step_event["field"] = interrupt_payload.get("field")
                plan_step_event["requested_value"] = interrupt_payload.get(
                    "requested_value"
                )
                plan_step_event["candidates"] = interrupt_payload.get(
                    "candidates",
                    [],
                )
                plan_step_event["options"] = interrupt_payload.get(
                    "candidates",
                    [],
                )
            else:
                plan_step_event["slot_name"] = interrupt_payload.get("slot_name")
                plan_step_event["options"] = interrupt_payload.get(
                    "options",
                    [],
                )
            return plan_step_event

        def _mark_workflow_end(
            *,
            cancelled: bool = False,
            failed: bool = False,
            timed_out: bool = False,
            interrupted: bool = False,
        ) -> float:
            elapsed_ms = (loop.time() - workflow_started_at) * 1000
            stage_metrics["workflow_executor_ms"] = elapsed_ms
            if cancelled:
                stage_metrics["workflow_cancelled"] = True
            if failed:
                stage_metrics["workflow_failed"] = True
            if timed_out:
                stage_metrics["workflow_timed_out"] = True
            if interrupted:
                stage_metrics["workflow_interrupted"] = True
            return elapsed_ms

        query_runner = QueryGraphRunner(
            request_id=self._request_id,
            risk_evaluator=build_high_risk_interrupt_payload,
            query_executor=execute_semantic_query,
        )
        semantic_runner = SemanticGraphRunner(
            graph_compiler=compile_semantic_parser_graph,
            checkpointer_getter=get_semantic_parser_checkpointer,
        )

        async def _emit_parse_result_event(
            parse_result: dict[str, Any],
            *,
            plan_step: Optional[dict[str, Any]] = None,
            step_metrics: Optional[dict[str, Any]] = None,
        ) -> dict[str, Any]:
            """Emit the parse-result event with the frontend-facing semantic summary."""
            semantic_raw = parse_result.get("semantic_output", {})
            summary = build_semantic_summary(semantic_raw)
            if summary:
                event: dict[str, Any] = {
                    "type": "parse_result",
                    "success": True,
                    "query_id": parse_result.get("query_id", ""),
                    "summary": summary,
                    "is_degraded": bool(parse_result.get("is_degraded", False)),
                    "query_cache_hit": bool(parse_result.get("query_cache_hit", False)),
                    "optimization_metrics": _current_metrics(step_metrics),
                }
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
                if plan_step:
                    event["planStep"] = plan_step
                if (
                    parse_result.get("analysis_plan")
                    and not parse_result.get("global_understanding")
                ):
                    event["analysis_plan"] = parse_result.get("analysis_plan")
                if parse_result.get("global_understanding"):
                    event["global_understanding"] = parse_result.get("global_understanding")
                await event_queue.put(event)
            return summary

        async def _emit_insight_event(
            insight_output_dict: dict[str, Any],
            *,
            source: str,
            plan_step: Optional[dict[str, Any]] = None,
            step_metrics: Optional[dict[str, Any]] = None,
        ) -> None:
            """Emit a structured insight event."""
            event: dict[str, Any] = {
                "type": "insight",
                "source": source,
                **serialize_insight_payload(insight_output_dict),
                "optimization_metrics": _current_metrics(step_metrics),
            }
            if plan_step:
                event["planStep"] = plan_step
            await event_queue.put(event)

        async def _emit_replan_events(
            *,
            replan_decision: Any,
            source: str,
            step_metrics: Optional[dict[str, Any]] = None,
            mode: str = "user_select",
            action: str = "await_user_select",
            selected_question: Optional[str] = None,
            projection: Optional[dict[str, Any]] = None,
        ) -> list[dict[str, Any]]:
            """Emit replan, candidate-question, and suggestion events."""
            if projection is None:
                projection = build_replan_projection(
                    replan_decision=replan_decision,
                    source=source,
                    replan_mode=mode,
                    current_question=question,
                    replan_history=replan_history_records,
                )
            metrics = _current_metrics(step_metrics)
            await event_queue.put({
                **projection["replan_event"],
                "selectedQuestion": selected_question,
                "action": action,
                "optimization_metrics": metrics,
            })
            return projection["candidate_questions"]

        async def _handle_replan_outcome(
            *,
            replan_decision: Any,
            source: str,
            round_history: list[dict[str, str]],
            round_summary: str,
            step_metrics: Optional[dict[str, Any]] = None,
            projection: Optional[dict[str, Any]] = None,
        ) -> None:
            """Project the replan outcome and optionally trigger auto-continue."""
            if projection is None:
                projection = build_replan_projection(
                    replan_decision=replan_decision,
                    source=source,
                    replan_mode=replan_mode,
                    current_question=question,
                    replan_history=replan_history_records,
                )
            selected_question = projection["selected_question"]
            action = projection["action"]

            await _emit_replan_events(
                replan_decision=replan_decision,
                source=source,
                step_metrics=step_metrics,
                mode=replan_mode,
                action=action,
                selected_question=selected_question,
                projection=projection,
            )
            if projection["interrupt_payload"] is not None:
                await event_queue.put(
                    _build_interrupt_event(
                        interrupt_type="followup_select",
                        payload=projection["interrupt_payload"],
                        step_metrics=step_metrics,
                    )
                )

            if hasattr(replan_decision, "model_dump"):
                replan_history_records.append(replan_decision.model_dump())

            if action != "auto_continue" or not selected_question:
                return

            stage_metrics["auto_continue_triggered"] = True
            stage_metrics["auto_continue_rounds"] = int(
                stage_metrics.get("auto_continue_rounds", 0)
            ) + 1
            followup_history = build_replan_followup_history(
                round_history,
                previous_question=question,
                round_summary=round_summary,
                replan_reason=str(getattr(replan_decision, "reason", "") or ""),
                next_question=selected_question,
            )

            async for followup_event in self.execute_stream(
                question=selected_question,
                datasource_name=datasource_name,
                datasource_luid=datasource_luid,
                project_name=project_name,
                history=followup_history,
                language=language,
                analysis_depth=analysis_depth,
                replan_mode=replan_mode,
                session_id=session_id,
                _replan_history=replan_history_records,
                _emit_complete=False,
                _confirmed_high_risk_signatures=list(
                    confirmed_high_risk_signatures
                ),
                _prepared_context=_prepared_context,
            ):
                await event_queue.put(followup_event)

        async def _run_post_query_agents(
            *,
            ctx: WorkflowContext,
            semantic_raw: dict[str, Any],
            query_id: Optional[str],
            table_data: Optional[dict[str, Any]],
            result_manifest_ref: Optional[str],
            evidence_bundle_dict: Optional[dict[str, Any]],
        ) -> Optional[Any]:
            """Run insight and replanning after a successful single-query execution."""
            answer_runner = AnswerGraphRunner(
                invoke_insight_agent=invoke_insight_agent,
                invoke_replanner_agent=invoke_replanner_agent,
                request_id=self._request_id,
            )

            await callbacks.on_node_start("insight_agent")
            await callbacks.on_node_start("replanner_agent")
            try:
                answer_state = await answer_runner.run(
                    source="single_query",
                    question=question,
                    semantic_raw=semantic_raw,
                    result_manifest_ref=result_manifest_ref,
                    evidence_bundle_dict=evidence_bundle_dict,
                    conversation_history=history,
                    replan_history=replan_history_records,
                    analysis_depth=analysis_depth,
                    replan_mode=replan_mode,
                    field_semantic=ctx.field_semantic,
                    query_id=query_id,
                    session_id=session_id,
                    on_token=callbacks.on_token,
                    on_thinking=callbacks.on_thinking,
                )
            finally:
                await callbacks.on_node_end("insight_agent")
                await callbacks.on_node_end("replanner_agent")

            if answer_state.get("insight_skipped"):
                stage_metrics["insight_skipped"] = True
                return None
            if answer_state.get("insight_failed"):
                stage_metrics["insight_failed"] = True
                return None
            if answer_state.get("insight_ms") is not None:
                stage_metrics["insight_ms"] = float(answer_state["insight_ms"])
            stage_metrics["insight_findings_count"] = int(
                answer_state.get("insight_findings_count") or 0
            )

            insight_output_dict = answer_state.get("insight_output_dict")
            if not isinstance(insight_output_dict, dict):
                return None

            await _emit_insight_event(
                insight_output_dict,
                source="single_query",
            )

            if answer_state.get("replanner_failed"):
                stage_metrics["replanner_failed"] = True
                return None
            if answer_state.get("replanner_ms") is not None:
                stage_metrics["replanner_ms"] = float(answer_state["replanner_ms"])
            if answer_state.get("replanner_should_replan") is not None:
                stage_metrics["replanner_should_replan"] = bool(
                    answer_state["replanner_should_replan"]
                )
            stage_metrics["replanner_suggested_questions_count"] = int(
                answer_state.get("replanner_suggested_questions_count") or 0
            )
            stage_metrics["replanner_candidate_questions_count"] = int(
                answer_state.get("replanner_candidate_questions_count") or 0
            )

            replan_decision = answer_state.get("replan_decision")
            if not replan_decision:
                return None

            await _handle_replan_outcome(
                replan_decision=replan_decision,
                source="single_query",
                round_history=history,
                round_summary=str(insight_output_dict.get("summary") or ""),
                projection=answer_state.get("replan_projection"),
            )
            return replan_decision

        async def _run_post_planner_agents(
            *,
            ctx: WorkflowContext,
            semantic_raw: dict[str, Any],
            evidence_context: EvidenceContext,
            completed_steps: list[dict[str, Any]],
        ) -> Optional[Any]:
            """Run insight and replanning after a multi-step planner finishes."""
            if not completed_steps:
                stage_metrics["planner_replanner_skipped"] = True
                return None

            answer_runner = AnswerGraphRunner(
                invoke_insight_agent=invoke_insight_agent,
                invoke_replanner_agent=invoke_replanner_agent,
                request_id=self._request_id,
            )
            planner_history = build_followup_history(
                history,
                question,
                completed_steps,
            )

            await callbacks.on_node_start("insight_agent")
            await callbacks.on_node_start("replanner_agent")
            try:
                answer_state = await answer_runner.run(
                    source="planner_synthesis",
                    question=question,
                    semantic_raw=semantic_raw,
                    evidence_bundle_dict=build_evidence_bundle_dict(
                        question,
                        evidence_context,
                        source="planner_synthesis",
                    ),
                    conversation_history=planner_history,
                    replan_history=replan_history_records,
                    analysis_depth=analysis_depth,
                    replan_mode=replan_mode,
                    field_semantic=ctx.field_semantic,
                    on_token=callbacks.on_token,
                    on_thinking=callbacks.on_thinking,
                )
            finally:
                await callbacks.on_node_end("insight_agent")
                await callbacks.on_node_end("replanner_agent")

            if answer_state.get("insight_skipped"):
                stage_metrics["planner_insight_skipped"] = True
                return None
            if answer_state.get("insight_failed"):
                stage_metrics["planner_insight_failed"] = True
                return None
            if answer_state.get("insight_ms") is not None:
                stage_metrics["planner_insight_ms"] = float(answer_state["insight_ms"])

            insight_output_dict = answer_state.get("insight_output_dict")
            if not isinstance(insight_output_dict, dict):
                return None

            await _emit_insight_event(
                insight_output_dict,
                source="planner_synthesis",
            )
            stage_metrics["planner_insight_findings_count"] = len(
                insight_output_dict.get("findings") or []
            )

            if answer_state.get("replanner_failed"):
                stage_metrics["planner_replanner_failed"] = True
                return None
            if answer_state.get("replanner_ms") is not None:
                stage_metrics["planner_replanner_ms"] = float(
                    answer_state["replanner_ms"]
                )
            if answer_state.get("replanner_should_replan") is not None:
                stage_metrics["planner_replanner_should_replan"] = bool(
                    answer_state["replanner_should_replan"]
                )
            stage_metrics["planner_replanner_suggested_questions_count"] = int(
                answer_state.get("replanner_suggested_questions_count") or 0
            )
            stage_metrics["planner_replanner_candidate_questions_count"] = int(
                answer_state.get("replanner_candidate_questions_count") or 0
            )

            replan_decision = answer_state.get("replan_decision")
            if not replan_decision:
                return None

            await _handle_replan_outcome(
                replan_decision=replan_decision,
                source="planner_synthesis",
                round_history=planner_history,
                round_summary=str(insight_output_dict.get("summary", "") or ""),
                projection=answer_state.get("replan_projection"),
            )
            return replan_decision

        async def _process_parse_result(
            *,
            ctx: WorkflowContext,
            datasource_luid: str,
            parse_result: dict[str, Any],
            graph: Any | None = None,
        ) -> bool:
            """Consume a resolved semantic parse result and continue with query/answer."""
            if not isinstance(parse_result, dict) or not parse_result.get("success"):
                raise ValueError("semantic parse_result must be a successful dict")

            _collect_metrics(parse_result.get("optimization_metrics") or {})
            semantic_raw, compiler_error = resolve_compiler_semantic_input(parse_result)
            analysis_plan = parse_analysis_plan(
                parse_result.get("analysis_plan"),
                parse_result.get("global_understanding"),
            )
            if (
                analysis_plan is not None
                and analysis_plan.needs_planning
                and analysis_plan.sub_questions
            ):
                if graph is None:
                    graph = await semantic_runner.acompile_graph()
                await _execute_analysis_plan(
                    graph=graph,
                    ctx=ctx,
                    datasource_luid=datasource_luid,
                    parse_result=parse_result,
                    analysis_plan=analysis_plan,
                )
                return bool(stage_metrics.get("planner_interrupted"))

            await _emit_parse_result_event(parse_result)
            if compiler_error:
                await event_queue.put({
                    "type": "error",
                    "error": compiler_error,
                    "optimization_metrics": _current_metrics(),
                })
                return False

            if semantic_raw and ctx.platform_adapter:
                single_query_result = await _execute_query_from_semantic(
                    ctx=ctx,
                    datasource_luid=datasource_luid,
                    semantic_raw=semantic_raw,
                )
                if single_query_result.get("interrupted"):
                    return True
                if single_query_result.get("success"):
                    await _run_post_query_agents(
                        ctx=ctx,
                        semantic_raw=semantic_raw,
                        query_id=parse_result.get("query_id"),
                        table_data=single_query_result.get("tableData"),
                        result_manifest_ref=single_query_result.get("result_manifest_ref"),
                        evidence_bundle_dict=build_result_evidence_bundle(
                            source="single_query",
                            question=question,
                            semantic_raw=semantic_raw,
                            result_manifest_ref=single_query_result.get("result_manifest_ref"),
                            data_profile_dict=single_query_result.get("data_profile_dict"),
                            query_id=parse_result.get("query_id"),
                        ),
                    )
            return False

        async def _run_plan_step_insight_round(
            *,
            semantic_raw: dict[str, Any],
            plan_step: dict[str, Any],
            query_id: Optional[str],
            table_data: Optional[dict[str, Any]],
            result_manifest_ref: Optional[str],
            semantic_summary: Optional[dict[str, Any]],
            step_metrics: Optional[dict[str, Any]] = None,
        ) -> dict[str, Any]:
            """Prefer the real Insight Agent for query steps and fall back to a summary."""
            fallback_output = build_step_insight_output(
                plan_step,
                build_query_step_summary(
                    plan_step,
                    semantic_summary or {},
                    table_data or {},
                ) if table_data else "",
                semantic_summary,
                table_data,
            )
            normalized_manifest_ref = str(result_manifest_ref or "").strip() or None

            insight_started_at = loop.time()
            await callbacks.on_node_start("insight_agent")
            try:
                # 规划步骤和单查询后处理都允许在无 manifest 时走注入式
                # InsightAgent，以保持测试桩与回退链路的一致行为。
                insight_output = await invoke_insight_agent(
                    result_manifest_ref=normalized_manifest_ref,
                    semantic_output_dict=semantic_raw,
                    analysis_depth=analysis_depth,
                    session_id=session_id,
                    on_token=callbacks.on_token,
                    on_thinking=callbacks.on_thinking,
                )
                elapsed_ms = (loop.time() - insight_started_at) * 1000
                stage_metrics["planner_step_insight_total_ms"] = (
                    float(stage_metrics.get("planner_step_insight_total_ms", 0.0))
                    + elapsed_ms
                )
                stage_metrics["planner_step_insight_rounds"] = int(
                    stage_metrics.get("planner_step_insight_rounds", 0)
                ) + 1
                if step_metrics is not None:
                    step_metrics["planner_step_insight_ms"] = elapsed_ms
                return insight_output.model_dump()
            except Exception as exc:
                logger.warning(
                    "query step insight agent failed; falling back to summary: %s",
                    exc,
                )
                stage_metrics["planner_step_insight_failed"] = int(
                    stage_metrics.get("planner_step_insight_failed", 0)
                ) + 1
                return fallback_output
            finally:
                await callbacks.on_node_end("insight_agent")

        async def _execute_query_from_semantic(
            *,
            ctx: WorkflowContext,
            datasource_luid: str,
            semantic_raw: dict[str, Any],
            plan_step: Optional[dict[str, Any]] = None,
            semantic_summary: Optional[dict[str, Any]] = None,
            step_metrics: Optional[dict[str, Any]] = None,
            fail_hard: bool = True,
        ) -> dict[str, Any]:
            """执行单次语义查询，并在需要时附带计划步骤信息。"""
            if not semantic_raw:
                error_message = "缺少可编译语义输出"
                if plan_step:
                    await event_queue.put({
                        "type": "plan_step",
                        "status": "error",
                        "step": plan_step,
                        "error": error_message,
                        "optimization_metrics": _current_metrics(step_metrics),
                    })
                elif fail_hard:
                    await event_queue.put({
                        "type": "error",
                        "error": error_message,
                        "optimization_metrics": _current_metrics(step_metrics),
                    })
                return {
                    "success": False,
                    "error": error_message,
                }

            query_state = await query_runner.run(
                ctx=ctx,
                datasource_luid=datasource_luid,
                semantic_raw=semantic_raw,
                confirmed_high_risk_signatures=list(
                    confirmed_high_risk_signatures
                ),
                run_id=self._request_id,
            )
            high_risk_payload = query_state.get("high_risk_payload")
            if high_risk_payload is not None:
                stage_metrics["high_risk_query_confirm_required"] = True
                stage_metrics["high_risk_query_estimated_rows"] = high_risk_payload[
                    "estimated_rows"
                ]
                _mark_workflow_end(interrupted=True)
                interrupt_event = _build_interrupt_event(
                    interrupt_type="high_risk_query_confirm",
                    payload=high_risk_payload,
                    step_metrics=step_metrics,
                )
                await event_queue.put(interrupt_event)
                if plan_step:
                    stage_metrics["planner_interrupted"] = True
                    stage_metrics["planner_blocked_step"] = plan_step.get("index")
                    await event_queue.put({
                        "type": "plan_step",
                        "status": "clarification",
                        "step": plan_step,
                        "interrupt_id": interrupt_event["interrupt_id"],
                        "interrupt_type": "high_risk_query_confirm",
                        "message": high_risk_payload["message"],
                        "summary": high_risk_payload["summary"],
                        "optimization_metrics": interrupt_event["payload"][
                            "optimization_metrics"
                        ],
                    })
                return {
                    "success": False,
                    "interrupted": True,
                    "error": "high risk query requires confirmation",
                }

                if plan_step is None:
                    await event_queue.put({
                        "type": "status",
                        "message": "正在执行数据查询...",
                    })

            query_execution = dict(query_state.get("query_execution") or {})
            if not query_execution:
                query_execution = {
                    "success": False,
                    "query_execute_ms": float(
                        query_state.get("query_execute_ms") or 0.0
                    ),
                    "error": "query_graph returned empty query_execution",
                }

            if plan_step:
                stage_metrics["planner_query_execute_total_ms"] = (
                    float(stage_metrics.get("planner_query_execute_total_ms", 0.0))
                    + float(query_execution["query_execute_ms"])
                )
                stage_metrics["planner_query_steps_executed"] = (
                    int(stage_metrics.get("planner_query_steps_executed", 0)) + 1
                )
                if plan_step.get("usesPrimaryQuery") and "query_execute_ms" not in stage_metrics:
                    stage_metrics["query_execute_ms"] = query_execution["query_execute_ms"]
            else:
                stage_metrics["query_execute_ms"] = query_execution["query_execute_ms"]
                stage_metrics["query_execute_failed"] = not bool(query_execution["success"])

            if query_execution["success"]:
                data_event: dict[str, Any] = {
                    "type": "data",
                    "tableData": query_execution["tableData"],
                    "truncated": bool(query_execution.get("truncated", False)),
                    "result_manifest_ref": query_execution.get("result_manifest_ref"),
                    "profiles_ref": query_execution.get("profiles_ref"),
                    "chunks_ref": query_execution.get("chunks_ref"),
                    "optimization_metrics": _current_metrics(step_metrics),
                }
                summary_text = ""
                if plan_step:
                    summary_text = build_query_step_summary(
                        plan_step,
                        semantic_summary or {},
                        query_execution["tableData"],
                    )
                    await event_queue.put({
                        "type": "plan_step",
                        "status": "completed",
                        "step": plan_step,
                        "queryId": semantic_raw.get("query_id", ""),
                        "semanticSummary": semantic_summary or {},
                        "summary": summary_text,
                        "optimization_metrics": _current_metrics(step_metrics),
                    })
                    data_event["planStep"] = plan_step
                    data_event["summary"] = summary_text

                await event_queue.put(data_event)
                return {
                    "success": True,
                    "tableData": query_execution["tableData"],
                    "execute_result_model": query_state.get("execute_result_model"),
                    "truncated": bool(query_execution.get("truncated", False)),
                    "result_manifest_ref": query_execution.get("result_manifest_ref"),
                    "data_profile_dict": query_execution.get("data_profile_dict"),
                    "profiles_ref": query_execution.get("profiles_ref"),
                    "chunks_ref": query_execution.get("chunks_ref"),
                    "summary_text": summary_text,
                }

            if plan_step:
                stage_metrics["planner_failed_step"] = plan_step.get("index")
                await event_queue.put({
                    "type": "plan_step",
                    "status": "error",
                    "step": plan_step,
                    "error": query_execution["error"],
                    "optimization_metrics": _current_metrics(step_metrics),
                })
                return {
                    "success": False,
                    "error": query_execution["error"],
                }

            await event_queue.put({
                "type": "error",
                "error": query_execution["error"],
                "optimization_metrics": _current_metrics(step_metrics),
            })
            return {
                "success": False,
                "error": query_execution["error"],
            }

        async def _execute_analysis_plan(
            *,
            graph: Any,
            ctx: WorkflowContext,
            datasource_luid: str,
            parse_result: dict[str, Any],
            analysis_plan: AnalysisPlan,
        ) -> None:
            """Execute a multi-step analysis plan based on `depends_on` relationships.

            Execution mode is controlled by `analysis_plan.execution_strategy`.
            - `parallel`: independent steps run with `asyncio.gather`
            - `sequential` and others: steps run one by one in plan order
            """
            total_steps = len(analysis_plan.sub_questions)
            if not analysis_plan.needs_planning or total_steps == 0:
                return

            evidence_context = build_initial_evidence_context(question)
            is_parallel = analysis_plan.execution_strategy == "parallel"

            planner_event = {
                "type": "planner",
                "planMode": analysis_plan.plan_mode.value,
                "goal": analysis_plan.goal or "",
                "executionStrategy": analysis_plan.execution_strategy,
                "reasoningFocus": analysis_plan.reasoning_focus,
                "steps": [
                    serialize_plan_step(step, index=index, total=total_steps)
                    for index, step in enumerate(analysis_plan.sub_questions, start=1)
                ],
                "optimization_metrics": _current_metrics(),
            }
            await event_queue.put(planner_event)

            stage_metrics["planner_multistep_enabled"] = True
            stage_metrics["planner_execution_strategy"] = analysis_plan.execution_strategy
            stage_metrics["planner_steps_total"] = total_steps
            stage_metrics["planner_query_steps_total"] = sum(
                1
                for step in analysis_plan.sub_questions
                if step.step_type == PlanStepType.QUERY
            )
            stage_metrics["planner_synthesis_steps_total"] = sum(
                1
                for step in analysis_plan.sub_questions
                if step.step_type == PlanStepType.SYNTHESIS
            )

            completed_steps: list[dict[str, Any]] = []
            completed_ids: set[str] = set()

            # Always execute the primary query step first.
            primary_index, primary_step = get_primary_plan_step(analysis_plan)

            if primary_index is not None and primary_step is not None:
                primary_payload = serialize_plan_step(
                    primary_step,
                    index=primary_index,
                    total=total_steps,
                )
                await _emit_parse_result_event(parse_result, plan_step=primary_payload)
                await event_queue.put({
                    "type": "plan_step",
                    "status": "running",
                    "step": primary_payload,
                    "message": f"正在执行规划步骤 {primary_index}/{total_steps}",
                    "optimization_metrics": _current_metrics(),
                })
                semantic_raw, compiler_error = resolve_compiler_semantic_input(parse_result)
                if compiler_error:
                    await event_queue.put({
                        "type": "plan_step",
                        "status": "error",
                        "step": primary_payload,
                        "error": compiler_error,
                        "optimization_metrics": _current_metrics(),
                    })
                    return
                semantic_summary = build_semantic_summary(semantic_raw)
                query_result = await _execute_query_from_semantic(
                    ctx=ctx,
                    datasource_luid=datasource_luid,
                    semantic_raw=semantic_raw,
                    plan_step=primary_payload,
                    semantic_summary=semantic_summary,
                )
                if not query_result["success"]:
                    return
                completed_steps.append({
                    "step": primary_payload,
                    "summary_text": query_result.get("summary_text", ""),
                    "tableData": query_result.get("tableData"),
                    "semantic_summary": semantic_summary,
                })
                primary_step_insight = await _run_plan_step_insight_round(
                    semantic_raw=semantic_raw,
                    plan_step=primary_payload,
                    query_id=parse_result.get("query_id"),
                    table_data=query_result.get("tableData"),
                    result_manifest_ref=query_result.get("result_manifest_ref"),
                    semantic_summary=semantic_summary,
                )
                await _emit_insight_event(
                    primary_step_insight,
                    source="plan_step",
                    plan_step=primary_payload,
                )
                stage_metrics["planner_step_insights_emitted"] = int(
                    stage_metrics.get("planner_step_insights_emitted", 0)
                ) + 1
                evidence_context = append_step_artifact(
                    evidence_context,
                    step_payload=primary_payload,
                    query_id=parse_result.get("query_id"),
                    restated_question=semantic_raw.get("restated_question"),
                    table_data=query_result.get("tableData"),
                    summary_text=query_result.get("summary_text", ""),
                    semantic_summary=semantic_summary,
                    key_findings=extract_insight_key_findings(primary_step_insight),
                )
                primary_step_id = primary_step.step_id or f"step-{primary_index}"
                completed_ids.add(primary_step_id)
                stage_metrics["planner_completed_steps"] = len(completed_steps)
            else:
                await _emit_parse_result_event(parse_result)

            # Execution logic for a single follow-up query step.
            async def _run_single_query_step(
                index: int,
                step: AnalysisPlanStep,
                snapshot_evidence: EvidenceContext,
                snapshot_completed: list[dict[str, Any]],
            ) -> Optional[dict[str, Any]]:
                step_payload = serialize_plan_step(step, index=index, total=total_steps)

                await event_queue.put({
                    "type": "plan_step",
                    "status": "running",
                    "step": step_payload,
                    "message": f"正在执行规划步骤 {index}/{total_steps}",
                    "optimization_metrics": _current_metrics(),
                })

                followup_history = build_followup_history(
                    history, question, snapshot_completed,
                )
                followup_started_at = loop.time()
                followup_config = semantic_runner.build_config(
                    ctx=ctx,
                    datasource_luid=datasource_luid,
                    session_id=session_id,
                    request_id=self._request_id,
                    run_id=self._request_id,
                    on_token=callbacks.on_token,
                    on_thinking=callbacks.on_thinking,
                    thread_suffix=f":plan-step-{index}",
                )
                followup_state = await graph.ainvoke(
                    {
                        "question": step.question,
                        "datasource_luid": datasource_luid,
                        "history": followup_history,
                        "chat_history": followup_history,
                        "current_step_intent": {
                            **step.model_dump(mode="json"),
                            "step_id": step.step_id or f"step-{index}",
                            "goal": step.goal or step.purpose,
                        },
                        "evidence_context": snapshot_evidence.model_dump(),
                        "current_time": ctx.current_time,
                        "language": language,
                        "analysis_depth": analysis_depth,
                    },
                    followup_config,
                )
                followup_parse_ms = (loop.time() - followup_started_at) * 1000
                stage_metrics["planner_followup_parse_total_ms"] = (
                    float(stage_metrics.get("planner_followup_parse_total_ms", 0.0))
                    + followup_parse_ms
                )
                stage_metrics["planner_followup_steps_executed"] = (
                    int(stage_metrics.get("planner_followup_steps_executed", 0)) + 1
                )
                followup_parse_result = followup_state.get("parse_result") or {}
                step_metrics_local = _merge_metrics(
                    followup_state.get("optimization_metrics"),
                    followup_parse_result.get("optimization_metrics"),
                    {"planner_followup_parse_ms": followup_parse_ms},
                )

                if "__interrupt__" in followup_state:
                    stage_metrics["planner_blocked_step"] = index
                    stage_metrics["planner_interrupted"] = True
                    _mark_workflow_end(interrupted=True)
                    interrupt_event = _build_langgraph_interrupt_event(
                        followup_state.get("__interrupt__"),
                        step_metrics=step_metrics_local,
                    )
                    await event_queue.put(
                        _build_plan_step_clarification_event(
                            interrupt_event,
                            step_payload=step_payload,
                        )
                    )
                    await event_queue.put(interrupt_event)
                    return None

                if followup_state.get("needs_clarification"):
                    raise ValueError(
                        "planner follow-up emitted legacy clarification output; "
                        "use native LangGraph interrupt() instead"
                    )

                if not followup_parse_result.get("success"):
                    stage_metrics["planner_failed_step"] = index
                    await event_queue.put({
                        "type": "plan_step",
                        "status": "error",
                        "step": step_payload,
                        "error": "Multi-step analysis did not produce an executable parse result.",
                        "optimization_metrics": _current_metrics(step_metrics_local),
                    })
                    return None

                semantic_raw_local, compiler_error = resolve_compiler_semantic_input(
                    followup_parse_result
                )
                semantic_summary_local = await _emit_parse_result_event(
                    followup_parse_result,
                    plan_step=step_payload,
                    step_metrics=step_metrics_local,
                )
                if compiler_error:
                    await event_queue.put({
                        "type": "plan_step",
                        "status": "error",
                        "step": step_payload,
                        "error": compiler_error,
                        "optimization_metrics": _current_metrics(step_metrics_local),
                    })
                    return None
                query_result = await _execute_query_from_semantic(
                    ctx=ctx,
                    datasource_luid=datasource_luid,
                    semantic_raw=semantic_raw_local,
                    plan_step=step_payload,
                    semantic_summary=semantic_summary_local,
                    step_metrics=step_metrics_local,
                    fail_hard=False,
                )
                if not query_result["success"]:
                    return None

                step_insight_output = await _run_plan_step_insight_round(
                    semantic_raw=semantic_raw_local,
                    plan_step=step_payload,
                    query_id=followup_parse_result.get("query_id"),
                    table_data=query_result.get("tableData"),
                    result_manifest_ref=query_result.get("result_manifest_ref"),
                    semantic_summary=semantic_summary_local,
                    step_metrics=step_metrics_local,
                )
                await _emit_insight_event(
                    step_insight_output,
                    source="plan_step",
                    plan_step=step_payload,
                    step_metrics=step_metrics_local,
                )
                stage_metrics["planner_step_insights_emitted"] = int(
                    stage_metrics.get("planner_step_insights_emitted", 0)
                ) + 1

                return {
                    "index": index,
                    "step": step,
                    "step_payload": step_payload,
                    "summary_text": query_result.get("summary_text", ""),
                    "tableData": query_result.get("tableData"),
                    "semantic_summary": semantic_summary_local,
                    "query_id": followup_parse_result.get("query_id"),
                    "semantic_raw": semantic_raw_local,
                    "insight_output": step_insight_output,
                }

            def _collect_step_result(
                result: dict[str, Any],
            ) -> None:
                """Persist a completed step into the accumulated planner state."""
                nonlocal evidence_context
                step_id = result["step"].step_id or f"step-{result['index']}"
                completed_ids.add(step_id)
                completed_steps.append({
                    "step": result["step_payload"],
                    "summary_text": result["summary_text"],
                    "tableData": result.get("tableData"),
                    "semantic_summary": result.get("semantic_summary"),
                })
                evidence_context = append_step_artifact(
                    evidence_context,
                    step_payload=result["step_payload"],
                    query_id=result.get("query_id"),
                    restated_question=(result.get("semantic_raw") or {}).get(
                        "restated_question"
                    ),
                    table_data=result.get("tableData"),
                    summary_text=result["summary_text"],
                    semantic_summary=result.get("semantic_summary"),
                    key_findings=extract_insight_key_findings(
                        result.get("insight_output")
                    ),
                )

            # Execute remaining planner branches according to `depends_on`.
            remaining: list[tuple[int, AnalysisPlanStep]] = [
                (index, step)
                for index, step in enumerate(analysis_plan.sub_questions, start=1)
                if primary_index is None or index != primary_index
            ]

            while remaining:
                ready: list[tuple[int, AnalysisPlanStep]] = []
                not_ready: list[tuple[int, AnalysisPlanStep]] = []
                for item in remaining:
                    idx, step = item
                    step_deps = set(step.depends_on or [])
                    if step_deps.issubset(completed_ids):
                        ready.append(item)
                    else:
                        not_ready.append(item)

                if not ready:
                    logger.warning(
                        "[_execute_analysis_plan] 依赖死锁，%d 个步骤无法执行",
                        len(remaining),
                    )
                    break

                synthesis_ready = [
                    (i, s) for i, s in ready
                    if s.step_type == PlanStepType.SYNTHESIS
                ]
                query_ready = [
                    (i, s) for i, s in ready
                    if s.step_type != PlanStepType.SYNTHESIS
                ]

                # Query-step branch.
                if query_ready:
                    if is_parallel and len(query_ready) > 1:
                        logger.info(
                            "[_execute_analysis_plan] 并行执行 %d 个查询步骤",
                            len(query_ready),
                        )
                        snapshot_ev = evidence_context.model_copy(deep=True)
                        snapshot_cs = list(completed_steps)
                        tasks = [
                            _run_single_query_step(i, s, snapshot_ev, snapshot_cs)
                            for i, s in query_ready
                        ]
                        results = await asyncio.gather(
                            *tasks, return_exceptions=True,
                        )
                        for (idx, step), result in zip(query_ready, results):
                            if isinstance(result, Exception):
                                logger.error(
                                    "[_execute_analysis_plan] step %s failed in parallel branch: %s",
                                    step.step_id or f"step-{idx}",
                                    result,
                                )
                                continue
                            if result is None:
                                continue
                            _collect_step_result(result)
                        if stage_metrics.get("planner_interrupted"):
                            return
                        stage_metrics["planner_completed_steps"] = len(completed_steps)
                        stage_metrics["planner_parallel_waves"] = int(
                            stage_metrics.get("planner_parallel_waves", 0)
                        ) + 1
                    else:
                        for idx, step in query_ready:
                            result = await _run_single_query_step(
                                idx, step, evidence_context, list(completed_steps),
                            )
                            if result is None:
                                return
                            _collect_step_result(result)
                            stage_metrics["planner_completed_steps"] = len(
                                completed_steps
                            )

                # Synthesis-step branch.
                for idx, step in synthesis_ready:
                    step_payload = serialize_plan_step(
                        step, index=idx, total=total_steps,
                    )
                    synthesis_summary = build_synthesis_step_summary(
                        question, completed_steps,
                    )
                    await event_queue.put({
                        "type": "plan_step",
                        "status": "completed",
                        "step": step_payload,
                        "summary": synthesis_summary,
                        "evidenceCount": len(completed_steps),
                        "optimization_metrics": _current_metrics(),
                    })
                    completed_steps.append({
                        "step": step_payload,
                        "summary_text": synthesis_summary,
                    })
                    syn_step_id = step.step_id or f"step-{idx}"
                    completed_ids.add(syn_step_id)
                    evidence_context = append_step_artifact(
                        evidence_context,
                        step_payload=step_payload,
                        summary_text=synthesis_summary,
                        key_findings=[synthesis_summary],
                        open_questions=analysis_plan.risk_flags,
                    )
                    stage_metrics["planner_completed_steps"] = len(completed_steps)

                remaining = not_ready

            await _run_post_planner_agents(
                ctx=ctx,
                semantic_raw=parse_result.get("semantic_output", {}) or {},
                evidence_context=evidence_context,
                completed_steps=completed_steps,
            )

        async def _run_semantic_graph(
            *,
            ctx: WorkflowContext,
            datasource_luid: str,
        ) -> None:
            """Run the semantic stage once a WorkflowContext is ready."""
            graph_compile_started_at = loop.time()
            logger.info("[workflow] step 4: compile semantic_parser graph")
            graph = await semantic_runner.acompile_graph()
            _record_stage("graph_compile_ms", graph_compile_started_at)
            logger.info("[workflow] semantic_parser graph ready")

            logger.info("[workflow] step 5: build runnable config")
            config = semantic_runner.build_config(
                ctx=ctx,
                datasource_luid=datasource_luid,
                session_id=session_id,
                request_id=self._request_id,
                run_id=self._request_id,
                on_token=callbacks.on_token,
                on_thinking=callbacks.on_thinking,
            )

            if _semantic_resume is None:
                logger.info("[workflow] step 6: build initial state")
                logger.debug("[workflow] question: %s", question)
                logger.info("[workflow] history messages: %s", len(history or []))
            else:
                logger.info("[workflow] step 6: resume semantic graph")
            graph_input = semantic_runner.build_input(
                question=question,
                datasource_luid=datasource_luid,
                history=history,
                current_time=ctx.current_time,
                language=language,
                analysis_depth=analysis_depth,
                field_semantic=ctx.field_semantic,
                resume=_semantic_resume,
            )
            logger.info("[workflow] graph input ready")
            logger.info("=" * 60)

            logger.info("[workflow] step 7: execute graph")
            logger.debug(
                "[workflow] graph input ready: datasource_luid=%s, resume=%s",
                datasource_luid,
                _semantic_resume is not None,
            )
            node_count = 0

            logger.debug("[workflow] calling graph.astream()")
            logger.debug("[workflow] stream_mode=updates")
            logger.debug("[workflow] config keys: %s", list(config.keys()))

            async for event in semantic_runner.astream(
                graph=graph,
                graph_input=graph_input,
                config=config,
            ):
                logger.debug("[workflow] received event keys: %s", list(event.keys()))
                if "__interrupt__" in event:
                    _mark_workflow_end(interrupted=True)
                    await event_queue.put(
                        _build_langgraph_interrupt_event(
                            event.get("__interrupt__"),
                        )
                    )
                    return
                for node_name, node_output in event.items():
                    node_count += 1
                    stage_metrics["graph_node_count"] = node_count
                    logger.debug("[workflow] node #%s: %s start", node_count, node_name)
                    await callbacks.on_node_start(node_name)

                    if isinstance(node_output, dict):
                        _collect_metrics(node_output.get("optimization_metrics"))
                        if "query_result" in node_output:
                            await event_queue.put({
                                "type": "data",
                                "tableData": node_output["query_result"],
                            })
                        if "chart_config" in node_output:
                            await event_queue.put({
                                "type": "chart",
                                "chartConfig": node_output["chart_config"],
                            })
                        if "suggestions" in node_output:
                            await event_queue.put({
                                "type": "suggestions",
                                "questions": node_output["suggestions"],
                            })
                        if "parse_result" in node_output:
                            parse_result = node_output["parse_result"]
                            if isinstance(parse_result, dict) and parse_result.get("success"):
                                if await _process_parse_result(
                                    ctx=ctx,
                                    datasource_luid=datasource_luid,
                                    parse_result=parse_result,
                                    graph=graph,
                                ):
                                    return
                        if node_output.get("needs_clarification"):
                            raise ValueError(
                                f"{node_name} emitted legacy clarification output; "
                                "use native LangGraph interrupt() instead"
                            )

                    await callbacks.on_node_end(node_name)

            stage_metrics["graph_node_count"] = node_count
            logger.info("[workflow] graph execution completed, node_count=%s", node_count)
            if _emit_complete:
                logger.info("[workflow] emit complete event")
                workflow_elapsed_ms = _mark_workflow_end()
                await event_queue.put({
                    "type": "complete",
                    "workflowTimeMs": workflow_elapsed_ms,
                    "optimization_metrics": _current_metrics(),
                })
        async def _run_workflow() -> None:
            """在后台任务中执行整轮工作流。"""
            nonlocal datasource_luid
            try:
                if _prepared_context is not None:
                    logger.info("=" * 60)
                    logger.info("[workflow] reuse prepared context from root_graph")
                    stage_metrics["context_reused"] = True
                    await callbacks.on_node_start("data_preparation")
                    async with VizQLClient() as vizql_client:
                        datasource_luid = _prepared_context.datasource_luid
                        ctx = _prepared_context.model_copy(update={
                            "platform_adapter": TableauAdapter(vizql_client=vizql_client),
                            "current_time": datetime.now().isoformat(),
                            "user_id": self._tableau_username,
                        })
                        stage_metrics["field_semantic_available"] = bool(ctx.field_semantic)
                        stage_metrics["field_samples_available"] = bool(ctx.field_samples)
                        stage_metrics["datasource_prewarm_scheduled"] = False
                        await callbacks.on_node_end("data_preparation")
                        if _semantic_parse_result is not None:
                            if await _process_parse_result(
                                ctx=ctx,
                                datasource_luid=datasource_luid,
                                parse_result=_semantic_parse_result,
                            ):
                                return
                            if _emit_complete:
                                logger.info("[workflow] emit complete event")
                                workflow_elapsed_ms = _mark_workflow_end()
                                await event_queue.put({
                                    "type": "complete",
                                    "workflowTimeMs": workflow_elapsed_ms,
                                    "optimization_metrics": _current_metrics(),
                                })
                        else:
                            await _run_semantic_graph(
                                ctx=ctx,
                                datasource_luid=datasource_luid,
                            )
                    return

                # 1. 璁よ瘉
                auth_started_at = loop.time()
                logger.info("=" * 60)
                logger.info("[工作流] 步骤 1: 开始认证")
                await callbacks.on_node_start("authentication")
                auth = await get_tableau_auth_async()
                _record_stage("auth_ms", auth_started_at)
                logger.info("[工作流] 认证成功: user=%s", self._tableau_username)
                await callbacks.on_node_end("authentication")

                async with VizQLClient() as vizql_client:
                    # 2. Load the data model. The loader resolves datasource name and LUID.
                    data_preparation_started_at = loop.time()
                    data_model_started_at = loop.time()
                    logger.info("[工作流] 步骤 2: 开始加载数据模型")
                    logger.info(f"[工作流] 数据源名称: {datasource_name}")
                    await callbacks.on_node_start("data_preparation")
                    loader = TableauDataLoader(client=vizql_client)
                    try:
                        data_model = await loader.load_data_model(
                            datasource_id=datasource_luid,
                            datasource_name=datasource_name,
                            project_name=project_name,
                            auth=auth,
                            skip_index_creation=True,
                        )
                    except TableauDatasourceAmbiguityError as exc:
                        _record_stage("data_model_load_ms", data_model_started_at)
                        _record_stage("data_preparation_ms", data_preparation_started_at)
                        stage_metrics["datasource_disambiguation_required"] = True
                        stage_metrics["datasource_disambiguation_choice_count"] = len(
                            exc.choices
                        )
                        _mark_workflow_end(interrupted=True)
                        await event_queue.put({
                            "type": "interrupt",
                            "interrupt_id": f"int_{uuid4().hex[:8]}",
                            "interrupt_type": "datasource_disambiguation",
                            "payload": {
                                "message": str(exc) or "找到多个同名数据源，请先选择具体数据源。",
                                "choices": list(exc.choices or []),
                                "datasource_name": exc.datasource_name,
                                "project_name": exc.project_name,
                                "optimization_metrics": _current_metrics(),
                            },
                        })
                        return
                    _record_stage("data_model_load_ms", data_model_started_at)
                    datasource_luid = data_model.datasource_id
                    logger.info(
                        "[工作流] 数据模型加载成功: luid=%s, fields=%s",
                        datasource_luid,
                        len(data_model.fields),
                    )

                    # 3. Build the workflow context and inject the platform adapter.
                    logger.info("[工作流] 步骤 3: 创建工作流上下文并注入 platform_adapter")
                    platform_adapter = TableauAdapter(vizql_client=vizql_client)
                    ctx = WorkflowContext(
                        auth=auth,
                        datasource_luid=datasource_luid,
                        data_model=data_model,
                        field_samples=getattr(data_model, "_field_samples_cache", None),
                        current_time=datetime.now().isoformat(),
                        user_id=self._tableau_username,
                        platform_adapter=platform_adapter,
                    )
                    logger.info("[工作流] 开始加载字段语义信息...")
                    field_semantic_started_at = loop.time()
                    ctx = await ctx.load_field_semantic(allow_online_inference=False)
                    _record_stage("field_semantic_load_ms", field_semantic_started_at)
                    stage_metrics["field_semantic_available"] = bool(ctx.field_semantic)
                    stage_metrics["field_samples_available"] = bool(ctx.field_samples)
                    logger.info("[工作流] 字段语义加载完成")
                    if not ctx.field_semantic or not ctx.field_samples:
                        scheduled = schedule_datasource_artifact_preparation(
                            datasource_id=datasource_luid,
                            auth=auth,
                        )
                        stage_metrics["datasource_prewarm_scheduled"] = scheduled
                        if scheduled:
                            logger.info(
                                "[工作流] 已调度 datasource 后台预热: %s",
                                datasource_luid,
                            )
                    else:
                        stage_metrics["datasource_prewarm_scheduled"] = False
                    _record_stage("data_preparation_ms", data_preparation_started_at)
                    await callbacks.on_node_end("data_preparation")

                    if _semantic_parse_result is not None:
                        if await _process_parse_result(
                            ctx=ctx,
                            datasource_luid=datasource_luid,
                            parse_result=_semantic_parse_result,
                        ):
                            return
                        if _emit_complete:
                            logger.info("[workflow] emit complete event")
                            workflow_elapsed_ms = _mark_workflow_end()
                            await event_queue.put({
                                "type": "complete",
                                "workflowTimeMs": workflow_elapsed_ms,
                                "optimization_metrics": _current_metrics(),
                            })
                    else:
                        await _run_semantic_graph(
                            ctx=ctx,
                            datasource_luid=datasource_luid,
                        )

            except asyncio.CancelledError:
                logger.info("工作流被取消: request_id=%s", self._request_id)
                _mark_workflow_end(cancelled=True)
                await event_queue.put({
                    "type": "error",
                    "error": "请求已取消",
                    "optimization_metrics": _current_metrics(),
                })
            except Exception as e:
                logger.exception(
                    f"工作流执行失败: request_id={self._request_id}, "
                    f"user={self._tableau_username}, "
                    f"datasource={datasource_name}, error={e}"
                )
                _mark_workflow_end(failed=True)
                await event_queue.put({
                    "type": "error",
                    "error": sanitize_error_message(str(e)),
                    "optimization_metrics": _current_metrics(),
                })
            finally:
                # Mark the event queue as completed.
                await event_queue.put(None)

        # Run the workflow in the background with an overall timeout.
        workflow_task = asyncio.create_task(_run_workflow())
        start_time = loop.time()

        try:
            while True:
                elapsed = loop.time() - start_time
                remaining = float(self._timeout) - elapsed
                if remaining <= 0:
                    logger.error(
                        "工作流整体超时: timeout=%ss, user=%s",
                        self._timeout,
                        self._tableau_username,
                    )
                    _mark_workflow_end(timed_out=True)
                    yield {
                        "type": "error",
                        "error": "工作流执行超时",
                        "optimization_metrics": _current_metrics(),
                    }
                    break

                try:
                    # 每次最多等待 30 秒，超时后发送 heartbeat 保持 SSE 连接。
                    event = await asyncio.wait_for(
                        event_queue.get(),
                        timeout=min(remaining, 30.0),
                    )
                except asyncio.TimeoutError:
                    # 30 秒内无事件时发送 heartbeat，避免连接被动断开。
                    yield {"type": "heartbeat"}
                    continue

                if event is None:
                    break
                yield event
        finally:
            # Cancel the workflow when the client disconnects.
            if not workflow_task.done():
                workflow_task.cancel()
                try:
                    await workflow_task
                except asyncio.CancelledError:
                    pass


__all__ = [
    "WorkflowExecutor",
]
