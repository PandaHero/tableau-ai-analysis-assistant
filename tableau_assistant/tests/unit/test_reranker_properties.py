"""
Reranker 属性测试

使用 Hypothesis 进行属性测试，验证 Reranker 的正确性。

**Feature: rag-enhancement, Property 7: Rerank 排序**
**Feature: rag-enhancement, Property 8: RRF 公式正确性**
"""
import pytest
from hypothesis import given, strategies as st, settings, assume
from typing import List

from tableau_assistant.src.capabilities.rag.models import (
    FieldChunk,
    RetrievalResult,
    RetrievalSource,
)
from tableau_assistant.src.capabilities.rag.reranker import (
    DefaultReranker,
    RRFReranker,
    CrossEncoderReranker,
)


# ==================== 测试数据生成策略 ====================

@st.composite
def field_chunk_strategy(draw):
    """生成随机 FieldChunk"""
    field_name = draw(st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=('L', 'N'))))
    field_caption = draw(st.text(min_size=1, max_size=100))
    role = draw(st.sampled_from(["dimension", "measure"]))
    data_type = draw(st.sampled_from(["STRING", "INTEGER", "REAL", "DATE", "DATETIME", "BOOLEAN"]))
    
    return FieldChunk(
        field_name=field_name,
        field_caption=field_caption,
        role=role,
        data_type=data_type,
        index_text=f"{field_caption} | {field_name} | {role} | {data_type}"
    )


@st.composite
def retrieval_result_strategy(draw, field_chunk=None):
    """生成随机 RetrievalResult"""
    if field_chunk is None:
        field_chunk = draw(field_chunk_strategy())
    
    score = draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False))
    source = draw(st.sampled_from([RetrievalSource.EMBEDDING, RetrievalSource.KEYWORD, RetrievalSource.HYBRID]))
    rank = draw(st.integers(min_value=1, max_value=100))
    
    return RetrievalResult(
        field_chunk=field_chunk,
        score=score,
        source=source,
        rank=rank
    )


@st.composite
def retrieval_results_strategy(draw, min_size=1, max_size=20):
    """生成随机 RetrievalResult 列表（确保字段名唯一）"""
    size = draw(st.integers(min_value=min_size, max_value=max_size))
    results = []
    used_names = set()
    
    for i in range(size):
        # 生成唯一的字段名
        field_name = f"field_{i}_{draw(st.text(min_size=1, max_size=10, alphabet='abcdefghijklmnopqrstuvwxyz'))}"
        while field_name in used_names:
            field_name = f"field_{i}_{draw(st.text(min_size=1, max_size=10, alphabet='abcdefghijklmnopqrstuvwxyz'))}"
        used_names.add(field_name)
        
        chunk = FieldChunk(
            field_name=field_name,
            field_caption=f"Caption {i}",
            role=draw(st.sampled_from(["dimension", "measure"])),
            data_type=draw(st.sampled_from(["STRING", "INTEGER", "REAL"])),
            index_text=f"Caption {i} | {field_name}"
        )
        
        score = draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False))
        source = draw(st.sampled_from([RetrievalSource.EMBEDDING, RetrievalSource.KEYWORD, RetrievalSource.HYBRID]))
        
        results.append(RetrievalResult(
            field_chunk=chunk,
            score=score,
            source=source,
            rank=i + 1
        ))
    
    return results


# ==================== Property 7: Rerank 排序 ====================

