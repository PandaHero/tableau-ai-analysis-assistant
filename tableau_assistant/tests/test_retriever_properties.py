"""
检索器属性测试

**Feature: rag-enhancement, Property 5: 分数范围**
**Validates: Requirements 5.3**

**Feature: rag-enhancement, Property 6: 元数据过滤**
**Validates: Requirements 2.4, 5.4**

测试检索器的分数范围和元数据过滤功能。
"""
import pytest
from hypothesis import given, strategies as st, settings
from dataclasses import dataclass
from typing import List, Optional

from tableau_assistant.src.capabilities.rag.retriever import (
    BaseRetriever,
    EmbeddingRetriever,
    KeywordRetriever,
    HybridRetriever,
    RetrieverFactory,
    RetrievalConfig,
    MetadataFilter,
)
from tableau_assistant.src.capabilities.rag.field_indexer import FieldIndexer
from tableau_assistant.src.capabilities.rag.embeddings import MockEmbedding
from tableau_assistant.src.capabilities.rag.models import RetrievalResult, RetrievalSource


@dataclass
class MockFieldMetadata:
    """Mock FieldMetadata for testing"""
    name: str
    fieldCaption: str
    role: str
    dataType: str
    columnClass: Optional[str] = None
    category: Optional[str] = None
    formula: Optional[str] = None
    logicalTableId: Optional[str] = None
    logicalTableCaption: Optional[str] = None
    sample_values: Optional[List[str]] = None


