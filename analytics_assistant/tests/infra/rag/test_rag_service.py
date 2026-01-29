"""RAGService 属性测试

**Feature: rag-service-refactor**

测试 RAGService 的正确性属性：
- Property 12: RAG 服务单例
"""

import pytest

from analytics_assistant.src.infra.rag.service import RAGService, get_rag_service
from analytics_assistant.src.infra.rag.embedding_service import EmbeddingService
from analytics_assistant.src.infra.rag.index_manager import IndexManager
from analytics_assistant.src.infra.rag.retrieval_service import RetrievalService


# ═══════════════════════════════════════════════════════════════════════════
# 测试 Fixtures
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def reset_singleton():
    """每个测试前后重置单例"""
    RAGService.reset_instance()
    yield
    RAGService.reset_instance()


# ═══════════════════════════════════════════════════════════════════════════
# 单元测试
# ═══════════════════════════════════════════════════════════════════════════

class TestRAGServiceUnit:
    """RAGService 单元测试"""
    
    def test_get_instance_returns_rag_service(self):
        """测试 get_instance 返回 RAGService 实例"""
        service = RAGService.get_instance()
        assert isinstance(service, RAGService)
    
    def test_get_rag_service_returns_rag_service(self):
        """测试 get_rag_service 返回 RAGService 实例"""
        service = get_rag_service()
        assert isinstance(service, RAGService)
    
    def test_embedding_property_returns_embedding_service(self):
        """测试 embedding 属性返回 EmbeddingService"""
        service = get_rag_service()
        assert isinstance(service.embedding, EmbeddingService)
    
    def test_index_property_returns_index_manager(self):
        """测试 index 属性返回 IndexManager"""
        service = get_rag_service()
        assert isinstance(service.index, IndexManager)
    
    def test_retrieval_property_returns_retrieval_service(self):
        """测试 retrieval 属性返回 RetrievalService"""
        service = get_rag_service()
        assert isinstance(service.retrieval, RetrievalService)
    
    def test_reset_instance_clears_singleton(self):
        """测试 reset_instance 清除单例"""
        service1 = get_rag_service()
        RAGService.reset_instance()
        service2 = get_rag_service()
        
        # 重置后应该是不同的实例
        assert service1 is not service2


# ═══════════════════════════════════════════════════════════════════════════
# 属性测试
# ═══════════════════════════════════════════════════════════════════════════

class TestRAGServiceProperties:
    """RAGService 属性测试"""
    
    def test_property_12_singleton(self):
        """**Feature: rag-service-refactor, Property 12: RAG 服务单例**
        
        *For any* 多次调用 get_rag_service()，应该返回同一个实例（对象 ID 相同）。
        
        **Validates: Requirements 5.1**
        """
        # 多次调用 get_rag_service()
        service1 = get_rag_service()
        service2 = get_rag_service()
        service3 = RAGService.get_instance()
        
        # 验证是同一个实例
        assert service1 is service2, "get_rag_service() 应返回同一实例"
        assert service2 is service3, "get_instance() 应返回同一实例"
        assert id(service1) == id(service2) == id(service3), "对象 ID 应相同"
    
    def test_property_12_singleton_with_multiple_calls(self):
        """**Feature: rag-service-refactor, Property 12: RAG 服务单例（多次调用）**
        
        *For any* 多次调用，子服务也应该是同一实例。
        
        **Validates: Requirements 5.1**
        """
        service = get_rag_service()
        
        # 多次访问子服务
        embedding1 = service.embedding
        embedding2 = service.embedding
        
        index1 = service.index
        index2 = service.index
        
        retrieval1 = service.retrieval
        retrieval2 = service.retrieval
        
        # 验证子服务也是同一实例（延迟初始化后缓存）
        assert embedding1 is embedding2, "embedding 应返回同一实例"
        assert index1 is index2, "index 应返回同一实例"
        assert retrieval1 is retrieval2, "retrieval 应返回同一实例"


# ═══════════════════════════════════════════════════════════════════════════
# 运行测试
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
