# -*- coding: utf-8 -*-
"""检索与记忆平面的反馈学习服务。

这里统一处理两类事情：
1. 成功查询后的受控记忆写入。
2. 检索 trace 与记忆审计的持久化。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Callable, Optional

from langgraph.types import RunnableConfig

from analytics_assistant.src.agents.base.context import get_context
from analytics_assistant.src.agents.semantic_parser.components import (
    FeedbackLearner,
    QueryCache,
    build_query_cache_scope_key,
    get_query_cache,
)
from analytics_assistant.src.agents.semantic_parser.schemas.output import SemanticOutput
from analytics_assistant.src.agents.semantic_parser.schemas.prefilter import (
    ComplexityType,
    PrefilterResult,
)
from analytics_assistant.src.agents.semantic_parser.state import SemanticParserState

from .memory_store import MemoryStore

logger = logging.getLogger(__name__)


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


def _dedupe_refs(refs: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for ref in refs:
        normalized = str(ref or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


class FeedbackLearningService:
    """统一封装成功查询后的记忆写入与可观测记录。"""

    def __init__(
        self,
        *,
        memory_store: Optional[MemoryStore] = None,
        query_cache_getter: Optional[Callable[[], QueryCache]] = None,
        learner_getter: Optional[Callable[[], FeedbackLearner]] = None,
    ) -> None:
        self._memory_store = memory_store or MemoryStore()
        self._query_cache_getter = query_cache_getter or get_query_cache
        self._learner_getter = learner_getter or FeedbackLearner

    def _build_retrieval_trace_payload(
        self,
        *,
        state: SemanticParserState,
        semantic_output: SemanticOutput,
        datasource_luid: str,
        schema_hash: Optional[str],
        request_id: Optional[str],
        session_id: Optional[str],
        run_id: Optional[str],
        user_id: Optional[str],
        scope_key: str,
        optimization_metrics: dict[str, Any],
        memory_target_refs: list[str],
        memory_write_refs: list[str],
        memory_write_reasons: list[str],
    ) -> dict[str, Any]:
        return {
            "query_id": semantic_output.query_id,
            "question": str(state.get("question") or ""),
            "datasource_luid": datasource_luid,
            "schema_hash": schema_hash,
            "request_id": request_id,
            "session_id": session_id,
            "run_id": run_id,
            "user_id": user_id,
            "query_cache_scope_key": scope_key,
            "query_cache_hit": bool(state.get("cache_hit", False)),
            "feature_cache_hit": bool(optimization_metrics.get("feature_cache_hit", False)),
            "field_candidate_count": len(state.get("field_candidates") or []),
            "few_shot_example_count": len(state.get("few_shot_examples") or []),
            "candidate_fields_ref": state.get("candidate_fields_ref"),
            "candidate_values_ref": state.get("candidate_values_ref"),
            "fewshot_examples_ref": state.get("fewshot_examples_ref"),
            "field_retriever_rerank_enabled": bool(
                optimization_metrics.get("field_retriever_rerank_enabled", False)
            ),
            "few_shot_skipped": bool(optimization_metrics.get("few_shot_skipped", False)),
            "parallel_retrieval_executed": bool(
                optimization_metrics.get("parallel_retrieval_executed", False)
            ),
            "retrieval_strategy": list(optimization_metrics.get("retrieval_strategy") or []),
            "candidate_count_before_rerank": int(
                optimization_metrics.get("candidate_count_before_rerank", 0)
            ),
            "candidate_count_after_rerank": int(
                optimization_metrics.get("candidate_count_after_rerank", 0)
            ),
            "is_degraded": bool(state.get("is_degraded", False)),
            "memory_write_count": len(memory_write_refs),
            "memory_write_reasons": list(memory_write_reasons),
            "memory_write_targets": list(memory_target_refs),
            "memory_write_refs": list(memory_write_refs),
            "created_at": datetime.now().isoformat(),
        }

    async def persist_success(
        self,
        *,
        state: SemanticParserState,
        config: Optional[RunnableConfig],
        semantic_output: SemanticOutput,
        semantic_query: Any,
        optimization_metrics: dict[str, Any],
    ) -> dict[str, Any]:
        """在成功语义解析后写入 query cache、value memory 和审计记录。"""
        question = str(state.get("question") or "")
        datasource_luid = str(state.get("datasource_luid") or "")
        confirmed_filters = list(state.get("confirmed_filters") or [])
        prefilter_result_raw = state.get("prefilter_result")
        prefilter_result = (
            PrefilterResult.model_validate(prefilter_result_raw)
            if prefilter_result_raw else None
        )
        ctx = get_context(config) if config else None
        schema_hash = getattr(ctx, "schema_hash", None)
        scope_key = str(
            getattr(ctx, "query_cache_scope_key", "")
            or build_query_cache_scope_key(
                tenant_domain=getattr(getattr(ctx, "auth", None), "domain", None),
                tenant_site=getattr(getattr(ctx, "auth", None), "site", None),
                user_id=getattr(ctx, "user_id", None),
            )
        ).strip() or "global"

        request_id = _get_configurable_value(config, "request_id")
        session_id = _get_configurable_value(config, "session_id")
        run_id = _get_configurable_value(config, "run_id") or request_id
        user_id = getattr(ctx, "user_id", None)

        memory_target_refs: list[str] = []
        memory_write_refs: list[str] = []
        memory_write_reasons: list[str] = []

        if datasource_luid and semantic_query:
            cache = self._query_cache_getter()
            if schema_hash:
                include_cache_embedding = (
                    bool(state.get("is_degraded", False))
                    or (bool(prefilter_result.low_confidence) if prefilter_result else False)
                    or (
                        prefilter_result.detected_complexity != [ComplexityType.SIMPLE]
                        if prefilter_result else False
                    )
                )
                optimization_metrics["query_cache_embedding_written"] = include_cache_embedding
                cache_written = cache.set(
                    question=question,
                    datasource_luid=datasource_luid,
                    schema_hash=schema_hash,
                    semantic_output=state.get("semantic_output"),
                    query=semantic_query,
                    analysis_plan=state.get("analysis_plan"),
                    global_understanding=state.get("global_understanding"),
                    include_embedding=include_cache_embedding,
                    scope_key=scope_key,
                )
                if cache_written:
                    target_ref = self._memory_store.build_query_cache_ref(
                        question=question,
                        datasource_luid=datasource_luid,
                        scope_key=scope_key,
                    )
                    memory_target_refs.append(target_ref)
                    memory_write_refs.append(
                        self._memory_store.record_memory_write(
                            datasource_luid=datasource_luid,
                            request_id=request_id,
                            session_id=session_id,
                            run_id=run_id,
                            user_id=user_id,
                            reason="query_cache_write",
                            target_ref=target_ref,
                            metadata={
                                "query_id": semantic_output.query_id,
                                "schema_hash": schema_hash,
                                "include_embedding": include_cache_embedding,
                                "scope_key": scope_key,
                            },
                            scope_key=scope_key,
                        )
                    )
                    memory_write_reasons.append("query_cache_write")
            else:
                logger.warning("FeedbackLearningService: 缺少 schema_hash，跳过 QueryCache 写入")

        if confirmed_filters and datasource_luid:
            learner = self._learner_getter()
            for conf in confirmed_filters:
                learned = await learner.learn_filter_value_correction(
                    field_name=conf.get("field_name", ""),
                    original_value=conf.get("original_value", ""),
                    confirmed_value=conf.get("confirmed_value", ""),
                    datasource_luid=datasource_luid,
                    scope_key=scope_key,
                )
                if not learned:
                    continue

                target_ref = self._memory_store.build_filter_value_ref(
                    field_name=str(conf.get("field_name") or ""),
                    original_value=str(conf.get("original_value") or ""),
                    datasource_luid=datasource_luid,
                    scope_key=scope_key,
                )
                memory_target_refs.append(target_ref)
                memory_write_refs.append(
                    self._memory_store.record_memory_write(
                        datasource_luid=datasource_luid,
                        request_id=request_id,
                        session_id=session_id,
                        run_id=run_id,
                        user_id=user_id,
                        reason="filter_value_confirmation",
                        target_ref=target_ref,
                        metadata={
                            "field_name": conf.get("field_name"),
                            "original_value": conf.get("original_value"),
                            "confirmed_value": conf.get("confirmed_value"),
                            "scope_key": scope_key,
                        },
                        scope_key=scope_key,
                    )
                )
                memory_write_reasons.append("filter_value_confirmation")

        retrieval_trace_key = str(semantic_output.query_id or "").strip()
        if not retrieval_trace_key:
            retrieval_trace_key = datetime.now().strftime("%Y%m%d%H%M%S%f")

        retrieval_trace_ref = None
        if datasource_luid:
            retrieval_trace_ref = self._memory_store.put_retrieval_trace(
                datasource_luid=datasource_luid,
                key=retrieval_trace_key,
                scope_key=scope_key,
                payload=self._build_retrieval_trace_payload(
                    state=state,
                    semantic_output=semantic_output,
                    datasource_luid=datasource_luid,
                    schema_hash=schema_hash,
                    request_id=request_id,
                    session_id=session_id,
                    run_id=run_id,
                    user_id=user_id,
                    scope_key=scope_key,
                    optimization_metrics=optimization_metrics,
                    memory_target_refs=_dedupe_refs(memory_target_refs),
                    memory_write_refs=_dedupe_refs(memory_write_refs),
                    memory_write_reasons=_dedupe_refs(memory_write_reasons),
                ),
            )

        return {
            "retrieval_trace_ref": retrieval_trace_ref,
            "memory_write_refs": _dedupe_refs(memory_write_refs),
        }