class TestScoreRange:
    """
    分数范围测试
    
    **Feature: rag-enhancement, Property 5: 分数范围**
    **Validates: Requirements 5.3**
    
    验证：*For any* 检索结果，相关性分数应在 [0, 1] 范围内。
    """
    
    @pytest.fixture
    def sample_fields(self):
        """创建测试字段"""
        return [
            MockFieldMetadata(
                name="sales_amount",
                fieldCaption="Sales Amount",
                role="measure",
                dataType="REAL",
                category="财务"
            ),
            MockFieldMetadata(
                name="revenue",
                fieldCaption="Revenue",
                role="measure",
                dataType="REAL",
                category="财务"
            ),
            MockFieldMetadata(
                name="profit",
                fieldCaption="Profit Margin",
                role="measure",
                dataType="REAL",
                category="财务"
            ),
            MockFieldMetadata(
                name="region",
                fieldCaption="Region",
                role="dimension",
                dataType="STRING",
                category="地理"
            ),
            MockFieldMetadata(
                name="customer_name",
                fieldCaption="Customer Name",
                role="dimension",
                dataType="STRING",
                category="客户"
            ),
        ]
    
    @pytest.fixture
    def field_indexer(self, sample_fields):
        """创建字段索引器"""
        provider = MockEmbedding(dimensions=64)
        indexer = FieldIndexer(embedding_provider=provider, use_cache=False)
        indexer.index_fields(sample_fields)
        return indexer
    
    def test_embedding_retriever_score_range(self, field_indexer):
        """测试向量检索器分数范围"""
        retriever = EmbeddingRetriever(field_indexer)
        results = retriever.retrieve("sales amount", top_k=5)
        
        for result in results:
            assert 0 <= result.score <= 1, f"分数 {result.score} 不在 [0, 1] 范围内"
    
    def test_keyword_retriever_score_range(self, field_indexer):
        """测试关键词检索器分数范围"""
        retriever = KeywordRetriever(field_indexer)
        results = retriever.retrieve("sales amount", top_k=5)
        
        for result in results:
            assert 0 <= result.score <= 1, f"分数 {result.score} 不在 [0, 1] 范围内"
    
    def test_hybrid_retriever_score_range(self, field_indexer):
        """测试混合检索器分数范围"""
        retriever = RetrieverFactory.create_hybrid_retriever(field_indexer)
        results = retriever.retrieve("sales amount", top_k=5)
        
        for result in results:
            assert 0 <= result.score <= 1, f"分数 {result.score} 不在 [0, 1] 范围内"
    
    @given(st.text(min_size=1, max_size=50))
    @settings(max_examples=20, deadline=None)
    def test_score_range_property_embedding(self, query):
        """
        属性测试：向量检索分数范围
        
        **Feature: rag-enhancement, Property 5: 分数范围**
        **Validates: Requirements 5.3**
        
        *For any* 查询，向量检索返回的分数应在 [0, 1] 范围内
        """
        fields = [
            MockFieldMetadata(name=f"field_{i}", fieldCaption=f"Field {i}", role="dimension", dataType="STRING")
            for i in range(5)
        ]
        
        provider = MockEmbedding(dimensions=32)
        indexer = FieldIndexer(embedding_provider=provider, use_cache=False)
        indexer.index_fields(fields)
        
        retriever = EmbeddingRetriever(indexer)
        results = retriever.retrieve(query, top_k=5)
        
        for result in results:
            assert 0 <= result.score <= 1, f"查询 '{query}' 的分数 {result.score} 不在 [0, 1] 范围内"
    
    @given(st.text(min_size=1, max_size=50))
    @settings(max_examples=20, deadline=None)
    def test_score_range_property_keyword(self, query):
        """
        属性测试：关键词检索分数范围
        
        **Feature: rag-enhancement, Property 5: 分数范围**
        **Validates: Requirements 5.3**
        
        *For any* 查询，关键词检索返回的分数应在 [0, 1] 范围内
        """
        fields = [
            MockFieldMetadata(name=f"field_{i}", fieldCaption=f"Field {i}", role="dimension", dataType="STRING")
            for i in range(5)
        ]
        
        provider = MockEmbedding(dimensions=32)
        indexer = FieldIndexer(embedding_provider=provider, use_cache=False)
        indexer.index_fields(fields)
        
        retriever = KeywordRetriever(indexer)
        results = retriever.retrieve(query, top_k=5)
        
        for result in results:
            assert 0 <= result.score <= 1, f"查询 '{query}' 的分数 {result.score} 不在 [0, 1] 范围内"
    
    @given(st.text(min_size=1, max_size=50))
    @settings(max_examples=20, deadline=None)
    def test_score_range_property_hybrid(self, query):
        """
        属性测试：混合检索分数范围
        
        **Feature: rag-enhancement, Property 5: 分数范围**
        **Validates: Requirements 5.3**
        
        *For any* 查询，混合检索返回的分数应在 [0, 1] 范围内
        """
        fields = [
            MockFieldMetadata(name=f"field_{i}", fieldCaption=f"Field {i}", role="dimension", dataType="STRING")
            for i in range(5)
        ]
        
        provider = MockEmbedding(dimensions=32)
        indexer = FieldIndexer(embedding_provider=provider, use_cache=False)
        indexer.index_fields(fields)
        
        retriever = RetrieverFactory.create_hybrid_retriever(indexer)
        results = retriever.retrieve(query, top_k=5)
        
        for result in results:
            assert 0 <= result.score <= 1, f"查询 '{query}' 的分数 {result.score} 不在 [0, 1] 范围内"
    
    def test_results_sorted_by_score(self, field_indexer):
        """测试结果按分数降序排列"""
        retriever = EmbeddingRetriever(field_indexer)
        results = retriever.retrieve("sales", top_k=5)
        
        if len(results) > 1:
            for i in range(len(results) - 1):
                assert results[i].score >= results[i + 1].score, "结果应按分数降序排列"



