from __future__ import annotations

from datetime import datetime

import pytest
from langgraph.store.memory import InMemoryStore

from analytics_assistant.src.agents.semantic_parser.components import (
    QueryCache,
    build_query_cache_partition_key,
    compute_question_hash,
)
from analytics_assistant.src.agents.semantic_parser.components.feedback_learner import (
    FeedbackLearner,
)
from analytics_assistant.src.agents.semantic_parser.schemas.cache import CachedQuery
from analytics_assistant.src.agents.semantic_parser.schemas.feedback import (
    FeedbackRecord,
    FeedbackType,
)
from analytics_assistant.src.orchestration.retrieval_memory import (
    MemoryInvalidationService,
    MemoryStore,
)


async def _seed_scope_partition(
    *,
    store: InMemoryStore,
    datasource_luid: str,
    scope_key: str,
    suffix: str,
) -> None:
    memory_store = MemoryStore(store=store)
    learner = FeedbackLearner(store=store, auto_promote_enabled=False)

    partition_key = build_query_cache_partition_key(
        datasource_luid,
        scope_key=scope_key,
    )
    question = f"question-{suffix}"
    store.put(
        ("semantic_parser", "query_cache", partition_key),
        compute_question_hash(question, datasource_luid),
        CachedQuery(
            question=question,
            question_hash=compute_question_hash(question, datasource_luid),
            datasource_luid=datasource_luid,
            scope_key=scope_key,
            schema_hash="schema-old",
            semantic_output={"restated_question": question},
            query={"kind": "vizql", "query": f"select-{suffix}"},
            expires_at=datetime(2026, 3, 13, 9, 0, 0),
        ).model_dump(mode="json"),
    )
    memory_store.put_candidate_fields(
        question=question,
        datasource_luid=datasource_luid,
        schema_hash="schema-old",
        payload={"candidate_fields": [{"field_name": f"field-{suffix}"}]},
        scope_key=scope_key,
    )
    memory_store.put_candidate_values(
        question=question,
        datasource_luid=datasource_luid,
        schema_hash="schema-old",
        payload={"candidate_values": [{"field_name": "Region", "value": suffix}]},
        scope_key=scope_key,
    )
    memory_store.put_fewshot_examples(
        question=question,
        datasource_luid=datasource_luid,
        schema_hash="schema-old",
        payload={"few_shot_examples": [{"id": f"fewshot-{suffix}"}]},
        scope_key=scope_key,
    )
    await learner.learn_filter_value_correction(
        field_name="Region",
        original_value=suffix,
        confirmed_value=suffix,
        datasource_luid=datasource_luid,
        scope_key=scope_key,
    )
    await learner.learn_synonym(
        original_term=f"term-{suffix}",
        correct_field=f"field-{suffix}",
        datasource_luid=datasource_luid,
        scope_key=scope_key,
    )
    await learner.record(
        FeedbackRecord(
            id=f"feedback-{suffix}",
            question=f"question-{suffix}",
            feedback_type=FeedbackType.ACCEPT,
            datasource_luid=datasource_luid,
            created_at=datetime(2026, 3, 12, 9, 0, 0),
        ),
        scope_key=scope_key,
    )


def _count_items(store: InMemoryStore, namespace_prefix: tuple[str, ...]) -> int:
    return len(list(store.search(namespace_prefix, limit=1000)))


@pytest.mark.asyncio
async def test_invalidate_for_schema_change_clears_schema_bound_entries_across_scopes() -> None:
    store = InMemoryStore()
    query_cache = QueryCache(store=store)
    service = MemoryInvalidationService(
        store=store,
        query_cache_getter=lambda: query_cache,
    )

    await _seed_scope_partition(
        store=store,
        datasource_luid="ds-1",
        scope_key="scope_a",
        suffix="a",
    )
    await _seed_scope_partition(
        store=store,
        datasource_luid="ds-1",
        scope_key="scope_b",
        suffix="b",
    )

    report = service.invalidate_for_schema_change(
        datasource_luid="ds-1",
        new_schema_hash="schema-new",
        previous_schema_hash="schema-old",
    )

    assert report["trigger"] == "schema_change"
    assert report["query_cache_deleted"] == 2
    assert report["candidate_fields_deleted"] == 2
    assert report["candidate_values_deleted"] == 2
    assert report["fewshot_examples_deleted"] == 2
    assert report["filter_value_deleted"] == 2
    assert report["synonym_deleted"] == 2
    assert report["feedback_deleted"] == 0
    assert report["total_deleted"] == 12

    assert _count_items(store, ("semantic_parser", "query_cache")) == 0
    assert _count_items(store, ("retrieval_memory", "candidate_fields")) == 0
    assert _count_items(store, ("retrieval_memory", "candidate_values")) == 0
    assert _count_items(store, ("retrieval_memory", "fewshot_examples")) == 0
    assert _count_items(store, ("semantic_parser", "filter_values")) == 0
    assert _count_items(store, ("semantic_parser", "synonyms")) == 0
    assert _count_items(store, ("semantic_parser", "feedback")) == 2


@pytest.mark.asyncio
async def test_clear_scope_only_removes_requested_partition() -> None:
    store = InMemoryStore()
    query_cache = QueryCache(store=store)
    service = MemoryInvalidationService(
        store=store,
        query_cache_getter=lambda: query_cache,
    )

    await _seed_scope_partition(
        store=store,
        datasource_luid="ds-1",
        scope_key="scope_a",
        suffix="a",
    )
    await _seed_scope_partition(
        store=store,
        datasource_luid="ds-1",
        scope_key="scope_b",
        suffix="b",
    )

    report = service.clear_scope(
        datasource_luid="ds-1",
        scope_key="scope_a",
    )

    assert report["trigger"] == "scope_reset"
    assert report["query_cache_deleted"] == 1
    assert report["candidate_fields_deleted"] == 1
    assert report["candidate_values_deleted"] == 1
    assert report["fewshot_examples_deleted"] == 1
    assert report["filter_value_deleted"] == 1
    assert report["synonym_deleted"] == 1
    assert report["feedback_deleted"] == 1
    assert report["total_deleted"] == 7

    feedback_items = list(store.search(("semantic_parser", "feedback"), limit=1000))
    remaining_namespaces = {tuple(item.namespace) for item in feedback_items}
    assert len(feedback_items) == 1
    assert remaining_namespaces == {
        ("semantic_parser", "feedback", build_query_cache_partition_key("ds-1", scope_key="scope_b"))
    }

    assert _count_items(store, ("semantic_parser", "query_cache")) == 1
    assert _count_items(store, ("retrieval_memory", "candidate_fields")) == 1
    assert _count_items(store, ("retrieval_memory", "candidate_values")) == 1
    assert _count_items(store, ("retrieval_memory", "fewshot_examples")) == 1
    assert _count_items(store, ("semantic_parser", "filter_values")) == 1
    assert _count_items(store, ("semantic_parser", "synonyms")) == 1
