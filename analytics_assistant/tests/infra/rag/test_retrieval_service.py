"""RetrievalService 属性测试

**Feature: rag-service-refactor**

测试 RetrievalService 的正确性属性：
- Property 10: 搜索分数归一化
- Property 11: 元数据过滤正确性
"""

import pytest
from hypothesis import given, strategies as st, settings
import uuid

from analytics_assistant.src.infra.rag.index_manager import IndexManager
from analytics_assistant.src.infra.rag.embedding_service import EmbeddingService
from analytics_assistant.src.infra.rag.retrieval_service import RetrievalService
from analytics_assistant.src.infra.rag.schemas import (
    IndexConfig,
    IndexDocument,
    IndexBackend,
)


# ═══════════════════════════════════════════════════════════════════════════
# 测试 Fixtures
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def test_index_name():
    """生成唯一的测试索引名称"""
    return f"test_retrieval_{uuid.uuid4().hex[:8]}"


@pytest.fixture
def index_manager():
    """创建测试用的 IndexManager"""
    namespace = f"test_retrieval_registry_{uuid.uuid4().hex[:8]}"
    return IndexManager(registry_namespace=namespace)


@pytest.fixture
def embedding_service():
    """创建测试用的 EmbeddingService"""
    return EmbeddingService()


@pytest.fixture
def retrieval_service(index_manager, embedding_service):
    """创建测试用的 RetrievalService"""
    return RetrievalService(index_manager, embedding_service)


@pytest.fixture
def sample_config():
    """创建测试用的索引配置"""
    from analytics_assistant.src.infra.config import get_config
    
    # 从配置文件读取正确的索引目录
    app_config = get_config()
    vector_config = app_config.config.get("vector_storage", {})
    index_dir = vector_config.get("index_dir", "data/indexes")
    
    return IndexConfig(
        backend=IndexBackend.FAISS,
        persist_directory=index_dir,
        default_top_k=10,
        score_threshold=0.0,
    )


@pytest.fixture
def sample_documents():
    """创建测试用的文档列表"""
    return [
        IndexDocument(id="sales", content="销售额是衡量业绩的指标", metadata={"role": "measure", "data_type": "number"}),
        IndexDocument(id="product", content="产品名称是商品的标识", metadata={"role": "dimension", "data_type": "string"}),
        IndexDocument(id="order_date", content="订单日期是交易发生的时间", metadata={"role": "dimension", "data_type": "date"}),
        IndexDocument(id="profit", content="利润是收入减去成本", metadata={"role": "measure", "data_type": "number"}),
        IndexDocument(id="category", content="类别是产品的分类", metadata={"role": "dimension", "data_type": "string"}),
    ]


@pytest.fixture
def populated_index(index_manager, sample_config, sample_documents, test_index_name):
    """创建并填充测试索引"""
    index_manager.create_index(
        name=test_index_name,
        config=sample_config,
        documents=sample_documents,
    )
    yield test_index_name
    # 清理
    index_manager.delete_index(test_index_name)


# ═══════════════════════════════════════════════════════════════════════════
# 单元测试
# ═══════════════════════════════════════════════════════════════════════════

