# -*- coding: utf-8 -*-
"""
检索器单元测试
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest
from unittest.mock import Mock, MagicMock
from src.infra.rag.retriever import (
    RetrievalConfig,
    MetadataFilter,
    Tokenizer,
    EmbeddingRetriever,
    KeywordRetriever,
    HybridRetriever,
    RetrievalPipeline,
    RetrieverFactory,
)
from src.infra.rag.vector_index_manager import VectorIndexManager
from src.infra.rag.models import FieldChunk, RetrievalResult, RetrievalSource


class MockEmbeddingProvider:
    """模拟 Embedding 提供者"""
    
    def embed_documents(self, texts):
        """模拟批量向量化"""
        return [[0.1, 0.2, 0.3] for _ in texts]
    
    def embed_query(self, text):
        """模拟查询向量化"""
        return [0.1, 0.2, 0.3]
    
    async def aembed_query(self, text):
        """模拟异步查询向量化"""
        return [0.1, 0.2, 0.3]


class MockFieldMetadata:
    """模拟 FieldMetadata 对象"""
    
    def __init__(self, name, caption, role="measure", data_type="real", category=None):
        self.name = name
        self.fieldCaption = caption
        self.role = role
        self.dataType = data_type
        self.category = category
        self.columnClass = None
        self.formula = None
        self.logicalTableId = None
        self.logicalTableCaption = None
        self.sample_values = []


def create_test_index_manager():
    """创建测试用的索引管理器"""
    embedding_provider = MockEmbeddingProvider()
    manager = VectorIndexManager(embedding_provider=embedding_provider)
    
    fields = [
        MockFieldMetadata("sales_amount", "销售额", "measure", "real", "财务"),
        MockFieldMetadata("province", "省份", "dimension", "string", "地理"),
        MockFieldMetadata("quantity", "数量", "measure", "integer", "销售"),
    ]
    manager.index_fields(fields)
    
    return manager


class TestRetrievalConfig:
    """测试 RetrievalConfig"""
    
    def test_default_config(self):
        """测试默认配置"""
        config = RetrievalConfig()
        
        assert config.top_k == 10
        assert config.score_threshold == 0.0
        assert config.use_reranker is False
    
    def test_custom_config(self):
        """测试自定义配置"""
        config = RetrievalConfig(
            top_k=5,
            score_threshold=0.7,
            use_reranker=True
        )
        
        assert config.top_k == 5
        assert config.score_threshold == 0.7
        assert config.use_reranker is True


class TestMetadataFilter:
    """测试 MetadataFilter"""
    
    def test_filter_by_role(self):
        """测试按角色过滤"""
        filter = MetadataFilter(role="measure")
        
        chunk_measure = FieldChunk(
            field_name="sales",
            field_caption="销售额",
            role="measure",
            data_type="real",
            index_text="销售额"
        )
        
        chunk_dimension = FieldChunk(
            field_name="province",
            field_caption="省份",
            role="dimension",
            data_type="string",
            index_text="省份"
        )
        
        assert filter.matches(chunk_measure) is True
        assert filter.matches(chunk_dimension) is False
    
    def test_filter_by_category(self):
        """测试按类别过滤"""
        filter = MetadataFilter(category="财务")
        
        chunk_finance = FieldChunk(
            field_name="sales",
            field_caption="销售额",
            role="measure",
            data_type="real",
            index_text="销售额",
            category="财务"
        )
        
        chunk_geo = FieldChunk(
            field_name="province",
            field_caption="省份",
            role="dimension",
            data_type="string",
            index_text="省份",
            category="地理"
        )
        
        assert filter.matches(chunk_finance) is True
        assert filter.matches(chunk_geo) is False
    
    def test_filter_multiple_conditions(self):
        """测试多条件过滤"""
        filter = MetadataFilter(role="measure", category="财务")
        
        chunk_match = FieldChunk(
            field_name="sales",
            field_caption="销售额",
            role="measure",
            data_type="real",
            index_text="销售额",
            category="财务"
        )
        
        chunk_no_match = FieldChunk(
            field_name="quantity",
            field_caption="数量",
            role="measure",
            data_type="integer",
            index_text="数量",
            category="销售"
        )
        
        assert filter.matches(chunk_match) is True
        assert filter.matches(chunk_no_match) is False


class TestTokenizer:
    """测试 Tokenizer"""
    
    def test_tokenize_chinese(self):
        """测试中文分词"""
        tokens = Tokenizer.tokenize("销售额和数量")
        
        assert len(tokens) > 0
        assert all(isinstance(t, str) for t in tokens)
    
    def test_tokenize_english(self):
        """测试英文分词"""
        tokens = Tokenizer.tokenize("sales amount")
        
        assert "sales" in tokens
        assert "amount" in tokens
    
    def test_tokenize_mixed(self):
        """测试中英文混合分词"""
        tokens = Tokenizer.tokenize("销售额 sales")
        
        assert len(tokens) > 0
    
    def test_tokenize_empty(self):
        """测试空文本分词"""
        tokens = Tokenizer.tokenize("")
        
        assert tokens == []


class TestEmbeddingRetriever:
    """测试 EmbeddingRetriever"""
    
    def test_retrieve(self):
        """测试向量检索"""
        manager = create_test_index_manager()
        retriever = EmbeddingRetriever(manager)
        
        results = retriever.retrieve("销售额", top_k=2)
        
        assert len(results) <= 2
        for result in results:
            assert isinstance(result, RetrievalResult)
            assert result.source == RetrievalSource.EMBEDDING
            assert 0 <= result.score <= 1
    
    def test_retrieve_with_filter(self):
        """测试带过滤器的向量检索"""
        manager = create_test_index_manager()
        retriever = EmbeddingRetriever(manager)
        
        filter = MetadataFilter(role="measure")
        results = retriever.retrieve("销售", top_k=5, filters=filter)
        
        for result in results:
            assert result.field_chunk.role == "measure"
    
    def test_retrieve_empty_query(self):
        """测试空查询"""
        manager = create_test_index_manager()
        retriever = EmbeddingRetriever(manager)
        
        results = retriever.retrieve("", top_k=5)
        
        assert results == []
    
    @pytest.mark.asyncio
    async def test_aretrieve(self):
        """测试异步向量检索"""
        manager = create_test_index_manager()
        retriever = EmbeddingRetriever(manager)
        
        results = await retriever.aretrieve("销售额", top_k=2)
        
        assert len(results) <= 2


class TestKeywordRetriever:
    """测试 KeywordRetriever"""
    
    def test_retrieve(self):
        """测试关键词检索"""
        manager = create_test_index_manager()
        retriever = KeywordRetriever(manager)
        
        results = retriever.retrieve("销售额", top_k=2)
        
        assert len(results) <= 2
        for result in results:
            assert isinstance(result, RetrievalResult)
            assert result.source == RetrievalSource.KEYWORD
            assert 0 <= result.score <= 1
    
    def test_retrieve_with_filter(self):
        """测试带过滤器的关键词检索"""
        manager = create_test_index_manager()
        retriever = KeywordRetriever(manager)
        
        filter = MetadataFilter(role="dimension")
        results = retriever.retrieve("省份", top_k=5, filters=filter)
        
        for result in results:
            assert result.field_chunk.role == "dimension"
    
    def test_rebuild_index(self):
        """测试重建 BM25 索引"""
        manager = create_test_index_manager()
        retriever = KeywordRetriever(manager)
        
        # 重建索引
        retriever.rebuild_index()
        
        # 验证仍可检索
        results = retriever.retrieve("销售额", top_k=2)
        assert len(results) <= 2
    
    @pytest.mark.asyncio
    async def test_aretrieve(self):
        """测试异步关键词检索"""
        manager = create_test_index_manager()
        retriever = KeywordRetriever(manager)
        
        results = await retriever.aretrieve("销售额", top_k=2)
        
        assert len(results) <= 2


class TestHybridRetriever:
    """测试 HybridRetriever"""
    
    def test_retrieve_with_rrf(self):
        """测试 RRF 混合检索"""
        manager = create_test_index_manager()
        embedding_retriever = EmbeddingRetriever(manager)
        keyword_retriever = KeywordRetriever(manager)
        
        hybrid_retriever = HybridRetriever(
            embedding_retriever=embedding_retriever,
            keyword_retriever=keyword_retriever,
            use_rrf=True
        )
        
        results = hybrid_retriever.retrieve("销售额", top_k=2)
        
        assert len(results) <= 2
        for result in results:
            assert isinstance(result, RetrievalResult)
            assert result.source == RetrievalSource.HYBRID
            assert 0 <= result.score <= 1
    
    def test_retrieve_with_weighted_fusion(self):
        """测试加权融合混合检索"""
        manager = create_test_index_manager()
        embedding_retriever = EmbeddingRetriever(manager)
        keyword_retriever = KeywordRetriever(manager)
        
        hybrid_retriever = HybridRetriever(
            embedding_retriever=embedding_retriever,
            keyword_retriever=keyword_retriever,
            use_rrf=False,
            embedding_weight=0.7,
            keyword_weight=0.3
        )
        
        results = hybrid_retriever.retrieve("销售额", top_k=2)
        
        assert len(results) <= 2
        for result in results:
            assert result.source == RetrievalSource.HYBRID
    
    @pytest.mark.asyncio
    async def test_aretrieve(self):
        """测试异步混合检索"""
        manager = create_test_index_manager()
        embedding_retriever = EmbeddingRetriever(manager)
        keyword_retriever = KeywordRetriever(manager)
        
        hybrid_retriever = HybridRetriever(
            embedding_retriever=embedding_retriever,
            keyword_retriever=keyword_retriever
        )
        
        results = await hybrid_retriever.aretrieve("销售额", top_k=2)
        
        assert len(results) <= 2


class TestRetrievalPipeline:
    """测试 RetrievalPipeline"""
    
    def test_search_without_reranker(self):
        """测试无重排序的检索管道"""
        manager = create_test_index_manager()
        retriever = EmbeddingRetriever(manager)
        pipeline = RetrievalPipeline(retriever=retriever)
        
        results = pipeline.search("销售额", top_k=2)
        
        assert len(results) <= 2
    
    def test_search_with_reranker(self):
        """测试带重排序的检索管道"""
        from src.infra.rag.reranker import DefaultReranker
        
        manager = create_test_index_manager()
        retriever = EmbeddingRetriever(manager)
        reranker = DefaultReranker(top_k=2)
        pipeline = RetrievalPipeline(retriever=retriever, reranker=reranker)
        
        results = pipeline.search("销售额", top_k=2, rerank_top_k=5)
        
        assert len(results) <= 2
    
    @pytest.mark.asyncio
    async def test_asearch(self):
        """测试异步检索管道"""
        manager = create_test_index_manager()
        retriever = EmbeddingRetriever(manager)
        pipeline = RetrievalPipeline(retriever=retriever)
        
        results = await pipeline.asearch("销售额", top_k=2)
        
        assert len(results) <= 2
    
    def test_batch_search(self):
        """测试批量检索"""
        manager = create_test_index_manager()
        retriever = EmbeddingRetriever(manager)
        pipeline = RetrievalPipeline(retriever=retriever)
        
        queries = ["销售额", "省份"]
        results = pipeline.batch_search(queries, top_k=2)
        
        assert len(results) == 2
        assert "销售额" in results
        assert "省份" in results


class TestRetrieverFactory:
    """测试 RetrieverFactory"""
    
    def test_create_embedding_retriever(self):
        """测试创建向量检索器"""
        manager = create_test_index_manager()
        retriever = RetrieverFactory.create_embedding_retriever(manager)
        
        assert isinstance(retriever, EmbeddingRetriever)
    
    def test_create_keyword_retriever(self):
        """测试创建关键词检索器"""
        manager = create_test_index_manager()
        retriever = RetrieverFactory.create_keyword_retriever(manager)
        
        assert isinstance(retriever, KeywordRetriever)
    
    def test_create_hybrid_retriever(self):
        """测试创建混合检索器"""
        manager = create_test_index_manager()
        retriever = RetrieverFactory.create_hybrid_retriever(manager)
        
        assert isinstance(retriever, HybridRetriever)
    
    def test_create_pipeline_embedding(self):
        """测试创建向量检索管道"""
        manager = create_test_index_manager()
        pipeline = RetrieverFactory.create_pipeline(
            manager,
            retriever_type="embedding",
            reranker_type=None
        )
        
        assert isinstance(pipeline, RetrievalPipeline)
        assert isinstance(pipeline.retriever, EmbeddingRetriever)
    
    def test_create_pipeline_keyword(self):
        """测试创建关键词检索管道"""
        manager = create_test_index_manager()
        pipeline = RetrieverFactory.create_pipeline(
            manager,
            retriever_type="keyword",
            reranker_type=None
        )
        
        assert isinstance(pipeline, RetrievalPipeline)
        assert isinstance(pipeline.retriever, KeywordRetriever)
    
    def test_create_pipeline_hybrid(self):
        """测试创建混合检索管道"""
        manager = create_test_index_manager()
        pipeline = RetrieverFactory.create_pipeline(
            manager,
            retriever_type="hybrid",
            reranker_type=None
        )
        
        assert isinstance(pipeline, RetrievalPipeline)
        assert isinstance(pipeline.retriever, HybridRetriever)
    
    def test_create_pipeline_with_reranker(self):
        """测试创建带重排序的检索管道"""
        manager = create_test_index_manager()
        pipeline = RetrieverFactory.create_pipeline(
            manager,
            retriever_type="hybrid",
            reranker_type="default"
        )
        
        assert isinstance(pipeline, RetrievalPipeline)
        assert pipeline.reranker is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
