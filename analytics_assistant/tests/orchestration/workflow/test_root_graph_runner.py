# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import os
import sys
from types import SimpleNamespace
from typing import Any, AsyncIterator, Optional

import pytest

project_root = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
repo_root = os.path.dirname(project_root)
for candidate in (repo_root, project_root):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from analytics_assistant.src.orchestration.root_graph import RootGraphRunner
from analytics_assistant.src.orchestration.root_graph import planner_runtime as planner_runtime_module
from analytics_assistant.src.orchestration.root_graph import runner as root_runner_module
from analytics_assistant.src.orchestration.workflow.checkpoint import (
    reset_workflow_checkpointers,
)
from analytics_assistant.src.orchestration.workflow.context import (
    PreparedContextSnapshot,
    WorkflowContext,
)


@pytest.fixture(autouse=True)
def reset_checkpointers() -> None:
    """每个测试前后重置 checkpoint，避免跨事件循环污染。"""
    reset_workflow_checkpointers(clear_persisted_state=True)
    yield
    reset_workflow_checkpointers(clear_persisted_state=True)


def _build_snapshot(datasource_luid: str) -> PreparedContextSnapshot:
    return PreparedContextSnapshot(datasource_luid=datasource_luid).model_dump(mode="json")


async def _fake_auth_getter() -> SimpleNamespace:
    return SimpleNamespace(
        api_key="k",
        site="default",
        domain="https://tableau.example.com",
        auth_method="pat",
    )


class _SemanticGraphRunnerStub:
    def __init__(self, events_per_call: Optional[list[list[dict[str, Any]]]] = None) -> None:
        self.events_per_call = list(events_per_call or [[_make_parse_result_update()]])
        self.calls = 0
        self.build_input_calls: list[dict[str, Any]] = []
        self.astream_inputs: list[Any] = []

    async def acompile_graph(self) -> object:
        return object()

    def build_config(self, **_kwargs: Any) -> dict[str, Any]:
        return {"configurable": {"thread_id": "sess-test"}}

    def build_input(self, **kwargs: Any) -> dict[str, Any]:
        self.build_input_calls.append(kwargs)
        if kwargs.get("resume") is not None:
            return {"resume": kwargs["resume"]}
        return {"question": kwargs["question"]}

    async def astream(
        self,
        *,
        graph: Any,
        graph_input: Any,
        config: dict[str, Any],
    ) -> AsyncIterator[dict[str, Any]]:
        del graph
        del config
        self.astream_inputs.append(graph_input)
        index = min(self.calls, len(self.events_per_call) - 1)
        self.calls += 1
        for event in self.events_per_call[index]:
            yield event


class _ModelDumpStub:
    """为测试构造带 model_dump() 的轻量对象。"""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def model_dump(self) -> dict[str, Any]:
        return dict(self._payload)


