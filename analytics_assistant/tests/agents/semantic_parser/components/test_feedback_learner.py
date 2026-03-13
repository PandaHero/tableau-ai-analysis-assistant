from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from analytics_assistant.src.agents.semantic_parser.components.feedback_learner import (
    FeedbackLearner,
)
from analytics_assistant.src.agents.semantic_parser.components.query_cache import (
    build_query_cache_partition_key,
)
from analytics_assistant.src.agents.semantic_parser.schemas.feedback import (
    FeedbackRecord,
    FeedbackType,
)


class _FakeStore:
    def __init__(self) -> None:
        self._items: OrderedDict[tuple[tuple[str, ...], str], dict] = OrderedDict()

    def put(self, namespace: tuple[str, ...], key: str, value: dict) -> None:
        self._items[(tuple(namespace), key)] = value

    def get(self, namespace: tuple[str, ...], key: str):
        value = self._items.get((tuple(namespace), key))
        if value is None:
            return None
        return SimpleNamespace(key=key, value=value)

    def search(self, namespace: tuple[str, ...], limit: int = 1000):
        matched = [
            SimpleNamespace(key=key, value=value)
            for (item_namespace, key), value in self._items.items()
            if item_namespace == tuple(namespace)
        ]
        return matched[:limit]

    def delete(self, namespace: tuple[str, ...], key: str) -> None:
        self._items.pop((tuple(namespace), key), None)


@pytest.mark.asyncio
async def test_learn_filter_value_correction_isolated_by_scope_key() -> None:
    store = _FakeStore()
    learner = FeedbackLearner(store=store)

    await learner.learn_filter_value_correction(
        field_name="Region",
        original_value="East",
        confirmed_value="East",
        datasource_luid="ds-1",
        scope_key="scope_a",
    )
    await learner.learn_filter_value_correction(
        field_name="Region",
        original_value="East",
        confirmed_value="East",
        datasource_luid="ds-1",
        scope_key="scope_b",
    )

    partition_a = build_query_cache_partition_key("ds-1", scope_key="scope_a")
    partition_b = build_query_cache_partition_key("ds-1", scope_key="scope_b")

    item_a = store.get(("semantic_parser", "filter_values", partition_a), "region:east")
    item_b = store.get(("semantic_parser", "filter_values", partition_b), "region:east")

    assert item_a is not None
    assert item_b is not None
    assert item_a.value["confirmation_count"] == 1
    assert item_b.value["confirmation_count"] == 1


@pytest.mark.asyncio
async def test_synonym_learning_and_lookup_isolated_by_scope_key() -> None:
    store = _FakeStore()
    learner = FeedbackLearner(store=store, synonym_threshold=2)

    await learner.learn_synonym(
        original_term="销量",
        correct_field="销售额",
        datasource_luid="ds-1",
        scope_key="scope_a",
    )
    await learner.learn_synonym(
        original_term="销量",
        correct_field="销售额",
        datasource_luid="ds-1",
        scope_key="scope_a",
    )
    await learner.learn_synonym(
        original_term="销量",
        correct_field="销售额",
        datasource_luid="ds-1",
        scope_key="scope_b",
    )

    confirmed_a = await learner.get_confirmed_synonyms(
        "ds-1",
        scope_key="scope_a",
    )
    confirmed_b = await learner.get_confirmed_synonyms(
        "ds-1",
        scope_key="scope_b",
    )

    assert len(confirmed_a) == 1
    assert confirmed_a[0].confirmation_count == 2
    assert confirmed_b == []


@pytest.mark.asyncio
async def test_feedback_eviction_applies_per_scope_key() -> None:
    store = _FakeStore()
    learner = FeedbackLearner(
        store=store,
        max_feedback_per_datasource=1,
        auto_promote_enabled=False,
    )
    created_at = datetime(2026, 3, 12, 9, 0, 0)

    await learner.record(
        FeedbackRecord(
            id="fb-a-1",
            question="q1",
            feedback_type=FeedbackType.ACCEPT,
            datasource_luid="ds-1",
            created_at=created_at,
        ),
        scope_key="scope_a",
    )
    await learner.record(
        FeedbackRecord(
            id="fb-a-2",
            question="q2",
            feedback_type=FeedbackType.ACCEPT,
            datasource_luid="ds-1",
            created_at=created_at + timedelta(seconds=1),
        ),
        scope_key="scope_a",
    )
    await learner.record(
        FeedbackRecord(
            id="fb-b-1",
            question="q3",
            feedback_type=FeedbackType.ACCEPT,
            datasource_luid="ds-1",
            created_at=created_at + timedelta(seconds=2),
        ),
        scope_key="scope_b",
    )

    feedback_a = await learner.list_feedback("ds-1", scope_key="scope_a")
    feedback_b = await learner.list_feedback("ds-1", scope_key="scope_b")

    assert [record.id for record in feedback_a] == ["fb-a-2"]
    assert [record.id for record in feedback_b] == ["fb-b-1"]
