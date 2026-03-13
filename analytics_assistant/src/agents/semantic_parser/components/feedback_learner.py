# -*- coding: utf-8 -*-
"""反馈学习组件。

负责三类持久化学习能力：
1. 记录用户对查询结果的反馈。
2. 学习筛选值修正与字段同义词。
3. 将高质量接受反馈提升为 few-shot 示例。

重构后的隔离原则：
- 所有 feedback/value-memory/synonym-memory 都按 `scope_key + datasource_luid`
  分区，避免跨租户、跨用户串写或互相淘汰。
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Optional

from analytics_assistant.src.infra.config import get_config
from analytics_assistant.src.infra.storage import get_kv_store

from ..schemas.feedback import FeedbackRecord, FeedbackType, SynonymMapping
from ..schemas.intermediate import FewShotExample
from .few_shot_manager import FewShotManager
from .query_cache import build_query_cache_partition_key

logger = logging.getLogger(__name__)


def _get_config() -> dict[str, Any]:
    """读取 feedback_learner 配置。"""
    try:
        config = get_config()
        return config.config.get("semantic_parser", {}).get("feedback_learner", {})
    except Exception as exc:
        logger.warning("无法加载 feedback_learner 配置，使用默认值: %s", exc)
        return {}


class FeedbackLearner:
    """用户反馈学习器。"""

    FEEDBACK_NAMESPACE_PREFIX = ("semantic_parser", "feedback")
    SYNONYM_NAMESPACE_PREFIX = ("semantic_parser", "synonyms")
    FILTER_VALUE_NAMESPACE_PREFIX = ("semantic_parser", "filter_values")

    _DEFAULT_SYNONYM_THRESHOLD = 3
    _DEFAULT_MAX_FEEDBACK_PER_DATASOURCE = 1000
    _DEFAULT_AUTO_PROMOTE_ENABLED = True

    def __init__(
        self,
        store: Optional[Any] = None,
        few_shot_manager: Optional[FewShotManager] = None,
        synonym_threshold: Optional[int] = None,
        max_feedback_per_datasource: Optional[int] = None,
        auto_promote_enabled: Optional[bool] = None,
    ) -> None:
        self._store = store or get_kv_store()
        self._few_shot_manager = few_shot_manager
        # 计数器必须按作用域分区，否则不同用户会互相触发淘汰。
        self._feedback_counts: dict[str, int] = {}
        self._load_config(
            synonym_threshold,
            max_feedback_per_datasource,
            auto_promote_enabled,
        )

    def _load_config(
        self,
        synonym_threshold: Optional[int],
        max_feedback_per_datasource: Optional[int],
        auto_promote_enabled: Optional[bool],
    ) -> None:
        config = _get_config()
        self.synonym_threshold = (
            synonym_threshold
            if synonym_threshold is not None
            else config.get("synonym_threshold", self._DEFAULT_SYNONYM_THRESHOLD)
        )
        self.max_feedback_per_datasource = (
            max_feedback_per_datasource
            if max_feedback_per_datasource is not None
            else config.get(
                "max_feedback_per_datasource",
                self._DEFAULT_MAX_FEEDBACK_PER_DATASOURCE,
            )
        )
        self.auto_promote_enabled = (
            auto_promote_enabled
            if auto_promote_enabled is not None
            else config.get(
                "auto_promote_enabled",
                self._DEFAULT_AUTO_PROMOTE_ENABLED,
            )
        )

    def _normalize_scope_key(self, scope_key: Optional[str]) -> str:
        normalized_scope_key = str(scope_key or "").strip()
        return normalized_scope_key or "global"

    def _make_partition_key(
        self,
        datasource_luid: str,
        *,
        scope_key: Optional[str] = None,
    ) -> str:
        return build_query_cache_partition_key(
            datasource_luid,
            scope_key=self._normalize_scope_key(scope_key),
        )

    def _make_feedback_namespace(
        self,
        datasource_luid: str,
        *,
        scope_key: Optional[str] = None,
    ) -> tuple[str, ...]:
        return (
            *self.FEEDBACK_NAMESPACE_PREFIX,
            self._make_partition_key(datasource_luid, scope_key=scope_key),
        )

    def _make_synonym_namespace(
        self,
        datasource_luid: str,
        *,
        scope_key: Optional[str] = None,
    ) -> tuple[str, ...]:
        return (
            *self.SYNONYM_NAMESPACE_PREFIX,
            self._make_partition_key(datasource_luid, scope_key=scope_key),
        )

    def _make_filter_value_namespace(
        self,
        datasource_luid: str,
        *,
        scope_key: Optional[str] = None,
    ) -> tuple[str, ...]:
        return (
            *self.FILTER_VALUE_NAMESPACE_PREFIX,
            self._make_partition_key(datasource_luid, scope_key=scope_key),
        )

    def _make_synonym_key(self, original_term: str, correct_field: str) -> str:
        return f"{original_term.lower()}:{correct_field.lower()}"

    async def learn_filter_value_correction(
        self,
        field_name: str,
        original_value: str,
        confirmed_value: str,
        datasource_luid: str,
        scope_key: Optional[str] = None,
    ) -> bool:
        if self._store is None:
            logger.warning("FeedbackLearner 存储不可用，无法学习筛选值修正")
            return False

        namespace = self._make_filter_value_namespace(
            datasource_luid,
            scope_key=scope_key,
        )
        key = f"{field_name.lower()}:{original_value.lower()}"

        try:
            item = self._store.get(namespace, key)
            if item is not None and item.value is not None:
                data = dict(item.value)
                data["confirmation_count"] = int(data.get("confirmation_count", 0)) + 1
                data["updated_at"] = datetime.now().isoformat()
            else:
                data = {
                    "field_name": field_name,
                    "original_value": original_value,
                    "confirmed_value": confirmed_value,
                    "datasource_luid": datasource_luid,
                    "scope_key": self._normalize_scope_key(scope_key),
                    "confirmation_count": 1,
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat(),
                }

            self._store.put(namespace, key, data)
            logger.info(
                "FeedbackLearner 已学习筛选值修正: field=%s, '%s' -> '%s', count=%s",
                field_name,
                original_value,
                confirmed_value,
                data["confirmation_count"],
            )
            return True
        except Exception as exc:
            logger.error("FeedbackLearner learn_filter_value_correction 失败: %s", exc)
            return False

    async def record(
        self,
        feedback: FeedbackRecord,
        *,
        scope_key: Optional[str] = None,
    ) -> bool:
        if self._store is None:
            logger.warning("FeedbackLearner 存储不可用，无法记录反馈")
            return False

        namespace = self._make_feedback_namespace(
            feedback.datasource_luid,
            scope_key=scope_key,
        )

        try:
            if not feedback.id:
                feedback.id = f"fb_{uuid.uuid4().hex[:12]}"

            self._store.put(namespace, feedback.id, feedback.model_dump(mode="json"))
            logger.info(
                "FeedbackLearner 已记录反馈: id=%s, type=%s, question='%s...'",
                feedback.id,
                feedback.feedback_type.value,
                feedback.question[:30],
            )

            if (
                feedback.feedback_type == FeedbackType.ACCEPT
                and self.auto_promote_enabled
                and feedback.semantic_output is not None
            ):
                await self._auto_promote(feedback, scope_key=scope_key)

            await self._evict_if_needed(
                feedback.datasource_luid,
                scope_key=scope_key,
            )
            return True
        except Exception as exc:
            logger.error("FeedbackLearner record 失败: %s", exc)
            return False

    async def learn_synonym(
        self,
        original_term: str,
        correct_field: str,
        datasource_luid: str,
        scope_key: Optional[str] = None,
    ) -> bool:
        if self._store is None:
            logger.warning("FeedbackLearner 存储不可用，无法学习同义词")
            return False

        namespace = self._make_synonym_namespace(
            datasource_luid,
            scope_key=scope_key,
        )
        key = self._make_synonym_key(original_term, correct_field)

        try:
            item = self._store.get(namespace, key)
            if item is not None and item.value is not None:
                mapping = SynonymMapping.model_validate(item.value)
                mapping.confirmation_count += 1
                mapping.updated_at = datetime.now()
            else:
                mapping = SynonymMapping(
                    id=f"syn_{uuid.uuid4().hex[:12]}",
                    original_term=original_term,
                    correct_field=correct_field,
                    datasource_luid=datasource_luid,
                    confirmation_count=1,
                )

            self._store.put(namespace, key, mapping.model_dump(mode="json"))
            logger.info(
                "FeedbackLearner 已学习同义词: '%s' -> '%s', count=%s",
                original_term,
                correct_field,
                mapping.confirmation_count,
            )
            return True
        except Exception as exc:
            logger.error("FeedbackLearner learn_synonym 失败: %s", exc)
            return False

    async def promote_to_example(
        self,
        feedback_id: str,
        datasource_luid: str,
        *,
        scope_key: Optional[str] = None,
    ) -> bool:
        if self._store is None:
            logger.warning("FeedbackLearner 存储不可用，无法提升示例")
            return False
        if self._few_shot_manager is None:
            logger.warning("FeedbackLearner FewShotManager 不可用，无法提升示例")
            return False

        feedback = await self.get_feedback(
            feedback_id,
            datasource_luid,
            scope_key=scope_key,
        )
        if feedback is None:
            logger.warning("FeedbackLearner 反馈记录不存在: id=%s", feedback_id)
            return False
        if feedback.feedback_type != FeedbackType.ACCEPT:
            logger.warning(
                "FeedbackLearner 只能提升 ACCEPT 类型反馈: id=%s, type=%s",
                feedback_id,
                feedback.feedback_type.value,
            )
            return False
        if feedback.semantic_output is None:
            logger.warning("FeedbackLearner 反馈缺少 semantic_output: id=%s", feedback_id)
            return False

        example = FewShotExample(
            id=f"ex_{uuid.uuid4().hex[:12]}",
            question=feedback.question,
            restated_question=feedback.restated_question or feedback.question,
            what=feedback.semantic_output.get("what", {}),
            where=feedback.semantic_output.get("where", {}),
            how=feedback.semantic_output.get("how", "SIMPLE"),
            computations=feedback.semantic_output.get("computations"),
            query=feedback.query or "",
            datasource_luid=datasource_luid,
            accepted_count=1,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        success = await self._few_shot_manager.add(example)
        if success:
            logger.info(
                "FeedbackLearner 已提升为示例: feedback_id=%s, example_id=%s",
                feedback_id,
                example.id,
            )
        return success

    async def get_feedback(
        self,
        feedback_id: str,
        datasource_luid: str,
        *,
        scope_key: Optional[str] = None,
    ) -> Optional[FeedbackRecord]:
        if self._store is None:
            return None

        namespace = self._make_feedback_namespace(
            datasource_luid,
            scope_key=scope_key,
        )
        try:
            item = self._store.get(namespace, feedback_id)
            if item is None or item.value is None:
                return None
            return FeedbackRecord.model_validate(item.value)
        except Exception as exc:
            logger.error("FeedbackLearner get_feedback 失败: %s", exc)
            return None

    async def get_synonym_mapping(
        self,
        original_term: str,
        correct_field: str,
        datasource_luid: str,
        *,
        scope_key: Optional[str] = None,
    ) -> Optional[SynonymMapping]:
        if self._store is None:
            return None

        namespace = self._make_synonym_namespace(
            datasource_luid,
            scope_key=scope_key,
        )
        key = self._make_synonym_key(original_term, correct_field)
        try:
            item = self._store.get(namespace, key)
            if item is None or item.value is None:
                return None
            return SynonymMapping.model_validate(item.value)
        except Exception as exc:
            logger.error("FeedbackLearner get_synonym_mapping 失败: %s", exc)
            return None

    async def get_learned_synonyms(
        self,
        datasource_luid: str,
        min_count: Optional[int] = None,
        *,
        scope_key: Optional[str] = None,
    ) -> list[SynonymMapping]:
        if self._store is None:
            return []

        namespace = self._make_synonym_namespace(
            datasource_luid,
            scope_key=scope_key,
        )
        min_count = min_count or 1
        try:
            items = self._store.search(namespace, limit=1000)
            mappings: list[SynonymMapping] = []
            for item in items:
                if item.value is None:
                    continue
                try:
                    mapping = SynonymMapping.model_validate(item.value)
                except Exception as exc:
                    logger.debug("解析同义词映射失败: %s", exc)
                    continue
                if mapping.confirmation_count >= min_count:
                    mappings.append(mapping)

            mappings.sort(key=lambda item: item.confirmation_count, reverse=True)
            return mappings
        except Exception as exc:
            logger.error("FeedbackLearner get_learned_synonyms 失败: %s", exc)
            return []

    async def get_confirmed_synonyms(
        self,
        datasource_luid: str,
        *,
        scope_key: Optional[str] = None,
    ) -> list[SynonymMapping]:
        return await self.get_learned_synonyms(
            datasource_luid,
            min_count=self.synonym_threshold,
            scope_key=scope_key,
        )

    async def list_feedback(
        self,
        datasource_luid: str,
        feedback_type: Optional[FeedbackType] = None,
        limit: int = 100,
        *,
        scope_key: Optional[str] = None,
    ) -> list[FeedbackRecord]:
        if self._store is None:
            return []

        namespace = self._make_feedback_namespace(
            datasource_luid,
            scope_key=scope_key,
        )
        try:
            items = self._store.search(namespace, limit=limit)
            records: list[FeedbackRecord] = []
            for item in items:
                if item.value is None:
                    continue
                try:
                    record = FeedbackRecord.model_validate(item.value)
                except Exception as exc:
                    logger.debug("解析反馈记录失败: %s", exc)
                    continue
                if feedback_type is None or record.feedback_type == feedback_type:
                    records.append(record)

            records.sort(key=lambda item: item.created_at, reverse=True)
            return records[:limit]
        except Exception as exc:
            logger.error("FeedbackLearner list_feedback 失败: %s", exc)
            return []

    async def count_feedback(
        self,
        datasource_luid: str,
        feedback_type: Optional[FeedbackType] = None,
        *,
        scope_key: Optional[str] = None,
    ) -> int:
        records = await self.list_feedback(
            datasource_luid,
            feedback_type=feedback_type,
            limit=self.max_feedback_per_datasource,
            scope_key=scope_key,
        )
        return len(records)

    async def _auto_promote(
        self,
        feedback: FeedbackRecord,
        *,
        scope_key: Optional[str] = None,
    ) -> None:
        if self._few_shot_manager is None:
            return
        try:
            await self.promote_to_example(
                feedback.id,
                feedback.datasource_luid,
                scope_key=scope_key,
            )
        except Exception as exc:
            logger.warning("FeedbackLearner 自动提升失败: %s", exc)

    async def _evict_if_needed(
        self,
        datasource_luid: str,
        *,
        scope_key: Optional[str] = None,
    ) -> None:
        if self._store is None:
            return

        feedback_count_key = self._make_partition_key(
            datasource_luid,
            scope_key=scope_key,
        )
        count = self._feedback_counts.get(feedback_count_key, 0) + 1
        self._feedback_counts[feedback_count_key] = count
        if count <= self.max_feedback_per_datasource:
            return

        namespace = self._make_feedback_namespace(
            datasource_luid,
            scope_key=scope_key,
        )
        try:
            items = self._store.search(
                namespace,
                limit=self.max_feedback_per_datasource + 100,
            )
            self._feedback_counts[feedback_count_key] = len(items)
            if len(items) <= self.max_feedback_per_datasource:
                return

            records_with_key: list[tuple[str, FeedbackRecord]] = []
            for item in items:
                if item.value is None:
                    continue
                try:
                    record = FeedbackRecord.model_validate(item.value)
                except Exception as exc:
                    logger.debug("解析反馈记录失败（淘汰检查）: %s", exc)
                    continue
                records_with_key.append((item.key, record))

            if len(records_with_key) <= self.max_feedback_per_datasource:
                return

            records_with_key.sort(key=lambda item: item[1].created_at)
            to_delete = len(records_with_key) - self.max_feedback_per_datasource
            for index in range(to_delete):
                key, record = records_with_key[index]
                self._store.delete(namespace, key)
                logger.debug("FeedbackLearner 淘汰反馈: id=%s", record.id)

            self._feedback_counts[feedback_count_key] = len(records_with_key) - to_delete
        except Exception as exc:
            logger.error("FeedbackLearner _evict_if_needed 失败: %s", exc)


__all__ = ["FeedbackLearner"]
