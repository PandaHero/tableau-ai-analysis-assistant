# -*- coding: utf-8 -*-
"""
维度模式 RAG 检索器

使用 infra/rag 通用组件实现维度模式的向量检索，
并复用 LangGraph Store 存储模式元数据。

职责：
- 批量检索相似模式（仅用元数据）
- 从 LangGraph Store 获取模式详情
- 存储新模式到 RAG

阈值分层策略：
- seed/verified: 使用标准阈值 0.92
- llm/unverified: 使用更高阈值 0.95（防止 RAG 污染）

Requirements: 1.1, 2.1, 2.2
"""
from typing import List, Dict, Any, Optional, Tuple
import hashlib
import logging

from tableau_assistant.src.infra.rag import FieldIndexer, IndexConfig
from tableau_assistant.src.infra.rag.models import RetrievalResult
from tableau_assistant.src.infra.storage.data_model import FieldMetadata

from tableau_assistant.src.agents.dimension_hierarchy.cache_storage import (
    DimensionHierarchyCacheStorage,
    RAG_SIMILARITY_THRESHOLD,
    RAG_SIMILARITY_THRESHOLD_UNVERIFIED,
    PatternSource,
)


logger = logging.getLogger(__name__)


class DimensionRAGRetriever:
    """
    维度模式 RAG 检索器（基于 infra/rag）

    复用 FieldIndexer + EmbeddingRetriever 实现向量检索，
    并使用 LangGraph Store 存储模式元数据。
    """

    # 检索时的候选数量（top-k），用于处理 metadata 缺失或阈值边缘情况
    DEFAULT_SEARCH_K = 3
    DEFAULT_LOAD_LIMIT = 10000
    INDEX_DATASOURCE_LUID = "dimension_patterns"

    def __init__(
        self,
        cache_storage: DimensionHierarchyCacheStorage,
        field_indexer: Optional[FieldIndexer] = None,
        similarity_threshold: float = RAG_SIMILARITY_THRESHOLD,
        similarity_threshold_unverified: float = RAG_SIMILARITY_THRESHOLD_UNVERIFIED,
        load_limit: int = DEFAULT_LOAD_LIMIT,
    ):
        """
        Args:
            cache_storage: 缓存存储实例
            field_indexer: FieldIndexer 实例（可选，不传则自动创建）
            similarity_threshold: 标准相似度阈值（seed/verified）
            similarity_threshold_unverified: 未验证结果的相似度阈值（llm/unverified）
            load_limit: 加载模式的最大数量
        """
        self._cache_storage = cache_storage
        self.similarity_threshold = similarity_threshold
        self.similarity_threshold_unverified = similarity_threshold_unverified
        self._load_limit = load_limit

        if field_indexer is None:
            index_config = IndexConfig(
                max_samples=0,
                include_formula=False,
                include_table_caption=False,
                include_category=False,
            )
            field_indexer = FieldIndexer(
                index_config=index_config,
                datasource_luid=self.INDEX_DATASOURCE_LUID,
                index_dir="data/indexes",
                use_cache=True,
            )

        self._indexer = field_indexer
        self._pattern_fields: Dict[str, FieldMetadata] = {}
        self._index_initialized = False

    # ═══════════════════════════════════════════════════════════
    # 内部辅助
    # ═══════════════════════════════════════════════════════════

    def _get_effective_threshold(self, pattern: Optional[Dict[str, Any]]) -> float:
        """根据 pattern 来源获取有效阈值（污染控制）"""
        if not pattern:
            return self.similarity_threshold

        source = pattern.get("source", "llm")
        verified = pattern.get("verified", False)

        if source == "seed" or verified:
            return self.similarity_threshold
        return self.similarity_threshold_unverified

    @staticmethod
    def generate_pattern_id(
        field_caption: str,
        data_type: str,
        datasource_luid: Optional[str] = None,
    ) -> str:
        """生成模式 ID（包含 data_type 避免同名不同类型字段碰撞）"""
        scope = datasource_luid or "global"
        key = f"{field_caption}|{data_type}|{scope}"
        return hashlib.md5(key.encode()).hexdigest()[:16]

    def _build_field_metadata(
        self,
        pattern_id: str,
        field_caption: str,
        data_type: str,
        category: Optional[str] = None,
    ) -> FieldMetadata:
        """构建用于索引的 FieldMetadata"""
        return FieldMetadata(
            name=pattern_id,
            fieldCaption=field_caption,
            role="dimension",
            dataType=data_type,
            category=category,
            sample_values=None,
        )

    def _build_query_text_metadata_only(self, field_caption: str, data_type: str) -> str:
        """构建查询文本（仅用元数据，不含样例数据）"""
        temp_field = self._build_field_metadata("_query", field_caption, data_type)
        return self._indexer.build_index_text(temp_field)

    def _refresh_pattern_metadata(self) -> None:
        """从缓存存储刷新模式元数据"""
        items = self._cache_storage.get_all_pattern_metadata(limit=self._load_limit)
        self._pattern_fields.clear()
        for data in items:
            if not data:
                continue
            pattern_id = data.get("pattern_id")
            field_caption = data.get("field_caption") or data.get("field_name")
            data_type = data.get("data_type")
            if not pattern_id or not field_caption or not data_type:
                continue
            field = self._build_field_metadata(
                pattern_id=pattern_id,
                field_caption=field_caption,
                data_type=data_type,
                category=data.get("category"),
            )
            self._pattern_fields[pattern_id] = field

    def _rebuild_index_from_metadata(self) -> bool:
        """从元数据重建索引"""
        if self._indexer is None or not self._pattern_fields:
            return False

        fields = list(self._pattern_fields.values())
        self._indexer.index_fields(fields, force_rebuild=True)
        self._indexer.save_index()
        return True

    def _ensure_index(self) -> None:
        """确保索引可用并与元数据一致"""
        if self._indexer is None:
            return

        self._refresh_pattern_metadata()
        metadata_count = len(self._pattern_fields)
        index_count = self._indexer.field_count

        if not self._index_initialized or index_count != metadata_count:
            if metadata_count == 0:
                self._index_initialized = True
                return
            self._rebuild_index_from_metadata()
            self._index_initialized = True

    # ═══════════════════════════════════════════════════════════
    # 公开接口
    # ═══════════════════════════════════════════════════════════

    def get_index_count(self) -> int:
        """获取索引中的模式数量"""
        return self._indexer.field_count if self._indexer else 0

    def get_metadata_count(self) -> int:
        """获取元数据数量"""
        return len(self._cache_storage.get_all_pattern_metadata(limit=self._load_limit))

    def rebuild_index_from_metadata(self) -> bool:
        """从元数据重建索引"""
        self._refresh_pattern_metadata()
        return self._rebuild_index_from_metadata()

    def batch_search_metadata_only(
        self,
        fields: List[Dict[str, Any]],
        k: int = DEFAULT_SEARCH_K,
    ) -> Dict[str, Tuple[Optional[Dict[str, Any]], float]]:
        """
        批量检索（仅用元数据，不含样例数据）

        Returns:
            {field_name: (pattern_dict or None, similarity_score)}
        """
        if not fields:
            return {}

        self._ensure_index()
        results: Dict[str, Tuple[Optional[Dict[str, Any]], float]] = {}

        for f in fields:
            field_name = f["field_name"]
            query_text = self._build_query_text_metadata_only(
                f["field_caption"],
                f["data_type"],
            )

            search_results: List[RetrievalResult] = self._indexer.search(query_text, top_k=k)
            if not search_results:
                results[field_name] = (None, 0.0)
                continue

            best_similarity = 0.0
            matched_pattern = None

            for result in search_results:
                pattern_id = result.field_chunk.field_name
                similarity = result.score
                best_similarity = max(best_similarity, similarity)

                pattern = self._cache_storage.get_pattern_metadata(pattern_id)
                if pattern is None:
                    continue

                effective_threshold = self._get_effective_threshold(pattern)
                if similarity >= effective_threshold:
                    matched_pattern = pattern
                    best_similarity = similarity
                    break

            if matched_pattern:
                results[field_name] = (matched_pattern, best_similarity)
            else:
                results[field_name] = (None, best_similarity)

        hit_count = sum(1 for _, (p, _) in results.items() if p is not None)
        log_msg = (
            f"RAG 检索: {len(fields)} 字段, 命中 {hit_count} "
            f"({hit_count/len(fields)*100:.0f}%), "
            f"标准阈值={self.similarity_threshold}, 未验证阈值={self.similarity_threshold_unverified}"
        )
        logger.info(log_msg)

        return results

    def store_pattern(
        self,
        field_caption: str,
        data_type: str,
        category: str,
        category_detail: str,
        level: int,
        granularity: str,
        reasoning: str,
        confidence: float,
        datasource_luid: Optional[str] = None,
        sample_values: Optional[List[str]] = None,
        unique_count: int = 0,
        source: str = "llm",
        verified: bool = False,
    ) -> bool:
        """存入 RAG 模式（LangGraph Store + infra/rag 索引）"""
        pattern_id = self.generate_pattern_id(field_caption, data_type, datasource_luid)
        existing = self._cache_storage.get_pattern_metadata(pattern_id)
        if existing:
            logger.debug(f"模式已存在，跳过: {pattern_id} ({field_caption})")
            return True

        try:
            source_enum = PatternSource(source) if isinstance(source, str) else source
            metadata_stored = self._cache_storage.store_pattern_metadata(
                pattern_id=pattern_id,
                field_caption=field_caption,
                data_type=data_type,
                sample_values=sample_values or [],
                unique_count=unique_count,
                category=category,
                category_detail=category_detail,
                level=level,
                granularity=granularity,
                reasoning=reasoning,
                confidence=confidence,
                datasource_luid=datasource_luid,
                source=source_enum,
                verified=verified,
            )
            if not metadata_stored:
                logger.warning(f"存储 metadata 失败，跳过索引: {pattern_id}")
                return False

            field = self._build_field_metadata(
                pattern_id=pattern_id,
                field_caption=field_caption,
                data_type=data_type,
                category=category,
            )
            self._pattern_fields[pattern_id] = field
            self._indexer.index_fields(list(self._pattern_fields.values()), force_rebuild=False)
            self._indexer.save_index()
            return True

        except Exception as e:
            logger.warning(f"存储模式失败: {e}")
            return False

    def batch_store_patterns(
        self,
        patterns: List[Dict[str, Any]],
        save_after_all: bool = True,
    ) -> Dict[str, int]:
        """
        批量存入 RAG 模式

        Returns:
            统计字典：
            - metadata_written: metadata 成功写入数（含已存在跳过的）
            - faiss_written: 实际索引写入数（增量）
            - skipped_existing: 已存在跳过数
            - total: 总请求数
        """
        result = {
            "metadata_written": 0,
            "faiss_written": 0,
            "skipped_existing": 0,
            "total": len(patterns),
        }

        if not patterns:
            return result

        new_fields = []

        for p in patterns:
            pattern_id = self.generate_pattern_id(
                p["field_caption"],
                p["data_type"],
                p.get("datasource_luid"),
            )

            existing = self._cache_storage.get_pattern_metadata(pattern_id)
            if existing:
                result["metadata_written"] += 1
                result["skipped_existing"] += 1
                continue

            source = p.get("source", "llm")
            source_enum = PatternSource(source) if isinstance(source, str) else source

            stored = self._cache_storage.store_pattern_metadata(
                pattern_id=pattern_id,
                field_caption=p["field_caption"],
                data_type=p["data_type"],
                sample_values=p.get("sample_values") or [],
                unique_count=p.get("unique_count", 0),
                category=p["category"],
                category_detail=p["category_detail"],
                level=p["level"],
                granularity=p["granularity"],
                reasoning=p.get("reasoning", ""),
                confidence=p.get("confidence", 0.0),
                datasource_luid=p.get("datasource_luid"),
                source=source_enum,
                verified=p.get("verified", False),
            )

            if not stored:
                logger.warning(f"存储 metadata 失败，跳过索引: {pattern_id}")
                continue

            result["metadata_written"] += 1

            field = self._build_field_metadata(
                pattern_id=pattern_id,
                field_caption=p["field_caption"],
                data_type=p["data_type"],
                category=p.get("category"),
            )
            new_fields.append(field)
            self._pattern_fields[pattern_id] = field

        if new_fields:
            pre_count = self._indexer.field_count
            self._indexer.index_fields(list(self._pattern_fields.values()), force_rebuild=False)
            if save_after_all:
                self._indexer.save_index()
            post_count = self._indexer.field_count
            result["faiss_written"] = max(0, post_count - pre_count)

        logger.info(
            f"批量存储模式: metadata={result['metadata_written']}/{result['total']}, "
            f"index_new={result['faiss_written']}, 已存在跳过={result['skipped_existing']}"
        )
        return result


__all__ = [
    "DimensionRAGRetriever",
]
