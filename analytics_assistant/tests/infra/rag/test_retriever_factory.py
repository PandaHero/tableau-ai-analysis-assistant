# -*- coding: utf-8 -*-
"""
RetrieverFactory 回退行为测试。

确保 BM25 依赖不可用时仍能正常构建 cascade retriever，
不影响已有向量索引和 metadata 的恢复。
"""

from unittest.mock import MagicMock, patch

from analytics_assistant.src.infra.rag.retriever import CascadeRetriever, RetrieverFactory


class _DummyConfig:
    config = {"vector_storage": {"backend": "faiss", "index_dir": "data/indexes"}}


def test_create_cascade_retriever_degrades_when_bm25_unavailable():
    """BM25 初始化失败时应降级到 exact+embedding，而不是整体失败。"""
    fields = [
        {
            "field_name": "Comp Name",
            "field_caption": "Comp Name",
            "role": "dimension",
            "data_type": "string",
            "index_text": "Comp Name: 表示省份，地理维度粗粒度。别名: 省份, 省。",
            "category": "geography",
        }
    ]

    fake_embeddings = MagicMock()
    fake_vector_store = MagicMock()

    with patch(
        "analytics_assistant.src.infra.rag.retriever.get_config",
        return_value=_DummyConfig(),
    ), patch(
        "analytics_assistant.src.infra.rag.retriever.get_embeddings",
        return_value=fake_embeddings,
    ), patch(
        "analytics_assistant.src.infra.rag.retriever.get_vector_store",
        return_value=fake_vector_store,
    ), patch(
        "analytics_assistant.src.infra.rag.retriever.BM25Retriever",
        side_effect=ImportError("No module named 'rank_bm25'"),
    ):
        retriever = RetrieverFactory.create_cascade_retriever(
            fields=fields,
            collection_name="fields_test_recover",
            include_bm25=True,
        )

    assert isinstance(retriever, CascadeRetriever)
    assert retriever._bm25 is None
    assert retriever._exact is not None
    assert retriever._embedding is not None
