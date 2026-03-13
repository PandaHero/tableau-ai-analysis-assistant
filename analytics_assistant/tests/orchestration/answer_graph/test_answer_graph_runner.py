# -*- coding: utf-8 -*-
import asyncio
from pathlib import Path
from shutil import rmtree

import pytest

from analytics_assistant.src.agents.replanner.schemas.output import ReplanDecision
from analytics_assistant.src.core.schemas.execute_result import ColumnInfo, ExecuteResult
from analytics_assistant.src.orchestration.answer_graph import service as answer_service
from analytics_assistant.src.orchestration.answer_graph.graph import AnswerGraphRunner
from analytics_assistant.src.orchestration.query_graph.artifacts import materialize_result_artifacts


class _InsightStub:
    def model_dump(self):
        return {
            "summary": "直营渠道贡献了主要降幅。",
            "overall_confidence": 0.82,
            "findings": [
                {
                    "finding_type": "anomaly",
                    "analysis_level": "diagnostic",
                    "description": "直营渠道降幅最大。",
                    "confidence": 0.82,
                    "supporting_data": {"channel": "直营"},
                }
            ],
        }

    @property
    def findings(self):
        return [1]


async def _fake_insight_agent(**kwargs):
    assert kwargs.get("result_manifest_ref")
    assert kwargs.get("workspace") is not None
    return _InsightStub()


async def _fake_replanner_agent(**kwargs):
    assert "data_profile_dict" not in kwargs
    assert isinstance(kwargs.get("evidence_bundle_dict"), dict)
    return ReplanDecision(
        should_replan=True,
        reason="可以继续按产品线下钻。",
        new_question="按产品线继续分析",
        suggested_questions=["按渠道继续分析"],
    )


async def _should_not_run_insight(**kwargs):
    raise AssertionError("prebuilt insight path should not invoke insight agent")


@pytest.fixture
def artifact_root() -> Path:
    path = Path("analytics_assistant/tests/.tmp/answer_graph_runner")
    if path.exists():
        rmtree(path)
    path.mkdir(parents=True, exist_ok=True)
    yield path
    if path.exists():
        rmtree(path)



def _make_execute_result() -> ExecuteResult:
    return ExecuteResult(
        data=[{"Region": "East", "Sales": 10}],
        columns=[
            ColumnInfo(name="Region", data_type="STRING", is_dimension=True),
            ColumnInfo(name="Sales", data_type="NUMBER", is_measure=True),
        ],
        row_count=1,
        execution_time_ms=11,
        query_id="q-1",
    )



def test_answer_graph_runner_single_query_chain(artifact_root: Path):
    bundle = materialize_result_artifacts(
        execute_result=_make_execute_result(),
        run_id="run-answer-1",
        artifact_root_dir=artifact_root,
    )
    runner = AnswerGraphRunner(
        invoke_insight_agent=_fake_insight_agent,
        invoke_replanner_agent=_fake_replanner_agent,
        request_id="req-1",
    )
    result = asyncio.run(
        runner.run(
            source="single_query",
            question="为什么销售下降",
            semantic_raw={"restated_question": "为什么销售下降"},
            result_manifest_ref=bundle["result_manifest_ref"],
            artifact_root_dir=str(artifact_root),
            conversation_history=[],
            replan_history=[],
            analysis_depth="detailed",
            replan_mode="user_select",
            field_semantic={},
            query_id="q-1",
            session_id="sess-answer-1",
        )
    )

    assert result["insight_output_dict"]["summary"] == "直营渠道贡献了主要降幅。"
    assert result["evidence_bundle_dict"]["result_profile"]["row_count"] == 1
    assert result["workspace"].run_id == "run-answer-1"
    assert result["replan_projection"]["action"] == "await_user_select"
    assert result["replan_projection"]["interrupt_payload"] is not None



