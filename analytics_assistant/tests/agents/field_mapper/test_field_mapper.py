# -*- coding: utf-8 -*-
"""
FieldMapper 核心逻辑单元测试

测试字段映射核心逻辑：
- 缓存命中路径
- RAG 高置信度快速路径
- LLM fallback 路径
- 空术语处理
- RAG 不可用时的降级

Mock LLM 调用，验证各路径的正确性。
"""

import pytest
from dataclasses import dataclass, field as dataclass_field
from typing import Optional, Any
from unittest.mock import AsyncMock, MagicMock, patch

from analytics_assistant.src.agents.field_mapper.schemas.config import FieldMappingConfig
from analytics_assistant.src.agents.field_mapper.schemas.mapping import FieldMapping
from analytics_assistant.src.agents.field_mapper.node import FieldMapperNode
from analytics_assistant.src.infra.rag.models import FieldChunk, RetrievalResult, RetrievalSource


# ---- 辅助工具 ----

def _make_chunk(name: str, caption: str, role: str = "dimension") -> FieldChunk:
    """创建测试用 FieldChunk。"""
    return FieldChunk(
        field_name=name,
        field_caption=caption,
        role=role,
        data_type="string",
        index_text=f"{caption} | {name} | {role}",
    )


def _make_retrieval_result(
    chunk: FieldChunk, score: float, rank: int = 1
) -> RetrievalResult:
    """创建测试用 RetrievalResult。"""
    return RetrievalResult(
        field_chunk=chunk,
        score=score,
        source=RetrievalSource.EXACT if score >= 1.0 else RetrievalSource.EMBEDDING,
        rank=rank,
    )


def _make_mapper(
    field_chunks: Optional[list] = None,
    retriever: Optional[Any] = None,
    enable_cache: bool = False,
    enable_llm_fallback: bool = True,
) -> FieldMapperNode:
    """创建测试用 FieldMapperNode（Mock 配置加载）。"""
    config = FieldMappingConfig(
        enable_cache=enable_cache,
        enable_llm_fallback=enable_llm_fallback,
        high_confidence_threshold=0.95,
        max_concurrency=2,
    )
    return FieldMapperNode(
        config=config,
        retriever=retriever,
        field_chunks=field_chunks or [],
    )


DATASOURCE_LUID = "test-datasource-001"


class TestEmptyTermHandling:
    """空术语处理测试。"""

    @pytest.mark.asyncio
    async def test_empty_string_returns_error(self):
        """空字符串返回 error 映射。"""
        mapper = _make_mapper()
        result = await mapper.map_field("", DATASOURCE_LUID)
        assert result.mapping_source == "error"
        assert result.confidence == 0.0
        assert result.technical_field is None

    @pytest.mark.asyncio
    async def test_whitespace_only_returns_error(self):
        """纯空白字符串返回 error 映射。"""
        mapper = _make_mapper()
        result = await mapper.map_field("   ", DATASOURCE_LUID)
        assert result.mapping_source == "error"
        assert result.confidence == 0.0


class TestRAGDirectPath:
    """RAG 高置信度快速路径测试。"""

    @pytest.mark.asyncio
    async def test_high_confidence_rag_returns_direct(self):
        """RAG 高置信度（>=0.95）直接返回，不调用 LLM。"""
        chunk = _make_chunk("Sales", "销售额", "measure")
        retrieval_result = _make_retrieval_result(chunk, score=1.0)

        mock_retriever = MagicMock()
        mock_retriever.aretrieve = AsyncMock(return_value=[retrieval_result])

        mapper = _make_mapper(
            field_chunks=[chunk],
            retriever=mock_retriever,
        )

        result = await mapper.map_field("销售额", DATASOURCE_LUID)
        assert result.mapping_source == "rag_direct"
        assert result.technical_field == "Sales"
        assert result.confidence == 1.0


class TestRAGNotAvailable:
    """RAG 不可用时的降级测试。"""

    @pytest.mark.asyncio
    async def test_no_retriever_falls_back_to_llm_only(self):
        """无 retriever 时使用 LLM only 路径。"""
        chunk = _make_chunk("Sales", "销售额", "measure")

        mapper = _make_mapper(field_chunks=[chunk])

        # Mock LLM 调用
        with patch.object(
            mapper,
            "_llm_select_from_candidates",
            new_callable=AsyncMock,
            return_value=FieldMapping(
                business_term="销售额",
                technical_field="Sales",
                confidence=0.85,
                mapping_source="llm_only",
            ),
        ):
            result = await mapper.map_field("销售额", DATASOURCE_LUID)
            assert result.mapping_source == "llm_only"
            assert result.technical_field == "Sales"

    @pytest.mark.asyncio
    async def test_no_field_chunks_returns_no_metadata(self):
        """无字段元数据时返回空结果。"""
        mapper = _make_mapper(field_chunks=[])
        result = await mapper.map_field("销售额", DATASOURCE_LUID)
        assert result.mapping_source == "llm_only"
        assert result.technical_field is None
        assert "没有可用的字段元数据" in (result.reasoning or "")