class TestRerankSorting:
    """
    **Feature: rag-enhancement, Property 7: Rerank 排序**
    **Validates: Requirements 4.5**
    
    *For any* 重排序后的结果列表，应按分数降序排列。
    """
    
    @given(candidates=retrieval_results_strategy(min_size=2, max_size=15))
    @settings(max_examples=100)
    def test_default_reranker_sorted_by_score(self, candidates: List[RetrievalResult]):
        """DefaultReranker 结果应按分数降序排列"""
        reranker = DefaultReranker(top_k=len(candidates))
        results = reranker.rerank("test query", candidates)
        
        # 验证结果按分数降序排列
        for i in range(len(results) - 1):
            assert results[i].score >= results[i + 1].score, \
                f"结果未按分数降序排列: {results[i].score} < {results[i + 1].score}"
    
    @given(candidates=retrieval_results_strategy(min_size=2, max_size=15))
    @settings(max_examples=100)
    def test_rrf_reranker_sorted_by_score(self, candidates: List[RetrievalResult]):
        """RRFReranker 结果应按分数降序排列"""
        reranker = RRFReranker(top_k=len(candidates))
        results = reranker.rerank("test query", candidates)
        
        # 验证结果按分数降序排列
        for i in range(len(results) - 1):
            assert results[i].score >= results[i + 1].score, \
                f"结果未按分数降序排列: {results[i].score} < {results[i + 1].score}"
    
    @given(candidates=retrieval_results_strategy(min_size=2, max_size=15))
    @settings(max_examples=100)
    def test_rerank_updates_ranks(self, candidates: List[RetrievalResult]):
        """重排序后排名应从 1 开始连续递增"""
        reranker = DefaultReranker(top_k=len(candidates))
        results = reranker.rerank("test query", candidates)
        
        # 验证排名从 1 开始连续递增
        for i, result in enumerate(results):
            assert result.rank == i + 1, \
                f"排名不正确: 期望 {i + 1}, 实际 {result.rank}"


# ==================== Property 8: RRF 公式正确性 ====================

class TestRRFFormula:
    """
    **Feature: rag-enhancement, Property 8: RRF 公式正确性**
    **Validates: Requirements 4.4**
    
    *For any* 多源检索结果，RRF 融合分数应等于 Σ(1/(k+rank))。
    """
    
    @given(
        candidates=retrieval_results_strategy(min_size=2, max_size=10),
        k=st.integers(min_value=1, max_value=100)
    )
    @settings(max_examples=100)
    def test_rrf_formula_correctness(self, candidates: List[RetrievalResult], k: int):
        """验证 RRF 公式: score = Σ(1/(k+rank))"""
        reranker = RRFReranker(top_k=len(candidates), k=k)
        
        # 先按分数排序（模拟检索结果）
        sorted_candidates = sorted(candidates, key=lambda x: x.score, reverse=True)
        
        # 手动计算 RRF 分数
        expected_scores = {}
        for rank, candidate in enumerate(sorted_candidates, 1):
            field_name = candidate.field_chunk.field_name
            rrf_score = 1.0 / (k + rank)
            expected_scores[field_name] = rrf_score
        
        # 归一化
        if expected_scores:
            max_score = max(expected_scores.values())
            if max_score > 0:
                expected_scores = {name: score / max_score for name, score in expected_scores.items()}
        
        # 执行 RRF 重排序
        results = reranker.rerank("test query", candidates)
        
        # 验证分数
        for result in results:
            field_name = result.field_chunk.field_name
            if field_name in expected_scores:
                expected = expected_scores[field_name]
                actual = result.score
                # 允许小的浮点误差
                assert abs(actual - expected) < 1e-6, \
                    f"RRF 分数不正确: 字段 {field_name}, 期望 {expected}, 实际 {actual}"
    
    @given(k=st.integers(min_value=1, max_value=100))
    @settings(max_examples=50)
    def test_rrf_score_decreases_with_rank(self, k: int):
        """验证 RRF 分数随排名递减"""
        # 创建固定的候选列表
        candidates = []
        for i in range(5):
            chunk = FieldChunk(
                field_name=f"field_{i}",
                field_caption=f"Caption {i}",
                role="dimension",
                data_type="STRING",
                index_text=f"Caption {i}"
            )
            candidates.append(RetrievalResult(
                field_chunk=chunk,
                score=1.0 - i * 0.1,  # 分数递减
                source=RetrievalSource.EMBEDDING,
                rank=i + 1
            ))
        
        reranker = RRFReranker(top_k=5, k=k)
        results = reranker.rerank("test query", candidates)
        
        # 验证分数递减
        for i in range(len(results) - 1):
            assert results[i].score >= results[i + 1].score, \
                f"RRF 分数未递减: {results[i].score} < {results[i + 1].score}"
    
    @given(
        result_list1=retrieval_results_strategy(min_size=2, max_size=5),
        result_list2=retrieval_results_strategy(min_size=2, max_size=5),
        k=st.integers(min_value=1, max_value=100)
    )
    @settings(max_examples=50)
    def test_rrf_multiple_lists_fusion(
        self,
        result_list1: List[RetrievalResult],
        result_list2: List[RetrievalResult],
        k: int
    ):
        """验证多列表 RRF 融合"""
        reranker = RRFReranker(top_k=10, k=k)
        
        # 使用 rerank_multiple 方法
        results = reranker.rerank_multiple("test query", [result_list1, result_list2])
        
        # 验证结果按分数降序排列
        for i in range(len(results) - 1):
            assert results[i].score >= results[i + 1].score, \
                f"融合结果未按分数降序排列"
        
        # 验证分数在 [0, 1] 范围内
        for result in results:
            assert 0 <= result.score <= 1, \
                f"分数超出范围: {result.score}"


