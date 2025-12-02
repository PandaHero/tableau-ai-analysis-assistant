"""
字段索引器属性测试

**Feature: rag-enhancement, Property 1: 索引完整性**
**Validates: Requirements 1.1, 1.2**

测试字段索引器的索引完整性和持久化功能。
"""
import pytest
import tempfile
import os
from hypothesis import given, strategies as st, settings
from dataclasses import dataclass
from typing import List, Optional

from tableau_assistant.src.capabilities.rag.field_indexer import FieldIndexer, IndexConfig
from tableau_assistant.src.capabilities.rag.embeddings import MockEmbedding
from tableau_assistant.src.capabilities.rag.models import FieldChunk


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


class TestFieldIndexerBasic:
    """基本功能测试"""
    
    @pytest.fixture
    def indexer(self):
        """创建测试索引器"""
        provider = MockEmbedding(dimensions=128)
        return FieldIndexer(
            embedding_provider=provider,
            use_cache=False
        )
    
    @pytest.fixture
    def sample_fields(self):
        """创建测试字段"""
        return [
            MockFieldMetadata(
                name="sales",
                fieldCaption="Sales Amount",
                role="measure",
                dataType="REAL",
                category="财务",
                sample_values=["100", "200", "300"]
            ),
            MockFieldMetadata(
                name="region",
                fieldCaption="Region",
                role="dimension",
                dataType="STRING",
                category="地理",
                logicalTableCaption="订单表",
                sample_values=["华东", "华北", "华南"]
            ),
            MockFieldMetadata(
                name="order_date",
                fieldCaption="Order Date",
                role="dimension",
                dataType="DATE",
                category="时间"
            ),
        ]
    
    def test_index_fields_returns_count(self, indexer, sample_fields):
        """测试索引字段返回正确数量"""
        count = indexer.index_fields(sample_fields)
        assert count == len(sample_fields)
    
    def test_field_count_property(self, indexer, sample_fields):
        """测试 field_count 属性"""
        indexer.index_fields(sample_fields)
        assert indexer.field_count == len(sample_fields)
    
    def test_get_chunk_returns_correct_chunk(self, indexer, sample_fields):
        """测试获取字段分块"""
        indexer.index_fields(sample_fields)
        
        chunk = indexer.get_chunk("sales")
        assert chunk is not None
        assert chunk.field_name == "sales"
        assert chunk.field_caption == "Sales Amount"
        assert chunk.role == "measure"
    
    def test_get_all_chunks(self, indexer, sample_fields):
        """测试获取所有字段分块"""
        indexer.index_fields(sample_fields)
        
        chunks = indexer.get_all_chunks()
        assert len(chunks) == len(sample_fields)
        
        names = {c.field_name for c in chunks}
        expected_names = {f.name for f in sample_fields}
        assert names == expected_names