class TestLLMFallbackPath:
    """LLM fallback 路径测试。"""

    @pytest.mark.asyncio
    async def test_low_confidence_rag_triggers_llm_fallback(self):
        """RAG 低置信度触发 LLM fallback。"""
        chunk = _make_chunk("Revenue", "收入", "measure")
        retrieval_result = _make_retrieval_result(chunk, score=0.6)

        mock_retriever = MagicMock()
        mock_retriever.aretrieve = AsyncMock(return_value=[retrieval_result])

        mapper = _make_mapper(
            field_chunks=[chunk],
            retriever=mock_retriever,
            enable_llm_fallback=True,
        )

        with patch.object(
            mapper,
            "_llm_select_from_candidates",
            new_callable=AsyncMock,
            return_value=FieldMapping(
                business_term="收入",
                technical_field="Revenue",
                confidence=0.9,
                mapping_source="rag_llm_fallback",
            ),
        ):
            result = await mapper.map_field("收入", DATASOURCE_LUID)
            assert result.mapping_source == "rag_llm_fallback"
            assert result.technical_field == "Revenue"
            assert result.confidence == 0.9

    @pytest.mark.asyncio
    async def test_llm_fallback_disabled_uses_rag_result(self):
        """LLM fallback 禁用时使用 RAG 结果。"""
        chunk = _make_chunk("Revenue", "收入", "measure")
        retrieval_result = _make_retrieval_result(chunk, score=0.6)

        mock_retriever = MagicMock()
        mock_retriever.aretrieve = AsyncMock(return_value=[retrieval_result])

        mapper = _make_mapper(
            field_chunks=[chunk],
            retriever=mock_retriever,
            enable_llm_fallback=False,
        )

        result = await mapper.map_field("收入", DATASOURCE_LUID)
        assert result.mapping_source == "rag_direct"
        assert result.technical_field == "Revenue"
        assert result.confidence == 0.6


class TestCacheHitPath:
    """缓存命中路径测试。"""

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_result(self):
        """缓存命中时直接返回缓存结果。"""
        mapper = _make_mapper(enable_cache=True)

        # Mock 缓存返回
        with patch.object(
            mapper,
            "_get_from_cache",
            return_value={
                "technical_field": "Sales",
                "confidence": 0.95,
                "category": "financial",
            },
        ):
            result = await mapper.map_field("销售额", DATASOURCE_LUID)
            assert result.mapping_source == "cache_hit"
            assert result.technical_field == "Sales"
            assert result.confidence == 0.95


class TestBatchMapping:
    """批量映射测试。"""

    @pytest.mark.asyncio
    async def test_batch_mapping_returns_all_terms(self):
        """批量映射返回所有术语的结果。"""
        chunks = [
            _make_chunk("Sales", "销售额", "measure"),
            _make_chunk("Region", "地区", "dimension"),
        ]

        mock_retriever = MagicMock()
        mock_retriever.aretrieve = AsyncMock(
            side_effect=lambda query, **kwargs: [
                _make_retrieval_result(
                    chunks[0] if "销售" in query else chunks[1],
                    score=1.0,
                )
            ]
        )

        mapper = _make_mapper(
            field_chunks=chunks,
            retriever=mock_retriever,
        )

        results = await mapper.map_fields_batch(
            terms=["销售额", "地区"],
            datasource_luid=DATASOURCE_LUID,
        )

        assert len(results) == 2
        assert "销售额" in results
        assert "地区" in results

    @pytest.mark.asyncio
    async def test_batch_empty_terms_returns_empty(self):
        """空术语列表返回空字典。"""
        mapper = _make_mapper()
        results = await mapper.map_fields_batch([], DATASOURCE_LUID)
        assert results == {}


class TestStats:
    """统计信息测试。"""

    def test_initial_stats_are_zero(self):
        """初始统计信息为零。"""
        mapper = _make_mapper()
        stats = mapper.get_stats()
        assert stats["total_mappings"] == 0
        assert stats["cache_hits"] == 0
        assert stats["fast_path_hits"] == 0
