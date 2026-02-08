# -*- coding: utf-8 -*-
"""
RAG 检索与自学习 Mixin

负责 RAG 索引初始化、检索匹配、自学习存储。
从 inference.py 拆分而来。
"""
import logging
from typing import Any, Callable, Awaitable, Dict, List, Optional, Tuple

from analytics_assistant.src.core.schemas.data_model import Field
from analytics_assistant.src.core.schemas.enums import DimensionCategory, MeasureCategory
from analytics_assistant.src.agents.field_semantic.schemas import (
    FieldSemanticAttributes,
)
from analytics_assistant.src.infra.config import get_config
from analytics_assistant.src.infra.rag import (
    get_rag_service,
    IndexConfig,
    IndexDocument,
    IndexBackend,
)
from analytics_assistant.src.agents.field_semantic.utils import (
    FIELD_SEMANTIC_PATTERNS_INDEX,
    PatternSource,
    build_enhanced_index_text,
    generate_pattern_id,
    _get_rag_threshold_seed,
    _get_rag_threshold_unverified,
)

logger = logging.getLogger(__name__)


class RAGMixin:
    """RAG 检索与自学习 Mixin

    提供 RAG 索引初始化、批量检索、自学习存储功能。
    需要宿主类提供:
    - self._enable_rag
    - self._rag_initialized
    - self._pattern_store
    - self._enable_self_learning
    - self._high_confidence
    """

    def _get_index_count(self) -> int:
        """获取向量索引中的模式数量"""
        try:
            rag_service = get_rag_service()
            index_info = rag_service.index.get_index_info(FIELD_SEMANTIC_PATTERNS_INDEX)
            if index_info:
                return index_info.document_count
        except Exception as e:
            logger.warning(f"获取索引模式数量失败: {e}")
        return 0

    def _init_rag(self) -> None:
        """初始化 RAG 检索器"""
        if self._rag_initialized:
            return

        if not self._enable_rag:
            self._rag_initialized = True
            return

        try:
            rag_service = get_rag_service()

            patterns = self._load_patterns()
            if not patterns:
                patterns = self._init_seed_patterns()

            if not patterns:
                self._rag_initialized = True
                return

            existing_index = rag_service.index.get_index(FIELD_SEMANTIC_PATTERNS_INDEX)
            if existing_index is not None:
                logger.info(f"RAG 索引已存在: {FIELD_SEMANTIC_PATTERNS_INDEX}")
                self._rag_initialized = True
                return

            app_config = get_config()
            vector_cfg = app_config.config.get("vector_storage", {})
            index_dir = vector_cfg.get("index_dir", "data/indexes")

            documents = []
            for p in patterns:
                index_text = build_enhanced_index_text(
                    caption=p["field_caption"],
                    business_description=p.get("business_description", p["field_caption"]),
                    aliases=p.get("aliases", []),
                    role=p.get("role", "dimension"),
                    data_type=p["data_type"],
                )

                metadata = {
                    "field_caption": p["field_caption"],
                    "data_type": p["data_type"],
                    "role": p.get("role", "dimension"),
                    "source": p.get("source", ""),
                    "verified": p.get("verified", False),
                }

                if p.get("role") == "measure":
                    metadata["measure_category"] = p.get("measure_category", "other")
                else:
                    metadata["category"] = p.get("category", "other")
                    metadata["category_detail"] = p.get("category_detail", "")

                doc = IndexDocument(
                    id=p["pattern_id"],
                    content=index_text,
                    metadata=metadata,
                )
                documents.append(doc)

            config = IndexConfig(
                backend=IndexBackend.FAISS,
                persist_directory=index_dir,
                default_top_k=5,
                score_threshold=_get_rag_threshold_seed(),
            )

            rag_service.index.create_index(
                name=FIELD_SEMANTIC_PATTERNS_INDEX,
                config=config,
                documents=documents,
            )
            logger.info(f"RAG 索引创建完成: {len(patterns)} 个模式")

        except Exception as e:
            logger.warning(f"RAG 初始化失败: {e}")

        self._rag_initialized = True

    async def _rag_search(
        self,
        fields: List[Field],
    ) -> Tuple[Dict[str, FieldSemanticAttributes], List[Field]]:
        """
        RAG 批量检索，返回 (命中结果, 未命中字段)

        优化：使用 batch_search_async 批量检索，避免逐个字段调用 embedding API
        """
        if not fields:
            return {}, []

        results: Dict[str, FieldSemanticAttributes] = {}
        misses: List[Field] = []

        rag_threshold_seed = _get_rag_threshold_seed()
        rag_threshold_unverified = _get_rag_threshold_unverified()

        try:
            rag_service = get_rag_service()

            if rag_service.index.get_index(FIELD_SEMANTIC_PATTERNS_INDEX) is None:
                logger.warning(f"RAG 索引不存在: {FIELD_SEMANTIC_PATTERNS_INDEX}")
                return {}, fields

            field_map: Dict[str, Field] = {}
            queries: List[str] = []
            for f in fields:
                name = f.caption or f.name
                field_map[name] = f
                queries.append(name)

            logger.info(f"RAG 批量检索: {len(queries)} 个字段")

            batch_results = await rag_service.retrieval.batch_search_async(
                index_name=FIELD_SEMANTIC_PATTERNS_INDEX,
                queries=queries,
                top_k=3,
            )

            for name, search_results in batch_results.items():
                f = field_map.get(name)
                if not f:
                    continue

                if not search_results:
                    misses.append(f)
                    continue

                best = search_results[0]

                if best.score < rag_threshold_seed:
                    misses.append(f)
                    continue

                pattern = self._pattern_store.get(best.doc_id) if self._pattern_store else None

                if not pattern:
                    misses.append(f)
                    continue

                source = pattern.get("source", "llm")
                verified = pattern.get("verified", False)
                threshold = rag_threshold_seed if source == PatternSource.SEED.value or verified else rag_threshold_unverified

                if best.score < threshold:
                    misses.append(f)
                    continue

                pattern_role = pattern.get("role", "dimension")
                if pattern_role == "measure":
                    try:
                        measure_cat = MeasureCategory(pattern.get("measure_category", "other"))
                    except ValueError:
                        measure_cat = MeasureCategory.OTHER

                    pattern_caption = pattern.get("field_caption", "")
                    inherit_aliases = pattern.get("aliases", []) if pattern_caption.lower() == name.lower() else []

                    results[name] = FieldSemanticAttributes(
                        role="measure",
                        measure_category=measure_cat,
                        business_description=pattern.get("business_description", name),
                        aliases=inherit_aliases,
                        confidence=best.score,
                        reasoning=f"RAG 匹配: {pattern['field_caption']} ({best.score:.2f})",
                    )
                else:
                    try:
                        category = DimensionCategory(pattern.get("category", "other"))
                    except ValueError:
                        category = DimensionCategory.OTHER

                    pattern_caption = pattern.get("field_caption", "")
                    inherit_aliases = pattern.get("aliases", []) if pattern_caption.lower() == name.lower() else []

                    results[name] = FieldSemanticAttributes(
                        role="dimension",
                        category=category,
                        category_detail=pattern.get("category_detail", "other-unknown"),
                        level=pattern.get("level", 3),
                        granularity=pattern.get("granularity", "medium"),
                        business_description=pattern.get("business_description", name),
                        aliases=inherit_aliases,
                        confidence=best.score,
                        reasoning=f"RAG 匹配: {pattern['field_caption']} ({best.score:.2f})",
                    )

            logger.info(f"RAG 批量检索完成: 命中 {len(results)} 个, 未命中 {len(misses)} 个")

        except Exception as e:
            logger.warning(f"RAG 批量检索失败: {e}")
            return {}, fields

        return results, misses

    def _store_to_rag(
        self,
        results: Dict[str, FieldSemanticAttributes],
        fields: List[Field],
        datasource_luid: str,
    ) -> int:
        """将高置信度结果存入 RAG"""
        if not self._pattern_store or not self._enable_self_learning:
            return 0

        field_map = {f.caption or f.name: f for f in fields}
        pattern_ids = self._pattern_store.get("_pattern_index") or []
        new_patterns = []

        for name, attrs in results.items():
            if attrs.confidence < self._high_confidence:
                continue
            if "种子匹配" in attrs.reasoning or "RAG 匹配" in attrs.reasoning:
                continue

            f = field_map.get(name)
            if not f:
                continue

            pid = generate_pattern_id(name, f.data_type, datasource_luid)
            if self._pattern_store.get(pid):
                continue

            pattern = {
                "pattern_id": pid,
                "field_caption": name,
                "data_type": f.data_type,
                "role": attrs.role,
                "business_description": attrs.business_description,
                "aliases": attrs.aliases,
                "reasoning": attrs.reasoning,
                "confidence": attrs.confidence,
                "source": PatternSource.LLM.value,
                "verified": False,
                "datasource_luid": datasource_luid,
            }

            if attrs.role == "measure":
                pattern["measure_category"] = attrs.measure_category.value if attrs.measure_category else "other"
            else:
                pattern["category"] = attrs.category.value if attrs.category else "other"
                pattern["category_detail"] = attrs.category_detail or "other-unknown"
                pattern["level"] = attrs.level or 3
                pattern["granularity"] = attrs.granularity or "medium"

            self._pattern_store.set(pid, pattern)
            pattern_ids.append(pid)
            new_patterns.append(pattern)

        if new_patterns:
            self._pattern_store.set("_pattern_index", pattern_ids)
            self._add_patterns_to_index(new_patterns)
            logger.info(f"自学习: 存储 {len(new_patterns)} 个新模式")

        return len(new_patterns)

    def _add_patterns_to_index(self, patterns: List[Dict[str, Any]]) -> None:
        """增量添加 patterns 到索引"""
        if not patterns:
            return

        try:
            rag_service = get_rag_service()

            if rag_service.index.get_index(FIELD_SEMANTIC_PATTERNS_INDEX) is None:
                logger.warning(f"RAG 索引不存在，跳过增量更新: {FIELD_SEMANTIC_PATTERNS_INDEX}")
                return

            documents = []
            for p in patterns:
                index_text = build_enhanced_index_text(
                    caption=p["field_caption"],
                    business_description=p.get("business_description", p["field_caption"]),
                    aliases=p.get("aliases", []),
                    role=p.get("role", "dimension"),
                    data_type=p["data_type"],
                )

                metadata = {
                    "field_caption": p["field_caption"],
                    "data_type": p["data_type"],
                    "role": p.get("role", "dimension"),
                    "source": p.get("source", ""),
                    "verified": p.get("verified", False),
                }

                if p.get("role") == "measure":
                    metadata["measure_category"] = p.get("measure_category", "other")
                else:
                    metadata["category"] = p.get("category", "other")
                    metadata["category_detail"] = p.get("category_detail", "")

                doc = IndexDocument(
                    id=p["pattern_id"],
                    content=index_text,
                    metadata=metadata,
                )
                documents.append(doc)

            added_count = rag_service.index.add_documents(
                index_name=FIELD_SEMANTIC_PATTERNS_INDEX,
                documents=documents,
            )

            logger.debug(f"RAG 索引增量更新: +{added_count} 条")

        except Exception as e:
            logger.warning(f"更新 RAG 索引失败: {e}")
