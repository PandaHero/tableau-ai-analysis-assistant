# -*- coding: utf-8 -*-
"""retrieval/memory 平面的统一失效服务。

这个模块负责两类清理动作：
1. schema 变化后，清理依赖旧 schema 的缓存与记忆产物。
2. 按 `scope_key + datasource_luid` 或按 datasource 清理租户/用户隔离分区。

设计约束：
- `query_cache` 既可能通过 `CacheManager(namespace="query_cache_<partition>")`
  落到单段 namespace，也可能通过测试时的 direct store 落到
  `("semantic_parser", "query_cache", partition)`。
- retrieval candidate artifacts 与 value/synonym/feedback 使用 tuple namespace。
- retrieval trace / memory audit 属于审计记录，不在这里做常规失效删除。
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from analytics_assistant.src.agents.semantic_parser.components import (
    QueryCache,
    build_query_cache_partition_key,
    get_query_cache,
)
from analytics_assistant.src.infra.storage import get_kv_store

logger = logging.getLogger(__name__)


class MemoryInvalidationService:
    """统一管理 retrieval/memory 平面的失效规则。"""

    _QUERY_CACHE_NAMESPACE_PREFIX = "query_cache_"

    _FEEDBACK_NAMESPACE_PREFIX = ("semantic_parser", "feedback")
    _FILTER_VALUE_NAMESPACE_PREFIX = ("semantic_parser", "filter_values")
    _SYNONYM_NAMESPACE_PREFIX = ("semantic_parser", "synonyms")

    _CANDIDATE_FIELDS_NAMESPACE_PREFIX = ("retrieval_memory", "candidate_fields")
    _CANDIDATE_VALUES_NAMESPACE_PREFIX = ("retrieval_memory", "candidate_values")
    _FEWSHOT_EXAMPLES_NAMESPACE_PREFIX = ("retrieval_memory", "fewshot_examples")

    def __init__(
        self,
        *,
        store: Optional[Any] = None,
        query_cache_getter: Optional[Callable[[], QueryCache]] = None,
    ) -> None:
        self._store = store or get_kv_store()
        self._query_cache_getter = query_cache_getter or get_query_cache

    def _normalize_scope_key(self, scope_key: Optional[str]) -> str:
        normalized_scope_key = str(scope_key or "").strip()
        return normalized_scope_key or "global"

    def _matches_partition(
        self,
        partition_key: str,
        datasource_luid: str,
        *,
        scope_key: Optional[str] = None,
    ) -> bool:
        normalized_partition_key = str(partition_key or "").strip()
        normalized_datasource_luid = str(datasource_luid or "").strip()
        if not normalized_partition_key or not normalized_datasource_luid:
            return False

        if scope_key is not None:
            return normalized_partition_key == build_query_cache_partition_key(
                normalized_datasource_luid,
                scope_key=self._normalize_scope_key(scope_key),
            )

        return (
            normalized_partition_key == normalized_datasource_luid
            or normalized_partition_key.endswith(f"__{normalized_datasource_luid}")
        )

    def _extract_query_cache_partition_key(
        self,
        namespace: tuple[str, ...],
    ) -> Optional[str]:
        if not namespace:
            return None

        if len(namespace) == 1 and namespace[0].startswith(self._QUERY_CACHE_NAMESPACE_PREFIX):
            return namespace[0][len(self._QUERY_CACHE_NAMESPACE_PREFIX):]

        if len(namespace) >= 3 and namespace[:2] == ("semantic_parser", "query_cache"):
            return str(namespace[-1]).strip() or None

        return None

    def _delete_by_namespace_prefix(
        self,
        namespace_prefix: tuple[str, ...],
        *,
        datasource_luid: str,
        scope_key: Optional[str] = None,
        value_predicate: Optional[Callable[[dict[str, Any]], bool]] = None,
    ) -> int:
        deleted = 0
        for item in self._store.search((), limit=10000):
            namespace = tuple(getattr(item, "namespace", ()) or ())
            if namespace[: len(namespace_prefix)] != namespace_prefix:
                continue

            partition_key = str(namespace[-1] or "").strip()
            if not self._matches_partition(
                partition_key,
                datasource_luid,
                scope_key=scope_key,
            ):
                continue

            value = getattr(item, "value", None)
            if value_predicate is not None and not value_predicate(dict(value or {})):
                continue

            self._store.delete(namespace, item.key)
            deleted += 1

        return deleted

    def _delete_query_cache_entries(
        self,
        *,
        datasource_luid: str,
        scope_key: Optional[str] = None,
        value_predicate: Optional[Callable[[dict[str, Any]], bool]] = None,
    ) -> int:
        deleted = 0
        touched_partitions: set[str] = set()

        for item in self._store.search((), limit=10000):
            namespace = tuple(getattr(item, "namespace", ()) or ())
            partition_key = self._extract_query_cache_partition_key(namespace)
            if partition_key is None:
                continue
            if not self._matches_partition(
                partition_key,
                datasource_luid,
                scope_key=scope_key,
            ):
                continue

            value = getattr(item, "value", None)
            if value_predicate is not None and not value_predicate(dict(value or {})):
                continue

            self._store.delete(namespace, item.key)
            deleted += 1
            touched_partitions.add(partition_key)

        if touched_partitions:
            query_cache = self._query_cache_getter()
            for partition_key in touched_partitions:
                query_cache.rebuild_faiss_index(partition_key)

        return deleted

    def _build_report(
        self,
        *,
        trigger: str,
        datasource_luid: str,
        scope_key: Optional[str],
        counts: dict[str, int],
        previous_schema_hash: Optional[str] = None,
        new_schema_hash: Optional[str] = None,
    ) -> dict[str, Any]:
        report: dict[str, Any] = {
            "trigger": trigger,
            "datasource_luid": str(datasource_luid or "").strip() or None,
            "scope_key": self._normalize_scope_key(scope_key) if scope_key is not None else None,
            "previous_schema_hash": str(previous_schema_hash or "").strip() or None,
            "new_schema_hash": str(new_schema_hash or "").strip() or None,
            **counts,
        }
        report["total_deleted"] = sum(int(value) for value in counts.values())
        return report

    def invalidate_for_schema_change(
        self,
        *,
        datasource_luid: str,
        new_schema_hash: str,
        previous_schema_hash: Optional[str] = None,
    ) -> dict[str, Any]:
        """schema 变化时清理依赖旧 schema 的缓存与学习记忆。

        这里按 datasource 全 scope 清理，而不是只清当前用户 scope。
        原因是 schema 变化属于数据源级事件，旧的 query cache / value memory /
        synonym memory 对所有租户分区都可能变为陈旧数据。
        """
        counts = {
            "query_cache_deleted": self._delete_query_cache_entries(
                datasource_luid=datasource_luid,
                value_predicate=lambda value: value.get("schema_hash") != new_schema_hash,
            ),
            "candidate_fields_deleted": self._delete_by_namespace_prefix(
                self._CANDIDATE_FIELDS_NAMESPACE_PREFIX,
                datasource_luid=datasource_luid,
            ),
            "candidate_values_deleted": self._delete_by_namespace_prefix(
                self._CANDIDATE_VALUES_NAMESPACE_PREFIX,
                datasource_luid=datasource_luid,
            ),
            "fewshot_examples_deleted": self._delete_by_namespace_prefix(
                self._FEWSHOT_EXAMPLES_NAMESPACE_PREFIX,
                datasource_luid=datasource_luid,
            ),
            "filter_value_deleted": self._delete_by_namespace_prefix(
                self._FILTER_VALUE_NAMESPACE_PREFIX,
                datasource_luid=datasource_luid,
            ),
            "synonym_deleted": self._delete_by_namespace_prefix(
                self._SYNONYM_NAMESPACE_PREFIX,
                datasource_luid=datasource_luid,
            ),
            # feedback 属于用户纠错审计，不在 schema 变化时自动清除。
            "feedback_deleted": 0,
        }
        report = self._build_report(
            trigger="schema_change",
            datasource_luid=datasource_luid,
            scope_key=None,
            counts=counts,
            previous_schema_hash=previous_schema_hash,
            new_schema_hash=new_schema_hash,
        )
        logger.info(
            "MemoryInvalidationService schema_change: datasource=%s total_deleted=%s",
            datasource_luid,
            report["total_deleted"],
        )
        return report

    def clear_scope(
        self,
        *,
        datasource_luid: str,
        scope_key: str,
    ) -> dict[str, Any]:
        """按 scope_key + datasource_luid 清理当前租户/用户分区。"""
        counts = {
            "query_cache_deleted": self._delete_query_cache_entries(
                datasource_luid=datasource_luid,
                scope_key=scope_key,
            ),
            "candidate_fields_deleted": self._delete_by_namespace_prefix(
                self._CANDIDATE_FIELDS_NAMESPACE_PREFIX,
                datasource_luid=datasource_luid,
                scope_key=scope_key,
            ),
            "candidate_values_deleted": self._delete_by_namespace_prefix(
                self._CANDIDATE_VALUES_NAMESPACE_PREFIX,
                datasource_luid=datasource_luid,
                scope_key=scope_key,
            ),
            "fewshot_examples_deleted": self._delete_by_namespace_prefix(
                self._FEWSHOT_EXAMPLES_NAMESPACE_PREFIX,
                datasource_luid=datasource_luid,
                scope_key=scope_key,
            ),
            "filter_value_deleted": self._delete_by_namespace_prefix(
                self._FILTER_VALUE_NAMESPACE_PREFIX,
                datasource_luid=datasource_luid,
                scope_key=scope_key,
            ),
            "synonym_deleted": self._delete_by_namespace_prefix(
                self._SYNONYM_NAMESPACE_PREFIX,
                datasource_luid=datasource_luid,
                scope_key=scope_key,
            ),
            "feedback_deleted": self._delete_by_namespace_prefix(
                self._FEEDBACK_NAMESPACE_PREFIX,
                datasource_luid=datasource_luid,
                scope_key=scope_key,
            ),
        }
        report = self._build_report(
            trigger="scope_reset",
            datasource_luid=datasource_luid,
            scope_key=scope_key,
            counts=counts,
        )
        logger.info(
            "MemoryInvalidationService scope_reset: datasource=%s scope=%s total_deleted=%s",
            datasource_luid,
            self._normalize_scope_key(scope_key),
            report["total_deleted"],
        )
        return report

    def clear_datasource(
        self,
        *,
        datasource_luid: str,
    ) -> dict[str, Any]:
        """按 datasource 清理所有 scope 分区。"""
        counts = {
            "query_cache_deleted": self._delete_query_cache_entries(
                datasource_luid=datasource_luid,
            ),
            "candidate_fields_deleted": self._delete_by_namespace_prefix(
                self._CANDIDATE_FIELDS_NAMESPACE_PREFIX,
                datasource_luid=datasource_luid,
            ),
            "candidate_values_deleted": self._delete_by_namespace_prefix(
                self._CANDIDATE_VALUES_NAMESPACE_PREFIX,
                datasource_luid=datasource_luid,
            ),
            "fewshot_examples_deleted": self._delete_by_namespace_prefix(
                self._FEWSHOT_EXAMPLES_NAMESPACE_PREFIX,
                datasource_luid=datasource_luid,
            ),
            "filter_value_deleted": self._delete_by_namespace_prefix(
                self._FILTER_VALUE_NAMESPACE_PREFIX,
                datasource_luid=datasource_luid,
            ),
            "synonym_deleted": self._delete_by_namespace_prefix(
                self._SYNONYM_NAMESPACE_PREFIX,
                datasource_luid=datasource_luid,
            ),
            "feedback_deleted": self._delete_by_namespace_prefix(
                self._FEEDBACK_NAMESPACE_PREFIX,
                datasource_luid=datasource_luid,
            ),
        }
        report = self._build_report(
            trigger="datasource_reset",
            datasource_luid=datasource_luid,
            scope_key=None,
            counts=counts,
        )
        logger.info(
            "MemoryInvalidationService datasource_reset: datasource=%s total_deleted=%s",
            datasource_luid,
            report["total_deleted"],
        )
        return report


__all__ = ["MemoryInvalidationService"]
