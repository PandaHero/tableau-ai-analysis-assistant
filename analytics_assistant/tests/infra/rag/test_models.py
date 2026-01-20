# -*- coding: utf-8 -*-
"""
RAG 数据模型单元测试
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest
from src.infra.rag.models import (
    RetrievalSource,
    EmbeddingResult,
    FieldChunk,
    RetrievalResult,
    MappingResult,
)


class TestRetrievalSource:
    """测试 RetrievalSource 枚举"""
    
    def test_retrieval_source_values(self):
        """测试检索来源枚举值"""
        assert RetrievalSource.EMBEDDING.value == "embedding"
        assert RetrievalSource.KEYWORD.value == "keyword"
        assert RetrievalSource.HYBRID.value == "hybrid"
        assert RetrievalSource.EXACT.value == "exact"
        assert RetrievalSource.FUZZY.value == "fuzzy"
        assert RetrievalSource.CASCADE.value == "cascade"


class TestEmbeddingResult:
    """测试 EmbeddingResult 数据类"""
    
    def test_create_embedding_result(self):
        """测试创建向量化结果"""
        result = EmbeddingResult(
            text="测试文本",
            vector=[0.1, 0.2, 0.3],
            model="test-model",
            dimensions=3
        )
        
        assert result.text == "测试文本"
        assert result.vector == [0.1, 0.2, 0.3]
        assert result.model == "test-model"
        assert result.dimensions == 3
    
    def test_embedding_result_dimension_mismatch(self):
        """测试向量维度不匹配"""
        with pytest.raises(ValueError, match="向量维度不匹配"):
            EmbeddingResult(
                text="测试文本",
                vector=[0.1, 0.2],
                model="test-model",
                dimensions=3
            )


class TestFieldChunk:
    """测试 FieldChunk 数据类"""
    
    def test_create_field_chunk(self):
        """测试创建字段分块"""
        chunk = FieldChunk(
            field_name="sales_amount",
            field_caption="销售额",
            role="measure",
            data_type="real",
            index_text="销售额 | measure | real"
        )
        
        assert chunk.field_name == "sales_amount"
        assert chunk.field_caption == "销售额"
        assert chunk.role == "measure"
        assert chunk.data_type == "real"
        assert chunk.index_text == "销售额 | measure | real"
    
    def test_field_chunk_with_optional_fields(self):
        """测试包含可选字段的字段分块"""
        chunk = FieldChunk(
            field_name="province",
            field_caption="省份",
            role="dimension",
            data_type="string",
            index_text="省份 | dimension | string",
            category="地理",
            sample_values=["北京", "上海", "广东"]
        )
        
        assert chunk.category == "地理"
        assert chunk.sample_values == ["北京", "上海", "广东"]
    
    def test_from_field_metadata(self):
        """测试从 FieldMetadata 创建 FieldChunk"""
        # 模拟 FieldMetadata 对象
        class MockFieldMetadata:
            def __init__(self):
                self.name = "sales_amount"
                self.fieldCaption = "销售额"
                self.role = "measure"
                self.dataType = "real"
                self.category = "财务"
                self.logicalTableCaption = "销售表"
                self.formula = "SUM([Amount])"
                self.sample_values = ["1000", "2000", "3000"]
        
        metadata = MockFieldMetadata()
        chunk = FieldChunk.from_field_metadata(metadata, max_samples=2)
        
        assert chunk.field_name == "sales_amount"
        assert chunk.field_caption == "销售额"
        assert chunk.role == "measure"
        assert chunk.data_type == "real"
        assert chunk.category == "财务"
        assert "销售额" in chunk.index_text
        assert "财务" in chunk.index_text
        assert "1000" in chunk.index_text
        assert "2000" in chunk.index_text
        assert "3000" not in chunk.index_text  # max_samples=2


class TestRetrievalResult:
    """测试 RetrievalResult 数据类"""
    
    def test_create_retrieval_result(self):
        """测试创建检索结果"""
        chunk = FieldChunk(
            field_name="sales_amount",
            field_caption="销售额",
            role="measure",
            data_type="real",
            index_text="销售额 | measure | real"
        )
        
        result = RetrievalResult(
            field_chunk=chunk,
            score=0.95,
            source=RetrievalSource.EMBEDDING,
            rank=1
        )
        
        assert result.field_chunk == chunk
        assert result.score == 0.95
        assert result.source == RetrievalSource.EMBEDDING
        assert result.rank == 1
    
    def test_retrieval_result_score_validation(self):
        """测试分数验证"""
        chunk = FieldChunk(
            field_name="test",
            field_caption="测试",
            role="measure",
            data_type="real",
            index_text="测试"
        )
        
        # 分数超出范围
        with pytest.raises(ValueError, match="分数必须在 0-1 之间"):
            RetrievalResult(
                field_chunk=chunk,
                score=1.5,
                source=RetrievalSource.EMBEDDING,
                rank=1
            )
        
        with pytest.raises(ValueError, match="分数必须在 0-1 之间"):
            RetrievalResult(
                field_chunk=chunk,
                score=-0.1,
                source=RetrievalSource.EMBEDDING,
                rank=1
            )
    
    def test_retrieval_result_rank_validation(self):
        """测试排名验证"""
        chunk = FieldChunk(
            field_name="test",
            field_caption="测试",
            role="measure",
            data_type="real",
            index_text="测试"
        )
        
        # 排名小于 1
        with pytest.raises(ValueError, match="排名必须 >= 1"):
            RetrievalResult(
                field_chunk=chunk,
                score=0.9,
                source=RetrievalSource.EMBEDDING,
                rank=0
            )
    
    def test_retrieval_result_with_rerank(self):
        """测试包含重排序信息的检索结果"""
        chunk = FieldChunk(
            field_name="sales_amount",
            field_caption="销售额",
            role="measure",
            data_type="real",
            index_text="销售额"
        )
        
        result = RetrievalResult(
            field_chunk=chunk,
            score=0.95,
            source=RetrievalSource.HYBRID,
            rank=1,
            rerank_score=0.98,
            original_rank=3
        )
        
        assert result.rerank_score == 0.98
        assert result.original_rank == 3


class TestMappingResult:
    """测试 MappingResult 数据类"""
    
    def test_create_mapping_result(self):
        """测试创建字段映射结果"""
        result = MappingResult(
            user_field="销售额",
            matched_field="sales_amount",
            confidence=0.95
        )
        
        assert result.user_field == "销售额"
        assert result.matched_field == "sales_amount"
        assert result.confidence == 0.95
    
    def test_is_confident(self):
        """测试高置信度判断"""
        result_high = MappingResult(
            user_field="销售额",
            matched_field="sales_amount",
            confidence=0.85
        )
        assert result_high.is_confident is True
        
        result_low = MappingResult(
            user_field="销售额",
            matched_field="sales_amount",
            confidence=0.65
        )
        assert result_low.is_confident is False
    
    def test_needs_disambiguation(self):
        """测试是否需要消歧"""
        result_no_alternatives = MappingResult(
            user_field="销售额",
            matched_field="sales_amount",
            confidence=0.65,
            alternatives=[]
        )
        assert result_no_alternatives.needs_disambiguation is False
        
        result_with_alternatives = MappingResult(
            user_field="销售额",
            matched_field="sales_amount",
            confidence=0.65,
            alternatives=["total_sales", "revenue"]
        )
        assert result_with_alternatives.needs_disambiguation is True
        
        result_high_confidence = MappingResult(
            user_field="销售额",
            matched_field="sales_amount",
            confidence=0.85,
            alternatives=["total_sales"]
        )
        assert result_high_confidence.needs_disambiguation is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