def test_answer_graph_runner_builds_insight_from_evidence_bundle_for_planner_synthesis():
    runner = AnswerGraphRunner(
        invoke_insight_agent=_should_not_run_insight,
        invoke_replanner_agent=_fake_replanner_agent,
        request_id="req-2",
    )
    result = asyncio.run(
        runner.run(
            source="planner_synthesis",
            question="为什么销售下降",
            semantic_raw={"restated_question": "为什么销售下降"},
            evidence_bundle_dict={
                "source": "planner_synthesis",
                "question": "为什么销售下降",
                "latest_summary": "多步证据表明直营渠道贡献了主要降幅。",
                "step_count": 2,
                "validated_axes": ["渠道"],
                "anomalous_entities": ["直营渠道"],
                "step_artifacts": [
                    {
                        "step_id": "step-4",
                        "title": "定位异常切片",
                        "table_summary": "直营渠道贡献了主要降幅。",
                        "validated_axes": ["渠道"],
                    }
                ],
            },
            conversation_history=[],
            replan_history=[{"new_question": "按产品线继续分析"}],
            analysis_depth="detailed",
            replan_mode="auto_continue",
            field_semantic={},
        )
    )

    assert result["insight_output_dict"]["summary"].startswith("多步证据")
    assert result["insight_output_dict"]["findings"]
    assert result["replan_projection"]["action"] == "auto_continue"
    assert result["replan_projection"]["selected_question"] == "按渠道继续分析"


def test_answer_graph_runner_stops_when_replan_limit_reached(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(answer_service, "_get_max_replan_rounds", lambda: 1)
    runner = AnswerGraphRunner(
        invoke_insight_agent=_should_not_run_insight,
        invoke_replanner_agent=_fake_replanner_agent,
        request_id="req-3",
    )
    result = asyncio.run(
        runner.run(
            source="planner_synthesis",
            question="为什么销售下降",
            semantic_raw={"restated_question": "为什么销售下降"},
            evidence_bundle_dict={
                "source": "planner_synthesis",
                "question": "为什么销售下降",
                "latest_summary": "直营渠道贡献了主要降幅。",
                "step_count": 1,
                "step_artifacts": [
                    {
                        "step_id": "step-4",
                        "title": "定位异常切片",
                        "table_summary": "直营渠道贡献了主要降幅。",
                    }
                ],
            },
            conversation_history=[],
            replan_history=[{"new_question": "按产品线继续分析"}],
            analysis_depth="detailed",
            replan_mode="user_select",
            field_semantic={},
        )
    )

    assert result["replan_projection"]["action"] == "stop"
    assert result["replan_projection"]["candidate_questions"] == []
    assert result["replan_projection"]["interrupt_payload"] is None
    assert result["replan_projection"]["replan_event"]["replanRoundLimitReached"] is True


def test_answer_graph_runner_emits_stage_callbacks(artifact_root: Path):
    bundle = materialize_result_artifacts(
        execute_result=_make_execute_result(),
        run_id="run-answer-stage",
        artifact_root_dir=artifact_root,
    )
    runner = AnswerGraphRunner(
        invoke_insight_agent=_fake_insight_agent,
        invoke_replanner_agent=_fake_replanner_agent,
        request_id="req-stage",
    )
    stage_events: list[tuple[str, str]] = []

    async def _on_stage(stage: str, status: str) -> None:
        stage_events.append((stage, status))

    result = asyncio.run(
        runner.run(
            source="single_query",
            question="为什么销售下降",
            semantic_raw={"restated_question": "为什么销售下降"},
            result_manifest_ref=bundle["result_manifest_ref"],
            artifact_root_dir=str(artifact_root),
            conversation_history=[],
            replan_history=[],
            analysis_depth="detailed",
            replan_mode="user_select",
            field_semantic={},
            query_id="q-stage",
            session_id="sess-stage",
            on_stage=_on_stage,
        )
    )

    assert result["insight_output_dict"]["summary"] == "直营渠道贡献了主要降幅。"
    assert stage_events == [
        ("generating", "running"),
        ("generating", "completed"),
        ("replanning", "running"),
        ("replanning", "completed"),
    ]
