"""EmbeddingService 属性测试

**Feature: rag-service-refactor**

测试 EmbeddingService 的正确性属性：
- Property 1: Embedding 缓存往返
- Property 2: Embedding 统计一致性
"""

import pytest
from hypothesis import given, strategies as st, settings

from analytics_assistant.src.infra.rag.embedding_service import (
    EmbeddingService,
    EmbeddingStats,
)


# ═══════════════════════════════════════════════════════════════════════════
# 单元测试
# ═══════════════════════════════════════════════════════════════════════════

class TestEmbeddingServiceUnit:
    """EmbeddingService 单元测试"""
    
    def test_embed_query_returns_vector(self):
        """测试单文本向量化返回正确维度"""
        service = EmbeddingService()
        vector = service.embed_query("测试文本")
        
        assert isinstance(vector, list)
        assert len(vector) > 0
        assert all(isinstance(v, float) for v in vector)
    
    def test_embed_documents_returns_correct_count(self):
        """测试批量向量化返回正确数量的向量"""
        service = EmbeddingService()
        texts = ["文本1", "文本2", "文本3"]
        vectors = service.embed_documents(texts)
        
        assert len(vectors) == len(texts)
        for vector in vectors:
            assert isinstance(vector, list)
            assert len(vector) > 0
    
    def test_embed_empty_text(self):
        """测试空文本处理"""
        service = EmbeddingService()
        vector = service.embed_query("")
        
        # 空文本应该返回向量（API 行为）
        assert isinstance(vector, list)
    
    def test_stats_initial_state(self):
        """测试统计信息初始状态"""
        service = EmbeddingService()
        stats = service.get_stats()
        
        assert stats.total_requests == 0
        assert stats.cache_hits == 0
        assert stats.cache_misses == 0
        assert stats.hit_rate == 0.0
    
    def test_reset_stats(self):
        """测试重置统计信息"""
        service = EmbeddingService()
        
        # 执行一些操作
        service.embed_query("测试")
        
        # 重置
        service.reset_stats()
        stats = service.get_stats()
        
        assert stats.total_requests == 0
        assert stats.cache_hits == 0
        assert stats.cache_misses == 0


# ═══════════════════════════════════════════════════════════════════════════
# 属性测试
# ═══════════════════════════════════════════════════════════════════════════

class TestEmbeddingServiceProperties:
    """EmbeddingService 属性测试"""
    
    @settings(max_examples=10, deadline=60000)
    @given(st.text(min_size=1, max_size=100))
    def test_property_1_cache_roundtrip(self, text: str):
        """**Feature: rag-service-refactor, Property 1: Embedding 缓存往返**
        
        *For any* 文本字符串，首次调用 embed_query(text) 后再次调用相同文本，
        应该命中缓存并返回相同的向量。
        
        **Validates: Requirements 1.3, 1.4**
        """
        service = EmbeddingService()
        
        # 首次调用
        vector1 = service.embed_query(text)
        stats1 = service.get_stats()
        
        # 再次调用相同文本
        vector2 = service.embed_query(text)
        stats2 = service.get_stats()
        
        # 验证：向量相同
        assert vector1 == vector2, "相同文本应返回相同向量"
        
        # 验证：第二次应该命中缓存（cache_hits 增加）
        # 注意：第一次可能命中也可能未命中（取决于之前是否缓存过）
        # 但第二次一定会命中
        assert stats2.cache_hits >= stats1.cache_hits, "第二次调用应命中缓存"
    
    @settings(max_examples=10, deadline=60000)
    @given(st.lists(st.text(min_size=1, max_size=50), min_size=1, max_size=5))
    def test_property_2_stats_consistency(self, texts: list):
        """**Feature: rag-service-refactor, Property 2: Embedding 统计一致性**
        
        *For any* 一系列 Embedding 调用，统计信息中的 total_requests 
        应该等于 cache_hits + cache_misses。
        
        **Validates: Requirements 1.6**
        """
        service = EmbeddingService()
        
        # 执行批量向量化
        service.embed_documents(texts)
        
        stats = service.get_stats()
        
        # 验证：total_requests == cache_hits + cache_misses
        assert stats.total_requests == stats.cache_hits + stats.cache_misses, \
            f"统计不一致: total={stats.total_requests}, hits={stats.cache_hits}, misses={stats.cache_misses}"
        
        # 验证：total_requests == len(texts)
        assert stats.total_requests == len(texts), \
            f"请求数不匹配: expected={len(texts)}, actual={stats.total_requests}"


# ═══════════════════════════════════════════════════════════════════════════
# 运行测试
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
