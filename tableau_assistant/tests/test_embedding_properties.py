"""
Embedding 提供者属性测试

**Feature: rag-enhancement, Property 16: 向量化提供者兼容性**
**Validates: Requirements 11.1**

测试所有 Embedding 提供者实现相同的接口并返回一致的结果格式。
"""
import pytest
from hypothesis import given, strategies as st, settings

from tableau_assistant.src.capabilities.rag.embeddings import (
    EmbeddingProvider,
    MockEmbedding,
    EmbeddingProviderFactory,
)
from tableau_assistant.src.capabilities.rag.models import EmbeddingResult


class TestEmbeddingProviderInterface:
    """
    测试 EmbeddingProvider 接口兼容性
    
    **Feature: rag-enhancement, Property 16: 向量化提供者兼容性**
    **Validates: Requirements 11.1**
    """
    
    @pytest.fixture
    def mock_provider(self):
        """创建 Mock 提供者"""
        return MockEmbedding(dimensions=1024)
    
    def test_embed_documents_returns_list(self, mock_provider):
        """测试 embed_documents 返回列表"""
        texts = ["销售额", "利润", "地区"]
        vectors = mock_provider.embed_documents(texts)
        
        assert isinstance(vectors, list)
        assert len(vectors) == len(texts)
    
    def test_embed_query_returns_list(self, mock_provider):
        """测试 embed_query 返回向量"""
        text = "销售金额"
        vector = mock_provider.embed_query(text)
        
        assert isinstance(vector, list)
        assert len(vector) == mock_provider.dimensions
    
    def test_vector_dimensions_consistent(self, mock_provider):
        """测试向量维度一致性"""
        texts = ["字段1", "字段2", "字段3"]
        vectors = mock_provider.embed_documents(texts)
        
        for vector in vectors:
            assert len(vector) == mock_provider.dimensions
    
    @given(st.lists(st.text(min_size=1, max_size=100), min_size=1, max_size=10))
    @settings(max_examples=50)
    def test_embed_documents_length_property(self, texts):
        """
        属性测试：embed_documents 返回的向量数量等于输入文本数量
        
        **Feature: rag-enhancement, Property 16: 向量化提供者兼容性**
        """
        provider = MockEmbedding(dimensions=128)
        vectors = provider.embed_documents(texts)
        
        assert len(vectors) == len(texts)
    
    @given(st.text(min_size=1, max_size=100))
    @settings(max_examples=50)
    def test_embed_query_dimensions_property(self, text):
        """
        属性测试：embed_query 返回的向量维度等于配置的维度
        
        **Feature: rag-enhancement, Property 16: 向量化提供者兼容性**
        """
        dimensions = 256
        provider = MockEmbedding(dimensions=dimensions)
        vector = provider.embed_query(text)
        
        assert len(vector) == dimensions
    
    def test_empty_documents_returns_empty_list(self, mock_provider):
        """测试空文档列表返回空列表"""
        vectors = mock_provider.embed_documents([])
        assert vectors == []


class TestEmbeddingResult:
    """测试 EmbeddingResult 数据模型"""
    
    def test_embedding_result_creation(self):
        """测试 EmbeddingResult 创建"""
        result = EmbeddingResult(
            text="测试文本",
            vector=[0.1, 0.2, 0.3],
            model="test-model",
            dimensions=3
        )
        
        assert result.text == "测试文本"
        assert result.vector == [0.1, 0.2, 0.3]
        assert result.model == "test-model"
        assert result.dimensions == 3
    
    def test_embedding_result_dimension_validation(self):
        """测试 EmbeddingResult 维度验证"""
        with pytest.raises(ValueError, match="向量维度不匹配"):
            EmbeddingResult(
                text="测试",
                vector=[0.1, 0.2],
                model="test",
                dimensions=3  # 不匹配
            )
    
    def test_embed_documents_with_results(self):
        """测试 embed_documents_with_results 方法"""
        provider = MockEmbedding(dimensions=128)
        texts = ["文本1", "文本2"]
        
        results = provider.embed_documents_with_results(texts)
        
        assert len(results) == 2
        for i, result in enumerate(results):
            assert isinstance(result, EmbeddingResult)
            assert result.text == texts[i]
            assert result.model == provider.model_name
            assert result.dimensions == provider.dimensions
    
    def test_embed_query_with_result(self):
        """测试 embed_query_with_result 方法"""
        provider = MockEmbedding(dimensions=128)
        text = "查询文本"
        
        result = provider.embed_query_with_result(text)
        
        assert isinstance(result, EmbeddingResult)
        assert result.text == text
        assert result.model == provider.model_name


