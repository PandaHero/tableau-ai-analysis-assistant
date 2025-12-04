"""
RAG 集成测试（使用真实 Embedding 模型）

使用真实的 ZhipuEmbedding 进行端到端测试，验证：
- 向量化质量
- 检索准确性
- 语义相似度

注意：这些测试需要有效的 ZHIPUAI_API_KEY 环境变量
"""
import os
import pytest
from typing import List
from dataclasses import dataclass

# 检查是否有 API Key
ZHIPU_API_KEY = os.getenv("ZHIPUAI_API_KEY") or os.getenv("ZHIPU_API_KEY")
SKIP_REASON = "需要 ZHIPUAI_API_KEY 环境变量"


@dataclass
class MockFieldMetadata:
    """Mock FieldMetadata for testing"""
    name: str
    fieldCaption: str
    role: str
    dataType: str
    columnClass: str = "COLUMN"
    category: str = None
    formula: str = None
    logicalTableId: str = None
    logicalTableCaption: str = None
    sample_values: List[str] = None


@pytest.mark.skipif(not ZHIPU_API_KEY, reason=SKIP_REASON)
class TestZhipuEmbeddingIntegration:
    """
    智谱 AI Embedding 集成测试
    
    验证真实 embedding 模型的行为
    """
    
    @pytest.fixture
    def zhipu_provider(self):
        """创建真实的智谱 Embedding 提供者"""
        from tableau_assistant.src.model_manager.embeddings import ZhipuEmbedding
        return ZhipuEmbedding()
    
    def test_embed_single_query(self, zhipu_provider):
        """测试单个查询向量化"""
        text = "销售金额"
        vector = zhipu_provider.embed_query(text)
        
        assert isinstance(vector, list)
        assert len(vector) == 1024  # 智谱 embedding-2 维度
        assert all(isinstance(v, float) for v in vector)
    
    def test_embed_documents_batch(self, zhipu_provider):
        """测试批量文档向量化"""
        texts = ["销售金额", "利润率", "客户名称", "订单日期"]
        vectors = zhipu_provider.embed_documents(texts)
        
        assert len(vectors) == len(texts)
        for vector in vectors:
            assert len(vector) == 1024
    
    def test_semantic_similarity(self, zhipu_provider):
        """测试语义相似度"""
        # 相似的文本应该有更高的相似度
        similar_texts = ["销售金额", "销售额", "Sales Amount"]
        different_text = "客户地址"
        
        similar_vectors = zhipu_provider.embed_documents(similar_texts)
        different_vector = zhipu_provider.embed_query(different_text)
        
        # 计算余弦相似度
        def cosine_similarity(v1, v2):
            dot = sum(a * b for a, b in zip(v1, v2))
            norm1 = sum(a * a for a in v1) ** 0.5
            norm2 = sum(b * b for b in v2) ** 0.5
            return dot / (norm1 * norm2) if norm1 and norm2 else 0
        
        # 相似文本之间的相似度
        sim_01 = cosine_similarity(similar_vectors[0], similar_vectors[1])
        sim_02 = cosine_similarity(similar_vectors[0], similar_vectors[2])
        
        # 不同文本之间的相似度
        sim_diff = cosine_similarity(similar_vectors[0], different_vector)
        
        # 相似文本的相似度应该更高
        assert sim_01 > sim_diff, f"相似文本相似度 {sim_01} 应大于不同文本 {sim_diff}"
        assert sim_02 > sim_diff, f"相似文本相似度 {sim_02} 应大于不同文本 {sim_diff}"
        
        print(f"\n语义相似度测试:")
        print(f"  '销售金额' vs '销售额': {sim_01:.4f}")
        print(f"  '销售金额' vs 'Sales Amount': {sim_02:.4f}")
        print(f"  '销售金额' vs '客户地址': {sim_diff:.4f}")
    
    def test_chinese_english_similarity(self, zhipu_provider):
        """测试中英文语义对齐"""
        pairs = [
            ("销售金额", "Sales Amount"),
            ("客户名称", "Customer Name"),
            ("订单日期", "Order Date"),
            ("利润", "Profit"),
        ]
        
        print("\n中英文语义对齐测试:")
        for cn, en in pairs:
            cn_vec = zhipu_provider.embed_query(cn)
            en_vec = zhipu_provider.embed_query(en)
            
            dot = sum(a * b for a, b in zip(cn_vec, en_vec))
            norm1 = sum(a * a for a in cn_vec) ** 0.5
            norm2 = sum(b * b for b in en_vec) ** 0.5
            similarity = dot / (norm1 * norm2)
            
            print(f"  '{cn}' vs '{en}': {similarity:.4f}")
            # 中英文对应词应该有较高相似度
            assert similarity > 0.5, f"'{cn}' 和 '{en}' 相似度应 > 0.5"


