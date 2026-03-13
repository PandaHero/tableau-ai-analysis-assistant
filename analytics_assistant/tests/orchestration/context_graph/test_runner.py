# -*- coding: utf-8 -*-
import hashlib
from typing import Any
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from langgraph.store.memory import InMemoryStore

from analytics_assistant.src.orchestration.context_graph import ContextGraphRunner
from analytics_assistant.src.core.schemas.data_model import DataModel
from analytics_assistant.src.agents.semantic_parser.components import (
    QueryCache,
    compute_question_hash,
)
from analytics_assistant.src.agents.semantic_parser.components.feedback_learner import (
    FeedbackLearner,
)
from analytics_assistant.src.agents.semantic_parser.schemas.cache import CachedQuery
from analytics_assistant.src.orchestration.retrieval_memory import (
    MemoryInvalidationService,
    MemoryStore,
)
from analytics_assistant.src.orchestration.workflow.context import PreparedContextSnapshot
from analytics_assistant.src.platform.tableau.artifact_keys import (
    build_field_artifact_key,
    build_metadata_snapshot_cache_key,
)
from analytics_assistant.src.platform.tableau.client import TableauDatasourceAmbiguityError


class _DummyVizQLClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None


class _Loader:
    def __init__(self, result):
        self._result = result

    async def load_data_model(self, **_kwargs):
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


@pytest.mark.asyncio
async def test_context_graph_runner_builds_prepared_context_snapshot():
    auth = SimpleNamespace(
        api_key="k",
        site="default",
        domain="https://tableau.example.com",
        auth_method="pat",
    )
    data_model = DataModel(
        datasource_id="ds-sales",
    )
    data_model._field_samples_cache = {"Region": {"sample_values": ["East"]}}
    runner = ContextGraphRunner(
        tableau_username="alice",
        request_id="req-context-1",
        auth_getter=AsyncMock(return_value=auth),
        vizql_client_factory=_DummyVizQLClient,
        data_loader_factory=lambda _client: _Loader(data_model),
        prewarm_scheduler=lambda **_kwargs: False,
    )

    async def _fake_load_field_semantic(self, **_kwargs):
        return self.model_copy(update={
            "field_semantic": {"Region": {"category": "geography"}},
        })

    with patch(
        "analytics_assistant.src.orchestration.context_graph.graph.WorkflowContext.load_field_semantic",
        new=_fake_load_field_semantic,
    ):
        state = await runner.run(datasource_name="Revenue")

    assert state["tenant_domain"] == "https://tableau.example.com"
    assert state["tenant_site"] == "default"
    assert state["tenant_auth_method"] == "pat"
    assert state["datasource_luid"] == "ds-sales"
    assert state["prepared_context_snapshot"] is not None
    snapshot = PreparedContextSnapshot.model_validate(state["prepared_context_snapshot"])
    assert snapshot.datasource_luid == "ds-sales"
    assert state["field_semantic_available"] is True
    assert state["field_samples_available"] is True
    assert state["datasource_prewarm_scheduled"] is False
    assert state["artifact_refresh_scheduled"] is False
    report = state["artifact_freshness_report"]
    assert report["metadata_snapshot"]["artifact_key"] == build_metadata_snapshot_cache_key(
        datasource_id="ds-sales",
        site="default",
        schema_hash=hashlib.md5(b"empty").hexdigest(),
    )
    assert report["metadata_snapshot"]["status"] == "ready"
    assert report["metadata_snapshot"]["reason"] == "metadata_ready"
    assert report["field_semantic_index"]["artifact_key"] == build_field_artifact_key(
        datasource_id="ds-sales",
        site="default",
        artifact_type="field_semantic_index",
        schema_hash=hashlib.md5(b"empty").hexdigest(),
    )
    assert report["field_semantic_index"]["status"] == "ready"
    assert report["field_semantic_index"]["reason"] == "artifact_ready"
    assert report["field_semantic_index"]["degrade_mode"] == "none"
    assert report["field_values_index"]["artifact_key"] == build_field_artifact_key(
        datasource_id="ds-sales",
        site="default",
        artifact_type="field_values_index",
        schema_hash=hashlib.md5(b"empty").hexdigest(),
    )
    assert report["field_values_index"]["status"] == "ready"
    assert report["field_values_index"]["reason"] == "artifact_ready"
    assert report["field_values_index"]["degrade_mode"] == "none"
    assert state["degrade_flags"] == []
    assert state["degrade_details"] == []


