# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Optional

import pytest

from analytics_assistant.src.agents.field_semantic import FieldSemanticAttributes
from analytics_assistant.src.core.schemas import DataModel, Field
from analytics_assistant.src.infra.rag.schemas.index import UpdateResult
from analytics_assistant.src.platform.tableau.artifact_keys import (
    build_field_index_name,
    build_field_values_index_name,
)
from analytics_assistant.src.platform.tableau import data_loader as data_loader_module
from analytics_assistant.src.platform.tableau import prewarm_runtime as prewarm_runtime_module
from analytics_assistant.src.platform.tableau.data_loader import TableauDataLoader


class _IndexStub:
    def __init__(self) -> None:
        self.updated_documents: list[tuple[str, list[object]]] = []
        self._fields: dict[str, list[dict[str, object]]] = {}

    def get_index(self, _name: str) -> object:
        return object()

    def update_documents(self, index_name: str, documents: list[object]) -> UpdateResult:
        self.updated_documents.append((index_name, list(documents)))
        self._fields[index_name] = [dict(doc.metadata) for doc in documents]
        return UpdateResult()

    def get_index_fields(self, name: str) -> list[dict]:
        return list(self._fields.get(name, []))

    def list_indexes(self) -> list[object]:
        return []

    def delete_index(self, _name: str) -> bool:
        return True

    def delete_documents(self, _index_name: str, doc_ids: list[str]) -> int:
        return len(doc_ids)


class _PrepareLoaderStub:
    async def __aenter__(self) -> "_PrepareLoaderStub":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb

    async def prepare_datasource_artifacts(self, **_kwargs) -> None:
        return None


class _LifecycleIndexStub:
    def __init__(
        self,
        *,
        existing_indexes: Optional[dict[str, list[dict[str, object]]]] = None,
    ) -> None:
        self.updated_documents: list[tuple[str, list[object]]] = []
        self.created_indexes: list[tuple[str, list[object]]] = []
        self.deleted_documents: list[tuple[str, list[str]]] = []
        self.deleted_indexes: list[str] = []
        self._indexes: dict[str, object] = {}
        self._fields: dict[str, list[dict[str, object]]] = {}
        for index_name, fields in (existing_indexes or {}).items():
            self._indexes[index_name] = object()
            self._fields[index_name] = list(fields)

    def get_index(self, name: str) -> object | None:
        return self._indexes.get(name)

    def create_index(self, name: str, config: object, documents: list[object]) -> object:
        del config
        self.created_indexes.append((name, list(documents)))
        self._indexes[name] = object()
        self._fields[name] = [dict(doc.metadata) for doc in documents]
        return object()

    def update_documents(self, index_name: str, documents: list[object]) -> UpdateResult:
        self.updated_documents.append((index_name, list(documents)))
        self._indexes[index_name] = object()
        existing_fields = {
            str(field_info.get("field_name") or ""): dict(field_info)
            for field_info in self._fields.get(index_name, [])
            if str(field_info.get("field_name") or "")
        }
        for document in documents:
            field_name = str(document.metadata.get("field_name") or "")
            if field_name:
                existing_fields[field_name] = dict(document.metadata)
        self._fields[index_name] = list(existing_fields.values())
        return UpdateResult()

    def get_index_fields(self, name: str) -> list[dict]:
        return list(self._fields.get(name, []))

    def delete_documents(self, index_name: str, doc_ids: list[str]) -> int:
        self.deleted_documents.append((index_name, list(doc_ids)))
        existing_fields = self._fields.get(index_name, [])
        self._fields[index_name] = [
            field_info
            for field_info in existing_fields
            if str(field_info.get("field_name") or "") not in set(doc_ids)
        ]
        return len(doc_ids)

    def list_indexes(self) -> list[object]:
        return [SimpleNamespace(name=index_name) for index_name in self._indexes]

    def delete_index(self, name: str) -> bool:
        self.deleted_indexes.append(name)
        self._indexes.pop(name, None)
        self._fields.pop(name, None)
        return True


@pytest.fixture(autouse=True)
def _reset_prewarm_runtime_state() -> None:
    prewarm_runtime_module.reset_datasource_artifact_refresh_runtime_for_tests()
    data_loader_module._data_model_cache.clear()
    data_loader_module._datasource_name_cache.clear()
    data_loader_module._prewarming_requests.clear()
    data_loader_module._prewarm_tasks.clear()
    data_loader_module._prewarm_semaphore = None
    data_loader_module._prewarm_loop = None
    data_loader_module._prewarm_concurrency_limit = None
    yield
    data_loader_module._data_model_cache.clear()
    data_loader_module._datasource_name_cache.clear()
    data_loader_module._prewarming_requests.clear()
    data_loader_module._prewarm_tasks.clear()
    data_loader_module._prewarm_semaphore = None
    data_loader_module._prewarm_loop = None
    data_loader_module._prewarm_concurrency_limit = None
    prewarm_runtime_module.reset_datasource_artifact_refresh_runtime_for_tests()


