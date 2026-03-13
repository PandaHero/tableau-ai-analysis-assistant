# -*- coding: utf-8 -*-
"""统一检索路由器。

当前实现复用已有字段检索与 few-shot 检索能力，不重复实现召回逻辑；
这个路由器负责把分散的检索结果收口为稳定契约，并物化为可追踪的 ref。
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Awaitable, Callable, Optional

from langgraph.types import RunnableConfig

from analytics_assistant.src.agents.base.context import get_context
from analytics_assistant.src.agents.semantic_parser.state import SemanticParserState

from .memory_store import MemoryStore

logger = logging.getLogger(__name__)

_DEFAULT_RETRIEVAL_STRATEGIES = ["exact", "bm25", "embedding", "hybrid"]


def _get_configurable_value(
    config: Optional[RunnableConfig],
    key: str,
) -> Optional[str]:
    if not isinstance(config, dict):
        return None
    configurable = config.get("configurable") or {}
    value = configurable.get(key)
    normalized = str(value or "").strip()
    return normalized or None


class RetrievalRouter:
    """把字段检索、值候选和 few-shot 检索统一收口。"""

    def __init__(
        self,
        *,
        field_retriever: Callable[..., Awaitable[dict[str, Any]]],
        fewshot_retriever: Callable[..., Awaitable[dict[str, Any]]],
        memory_store: Optional[MemoryStore] = None,
    ) -> None:
        self._field_retriever = field_retriever
        self._fewshot_retriever = fewshot_retriever
        self._memory_store = memory_store or MemoryStore()

    def _extract_candidate_values(
        self,
        *,
        field_candidates: list[dict[str, Any]],
        ctx: Any,
    ) -> list[dict[str, Any]]:
        """优先复用字段候选里的 sample_values，缺失时回退到 context.field_samples。"""
        field_samples = getattr(ctx, "field_samples", None) or {}
        candidate_values: list[dict[str, Any]] = []
        seen_fields: set[str] = set()

        for candidate in field_candidates:
            if not isinstance(candidate, dict):
                continue

            field_name = str(
                candidate.get("field_name")
                or candidate.get("field_caption")
                or ""
            ).strip()
            if not field_name:
                continue

            normalized_field = field_name.casefold()
            if normalized_field in seen_fields:
                continue
            seen_fields.add(normalized_field)

            sample_values = list(candidate.get("sample_values") or [])
            if not sample_values:
                sample_info = (
                    field_samples.get(field_name)
                    or field_samples.get(candidate.get("field_caption") or "")
                    or {}
                )
                if isinstance(sample_info, dict):
                    sample_values = list(sample_info.get("sample_values") or [])

            sample_values = [
                str(value).strip()
                for value in sample_values
                if str(value).strip()
            ]
            if not sample_values:
                continue

            candidate_values.append({
                "field_name": field_name,
                "sample_values": sample_values[:10],
            })

        return candidate_values

    def _build_artifact_payload(
        self,
        *,
        question: str,
        datasource_luid: str,
        schema_hash: Optional[str],
        scope_key: str,
        request_id: Optional[str],
        session_id: Optional[str],
        artifact_key: str,
        artifact_value: Any,
    ) -> dict[str, Any]:
        return {
            "question": question,
            "datasource_luid": datasource_luid,
            "schema_hash": schema_hash,
            "scope_key": scope_key,
            "request_id": request_id,
            "session_id": session_id,
            artifact_key: artifact_value,
            "created_at": datetime.now().isoformat(),
        }

    async def retrieve(
        self,
        *,
        state: SemanticParserState,
        config: Optional[RunnableConfig] = None,
    ) -> dict[str, Any]:
        """执行统一检索，并返回实际候选与其物化引用。"""
        start_time = time.time()
        question = str(state.get("question") or "").strip()
        ctx = get_context(config) if config else None
        datasource_luid = str(
            state.get("datasource_luid")
            or getattr(ctx, "datasource_luid", "")
            or ""
        ).strip()

        if not question or not datasource_luid:
            logger.warning("RetrievalRouter: 缺少 question 或 datasource_luid，返回空结果")
            return {
                "field_candidates": [],
                "few_shot_examples": [],
                "candidate_fields_ref": None,
                "candidate_values_ref": None,
                "fewshot_examples_ref": None,
                "optimization_metrics": {
                    "parallel_retrieval_total_ms": 0.0,
                    "parallel_retrieval_executed": False,
                    "retrieval_strategy": [],
                    "candidate_count_before_rerank": 0,
                    "candidate_count_after_rerank": 0,
                },
            }

        raw_field, raw_fewshot = await asyncio.gather(
            self._field_retriever(state, config=config),
            self._fewshot_retriever(state),
            return_exceptions=True,
        )

        if isinstance(raw_field, BaseException):
            logger.error("RetrievalRouter: field_retriever 执行失败: %s", raw_field)
            field_result: dict[str, Any] = {"field_candidates": []}
        else:
            field_result = raw_field

        if isinstance(raw_fewshot, BaseException):
            logger.error("RetrievalRouter: fewshot_retriever 执行失败: %s", raw_fewshot)
            fewshot_result: dict[str, Any] = {"few_shot_examples": []}
        else:
            fewshot_result = raw_fewshot

        field_candidates = list(field_result.get("field_candidates") or [])
        few_shot_examples = list(fewshot_result.get("few_shot_examples") or [])
        candidate_values = self._extract_candidate_values(
            field_candidates=field_candidates,
            ctx=ctx,
        )

        schema_hash = getattr(ctx, "schema_hash", None)
        scope_key = str(getattr(ctx, "query_cache_scope_key", "") or "").strip() or "global"
        request_id = _get_configurable_value(config, "request_id")
        session_id = _get_configurable_value(config, "session_id")

        candidate_fields_ref = self._memory_store.put_candidate_fields(
            question=question,
            datasource_luid=datasource_luid,
            schema_hash=schema_hash,
            scope_key=scope_key,
            payload=self._build_artifact_payload(
                question=question,
                datasource_luid=datasource_luid,
                schema_hash=schema_hash,
                scope_key=scope_key,
                request_id=request_id,
                session_id=session_id,
                artifact_key="field_candidates",
                artifact_value=field_candidates,
            ),
        )
        candidate_values_ref = self._memory_store.put_candidate_values(
            question=question,
            datasource_luid=datasource_luid,
            schema_hash=schema_hash,
            scope_key=scope_key,
            payload=self._build_artifact_payload(
                question=question,
                datasource_luid=datasource_luid,
                schema_hash=schema_hash,
                scope_key=scope_key,
                request_id=request_id,
                session_id=session_id,
                artifact_key="candidate_values",
                artifact_value=candidate_values,
            ),
        )
        fewshot_examples_ref = self._memory_store.put_fewshot_examples(
            question=question,
            datasource_luid=datasource_luid,
            schema_hash=schema_hash,
            scope_key=scope_key,
            payload=self._build_artifact_payload(
                question=question,
                datasource_luid=datasource_luid,
                schema_hash=schema_hash,
                scope_key=scope_key,
                request_id=request_id,
                session_id=session_id,
                artifact_key="few_shot_examples",
                artifact_value=few_shot_examples,
            ),
        )

        total_ms = (time.time() - start_time) * 1000
        field_metrics = field_result.get("optimization_metrics", {})
        fewshot_metrics = fewshot_result.get("optimization_metrics", {})
        retrieval_strategy = list(_DEFAULT_RETRIEVAL_STRATEGIES)
        if bool(field_metrics.get("field_retriever_rerank_enabled", False)):
            retrieval_strategy.append("rerank")

        return {
            "field_candidates": field_candidates,
            "few_shot_examples": few_shot_examples,
            "candidate_fields_ref": candidate_fields_ref,
            "candidate_values_ref": candidate_values_ref,
            "fewshot_examples_ref": fewshot_examples_ref,
            "optimization_metrics": {
                **field_metrics,
                **fewshot_metrics,
                "parallel_retrieval_total_ms": total_ms,
                "parallel_retrieval_executed": True,
                "retrieval_strategy": retrieval_strategy,
                # 现有 FieldRetriever 只输出重排后的结果，先记录稳定口径；
                # 若后续组件暴露 pre-rerank 计数，再替换这里即可。
                "candidate_count_before_rerank": len(field_candidates),
                "candidate_count_after_rerank": len(field_candidates),
            },
        }