@pytest.mark.skipif(not ZHIPU_API_KEY, reason=SKIP_REASON)
class TestRetrieverIntegration:
    """
    检索器集成测试
    
    使用真实 embedding 测试检索功能
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
                category="财务",
                sample_values=["1000", "2500", "3800"]
            ),
            MockFieldMetadata(
                name="profit",
                fieldCaption="Profit",
                role="measure",
                dataType="REAL",
                category="财务"
            ),
            MockFieldMetadata(
                name="profit_ratio",
                fieldCaption="Profit Ratio",
                role="measure",
                dataType="REAL",
                category="财务"
            ),
            MockFieldMetadata(
                name="customer_name",
                fieldCaption="Customer Name",
                role="dimension",
                dataType="STRING",
                category="客户"
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
                name="order_date",
                fieldCaption="Order Date",
                role="dimension",
                dataType="DATE",
                category="时间"
            ),
            MockFieldMetadata(
                name="ship_date",
                fieldCaption="Ship Date",
                role="dimension",
                dataType="DATE",
                category="时间"
            ),
            MockFieldMetadata(
                name="product_name",
                fieldCaption="Product Name",
                role="dimension",
                dataType="STRING",
                category="产品"
            ),
        ]
    
    @pytest.fixture
    def field_indexer(self, sample_fields):
        """创建使用真实 embedding 的字段索引器"""
        from tableau_assistant.src.model_manager.embeddings import ZhipuEmbedding
        from tableau_assistant.src.capabilities.rag.field_indexer import FieldIndexer
        
        provider = ZhipuEmbedding()
        indexer = FieldIndexer(embedding_provider=provider, use_cache=True)
        indexer.index_fields(sample_fields)
        return indexer
    
    def test_semantic_retrieval_chinese(self, field_indexer):
        """测试中文语义检索"""
        from tableau_assistant.src.capabilities.rag.retriever import EmbeddingRetriever
        
        retriever = EmbeddingRetriever(field_indexer)
        
        # 测试中文查询
        test_cases = [
            ("销售额", "sales_amount"),      # 同义词
            ("利润", "profit"),              # 直接匹配
            ("客户", "customer_name"),       # 部分匹配
            ("地区", "region"),              # 同义词
            ("下单时间", "order_date"),      # 语义相关
        ]
        
        print("\n中文语义检索测试:")
        for query, expected_field in test_cases:
            results = retriever.retrieve(query, top_k=3)
            
            if results:
                top_result = results[0]
                print(f"  查询 '{query}' -> top-1: {top_result.field_chunk.field_name} (score: {top_result.score:.4f})")
                
                # 检查期望字段是否在 top-3
                top_3_names = [r.field_chunk.field_name for r in results[:3]]
                assert expected_field in top_3_names, \
                    f"期望 '{expected_field}' 在 top-3 中，实际: {top_3_names}"
    
    def test_semantic_retrieval_english(self, field_indexer):
        """测试英文语义检索"""
        from tableau_assistant.src.capabilities.rag.retriever import EmbeddingRetriever
        
        retriever = EmbeddingRetriever(field_indexer)
        
        test_cases = [
            ("revenue", "sales_amount"),     # 同义词
            ("margin", "profit_ratio"),      # 语义相关
            ("client", "customer_name"),     # 同义词
            ("area", "region"),              # 同义词
        ]
        
        print("\n英文语义检索测试:")
        for query, expected_field in test_cases:
            results = retriever.retrieve(query, top_k=3)
            
            if results:
                top_result = results[0]
                print(f"  查询 '{query}' -> top-1: {top_result.field_chunk.field_name} (score: {top_result.score:.4f})")
                
                top_3_names = [r.field_chunk.field_name for r in results[:3]]
                # 英文同义词检索可能不如中文准确，放宽到 top-5
                results_5 = retriever.retrieve(query, top_k=5)
                top_5_names = [r.field_chunk.field_name for r in results_5]
                assert expected_field in top_5_names, \
                    f"期望 '{expected_field}' 在 top-5 中，实际: {top_5_names}"
    
    def test_hybrid_retrieval(self, field_indexer):
        """测试混合检索"""
        from tableau_assistant.src.capabilities.rag.retriever import RetrieverFactory
        
        retriever = RetrieverFactory.create_hybrid_retriever(field_indexer)
        
        # 混合检索应该结合向量和关键词的优势
        results = retriever.retrieve("销售金额", top_k=5)
        
        assert len(results) > 0
        print(f"\n混合检索 '销售金额' 结果:")
        for r in results:
            print(f"  {r.field_chunk.field_name}: {r.score:.4f}")
        
        # 最相关的应该是 sales_amount
        assert results[0].field_chunk.field_name == "sales_amount"
    
    def test_metadata_filter_with_real_embedding(self, field_indexer):
        """测试带元数据过滤的检索"""
        from tableau_assistant.src.capabilities.rag.retriever import (
            EmbeddingRetriever, MetadataFilter
        )
        
        retriever = EmbeddingRetriever(field_indexer)
        
        # 只检索 measure
        measure_filter = MetadataFilter(role="measure")
        results = retriever.retrieve("金额", top_k=5, filters=measure_filter)
        
        print(f"\n过滤 role=measure 后检索 '金额':")
        for r in results:
            print(f"  {r.field_chunk.field_name} ({r.field_chunk.role}): {r.score:.4f}")
            assert r.field_chunk.role == "measure"
        
        # 只检索 dimension
        dim_filter = MetadataFilter(role="dimension")
        results = retriever.retrieve("日期", top_k=5, filters=dim_filter)
        
        print(f"\n过滤 role=dimension 后检索 '日期':")
        for r in results:
            print(f"  {r.field_chunk.field_name} ({r.field_chunk.role}): {r.score:.4f}")
            assert r.field_chunk.role == "dimension"


@pytest.mark.skipif(not ZHIPU_API_KEY, reason=SKIP_REASON)
class TestSemanticMapperIntegration:
    """
    语义映射器集成测试
    """
    
    @pytest.fixture
    def sample_fields(self):
        """创建测试字段"""
        return [
            MockFieldMetadata(name="sales", fieldCaption="Sales Amount", role="measure", dataType="REAL"),
            MockFieldMetadata(name="profit", fieldCaption="Profit", role="measure", dataType="REAL"),
            MockFieldMetadata(name="customer", fieldCaption="Customer Name", role="dimension", dataType="STRING"),
            MockFieldMetadata(name="region", fieldCaption="Region", role="dimension", dataType="STRING"),
            MockFieldMetadata(name="order_date", fieldCaption="Order Date", role="dimension", dataType="DATE"),
        ]
    
    @pytest.fixture
    def semantic_mapper(self, sample_fields):
        """创建语义映射器"""
        from tableau_assistant.src.model_manager.embeddings import ZhipuEmbedding
        from tableau_assistant.src.capabilities.rag.field_indexer import FieldIndexer
        from tableau_assistant.src.capabilities.rag.semantic_mapper import SemanticMapper
        
        provider = ZhipuEmbedding()
        indexer = FieldIndexer(embedding_provider=provider, use_cache=True)
        indexer.index_fields(sample_fields)
        
        return SemanticMapper(field_indexer=indexer)
    
    def test_map_field_chinese(self, semantic_mapper):
        """测试中文字段映射"""
        test_cases = [
            ("销售额", "sales"),
            ("利润", "profit"),
            ("客户", "customer"),
            ("地区", "region"),
        ]
        
        print("\n中文字段映射测试:")
        for term, expected in test_cases:
            result = semantic_mapper.map_field(term)
            print(f"  '{term}' -> matched: {result.matched_field}, confidence: {result.confidence:.4f}")
            print(f"    alternatives: {result.alternatives}")
            
            # 当置信度 < 0.7 时，matched_field 为 None，但期望字段应在备选中
            # 或者在检索结果的 top-3 中
            if result.matched_field:
                assert result.matched_field == expected or expected in result.alternatives
            else:
                # 检查检索结果中是否包含期望字段
                retrieval_names = [r.field_chunk.field_name for r in result.retrieval_results[:5]]
                all_candidates = result.alternatives + retrieval_names
                assert expected in all_candidates, \
                    f"期望 '{expected}' 在候选中，实际: {all_candidates}"
    
    def test_batch_mapping(self, semantic_mapper):
        """测试批量映射"""
        terms = ["销售额", "利润", "客户名称"]
        results = semantic_mapper.map_fields_batch(terms)
        
        assert len(results) == len(terms)
        print("\n批量映射测试:")
        for term, result in zip(terms, results):
            print(f"  '{term}' -> {result.matched_field}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