@pytest.mark.asyncio
async def test_context_graph_runner_reports_degraded_artifact_freshness():
    auth = SimpleNamespace(
        api_key="k",
        site="default",
        domain="https://tableau.example.com",
        auth_method="pat",
    )
    data_model = DataModel(
        datasource_id="ds-sales",
    )
    scheduled_requests: list[dict[str, Any]] = []

    def _capture_prewarm(**kwargs: Any) -> bool:
        scheduled_requests.append(dict(kwargs))
        return True

    runner = ContextGraphRunner(
        tableau_username="alice",
        request_id="req-context-1b",
        auth_getter=AsyncMock(return_value=auth),
        vizql_client_factory=_DummyVizQLClient,
        data_loader_factory=lambda _client: _Loader(data_model),
        prewarm_scheduler=_capture_prewarm,
    )

    async def _fake_load_field_semantic(self, **_kwargs):
        return self

    with patch(
        "analytics_assistant.src.orchestration.context_graph.graph.WorkflowContext.load_field_semantic",
        new=_fake_load_field_semantic,
    ):
        state = await runner.run(datasource_name="Revenue")

    assert state["field_semantic_available"] is False
    assert state["field_samples_available"] is False
    assert state["datasource_prewarm_scheduled"] is True
    assert state["artifact_refresh_scheduled"] is True
    report = state["artifact_freshness_report"]
    assert report["metadata_snapshot"]["artifact_key"] == build_metadata_snapshot_cache_key(
        datasource_id="ds-sales",
        site="default",
        schema_hash=hashlib.md5(b"empty").hexdigest(),
    )
    assert report["metadata_snapshot"]["status"] == "ready"
    assert report["metadata_snapshot"]["reason"] == "metadata_ready"
    assert report["field_semantic_index"]["artifact_key"] == build_field_artifact_key(
        datasource_id="ds-sales",
        site="default",
        artifact_type="field_semantic_index",
        schema_hash=hashlib.md5(b"empty").hexdigest(),
    )
    assert report["field_semantic_index"]["status"] == "building"
    assert report["field_semantic_index"]["reason"] == "refresh_scheduled"
    assert report["field_semantic_index"]["degrade_mode"] == "fallback_retrieval"
    assert report["field_semantic_index"]["refresh_requested"] is True
    assert report["field_semantic_index"]["refresh_scheduled"] is True
    assert report["field_values_index"]["artifact_key"] == build_field_artifact_key(
        datasource_id="ds-sales",
        site="default",
        artifact_type="field_values_index",
        schema_hash=hashlib.md5(b"empty").hexdigest(),
    )
    assert report["field_values_index"]["status"] == "building"
    assert report["field_values_index"]["reason"] == "refresh_scheduled"
    assert report["field_values_index"]["degrade_mode"] == "fallback_retrieval"
    assert state["degrade_flags"] == [
        "semantic_retrieval_degraded",
        "value_retrieval_degraded",
    ]
    assert state["degrade_details"] == [
        {
            "artifact": "field_semantic_index",
            "degrade_flag": "semantic_retrieval_degraded",
            "status": "building",
            "reason": "refresh_scheduled",
            "degrade_mode": "fallback_retrieval",
            "refresh_requested": True,
            "refresh_scheduled": True,
            "refresh_trigger": "missing_artifacts",
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
            "refresh_trigger": "missing_artifacts",
            "alert_required": False,
        },
    ]
    assert state["artifact_refresh_request"] == {
        "datasource_luid": "ds-sales",
        "trigger": "missing_artifacts",
        "requested_artifacts": [
            "field_semantic_index",
            "field_values_index",
        ],
        "prefer_incremental": True,
        "previous_schema_hash": None,
        "schema_hash": hashlib.md5(b"empty").hexdigest(),
        "refresh_reason": "字段语义或字段值产物缺失，已安排后台补齐。",
    }
    assert len(scheduled_requests) == 1
    assert scheduled_requests[0]["refresh_request"] == state["artifact_refresh_request"]


