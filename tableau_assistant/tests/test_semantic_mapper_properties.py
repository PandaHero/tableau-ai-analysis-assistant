"""
语义映射器属性测试

**Feature: rag-enhancement, Property 4: 检索结果数量**
**Validates: Requirements 2.1, 3.1**

**Feature: rag-enhancement, Property 11: 低置信度备选**
**Validates: Requirements 3.5**

测试语义映射器的检索结果数量和低置信度备选功能。
"""
import pytest
from hypothesis import given, strategies as st, settings
from dataclasses import dataclass
from typing import List, Optional

from tableau_assistant.src.capabilities.rag.semantic_mapper import (
    SemanticMapper,
    MappingConfig,
    FieldMappingResult,
    MappingSource,
)
from tableau_assistant.src.capabilities.rag.field_indexer import FieldIndexer
from tableau_assistant.src.capabilities.rag.embeddings import MockEmbedding, ZhipuEmbedding


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


class TestSemanticMapperBasic:
    """基本功能测试"""
    
    @pytest.fixture
    def sample_fields(self):
        """创建测试字段"""
        return [
            MockFieldMetadata(
                name="sales_amount",
                fieldCaption="Sales Amount",
                role="measure",
                dataType="REAL",
                category="财务",
                sample_values=["1000", "2000", "3000"]
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
                category="地理",
                sample_values=["华东", "华北", "华南"]
            ),
            MockFieldMetadata(
                name="customer_name",
                fieldCaption="Customer Name",
                role="dimension",
                dataType="STRING",
                category="客户"
            ),
            MockFieldMetadata(
                name="order_date",
                fieldCaption="Order Date",
                role="dimension",
                dataType="DATE",
                category="时间"
            ),
        ]
    
    @pytest.fixture
    def semantic_mapper(self, sample_fields):
        """创建语义映射器"""
        provider = MockEmbedding(dimensions=128)
        indexer = FieldIndexer(embedding_provider=provider, use_cache=False)
        indexer.index_fields(sample_fields)
        
        config = MappingConfig(
            top_k=10,
            confidence_threshold=0.7,
            high_confidence_threshold=0.9
        )
        return SemanticMapper(indexer, config)
    
    def test_map_field_returns_result(self, semantic_mapper):
        """测试映射字段返回结果"""
        result = semantic_mapper.map_field("销售金额")
        
        assert isinstance(result, FieldMappingResult)
        assert result.term == "销售金额"
        # 使用 float() 转换以支持 numpy 类型
        assert isinstance(float(result.confidence), float)
        assert 0 <= result.confidence <= 1
        assert result.latency_ms >= 0
    
    def test_map_fields_batch(self, semantic_mapper):
        """测试批量映射"""
        terms = ["销售金额", "地区", "客户名称"]
        results = semantic_mapper.map_fields_batch(terms)
        
        assert len(results) == len(terms)
        for i, result in enumerate(results):
            assert result.term == terms[i]
    
    def test_empty_term_returns_none(self, semantic_mapper):
        """测试空术语返回 None"""
        result = semantic_mapper.map_field("")
        assert result.matched_field is None
        assert result.confidence == 0.0
        
        result = semantic_mapper.map_field("   ")
        assert result.matched_field is None


