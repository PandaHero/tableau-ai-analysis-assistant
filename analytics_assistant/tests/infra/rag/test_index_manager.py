"""IndexManager 属性测试

**Feature: rag-service-refactor**

测试 IndexManager 的正确性属性：
- Property 3: 索引创建-获取往返
- Property 4: 索引删除后不可获取
- Property 5: 索引元数据完整性
- Property 6: 增量添加文档
- Property 7: 增量更新文档
- Property 8: 文档删除
- Property 9: 文档哈希跟踪
"""

import pytest
from hypothesis import given, strategies as st, settings
from datetime import datetime

from analytics_assistant.src.infra.rag.index_manager import IndexManager
from analytics_assistant.src.infra.rag.schemas import (
    IndexConfig,
    IndexDocument,
    IndexInfo,
    IndexStatus,
    IndexBackend,
)


# ═══════════════════════════════════════════════════════════════════════════
# 测试 Fixtures
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def index_manager():
    """创建测试用的 IndexManager"""
    # 使用唯一的命名空间避免测试间干扰
    import uuid
    namespace = f"test_index_registry_{uuid.uuid4().hex[:8]}"
    return IndexManager(registry_namespace=namespace)


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
        IndexDocument(id="doc1", content="销售额是衡量业绩的指标", metadata={"role": "measure"}),
        IndexDocument(id="doc2", content="产品名称是商品的标识", metadata={"role": "dimension"}),
        IndexDocument(id="doc3", content="订单日期是交易发生的时间", metadata={"role": "dimension"}),
    ]


# ═══════════════════════════════════════════════════════════════════════════
# 单元测试
# ═══════════════════════════════════════════════════════════════════════════

class TestIndexManagerUnit:
    """IndexManager 单元测试"""
    
    def test_create_index_success(self, index_manager, sample_config, sample_documents):
        """测试创建索引成功"""
        info = index_manager.create_index(
            name="test_index_unit",
            config=sample_config,
            documents=sample_documents,
        )
        
        assert info.name == "test_index_unit"
        assert info.status == IndexStatus.READY
        assert info.document_count == len(sample_documents)
        
        # 清理
        index_manager.delete_index("test_index_unit")
    
    def test_create_duplicate_index_raises(self, index_manager, sample_config, sample_documents):
        """测试创建重复索引抛出异常"""
        from analytics_assistant.src.infra.rag.exceptions import IndexExistsError
        
        index_manager.create_index(
            name="test_duplicate",
            config=sample_config,
            documents=sample_documents,
        )
        
        with pytest.raises(IndexExistsError):
            index_manager.create_index(
                name="test_duplicate",
                config=sample_config,
                documents=sample_documents,
            )
        
        # 清理
        index_manager.delete_index("test_duplicate")
    
    def test_delete_nonexistent_index_returns_false(self, index_manager):
        """测试删除不存在的索引返回 False"""
        result = index_manager.delete_index("nonexistent_index")
        assert result is False
    
    def test_get_nonexistent_index_returns_none(self, index_manager):
        """测试获取不存在的索引返回 None"""
        result = index_manager.get_index("nonexistent_index")
        assert result is None
    
    def test_list_indexes_empty(self, index_manager):
        """测试空索引列表"""
        indexes = index_manager.list_indexes()
        assert isinstance(indexes, list)


# ═══════════════════════════════════════════════════════════════════════════
# 属性测试
# ═══════════════════════════════════════════════════════════════════════════

