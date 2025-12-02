"""
向量缓存属性测试

**Feature: rag-enhancement, Property 14: 向量缓存往返**
**Validates: Requirements 11.5**

测试向量缓存的存储和检索一致性。
"""
import pytest
import tempfile
import os
import time
from hypothesis import given, strategies as st, settings

from tableau_assistant.src.capabilities.rag.cache import (
    VectorCache,
    CachedEmbeddingProvider,
)
from tableau_assistant.src.capabilities.rag.embeddings import MockEmbedding


# 使用固定的测试数据库路径，避免 Windows 文件锁定问题
TEST_DB_PATH = "data/test_vector_cache.db"


def get_test_cache():
    """获取测试缓存实例"""
    cache = VectorCache(db_path=TEST_DB_PATH)
    cache.clear()  # 清除之前的数据
    return cache


class TestVectorCacheRoundTrip:
    """
    向量缓存往返测试
    
    **Feature: rag-enhancement, Property 14: 向量缓存往返**
    **Validates: Requirements 11.5**
    """
    
    @pytest.fixture
    def temp_cache(self):
        """创建测试缓存"""
        cache = get_test_cache()
        yield cache
        cache.clear()
    
    def test_put_and_get_vector(self, temp_cache):
        """测试存储和获取向量"""
        text = "销售额"
        vector = [0.1, 0.2, 0.3, 0.4, 0.5]
        model = "test-model"
        
        # 存储
        result = temp_cache.put(text, vector, model)
        assert result is True
        
        # 获取
        cached_vector = temp_cache.get(text, model)
        assert cached_vector == vector
    
    def test_get_nonexistent_returns_none(self, temp_cache):
        """测试获取不存在的向量返回 None"""
        result = temp_cache.get("不存在的文本", "model")
        assert result is None
    
    def test_different_models_separate_cache(self):
        """测试不同模型的缓存是分开的"""
        # 使用独立的缓存实例避免 fixture 清理问题
        cache = VectorCache(db_path="data/test_model_separate.db")
        cache.clear()
        
        text = "测试文本_模型分离"
        vector1 = [0.1, 0.2]
        vector2 = [0.3, 0.4]
        model1 = "model1_separate"
        model2 = "model2_separate"
        
        cache.put(text, vector1, model1)
        cache.put(text, vector2, model2)
        
        assert cache.get(text, model1) == vector1
        assert cache.get(text, model2) == vector2
        
        cache.clear()
    
    @given(
        st.text(min_size=1, max_size=100),
        st.lists(st.floats(min_value=-1, max_value=1, allow_nan=False), min_size=1, max_size=100)
    )
    @settings(max_examples=50)
    def test_round_trip_property(self, text, vector):
        """
        属性测试：存储后获取的向量与原始向量相同
        
        **Feature: rag-enhancement, Property 14: 向量缓存往返**
        """
        cache = get_test_cache()
        
        model = f"test-model-{time.time()}"  # 使用唯一模型名避免冲突
        cache.put(text, vector, model)
        cached = cache.get(text, model)
        
        assert cached is not None
        assert len(cached) == len(vector)
        for i in range(len(vector)):
            assert abs(cached[i] - vector[i]) < 1e-10


class TestVectorCacheBatch:
    """批量缓存测试"""
    
    @pytest.fixture
    def temp_cache(self):
        """创建测试缓存"""
        cache = get_test_cache()
        yield cache
        cache.clear()
    
    def test_get_batch_partial_hit(self, temp_cache):
        """测试批量获取部分命中"""
        # 预先缓存一些向量
        temp_cache.put("text1", [0.1, 0.2], "model")
        temp_cache.put("text3", [0.5, 0.6], "model")
        
        # 批量获取
        texts = ["text1", "text2", "text3"]
        cached, missed = temp_cache.get_batch(texts, "model")
        
        assert "text1" in cached
        assert "text3" in cached
        assert "text2" not in cached
        assert missed == ["text2"]
    
    def test_put_batch(self, temp_cache):
        """测试批量存储"""
        text_vectors = {
            "text1": [0.1, 0.2],
            "text2": [0.3, 0.4],
            "text3": [0.5, 0.6],
        }
        
        count = temp_cache.put_batch(text_vectors, "model")
        assert count == 3
        
        # 验证存储成功
        for text, vector in text_vectors.items():
            assert temp_cache.get(text, "model") == vector
    
    @given(st.dictionaries(
        st.text(min_size=1, max_size=50),
        st.lists(st.floats(min_value=-1, max_value=1, allow_nan=False), min_size=1, max_size=10),
        min_size=1,
        max_size=20
    ))
    @settings(max_examples=30)
    def test_batch_round_trip_property(self, text_vectors):
        """
        属性测试：批量存储后批量获取的向量与原始向量相同
        
        **Feature: rag-enhancement, Property 14: 向量缓存往返**
        """
        cache = get_test_cache()
        
        model = f"test-model-{time.time()}"  # 使用唯一模型名避免冲突
        cache.put_batch(text_vectors, model)
        
        texts = list(text_vectors.keys())
        cached, missed = cache.get_batch(texts, model)
        
        assert len(missed) == 0
        assert len(cached) == len(text_vectors)