class TestMetadataFilter:
    """
    元数据过滤测试
    
    **Feature: rag-enhancement, Property 6: 元数据过滤**
    **Validates: Requirements 2.4, 5.4**
    
    验证：*For any* 带有 role 过滤器的检索，返回的所有字段应匹配指定的 role。
    """
    
    @pytest.fixture
    def mixed_fields(self):
        """创建混合角色的测试字段"""
        return [
            MockFieldMetadata(name="sales", fieldCaption="Sales Amount", role="measure", dataType="REAL", category="财务"),
            MockFieldMetadata(name="profit", fieldCaption="Profit", role="measure", dataType="REAL", category="财务"),
            MockFieldMetadata(name="cost", fieldCaption="Cost", role="measure", dataType="REAL", category="财务"),
            MockFieldMetadata(name="region", fieldCaption="Region", role="dimension", dataType="STRING", category="地理"),
            MockFieldMetadata(name="city", fieldCaption="City", role="dimension", dataType="STRING", category="地理"),
            MockFieldMetadata(name="date", fieldCaption="Order Date", role="dimension", dataType="DATE", category="时间"),
        ]
    
    @pytest.fixture
    def field_indexer(self, mixed_fields):
        """创建字段索引器"""
        provider = MockEmbedding(dimensions=64)
        indexer = FieldIndexer(embedding_provider=provider, use_cache=False)
        indexer.index_fields(mixed_fields)
        return indexer
    
    def test_role_filter_dimension(self, field_indexer):
        """测试角色过滤：dimension"""
        retriever = EmbeddingRetriever(field_indexer)
        filters = MetadataFilter(role="dimension")
        results = retriever.retrieve("test", top_k=10, filters=filters)
        
        for result in results:
            assert result.field_chunk.role == "dimension", f"期望 dimension，实际 {result.field_chunk.role}"
    
    def test_role_filter_measure(self, field_indexer):
        """测试角色过滤：measure"""
        retriever = EmbeddingRetriever(field_indexer)
        filters = MetadataFilter(role="measure")
        results = retriever.retrieve("test", top_k=10, filters=filters)
        
        for result in results:
            assert result.field_chunk.role == "measure", f"期望 measure，实际 {result.field_chunk.role}"
    
    def test_category_filter(self, field_indexer):
        """测试类别过滤"""
        retriever = EmbeddingRetriever(field_indexer)
        filters = MetadataFilter(category="财务")
        results = retriever.retrieve("test", top_k=10, filters=filters)
        
        for result in results:
            assert result.field_chunk.category == "财务", f"期望 财务，实际 {result.field_chunk.category}"
    
    def test_data_type_filter(self, field_indexer):
        """测试数据类型过滤"""
        retriever = EmbeddingRetriever(field_indexer)
        filters = MetadataFilter(data_type="STRING")
        results = retriever.retrieve("test", top_k=10, filters=filters)
        
        for result in results:
            assert result.field_chunk.data_type == "STRING", f"期望 STRING，实际 {result.field_chunk.data_type}"
    
    def test_combined_filters(self, field_indexer):
        """测试组合过滤"""
        retriever = EmbeddingRetriever(field_indexer)
        filters = MetadataFilter(role="dimension", category="地理")
        results = retriever.retrieve("test", top_k=10, filters=filters)
        
        for result in results:
            assert result.field_chunk.role == "dimension"
            assert result.field_chunk.category == "地理"
    
    @given(st.sampled_from(["dimension", "measure"]))
    @settings(max_examples=10, deadline=None)
    def test_role_filter_property(self, role):
        """
        属性测试：角色过滤
        
        **Feature: rag-enhancement, Property 6: 元数据过滤**
        **Validates: Requirements 2.4, 5.4**
        
        *For any* 角色过滤器，返回的所有字段应匹配指定的角色
        """
        fields = [
            MockFieldMetadata(name=f"dim_{i}", fieldCaption=f"Dimension {i}", role="dimension", dataType="STRING")
            for i in range(5)
        ] + [
            MockFieldMetadata(name=f"mea_{i}", fieldCaption=f"Measure {i}", role="measure", dataType="REAL")
            for i in range(5)
        ]
        
        provider = MockEmbedding(dimensions=32)
        indexer = FieldIndexer(embedding_provider=provider, use_cache=False)
        indexer.index_fields(fields)
        
        retriever = EmbeddingRetriever(indexer)
        filters = MetadataFilter(role=role)
        results = retriever.retrieve("test", top_k=10, filters=filters)
        
        for result in results:
            assert result.field_chunk.role == role, f"期望 {role}，实际 {result.field_chunk.role}"
    
    @given(st.sampled_from(["财务", "地理", "时间"]))
    @settings(max_examples=10, deadline=None)
    def test_category_filter_property(self, category):
        """
        属性测试：类别过滤
        
        **Feature: rag-enhancement, Property 6: 元数据过滤**
        **Validates: Requirements 2.4, 5.4**
        
        *For any* 类别过滤器，返回的所有字段应匹配指定的类别
        """
        fields = [
            MockFieldMetadata(name="sales", fieldCaption="Sales", role="measure", dataType="REAL", category="财务"),
            MockFieldMetadata(name="profit", fieldCaption="Profit", role="measure", dataType="REAL", category="财务"),
            MockFieldMetadata(name="region", fieldCaption="Region", role="dimension", dataType="STRING", category="地理"),
            MockFieldMetadata(name="city", fieldCaption="City", role="dimension", dataType="STRING", category="地理"),
            MockFieldMetadata(name="date", fieldCaption="Date", role="dimension", dataType="DATE", category="时间"),
            MockFieldMetadata(name="month", fieldCaption="Month", role="dimension", dataType="STRING", category="时间"),
        ]
        
        provider = MockEmbedding(dimensions=32)
        indexer = FieldIndexer(embedding_provider=provider, use_cache=False)
        indexer.index_fields(fields)
        
        retriever = EmbeddingRetriever(indexer)
        filters = MetadataFilter(category=category)
        results = retriever.retrieve("test", top_k=10, filters=filters)
        
        for result in results:
            assert result.field_chunk.category == category, f"期望 {category}，实际 {result.field_chunk.category}"
    
    def test_filter_reduces_result_count(self, field_indexer):
        """测试过滤器减少结果数量"""
        retriever = EmbeddingRetriever(field_indexer)
        
        # 不带过滤器
        results_all = retriever.retrieve("test", top_k=10)
        
        # 带角色过滤器
        filters = MetadataFilter(role="dimension")
        results_filtered = retriever.retrieve("test", top_k=10, filters=filters)
        
        # 过滤后结果应该更少或相等
        assert len(results_filtered) <= len(results_all)
    
    def test_keyword_retriever_with_filter(self, field_indexer):
        """测试关键词检索器的过滤功能"""
        retriever = KeywordRetriever(field_indexer)
        filters = MetadataFilter(role="measure")
        results = retriever.retrieve("amount", top_k=10, filters=filters)
        
        for result in results:
            assert result.field_chunk.role == "measure"
    
    def test_hybrid_retriever_with_filter(self, field_indexer):
        """测试混合检索器的过滤功能"""
        retriever = RetrieverFactory.create_hybrid_retriever(field_indexer)
        filters = MetadataFilter(role="dimension")
        results = retriever.retrieve("region", top_k=10, filters=filters)
        
        for result in results:
            assert result.field_chunk.role == "dimension"


