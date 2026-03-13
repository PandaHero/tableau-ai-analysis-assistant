from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from analytics_assistant.src.orchestration.root_graph import RootGraphRunner
from analytics_assistant.src.orchestration.workflow.checkpoint import (
    reset_workflow_checkpointers,
)
from analytics_assistant.tests.orchestration.workflow.test_root_graph_runner import (
    _SemanticGraphRunnerStub,
    _fake_auth_getter,
    _make_multistep_planning_parse_result_update,
    _make_parse_result_update,
    _make_why_axis_planning_parse_result_update,
    _patch_direct_round,
    _resolved_context,
)

_GOLDEN_CASES_FILE = (
    Path(__file__).resolve().parent / "test_data" / "root_graph_golden_cases.yaml"
)


def _load_golden_cases() -> list[dict[str, Any]]:
    with open(_GOLDEN_CASES_FILE, "r", encoding="utf-8") as file:
        payload = yaml.safe_load(file) or {}
    return list(payload.get("cases") or [])


def _build_semantic_events(scenario: str) -> list[list[dict[str, Any]]]:
    if scenario == "simple":
        return [[_make_parse_result_update()]]
    if scenario == "complex":
        return [[_make_multistep_planning_parse_result_update()]]
    if scenario == "why":
        return [[_make_why_axis_planning_parse_result_update()]]
    raise AssertionError(f"未知 golden scenario: {scenario}")


def _normalize_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    business_events = [event for event in events if event.get("type") != "thinking"]
    planner_event = next((event for event in business_events if event["type"] == "planner"), None)
    replan_event = next((event for event in reversed(business_events) if event["type"] == "replan"), None)
    complete_event = next((event for event in reversed(business_events) if event["type"] == "complete"), None)

    return {
        "business_event_types": [event["type"] for event in business_events],
        "planner_plan_mode": planner_event.get("planMode") if planner_event else None,
        "planner_execution_strategy": (
            planner_event.get("executionStrategy") if planner_event else None
        ),
        "planner_step_titles": [
            str(step.get("title") or "")
            for step in (planner_event.get("steps") or [])
        ]
        if planner_event
        else [],
        "planner_step_kinds": [
            step.get("stepKind")
            for step in (planner_event.get("steps") or [])
        ]
        if planner_event
        else [],
        "insight_sources": list(dict.fromkeys(
            event.get("source")
            for event in business_events
            if event["type"] == "insight"
        )),
        "replan": {
            "source": replan_event.get("source") if replan_event else None,
            "mode": replan_event.get("mode") if replan_event else None,
            "action": replan_event.get("action") if replan_event else None,
            "should_replan": replan_event.get("shouldReplan") if replan_event else None,
            "candidate_count": len(replan_event.get("candidateQuestions") or [])
            if replan_event
            else None,
        },
        "complete_status": complete_event.get("status") if complete_event else None,
    }


def _shadow_compare(expected: Any, actual: Any, *, path: str = "") -> list[str]:
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return [f"{path or 'root'}: expected dict, got {type(actual).__name__}"]
        diffs: list[str] = []
        for key, value in expected.items():
            child_path = f"{path}.{key}" if path else str(key)
            diffs.extend(_shadow_compare(value, actual.get(key), path=child_path))
        return diffs

    if isinstance(expected, list):
        if not isinstance(actual, list):
            return [f"{path or 'root'}: expected list, got {type(actual).__name__}"]
        if expected != actual:
            return [f"{path or 'root'}: expected {expected!r}, got {actual!r}"]
        return []

    if expected != actual:
        return [f"{path or 'root'}: expected {expected!r}, got {actual!r}"]
    return []


@pytest.mark.asyncio
@pytest.mark.parametrize("case", _load_golden_cases(), ids=lambda case: case["id"])
async def test_root_graph_golden_cases_match_committed_snapshots(
    monkeypatch: pytest.MonkeyPatch,
    case: dict[str, Any],
) -> None:
    reset_workflow_checkpointers(clear_persisted_state=True)
    try:
        _patch_direct_round(monkeypatch)
        runner = RootGraphRunner(
            "alice",
            request_id=f"golden_{case['id']}",
            auth_getter=_fake_auth_getter,
            semantic_graph_runner=_SemanticGraphRunnerStub(
                events_per_call=_build_semantic_events(case["scenario"])
            ),
            context_resolver=_resolved_context,
        )
        events = [
            event
            async for event in runner.execute_stream(
                question=case["question"],
                datasource_name="Revenue",
                session_id=f"golden_{case['id']}",
            )
        ]
        actual_snapshot = _normalize_events(events)
        diffs = _shadow_compare(case["expected"], actual_snapshot)

        assert diffs == [], "golden snapshot mismatch:\n" + "\n".join(diffs)
    finally:
        reset_workflow_checkpointers(clear_persisted_state=True)


def test_shadow_compare_reports_differences() -> None:
    diffs = _shadow_compare(
        {"planner_plan_mode": "why_analysis", "replan": {"action": "stop"}},
        {"planner_plan_mode": "decomposed_query", "replan": {"action": "continue"}},
    )

    assert diffs == [
        "planner_plan_mode: expected 'why_analysis', got 'decomposed_query'",
        "replan.action: expected 'stop', got 'continue'",
    ]