class TestIndexCompleteness:
    """
    索引完整性测试
    
    **Feature: rag-enhancement, Property 1: 索引完整性**
    **Validates: Requirements 1.1, 1.2**
    """
    
    @pytest.fixture
    def indexer(self):
        """创建测试索引器"""
        provider = MockEmbedding(dimensions=128)
        return FieldIndexer(
            embedding_provider=provider,
            use_cache=False
        )
    
    @given(st.lists(
        st.fixed_dictionaries({
            "name": st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz_"),
            "caption": st.text(min_size=1, max_size=50),
            "role": st.sampled_from(["dimension", "measure"]),
            "dataType": st.sampled_from(["STRING", "INTEGER", "REAL", "DATE"]),
        }),
        min_size=1,
        max_size=20,
        unique_by=lambda x: x["name"]
    ))
    @settings(max_examples=30, deadline=None)
    def test_all_fields_indexed_property(self, field_dicts):
        """
        属性测试：所有输入字段都被索引
        
        **Feature: rag-enhancement, Property 1: 索引完整性**
        """
        provider = MockEmbedding(dimensions=64)
        indexer = FieldIndexer(embedding_provider=provider, use_cache=False)
        
        fields = [
            MockFieldMetadata(
                name=d["name"],
                fieldCaption=d["caption"],
                role=d["role"],
                dataType=d["dataType"]
            )
            for d in field_dicts
        ]
        
        count = indexer.index_fields(fields)
        
        # 验证索引数量
        assert count == len(fields)
        assert indexer.field_count == len(fields)
        
        # 验证每个字段都被索引
        for field in fields:
            chunk = indexer.get_chunk(field.name)
            assert chunk is not None, f"字段 {field.name} 未被索引"
            assert chunk.field_caption == field.fieldCaption
            assert chunk.role == field.role
    
    def test_index_text_contains_required_info(self):
        """测试索引文本包含必需信息"""
        provider = MockEmbedding(dimensions=64)
        indexer = FieldIndexer(embedding_provider=provider, use_cache=False)
        
        field = MockFieldMetadata(
            name="test_field",
            fieldCaption="Test Field Caption",
            role="dimension",
            dataType="STRING",
            category="测试类别",
            logicalTableCaption="测试表",
            sample_values=["值1", "值2", "值3"]
        )
        
        index_text = indexer.build_index_text(field)
        
        # 验证必需信息
        assert "Test Field Caption" in index_text
        assert "dimension" in index_text
        assert "STRING" in index_text
        
        # 验证可选信息
        assert "测试类别" in index_text
        assert "测试表" in index_text
        assert "值1" in index_text


