# -*- coding: utf-8 -*-
"""
VectorIndexManager 单元测试
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest
from unittest.mock import Mock, MagicMock, patch
from src.infra.rag.vector_index_manager import (
    VectorIndexManager,
    IndexConfig,
)
from src.infra.rag.models import FieldChunk, RetrievalSource


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


class TestIndexConfig:
    """测试 IndexConfig"""
    
    def test_default_config(self):
        """测试默认配置"""
        config = IndexConfig()
        
        assert config.max_samples == 5
        assert config.include_formula is True
        assert config.include_table_caption is True
        assert config.include_category is True
    
    def test_custom_config(self):
        """测试自定义配置"""
        config = IndexConfig(
            max_samples=3,
            include_formula=False,
            include_table_caption=False,
            include_category=False
        )
        
        assert config.max_samples == 3
        assert config.include_formula is False
        assert config.include_table_caption is False
        assert config.include_category is False


class TestVectorIndexManager:
    """测试 VectorIndexManager"""
    
    def test_initialization(self):
        """测试初始化"""
        embedding_provider = MockEmbeddingProvider()
        manager = VectorIndexManager(
            embedding_provider=embedding_provider,
            datasource_luid="test-datasource"
        )
        
        assert manager.datasource_luid == "test-datasource"
        assert manager.embedding_provider == embedding_provider
        assert manager.rag_available is True
        assert manager.field_count == 0
    
    def test_initialization_without_embedding(self):
        """测试无 Embedding 提供者的初始化"""
        # 直接传入 None 作为 embedding_provider，并且 mock _create_default_embedding_provider
        with patch.object(VectorIndexManager, '_create_default_embedding_provider', return_value=None):
            manager = VectorIndexManager()
            
            assert manager.rag_available is False
    
    def test_build_index_text(self):
        """测试构建索引文本"""
        embedding_provider = MockEmbeddingProvider()
        manager = VectorIndexManager(embedding_provider=embedding_provider)
        
        field = MockFieldMetadata(
            name="sales_amount",
            caption="销售额",
            role="measure",
            data_type="real",
            category="财务"
        )
        
        index_text = manager.build_index_text(field)
        
        assert "销售额" in index_text
        assert "measure" in index_text
        assert "real" in index_text
        assert "财务" in index_text
    
    def test_index_fields(self):
        """测试索引字段"""
        embedding_provider = MockEmbeddingProvider()
        manager = VectorIndexManager(embedding_provider=embedding_provider)
        
        fields = [
            MockFieldMetadata("sales_amount", "销售额", "measure", "real"),
            MockFieldMetadata("province", "省份", "dimension", "string"),
        ]
        
        count = manager.index_fields(fields)
        
        assert count == 2
        assert manager.field_count == 2
        assert "sales_amount" in manager._chunks
        assert "province" in manager._chunks
    
    def test_index_fields_without_rag(self):
        """测试无 RAG 时索引字段"""
        # 直接传入 None 作为 embedding_provider，并且 mock _create_default_embedding_provider
        with patch.object(VectorIndexManager, '_create_default_embedding_provider', return_value=None):
            manager = VectorIndexManager()
            
            fields = [
                MockFieldMetadata("sales_amount", "销售额"),
            ]
            
            count = manager.index_fields(fields)
            
            assert count == 0  # 无向量索引
            assert manager.field_count == 1  # 但存储了元数据
    
    def test_search(self):
        """测试搜索"""
        embedding_provider = MockEmbeddingProvider()
        manager = VectorIndexManager(embedding_provider=embedding_provider)
        
        fields = [
            MockFieldMetadata("sales_amount", "销售额", "measure", "real"),
            MockFieldMetadata("province", "省份", "dimension", "string"),
        ]
        manager.index_fields(fields)
        
        results = manager.search("销售额", top_k=1)
        
        assert len(results) <= 1
        if results:
            assert results[0].field_chunk.field_name in ["sales_amount", "province"]
            assert 0 <= results[0].score <= 1
            assert results[0].source == RetrievalSource.EMBEDDING
    
    def test_search_with_filters(self):
        """测试带过滤器的搜索"""
        embedding_provider = MockEmbeddingProvider()
        manager = VectorIndexManager(embedding_provider=embedding_provider)
        
        fields = [
            MockFieldMetadata("sales_amount", "销售额", "measure", "real", "财务"),
            MockFieldMetadata("province", "省份", "dimension", "string", "地理"),
        ]
        manager.index_fields(fields)
        
        # 按角色过滤
        results = manager.search("销售", top_k=5, role_filter="measure")
        
        for result in results:
            assert result.field_chunk.role == "measure"
        
        # 按类别过滤
        results = manager.search("省份", top_k=5, category_filter="地理")
        
        for result in results:
            assert result.field_chunk.category == "地理"
    
    def test_search_empty_index(self):
        """测试空索引搜索"""
        embedding_provider = MockEmbeddingProvider()
        manager = VectorIndexManager(embedding_provider=embedding_provider)
        
        results = manager.search("销售额")
        
        assert results == []
    
    def test_search_without_rag(self):
        """测试无 RAG 时搜索"""
        # 直接传入 None 作为 embedding_provider，并且 mock _create_default_embedding_provider
        with patch.object(VectorIndexManager, '_create_default_embedding_provider', return_value=None):
            manager = VectorIndexManager()
            
            fields = [MockFieldMetadata("sales_amount", "销售额")]
            manager.index_fields(fields)
            
            results = manager.search("销售额")
            
            assert results == []  # 无 RAG 返回空列表
    
    @pytest.mark.asyncio
    async def test_asearch(self):
        """测试异步搜索"""
        embedding_provider = MockEmbeddingProvider()
        manager = VectorIndexManager(embedding_provider=embedding_provider)
        
        fields = [
            MockFieldMetadata("sales_amount", "销售额", "measure", "real"),
        ]
        manager.index_fields(fields)
        
        results = await manager.asearch("销售额", top_k=1)
        
        assert len(results) <= 1
    
    def test_get_chunk(self):
        """测试获取字段分块"""
        embedding_provider = MockEmbeddingProvider()
        manager = VectorIndexManager(embedding_provider=embedding_provider)
        
        fields = [MockFieldMetadata("sales_amount", "销售额")]
        manager.index_fields(fields)
        
        chunk = manager.get_chunk("sales_amount")
        
        assert chunk is not None
        assert chunk.field_name == "sales_amount"
        assert chunk.field_caption == "销售额"
    
    def test_get_all_chunks(self):
        """测试获取所有字段分块"""
        embedding_provider = MockEmbeddingProvider()
        manager = VectorIndexManager(embedding_provider=embedding_provider)
        
        fields = [
            MockFieldMetadata("sales_amount", "销售额"),
            MockFieldMetadata("province", "省份"),
        ]
        manager.index_fields(fields)
        
        chunks = manager.get_all_chunks()
        
        assert len(chunks) == 2
        assert all(isinstance(c, FieldChunk) for c in chunks)
    
    def test_incremental_update(self):
        """测试增量更新"""
        embedding_provider = MockEmbeddingProvider()
        manager = VectorIndexManager(embedding_provider=embedding_provider)
        
        # 初始索引
        fields = [
            MockFieldMetadata("sales_amount", "销售额"),
        ]
        manager.index_fields(fields)
        
        assert manager.field_count == 1
        
        # 增量更新（添加新字段）
        fields = [
            MockFieldMetadata("sales_amount", "销售额"),
            MockFieldMetadata("province", "省份"),
        ]
        count = manager.index_fields(fields)
        
        assert count == 2
        assert manager.field_count == 2
    
    def test_force_rebuild(self):
        """测试强制重建索引"""
        embedding_provider = MockEmbeddingProvider()
        manager = VectorIndexManager(embedding_provider=embedding_provider)
        
        fields = [MockFieldMetadata("sales_amount", "销售额")]
        manager.index_fields(fields)
        
        # 强制重建
        count = manager.index_fields(fields, force_rebuild=True)
        
        assert count == 1
    
    def test_export_and_restore_cache(self):
        """测试导出和恢复缓存"""
        embedding_provider = MockEmbeddingProvider()
        manager = VectorIndexManager(embedding_provider=embedding_provider)
        
        fields = [MockFieldMetadata("sales_amount", "销售额")]
        manager.index_fields(fields)
        
        # 导出
        cache_data = manager.export_for_cache()
        
        assert "metadata_hash" in cache_data
        assert "field_names" in cache_data
        assert "chunks" in cache_data
        assert "vectors" in cache_data
        
        # 创建新管理器并恢复
        new_manager = VectorIndexManager(embedding_provider=embedding_provider)
        success = new_manager.restore_from_cache(cache_data)
        
        assert success is True
        assert new_manager.field_count == 1
        assert new_manager.get_chunk("sales_amount") is not None
    
    def test_save_and_load_index(self, tmp_path):
        """测试保存和加载索引"""
        embedding_provider = MockEmbeddingProvider()
        manager = VectorIndexManager(
            embedding_provider=embedding_provider,
            datasource_luid="test-datasource",
            index_dir=str(tmp_path)
        )
        
        fields = [MockFieldMetadata("sales_amount", "销售额")]
        manager.index_fields(fields)
        
        # 保存
        success = manager.save_index()
        assert success is True
        
        # 加载
        new_manager = VectorIndexManager(
            embedding_provider=embedding_provider,
            datasource_luid="test-datasource",
            index_dir=str(tmp_path)
        )
        success = new_manager.load_index()
        
        assert success is True
        assert new_manager.field_count == 1
        assert new_manager.get_chunk("sales_amount") is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