@pytest.mark.asyncio
async def test_context_graph_runner_marks_stale_artifacts_when_schema_changes():
    auth = SimpleNamespace(
        api_key="k",
        site="default",
        domain="https://tableau.example.com",
        auth_method="pat",
    )
    data_model = DataModel(datasource_id="ds-sales")
    data_model._field_samples_cache = {"Region": {"sample_values": ["East"]}}
    scheduled_requests: list[dict[str, Any]] = []

    def _capture_prewarm(**kwargs: Any) -> bool:
        scheduled_requests.append(dict(kwargs))
        return True

    runner = ContextGraphRunner(
        tableau_username="alice",
        request_id="req-context-stale-1",
        auth_getter=AsyncMock(return_value=auth),
        vizql_client_factory=_DummyVizQLClient,
        data_loader_factory=lambda _client: _Loader(data_model),
        prewarm_scheduler=_capture_prewarm,
    )

    async def _fake_load_field_semantic(self, **_kwargs):
        return self.model_copy(update={
            "field_semantic": {"Region": {"category": "geography"}},
        })

    with patch(
        "analytics_assistant.src.orchestration.context_graph.graph.WorkflowContext.load_field_semantic",
        new=_fake_load_field_semantic,
    ):
        state = await runner.run(
            datasource_name="Revenue",
            previous_schema_hash="schema-old",
        )

    assert state["artifact_refresh_scheduled"] is True
    report = state["artifact_freshness_report"]
    assert report["metadata_snapshot"]["artifact_key"] == build_metadata_snapshot_cache_key(
        datasource_id="ds-sales",
        site="default",
        schema_hash=hashlib.md5(b"empty").hexdigest(),
    )
    assert report["metadata_snapshot"]["status"] == "ready"
    assert report["field_semantic_index"]["status"] == "stale"
    assert report["field_semantic_index"]["reason"] == "schema_changed"
    assert report["field_semantic_index"]["degrade_mode"] == "read_stale"
    assert report["field_semantic_index"]["refresh_trigger"] == "schema_change"
    assert report["field_values_index"]["status"] == "stale"
    assert report["field_values_index"]["reason"] == "schema_changed"
    assert report["field_values_index"]["degrade_mode"] == "read_stale"
    assert state["degrade_flags"] == [
        "semantic_retrieval_degraded",
        "value_retrieval_degraded",
    ]
    assert state["degrade_details"] == [
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
            "status": "stale",
            "reason": "schema_changed",
            "degrade_mode": "read_stale",
            "refresh_requested": True,
            "refresh_scheduled": True,
            "refresh_trigger": "schema_change",
            "alert_required": False,
        },
    ]
    assert state["artifact_refresh_request"] == {
        "datasource_luid": "ds-sales",
        "trigger": "schema_change",
        "requested_artifacts": [
            "field_semantic_index",
            "field_values_index",
        ],
        "prefer_incremental": True,
        "previous_schema_hash": "schema-old",
        "schema_hash": hashlib.md5(b"empty").hexdigest(),
        "refresh_reason": "schema 变化后需要失效旧产物，并优先做增量重建。",
    }
    assert len(scheduled_requests) == 1
    assert scheduled_requests[0]["refresh_request"] == state["artifact_refresh_request"]


@pytest.mark.asyncio
async def test_context_graph_runner_returns_datasource_disambiguation_interrupt():
    auth = SimpleNamespace(
        api_key="k",
        site="default",
        domain="https://tableau.example.com",
        auth_method="pat",
    )
    ambiguity = TableauDatasourceAmbiguityError(
        "multiple matches",
        datasource_name="Revenue",
        project_name="Sales",
        choices=[
            {"datasource_luid": "ds-sales", "name": "Revenue", "project": "Sales"},
            {"datasource_luid": "ds-ops", "name": "Revenue", "project": "Ops"},
        ],
    )
    runner = ContextGraphRunner(
        tableau_username="alice",
        request_id="req-context-2",
        auth_getter=AsyncMock(return_value=auth),
        vizql_client_factory=_DummyVizQLClient,
        data_loader_factory=lambda _client: _Loader(ambiguity),
        prewarm_scheduler=lambda **_kwargs: False,
    )

    state = await runner.run(datasource_name="Revenue")

    assert state["prepared_context_snapshot"] is None
    assert state["pending_interrupt_type"] == "datasource_disambiguation"
    assert state["pending_interrupt_payload"]["resume_strategy"] == "root_graph_native"
    assert len(state["pending_interrupt_payload"]["choices"]) == 2


