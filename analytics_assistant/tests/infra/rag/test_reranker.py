# -*- coding: utf-8 -*-
"""
重排序器单元测试
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest
from src.infra.rag.reranker import (
    DefaultReranker,
    RRFReranker,
    LLMReranker,
)
from src.infra.rag.models import FieldChunk, RetrievalResult, RetrievalSource


def create_test_results():
    """创建测试用的检索结果"""
    chunks = [
        FieldChunk(
            field_name="sales_amount",
            field_caption="销售额",
            role="measure",
            data_type="real",
            index_text="销售额 | measure | real"
        ),
        FieldChunk(
            field_name="quantity",
            field_caption="数量",
            role="measure",
            data_type="integer",
            index_text="数量 | measure | integer"
        ),
        FieldChunk(
            field_name="province",
            field_caption="省份",
            role="dimension",
            data_type="string",
            index_text="省份 | dimension | string"
        ),
    ]
    
    results = [
        RetrievalResult(
            field_chunk=chunks[0],
            score=0.9,
            source=RetrievalSource.EMBEDDING,
            rank=1
        ),
        RetrievalResult(
            field_chunk=chunks[1],
            score=0.7,
            source=RetrievalSource.EMBEDDING,
            rank=2
        ),
        RetrievalResult(
            field_chunk=chunks[2],
            score=0.5,
            source=RetrievalSource.EMBEDDING,
            rank=3
        ),
    ]
    
    return results


class TestDefaultReranker:
    """测试 DefaultReranker"""
    
    def test_rerank(self):
        """测试默认重排序"""
        reranker = DefaultReranker(top_k=2)
        results = create_test_results()
        
        reranked = reranker.rerank("销售额", results)
        
        assert len(reranked) == 2
        # 应该按分数降序排序
        assert reranked[0].score >= reranked[1].score
        # 排名应该更新
        assert reranked[0].rank == 1
        assert reranked[1].rank == 2
    
    def test_rerank_with_duplicates(self):
        """测试过滤重复结果"""
        reranker = DefaultReranker(top_k=5)
        results = create_test_results()
        
        # 添加重复结果
        duplicate = RetrievalResult(
            field_chunk=results[0].field_chunk,
            score=0.8,
            source=RetrievalSource.KEYWORD,
            rank=4
        )
        results.append(duplicate)
        
        reranked = reranker.rerank("销售额", results)
        
        # 重复的应该被过滤
        field_names = [r.field_chunk.field_name for r in reranked]
        assert len(field_names) == len(set(field_names))
    
    @pytest.mark.asyncio
    async def test_arerank(self):
        """测试异步重排序"""
        reranker = DefaultReranker(top_k=2)
        results = create_test_results()
        
        reranked = await reranker.arerank("销售额", results)
        
        assert len(reranked) == 2


class TestRRFReranker:
    """测试 RRFReranker"""
    
    def test_rerank(self):
        """测试 RRF 重排序"""
        reranker = RRFReranker(top_k=2, k=60)
        results = create_test_results()
        
        reranked = reranker.rerank("销售额", results)
        
        assert len(reranked) == 2
        # 应该有 rerank_score
        assert all(r.rerank_score is not None for r in reranked)
        # 应该有 original_rank
        assert all(r.original_rank is not None for r in reranked)
    
    def test_rerank_multiple(self):
        """测试融合多个检索结果列表"""
        reranker = RRFReranker(top_k=2, k=60)
        
        # 创建两个结果列表（模拟向量检索和关键词检索）
        results1 = create_test_results()[:2]
        results2 = create_test_results()[1:]
        
        reranked = reranker.rerank_multiple("销售额", [results1, results2])
        
        assert len(reranked) == 2
        # 应该是混合来源
        assert all(r.source == RetrievalSource.HYBRID for r in reranked)
    
    def test_rrf_score_calculation(self):
        """测试 RRF 分数计算"""
        reranker = RRFReranker(top_k=3, k=60)
        results = create_test_results()
        
        reranked = reranker.rerank("销售额", results)
        
        # RRF 分数应该在 0-1 范围
        assert all(0 <= r.score <= 1 for r in reranked)
        # 分数应该降序排列
        for i in range(len(reranked) - 1):
            assert reranked[i].score >= reranked[i + 1].score


class TestLLMReranker:
    """测试 LLMReranker"""
    
    def test_rerank_without_llm(self):
        """测试无 LLM 时的重排序（应回退到默认排序）"""
        reranker = LLMReranker(top_k=2)
        results = create_test_results()
        
        reranked = reranker.rerank("销售额", results)
        
        # 应该回退到默认排序
        assert len(reranked) == 2
    
    def test_rerank_with_llm(self):
        """测试使用 LLM 重排序"""
        # 模拟 LLM 调用函数
        def mock_llm_call(prompt):
            # 返回重排序结果：2,0,1（将 quantity 排第一）
            return "2,0,1"
        
        reranker = LLMReranker(top_k=2, llm_call_fn=mock_llm_call)
        results = create_test_results()
        
        reranked = reranker.rerank("数量", results)
        
        assert len(reranked) == 2
        # 应该根据 LLM 返回的顺序重排
        # 注意：LLM 返回 "2,0,1"，所以第一个应该是 index=2 的结果（province）
        assert reranked[0].field_chunk.field_name == "province"
    
    def test_rerank_with_llm_error(self):
        """测试 LLM 调用失败时的处理"""
        # 模拟 LLM 调用失败
        def mock_llm_call_error(prompt):
            raise Exception("LLM call failed")
        
        reranker = LLMReranker(top_k=2, llm_call_fn=mock_llm_call_error)
        results = create_test_results()
        
        reranked = reranker.rerank("销售额", results)
        
        # 应该回退到默认排序
        assert len(reranked) == 2
    
    def test_rerank_single_result(self):
        """测试单个结果的重排序"""
        reranker = LLMReranker(top_k=2)
        results = create_test_results()[:1]
        
        reranked = reranker.rerank("销售额", results)
        
        # 单个结果直接返回
        assert len(reranked) == 1
    
    def test_build_rerank_prompt(self):
        """测试构建重排序提示"""
        reranker = LLMReranker(top_k=2)
        results = create_test_results()
        
        prompt = reranker._build_rerank_prompt("销售额", results)
        
        # 提示应该包含查询和候选字段
        assert "销售额" in prompt
        assert "销售额" in prompt or "sales_amount" in prompt
        assert "数量" in prompt or "quantity" in prompt
    
    def test_parse_ranking(self):
        """测试解析排序结果"""
        reranker = LLMReranker(top_k=3)
        
        # 测试正常格式
        indices = reranker._parse_ranking("2,0,1", 3)
        assert indices == [2, 0, 1]
        
        # 测试带空格
        indices = reranker._parse_ranking("2, 0, 1", 3)
        assert indices == [2, 0, 1]
        
        # 测试带文本
        indices = reranker._parse_ranking("排序结果: 2,0,1", 3)
        assert indices == [2, 0, 1]
        
        # 测试超出范围的索引
        indices = reranker._parse_ranking("5,0,1", 3)
        assert 5 not in indices
        assert 0 in indices
        assert 1 in indices
    
    def test_rerank_score_recalculation(self):
        """测试重排序后分数重新计算"""
        def mock_llm_call(prompt):
            return "1,0,2"  # 重新排序
        
        reranker = LLMReranker(top_k=3, llm_call_fn=mock_llm_call)
        results = create_test_results()
        
        reranked = reranker.rerank("销售额", results)
        
        # 重排序后，第一名的分数应该最高
        assert reranked[0].score >= reranked[1].score
        assert reranked[1].score >= reranked[2].score
        # 分数应该在合理范围
        assert all(0.5 <= r.score <= 1.0 for r in reranked)


class TestRerankerIntegration:
    """测试重排序器集成"""
    
    def test_reranker_comparison(self):
        """测试不同重排序器的结果对比"""
        results = create_test_results()
        
        # 默认重排序
        default_reranker = DefaultReranker(top_k=2)
        default_results = default_reranker.rerank("销售额", results)
        
        # RRF 重排序
        rrf_reranker = RRFReranker(top_k=2)
        rrf_results = rrf_reranker.rerank("销售额", results)
        
        # 两种方法都应该返回结果
        assert len(default_results) == 2
        assert len(rrf_results) == 2
        
        # 结果可能不同，但都应该有效
        assert all(0 <= r.score <= 1 for r in default_results)
        assert all(0 <= r.score <= 1 for r in rrf_results)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