class TestIndexPersistence:
    """
    索引持久化测试
    
    **Feature: rag-enhancement, Property 2: 索引持久化往返**
    **Validates: Requirements 1.5, 6.3**
    """
    
    def test_save_and_load_index(self):
        """测试保存和加载索引"""
        with tempfile.TemporaryDirectory() as tmpdir:
            provider = MockEmbedding(dimensions=64)
            indexer = FieldIndexer(
                embedding_provider=provider,
                index_dir=tmpdir,
                datasource_luid="test-ds",
                use_cache=False
            )
            
            fields = [
                MockFieldMetadata(
                    name="field1",
                    fieldCaption="Field 1",
                    role="dimension",
                    dataType="STRING"
                ),
                MockFieldMetadata(
                    name="field2",
                    fieldCaption="Field 2",
                    role="measure",
                    dataType="REAL"
                ),
            ]
            
            # 索引并保存
            indexer.index_fields(fields)
            assert indexer.save_index()
            
            # 创建新的索引器并加载
            new_indexer = FieldIndexer(
                embedding_provider=provider,
                index_dir=tmpdir,
                datasource_luid="test-ds",
                use_cache=False
            )
            assert new_indexer.load_index()
            
            # 验证加载的数据
            assert new_indexer.field_count == 2
            
            chunk1 = new_indexer.get_chunk("field1")
            assert chunk1 is not None
            assert chunk1.field_caption == "Field 1"
            
            chunk2 = new_indexer.get_chunk("field2")
            assert chunk2 is not None
            assert chunk2.role == "measure"
    
    @given(st.lists(
        st.fixed_dictionaries({
            "name": st.text(min_size=1, max_size=10, alphabet="abcdefghijklmnopqrstuvwxyz"),
            "caption": st.text(min_size=1, max_size=30),
            "role": st.sampled_from(["dimension", "measure"]),
        }),
        min_size=1,
        max_size=10,
        unique_by=lambda x: x["name"]
    ))
    @settings(max_examples=20, deadline=None)
    def test_persistence_round_trip_property(self, field_dicts):
        """
        属性测试：保存后加载的索引与原始索引一致
        
        **Feature: rag-enhancement, Property 2: 索引持久化往返**
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            provider = MockEmbedding(dimensions=32)
            
            fields = [
                MockFieldMetadata(
                    name=d["name"],
                    fieldCaption=d["caption"],
                    role=d["role"],
                    dataType="STRING"
                )
                for d in field_dicts
            ]
            
            # 创建并保存索引
            indexer1 = FieldIndexer(
                embedding_provider=provider,
                index_dir=tmpdir,
                datasource_luid="test",
                use_cache=False
            )
            indexer1.index_fields(fields)
            indexer1.save_index()
            
            # 加载索引
            indexer2 = FieldIndexer(
                embedding_provider=provider,
                index_dir=tmpdir,
                datasource_luid="test",
                use_cache=False
            )
            indexer2.load_index()
            
            # 验证一致性
            assert indexer2.field_count == indexer1.field_count
            
            for field in fields:
                chunk1 = indexer1.get_chunk(field.name)
                chunk2 = indexer2.get_chunk(field.name)
                
                assert chunk2 is not None
                assert chunk1.field_name == chunk2.field_name
                assert chunk1.field_caption == chunk2.field_caption
                assert chunk1.role == chunk2.role


class TestIncrementalUpdate:
    """增量更新测试"""
    
    def test_incremental_update_detects_changes(self):
        """测试增量更新检测变化"""
        provider = MockEmbedding(dimensions=64)
        indexer = FieldIndexer(embedding_provider=provider, use_cache=False)
        
        # 初始索引
        fields_v1 = [
            MockFieldMetadata(name="field1", fieldCaption="Field 1", role="dimension", dataType="STRING"),
            MockFieldMetadata(name="field2", fieldCaption="Field 2", role="measure", dataType="REAL"),
        ]
        indexer.index_fields(fields_v1)
        assert indexer.field_count == 2
        
        # 修改一个字段
        fields_v2 = [
            MockFieldMetadata(name="field1", fieldCaption="Field 1 Updated", role="dimension", dataType="STRING"),
            MockFieldMetadata(name="field2", fieldCaption="Field 2", role="measure", dataType="REAL"),
        ]
        indexer.index_fields(fields_v2)
        
        # 验证更新
        chunk = indexer.get_chunk("field1")
        assert chunk.field_caption == "Field 1 Updated"
    
    def test_no_update_when_unchanged(self):
        """测试无变化时不更新"""
        provider = MockEmbedding(dimensions=64)
        indexer = FieldIndexer(embedding_provider=provider, use_cache=False)
        
        fields = [
            MockFieldMetadata(name="field1", fieldCaption="Field 1", role="dimension", dataType="STRING"),
        ]
        
        # 第一次索引
        count1 = indexer.index_fields(fields)
        
        # 第二次索引（相同数据）
        count2 = indexer.index_fields(fields)
        
        assert count1 == count2


class TestSearch:
    """搜索功能测试"""
    
    @pytest.fixture
    def indexed_indexer(self):
        """创建已索引的索引器"""
        provider = MockEmbedding(dimensions=128)
        indexer = FieldIndexer(embedding_provider=provider, use_cache=False)
        
        fields = [
            MockFieldMetadata(name="sales", fieldCaption="Sales Amount", role="measure", dataType="REAL", category="财务"),
            MockFieldMetadata(name="profit", fieldCaption="Profit", role="measure", dataType="REAL", category="财务"),
            MockFieldMetadata(name="region", fieldCaption="Region", role="dimension", dataType="STRING", category="地理"),
            MockFieldMetadata(name="date", fieldCaption="Order Date", role="dimension", dataType="DATE", category="时间"),
        ]
        indexer.index_fields(fields)
        return indexer
    
    def test_search_returns_results(self, indexed_indexer):
        """测试搜索返回结果"""
        results = indexed_indexer.search("销售金额", top_k=3)
        
        assert len(results) > 0
        assert len(results) <= 3
    
    def test_search_results_have_scores(self, indexed_indexer):
        """测试搜索结果有分数"""
        results = indexed_indexer.search("销售", top_k=3)
        
        for result in results:
            assert 0 <= result.score <= 1
            assert result.rank >= 1
    
    def test_search_with_role_filter(self, indexed_indexer):
        """测试按角色过滤搜索"""
        results = indexed_indexer.search("金额", top_k=10, role_filter="measure")
        
        for result in results:
            assert result.field_chunk.role == "measure"
    
    def test_search_with_category_filter(self, indexed_indexer):
        """测试按类别过滤搜索"""
        results = indexed_indexer.search("数据", top_k=10, category_filter="财务")
        
        for result in results:
            assert result.field_chunk.category == "财务"


class TestFieldTableMapping:
    """
    字段-表映射测试
    
    **Feature: rag-enhancement, Property 13: 字段-表映射**
    **Validates: Requirements 12.4, 1.2**
    """
    
    def test_field_contains_table_info(self):
        """测试字段包含表信息"""
        provider = MockEmbedding(dimensions=64)
        indexer = FieldIndexer(embedding_provider=provider, use_cache=False)
        
        fields = [
            MockFieldMetadata(
                name="order_id",
                fieldCaption="Order ID",
                role="dimension",
                dataType="STRING",
                logicalTableId="t1",
                logicalTableCaption="订单表"
            ),
            MockFieldMetadata(
                name="customer_name",
                fieldCaption="Customer Name",
                role="dimension",
                dataType="STRING",
                logicalTableId="t2",
                logicalTableCaption="客户表"
            ),
        ]
        
        indexer.index_fields(fields)
        
        # 验证表信息被保留
        chunk1 = indexer.get_chunk("order_id")
        assert chunk1.logical_table_id == "t1"
        assert chunk1.logical_table_caption == "订单表"
        
        chunk2 = indexer.get_chunk("customer_name")
        assert chunk2.logical_table_id == "t2"
        assert chunk2.logical_table_caption == "客户表"
    
    def test_index_text_includes_table_caption(self):
        """测试索引文本包含表名"""
        provider = MockEmbedding(dimensions=64)
        indexer = FieldIndexer(embedding_provider=provider, use_cache=False)
        
        field = MockFieldMetadata(
            name="field1",
            fieldCaption="Field 1",
            role="dimension",
            dataType="STRING",
            logicalTableCaption="测试表"
        )
        
        index_text = indexer.build_index_text(field)
        assert "测试表" in index_text
    
    @given(st.lists(
        st.fixed_dictionaries({
            "name": st.text(min_size=1, max_size=10, alphabet="abcdefghijklmnopqrstuvwxyz"),
            "caption": st.text(min_size=1, max_size=20),
            "role": st.sampled_from(["dimension", "measure"]),
            "table_id": st.text(min_size=1, max_size=10, alphabet="abcdefghijklmnopqrstuvwxyz0123456789"),
            "table_caption": st.text(min_size=1, max_size=20),
        }),
        min_size=1,
        max_size=15,
        unique_by=lambda x: x["name"]
    ))
    @settings(max_examples=30, deadline=None)
    def test_field_table_mapping_property(self, field_dicts):
        """
        属性测试：带有 logicalTableId 的字段，索引文本应包含对应的逻辑表名称
        
        **Feature: rag-enhancement, Property 13: 字段-表映射**
        **Validates: Requirements 12.4, 1.2**
        """
        provider = MockEmbedding(dimensions=32)
        indexer = FieldIndexer(embedding_provider=provider, use_cache=False)
        
        fields = [
            MockFieldMetadata(
                name=d["name"],
                fieldCaption=d["caption"],
                role=d["role"],
                dataType="STRING",
                logicalTableId=d["table_id"],
                logicalTableCaption=d["table_caption"]
            )
            for d in field_dicts
        ]
        
        indexer.index_fields(fields)
        
        # 验证每个字段的表映射
        for field in fields:
            chunk = indexer.get_chunk(field.name)
            assert chunk is not None, f"字段 {field.name} 未被索引"
            
            # 验证表信息被保留
            assert chunk.logical_table_id == field.logicalTableId
            assert chunk.logical_table_caption == field.logicalTableCaption
            
            # 验证索引文本包含表名
            assert field.logicalTableCaption in chunk.index_text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