@pytest.mark.asyncio
async def test_context_graph_runner_invalidates_memory_when_schema_changes():
    auth = SimpleNamespace(
        api_key="k",
        site="default",
        domain="https://tableau.example.com",
        auth_method="pat",
    )
    store = InMemoryStore()
    query_cache = QueryCache(store=store)
    memory_store = MemoryStore(store=store)
    learner = FeedbackLearner(store=store, auto_promote_enabled=False)
    invalidation_service = MemoryInvalidationService(
        store=store,
        query_cache_getter=lambda: query_cache,
    )
    data_model = DataModel(datasource_id="ds-sales")

    store.put(
        ("semantic_parser", "query_cache", "ds-sales"),
        compute_question_hash("show revenue", "ds-sales"),
        CachedQuery(
            question="show revenue",
            question_hash=compute_question_hash("show revenue", "ds-sales"),
            datasource_luid="ds-sales",
            scope_key="global",
            schema_hash="schema-old",
            semantic_output={"restated_question": "show revenue"},
            query={"kind": "vizql", "query": "select 1"},
            expires_at=datetime(2026, 3, 13, 9, 0, 0),
        ).model_dump(mode="json"),
    )
    memory_store.put_candidate_fields(
        question="show revenue",
        datasource_luid="ds-sales",
        schema_hash="schema-old",
        payload={"candidate_fields": [{"field_name": "Region"}]},
    )
    await learner.learn_filter_value_correction(
        field_name="Region",
        original_value="East",
        confirmed_value="East",
        datasource_luid="ds-sales",
    )
    await learner.learn_synonym(
        original_term="gmv",
        correct_field="sales",
        datasource_luid="ds-sales",
    )

    runner = ContextGraphRunner(
        tableau_username="alice",
        request_id="req-context-schema-change",
        auth_getter=AsyncMock(return_value=auth),
        vizql_client_factory=_DummyVizQLClient,
        data_loader_factory=lambda _client: _Loader(data_model),
        prewarm_scheduler=lambda **_kwargs: False,
        memory_invalidation_service=invalidation_service,
    )

    async def _fake_load_field_semantic(self, **_kwargs):
        return self

    with patch(
        "analytics_assistant.src.orchestration.context_graph.graph.WorkflowContext.load_field_semantic",
        new=_fake_load_field_semantic,
    ):
        state = await runner.run(
            datasource_name="Revenue",
            previous_schema_hash="schema-old",
        )

    report = state["memory_invalidation_report"]
    assert report["trigger"] == "schema_change"
    assert report["query_cache_deleted"] == 1
    assert report["candidate_fields_deleted"] == 1
    assert report["filter_value_deleted"] == 1
    assert report["synonym_deleted"] == 1
    assert report["total_deleted"] == 4
    assert state["artifact_refresh_scheduled"] is False
    freshness = state["artifact_freshness_report"]
    assert freshness["field_semantic_index"]["status"] == "missing"
    assert freshness["field_semantic_index"]["reason"] == "refresh_not_scheduled"
    assert freshness["field_semantic_index"]["alert_required"] is True
    assert freshness["field_values_index"]["status"] == "missing"
    assert freshness["field_values_index"]["reason"] == "refresh_not_scheduled"
    assert state["artifact_refresh_request"] == {
        "datasource_luid": "ds-sales",
        "trigger": "schema_change",
        "requested_artifacts": [
            "field_semantic_index",
            "field_values_index",
        ],
        "prefer_incremental": True,
        "previous_schema_hash": "schema-old",
        "schema_hash": hashlib.md5(b"empty").hexdigest(),
        "refresh_reason": "schema 变化后需要失效旧产物，并优先做增量重建。",
    }
    assert state["degrade_details"] == [
        {
            "artifact": "field_semantic_index",
            "degrade_flag": "semantic_retrieval_degraded",
            "status": "missing",
            "reason": "refresh_not_scheduled",
            "degrade_mode": "fallback_retrieval",
            "refresh_requested": True,
            "refresh_scheduled": False,
            "refresh_trigger": "schema_change",
            "alert_required": True,
        },
        {
            "artifact": "field_values_index",
            "degrade_flag": "value_retrieval_degraded",
            "status": "missing",
            "reason": "refresh_not_scheduled",
            "degrade_mode": "fallback_retrieval",
            "refresh_requested": True,
            "refresh_scheduled": False,
            "refresh_trigger": "schema_change",
            "alert_required": True,
        },
    ]

    snapshot = PreparedContextSnapshot.model_validate(state["prepared_context_snapshot"])
    assert snapshot.previous_schema_hash == hashlib.md5(b"empty").hexdigest()