class TestRetrieverFactory:
    """检索器工厂测试"""
    
    @pytest.fixture
    def field_indexer(self):
        """创建字段索引器"""
        fields = [
            MockFieldMetadata(name="field1", fieldCaption="Field 1", role="dimension", dataType="STRING"),
            MockFieldMetadata(name="field2", fieldCaption="Field 2", role="measure", dataType="REAL"),
        ]
        provider = MockEmbedding(dimensions=64)
        indexer = FieldIndexer(embedding_provider=provider, use_cache=False)
        indexer.index_fields(fields)
        return indexer
    
    def test_create_embedding_retriever(self, field_indexer):
        """测试创建向量检索器"""
        retriever = RetrieverFactory.create_embedding_retriever(field_indexer)
        assert isinstance(retriever, EmbeddingRetriever)
    
    def test_create_keyword_retriever(self, field_indexer):
        """测试创建关键词检索器"""
        retriever = RetrieverFactory.create_keyword_retriever(field_indexer)
        assert isinstance(retriever, KeywordRetriever)
    
    def test_create_hybrid_retriever(self, field_indexer):
        """测试创建混合检索器"""
        retriever = RetrieverFactory.create_hybrid_retriever(field_indexer)
        assert isinstance(retriever, HybridRetriever)
    
    def test_hybrid_retriever_with_custom_weights(self, field_indexer):
        """测试自定义权重的混合检索器"""
        retriever = RetrieverFactory.create_hybrid_retriever(
            field_indexer,
            embedding_weight=0.8,
            keyword_weight=0.2,
            use_rrf=False
        )
        assert isinstance(retriever, HybridRetriever)
        assert retriever.embedding_weight == 0.8
        assert retriever.keyword_weight == 0.2
        assert retriever.use_rrf is False


