# -*- coding: utf-8 -*-
"""
ExactRetriever 精确匹配正确性属性测试（Property 13）

验证精确匹配字段名或 caption 时返回置信度 1.0。
"""

from hypothesis import given, settings, assume, strategies as st

from analytics_assistant.src.infra.rag.models import FieldChunk, RetrievalSource
from analytics_assistant.src.infra.rag.retriever import ExactRetriever


# ---- Hypothesis 策略 ----

_field_name_st = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_",
    min_size=1,
    max_size=30,
)

_caption_st = st.text(min_size=1, max_size=30, alphabet=st.characters(
    categories=("L", "N"),
))

_role_st = st.sampled_from(["dimension", "measure"])
_data_type_st = st.sampled_from(["string", "number", "date", "boolean"])


def _make_chunk(name: str, caption: str, role: str = "dimension", data_type: str = "string") -> FieldChunk:
    """创建 FieldChunk 实例。"""
    return FieldChunk(
        field_name=name,
        field_caption=caption,
        role=role,
        data_type=data_type,
        index_text=f"{caption} | {name} | {role} | {data_type}",
    )


def _make_retriever(chunks: list[FieldChunk]) -> ExactRetriever:
    """从 FieldChunk 列表创建 ExactRetriever。"""
    chunks_dict = {c.field_name: c for c in chunks}
    return ExactRetriever(chunks_dict, case_sensitive=False)


class TestExactRetrieverPBT:
    """Property 13: ExactRetriever 精确匹配正确性

    **Validates: Requirements 21.3**
    """

    @given(
        name=_field_name_st,
        caption=_caption_st,
        role=_role_st,
    )
    @settings(max_examples=100)
    def test_exact_match_by_name_returns_score_1(self, name: str, caption: str, role: str):
        """精确匹配字段名时返回置信度 1.0。"""
        chunk = _make_chunk(name, caption, role)
        retriever = _make_retriever([chunk])

        results = retriever.retrieve(name)
        assert len(results) == 1
        assert results[0].score == 1.0
        assert results[0].source == RetrievalSource.EXACT
        assert results[0].field_chunk.field_name == name

    @given(
        name=_field_name_st,
        caption=_caption_st,
        role=_role_st,
    )
    @settings(max_examples=100)
    def test_exact_match_by_caption_returns_score_1(self, name: str, caption: str, role: str):
        """精确匹配 caption 时返回置信度 1.0。"""
        # 确保 caption 和 name 不同，以测试 caption 匹配路径
        assume(caption.lower() != name.lower())

        chunk = _make_chunk(name, caption, role)
        retriever = _make_retriever([chunk])

        results = retriever.retrieve(caption)
        assert len(results) == 1
        assert results[0].score == 1.0
        assert results[0].source == RetrievalSource.EXACT
        assert results[0].field_chunk.field_caption == caption

    @given(
        name=_field_name_st,
        caption=_caption_st,
    )
    @settings(max_examples=50)
    def test_case_insensitive_match(self, name: str, caption: str):
        """大小写不敏感匹配。"""
        chunk = _make_chunk(name, caption)
        retriever = _make_retriever([chunk])

        # 用大写查询
        results_upper = retriever.retrieve(name.upper())
        assert len(results_upper) == 1
        assert results_upper[0].score == 1.0

        # 用小写查询
        results_lower = retriever.retrieve(name.lower())
        assert len(results_lower) == 1
        assert results_lower[0].score == 1.0

    @given(query=_field_name_st)
    @settings(max_examples=50)
    def test_no_match_returns_empty(self, query: str):
        """不匹配时返回空列表。"""
        # 创建一个与 query 不同的字段
        other_name = query + "_other"
        other_caption = query + "_caption_other"
        chunk = _make_chunk(other_name, other_caption)
        retriever = _make_retriever([chunk])

        results = retriever.retrieve(query)
        assert len(results) == 0

    def test_empty_query_returns_empty(self):
        """空查询返回空列表。"""
        chunk = _make_chunk("Sales", "销售额")
        retriever = _make_retriever([chunk])
        assert retriever.retrieve("") == []

    @given(
        names=st.lists(
            _field_name_st, min_size=2, max_size=10, unique_by=str.lower
        ),
    )
    @settings(max_examples=30)
    def test_multiple_fields_exact_match_correct_one(self, names: list[str]):
        """多字段时精确匹配返回正确的字段。"""
        chunks = [_make_chunk(n, f"caption_{i}") for i, n in enumerate(names)]
        retriever = _make_retriever(chunks)

        # 查询第一个字段名
        target = names[0]
        results = retriever.retrieve(target)
        assert len(results) == 1
        assert results[0].field_chunk.field_name == target