# ==================== 其他属性测试 ====================

class TestRerankerProperties:
    """其他 Reranker 属性测试"""
    
    @given(candidates=retrieval_results_strategy(min_size=1, max_size=20))
    @settings(max_examples=100)
    def test_score_in_valid_range(self, candidates: List[RetrievalResult]):
        """重排序后分数应在 [0, 1] 范围内"""
        reranker = DefaultReranker(top_k=len(candidates))
        results = reranker.rerank("test query", candidates)
        
        for result in results:
            assert 0 <= result.score <= 1, \
                f"分数超出范围: {result.score}"
    
    @given(
        candidates=retrieval_results_strategy(min_size=5, max_size=20),
        top_k=st.integers(min_value=1, max_value=10)
    )
    @settings(max_examples=100)
    def test_top_k_limit(self, candidates: List[RetrievalResult], top_k: int):
        """重排序结果数量应不超过 top_k"""
        reranker = DefaultReranker(top_k=top_k)
        results = reranker.rerank("test query", candidates)
        
        assert len(results) <= top_k, \
            f"结果数量超过 top_k: {len(results)} > {top_k}"
    
    @given(candidates=retrieval_results_strategy(min_size=1, max_size=10))
    @settings(max_examples=100)
    def test_no_duplicates(self, candidates: List[RetrievalResult]):
        """重排序结果不应有重复字段"""
        reranker = DefaultReranker(top_k=len(candidates))
        results = reranker.rerank("test query", candidates)
        
        field_names = [r.field_chunk.field_name for r in results]
        assert len(field_names) == len(set(field_names)), \
            f"结果中有重复字段: {field_names}"
    
    def test_empty_candidates(self):
        """空候选列表应返回空结果"""
        reranker = DefaultReranker(top_k=5)
        results = reranker.rerank("test query", [])
        
        assert results == [], "空候选应返回空结果"
    
    def test_single_candidate(self):
        """单个候选应直接返回"""
        chunk = FieldChunk(
            field_name="single_field",
            field_caption="Single Field",
            role="dimension",
            data_type="STRING",
            index_text="Single Field"
        )
        candidate = RetrievalResult(
            field_chunk=chunk,
            score=0.8,
            source=RetrievalSource.EMBEDDING,
            rank=1
        )
        
        reranker = DefaultReranker(top_k=5)
        results = reranker.rerank("test query", [candidate])
        
        assert len(results) == 1
        assert results[0].field_chunk.field_name == "single_field"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