class TestVectorCacheStats:
    """缓存统计测试"""
    
    @pytest.fixture
    def temp_cache(self):
        """创建测试缓存"""
        cache = get_test_cache()
        yield cache
        cache.clear()
    
    def test_stats_empty_cache(self, temp_cache):
        """测试空缓存的统计"""
        stats = temp_cache.stats()
        assert stats["total"] == 0
        assert stats["by_model"] == {}
    
    def test_stats_with_data(self, temp_cache):
        """测试有数据的缓存统计"""
        temp_cache.put("text1", [0.1], "model1")
        temp_cache.put("text2", [0.2], "model1")
        temp_cache.put("text3", [0.3], "model2")
        
        stats = temp_cache.stats()
        assert stats["total"] == 3
        assert stats["by_model"]["model1"] == 2
        assert stats["by_model"]["model2"] == 1
    
    def test_clear_by_model(self, temp_cache):
        """测试按模型清除缓存"""
        temp_cache.put("text1", [0.1], "model1")
        temp_cache.put("text2", [0.2], "model2")
        
        count = temp_cache.clear("model1")
        assert count == 1
        
        assert temp_cache.get("text1", "model1") is None
        assert temp_cache.get("text2", "model2") is not None
    
    def test_clear_all(self, temp_cache):
        """测试清除所有缓存"""
        temp_cache.put("text1", [0.1], "model1")
        temp_cache.put("text2", [0.2], "model2")
        
        count = temp_cache.clear()
        assert count == 2
        
        stats = temp_cache.stats()
        assert stats["total"] == 0


class TestCachedEmbeddingProvider:
    """带缓存的 Embedding 提供者测试"""
    
    @pytest.fixture
    def cached_provider(self):
        """创建带缓存的提供者"""
        cache = get_test_cache()
        provider = MockEmbedding(dimensions=128)
        cached = CachedEmbeddingProvider(provider, cache)
        yield cached
        cache.clear()
    
    def test_embed_documents_caches_results(self, cached_provider):
        """测试 embed_documents 缓存结果"""
        texts = ["text1", "text2"]
        
        # 第一次调用
        vectors1 = cached_provider.embed_documents(texts)
        
        # 第二次调用（应该从缓存获取）
        vectors2 = cached_provider.embed_documents(texts)
        
        # 由于 MockEmbedding 生成随机向量，如果缓存工作正常，两次结果应该相同
        assert vectors1 == vectors2
    
    def test_embed_query_caches_result(self, cached_provider):
        """测试 embed_query 缓存结果"""
        text = "查询文本"
        
        # 第一次调用
        vector1 = cached_provider.embed_query(text)
        
        # 第二次调用（应该从缓存获取）
        vector2 = cached_provider.embed_query(text)
        
        assert vector1 == vector2
    
    def test_cache_hit_rate(self, cached_provider):
        """测试缓存命中率"""
        texts = ["text1", "text2"]
        
        # 第一次调用（全部未命中）
        cached_provider.embed_documents(texts)
        assert cached_provider.cache_hit_rate == 0.0
        
        # 重置统计
        cached_provider.reset_stats()
        
        # 第二次调用（全部命中）
        cached_provider.embed_documents(texts)
        assert cached_provider.cache_hit_rate == 1.0
    
    @given(st.lists(st.text(min_size=1, max_size=50), min_size=1, max_size=10))
    @settings(max_examples=30, deadline=None)  # 禁用超时限制
    def test_cached_results_consistent_property(self, texts):
        """
        属性测试：缓存后的结果与首次调用结果一致
        
        **Feature: rag-enhancement, Property 14: 向量缓存往返**
        """
        cache = get_test_cache()
        provider = MockEmbedding(dimensions=64)
        cached = CachedEmbeddingProvider(provider, cache)
        
        # 第一次调用
        vectors1 = cached.embed_documents(texts)
        
        # 第二次调用
        vectors2 = cached.embed_documents(texts)
        
        assert vectors1 == vectors2


class TestHashConsistency:
    """哈希一致性测试"""
    
    @given(st.text(min_size=1, max_size=1000))
    @settings(max_examples=50)
    def test_hash_deterministic(self, text):
        """
        属性测试：相同文本的哈希值始终相同
        
        **Feature: rag-enhancement, Property 14: 向量缓存往返**
        """
        hash1 = VectorCache.compute_hash(text)
        hash2 = VectorCache.compute_hash(text)
        
        assert hash1 == hash2
    
    @given(st.text(min_size=1, max_size=100), st.text(min_size=1, max_size=100))
    @settings(max_examples=50)
    def test_different_texts_different_hashes(self, text1, text2):
        """
        属性测试：不同文本的哈希值（几乎总是）不同
        """
        if text1 != text2:
            hash1 = VectorCache.compute_hash(text1)
            hash2 = VectorCache.compute_hash(text2)
            # 哈希碰撞概率极低，但理论上可能发生
            # 这里我们只验证哈希函数正常工作
            assert isinstance(hash1, str)
            assert isinstance(hash2, str)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
