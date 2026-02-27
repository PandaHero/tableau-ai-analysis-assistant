# -*- coding: utf-8 -*-
"""RAG 检索相关方法。依赖主类初始化 self._retriever 和 self.config。"""
import logging
from typing import Any, Optional

from analytics_assistant.src.infra.config import get_config
from analytics_assistant.src.infra.rag import (
    create_retriever,
    RetrievalConfig,
    MetadataFilter,
)

from ..schemas import FieldCandidate

logger = logging.getLogger(__name__)

class RAGMixin:
    """RAG 检索相关方法 Mixin"""

    def load_metadata(
        self,
        fields: list[Any],
        datasource_luid: str,
    ) -> int:
        """加载元数据并构建索引

        Args:
            fields: 字段元数据列表
            datasource_luid: 数据源标识

        Returns:
            索引的字段数量
        """
        self._field_chunks = fields

        try:
            config = get_config()
            rag_config = config.get("rag", {}).get("retrieval", {})

            retrieval_config = RetrievalConfig(
                top_k=rag_config.get("top_k", self.config.top_k_candidates),
                score_threshold=rag_config.get("score_threshold", 0.7),
            )

            self._retriever = create_retriever(
                fields=fields,
                retriever_type="cascade",
                config=retrieval_config,
                collection_name=f"field_mapper_{datasource_luid}",
            )
            logger.info(f"已创建级联检索器 (datasource={datasource_luid})")

        except Exception as e:
            logger.warning(f"创建检索器失败，将使用 LLM only 模式: {e}")

        logger.info(f"已加载 {len(fields)} 个字段到索引 (datasource={datasource_luid})")
        return len(fields)

    async def _retrieve(
        self,
        term: str,
        context: Optional[str] = None,
        role_filter: Optional[str] = None,
    ) -> list[Any]:
        """执行 RAG 检索"""
        if self._retriever is None:
            return []

        filters = MetadataFilter(role=role_filter) if role_filter else None

        if hasattr(self._retriever, 'aretrieve'):
            results = await self._retriever.aretrieve(
                query=term,
                top_k=self.config.top_k_candidates,
                filters=filters,
            )
        elif hasattr(self._retriever, 'retrieve'):
            results = self._retriever.retrieve(
                query=term,
                top_k=self.config.top_k_candidates,
                filters=filters,
            )
        else:
            logger.warning("检索器没有 retrieve 或 aretrieve 方法")
            return []

        return results

    def _convert_to_candidates(self, retrieval_results: list[Any]) -> list[FieldCandidate]:
        """将 RAG 检索结果转换为 FieldCandidate 列表"""
        candidates = []
        for r in retrieval_results[:self.config.top_k_candidates]:
            chunk = getattr(r, 'field_chunk', r)
            candidates.append(FieldCandidate(
                field_name=getattr(chunk, 'field_name', None) or getattr(chunk, 'name', ''),
                field_caption=getattr(chunk, 'field_caption', None) or getattr(chunk, 'fieldCaption', ''),
                role=getattr(chunk, 'role', ''),
                data_type=getattr(chunk, 'data_type', None) or getattr(chunk, 'dataType', ''),
                confidence=getattr(r, 'score', 0.0),
                category=getattr(chunk, 'category', None),
                level=getattr(chunk, 'metadata', {}).get("level") if hasattr(chunk, 'metadata') else None,
                granularity=getattr(chunk, 'metadata', {}).get("granularity") if hasattr(chunk, 'metadata') else None,
                sample_values=getattr(chunk, 'sample_values', None)
            ))
        return candidates