class TestAsyncRetrieval:
    """异步检索测试"""
    
    @pytest.fixture
    def field_indexer(self):
        """创建字段索引器"""
        fields = [
            MockFieldMetadata(name="field1", fieldCaption="Field 1", role="dimension", dataType="STRING"),
            MockFieldMetadata(name="field2", fieldCaption="Field 2", role="measure", dataType="REAL"),
        ]
        provider = MockEmbedding(dimensions=64)
        indexer = FieldIndexer(embedding_provider=provider, use_cache=False)
        indexer.index_fields(fields)
        return indexer
    
    @pytest.mark.asyncio
    async def test_async_embedding_retrieval(self, field_indexer):
        """测试异步向量检索"""
        retriever = EmbeddingRetriever(field_indexer)
        results = await retriever.aretrieve("test", top_k=5)
        
        assert isinstance(results, list)
        for result in results:
            assert isinstance(result, RetrievalResult)
            assert 0 <= result.score <= 1
    
    @pytest.mark.asyncio
    async def test_async_keyword_retrieval(self, field_indexer):
        """测试异步关键词检索"""
        retriever = KeywordRetriever(field_indexer)
        results = await retriever.aretrieve("field", top_k=5)
        
        assert isinstance(results, list)
        for result in results:
            assert isinstance(result, RetrievalResult)
            assert 0 <= result.score <= 1
    
    @pytest.mark.asyncio
    async def test_async_hybrid_retrieval(self, field_indexer):
        """测试异步混合检索"""
        retriever = RetrieverFactory.create_hybrid_retriever(field_indexer)
        results = await retriever.aretrieve("test", top_k=5)
        
        assert isinstance(results, list)
        for result in results:
            assert isinstance(result, RetrievalResult)
            assert 0 <= result.score <= 1


class TestRetrievalConfig:
    """检索配置测试"""
    
    @pytest.fixture
    def field_indexer(self):
        """创建字段索引器"""
        fields = [
            MockFieldMetadata(name=f"field_{i}", fieldCaption=f"Field {i}", role="dimension", dataType="STRING")
            for i in range(10)
        ]
        provider = MockEmbedding(dimensions=64)
        indexer = FieldIndexer(embedding_provider=provider, use_cache=False)
        indexer.index_fields(fields)
        return indexer
    
    def test_top_k_config(self, field_indexer):
        """测试 top_k 配置"""
        config = RetrievalConfig(top_k=3)
        retriever = EmbeddingRetriever(field_indexer, config)
        results = retriever.retrieve("test")
        
        assert len(results) <= 3
    
    def test_score_threshold_config(self, field_indexer):
        """测试分数阈值配置"""
        config = RetrievalConfig(score_threshold=0.5)
        retriever = EmbeddingRetriever(field_indexer, config)
        results = retriever.retrieve("test")
        
        for result in results:
            assert result.score >= 0.5
    
    def test_override_config_in_retrieve(self, field_indexer):
        """测试在检索时覆盖配置"""
        config = RetrievalConfig(top_k=10)
        retriever = EmbeddingRetriever(field_indexer, config)
        
        # 覆盖 top_k
        results = retriever.retrieve("test", top_k=2)
        assert len(results) <= 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