class TestEmbeddingProviderFactory:
    """测试 EmbeddingProviderFactory"""
    
    def test_create_mock_provider(self):
        """测试创建 Mock 提供者"""
        provider = EmbeddingProviderFactory.create("mock", dimensions=512)
        
        assert isinstance(provider, MockEmbedding)
        assert provider.dimensions == 512
    
    def test_available_providers(self):
        """测试获取可用提供者列表"""
        providers = EmbeddingProviderFactory.available_providers()
        
        assert "mock" in providers
        assert "zhipu" in providers
    
    def test_unknown_provider_raises_error(self):
        """测试未知提供者抛出错误"""
        with pytest.raises(ValueError, match="未知的 Embedding 提供者"):
            EmbeddingProviderFactory.create("unknown_provider")
    
    def test_register_custom_provider(self):
        """测试注册自定义提供者"""
        class CustomEmbedding(EmbeddingProvider):
            def __init__(self):
                super().__init__("custom", 256)
            
            def embed_documents(self, texts):
                return [[0.0] * 256 for _ in texts]
            
            def embed_query(self, text):
                return [0.0] * 256
        
        EmbeddingProviderFactory.register("custom", CustomEmbedding)
        
        provider = EmbeddingProviderFactory.create("custom")
        assert isinstance(provider, CustomEmbedding)


class TestTextHash:
    """测试文本哈希功能"""
    
    def test_compute_text_hash(self):
        """测试计算文本哈希"""
        hash1 = EmbeddingProvider.compute_text_hash("测试文本")
        hash2 = EmbeddingProvider.compute_text_hash("测试文本")
        hash3 = EmbeddingProvider.compute_text_hash("不同文本")
        
        assert hash1 == hash2  # 相同文本哈希相同
        assert hash1 != hash3  # 不同文本哈希不同
    
    @given(st.text(min_size=1, max_size=1000))
    @settings(max_examples=50)
    def test_hash_deterministic_property(self, text):
        """
        属性测试：相同文本的哈希值始终相同
        
        **Feature: rag-enhancement, Property 16: 向量化提供者兼容性**
        """
        hash1 = EmbeddingProvider.compute_text_hash(text)
        hash2 = EmbeddingProvider.compute_text_hash(text)
        
        assert hash1 == hash2


class TestBatchProcessing:
    """测试批量处理功能"""
    
    def test_batch_texts(self):
        """测试文本分批"""
        provider = MockEmbedding(dimensions=128, batch_size=3)
        texts = ["t1", "t2", "t3", "t4", "t5"]
        
        batches = provider._batch_texts(texts)
        
        assert len(batches) == 2
        assert batches[0] == ["t1", "t2", "t3"]
        assert batches[1] == ["t4", "t5"]
    
    @given(st.lists(st.text(min_size=1, max_size=10), min_size=1, max_size=100))
    @settings(max_examples=30)
    def test_batch_preserves_all_texts(self, texts):
        """
        属性测试：分批后的文本总数等于原始文本数
        
        **Feature: rag-enhancement, Property 16: 向量化提供者兼容性**
        """
        provider = MockEmbedding(dimensions=128, batch_size=10)
        batches = provider._batch_texts(texts)
        
        total_texts = sum(len(batch) for batch in batches)
        assert total_texts == len(texts)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