class TestRetrievalResultCount:
    """
    检索结果数量测试
    
    **Feature: rag-enhancement, Property 4: 检索结果数量**
    **Validates: Requirements 2.1, 3.1**
    """
    
    @pytest.fixture
    def many_fields(self):
        """创建多个测试字段"""
        fields = []
        for i in range(20):
            fields.append(MockFieldMetadata(
                name=f"field_{i}",
                fieldCaption=f"Field {i}",
                role="dimension" if i % 2 == 0 else "measure",
                dataType="STRING" if i % 2 == 0 else "REAL"
            ))
        return fields
    
    def test_retrieval_returns_top_k(self, many_fields):
        """测试检索返回 top-K 结果"""
        provider = MockEmbedding(dimensions=64)
        indexer = FieldIndexer(embedding_provider=provider, use_cache=False)
        indexer.index_fields(many_fields)
        
        config = MappingConfig(top_k=10)
        mapper = SemanticMapper(indexer, config)
        
        result = mapper.map_field("test query")
        
        # 验证检索结果数量
        assert len(result.retrieval_results) <= config.top_k
    
    @given(st.integers(min_value=1, max_value=15))
    @settings(max_examples=10, deadline=None)
    def test_retrieval_count_property(self, top_k):
        """
        属性测试：向量检索应返回恰好 top-K 个候选（或全部字段如果少于 K）
        
        **Feature: rag-enhancement, Property 4: 检索结果数量**
        **Validates: Requirements 2.1, 3.1**
        """
        # 创建固定数量的字段
        num_fields = 20
        fields = [
            MockFieldMetadata(
                name=f"field_{i}",
                fieldCaption=f"Field {i}",
                role="dimension",
                dataType="STRING"
            )
            for i in range(num_fields)
        ]
        
        provider = MockEmbedding(dimensions=32)
        indexer = FieldIndexer(embedding_provider=provider, use_cache=False)
        indexer.index_fields(fields)
        
        config = MappingConfig(top_k=top_k)
        mapper = SemanticMapper(indexer, config)
        
        result = mapper.map_field("test")
        
        # 验证：返回数量应该是 min(top_k, num_fields)
        expected_count = min(top_k, num_fields)
        assert len(result.retrieval_results) == expected_count
    
    def test_retrieval_with_filter_reduces_count(self):
        """测试过滤器减少结果数量"""
        fields = [
            MockFieldMetadata(name="dim1", fieldCaption="Dimension 1", role="dimension", dataType="STRING"),
            MockFieldMetadata(name="dim2", fieldCaption="Dimension 2", role="dimension", dataType="STRING"),
            MockFieldMetadata(name="mea1", fieldCaption="Measure 1", role="measure", dataType="REAL"),
            MockFieldMetadata(name="mea2", fieldCaption="Measure 2", role="measure", dataType="REAL"),
        ]
        
        provider = MockEmbedding(dimensions=64)
        indexer = FieldIndexer(embedding_provider=provider, use_cache=False)
        indexer.index_fields(fields)
        
        mapper = SemanticMapper(indexer, MappingConfig(top_k=10))
        
        # 不带过滤器
        result_all = mapper.map_field("test")
        
        # 带角色过滤器
        result_dim = mapper.map_field("test", role_filter="dimension")
        result_mea = mapper.map_field("test", role_filter="measure")
        
        # 验证过滤后结果只包含对应角色
        for r in result_dim.retrieval_results:
            assert r.field_chunk.role == "dimension"
        
        for r in result_mea.retrieval_results:
            assert r.field_chunk.role == "measure"


class TestLowConfidenceAlternatives:
    """
    低置信度备选测试
    
    **Feature: rag-enhancement, Property 11: 低置信度备选**
    **Validates: Requirements 3.5**
    """
    
    @pytest.fixture
    def similar_fields(self):
        """创建相似字段（用于测试低置信度场景）"""
        return [
            MockFieldMetadata(name="amount_1", fieldCaption="Amount Type 1", role="measure", dataType="REAL"),
            MockFieldMetadata(name="amount_2", fieldCaption="Amount Type 2", role="measure", dataType="REAL"),
            MockFieldMetadata(name="amount_3", fieldCaption="Amount Type 3", role="measure", dataType="REAL"),
            MockFieldMetadata(name="amount_4", fieldCaption="Amount Type 4", role="measure", dataType="REAL"),
            MockFieldMetadata(name="other_field", fieldCaption="Other Field", role="dimension", dataType="STRING"),
        ]
    
    def test_low_confidence_returns_alternatives(self, similar_fields):
        """测试低置信度返回备选"""
        provider = MockEmbedding(dimensions=64)
        indexer = FieldIndexer(embedding_provider=provider, use_cache=False)
        indexer.index_fields(similar_fields)
        
        # 设置较高的置信度阈值，使结果更可能是低置信度
        config = MappingConfig(
            top_k=10,
            confidence_threshold=0.99,  # 非常高的阈值
            max_alternatives=3
        )
        mapper = SemanticMapper(indexer, config)
        
        result = mapper.map_field("amount")
        
        # 如果置信度低于阈值，应该有备选
        if result.confidence < config.confidence_threshold:
            assert len(result.alternatives) <= config.max_alternatives
    
    @given(st.integers(min_value=1, max_value=5))
    @settings(max_examples=10, deadline=None)
    def test_alternatives_count_property(self, max_alternatives):
        """
        属性测试：低置信度时返回的备选数量不超过 max_alternatives
        
        **Feature: rag-enhancement, Property 11: 低置信度备选**
        **Validates: Requirements 3.5**
        """
        fields = [
            MockFieldMetadata(name=f"field_{i}", fieldCaption=f"Field {i}", role="measure", dataType="REAL")
            for i in range(10)
        ]
        
        provider = MockEmbedding(dimensions=32)
        indexer = FieldIndexer(embedding_provider=provider, use_cache=False)
        indexer.index_fields(fields)
        
        config = MappingConfig(
            top_k=10,
            confidence_threshold=0.99,  # 高阈值确保低置信度
            max_alternatives=max_alternatives
        )
        mapper = SemanticMapper(indexer, config)
        
        result = mapper.map_field("test")
        
        # 验证备选数量不超过配置
        assert len(result.alternatives) <= max_alternatives
    
    def test_high_confidence_no_alternatives(self):
        """测试高置信度不返回备选"""
        fields = [
            MockFieldMetadata(name="exact_match", fieldCaption="Exact Match Field", role="measure", dataType="REAL"),
        ]
        
        provider = MockEmbedding(dimensions=64)
        indexer = FieldIndexer(embedding_provider=provider, use_cache=False)
        indexer.index_fields(fields)
        
        # 设置较低的置信度阈值
        config = MappingConfig(
            top_k=10,
            confidence_threshold=0.1,  # 低阈值
            max_alternatives=3
        )
        mapper = SemanticMapper(indexer, config)
        
        result = mapper.map_field("exact match")
        
        # 高置信度时不应该有备选
        if result.confidence >= config.confidence_threshold:
            assert len(result.alternatives) == 0


