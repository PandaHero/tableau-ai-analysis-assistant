# -*- coding: utf-8 -*-
from pathlib import Path
from shutil import rmtree
from types import SimpleNamespace

import pytest

from analytics_assistant.src.core.schemas.execute_result import ColumnInfo, ExecuteResult
from analytics_assistant.src.orchestration.query_graph import QueryGraphRunner
from analytics_assistant.src.orchestration.workflow.context import WorkflowContext


class _DummyAdapter:
    def __init__(self, result: ExecuteResult | Exception):
        self._result = result
        self.calls: list[dict[str, object]] = []

    async def execute_query(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


def _semantic_raw() -> dict[str, object]:
    return {
        "query_id": "semantic-1",
        "restated_question": "Show sales by region",
        "what": {"measures": [{"field_name": "Sales"}]},
        "where": {"dimensions": [{"field_name": "Region"}], "filters": []},
        "self_check": {
            "field_mapping_confidence": 0.9,
            "time_range_confidence": 0.9,
            "computation_confidence": 0.9,
            "overall_confidence": 0.9,
            "potential_issues": [],
        },
    }


@pytest.fixture
def artifact_root() -> Path:
    path = Path("analytics_assistant/tests/.tmp/query_graph_runner")
    if path.exists():
        rmtree(path)
    path.mkdir(parents=True, exist_ok=True)
    yield path
    if path.exists():
        rmtree(path)


@pytest.mark.asyncio
async def test_query_graph_runner_executes_query_when_risk_guard_passes(artifact_root: Path):
    adapter = _DummyAdapter(
        ExecuteResult(
            data=[{"Region": "East", "Sales": 10}],
            columns=[
                ColumnInfo(name="Region", data_type="STRING", is_dimension=True),
                ColumnInfo(name="Sales", data_type="NUMBER", is_measure=True),
            ],
            row_count=1,
            execution_time_ms=42,
            query_id="q-1",
        )
    )
    ctx = WorkflowContext(
        datasource_luid="ds-1",
        data_model=SimpleNamespace(get_field=lambda _name: None),
        field_samples={"Region": {"sample_values": ["East"]}},
        platform_adapter=adapter,
        auth=SimpleNamespace(api_key="k", site="site-a"),
    )
    runner = QueryGraphRunner(request_id="req-query-1", artifact_root_dir=str(artifact_root))

    state = await runner.run(
        ctx=ctx,
        datasource_luid="ds-1",
        semantic_raw=_semantic_raw(),
        run_id="run-query-graph-1",
    )

    assert state["high_risk_payload"] is None
    assert state["query_failed"] is False
    assert state["query_execution"]["success"] is True
    assert state["table_data"]["rowCount"] == 1
    assert state["result_manifest_ref"] == "artifacts/runs/run-query-graph-1/result/result_manifest.json"
    assert state["profiles_ref"] == "artifacts/runs/run-query-graph-1/result/profiles/"
    assert state["chunks_ref"] == "artifacts/runs/run-query-graph-1/result/chunks/"
    assert state["execute_result_model"].row_count == 1
    assert (artifact_root / "runs" / "run-query-graph-1" / "result" / "result_manifest.json").exists()
    assert adapter.calls[0]["datasource_id"] == "ds-1"


@pytest.mark.asyncio
async def test_query_graph_runner_stops_at_high_risk_guard():
    class _DataModel:
        def get_field(self, field_name: str):
            return SimpleNamespace(name=field_name, caption=field_name)

    ctx = WorkflowContext(
        datasource_luid="ds-risk",
        data_model=_DataModel(),
        field_samples={
            "Region": {
                "unique_count": 9000,
                "sample_values": ["East", "West"],
            }
        },
        platform_adapter=_DummyAdapter(
            ExecuteResult(data=[], columns=[], row_count=0, execution_time_ms=0)
        ),
    )
    runner = QueryGraphRunner(request_id="req-query-2")

    state = await runner.run(
        ctx=ctx,
        datasource_luid="ds-risk",
        semantic_raw=_semantic_raw(),
    )

    assert state["high_risk_payload"] is not None
    assert state["high_risk_payload"]["risk_level"] == "high"
    assert state["query_execution"] is None
    assert state["table_data"] is None


@pytest.mark.asyncio
async def test_query_graph_runner_captures_query_failure_payload():
    adapter = _DummyAdapter(RuntimeError("backend exploded"))
    ctx = WorkflowContext(
        datasource_luid="ds-1",
        data_model=SimpleNamespace(get_field=lambda _name: None),
        field_samples={"Region": {"sample_values": ["East"]}},
        platform_adapter=adapter,
    )
    runner = QueryGraphRunner(request_id="req-query-3")

    state = await runner.run(
        ctx=ctx,
        datasource_luid="ds-1",
        semantic_raw=_semantic_raw(),
        confirmed_high_risk_signatures=["already-approved"],
    )

    assert state["high_risk_payload"] is None
    assert state["query_failed"] is True
    assert state["query_execution"]["success"] is False
    assert state["query_error"]
