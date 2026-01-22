"""
检索器测试
"""
import pytest
from dataclasses import dataclass
from typing import List

from analytics_assistant.src.infra.rag.models import FieldChunk, RetrievalResult, RetrievalSource
from analytics_assistant.src.infra.rag.retriever import (
    RetrievalConfig,
    MetadataFilter,
    ExactRetriever,
    create_retriever,
)


# Mock 数据
@dataclass
class MockFieldMetadata:
    name: str
    fieldCaption: str
    role: str
    dataType: str
    category: str = None
    formula: str = None
    logicalTableCaption: str = None
    sample_values: List[str] = None


def create_mock_fields():
    return [
        MockFieldMetadata(
            name="sales_amount",
            fieldCaption="销售金额",
            role="measure",
            dataType="real",
            category="销售",
        ),
        MockFieldMetadata(
            name="region",
            fieldCaption="区域",
            role="dimension",
            dataType="string",
            category="地理",
        ),
        MockFieldMetadata(
            name="order_date",
            fieldCaption="订单日期",
            role="dimension",
            dataType="date",
            category="时间",
        ),
    ]


class TestMetadataFilter:
    """测试元数据过滤器"""
    
    def test_to_dict_empty(self):
        f = MetadataFilter()
        assert f.to_dict() == {}
    
    def test_to_dict_with_role(self):
        f = MetadataFilter(role="dimension")
        assert f.to_dict() == {"role": "dimension"}
    
    def test_to_dict_with_category(self):
        f = MetadataFilter(category="销售")
        assert f.to_dict() == {"category": "销售"}


class TestExactRetriever:
    """测试精确匹配检索器"""
    
    def test_retrieve_by_caption(self):
        fields = create_mock_fields()
        chunks = {f.name: FieldChunk.from_field_metadata(f) for f in fields}
        
        retriever = ExactRetriever(chunks)
        results = retriever.retrieve("销售金额")
        
        assert len(results) == 1
        assert results[0].field_chunk.field_name == "sales_amount"
        assert results[0].score == 1.0
        assert results[0].source == RetrievalSource.EXACT
    
    def test_retrieve_by_name(self):
        fields = create_mock_fields()
        chunks = {f.name: FieldChunk.from_field_metadata(f) for f in fields}
        
        retriever = ExactRetriever(chunks)
        results = retriever.retrieve("region")
        
        assert len(results) == 1
        assert results[0].field_chunk.field_name == "region"
    
    def test_retrieve_case_insensitive(self):
        fields = create_mock_fields()
        chunks = {f.name: FieldChunk.from_field_metadata(f) for f in fields}
        
        retriever = ExactRetriever(chunks, case_sensitive=False)
        results = retriever.retrieve("REGION")
        
        assert len(results) == 1
        assert results[0].field_chunk.field_name == "region"
    
    def test_retrieve_not_found(self):
        fields = create_mock_fields()
        chunks = {f.name: FieldChunk.from_field_metadata(f) for f in fields}
        
        retriever = ExactRetriever(chunks)
        results = retriever.retrieve("不存在的字段")
        
        assert len(results) == 0
    
    def test_retrieve_empty_query(self):
        fields = create_mock_fields()
        chunks = {f.name: FieldChunk.from_field_metadata(f) for f in fields}
        
        retriever = ExactRetriever(chunks)
        results = retriever.retrieve("")
        
        assert results == []


class TestCreateRetriever:
    """测试 create_retriever 工厂函数"""
    
    def test_create_exact_retriever(self):
        fields = create_mock_fields()
        
        retriever = create_retriever(
            fields=fields,
            retriever_type="exact"
        )
        
        assert retriever is not None
        assert isinstance(retriever, ExactRetriever)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