class TestIndexManagerProperties:
    """IndexManager 属性测试"""
    
    @settings(max_examples=5, deadline=120000)
    @given(st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz0123456789_"))
    def test_property_3_create_get_roundtrip(self, index_name):
        """**Feature: rag-service-refactor, Property 3: 索引创建-获取往返**
        
        *For any* 索引名称和配置，创建索引后调用 get_index(name) 应该返回非空结果，
        且索引信息应该出现在 list_indexes() 结果中。
        
        **Validates: Requirements 2.2, 2.4, 2.6**
        """
        import uuid
        from analytics_assistant.src.infra.config import get_config
        
        namespace = f"test_prop3_{uuid.uuid4().hex[:8]}"
        manager = IndexManager(registry_namespace=namespace)
        
        # 从配置文件读取索引目录
        app_config = get_config()
        vector_config = app_config.config.get("vector_storage", {})
        index_dir = vector_config.get("index_dir", "data/indexes")
        
        config = IndexConfig(
            backend=IndexBackend.FAISS,
            persist_directory=index_dir,
        )
        
        # 使用唯一名称避免冲突
        unique_name = f"{index_name}_{uuid.uuid4().hex[:8]}"
        
        try:
            # 创建索引
            manager.create_index(name=unique_name, config=config, documents=[])
            
            # 验证：get_index 返回非空
            retriever = manager.get_index(unique_name)
            assert retriever is not None, f"get_index('{unique_name}') 应返回非空"
            
            # 验证：出现在 list_indexes 中
            indexes = manager.list_indexes()
            names = [idx.name for idx in indexes]
            assert unique_name in names, f"'{unique_name}' 应出现在 list_indexes() 中"
            
        finally:
            # 清理
            manager.delete_index(unique_name)
    
    @settings(max_examples=5, deadline=120000)
    @given(st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz0123456789_"))
    def test_property_4_delete_then_not_found(self, index_name):
        """**Feature: rag-service-refactor, Property 4: 索引删除后不可获取**
        
        *For any* 已创建的索引，删除后调用 get_index(name) 应该返回空结果，
        且索引信息不应该出现在 list_indexes() 结果中。
        
        **Validates: Requirements 2.3, 2.7**
        """
        import uuid
        from analytics_assistant.src.infra.config import get_config
        
        namespace = f"test_prop4_{uuid.uuid4().hex[:8]}"
        manager = IndexManager(registry_namespace=namespace)
        
        # 从配置文件读取索引目录
        app_config = get_config()
        vector_config = app_config.config.get("vector_storage", {})
        index_dir = vector_config.get("index_dir", "data/indexes")
        
        config = IndexConfig(
            backend=IndexBackend.FAISS,
            persist_directory=index_dir,
        )
        
        unique_name = f"{index_name}_{uuid.uuid4().hex[:8]}"
        
        # 创建索引
        manager.create_index(name=unique_name, config=config, documents=[])
        
        # 删除索引
        deleted = manager.delete_index(unique_name)
        assert deleted is True, "删除应成功"
        
        # 验证：get_index 返回 None
        retriever = manager.get_index(unique_name)
        assert retriever is None, f"删除后 get_index('{unique_name}') 应返回 None"
        
        # 验证：不在 list_indexes 中
        indexes = manager.list_indexes()
        names = [idx.name for idx in indexes]
        assert unique_name not in names, f"删除后 '{unique_name}' 不应出现在 list_indexes() 中"
    
    def test_property_5_index_info_completeness(self, index_manager, sample_config, sample_documents):
        """**Feature: rag-service-refactor, Property 5: 索引元数据完整性**
        
        *For any* 创建的索引，其 IndexInfo 应该包含所有必需字段：
        name、config、status、document_count、created_at、updated_at。
        
        **Validates: Requirements 2.5**
        """
        import uuid
        unique_name = f"test_prop5_{uuid.uuid4().hex[:8]}"
        
        try:
            info = index_manager.create_index(
                name=unique_name,
                config=sample_config,
                documents=sample_documents,
            )
            
            # 验证所有必需字段
            assert info.name == unique_name
            assert info.config is not None
            assert info.status == IndexStatus.READY
            assert info.document_count == len(sample_documents)
            assert isinstance(info.created_at, datetime)
            assert isinstance(info.updated_at, datetime)
            
        finally:
            index_manager.delete_index(unique_name)
    
    def test_property_9_document_hash_tracking(self, index_manager, sample_config, sample_documents):
        """**Feature: rag-service-refactor, Property 9: 文档哈希跟踪**
        
        *For any* 添加到索引的文档，应该能够通过文档 ID 查询到其内容哈希值。
        
        **Validates: Requirements 3.6**
        """
        import uuid
        unique_name = f"test_prop9_{uuid.uuid4().hex[:8]}"
        
        try:
            index_manager.create_index(
                name=unique_name,
                config=sample_config,
                documents=sample_documents,
            )
            
            # 验证每个文档的哈希都可以查询到
            for doc in sample_documents:
                hash_data = index_manager.get_document_hash(unique_name, doc.id)
                assert hash_data is not None, f"文档 '{doc.id}' 的哈希应存在"
                assert "content" in hash_data, "应包含 content 哈希"
                assert "metadata" in hash_data, "应包含 metadata 哈希"
                assert hash_data["content"] == doc.content_hash
                assert hash_data["metadata"] == doc.metadata_hash
            
        finally:
            index_manager.delete_index(unique_name)


# ═══════════════════════════════════════════════════════════════════════════
# 运行测试
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