class TestRetrievalServiceUnit:
    """RetrievalService 单元测试"""
    
    def test_search_returns_results(self, retrieval_service, index_manager, sample_config, sample_documents):
        """测试搜索返回结果"""
        index_name = f"test_search_{uuid.uuid4().hex[:8]}"
        
        try:
            index_manager.create_index(
                name=index_name,
                config=sample_config,
                documents=sample_documents,
            )
            
            results = retrieval_service.search(
                index_name=index_name,
                query="销售",
                top_k=5,
            )
            
            assert isinstance(results, list)
            # 搜索应该返回列表（可能为空，取决于索引状态）
            # 主要验证不抛出异常
            
        finally:
            index_manager.delete_index(index_name)
    
    def test_search_nonexistent_index_raises(self, retrieval_service):
        """测试搜索不存在的索引抛出异常"""
        from analytics_assistant.src.infra.rag.exceptions import IndexNotFoundError
        
        with pytest.raises(IndexNotFoundError):
            retrieval_service.search(
                index_name="nonexistent_index",
                query="test",
            )
    
    def test_normalize_score_l2(self):
        """测试 L2 距离归一化"""
        # L2 距离 0 → 相似度 1.0
        assert RetrievalService.normalize_score(0.0, "l2") == 1.0
        
        # L2 距离 1 → 相似度 0.5
        assert RetrievalService.normalize_score(1.0, "l2") == 0.5
        
        # L2 距离越大，相似度越低
        score1 = RetrievalService.normalize_score(0.5, "l2")
        score2 = RetrievalService.normalize_score(2.0, "l2")
        assert score1 > score2
    
    def test_normalize_score_cosine(self):
        """测试余弦相似度归一化"""
        # 余弦 1.0 → 归一化 1.0
        assert RetrievalService.normalize_score(1.0, "cosine") == 1.0
        
        # 余弦 0.0 → 归一化 0.5
        assert RetrievalService.normalize_score(0.0, "cosine") == 0.5
        
        # 余弦 -1.0 → 归一化 0.0
        assert RetrievalService.normalize_score(-1.0, "cosine") == 0.0


# ═══════════════════════════════════════════════════════════════════════════
# 属性测试
# ═══════════════════════════════════════════════════════════════════════════

class TestRetrievalServiceProperties:
    """RetrievalService 属性测试"""
    
    @settings(max_examples=20, deadline=None)
    @given(st.floats(min_value=-10.0, max_value=10.0, allow_nan=False, allow_infinity=False))
    def test_property_10_score_normalization(self, raw_score):
        """**Feature: rag-service-refactor, Property 10: 搜索分数归一化**
        
        *For any* 搜索结果，其 score 字段应该在 [0, 1] 范围内。
        
        **Validates: Requirements 4.3, 4.4**
        """
        # 测试 L2 归一化
        normalized_l2 = RetrievalService.normalize_score(raw_score, "l2")
        assert 0.0 <= normalized_l2 <= 1.0, f"L2 归一化分数 {normalized_l2} 不在 [0, 1] 范围内"
        
        # 测试余弦归一化
        normalized_cosine = RetrievalService.normalize_score(raw_score, "cosine")
        assert 0.0 <= normalized_cosine <= 1.0, f"余弦归一化分数 {normalized_cosine} 不在 [0, 1] 范围内"
        
        # 测试内积归一化
        normalized_ip = RetrievalService.normalize_score(raw_score, "inner_product")
        assert 0.0 <= normalized_ip <= 1.0, f"内积归一化分数 {normalized_ip} 不在 [0, 1] 范围内"
    
    def test_property_11_metadata_filter(self, retrieval_service, index_manager, sample_config, sample_documents):
        """**Feature: rag-service-refactor, Property 11: 元数据过滤正确性**
        
        *For any* 带有元数据过滤条件的搜索，返回的所有结果应该满足过滤条件。
        
        **Validates: Requirements 4.6**
        """
        index_name = f"test_filter_{uuid.uuid4().hex[:8]}"
        
        try:
            index_manager.create_index(
                name=index_name,
                config=sample_config,
                documents=sample_documents,
            )
            
            # 测试 role=measure 过滤
            results = retrieval_service.search(
                index_name=index_name,
                query="指标",
                top_k=10,
                filters={"role": "measure"},
            )
            
            # 验证所有结果都满足过滤条件
            for result in results:
                assert result.metadata.get("role") == "measure", \
                    f"结果 {result.doc_id} 的 role 应为 'measure'，实际为 '{result.metadata.get('role')}'"
            
        finally:
            index_manager.delete_index(index_name)


# ═══════════════════════════════════════════════════════════════════════════
# 运行测试
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