def _build_data_model() -> DataModel:
    return DataModel(
        datasource_id="ds-1",
        fields=[
            Field(name="Sales", caption="Sales", role="MEASURE", data_type="REAL"),
            Field(name="Region", caption="Region", role="DIMENSION", data_type="STRING"),
        ],
    )


def _build_semantic() -> dict[str, FieldSemanticAttributes]:
    return {
        "Region": FieldSemanticAttributes(
            role="dimension",
            business_description="地区维度",
            aliases=["区域"],
            confidence=0.92,
            reasoning="测试语义",
        )
    }


def test_data_model_cache_is_partitioned_by_site() -> None:
    loader = TableauDataLoader()
    model = _build_data_model()

    loader._cache_data_model(model, site="site-a")

    cached_site_a = loader._get_cached_data_model("ds-1", site="site-a")
    cached_site_b = loader._get_cached_data_model("ds-1", site="site-b")

    assert cached_site_a is not None
    assert cached_site_a.datasource_id == "ds-1"
    assert cached_site_b is None


def test_field_index_name_is_partitioned_by_site_and_schema() -> None:
    site_a_schema_v1 = build_field_index_name(
        datasource_id="ds-1",
        site="site-a",
        schema_hash="schema-v1-abcdef",
    )
    site_a_schema_v2 = build_field_index_name(
        datasource_id="ds-1",
        site="site-a",
        schema_hash="schema-v2-abcdef",
    )
    site_b_schema_v1 = build_field_index_name(
        datasource_id="ds-1",
        site="site-b",
        schema_hash="schema-v1-abcdef",
    )
    site_a_values_v1 = build_field_values_index_name(
        datasource_id="ds-1",
        site="site-a",
        schema_hash="schema-v1-abcdef",
    )

    assert site_a_schema_v1 == "field_semantic_site-a_ds-1_schema-v1-ab"
    assert site_a_schema_v2 == "field_semantic_site-a_ds-1_schema-v2-ab"
    assert site_b_schema_v1 == "field_semantic_site-b_ds-1_schema-v1-ab"
    assert site_a_values_v1 == "field_values_site-a_ds-1_schema-v1-ab"
    assert site_a_schema_v1 != site_a_schema_v2
    assert site_a_schema_v1 != site_b_schema_v1
    assert site_a_schema_v1 != site_a_values_v1


@pytest.mark.asyncio
async def test_refresh_field_values_only_skips_semantic_inference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loader = TableauDataLoader()
    data_model = _build_data_model()
    data_model._field_semantic_cache = _build_semantic()

    index_stub = _IndexStub()
    monkeypatch.setattr(
        data_loader_module,
        "get_rag_service",
        lambda: SimpleNamespace(index=index_stub),
    )
    monkeypatch.setattr(loader, "_restore_queryable_flags", lambda *args, **kwargs: None)
    monkeypatch.setattr(loader, "_restore_field_semantic", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        loader,
        "_restore_field_samples",
        lambda *args, **kwargs: {"Region": {"sample_values": ["East"]}},
    )

    fetch_calls = 0
    infer_calls = 0

    async def _fake_fetch_field_samples_for_index(**_kwargs):
        nonlocal fetch_calls
        fetch_calls += 1
        return {"Region": {"sample_values": ["West"]}}, set()

    async def _fake_infer_field_semantic_for_index(**_kwargs):
        nonlocal infer_calls
        infer_calls += 1
        return _build_semantic()

    monkeypatch.setattr(
        loader,
        "_fetch_field_samples_for_index",
        _fake_fetch_field_samples_for_index,
    )
    monkeypatch.setattr(
        loader,
        "_infer_field_semantic_for_index",
        _fake_infer_field_semantic_for_index,
    )

    field_samples = await loader._ensure_field_index(
        "ds-1",
        data_model,
        refresh_artifacts={"field_values_index"},
    )

    assert fetch_calls == 1
    assert infer_calls == 0
    assert field_samples == {"Region": {"sample_values": ["West"]}}
    assert index_stub.updated_documents
    assert index_stub.updated_documents[0][0] == build_field_values_index_name(
        datasource_id="ds-1",
        site=None,
        schema_hash=data_model.schema_hash,
    )


