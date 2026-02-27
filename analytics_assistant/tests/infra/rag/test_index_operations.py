# -*- coding: utf-8 -*-
"""
索引操作一致性属性测试

Property 6: 索引操作后检索一致性

验证删除的文档不出现在检索结果中，更新的文档返回最新版本。

验证: 需求 6.2, 6.3
"""

import hashlib
from typing import Optional

from hypothesis import given, settings, strategies as st
from langchain_community.vectorstores import FAISS
from langchain_core.embeddings import Embeddings


# ---------------------------------------------------------------------------
# 确定性 Fake Embedding（用于测试，不依赖外部服务）
# ---------------------------------------------------------------------------


class _DeterministicEmbeddings(Embeddings):
    """基于文本哈希的确定性 Embedding，用于测试。"""

    _DIM = 32

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._hash_to_vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._hash_to_vector(text)

    def _hash_to_vector(self, text: str) -> list[float]:
        """将文本哈希为固定维度的浮点向量。"""
        digest = hashlib.sha256(text.encode()).digest()
        # 取前 _DIM 个字节，归一化到 [-1, 1]
        return [(b / 127.5 - 1.0) for b in digest[: self._DIM]]


# ---------------------------------------------------------------------------
# Hypothesis 策略
# ---------------------------------------------------------------------------

# 文档 ID 策略（简短 ASCII 字符串）
_doc_id_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), max_codepoint=127),
    min_size=1,
    max_size=20,
)

# 文档内容策略
_content_strategy = st.text(min_size=1, max_size=100)


def _create_faiss_store(
    docs: dict[str, str],
    embeddings: Optional[_DeterministicEmbeddings] = None,
) -> FAISS:
    """创建包含指定文档的 FAISS 向量存储。

    Args:
        docs: {field_name: content} 映射
        embeddings: Embedding 实例

    Returns:
        FAISS 向量存储实例
    """
    if embeddings is None:
        embeddings = _DeterministicEmbeddings()

    texts = list(docs.values())
    metadatas = [{"field_name": fid} for fid in docs]
    return FAISS.from_texts(texts, embeddings, metadatas=metadatas)


def _search_field_names(store: FAISS, query: str, k: int = 100) -> set[str]:
    """检索并返回结果中的 field_name 集合。"""
    embeddings = _DeterministicEmbeddings()
    results = store.similarity_search(query, k=k)
    return {doc.metadata.get("field_name") for doc in results}


def _delete_by_field_names(store: FAISS, field_names: set[str]) -> None:
    """从 FAISS 中删除指定 field_name 的向量。"""
    ids_to_delete = []
    if hasattr(store, 'index_to_docstore_id'):
        for idx, docstore_id in store.index_to_docstore_id.items():
            doc = store.docstore.search(docstore_id)
            if doc and hasattr(doc, 'metadata'):
                if doc.metadata.get("field_name") in field_names:
                    ids_to_delete.append(docstore_id)
    if ids_to_delete:
        store.delete(ids_to_delete)


# ---------------------------------------------------------------------------
# Property 6: 索引操作后检索一致性
# ---------------------------------------------------------------------------


class TestIndexOperationConsistencyPBT:
    """Property 6: 索引操作后检索一致性

    **Validates: Requirements 6.2, 6.3**

    *For any* 文档集合和索引操作序列（添加、删除、更新），
    执行操作后的检索结果应仅包含当前有效的文档版本。
    """

    @given(
        doc_ids=st.lists(
            _doc_id_strategy,
            min_size=2,
            max_size=8,
            unique=True,
        ),
        data=st.data(),
    )
    @settings(max_examples=50, deadline=10000)
    def test_deleted_documents_not_in_search_results(self, doc_ids, data):
        """删除的文档不应出现在检索结果中。"""
        # 为每个 doc_id 生成唯一内容
        docs = {did: f"内容_{did}_{i}" for i, did in enumerate(doc_ids)}
        store = _create_faiss_store(docs)

        # 随机选择要删除的文档子集（至少 1 个，不全删）
        to_delete = data.draw(
            st.lists(
                st.sampled_from(doc_ids),
                min_size=1,
                max_size=max(1, len(doc_ids) - 1),
                unique=True,
            )
        )
        remaining = set(doc_ids) - set(to_delete)

        # 执行删除
        _delete_by_field_names(store, set(to_delete))

        # 用任意查询检索，验证删除的文档不在结果中
        for did in to_delete:
            results = _search_field_names(store, docs[did])
            assert did not in results, (
                f"已删除的文档 '{did}' 仍出现在检索结果中"
            )

    @given(
        doc_ids=st.lists(
            _doc_id_strategy,
            min_size=2,
            max_size=8,
            unique=True,
        ),
        data=st.data(),
    )
    @settings(max_examples=50, deadline=10000)
    def test_remaining_documents_still_retrievable(self, doc_ids, data):
        """删除部分文档后，剩余文档仍可检索。"""
        docs = {did: f"内容_{did}_{i}" for i, did in enumerate(doc_ids)}
        store = _create_faiss_store(docs)

        # 随机选择要删除的文档（不全删）
        to_delete = data.draw(
            st.lists(
                st.sampled_from(doc_ids),
                min_size=1,
                max_size=max(1, len(doc_ids) - 1),
                unique=True,
            )
        )
        remaining = set(doc_ids) - set(to_delete)

        _delete_by_field_names(store, set(to_delete))

        # 验证剩余文档仍可检索
        all_results = _search_field_names(store, "内容", k=100)
        for did in remaining:
            assert did in all_results, (
                f"未删除的文档 '{did}' 在检索结果中丢失"
            )

    @given(
        doc_ids=st.lists(
            _doc_id_strategy,
            min_size=1,
            max_size=6,
            unique=True,
        ),
        data=st.data(),
    )
    @settings(max_examples=50, deadline=10000)
    def test_updated_document_returns_new_content(self, doc_ids, data):
        """更新文档后，检索应返回新版本内容。"""
        embeddings = _DeterministicEmbeddings()
        docs = {did: f"旧内容_{did}" for did in doc_ids}
        store = _create_faiss_store(docs, embeddings)

        # 随机选择要更新的文档
        to_update = data.draw(
            st.lists(
                st.sampled_from(doc_ids),
                min_size=1,
                max_size=len(doc_ids),
                unique=True,
            )
        )

        # 先删除旧向量，再添加新向量（模拟更新操作）
        _delete_by_field_names(store, set(to_update))

        new_texts = []
        new_metadatas = []
        for did in to_update:
            new_content = f"新内容_{did}_已更新"
            docs[did] = new_content
            new_texts.append(new_content)
            new_metadatas.append({"field_name": did})

        store.add_texts(new_texts, metadatas=new_metadatas)

        # 验证更新后的文档返回新内容
        for did in to_update:
            results = store.similarity_search(docs[did], k=5)
            found_contents = [r.page_content for r in results]
            assert any("新内容" in c and "已更新" in c for c in found_contents), (
                f"更新后的文档 '{did}' 未返回新内容，"
                f"实际结果: {found_contents[:3]}"
            )
