# -*- coding: utf-8 -*-
from pathlib import Path
from shutil import rmtree
from types import SimpleNamespace

import pytest

from analytics_assistant.src.core.schemas.execute_result import ColumnInfo, ExecuteResult
from analytics_assistant.src.orchestration.query_graph.artifacts import (
    materialize_result_artifacts,
)
from analytics_assistant.src.orchestration.query_graph.service import (
    build_high_risk_interrupt_payload,
    execute_semantic_query,
    table_data_to_execute_result,
)
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
    path = Path("analytics_assistant/tests/.tmp/query_graph_service")
    if path.exists():
        rmtree(path)
    path.mkdir(parents=True, exist_ok=True)
    yield path
    if path.exists():
        rmtree(path)


@pytest.mark.asyncio
async def test_execute_semantic_query_returns_existing_table_data_shape(artifact_root: Path):
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
        data_model=SimpleNamespace(),
        field_samples={"Region": {"sample_values": ["East"]}},
        platform_adapter=adapter,
        auth=SimpleNamespace(api_key="k", site="site-a"),
    )

    result = await execute_semantic_query(
        ctx=ctx,
        datasource_luid="ds-1",
        semantic_raw=_semantic_raw(),
        request_id="req-1",
        run_id="run-query-1",
        artifact_root_dir=str(artifact_root),
    )

    assert result["success"] is True
    assert result["tableData"]["rowCount"] == 1
    assert result["tableData"]["executionTimeMs"] == 42
    assert result["tableData"]["columns"][0]["name"] == "Region"
    assert result["result_manifest_ref"] == "artifacts/runs/run-query-1/result/result_manifest.json"
    assert result["profiles_ref"] == "artifacts/runs/run-query-1/result/profiles/"
    assert result["chunks_ref"] == "artifacts/runs/run-query-1/result/chunks/"
    assert (artifact_root / "runs" / "run-query-1" / "result" / "result_manifest.json").exists()
    assert adapter.calls[0]["datasource_id"] == "ds-1"
    assert adapter.calls[0]["api_key"] == "k"
    assert adapter.calls[0]["site"] == "site-a"


@pytest.mark.asyncio
async def test_execute_semantic_query_sanitizes_platform_errors():
    adapter = _DummyAdapter(RuntimeError("backend exploded"))
    ctx = WorkflowContext(
        datasource_luid="ds-1",
        platform_adapter=adapter,
    )

    result = await execute_semantic_query(
        ctx=ctx,
        datasource_luid="ds-1",
        semantic_raw=_semantic_raw(),
        request_id="req-2",
    )

    assert result["success"] is False
    assert "查询执行失败" in result["error"]


def test_materialize_result_artifacts_writes_manifest_chunks_and_profiles(artifact_root: Path):
    execute_result = ExecuteResult(
        data=[
            {"Region": "East", "Sales": 10},
            {"Region": "West", "Sales": 12},
            {"Region": "South", "Sales": 9},
        ],
        columns=[
            ColumnInfo(name="Region", data_type="STRING", is_dimension=True),
            ColumnInfo(name="Sales", data_type="NUMBER", is_measure=True),
        ],
        row_count=3,
        execution_time_ms=11,
        query_id="q-manifest",
    )

    artifact_payload = materialize_result_artifacts(
        execute_result=execute_result,
        run_id="run-artifacts-1",
        artifact_root_dir=artifact_root,
        preview_row_limit=2,
        chunk_row_limit=2,
    )

    assert artifact_payload["truncated"] is True
    assert artifact_payload["result_manifest_ref"] == "artifacts/runs/run-artifacts-1/result/result_manifest.json"
    assert artifact_payload["profiles_ref"] == "artifacts/runs/run-artifacts-1/result/profiles/"
    assert artifact_payload["chunks_ref"] == "artifacts/runs/run-artifacts-1/result/chunks/"
    assert artifact_payload["preview_table_data"]["rowCount"] == 3
    assert len(artifact_payload["preview_table_data"]["rows"]) == 2
    assert len(artifact_payload["allowed_files"]) == 4

    manifest_path = artifact_root / "runs" / "run-artifacts-1" / "result" / "result_manifest.json"
    assert manifest_path.exists()
    manifest = manifest_path.read_text(encoding="utf-8")
    assert "preview.json" in manifest
    assert "profiles/data_profile.json" in manifest
    assert "chunks/chunk_0001.jsonl" in manifest


def test_table_data_to_execute_result_normalizes_sequence_rows():
    execute_result = table_data_to_execute_result(
        {
            "columns": [
                {"name": "Region", "dataType": "STRING", "isDimension": True},
                {"name": "Sales", "dataType": "NUMBER", "isMeasure": True},
            ],
            "rows": [["East", 10], ["West", 12]],
            "rowCount": 2,
            "executionTimeMs": 9,
        },
        query_id="query-1",
    )

    assert execute_result is not None
    assert execute_result.query_id == "query-1"
    assert execute_result.data == [
        {"Region": "East", "Sales": 10},
        {"Region": "West", "Sales": 12},
    ]
    assert execute_result.columns[0].is_dimension is True


def test_build_high_risk_interrupt_payload_for_broad_dimension_query():
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
    )

    payload = build_high_risk_interrupt_payload(
        ctx=ctx,
        datasource_luid="ds-risk",
        semantic_raw={
            "restated_question": "Show sales by region",
            "what": {"measures": [{"field_name": "Sales"}]},
            "where": {
                "dimensions": [{"field_name": "Region"}],
                "filters": [],
            },
        },
    )

    assert payload is not None
    assert payload["risk_level"] == "high"
    assert payload["estimated_rows"] >= 9000
    assert payload["dimensions"][0]["field_name"] == "Region"


def test_build_high_risk_interrupt_payload_skips_confirmed_signature():
    ctx = WorkflowContext(
        datasource_luid="ds-risk",
        field_samples={"Region": {"unique_count": 9000}},
    )
    semantic_raw = {
        "restated_question": "Show sales by region",
        "what": {"measures": [{"field_name": "Sales"}]},
        "where": {"dimensions": [{"field_name": "Region"}], "filters": []},
    }

    initial_payload = build_high_risk_interrupt_payload(
        ctx=ctx,
        datasource_luid="ds-risk",
        semantic_raw=semantic_raw,
    )

    skipped_payload = build_high_risk_interrupt_payload(
        ctx=ctx,
        datasource_luid="ds-risk",
        semantic_raw=semantic_raw,
        confirmed_signatures={initial_payload["risk_signature"]},
    )

    assert initial_payload is not None
    assert skipped_payload is None