@pytest.mark.asyncio
async def test_refresh_field_semantic_only_reuses_existing_samples(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loader = TableauDataLoader()
    data_model = _build_data_model()

    index_stub = _IndexStub()
    monkeypatch.setattr(
        data_loader_module,
        "get_rag_service",
        lambda: SimpleNamespace(index=index_stub),
    )
    monkeypatch.setattr(loader, "_restore_queryable_flags", lambda *args, **kwargs: None)
    monkeypatch.setattr(loader, "_restore_field_semantic", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        loader,
        "_restore_field_samples",
        lambda *args, **kwargs: {"Region": {"sample_values": ["East"]}},
    )

    fetch_calls = 0
    captured_field_samples: list[dict[str, dict[str, object]]] = []

    async def _fake_fetch_field_samples_for_index(**_kwargs):
        nonlocal fetch_calls
        fetch_calls += 1
        return {"Region": {"sample_values": ["West"]}}, set()

    async def _fake_infer_field_semantic_for_index(**kwargs):
        captured_field_samples.append(dict(kwargs.get("field_samples") or {}))
        return _build_semantic()

    monkeypatch.setattr(
        loader,
        "_fetch_field_samples_for_index",
        _fake_fetch_field_samples_for_index,
    )
    monkeypatch.setattr(
        loader,
        "_infer_field_semantic_for_index",
        _fake_infer_field_semantic_for_index,
    )

    field_samples = await loader._ensure_field_index(
        "ds-1",
        data_model,
        refresh_artifacts={"field_semantic_index"},
    )

    assert fetch_calls == 0
    assert captured_field_samples == [{"Region": {"sample_values": ["East"]}}]
    assert field_samples == {"Region": {"sample_values": ["East"]}}
    assert index_stub.updated_documents
    assert index_stub.updated_documents[0][0] == build_field_index_name(
        datasource_id="ds-1",
        site=None,
        schema_hash=data_model.schema_hash,
    )


def test_schedule_datasource_artifact_preparation_deduplicates_same_refresh_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pending_coroutines = []
    monkeypatch.setattr(data_loader_module, "TableauDataLoader", _PrepareLoaderStub)
    monkeypatch.setattr(data_loader_module, "_get_prewarm_runtime_limits", lambda: (2, 8))
    monkeypatch.setattr(
        prewarm_runtime_module.asyncio,
        "create_task",
        lambda coro: pending_coroutines.append(coro) or SimpleNamespace(),
    )

    refresh_request = {
        "datasource_luid": "ds-1",
        "trigger": "schema_change",
        "requested_artifacts": ["field_semantic_index"],
        "schema_hash": "schema-new",
    }
    auth = SimpleNamespace(site="default")

    first = prewarm_runtime_module.schedule_datasource_artifact_preparation(
        datasource_id="ds-1",
        auth=auth,
        refresh_request=refresh_request,
    )
    second = prewarm_runtime_module.schedule_datasource_artifact_preparation(
        datasource_id="ds-1",
        auth=auth,
        refresh_request=refresh_request,
    )

    assert first is True
    assert second is False

    for coro in pending_coroutines:
        coro.close()


def test_schedule_datasource_artifact_preparation_allows_distinct_artifact_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pending_coroutines = []
    monkeypatch.setattr(data_loader_module, "TableauDataLoader", _PrepareLoaderStub)
    monkeypatch.setattr(data_loader_module, "_get_prewarm_runtime_limits", lambda: (2, 8))
    monkeypatch.setattr(
        prewarm_runtime_module.asyncio,
        "create_task",
        lambda coro: pending_coroutines.append(coro) or SimpleNamespace(),
    )

    auth = SimpleNamespace(site="default")
    semantic_request = {
        "datasource_luid": "ds-1",
        "trigger": "schema_change",
        "requested_artifacts": ["field_semantic_index"],
        "schema_hash": "schema-new",
    }
    values_request = {
        "datasource_luid": "ds-1",
        "trigger": "schema_change",
        "requested_artifacts": ["field_values_index"],
        "schema_hash": "schema-new",
    }

    semantic_scheduled = prewarm_runtime_module.schedule_datasource_artifact_preparation(
        datasource_id="ds-1",
        auth=auth,
        refresh_request=semantic_request,
    )
    values_scheduled = prewarm_runtime_module.schedule_datasource_artifact_preparation(
        datasource_id="ds-1",
        auth=auth,
        refresh_request=values_request,
    )

    assert semantic_scheduled is True
    assert values_scheduled is True

    for coro in pending_coroutines:
        coro.close()


@pytest.mark.asyncio
async def test_schedule_datasource_artifact_preparation_rejects_when_queue_full(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_started = asyncio.Event()
    release = asyncio.Event()

    class _BlockingPrepareLoaderStub:
        async def __aenter__(self) -> "_BlockingPrepareLoaderStub":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            del exc_type, exc, tb

        async def prepare_datasource_artifacts(self, **_kwargs) -> None:
            first_started.set()
            await release.wait()

    monkeypatch.setattr(data_loader_module, "TableauDataLoader", _BlockingPrepareLoaderStub)
    monkeypatch.setattr(data_loader_module, "_get_prewarm_runtime_limits", lambda: (1, 1))

    auth = SimpleNamespace(site="default")
    first = prewarm_runtime_module.schedule_datasource_artifact_preparation(
        datasource_id="ds-1",
        auth=auth,
        refresh_request={
            "datasource_luid": "ds-1",
            "requested_artifacts": ["field_semantic_index"],
            "schema_hash": "schema-a",
        },
    )
    await first_started.wait()

    second = prewarm_runtime_module.schedule_datasource_artifact_preparation(
        datasource_id="ds-1",
        auth=auth,
        refresh_request={
            "datasource_luid": "ds-1",
            "requested_artifacts": ["field_values_index"],
            "schema_hash": "schema-a",
        },
    )

    assert first is True
    assert second is False

    release.set()
    await asyncio.gather(*list(data_loader_module._prewarm_tasks.values()))


@pytest.mark.asyncio
async def test_schedule_datasource_artifact_preparation_honors_concurrency_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_started = asyncio.Event()
    release = asyncio.Event()
    started_order: list[str] = []
    active_count = 0
    max_active_count = 0

    class _BlockingPrepareLoaderStub:
        async def __aenter__(self) -> "_BlockingPrepareLoaderStub":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            del exc_type, exc, tb

        async def prepare_datasource_artifacts(self, **kwargs) -> None:
            nonlocal active_count, max_active_count
            active_count += 1
            max_active_count = max(max_active_count, active_count)
            datasource_luid = str(
                (kwargs.get("refresh_request") or {}).get("datasource_luid") or "unknown"
            )
            started_order.append(datasource_luid)
            if len(started_order) == 1:
                first_started.set()
            await release.wait()
            active_count -= 1

    monkeypatch.setattr(data_loader_module, "TableauDataLoader", _BlockingPrepareLoaderStub)
    monkeypatch.setattr(data_loader_module, "_get_prewarm_runtime_limits", lambda: (1, 4))

    auth = SimpleNamespace(site="default")
    first = prewarm_runtime_module.schedule_datasource_artifact_preparation(
        datasource_id="ds-1",
        auth=auth,
        refresh_request={
            "datasource_luid": "ds-1",
            "requested_artifacts": ["field_semantic_index"],
            "schema_hash": "schema-a",
        },
    )
    second = prewarm_runtime_module.schedule_datasource_artifact_preparation(
        datasource_id="ds-2",
        auth=auth,
        refresh_request={
            "datasource_luid": "ds-2",
            "requested_artifacts": ["field_semantic_index"],
            "schema_hash": "schema-a",
        },
    )

    assert first is True
    assert second is True

    await first_started.wait()
    await asyncio.sleep(0.05)
    assert started_order == ["ds-1"]
    assert max_active_count == 1

    release.set()
    await asyncio.gather(*list(data_loader_module._prewarm_tasks.values()))
    assert started_order == ["ds-1", "ds-2"]
    assert max_active_count == 1


@pytest.mark.asyncio
async def test_runtime_snapshot_reports_completed_builds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(data_loader_module, "TableauDataLoader", _PrepareLoaderStub)
    monkeypatch.setattr(data_loader_module, "_get_prewarm_runtime_limits", lambda: (2, 8))

    scheduled = prewarm_runtime_module.schedule_datasource_artifact_preparation(
        datasource_id="ds-1",
        auth=SimpleNamespace(site="default"),
        refresh_request={
            "datasource_luid": "ds-1",
            "requested_artifacts": ["field_semantic_index"],
            "schema_hash": "schema-a",
        },
    )

    assert scheduled is True
    await asyncio.gather(*list(data_loader_module._prewarm_tasks.values()))

    snapshot = prewarm_runtime_module.get_datasource_artifact_refresh_runtime_snapshot()
    assert snapshot["active_requests"] == 0
    assert snapshot["queued_requests"] == 0
    assert snapshot["completed_builds"] == 1
    assert snapshot["failed_builds"] == 0
    assert snapshot["last_build_latency_ms"] is not None


@pytest.mark.asyncio
async def test_incremental_refresh_tombstones_deleted_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loader = TableauDataLoader()
    data_model = _build_data_model()
    current_semantic_index = build_field_index_name(
        datasource_id="ds-1",
        site=None,
        schema_hash=data_model.schema_hash,
    )
    current_values_index = build_field_values_index_name(
        datasource_id="ds-1",
        site=None,
        schema_hash=data_model.schema_hash,
    )
    index_stub = _LifecycleIndexStub(
        existing_indexes={
            current_semantic_index: [
                {"field_name": "Sales", "field_caption": "Sales"},
                {"field_name": "Region", "field_caption": "Region"},
                {"field_name": "Legacy", "field_caption": "Legacy"},
            ],
            current_values_index: [
                {"field_name": "Sales", "field_caption": "Sales"},
                {"field_name": "Region", "field_caption": "Region"},
                {"field_name": "Legacy", "field_caption": "Legacy"},
            ],
        }
    )
    monkeypatch.setattr(
        data_loader_module,
        "get_rag_service",
        lambda: SimpleNamespace(index=index_stub),
    )
    monkeypatch.setattr(loader, "_restore_queryable_flags", lambda *args, **kwargs: None)
    monkeypatch.setattr(loader, "_restore_field_semantic", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        loader,
        "_restore_field_samples",
        lambda *args, **kwargs: {"Region": {"sample_values": ["East"]}},
    )
    monkeypatch.setattr(
        loader,
        "_fetch_field_samples_for_index",
        lambda **_kwargs: asyncio.sleep(0, result=({"Region": {"sample_values": ["West"]}}, set())),
    )
    monkeypatch.setattr(
        loader,
        "_infer_field_semantic_for_index",
        lambda **_kwargs: asyncio.sleep(0, result=_build_semantic()),
    )

    await loader._ensure_field_index(
        "ds-1",
        data_model,
        refresh_artifacts={"field_semantic_index", "field_values_index"},
        prefer_incremental=True,
    )

    assert (current_semantic_index, ["Legacy"]) in index_stub.deleted_documents
    assert (current_values_index, ["Legacy"]) in index_stub.deleted_documents


@pytest.mark.asyncio
async def test_prefer_incremental_false_recreates_requested_index_and_compacts_old_versions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loader = TableauDataLoader()
    data_model = _build_data_model()
    current_semantic_index = build_field_index_name(
        datasource_id="ds-1",
        site=None,
        schema_hash=data_model.schema_hash,
    )
    old_semantic_index = build_field_index_name(
        datasource_id="ds-1",
        site=None,
        schema_hash="schema-old-abcdef",
    )
    current_values_index = build_field_values_index_name(
        datasource_id="ds-1",
        site=None,
        schema_hash=data_model.schema_hash,
    )
    index_stub = _LifecycleIndexStub(
        existing_indexes={
            current_semantic_index: [
                {"field_name": "Sales", "field_caption": "Sales"},
                {"field_name": "Region", "field_caption": "Region"},
            ],
            old_semantic_index: [
                {"field_name": "Sales", "field_caption": "Sales"},
            ],
            current_values_index: [
                {"field_name": "Region", "field_caption": "Region"},
            ],
        }
    )
    monkeypatch.setattr(
        data_loader_module,
        "get_rag_service",
        lambda: SimpleNamespace(index=index_stub),
    )
    monkeypatch.setattr(loader, "_restore_queryable_flags", lambda *args, **kwargs: None)
    monkeypatch.setattr(loader, "_restore_field_semantic", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        loader,
        "_restore_field_samples",
        lambda *args, **kwargs: {"Region": {"sample_values": ["East"]}},
    )
    monkeypatch.setattr(
        loader,
        "_fetch_field_samples_for_index",
        lambda **_kwargs: asyncio.sleep(0, result=({"Region": {"sample_values": ["East"]}}, set())),
    )
    monkeypatch.setattr(
        loader,
        "_infer_field_semantic_for_index",
        lambda **_kwargs: asyncio.sleep(0, result=_build_semantic()),
    )

    await loader._ensure_field_index(
        "ds-1",
        data_model,
        refresh_artifacts={"field_semantic_index"},
        prefer_incremental=False,
    )

    assert current_semantic_index in index_stub.deleted_indexes
    assert old_semantic_index in index_stub.deleted_indexes
    assert any(index_name == current_semantic_index for index_name, _ in index_stub.created_indexes)
    assert current_values_index not in index_stub.deleted_indexes