def _make_parse_result_update(
    *,
    analysis_plan: Optional[dict[str, Any]] = None,
    include_query: bool = True,
    semantic_output_override: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    parse_result = {
        "success": True,
        "query_id": "q-root",
        "candidate_fields_ref": (
            "kv://retrieval_memory/candidate_fields/ds-resolved/cache-q-root"
        ),
        "candidate_values_ref": (
            "kv://retrieval_memory/candidate_values/ds-resolved/cache-q-root"
        ),
        "fewshot_examples_ref": (
            "kv://retrieval_memory/fewshot_examples/ds-resolved/cache-q-root"
        ),
        "retrieval_trace_ref": "kv://retrieval_memory/retrieval_trace/ds-resolved/q-root",
        "memory_write_refs": [
            "kv://retrieval_memory/memory_audit/ds-resolved/audit-q-root"
        ],
        "semantic_guard": {
            "verified": True,
            "validation_mode": "deterministic",
            "corrected": False,
            "compiler_ready": True,
            "allowed_to_execute": True,
            "query_contract_mode": "compiler_input",
            "query_contract_source": "semantic_output",
            "error_count": 0,
            "filter_confirmation_count": 0,
            "needs_clarification": False,
            "needs_value_confirmation": False,
            "has_unresolvable_filters": False,
            "errors": [],
        },
        "semantic_output": {
            "restated_question": "show revenue",
            "what": {"measures": [{"field_name": "Sales", "aggregation": "SUM"}]},
            "where": {"dimensions": [{"field_name": "Region"}], "filters": []},
            "how_type": "SIMPLE",
            "self_check": {
                "field_mapping_confidence": 0.93,
                "time_range_confidence": 0.93,
                "computation_confidence": 0.93,
                "overall_confidence": 0.93,
                "potential_issues": [],
            },
        },
        "analysis_plan": analysis_plan,
    }
    if semantic_output_override:
        parse_result["semantic_output"] = semantic_output_override
    if include_query:
        parse_result["query"] = {
            "mode": "compiler_input",
            "source": "semantic_output",
            "query_id": "q-root",
            "restated_question": str(
                (parse_result["semantic_output"] or {}).get("restated_question") or ""
            ),
        }
    return {
        "feedback_learner": {
            "parse_result": parse_result,
        },
    }


def _make_planning_parse_result_update() -> dict[str, Any]:
    return _make_parse_result_update(
        analysis_plan={
            "plan_mode": "decomposed_query",
            "single_query_feasible": False,
            "needs_planning": True,
            "sub_questions": [
                {
                    "step_id": "step-1",
                    "title": "拆解地区表现",
                    "question": "show revenue by region",
                }
            ],
        }
    )


def _make_multistep_planning_parse_result_update() -> dict[str, Any]:
    return _make_parse_result_update(
        analysis_plan={
            "plan_mode": "decomposed_query",
            "single_query_feasible": False,
            "needs_planning": True,
            "execution_strategy": "sequential",
            "sub_questions": [
                {
                    "step_id": "step-1",
                    "title": "拆解地区表现",
                    "question": "show revenue by region",
                    "uses_primary_query": True,
                },
                {
                    "step_id": "step-2",
                    "title": "拆解渠道表现",
                    "question": "show revenue by channel",
                    "depends_on": ["step-1"],
                },
            ],
        }
    )


def _make_parallel_wave_planning_parse_result_update() -> dict[str, Any]:
    return _make_parse_result_update(
        analysis_plan={
            "plan_mode": "decomposed_query",
            "single_query_feasible": False,
            "needs_planning": True,
            "execution_strategy": "parallel",
            "sub_questions": [
                {
                    "step_id": "step-1",
                    "title": "定位主异常区域",
                    "question": "show revenue by region",
                    "uses_primary_query": True,
                },
                {
                    "step_id": "step-2",
                    "title": "拆解渠道表现",
                    "question": "show revenue by channel",
                    "depends_on": ["step-1"],
                },
                {
                    "step_id": "step-3",
                    "title": "拆解客户类型表现",
                    "question": "show revenue by customer type",
                    "depends_on": ["step-1"],
                },
            ],
        }
    )


def _make_why_axis_planning_parse_result_update() -> dict[str, Any]:
    return _make_parse_result_update(
        analysis_plan={
            "plan_mode": "why_analysis",
            "single_query_feasible": False,
            "needs_planning": True,
            "execution_strategy": "sequential",
            "sub_questions": [
                {
                    "step_id": "step-1",
                    "title": "验证异常",
                    "question": "show revenue change by month",
                    "step_type": "query",
                    "step_kind": "verify_anomaly",
                    "uses_primary_query": True,
                },
                {
                    "step_id": "step-2",
                    "title": "解释轴排序",
                    "question": "rank the most likely explanatory axes",
                    "step_type": "query",
                    "step_kind": "rank_explanatory_axes",
                    "depends_on": ["step-1"],
                    "candidate_axes": ["channel", "product_line", "customer_type"],
                    "semantic_focus": ["change drivers"],
                },
                {
                    "step_id": "step-3",
                    "title": "筛查高优先解释轴",
                    "question": "screen the top ranked explanatory axes with real data",
                    "step_type": "query",
                    "step_kind": "screen_top_axes",
                    "depends_on": ["step-2"],
                    "candidate_axes": ["channel", "product_line", "customer_type"],
                    "semantic_focus": ["screening wave"],
                    "targets_anomaly": True,
                },
                {
                    "step_id": "step-4",
                    "title": "定位异常切片",
                    "question": "locate the anomalous slice under the best axis",
                    "step_type": "query",
                    "step_kind": "locate_anomalous_slice",
                    "depends_on": ["step-2", "step-3"],
                    "targets_anomaly": True,
                },
                {
                    "step_id": "step-5",
                    "title": "归因总结",
                    "question": "summarize the likely cause",
                    "step_type": "synthesis",
                    "step_kind": "synthesize_cause",
                    "depends_on": ["step-1", "step-2", "step-3", "step-4"],
                },
            ],
        }
    )


def _make_excessive_planning_parse_result_update() -> dict[str, Any]:
    return _make_parse_result_update(
        analysis_plan={
            "plan_mode": "decomposed_query",
            "single_query_feasible": False,
            "needs_planning": True,
            "execution_strategy": "parallel",
            "sub_questions": [
                {
                    "step_id": f"step-{index}",
                    "title": f"step {index}",
                    "question": f"show revenue slice {index}",
                    "uses_primary_query": index == 1,
                }
                for index in range(1, 10)
            ],
        }
    )


def _make_semantic_interrupt_update(
    *,
    interrupt_type: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "__interrupt__": [
            SimpleNamespace(
                value={"interrupt_type": interrupt_type, **payload},
                ns=[],
            )
        ]
    }


def _query_success_payload(
    *,
    row_count: int = 1,
    truncated: bool = False,
    result_manifest_ref: Optional[str] = None,
) -> dict[str, Any]:
    return {
        "success": True,
        "tableData": {
            "columns": [
                {
                    "name": "region",
                    "dataType": "STRING",
                    "isDimension": True,
                    "isMeasure": False,
                },
                {
                    "name": "sales",
                    "dataType": "REAL",
                    "isDimension": False,
                    "isMeasure": True,
                },
            ],
            "rows": [{"region": "East", "sales": 100}],
            "rowCount": row_count,
            "executionTimeMs": 12,
        },
        "truncated": truncated,
        "result_manifest_ref": result_manifest_ref,
    }


def _patch_direct_round(
    monkeypatch: pytest.MonkeyPatch,
    *,
    high_risk_builder: Optional[Any] = None,
    query_results: Optional[list[dict[str, Any]]] = None,
    insight_results: Optional[list[dict[str, Any]]] = None,
    replan_results: Optional[list[dict[str, Any]]] = None,
) -> None:
    """把 root_graph 直查路径依赖全部替换成可控 stub。"""

    query_queue = list(query_results) if query_results is not None else [
        _query_success_payload() for _ in range(4)
    ]
    insight_queue = list(insight_results) if insight_results is not None else [
        {
            "summary": "Revenue looks stable.",
            "overall_confidence": 0.82,
            "findings": [],
        }
        for _ in range(4)
    ]
    replan_queue = list(replan_results) if replan_results is not None else [
        {
            "should_replan": False,
            "reason": "当前结果已足够回答问题。",
            "suggested_questions": [],
            "candidate_questions": [],
        }
        for _ in range(4)
    ]

    def _next_payload(queue: list[dict[str, Any]]) -> dict[str, Any]:
        if not queue:
            raise AssertionError("测试 stub 队列已耗尽，请补充足够的返回值。")
        if len(queue) == 1:
            return dict(queue[0])
        return dict(queue.pop(0))

    def _default_high_risk_builder(**kwargs: Any) -> Optional[dict[str, Any]]:
        if high_risk_builder is not None:
            if callable(high_risk_builder):
                return high_risk_builder(**kwargs)
            return dict(high_risk_builder)
        return None

    async def _fake_execute_semantic_query(**_kwargs: Any) -> dict[str, Any]:
        return _next_payload(query_queue)

    async def _fake_invoke_insight_agent(**_kwargs: Any) -> _ModelDumpStub:
        return _ModelDumpStub(_next_payload(insight_queue))

    async def _fake_invoke_replanner_agent(**_kwargs: Any) -> _ModelDumpStub:
        return _ModelDumpStub(_next_payload(replan_queue))

    monkeypatch.setattr(
        root_runner_module,
        "build_high_risk_interrupt_payload",
        _default_high_risk_builder,
    )
    monkeypatch.setattr(
        planner_runtime_module,
        "build_high_risk_interrupt_payload",
        _default_high_risk_builder,
    )
    monkeypatch.setattr(
        root_runner_module,
        "execute_semantic_query",
        _fake_execute_semantic_query,
    )
    monkeypatch.setattr(
        planner_runtime_module,
        "execute_semantic_query",
        _fake_execute_semantic_query,
    )
    monkeypatch.setattr(
        root_runner_module,
        "invoke_insight_agent",
        _fake_invoke_insight_agent,
    )
    monkeypatch.setattr(
        planner_runtime_module,
        "invoke_insight_agent",
        _fake_invoke_insight_agent,
    )
    monkeypatch.setattr(
        root_runner_module,
        "invoke_replanner_agent",
        _fake_invoke_replanner_agent,
    )
    monkeypatch.setattr(
        planner_runtime_module,
        "invoke_replanner_agent",
        _fake_invoke_replanner_agent,
    )


def _non_thinking_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [event for event in events if event.get("type") != "thinking"]


def _thinking_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [event for event in events if event.get("type") == "thinking"]


def _assert_complete_event(
    event: dict[str, Any],
    *,
    status: str,
    reason: Optional[str] = None,
) -> None:
    """校验 root_graph 的稳定 complete 契约。"""
    assert event["type"] == "complete"
    assert event["status"] == status
    if reason is None:
        assert "reason" not in event
    else:
        assert event["reason"] == reason

    assert "artifact_freshness_report" in event
    assert "artifact_refresh_request" in event
    assert "artifact_refresh_scheduled" in event
    assert "degrade_flags" in event
    assert "degrade_details" in event
    assert "memory_invalidation_report" in event

    metrics = event["context_metrics"]
    assert "context_degraded" in metrics
    assert "artifact_refresh_requested" in metrics
    assert "artifact_refresh_scheduled" in metrics
    assert "artifact_refresh_schedule_failed" in metrics
    assert "refresh_trigger" in metrics
    assert "refresh_requested_artifacts" in metrics
    assert "schema_change_invalidated" in metrics
    assert "has_stale_artifacts" in metrics
    assert "has_missing_artifacts" in metrics
    assert "degraded_artifacts" in metrics
    assert "degrade_reason_codes" in metrics
    assert "requires_attention" in metrics
    assert "invalidation_trigger" in metrics
    assert "invalidation_total_deleted" in metrics
    assert "artifact_statuses" in metrics


async def _resolved_context(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "tenant_domain": "https://tableau.example.com",
        "tenant_site": "default",
        "tenant_auth_method": "pat",
        "datasource_luid": state.get("datasource_luid") or "ds-resolved",
        "datasource_name": state.get("datasource_name"),
        "project_name": state.get("project_name"),
        "prepared_context_snapshot": _build_snapshot(
            state.get("datasource_luid") or "ds-resolved"
        ),
        "pending_interrupt_type": None,
        "pending_interrupt_payload": None,
    }


async def _resolved_context_with_prepared_bundle(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "tenant_domain": "https://tableau.example.com",
        "tenant_site": "default",
        "tenant_auth_method": "pat",
        "datasource_luid": state.get("datasource_luid") or "ds-prepared",
        "datasource_name": state.get("datasource_name"),
        "project_name": state.get("project_name"),
        "prepared_context_snapshot": _build_snapshot("ds-prepared"),
        "pending_interrupt_type": None,
        "pending_interrupt_payload": None,
    }


class _FollowupExecutor:
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        self.calls: list[dict[str, Any]] = []

    async def execute_stream(self, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
        self.calls.append(kwargs)
        question = str(kwargs.get("question") or "")
        if question == "show revenue":
            yield {"type": "table_result", "tableData": {"rowCount": 1, "rows": [{"value": 1}]}}
            yield {
                "type": "interrupt",
                "interrupt_type": "followup_select",
                "payload": {
                    "message": "pick a follow-up",
                    "candidates": [
                        {"id": "q1", "question": "show revenue by region"},
                        {"id": "q2", "question": "show revenue by channel"},
                    ],
                },
            }
            return

        yield {"type": "complete", "question": question}


class _HighRiskExecutor:
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        self.calls: list[dict[str, Any]] = []

    async def execute_stream(self, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
        self.calls.append(kwargs)
        confirmed_signatures = set(kwargs.get("_confirmed_high_risk_signatures") or [])
        if "sig-risk-001" not in confirmed_signatures:
            yield {
                "type": "interrupt",
                "interrupt_type": "high_risk_query_confirm",
                "payload": {
                    "message": "confirm high risk query",
                    "summary": "预计扫描数据量较大，需要确认后继续。",
                    "risk_level": "high",
                    "estimated_rows": 200000,
                    "risk_signature": "sig-risk-001",
                },
            }
            return

        yield {"type": "complete", "status": "approved"}


class _ProjectionExecutor:
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        self.calls: list[dict[str, Any]] = []

    async def execute_stream(self, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
        self.calls.append(kwargs)
        yield {
            "type": "parse_result",
            "summary": {
                "measures": ["销售额"],
                "dimensions": ["地区"],
            },
            "confidence": 0.93,
        }
        yield {
            "type": "data",
            "tableData": {
                "rowCount": 24,
                "rows": [{"region": "East", "sales": 100}],
            },
            "truncated": False,
            "result_manifest_ref": "artifacts/runs/run_008/result/result_manifest.json",
        }
        yield {
            "type": "insight",
            "summary": "华东区销售额下降主要集中在直营渠道。",
        }
        yield {
            "type": "replan",
            "reason": "可以继续按渠道或产品线拆解",
            "candidateQuestions": [
                {"id": "q1", "question": "按渠道继续分析"},
                {"id": "q2", "question": "按产品线继续分析"},
            ],
        }
        yield {"type": "complete", "status": "ok"}


async def _ambiguous_context(state: dict[str, Any]) -> dict[str, Any]:
    datasource_luid = str(state.get("datasource_luid") or "").strip()
    if datasource_luid:
        return {
            "tenant_domain": "https://tableau.example.com",
            "tenant_site": "default",
            "tenant_auth_method": "pat",
            "datasource_luid": datasource_luid,
            "datasource_name": state.get("datasource_name"),
            "project_name": state.get("project_name"),
            "prepared_context_snapshot": _build_snapshot(datasource_luid),
            "pending_interrupt_type": None,
            "pending_interrupt_payload": None,
        }

    return {
        "tenant_domain": "https://tableau.example.com",
        "tenant_site": "default",
        "tenant_auth_method": "pat",
        "pending_interrupt_type": "datasource_disambiguation",
        "pending_interrupt_payload": {
            "message": "找到多个同名数据源，请先选择。",
            "datasource_name": "Revenue",
            "resume_strategy": "root_graph_native",
            "choices": [
                {"datasource_luid": "ds-sales", "name": "Revenue", "project": "Sales"},
                {"datasource_luid": "ds-ops", "name": "Revenue", "project": "Ops"},
            ],
        },
    }


def test_build_request_uses_session_id_as_thread_id() -> None:
    runner = RootGraphRunner(
        "alice",
        request_id="req_root_001",
        auth_getter=_fake_auth_getter,
        context_resolver=_resolved_context,
    )

    request = runner.build_request(
        latest_user_message="show revenue",
        datasource_name="Revenue",
        session_id="sess_root_001",
    )
    state = runner.build_run_state(request)

    assert request.session_id == "sess_root_001"
    assert request.thread_id == "sess_root_001"
    assert state.request.session_id == "sess_root_001"
    assert state.request.thread_id == "sess_root_001"


@pytest.mark.asyncio
async def test_default_context_resolver_passes_previous_schema_hash_to_context_graph():
    captured: dict[str, Any] = {}

    class _ContextGraphStub:
        async def run(self, **kwargs: Any) -> dict[str, Any]:
            captured.update(kwargs)
            return {
                "tenant_domain": "https://tableau.example.com",
                "tenant_site": "default",
                "tenant_auth_method": "pat",
                "datasource_luid": "ds-1",
                "prepared_context_snapshot": _build_snapshot("ds-1"),
                "artifact_freshness_report": {},
                "artifact_refresh_request": {
                    "datasource_luid": "ds-1",
                    "trigger": "missing_artifacts",
                    "requested_artifacts": ["field_semantic_index"],
                },
                "artifact_refresh_scheduled": True,
                "degrade_flags": [],
                "degrade_details": [],
                "memory_invalidation_report": {},
                "pending_interrupt_type": None,
                "pending_interrupt_payload": None,
            }

    previous_context = WorkflowContext(datasource_luid="ds-1").update_current_time()
    runner = RootGraphRunner(
        "alice",
        request_id="req_root_prev_schema",
        auth_getter=_fake_auth_getter,
        context_graph_runner=_ContextGraphStub(),
    )

    resolved = await runner._default_context_resolver(
        {
            "datasource_name": "Revenue",
            "prepared_context_snapshot": previous_context.to_snapshot().model_dump(mode="json"),
        }
    )

    assert captured["previous_schema_hash"] == previous_context.schema_hash
    assert resolved["artifact_refresh_request"] == {
        "datasource_luid": "ds-1",
        "trigger": "missing_artifacts",
        "requested_artifacts": ["field_semantic_index"],
    }
    assert resolved["artifact_refresh_scheduled"] is True
    assert resolved["degrade_details"] == []


@pytest.mark.asyncio
async def test_execute_stream_runs_planner_round_natively() -> None:
    monkeypatch = pytest.MonkeyPatch()
    _patch_direct_round(monkeypatch)
    runner = RootGraphRunner(
        "alice",
        request_id="req_root_002",
        auth_getter=_fake_auth_getter,
        semantic_graph_runner=_SemanticGraphRunnerStub(
            events_per_call=[[_make_planning_parse_result_update()]]
        ),
        context_resolver=_resolved_context,
    )

    events = [
        event
        async for event in runner.execute_stream(
            question="show revenue",
            datasource_name="Revenue",
            project_name="Sales",
            session_id="sess_root_002",
        )
    ]
    monkeypatch.undo()

    business_events = _non_thinking_events(events)
    assert _thinking_events(events)
    assert [event["type"] for event in business_events] == [
        "planner",
        "parse_result",
        "plan_step",
        "plan_step",
        "data",
        "insight",
        "insight",
        "replan",
        "complete",
    ]
    assert business_events[0]["executionStrategy"] == "single_query"


@pytest.mark.asyncio
async def test_execute_stream_planner_final_answer_uses_answer_graph_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_direct_round(monkeypatch)
    captured: dict[str, Any] = {}
    original_helper = root_runner_module.RootGraphRunner._run_answer_graph_round

    async def _capture_answer_graph_round(self, **kwargs: Any) -> Optional[dict[str, Any]]:
        captured.update(kwargs)
        return await original_helper(self, **kwargs)

    monkeypatch.setattr(
        root_runner_module.RootGraphRunner,
        "_run_answer_graph_round",
        _capture_answer_graph_round,
    )
    runner = RootGraphRunner(
        "alice",
        request_id="req_root_planner_answer_001",
        auth_getter=_fake_auth_getter,
        semantic_graph_runner=_SemanticGraphRunnerStub(
            events_per_call=[[_make_multistep_planning_parse_result_update()]]
        ),
        context_resolver=_resolved_context,
    )

    events = [
        event
        async for event in runner.execute_stream(
            question="why revenue dropped",
            datasource_name="Revenue",
            session_id="sess_root_planner_answer_001",
        )
    ]

    business_events = _non_thinking_events(events)
    assert captured["source"] == "planner_synthesis"
    assert "prebuilt_insight_output_dict" not in captured
    assert isinstance(captured["evidence_bundle_dict"], dict)
    assert captured["evidence_bundle_dict"]["source"] == "planner_synthesis"
    assert captured["question"] == "why revenue dropped"
    assert business_events[-1]["type"] == "complete"


@pytest.mark.asyncio
async def test_execute_stream_why_locate_step_inherits_ranked_axes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_direct_round(
        monkeypatch,
        query_results=[
            _query_success_payload(),
            _query_success_payload(row_count=2),
            _query_success_payload(row_count=2),
            _query_success_payload(row_count=2),
        ],
        replan_results=[{
            "should_replan": False,
            "reason": "why 证据已经足够。",
            "candidate_questions": [],
            "suggested_questions": [],
        }],
    )
    semantic_runner = _SemanticGraphRunnerStub(
        events_per_call=[
            [_make_why_axis_planning_parse_result_update()],
            [_make_parse_result_update(
                include_query=False,
                semantic_output_override={
                    "restated_question": "rank channel and product line for the revenue drop",
                    "what": {"measures": [{"field_name": "Sales", "aggregation": "SUM"}]},
                    "where": {
                        "dimensions": [{"field_name": "Channel"}],
                        "filters": [],
                    },
                    "how_type": "SIMPLE",
                    "self_check": {
                        "field_mapping_confidence": 0.91,
                        "time_range_confidence": 0.9,
                        "computation_confidence": 0.9,
                        "overall_confidence": 0.9,
                        "potential_issues": [],
                    },
                },
            )],
            [_make_parse_result_update(
                include_query=False,
                semantic_output_override={
                    "restated_question": "screen channel and product line with high-level data",
                    "what": {"measures": [{"field_name": "Sales", "aggregation": "SUM"}]},
                    "where": {
                        "dimensions": [{"field_name": "Product Line"}],
                        "filters": [],
                    },
                    "how_type": "SIMPLE",
                    "self_check": {
                        "field_mapping_confidence": 0.91,
                        "time_range_confidence": 0.9,
                        "computation_confidence": 0.9,
                        "overall_confidence": 0.9,
                        "potential_issues": [],
                    },
                },
            )],
            [_make_parse_result_update(
                include_query=False,
                semantic_output_override={
                    "restated_question": "locate the anomalous channel slice",
                    "what": {"measures": [{"field_name": "Sales", "aggregation": "SUM"}]},
                    "where": {
                        "dimensions": [{"field_name": "Product Line"}],
                        "filters": [],
                    },
                    "how_type": "SIMPLE",
                    "self_check": {
                        "field_mapping_confidence": 0.91,
                        "time_range_confidence": 0.9,
                        "computation_confidence": 0.9,
                        "overall_confidence": 0.9,
                        "potential_issues": [],
                    },
                },
            )],
        ]
    )
    runner = RootGraphRunner(
        "alice",
        request_id="req_root_why_axes_001",
        auth_getter=_fake_auth_getter,
        semantic_graph_runner=semantic_runner,
        context_resolver=_resolved_context_with_prepared_bundle,
    )

    events = [
        event
        async for event in runner.execute_stream(
            question="why revenue dropped",
            datasource_name="Revenue",
            session_id="sess_root_why_axes_001",
        )
    ]
    monkeypatch.undo()

    business_events = _non_thinking_events(events)
    assert business_events[-1]["type"] == "complete"

    step_two_input = semantic_runner.astream_inputs[1]
    assert step_two_input["current_step_intent"]["candidate_axes"] == [
        "channel",
        "product_line",
        "customer_type",
    ]

    step_three_input = semantic_runner.astream_inputs[2]
    assert step_three_input["current_step_intent"]["step_kind"] == "screen_top_axes"
    assert step_three_input["current_step_intent"]["candidate_axes"][:2] == [
        "channel",
        "product_line",
    ]
    assert "customer_type" not in step_three_input["current_step_intent"]["candidate_axes"][:2]
    assert "channel" in step_three_input["evidence_context"]["validated_axes"]
    assert step_three_input["evidence_context"]["axis_scores"][0]["axis"] == "channel"

    step_four_input = semantic_runner.astream_inputs[3]
    assert step_four_input["current_step_intent"]["step_kind"] == "locate_anomalous_slice"
    assert step_four_input["current_step_intent"]["candidate_axes"][:2] == [
        "product_line",
        "channel",
    ]


@pytest.mark.asyncio
async def test_execute_stream_replays_planner_step_interrupt_natively() -> None:
    monkeypatch = pytest.MonkeyPatch()
    _patch_direct_round(
        monkeypatch,
        query_results=[
            _query_success_payload(),
            _query_success_payload(),
        ],
        insight_results=[
            {
                "summary": "地区层已经识别出主要下降区域。",
                "overall_confidence": 0.82,
                "findings": [],
            },
            {
                "summary": "渠道层已经识别出主要下降渠道。",
                "overall_confidence": 0.82,
                "findings": [],
            },
        ],
        replan_results=[{
            "should_replan": False,
            "reason": "多步结果已经足够。",
            "candidate_questions": [],
            "suggested_questions": [],
        }],
    )
    semantic_runner = _SemanticGraphRunnerStub(
        events_per_call=[
            [_make_multistep_planning_parse_result_update()],
            [_make_semantic_interrupt_update(
                interrupt_type="missing_slot",
                payload={
                    "message": "请选择地区范围",
                    "slot_name": "region",
                    "options": ["East"],
                },
            )],
            [_make_parse_result_update()],
        ]
    )
    runner = RootGraphRunner(
        "alice",
        request_id="req_root_002b",
        auth_getter=_fake_auth_getter,
        semantic_graph_runner=semantic_runner,
        context_resolver=_resolved_context_with_prepared_bundle,
    )

    initial_events = [
        event
        async for event in runner.execute_stream(
            question="show revenue",
            datasource_name="Revenue",
            session_id="sess_root_002b",
        )
    ]

    assert _non_thinking_events(initial_events)[-1]["type"] == "interrupt"
    interrupted_snapshot = await runner.aget_state_snapshot(session_id="sess_root_002b")
    assert interrupted_snapshot["pending_interrupt_type"] == "missing_slot"
    assert interrupted_snapshot["resume_target"] == "execute_round"
    assert interrupted_snapshot["planner_state"]["pending_step"]["step"]["step_id"] == "step-2"

    resumed_events = [
        event
        async for event in runner.resume_stream(
            question="show revenue",
            resume_value="East",
            datasource_name="Revenue",
            session_id="sess_root_002b",
            resume_strategy="root_graph_native",
        )
    ]
    monkeypatch.undo()

    assert _thinking_events(resumed_events)
    _assert_complete_event(_non_thinking_events(resumed_events)[-1], status="ok")
    resumed_snapshot = await runner.aget_state_snapshot(session_id="sess_root_002b")
    assert resumed_snapshot["pending_interrupt_type"] is None
    assert resumed_snapshot["planner_state"] is None


@pytest.mark.asyncio
async def test_execute_stream_runs_parallel_planner_wave_natively() -> None:
    monkeypatch = pytest.MonkeyPatch()
    _patch_direct_round(
        monkeypatch,
        insight_results=[
            {
                "summary": "主异常区域已经识别完成。",
                "overall_confidence": 0.82,
                "findings": [],
            },
            {
                "summary": "渠道维度已经完成补查。",
                "overall_confidence": 0.82,
                "findings": [],
            },
            {
                "summary": "客户类型维度已经完成补查。",
                "overall_confidence": 0.82,
                "findings": [],
            },
        ],
        replan_results=[{
            "should_replan": False,
            "reason": "并行证据已经足够。",
            "candidate_questions": [],
            "suggested_questions": [],
        }],
    )

    active_queries = 0
    max_parallel_queries = 0
    total_queries = 0
    parallel_wave_ready = asyncio.Event()

    async def _parallel_query_executor(**_kwargs: Any) -> dict[str, Any]:
        nonlocal active_queries, max_parallel_queries, total_queries
        total_queries += 1
        active_queries += 1
        max_parallel_queries = max(max_parallel_queries, active_queries)

        # 第 2、3 次查询属于同一 follow-up 波次，只有同时进入执行阶段才放行。
        if total_queries >= 3 and active_queries >= 2:
            parallel_wave_ready.set()
        if total_queries >= 2:
            await asyncio.wait_for(parallel_wave_ready.wait(), timeout=1.0)

        active_queries -= 1
        return _query_success_payload()

    monkeypatch.setattr(
        planner_runtime_module,
        "execute_semantic_query",
        _parallel_query_executor,
    )

    semantic_runner = _SemanticGraphRunnerStub(
        events_per_call=[
            [_make_parallel_wave_planning_parse_result_update()],
            [_make_parse_result_update()],
            [_make_parse_result_update()],
        ]
    )
    runner = RootGraphRunner(
        "alice",
        request_id="req_root_parallel_001",
        auth_getter=_fake_auth_getter,
        semantic_graph_runner=semantic_runner,
        context_resolver=_resolved_context_with_prepared_bundle,
    )

    events = [
        event
        async for event in runner.execute_stream(
            question="why revenue dropped",
            datasource_name="Revenue",
            session_id="sess_root_parallel_001",
        )
    ]
    monkeypatch.undo()

    business_events = _non_thinking_events(events)
    assert _thinking_events(events)
    assert business_events[0]["type"] == "planner"
    assert business_events[0]["executionStrategy"] == "parallel"
    _assert_complete_event(business_events[-1], status="ok")
    assert max_parallel_queries >= 2
    assert total_queries == 3


@pytest.mark.asyncio
async def test_execute_stream_planner_followup_interrupt_uses_single_active_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_direct_round(
        monkeypatch,
        replan_results=[{
            "should_replan": True,
            "reason": "多步分析后建议继续按渠道补查。",
            "candidate_questions": [
                {"id": "q1", "question": "show revenue by channel"},
                {"id": "q2", "question": "show revenue by customer type"},
            ],
            "suggested_questions": [],
        }],
    )
    runner = RootGraphRunner(
        "alice",
        request_id="req_root_planner_followup_001",
        auth_getter=_fake_auth_getter,
        semantic_graph_runner=_SemanticGraphRunnerStub(
            events_per_call=[[_make_multistep_planning_parse_result_update()]]
        ),
        context_resolver=_resolved_context_with_prepared_bundle,
    )

    events = [
        event
        async for event in runner.execute_stream(
            question="why revenue dropped",
            datasource_name="Revenue",
            session_id="sess_root_planner_followup_001",
        )
    ]
    monkeypatch.undo()

    business_events = _non_thinking_events(events)
    assert business_events[0]["type"] == "planner"
    assert business_events[-1]["type"] == "interrupt"
    assert business_events[-1]["interrupt_type"] == "followup_select"
    assert business_events[-1]["payload"]["resume_strategy"] == "root_graph_native"
    assert business_events[-2]["type"] == "replan"
    assert business_events[-2]["candidateQuestions"][0]["question"] == "show revenue by channel"

    interrupted_snapshot = await runner.aget_state_snapshot(
        session_id="sess_root_planner_followup_001"
    )
    assert interrupted_snapshot["pending_interrupt_type"] == "followup_select"
    assert interrupted_snapshot["continue_with_question"] is None
    assert interrupted_snapshot["followup_candidates"] == [
        {"id": "candidate_1", "question": "show revenue by channel"},
        {"id": "candidate_2", "question": "show revenue by customer type"},
    ]


@pytest.mark.asyncio
async def test_execute_stream_planner_auto_continue_runs_next_round_natively(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_direct_round(
        monkeypatch,
        replan_results=[
            {
                "should_replan": True,
                "reason": "多步证据已经定位到渠道层，继续下钻。",
                "new_question": "show revenue by channel",
                "candidate_questions": [
                    {"id": "q1", "question": "show revenue by channel"},
                ],
                "suggested_questions": [],
            },
            {
                "should_replan": False,
                "reason": "渠道层结果已经足够。",
                "candidate_questions": [],
                "suggested_questions": [],
            },
        ],
    )
    semantic_runner = _SemanticGraphRunnerStub(
        events_per_call=[
            [_make_multistep_planning_parse_result_update()],
            [_make_parse_result_update()],
        ]
    )
    runner = RootGraphRunner(
        "alice",
        request_id="req_root_planner_auto_001",
        auth_getter=_fake_auth_getter,
        semantic_graph_runner=semantic_runner,
        context_resolver=_resolved_context_with_prepared_bundle,
    )

    events = [
        event
        async for event in runner.execute_stream(
            question="why revenue dropped",
            datasource_name="Revenue",
            session_id="sess_root_planner_auto_001",
            replan_mode="auto_continue",
        )
    ]
    monkeypatch.undo()

    business_events = _non_thinking_events(events)
    assert business_events[0]["type"] == "planner"
    assert any(
        event.get("type") == "replan"
        and event.get("action") == "auto_continue"
        and event.get("selectedQuestion") == "show revenue by channel"
        for event in business_events
    )
    assert semantic_runner.build_input_calls[0]["question"] == "why revenue dropped"
    assert semantic_runner.build_input_calls[1]["question"] == "show revenue by channel"
    _assert_complete_event(business_events[-1], status="ok")

    snapshot = await runner.aget_state_snapshot(session_id="sess_root_planner_auto_001")
    assert snapshot["pending_interrupt_type"] is None
    assert snapshot["planner_state"] is None
    assert snapshot["active_question"] == "show revenue by channel"
    assert snapshot["complete_payload"] == {"status": "ok"}
    assert semantic_runner.calls == 3


@pytest.mark.asyncio
async def test_execute_stream_applies_parallel_planner_wave_cap() -> None:
    monkeypatch = pytest.MonkeyPatch()
    _patch_direct_round(
        monkeypatch,
        insight_results=[
            {
                "summary": "主异常区域已经识别完成。",
                "overall_confidence": 0.82,
                "findings": [],
            },
            {
                "summary": "渠道维度已经完成补查。",
                "overall_confidence": 0.82,
                "findings": [],
            },
            {
                "summary": "客户类型维度已经完成补查。",
                "overall_confidence": 0.82,
                "findings": [],
            },
        ],
        replan_results=[{
            "should_replan": False,
            "reason": "并行证据已经足够。",
            "candidate_questions": [],
            "suggested_questions": [],
        }],
    )
    monkeypatch.setattr(
        planner_runtime_module,
        "_get_planner_runtime_limits",
        lambda: {
            "max_parallel_steps": 1,
            "max_total_steps": 8,
            "max_query_steps": 6,
            "max_runtime_ms": 45000,
        },
    )

    active_queries = 0
    max_parallel_queries = 0
    total_queries = 0

    async def _serial_query_executor(**_kwargs: Any) -> dict[str, Any]:
        nonlocal active_queries, max_parallel_queries, total_queries
        total_queries += 1
        active_queries += 1
        max_parallel_queries = max(max_parallel_queries, active_queries)
        await asyncio.sleep(0)
        active_queries -= 1
        return _query_success_payload()

    monkeypatch.setattr(
        planner_runtime_module,
        "execute_semantic_query",
        _serial_query_executor,
    )

    semantic_runner = _SemanticGraphRunnerStub(
        events_per_call=[
            [_make_parallel_wave_planning_parse_result_update()],
            [_make_parse_result_update()],
            [_make_parse_result_update()],
        ]
    )
    runner = RootGraphRunner(
        "alice",
        request_id="req_root_parallel_cap_001",
        auth_getter=_fake_auth_getter,
        semantic_graph_runner=semantic_runner,
        context_resolver=_resolved_context_with_prepared_bundle,
    )

    events = [
        event
        async for event in runner.execute_stream(
            question="why revenue dropped",
            datasource_name="Revenue",
            session_id="sess_root_parallel_cap_001",
        )
    ]
    monkeypatch.undo()

    business_events = _non_thinking_events(events)
    assert business_events[0]["type"] == "planner"
    _assert_complete_event(business_events[-1], status="ok")
    assert max_parallel_queries == 1
    assert total_queries == 3


@pytest.mark.asyncio
async def test_execute_stream_stops_when_planner_step_limit_exceeded() -> None:
    monkeypatch = pytest.MonkeyPatch()
    _patch_direct_round(monkeypatch)
    monkeypatch.setattr(
        planner_runtime_module,
        "_get_planner_runtime_limits",
        lambda: {
            "max_parallel_steps": 2,
            "max_total_steps": 3,
            "max_query_steps": 3,
            "max_runtime_ms": 45000,
        },
    )

    runner = RootGraphRunner(
        "alice",
        request_id="req_root_limit_001",
        auth_getter=_fake_auth_getter,
        semantic_graph_runner=_SemanticGraphRunnerStub(
            events_per_call=[[_make_excessive_planning_parse_result_update()]]
        ),
        context_resolver=_resolved_context_with_prepared_bundle,
    )

    events = [
        event
        async for event in runner.execute_stream(
            question="why revenue dropped badly",
            datasource_name="Revenue",
            session_id="sess_root_limit_001",
        )
    ]
    monkeypatch.undo()

    business_events = _non_thinking_events(events)
    assert business_events[0]["type"] == "error"
    assert business_events[0]["error_code"] == "planner_step_limit_exceeded"
    _assert_complete_event(
        business_events[-1],
        status="error",
        reason="planner_step_limit_exceeded",
    )
    snapshot = await runner.aget_state_snapshot(session_id="sess_root_limit_001")
    assert snapshot["planner_state"] is None
    assert snapshot["complete_payload"] == {
        "status": "error",
        "reason": "planner_step_limit_exceeded",
    }


@pytest.mark.asyncio
async def test_execute_stream_stops_when_planner_runtime_budget_exceeded() -> None:
    monkeypatch = pytest.MonkeyPatch()
    _patch_direct_round(
        monkeypatch,
        insight_results=[
            {
                "summary": "主异常区域已经识别完成。",
                "overall_confidence": 0.82,
                "findings": [],
            },
        ],
    )
    monkeypatch.setattr(
        planner_runtime_module,
        "_get_planner_runtime_limits",
        lambda: {
            "max_parallel_steps": 2,
            "max_total_steps": 8,
            "max_query_steps": 6,
            "max_runtime_ms": 1,
        },
    )

    async def _slow_query_executor(**_kwargs: Any) -> dict[str, Any]:
        await asyncio.sleep(0.02)
        return _query_success_payload()

    monkeypatch.setattr(
        planner_runtime_module,
        "execute_semantic_query",
        _slow_query_executor,
    )

    semantic_runner = _SemanticGraphRunnerStub(
        events_per_call=[
            [_make_multistep_planning_parse_result_update()],
            [_make_parse_result_update()],
        ]
    )
    runner = RootGraphRunner(
        "alice",
        request_id="req_root_budget_001",
        auth_getter=_fake_auth_getter,
        semantic_graph_runner=semantic_runner,
        context_resolver=_resolved_context_with_prepared_bundle,
    )

    events = [
        event
        async for event in runner.execute_stream(
            question="why revenue dropped",
            datasource_name="Revenue",
            session_id="sess_root_budget_001",
        )
    ]
    monkeypatch.undo()

    business_events = _non_thinking_events(events)
    error_event = next(event for event in business_events if event["type"] == "error")
    assert error_event["error_code"] == "planner_runtime_budget_exceeded"
    _assert_complete_event(
        business_events[-1],
        status="error",
        reason="planner_runtime_budget_exceeded",
    )
    snapshot = await runner.aget_state_snapshot(session_id="sess_root_budget_001")
    assert snapshot["planner_state"] is None
    assert snapshot["complete_payload"] == {
        "status": "error",
        "reason": "planner_runtime_budget_exceeded",
    }


@pytest.mark.asyncio
async def test_resume_stream_rejects_legacy_resume_strategy() -> None:
    runner = RootGraphRunner(
        "alice",
        request_id="req_root_003",
        auth_getter=_fake_auth_getter,
        context_resolver=_resolved_context,
    )

    with pytest.raises(ValueError, match="root_graph_native"):
        events = [
            event
            async for event in runner.resume_stream(
                question="show revenue",
                resume_value="East",
                datasource_name="Revenue",
                session_id="sess_root_003",
                resume_strategy="root_graph_native_invalid",
            )
        ]
        del events


@pytest.mark.asyncio
async def test_execute_stream_converts_followup_interrupt_to_root_native_resume(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_direct_round(
        monkeypatch,
        replan_results=[{
            "should_replan": True,
            "reason": "可以继续拆到渠道维度。",
            "candidate_questions": [
                {"id": "q1", "question": "show revenue by region"},
                {"id": "q2", "question": "show revenue by channel"},
            ],
            "suggested_questions": [],
        }],
    )
    runner = RootGraphRunner(
        "alice",
        request_id="req_root_004",
        auth_getter=_fake_auth_getter,
        semantic_graph_runner=_SemanticGraphRunnerStub(),
        context_resolver=_resolved_context,
    )

    events = [
        event
        async for event in runner.execute_stream(
            question="show revenue",
            datasource_name="Revenue",
            session_id="sess_root_004",
        )
    ]

    business_events = _non_thinking_events(events)
    assert _thinking_events(events)
    assert business_events[0]["type"] == "parse_result"
    assert business_events[1]["type"] == "data"
    assert business_events[-1]["type"] == "interrupt"
    assert business_events[-1]["interrupt_type"] == "followup_select"
    assert business_events[-1]["payload"]["resume_strategy"] == "root_graph_native"


@pytest.mark.asyncio
async def test_resume_stream_replays_root_graph_from_followup_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_direct_round(
        monkeypatch,
        replan_results=[
            {
                "should_replan": True,
                "reason": "可以继续拆到渠道维度。",
                "candidate_questions": [
                    {"id": "q1", "question": "show revenue by region"},
                    {"id": "q2", "question": "show revenue by channel"},
                ],
                "suggested_questions": [],
            },
            {
                "should_replan": False,
                "reason": "补查结果已经足够。",
                "candidate_questions": [],
                "suggested_questions": [],
            },
        ],
    )
    runner = RootGraphRunner(
        "alice",
        request_id="req_root_005",
        auth_getter=_fake_auth_getter,
        semantic_graph_runner=_SemanticGraphRunnerStub(
            events_per_call=[[_make_parse_result_update()], [_make_parse_result_update()]]
        ),
        context_resolver=_resolved_context,
    )

    initial_events = [
        event
        async for event in runner.execute_stream(
            question="show revenue",
            datasource_name="Revenue",
            session_id="sess_root_005",
        )
    ]
    assert initial_events[-1]["type"] == "interrupt"

    resumed_events = [
        event
        async for event in runner.resume_stream(
            question="show revenue by region",
            resume_value="show revenue by region",
            datasource_name="Revenue",
            session_id="sess_root_005",
            resume_strategy="root_graph_native",
        )
    ]

    assert _thinking_events(resumed_events)
    _assert_complete_event(_non_thinking_events(resumed_events)[-1], status="ok")


@pytest.mark.asyncio
async def test_execute_stream_auto_continue_runs_next_round_natively(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_direct_round(
        monkeypatch,
        replan_results=[
            {
                "should_replan": True,
                "reason": "需要继续按渠道定位下降来源。",
                "new_question": "show revenue by channel",
                "candidate_questions": [
                    {"id": "q1", "question": "show revenue by channel"},
                ],
                "suggested_questions": [],
            },
            {
                "should_replan": False,
                "reason": "渠道层结果已经足够。",
                "candidate_questions": [],
                "suggested_questions": [],
            },
        ],
    )
    semantic_runner = _SemanticGraphRunnerStub(
        events_per_call=[[_make_parse_result_update()], [_make_parse_result_update()]]
    )
    runner = RootGraphRunner(
        "alice",
        request_id="req_root_auto_001",
        auth_getter=_fake_auth_getter,
        semantic_graph_runner=semantic_runner,
        context_resolver=_resolved_context,
    )

    events = [
        event
        async for event in runner.execute_stream(
            question="show revenue",
            datasource_name="Revenue",
            session_id="sess_root_auto_001",
            replan_mode="auto_continue",
        )
    ]

    business_events = _non_thinking_events(events)
    assert _thinking_events(events)
    assert [event["type"] for event in business_events] == [
        "parse_result",
        "data",
        "insight",
        "replan",
        "parse_result",
        "data",
        "insight",
        "replan",
        "complete",
    ]
    assert semantic_runner.build_input_calls[0]["question"] == "show revenue"
    assert semantic_runner.build_input_calls[1]["question"] == "show revenue by channel"
    assert business_events[3]["action"] == "auto_continue"
    assert business_events[3]["selectedQuestion"] == "show revenue by channel"

    snapshot = await runner.aget_state_snapshot(session_id="sess_root_auto_001")
    assert snapshot["pending_interrupt_type"] is None
    assert snapshot["active_question"] == "show revenue by channel"
    assert snapshot["complete_payload"] == {"status": "ok"}


@pytest.mark.asyncio
async def test_execute_stream_converts_high_risk_interrupt_to_root_native_resume(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _high_risk_builder(**kwargs: Any) -> Optional[dict[str, Any]]:
        confirmed = set(kwargs.get("confirmed_signatures") or [])
        if "sig-risk-001" in confirmed:
            return None
        return {
            "message": "confirm high risk query",
            "summary": "预计扫描数据量较大，需要确认后继续。",
            "risk_level": "high",
            "estimated_rows": 200000,
            "risk_signature": "sig-risk-001",
        }

    _patch_direct_round(monkeypatch, high_risk_builder=_high_risk_builder)
    runner = RootGraphRunner(
        "alice",
        request_id="req_root_006",
        auth_getter=_fake_auth_getter,
        semantic_graph_runner=_SemanticGraphRunnerStub(),
        context_resolver=_resolved_context,
    )

    events = [
        event
        async for event in runner.execute_stream(
            question="show all revenue",
            datasource_name="Revenue",
            session_id="sess_root_006",
        )
    ]

    business_events = _non_thinking_events(events)
    assert _thinking_events(events)
    assert business_events[0]["type"] == "parse_result"
    assert business_events[-1]["type"] == "interrupt"
    assert business_events[-1]["interrupt_type"] == "high_risk_query_confirm"
    assert business_events[-1]["payload"]["risk_signature"] == "sig-risk-001"
    assert business_events[-1]["payload"]["resume_strategy"] == "root_graph_native"


@pytest.mark.asyncio
async def test_resume_stream_replays_root_graph_after_high_risk_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _high_risk_builder(**kwargs: Any) -> Optional[dict[str, Any]]:
        confirmed = set(kwargs.get("confirmed_signatures") or [])
        if "sig-risk-001" in confirmed:
            return None
        return {
            "message": "confirm high risk query",
            "summary": "预计扫描数据量较大，需要确认后继续。",
            "risk_level": "high",
            "estimated_rows": 200000,
            "risk_signature": "sig-risk-001",
        }

    _patch_direct_round(monkeypatch, high_risk_builder=_high_risk_builder)
    runner = RootGraphRunner(
        "alice",
        request_id="req_root_007",
        auth_getter=_fake_auth_getter,
        semantic_graph_runner=_SemanticGraphRunnerStub(
            events_per_call=[[_make_parse_result_update()], [_make_parse_result_update()]]
        ),
        context_resolver=_resolved_context,
    )

    initial_events = [
        event
        async for event in runner.execute_stream(
            question="show all revenue",
            datasource_name="Revenue",
            session_id="sess_root_007",
        )
    ]
    assert initial_events[-1]["type"] == "interrupt"

    resumed_events = [
        event
        async for event in runner.resume_stream(
            question="show all revenue",
            resume_value=True,
            datasource_name="Revenue",
            session_id="sess_root_007",
            resume_strategy="root_graph_native",
        )
    ]

    _assert_complete_event(_non_thinking_events(resumed_events)[-1], status="ok")

    snapshot = await runner.aget_state_snapshot(session_id="sess_root_007")
    assert snapshot["pending_interrupt_type"] is None
    assert snapshot["approved_high_risk_signatures"] == ["sig-risk-001"]
    assert snapshot["complete_payload"] == {"status": "ok"}


@pytest.mark.asyncio
async def test_execute_stream_runs_without_parse_result_query_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_direct_round(monkeypatch)
    runner = RootGraphRunner(
        "alice",
        request_id="req_root_compile_only_001",
        auth_getter=_fake_auth_getter,
        semantic_graph_runner=_SemanticGraphRunnerStub(
            events_per_call=[[_make_parse_result_update(include_query=False)]]
        ),
        context_resolver=_resolved_context,
    )

    events = [
        event
        async for event in runner.execute_stream(
            question="show revenue",
            datasource_name="Revenue",
            session_id="sess_root_compile_only_001",
        )
    ]

    business_events = _non_thinking_events(events)
    assert [event["type"] for event in business_events] == [
        "parse_result",
        "data",
        "insight",
        "replan",
        "complete",
    ]
    _assert_complete_event(business_events[-1], status="ok")


@pytest.mark.asyncio
async def test_execute_stream_blocks_non_compiler_query_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_direct_round(monkeypatch, query_results=[])
    guarded_update = _make_parse_result_update()
    guarded_parse_result = guarded_update["feedback_learner"]["parse_result"]
    guarded_parse_result["query"] = {"query": "legacy-vizql", "kind": "vizql"}
    guarded_parse_result["semantic_guard"] = {
        **dict(guarded_parse_result["semantic_guard"]),
        "compiler_ready": False,
        "allowed_to_execute": False,
        "query_contract_mode": "vizql",
        "query_contract_source": "legacy_cache",
    }
    runner = RootGraphRunner(
        "alice",
        request_id="req_root_compile_guard_001",
        auth_getter=_fake_auth_getter,
        semantic_graph_runner=_SemanticGraphRunnerStub(events_per_call=[[guarded_update]]),
        context_resolver=_resolved_context,
    )

    events = [
        event
        async for event in runner.execute_stream(
            question="show revenue",
            datasource_name="Revenue",
            session_id="sess_root_compile_guard_001",
        )
    ]

    business_events = _non_thinking_events(events)
    assert [event["type"] for event in business_events] == [
        "parse_result",
        "error",
    ]
    assert "semantic_guard rejected compiler input" in business_events[1]["error"]


@pytest.mark.asyncio
async def test_execute_stream_simple_round_uses_answer_graph_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_direct_round(monkeypatch)
    captured: dict[str, Any] = {}

    async def _fake_answer_run(self, **kwargs: Any) -> dict[str, Any]:
        del self
        captured.update(kwargs)
        return {
            "insight_output_dict": {
                "summary": "answer_graph 已接管简单问题洞察。",
                "overall_confidence": 0.88,
                "findings": [],
            },
            "replan_decision": {
                "should_replan": False,
                "reason": "当前结论已经足够。",
                "suggested_questions": [],
                "candidate_questions": [],
            },
            "replan_projection": {
                "action": "stop",
                "selected_question": None,
                "interrupt_payload": None,
                "replan_event": {
                    "type": "replan",
                    "source": "single_query",
                    "mode": "user_select",
                    "action": "stop",
                    "shouldReplan": False,
                    "reason": "当前结论已经足够。",
                    "replanRoundLimitReached": False,
                    "newQuestion": None,
                    "selectedQuestion": None,
                    "questions": [],
                    "candidateQuestions": [],
                },
            },
        }

    monkeypatch.setattr(root_runner_module.AnswerGraphRunner, "run", _fake_answer_run)
    runner = RootGraphRunner(
        "alice",
        request_id="req_root_answer_runner_001",
        auth_getter=_fake_auth_getter,
        semantic_graph_runner=_SemanticGraphRunnerStub(),
        context_resolver=_resolved_context,
    )

    events = [
        event
        async for event in runner.execute_stream(
            question="show revenue",
            datasource_name="Revenue",
            session_id="sess_root_answer_runner_001",
        )
    ]

    business_events = _non_thinking_events(events)
    assert captured["source"] == "single_query"
    assert captured["question"] == "show revenue"
    assert captured["query_id"] == "q-root"
    assert [event["type"] for event in business_events] == [
        "parse_result",
        "data",
        "insight",
        "replan",
        "complete",
    ]
    assert business_events[2]["summary"] == "answer_graph 已接管简单问题洞察。"
    _assert_complete_event(business_events[-1], status="ok")


@pytest.mark.asyncio
async def test_execute_stream_projects_round_outputs_into_root_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_direct_round(
        monkeypatch,
        query_results=[_query_success_payload(
            row_count=24,
            truncated=False,
            result_manifest_ref="artifacts/runs/run_008/result/result_manifest.json",
        )],
        insight_results=[{
            "summary": "华东区销售额下降主要集中在直营渠道。",
            "overall_confidence": 0.91,
            "findings": [],
        }],
        replan_results=[{
            "should_replan": False,
            "reason": "当前结论已经足够。",
            "candidate_questions": [],
            "suggested_questions": [],
        }],
    )
    runner = RootGraphRunner(
        "alice",
        request_id="req_root_008",
        auth_getter=_fake_auth_getter,
        semantic_graph_runner=_SemanticGraphRunnerStub(),
        context_resolver=_resolved_context,
    )

    events = [
        event
        async for event in runner.execute_stream(
            question="show revenue",
            datasource_name="Revenue",
            session_id="sess_root_008",
        )
    ]

    business_events = _non_thinking_events(events)
    assert _thinking_events(events)
    assert [event["type"] for event in business_events] == [
        "parse_result",
        "data",
        "insight",
        "replan",
        "complete",
    ]

    snapshot = await runner.aget_state_snapshot(session_id="sess_root_008")
    assert snapshot["semantic_summary"]["measures"] == ["Sales"]
    assert snapshot["semantic_summary"]["dimensions"] == ["Region"]
    assert snapshot["semantic_summary"]["restated_question"] == "show revenue"
    assert snapshot["semantic_confidence"] == 0.93
    assert snapshot["candidate_fields_ref"] == (
        "kv://retrieval_memory/candidate_fields/ds-resolved/cache-q-root"
    )
    assert snapshot["candidate_values_ref"] == (
        "kv://retrieval_memory/candidate_values/ds-resolved/cache-q-root"
    )
    assert snapshot["fewshot_examples_ref"] == (
        "kv://retrieval_memory/fewshot_examples/ds-resolved/cache-q-root"
    )
    assert snapshot["retrieval_trace_ref"] == (
        "kv://retrieval_memory/retrieval_trace/ds-resolved/q-root"
    )
    assert snapshot["memory_write_refs"] == [
        "kv://retrieval_memory/memory_audit/ds-resolved/audit-q-root"
    ]
    assert snapshot["query_status"] == "completed"
    assert snapshot["row_count"] == 24
    assert snapshot["truncated"] is False
    assert snapshot["result_manifest_ref"] == "artifacts/runs/run_008/result/result_manifest.json"
    assert snapshot["answer_summary"] == "华东区销售额下降主要集中在直营渠道。"
    assert snapshot["followup_candidates"] == []
    assert snapshot["complete_payload"] == {"status": "ok"}


@pytest.mark.asyncio
async def test_execute_stream_propagates_feature_flags_into_semantic_input_and_root_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_direct_round(monkeypatch)
    semantic_stub = _SemanticGraphRunnerStub()
    runner = RootGraphRunner(
        "alice",
        request_id="req_root_feature_flag_001",
        auth_getter=_fake_auth_getter,
        semantic_graph_runner=semantic_stub,
        context_resolver=_resolved_context,
    )

    events = [
        event
        async for event in runner.execute_stream(
            question="show revenue",
            datasource_name="Revenue",
            feature_flags={"why_screening_wave": False},
            session_id="sess_root_feature_flag_001",
        )
    ]

    assert _non_thinking_events(events)[-1]["type"] == "complete"
    assert semantic_stub.build_input_calls[0]["feature_flags"] == {
        "why_screening_wave": False,
    }

    snapshot = await runner.aget_state_snapshot(
        session_id="sess_root_feature_flag_001"
    )
    assert snapshot["feature_flags"] == {"why_screening_wave": False}


@pytest.mark.asyncio
async def test_execute_stream_emits_context_observability_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_direct_round(monkeypatch)

    async def _resolved_degraded_context(state: dict[str, Any]) -> dict[str, Any]:
        return {
            "tenant_domain": "https://tableau.example.com",
            "tenant_site": "default",
            "tenant_auth_method": "pat",
            "datasource_luid": state.get("datasource_luid") or "ds-observe",
            "datasource_name": state.get("datasource_name"),
            "project_name": state.get("project_name"),
            "prepared_context_snapshot": _build_snapshot("ds-observe"),
            "artifact_freshness_report": {
                "metadata_snapshot": {
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
                "field_semantic_index": {
                    "status": "stale",
                    "required": False,
                    "degraded": True,
                    "reason": "schema_changed",
                    "degrade_mode": "read_stale",
                    "refresh_requested": True,
                    "refresh_scheduled": True,
                    "refresh_trigger": "schema_change",
                    "alert_required": False,
                },
                "field_values_index": {
                    "status": "building",
                    "required": False,
                    "degraded": True,
                    "reason": "refresh_scheduled",
                    "degrade_mode": "fallback_retrieval",
                    "refresh_requested": True,
                    "refresh_scheduled": True,
                    "refresh_trigger": "schema_change",
                    "alert_required": False,
                },
            },
            "artifact_refresh_request": {
                "datasource_luid": "ds-observe",
                "trigger": "schema_change",
                "requested_artifacts": [
                    "field_semantic_index",
                    "field_values_index",
                ],
                "prefer_incremental": True,
                "previous_schema_hash": "schema-old",
                "schema_hash": "schema-new",
                "refresh_reason": "schema changed",
            },
            "artifact_refresh_scheduled": True,
            "degrade_flags": [
                "semantic_retrieval_degraded",
                "value_retrieval_degraded",
            ],
            "degrade_details": [
                {
                    "artifact": "field_semantic_index",
                    "degrade_flag": "semantic_retrieval_degraded",
                    "status": "stale",
                    "reason": "schema_changed",
                    "degrade_mode": "read_stale",
                    "refresh_requested": True,
                    "refresh_scheduled": True,
                    "refresh_trigger": "schema_change",
                    "alert_required": False,
                },
                {
                    "artifact": "field_values_index",
                    "degrade_flag": "value_retrieval_degraded",
                    "status": "building",
                    "reason": "refresh_scheduled",
                    "degrade_mode": "fallback_retrieval",
                    "refresh_requested": True,
                    "refresh_scheduled": True,
                    "refresh_trigger": "schema_change",
                    "alert_required": False,
                },
            ],
            "memory_invalidation_report": {
                "trigger": "schema_change",
                "total_deleted": 4,
            },
            "pending_interrupt_type": None,
            "pending_interrupt_payload": None,
        }

    runner = RootGraphRunner(
        "alice",
        request_id="req_root_context_observe_001",
        auth_getter=_fake_auth_getter,
        semantic_graph_runner=_SemanticGraphRunnerStub(),
        context_resolver=_resolved_degraded_context,
    )

    events = [
        event
        async for event in runner.execute_stream(
            question="show revenue",
            datasource_name="Revenue",
            session_id="sess_root_context_observe_001",
        )
    ]

    business_events = _non_thinking_events(events)
    parse_event = next(event for event in business_events if event["type"] == "parse_result")
    complete_event = next(event for event in business_events if event["type"] == "complete")

    assert parse_event["semantic_guard"] == {
        "verified": True,
        "validation_mode": "deterministic",
        "corrected": False,
        "compiler_ready": True,
        "allowed_to_execute": True,
        "query_contract_mode": "compiler_input",
        "query_contract_source": "semantic_output",
        "error_count": 0,
        "filter_confirmation_count": 0,
        "needs_clarification": False,
        "needs_value_confirmation": False,
        "has_unresolvable_filters": False,
        "errors": [],
    }
    assert parse_event["degrade_flags"] == [
        "semantic_retrieval_degraded",
        "value_retrieval_degraded",
    ]
    assert parse_event["artifact_refresh_request"]["trigger"] == "schema_change"
    assert parse_event["artifact_refresh_scheduled"] is True
    assert parse_event["degrade_details"] == [
        {
            "artifact": "field_semantic_index",
            "degrade_flag": "semantic_retrieval_degraded",
            "status": "stale",
            "reason": "schema_changed",
            "degrade_mode": "read_stale",
            "refresh_requested": True,
            "refresh_scheduled": True,
            "refresh_trigger": "schema_change",
            "alert_required": False,
        },
        {
            "artifact": "field_values_index",
            "degrade_flag": "value_retrieval_degraded",
            "status": "building",
            "reason": "refresh_scheduled",
            "degrade_mode": "fallback_retrieval",
            "refresh_requested": True,
            "refresh_scheduled": True,
            "refresh_trigger": "schema_change",
            "alert_required": False,
        },
    ]
    assert parse_event["context_metrics"] == {
        "context_degraded": True,
        "artifact_refresh_requested": True,
        "artifact_refresh_scheduled": True,
        "artifact_refresh_schedule_failed": False,
        "refresh_trigger": "schema_change",
        "refresh_requested_artifacts": [
            "field_semantic_index",
            "field_values_index",
        ],
        "schema_change_invalidated": True,
        "has_stale_artifacts": True,
        "has_missing_artifacts": False,
        "degraded_artifacts": [
            "field_semantic_index",
            "field_values_index",
        ],
        "degrade_reason_codes": [
            "schema_changed",
            "refresh_scheduled",
        ],
        "requires_attention": False,
        "invalidation_trigger": "schema_change",
        "invalidation_total_deleted": 4,
        "artifact_statuses": {
            "metadata_snapshot": "ready",
            "field_semantic_index": "stale",
            "field_values_index": "building",
        },
    }
    assert complete_event["artifact_freshness_report"]["field_semantic_index"]["status"] == "stale"
    assert complete_event["artifact_refresh_scheduled"] is True
    assert complete_event["degrade_details"][0]["reason"] == "schema_changed"
    assert complete_event["memory_invalidation_report"] == {
        "trigger": "schema_change",
        "total_deleted": 4,
    }
    assert complete_event["context_metrics"]["context_degraded"] is True


@pytest.mark.asyncio
async def test_followup_interrupt_updates_root_state_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_direct_round(
        monkeypatch,
        replan_results=[
            {
                "should_replan": True,
                "reason": "可以继续拆到渠道维度。",
                "candidate_questions": [
                    {"id": "q1", "question": "show revenue by region"},
                    {"id": "q2", "question": "show revenue by channel"},
                ],
                "suggested_questions": [],
            },
            {
                "should_replan": False,
                "reason": "补查结果已经足够。",
                "candidate_questions": [],
                "suggested_questions": [],
            },
        ],
    )
    runner = RootGraphRunner(
        "alice",
        request_id="req_root_009",
        auth_getter=_fake_auth_getter,
        semantic_graph_runner=_SemanticGraphRunnerStub(
            events_per_call=[[_make_parse_result_update()], [_make_parse_result_update()]]
        ),
        context_resolver=_resolved_context,
    )

    initial_events = [
        event
        async for event in runner.execute_stream(
            question="show revenue",
            datasource_name="Revenue",
            session_id="sess_root_009",
        )
    ]

    assert initial_events[-1]["type"] == "interrupt"
    interrupted_snapshot = await runner.aget_state_snapshot(session_id="sess_root_009")
    assert interrupted_snapshot["pending_interrupt_type"] == "followup_select"
    assert interrupted_snapshot["followup_candidates"] == [
        {"id": "candidate_1", "question": "show revenue by region"},
        {"id": "candidate_2", "question": "show revenue by channel"},
    ]

    resumed_events = [
        event
        async for event in runner.resume_stream(
            question="show revenue by region",
            resume_value="show revenue by region",
            datasource_name="Revenue",
            session_id="sess_root_009",
            resume_strategy="root_graph_native",
        )
    ]

    assert _thinking_events(resumed_events)
    _assert_complete_event(_non_thinking_events(resumed_events)[-1], status="ok")
    resumed_snapshot = await runner.aget_state_snapshot(session_id="sess_root_009")
    assert resumed_snapshot["pending_interrupt_type"] is None
    assert resumed_snapshot["active_question"] == "show revenue by region"
    assert resumed_snapshot["followup_candidates"] == []
    assert resumed_snapshot["complete_payload"] == {"status": "ok"}


@pytest.mark.asyncio
async def test_execute_stream_converts_datasource_disambiguation_to_root_native_interrupt() -> None:
    runner = RootGraphRunner(
        "alice",
        request_id="req_root_010",
        auth_getter=_fake_auth_getter,
        semantic_graph_runner=_SemanticGraphRunnerStub(),
        context_resolver=_ambiguous_context,
    )

    events = [
        event
        async for event in runner.execute_stream(
            question="show revenue",
            datasource_name="Revenue",
            session_id="sess_root_010",
        )
    ]

    assert len(events) == 1
    assert events[0]["type"] == "interrupt"
    assert events[0]["interrupt_type"] == "datasource_disambiguation"
    assert events[0]["payload"]["resume_strategy"] == "root_graph_native"


@pytest.mark.asyncio
async def test_resume_stream_replays_root_graph_after_datasource_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_direct_round(monkeypatch)
    runner = RootGraphRunner(
        "alice",
        request_id="req_root_011",
        auth_getter=_fake_auth_getter,
        semantic_graph_runner=_SemanticGraphRunnerStub(),
        context_resolver=_ambiguous_context,
    )

    initial_events = [
        event
        async for event in runner.execute_stream(
            question="show revenue",
            datasource_name="Revenue",
            session_id="sess_root_011",
        )
    ]
    assert initial_events[-1]["type"] == "interrupt"

    resumed_events = [
        event
        async for event in runner.resume_stream(
            question="show revenue",
            resume_value={
                "datasource_luid": "ds-sales",
                "datasource_name": "Revenue",
                "project_name": "Sales",
            },
            datasource_name="Revenue",
            session_id="sess_root_011",
            resume_strategy="root_graph_native",
        )
    ]

    assert _thinking_events(resumed_events)
    _assert_complete_event(_non_thinking_events(resumed_events)[-1], status="ok")
    snapshot = await runner.aget_state_snapshot(session_id="sess_root_011")
    assert snapshot["pending_interrupt_type"] is None
    assert snapshot["datasource_luid"] == "ds-sales"
    assert snapshot["project_name"] == "Sales"