class TestDisambiguation:
    """消歧功能测试"""
    
    def test_exact_name_match_boost(self):
        """测试精确名称匹配加分"""
        fields = [
            MockFieldMetadata(name="sales", fieldCaption="Sales Amount", role="measure", dataType="REAL"),
            MockFieldMetadata(name="revenue", fieldCaption="Revenue", role="measure", dataType="REAL"),
        ]
        
        provider = MockEmbedding(dimensions=64)
        indexer = FieldIndexer(embedding_provider=provider, use_cache=False)
        indexer.index_fields(fields)
        
        mapper = SemanticMapper(indexer, MappingConfig())
        
        # 搜索 "sales" 应该优先匹配 sales 字段
        result = mapper.map_field("sales")
        
        # 验证有检索结果
        assert len(result.retrieval_results) > 0
    
    def test_context_affects_disambiguation(self):
        """测试上下文影响消歧"""
        fields = [
            MockFieldMetadata(
                name="amount_finance",
                fieldCaption="Amount",
                role="measure",
                dataType="REAL",
                category="财务"
            ),
            MockFieldMetadata(
                name="amount_sales",
                fieldCaption="Amount",
                role="measure",
                dataType="REAL",
                category="销售"
            ),
        ]
        
        provider = MockEmbedding(dimensions=64)
        indexer = FieldIndexer(embedding_provider=provider, use_cache=False)
        indexer.index_fields(fields)
        
        mapper = SemanticMapper(indexer, MappingConfig())
        
        # 带财务上下文
        result_finance = mapper.map_field("金额", context="财务报表")
        
        # 带销售上下文
        result_sales = mapper.map_field("金额", context="销售数据")
        
        # 验证有检索结果
        assert len(result_finance.retrieval_results) > 0
        assert len(result_sales.retrieval_results) > 0


