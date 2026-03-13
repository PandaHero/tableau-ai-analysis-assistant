# -*- coding: utf-8 -*-
"""检索与记忆平面的统一存储封装。

这个模块只做两件事：
1. 为检索候选、检索 trace、记忆写入审计提供稳定的命名空间与引用格式。
2. 复用现有 LangGraph KV store，不再在各节点里手写 namespace/key 规则。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from analytics_assistant.src.agents.semantic_parser.components import (
    build_query_cache_partition_key,
    compute_question_hash,
)
from analytics_assistant.src.infra.storage import get_kv_store


class MemoryStore:
    """统一管理 retrieval/memory 平面的引用与审计写入。"""

    CANDIDATE_FIELDS_NAMESPACE_PREFIX = ("retrieval_memory", "candidate_fields")
    CANDIDATE_VALUES_NAMESPACE_PREFIX = ("retrieval_memory", "candidate_values")
    FEWSHOT_EXAMPLES_NAMESPACE_PREFIX = ("retrieval_memory", "fewshot_examples")
    RETRIEVAL_TRACE_NAMESPACE_PREFIX = ("retrieval_memory", "retrieval_trace")
    MEMORY_AUDIT_NAMESPACE_PREFIX = ("retrieval_memory", "memory_audit")

    QUERY_CACHE_NAMESPACE_PREFIX = ("semantic_parser", "query_cache")
    FEW_SHOT_NAMESPACE_PREFIX = ("semantic_parser", "few_shot")
    FILTER_VALUE_NAMESPACE_PREFIX = ("semantic_parser", "filter_values")
    SYNONYM_NAMESPACE_PREFIX = ("semantic_parser", "synonyms")

    def __init__(self, *, store: Optional[Any] = None) -> None:
        self._store = store or get_kv_store()

    def _normalize_scope_key(self, scope_key: Optional[str]) -> str:
        normalized_scope_key = str(scope_key or "").strip()
        return normalized_scope_key or "global"

    def _make_namespace(
        self,
        prefix: tuple[str, ...],
        datasource_luid: str,
        *,
        scope_key: Optional[str] = None,
    ) -> tuple[str, ...]:
        partition_key = build_query_cache_partition_key(
            datasource_luid,
            scope_key=self._normalize_scope_key(scope_key),
        )
        return (*prefix, partition_key)

    def _build_store_ref(self, namespace: tuple[str, ...], key: str) -> str:
        return "kv://" + "/".join([*namespace, key])

    def _build_question_key(
        self,
        *,
        question: str,
        datasource_luid: str,
        schema_hash: Optional[str] = None,
    ) -> str:
        question_hash = compute_question_hash(question, datasource_luid)
        normalized_schema_hash = str(schema_hash or "").strip()
        if not normalized_schema_hash:
            return question_hash
        return f"{normalized_schema_hash[:12]}-{question_hash}"

    def put_candidate_fields(
        self,
        *,
        question: str,
        datasource_luid: str,
        schema_hash: Optional[str],
        payload: dict[str, Any],
        scope_key: Optional[str] = None,
    ) -> str:
        namespace = self._make_namespace(
            self.CANDIDATE_FIELDS_NAMESPACE_PREFIX,
            datasource_luid,
            scope_key=scope_key,
        )
        key = self._build_question_key(
            question=question,
            datasource_luid=datasource_luid,
            schema_hash=schema_hash,
        )
        self._store.put(namespace, key, payload)
        return self._build_store_ref(namespace, key)

    def put_candidate_values(
        self,
        *,
        question: str,
        datasource_luid: str,
        schema_hash: Optional[str],
        payload: dict[str, Any],
        scope_key: Optional[str] = None,
    ) -> Optional[str]:
        values = payload.get("candidate_values") or []
        if not values:
            return None

        namespace = self._make_namespace(
            self.CANDIDATE_VALUES_NAMESPACE_PREFIX,
            datasource_luid,
            scope_key=scope_key,
        )
        key = self._build_question_key(
            question=question,
            datasource_luid=datasource_luid,
            schema_hash=schema_hash,
        )
        self._store.put(namespace, key, payload)
        return self._build_store_ref(namespace, key)

    def put_fewshot_examples(
        self,
        *,
        question: str,
        datasource_luid: str,
        schema_hash: Optional[str],
        payload: dict[str, Any],
        scope_key: Optional[str] = None,
    ) -> Optional[str]:
        examples = payload.get("few_shot_examples") or []
        if not examples:
            return None

        namespace = self._make_namespace(
            self.FEWSHOT_EXAMPLES_NAMESPACE_PREFIX,
            datasource_luid,
            scope_key=scope_key,
        )
        key = self._build_question_key(
            question=question,
            datasource_luid=datasource_luid,
            schema_hash=schema_hash,
        )
        self._store.put(namespace, key, payload)
        return self._build_store_ref(namespace, key)

    def put_retrieval_trace(
        self,
        *,
        datasource_luid: str,
        key: str,
        payload: dict[str, Any],
        scope_key: Optional[str] = None,
    ) -> str:
        namespace = self._make_namespace(
            self.RETRIEVAL_TRACE_NAMESPACE_PREFIX,
            datasource_luid,
            scope_key=scope_key,
        )
        self._store.put(namespace, key, payload)
        return self._build_store_ref(namespace, key)

    def record_memory_write(
        self,
        *,
        datasource_luid: str,
        request_id: Optional[str],
        session_id: Optional[str],
        run_id: Optional[str],
        user_id: Optional[str],
        reason: str,
        target_ref: str,
        metadata: Optional[dict[str, Any]] = None,
        scope_key: Optional[str] = None,
    ) -> str:
        """为每次实际记忆写入落一条独立审计记录。"""
        namespace = self._make_namespace(
            self.MEMORY_AUDIT_NAMESPACE_PREFIX,
            datasource_luid,
            scope_key=scope_key,
        )
        key = uuid4().hex
        payload = {
            "request_id": str(request_id or "").strip() or None,
            "session_id": str(session_id or "").strip() or None,
            "run_id": str(run_id or "").strip() or None,
            "user_id": str(user_id or "").strip() or None,
            "reason": reason,
            "target_ref": target_ref,
            "metadata": dict(metadata or {}),
            "created_at": datetime.now().isoformat(),
        }
        self._store.put(namespace, key, payload)
        return self._build_store_ref(namespace, key)

    def build_query_cache_ref(
        self,
        *,
        question: str,
        datasource_luid: str,
        scope_key: str = "global",
    ) -> str:
        namespace = self._make_namespace(
            self.QUERY_CACHE_NAMESPACE_PREFIX,
            datasource_luid,
            scope_key=scope_key,
        )
        key = compute_question_hash(question, datasource_luid)
        return self._build_store_ref(namespace, key)

    def build_filter_value_ref(
        self,
        *,
        field_name: str,
        original_value: str,
        datasource_luid: str,
        scope_key: Optional[str] = None,
    ) -> str:
        namespace = self._make_namespace(
            self.FILTER_VALUE_NAMESPACE_PREFIX,
            datasource_luid,
            scope_key=scope_key,
        )
        key = f"{field_name.lower()}:{original_value.lower()}"
        return self._build_store_ref(namespace, key)

    def build_fewshot_ref(
        self,
        *,
        datasource_luid: str,
        example_id: str,
        scope_key: Optional[str] = None,
    ) -> str:
        namespace = self._make_namespace(
            self.FEW_SHOT_NAMESPACE_PREFIX,
            datasource_luid,
            scope_key=scope_key,
        )
        return self._build_store_ref(namespace, example_id)

    def build_synonym_ref(
        self,
        *,
        datasource_luid: str,
        original_term: str,
        correct_field: str,
        scope_key: Optional[str] = None,
    ) -> str:
        namespace = self._make_namespace(
            self.SYNONYM_NAMESPACE_PREFIX,
            datasource_luid,
            scope_key=scope_key,
        )
        key = f"{original_term.lower()}:{correct_field.lower()}"
        return self._build_store_ref(namespace, key)