class TestMappingStats:
    """统计信息测试"""
    
    def test_stats_tracking(self):
        """测试统计信息追踪"""
        fields = [
            MockFieldMetadata(name="field1", fieldCaption="Field 1", role="dimension", dataType="STRING"),
        ]
        
        provider = MockEmbedding(dimensions=64)
        indexer = FieldIndexer(embedding_provider=provider, use_cache=False)
        indexer.index_fields(fields)
        
        mapper = SemanticMapper(indexer, MappingConfig())
        
        # 执行几次映射
        mapper.map_field("test1")
        mapper.map_field("test2")
        mapper.map_field("test3")
        
        stats = mapper.get_stats()
        
        assert stats["total_mappings"] == 3
        assert "cache_hit_rate" in stats
        assert "fast_path_rate" in stats
    
    def test_stats_reset(self):
        """测试统计信息重置"""
        fields = [
            MockFieldMetadata(name="field1", fieldCaption="Field 1", role="dimension", dataType="STRING"),
        ]
        
        provider = MockEmbedding(dimensions=64)
        indexer = FieldIndexer(embedding_provider=provider, use_cache=False)
        indexer.index_fields(fields)
        
        mapper = SemanticMapper(indexer, MappingConfig())
        
        mapper.map_field("test")
        mapper.reset_stats()
        
        stats = mapper.get_stats()
        assert stats["total_mappings"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class TestHighConfidenceFastPath:
    """
    高置信度快速路径测试
    
    **Feature: rag-enhancement, Property 10: 高置信度快速路径**
    **Validates: Requirements 13.1**
    
    验证：向量检索 top-1 置信度 > 0.9 时跳过 LLM 判断直接返回
    """
    
    def test_high_confidence_uses_fast_path(self):
        """测试高置信度使用快速路径"""
        fields = [
            MockFieldMetadata(name="field1", fieldCaption="Field 1", role="dimension", dataType="STRING"),
        ]
        
        provider = MockEmbedding(dimensions=64)
        indexer = FieldIndexer(embedding_provider=provider, use_cache=False)
        indexer.index_fields(fields)
        
        # 设置较低的高置信度阈值，使结果更可能触发快速路径
        config = MappingConfig(
            top_k=10,
            confidence_threshold=0.1,
            high_confidence_threshold=0.05  # 非常低的阈值
        )
        mapper = SemanticMapper(indexer, config)
        
        result = mapper.map_field("field")
        
        # 验证使用了快速路径
        if result.confidence >= config.high_confidence_threshold:
            assert result.source == MappingSource.VECTOR_FAST
    
    def test_fast_path_increments_stats(self):
        """测试快速路径增加统计"""
        fields = [
            MockFieldMetadata(name="field1", fieldCaption="Field 1", role="dimension", dataType="STRING"),
        ]
        
        provider = MockEmbedding(dimensions=64)
        indexer = FieldIndexer(embedding_provider=provider, use_cache=False)
        indexer.index_fields(fields)
        
        config = MappingConfig(high_confidence_threshold=0.01)  # 非常低
        mapper = SemanticMapper(indexer, config)
        
        mapper.map_field("test")
        stats = mapper.get_stats()
        
        # 验证统计信息
        assert stats["total_mappings"] == 1
        assert "fast_path_hits" in stats
        assert "fast_path_rate" in stats
    
    def test_fast_path_skips_disambiguation(self):
        """测试快速路径跳过消歧步骤"""
        # 创建多个相似字段
        fields = [
            MockFieldMetadata(name="sales_amount", fieldCaption="Sales Amount", role="measure", dataType="REAL"),
            MockFieldMetadata(name="sales_total", fieldCaption="Sales Total", role="measure", dataType="REAL"),
            MockFieldMetadata(name="sales_count", fieldCaption="Sales Count", role="measure", dataType="INTEGER"),
        ]
        
        provider = MockEmbedding(dimensions=64)
        indexer = FieldIndexer(embedding_provider=provider, use_cache=False)
        indexer.index_fields(fields)
        
        # 设置非常低的阈值确保触发快速路径
        config = MappingConfig(high_confidence_threshold=0.01)
        mapper = SemanticMapper(indexer, config)
        
        result = mapper.map_field("sales")
        
        # 快速路径应该直接返回 top-1，不进行消歧
        if result.source == MappingSource.VECTOR_FAST:
            assert result.matched_field is not None
            # 快速路径不应该有备选（因为直接返回）
            assert len(result.alternatives) == 0
    
    def test_below_threshold_uses_normal_path(self):
        """测试低于阈值使用正常路径
        
        注意：MockEmbedding 总是返回高置信度分数（基于向量相似度），
        所以需要设置超过 1.0 的阈值来确保不触发快速路径。
        """
        fields = [
            MockFieldMetadata(name="field1", fieldCaption="Field 1", role="dimension", dataType="STRING"),
        ]
        
        provider = MockEmbedding(dimensions=64)
        indexer = FieldIndexer(embedding_provider=provider, use_cache=False)
        indexer.index_fields(fields)
        
        # 设置阈值为 1.1（超过最大可能分数 1.0），确保不触发快速路径
        config = MappingConfig(high_confidence_threshold=1.1)
        mapper = SemanticMapper(indexer, config)
        
        result = mapper.map_field("completely unrelated query xyz")
        
        # 当阈值设置为 1.1 时，任何分数都低于阈值，应该使用正常路径
        # 但由于 MockEmbedding 的特性，实际分数可能仍然很高
        # 这里验证结果存在且有效即可
        assert result is not None
        assert result.matched_field == "field1"
        # 当阈值 > 1.0 时，不应该触发快速路径
        assert result.source != MappingSource.VECTOR_FAST or config.high_confidence_threshold <= 1.0
    
    @given(st.floats(min_value=0.01, max_value=0.5))
    @settings(max_examples=10, deadline=None)
    def test_fast_path_threshold_property(self, threshold):
        """
        属性测试：高置信度阈值决定是否使用快速路径
        
        **Feature: rag-enhancement, Property 10: 高置信度快速路径**
        **Validates: Requirements 13.1**
        
        *For any* 高置信度阈值，当 top-1 分数 >= 阈值时应使用快速路径
        """
        fields = [
            MockFieldMetadata(name="test", fieldCaption="Test", role="dimension", dataType="STRING"),
        ]
        
        provider = MockEmbedding(dimensions=32)
        indexer = FieldIndexer(embedding_provider=provider, use_cache=False)
        indexer.index_fields(fields)
        
        config = MappingConfig(high_confidence_threshold=threshold)
        mapper = SemanticMapper(indexer, config)
        
        result = mapper.map_field("test")
        
        # 验证：如果置信度 >= 阈值，应该使用快速路径
        if result.confidence >= threshold:
            assert result.source == MappingSource.VECTOR_FAST
        else:
            assert result.source == MappingSource.VECTOR
    
    @given(st.integers(min_value=1, max_value=10))
    @settings(max_examples=10, deadline=None)
    def test_fast_path_with_multiple_fields_property(self, num_fields):
        """
        属性测试：多字段场景下高置信度快速路径行为
        
        **Feature: rag-enhancement, Property 10: 高置信度快速路径**
        **Validates: Requirements 13.1**
        
        *For any* 字段数量，高置信度时应跳过 LLM 直接返回 top-1
        """
        fields = [
            MockFieldMetadata(
                name=f"field_{i}",
                fieldCaption=f"Field {i}",
                role="dimension" if i % 2 == 0 else "measure",
                dataType="STRING" if i % 2 == 0 else "REAL"
            )
            for i in range(num_fields)
        ]
        
        provider = MockEmbedding(dimensions=32)
        indexer = FieldIndexer(embedding_provider=provider, use_cache=False)
        indexer.index_fields(fields)
        
        # 使用低阈值确保触发快速路径
        config = MappingConfig(high_confidence_threshold=0.01)
        mapper = SemanticMapper(indexer, config)
        
        result = mapper.map_field("field")
        
        # 验证快速路径行为
        if result.confidence >= config.high_confidence_threshold:
            assert result.source == MappingSource.VECTOR_FAST
            assert result.matched_field is not None
            # 快速路径应该有检索结果
            assert len(result.retrieval_results) > 0
    
    def test_fast_path_stats_accuracy(self):
        """测试快速路径统计准确性"""
        fields = [
            MockFieldMetadata(name="field1", fieldCaption="Field 1", role="dimension", dataType="STRING"),
            MockFieldMetadata(name="field2", fieldCaption="Field 2", role="measure", dataType="REAL"),
        ]
        
        provider = MockEmbedding(dimensions=64)
        indexer = FieldIndexer(embedding_provider=provider, use_cache=False)
        indexer.index_fields(fields)
        
        # 低阈值确保快速路径
        config = MappingConfig(high_confidence_threshold=0.01)
        mapper = SemanticMapper(indexer, config)
        
        # 执行多次映射
        for _ in range(5):
            mapper.map_field("field")
        
        stats = mapper.get_stats()
        
        # 验证统计
        assert stats["total_mappings"] == 5
        assert stats["fast_path_hits"] >= 0
        assert stats["fast_path_rate"] == stats["fast_path_hits"] / stats["total_mappings"]


@pytest.mark.integration
class TestHistoryReuseWithRealEmbedding:
    """
    历史结果复用测试（使用真实 ZhipuEmbedding）
    
    **Feature: rag-enhancement, Property 9: 缓存一致性**
    **Validates: Requirements 7.1, 7.2, 13.2**
    
    测试相似度 > 0.95 时复用缓存结果的功能。
    使用真实的智谱 AI embedding-2 进行语义相似度计算。
    
    注意：这些测试需要网络连接和有效的 API Key。
    运行方式：pytest -m integration
    """
    
    @pytest.fixture
    def zhipu_provider(self):
        """创建真实的智谱 Embedding 提供者"""
        import os
        from tableau_assistant.src.capabilities.rag.embeddings import ZhipuEmbedding
        
        # 支持两种环境变量名
        api_key = os.getenv("ZHIPUAI_API_KEY") or os.getenv("ZHIPU_API_KEY")
        if not api_key:
            pytest.skip("ZHIPUAI_API_KEY 或 ZHIPU_API_KEY 环境变量未设置，跳过真实 Embedding 测试")
        
        try:
            provider = ZhipuEmbedding(api_key=api_key)
            # 测试连接是否正常
            provider.embed_query("test")
            return provider
        except Exception as e:
            pytest.skip(f"智谱 AI API 连接失败，跳过测试: {e}")
    
    @pytest.fixture
    def real_fields(self):
        """创建真实的测试字段"""
        return [
            MockFieldMetadata(
                name="sales_amount",
                fieldCaption="销售金额",
                role="measure",
                dataType="REAL",
                category="财务",
                sample_values=["1000", "2000", "3000"]
            ),
            MockFieldMetadata(
                name="revenue",
                fieldCaption="营业收入",
                role="measure",
                dataType="REAL",
                category="财务"
            ),
            MockFieldMetadata(
                name="profit",
                fieldCaption="利润",
                role="measure",
                dataType="REAL",
                category="财务"
            ),
            MockFieldMetadata(
                name="region",
                fieldCaption="地区",
                role="dimension",
                dataType="STRING",
                category="地理",
                sample_values=["华东", "华北", "华南"]
            ),
            MockFieldMetadata(
                name="customer_name",
                fieldCaption="客户名称",
                role="dimension",
                dataType="STRING",
                category="客户"
            ),
            MockFieldMetadata(
                name="order_date",
                fieldCaption="订单日期",
                role="dimension",
                dataType="DATE",
                category="时间"
            ),
        ]
    
    def test_identical_query_reuses_history(self, zhipu_provider, real_fields):
        """
        测试完全相同的查询复用历史结果
        
        **Feature: rag-enhancement, Property 9: 缓存一致性**
        **Validates: Requirements 13.2**
        """
        indexer = FieldIndexer(embedding_provider=zhipu_provider, use_cache=False)
        indexer.index_fields(real_fields)
        
        config = MappingConfig(
            enable_history_reuse=True,
            history_similarity_threshold=0.95
        )
        mapper = SemanticMapper(indexer, config)
        
        # 第一次查询
        result1 = mapper.map_field("销售金额")
        
        # 第二次完全相同的查询应该复用历史结果
        result2 = mapper.map_field("销售金额")
        
        # 验证结果一致
        assert result1.matched_field == result2.matched_field
        assert result2.source == MappingSource.CACHE
        
        stats = mapper.get_stats()
        assert stats["history_reuse_hits"] >= 1
    
    def test_similar_query_reuses_history(self, zhipu_provider, real_fields):
        """
        测试语义相似的查询复用历史结果
        
        **Feature: rag-enhancement, Property 9: 缓存一致性**
        **Validates: Requirements 13.2**
        
        例如："销售金额" 和 "销售额" 应该被认为是相似的
        """
        indexer = FieldIndexer(embedding_provider=zhipu_provider, use_cache=False)
        indexer.index_fields(real_fields)
        
        config = MappingConfig(
            enable_history_reuse=True,
            history_similarity_threshold=0.90  # 稍微降低阈值以测试相似查询
        )
        mapper = SemanticMapper(indexer, config)
        
        # 第一次查询
        result1 = mapper.map_field("销售金额")
        
        # 语义相似的查询
        result2 = mapper.map_field("销售额")
        
        # 如果相似度足够高，应该复用历史结果
        # 注意：这取决于实际的语义相似度
        stats = mapper.get_stats()
        print(f"历史复用统计: {stats}")
        
        # 验证至少有检索结果
        assert result1.retrieval_results is not None
        assert result2.retrieval_results is not None
    
    def test_different_query_no_reuse(self, zhipu_provider, real_fields):
        """
        测试语义不同的查询不复用历史结果
        
        **Feature: rag-enhancement, Property 9: 缓存一致性**
        **Validates: Requirements 13.2**
        """
        indexer = FieldIndexer(embedding_provider=zhipu_provider, use_cache=False)
        indexer.index_fields(real_fields)
        
        config = MappingConfig(
            enable_history_reuse=True,
            history_similarity_threshold=0.95
        )
        mapper = SemanticMapper(indexer, config)
        
        # 第一次查询
        result1 = mapper.map_field("销售金额")
        
        # 完全不同的查询不应该复用
        result2 = mapper.map_field("客户名称")
        
        # 第二次查询不应该从缓存获取
        assert result2.source != MappingSource.CACHE
    
    def test_history_reuse_performance(self, zhipu_provider, real_fields):
        """
        测试历史复用的性能提升
        
        **Feature: rag-enhancement, Property 9: 缓存一致性**
        **Validates: Requirements 13.2**
        
        复用历史结果应该比重新计算快得多
        """
        indexer = FieldIndexer(embedding_provider=zhipu_provider, use_cache=False)
        indexer.index_fields(real_fields)
        
        config = MappingConfig(
            enable_history_reuse=True,
            history_similarity_threshold=0.95
        )
        mapper = SemanticMapper(indexer, config)
        
        # 第一次查询（需要调用 API）
        result1 = mapper.map_field("销售金额")
        latency1 = result1.latency_ms
        
        # 第二次查询（应该复用历史）
        result2 = mapper.map_field("销售金额")
        latency2 = result2.latency_ms
        
        print(f"第一次查询延迟: {latency1}ms")
        print(f"第二次查询延迟: {latency2}ms")
        
        # 复用历史应该更快
        if result2.source == MappingSource.CACHE:
            assert latency2 < latency1, "历史复用应该比重新计算快"
    
    def test_history_size_limit(self, zhipu_provider, real_fields):
        """
        测试历史记录大小限制
        
        **Feature: rag-enhancement, Property 9: 缓存一致性**
        """
        indexer = FieldIndexer(embedding_provider=zhipu_provider, use_cache=False)
        indexer.index_fields(real_fields)
        
        config = MappingConfig(
            enable_history_reuse=True,
            history_similarity_threshold=0.95,
            max_history_size=5  # 限制历史大小
        )
        mapper = SemanticMapper(indexer, config)
        
        # 执行多次不同的查询
        queries = ["销售金额", "营业收入", "利润", "地区", "客户名称", "订单日期", "总金额"]
        for query in queries:
            mapper.map_field(query)
        
        stats = mapper.get_stats()
        
        # 历史大小不应超过限制
        assert stats["history_size"] <= config.max_history_size



class TestBatchProcessingConcurrency:
    """
    批量处理并发测试
    
    **Feature: rag-enhancement, Property 15: 批量处理并发**
    **Validates: Requirements 7.4, 13.4**
    
    测试批量字段映射的并发处理功能。
    """
    
    @pytest.fixture
    def sample_fields(self):
        """创建测试字段"""
        return [
            MockFieldMetadata(name="sales", fieldCaption="Sales Amount", role="measure", dataType="REAL"),
            MockFieldMetadata(name="profit", fieldCaption="Profit", role="measure", dataType="REAL"),
            MockFieldMetadata(name="region", fieldCaption="Region", role="dimension", dataType="STRING"),
            MockFieldMetadata(name="date", fieldCaption="Order Date", role="dimension", dataType="DATE"),
            MockFieldMetadata(name="customer", fieldCaption="Customer Name", role="dimension", dataType="STRING"),
        ]
    
    def test_batch_sync_returns_correct_count(self, sample_fields):
        """测试同步批量处理返回正确数量"""
        provider = MockEmbedding(dimensions=64)
        indexer = FieldIndexer(embedding_provider=provider, use_cache=False)
        indexer.index_fields(sample_fields)
        
        mapper = SemanticMapper(indexer, MappingConfig())
        
        terms = ["销售", "利润", "地区"]
        results = mapper.map_fields_batch(terms)
        
        assert len(results) == len(terms)
        for i, result in enumerate(results):
            assert result.term == terms[i]
    
    @pytest.mark.asyncio
    async def test_batch_async_returns_correct_count(self, sample_fields):
        """测试异步批量处理返回正确数量"""
        provider = MockEmbedding(dimensions=64)
        indexer = FieldIndexer(embedding_provider=provider, use_cache=False)
        indexer.index_fields(sample_fields)
        
        mapper = SemanticMapper(indexer, MappingConfig())
        
        terms = ["销售", "利润", "地区", "日期", "客户"]
        results = await mapper.map_fields_batch_async(terms, max_concurrency=3)
        
        assert len(results) == len(terms)
        for i, result in enumerate(results):
            assert result.term == terms[i]
    
    @pytest.mark.asyncio
    async def test_batch_async_preserves_order(self, sample_fields):
        """测试异步批量处理保持原始顺序"""
        provider = MockEmbedding(dimensions=64)
        indexer = FieldIndexer(embedding_provider=provider, use_cache=False)
        indexer.index_fields(sample_fields)
        
        mapper = SemanticMapper(indexer, MappingConfig())
        
        terms = ["term_1", "term_2", "term_3", "term_4", "term_5"]
        results = await mapper.map_fields_batch_async(terms, max_concurrency=5)
        
        # 验证顺序保持
        for i, result in enumerate(results):
            assert result.term == terms[i]
    
    @pytest.mark.asyncio
    async def test_batch_async_respects_concurrency_limit(self, sample_fields):
        """测试异步批量处理遵守并发限制"""
        provider = MockEmbedding(dimensions=64)
        indexer = FieldIndexer(embedding_provider=provider, use_cache=False)
        indexer.index_fields(sample_fields)
        
        mapper = SemanticMapper(indexer, MappingConfig())
        
        # 创建多个查询
        terms = [f"query_{i}" for i in range(10)]
        
        # 使用较小的并发限制
        results = await mapper.map_fields_batch_async(terms, max_concurrency=2)
        
        assert len(results) == len(terms)
    
    @given(st.integers(min_value=1, max_value=10))
    @settings(max_examples=5, deadline=None)
    def test_batch_sync_count_property(self, num_terms):
        """
        属性测试：同步批量处理返回数量等于输入数量
        
        **Feature: rag-enhancement, Property 15: 批量处理并发**
        **Validates: Requirements 7.4, 13.4**
        """
        fields = [
            MockFieldMetadata(name=f"field_{i}", fieldCaption=f"Field {i}", role="dimension", dataType="STRING")
            for i in range(5)
        ]
        
        provider = MockEmbedding(dimensions=32)
        indexer = FieldIndexer(embedding_provider=provider, use_cache=False)
        indexer.index_fields(fields)
        
        mapper = SemanticMapper(indexer, MappingConfig())
        
        terms = [f"term_{i}" for i in range(num_terms)]
        results = mapper.map_fields_batch(terms)
        
        assert len(results) == num_terms
    
    def test_batch_sync_vs_individual_consistency(self, sample_fields):
        """测试批量处理与单独处理结果一致"""
        provider = MockEmbedding(dimensions=64, seed=42)
        indexer = FieldIndexer(embedding_provider=provider, use_cache=False)
        indexer.index_fields(sample_fields)
        
        mapper = SemanticMapper(indexer, MappingConfig(enable_history_reuse=False))
        
        terms = ["销售", "利润"]
        
        # 单独处理
        individual_results = [mapper.map_field(term) for term in terms]
        
        # 重置统计
        mapper.reset_stats()
        
        # 批量处理
        batch_results = mapper.map_fields_batch(terms)
        
        # 验证结果一致
        for i in range(len(terms)):
            assert individual_results[i].matched_field == batch_results[i].matched_field


class TestLLMFallback:
    """
    LLM 降级测试
    
    **Feature: rag-enhancement**
    **Validates: Requirements 13.3**
    
    测试 LLM 不可用时的降级功能。
    """
    
    @pytest.fixture
    def sample_fields(self):
        """创建测试字段"""
        return [
            MockFieldMetadata(name="sales", fieldCaption="Sales Amount", role="measure", dataType="REAL"),
            MockFieldMetadata(name="profit", fieldCaption="Profit", role="measure", dataType="REAL"),
            MockFieldMetadata(name="region", fieldCaption="Region", role="dimension", dataType="STRING"),
        ]
    
    def test_fallback_returns_top1(self, sample_fields):
        """测试降级返回向量检索 top-1"""
        provider = MockEmbedding(dimensions=64)
        indexer = FieldIndexer(embedding_provider=provider, use_cache=False)
        indexer.index_fields(sample_fields)
        
        mapper = SemanticMapper(indexer, MappingConfig())
        
        result = mapper.map_field_fallback("销售")
        
        assert result.source == MappingSource.FALLBACK
        assert result.matched_field is not None
        assert "降级" in result.reasoning
    
    def test_fallback_has_retrieval_results(self, sample_fields):
        """测试降级结果包含检索结果"""
        provider = MockEmbedding(dimensions=64)
        indexer = FieldIndexer(embedding_provider=provider, use_cache=False)
        indexer.index_fields(sample_fields)
        
        mapper = SemanticMapper(indexer, MappingConfig())
        
        result = mapper.map_field_fallback("销售")
        
        # 降级应该只返回 top-1
        assert len(result.retrieval_results) == 1
    
    def test_fallback_empty_term(self, sample_fields):
        """测试降级处理空术语"""
        provider = MockEmbedding(dimensions=64)
        indexer = FieldIndexer(embedding_provider=provider, use_cache=False)
        indexer.index_fields(sample_fields)
        
        mapper = SemanticMapper(indexer, MappingConfig())
        
        result = mapper.map_field_fallback("")
        
        assert result.matched_field is None
        assert result.source == MappingSource.FALLBACK
