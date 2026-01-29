# -*- coding: utf-8 -*-
"""
DimensionHierarchyInference RAGService 迁移测试

验证 DimensionHierarchyInference 组件迁移到 RAGService 后功能正常。

**Validates: Requirements 6.3**
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest
from unittest.mock import patch, MagicMock

from src.agents.dimension_hierarchy.inference import (
    DimensionHierarchyInference,
    DIMENSION_PATTERNS_INDEX,
    PatternSource,
    generate_pattern_id,
)
from src.core.schemas.data_model import Field
from src.core.schemas.enums import DimensionCategory
from src.agents.dimension_hierarchy.schemas import DimensionAttributes


class TestRAGServiceIntegration:
    """测试 RAGService 集成"""
    
    def test_uses_rag_service_for_index_count(self):
        """测试使用 RAGService 获取索引数量"""
        with patch('src.agents.dimension_hierarchy.inference._get_config') as mock_config:
            mock_config.return_value = {}
            
            inference = DimensionHierarchyInference(
                enable_rag=True,
                enable_cache=False,
                enable_self_learning=False,
            )
            
            # 索引不存在时应返回 0
            count = inference._get_index_count()
            assert count == 0
    
    def test_init_rag_creates_index_via_rag_service(self):
        """测试 _init_rag 通过 RAGService 创建索引"""
        with patch('src.agents.dimension_hierarchy.inference._get_config') as mock_config:
            mock_config.return_value = {}
            
            with patch('src.agents.dimension_hierarchy.inference.get_rag_service') as mock_rag:
                mock_index_manager = MagicMock()
                mock_index_manager.get_index.return_value = None  # 索引不存在
                mock_rag.return_value.index = mock_index_manager
                
                inference = DimensionHierarchyInference(
                    enable_rag=True,
                    enable_cache=False,
                    enable_self_learning=True,  # 需要启用才能加载 patterns
                )
                
                # 初始化 RAG
                inference._init_rag()
                
                # 验证调用了 get_index 检查索引是否存在
                mock_index_manager.get_index.assert_called_with(DIMENSION_PATTERNS_INDEX)
    
    @pytest.mark.asyncio
    async def test_rag_search_uses_rag_service(self):
        """测试 _rag_search 使用 RAGService 进行检索"""
        with patch('src.agents.dimension_hierarchy.inference._get_config') as mock_config:
            mock_config.return_value = {}
            
            with patch('src.agents.dimension_hierarchy.inference.get_rag_service') as mock_rag:
                # 模拟索引存在
                mock_index_manager = MagicMock()
                mock_index_manager.get_index.return_value = MagicMock()
                mock_rag.return_value.index = mock_index_manager
                
                # 模拟检索结果
                mock_retrieval = MagicMock()
                mock_retrieval.search.return_value = []  # 无结果
                mock_rag.return_value.retrieval = mock_retrieval
                
                inference = DimensionHierarchyInference(
                    enable_rag=True,
                    enable_cache=False,
                    enable_self_learning=False,
                )
                inference._rag_initialized = True
                
                fields = [
                    Field(name="test", caption="测试字段", data_type="string", role="dimension"),
                ]
                
                results, misses = await inference._rag_search(fields)
                
                # 验证调用了 RAGService 检索
                mock_retrieval.search.assert_called()
    
    def test_add_patterns_to_index_uses_rag_service(self):
        """测试 _add_patterns_to_index 使用 RAGService 增量添加"""
        with patch('src.agents.dimension_hierarchy.inference._get_config') as mock_config:
            mock_config.return_value = {}
            
            with patch('src.agents.dimension_hierarchy.inference.get_rag_service') as mock_rag:
                mock_index_manager = MagicMock()
                mock_index_manager.get_index.return_value = MagicMock()  # 索引存在
                mock_index_manager.add_documents.return_value = 1
                mock_rag.return_value.index = mock_index_manager
                
                inference = DimensionHierarchyInference(
                    enable_rag=True,
                    enable_cache=False,
                    enable_self_learning=True,
                )
                
                patterns = [
                    {
                        "pattern_id": "test-id",
                        "field_caption": "测试字段",
                        "data_type": "string",
                        "category": "other",
                        "category_detail": "other-test",
                        "source": "llm",
                        "verified": False,
                    }
                ]
                
                inference._add_patterns_to_index(patterns)
                
                # 验证调用了 add_documents
                mock_index_manager.add_documents.assert_called_once()
                call_args = mock_index_manager.add_documents.call_args
                assert call_args[1]["index_name"] == DIMENSION_PATTERNS_INDEX


class TestMigrationCompatibility:
    """测试迁移兼容性"""
    
    @pytest.mark.asyncio
    async def test_rag_search_returns_correct_format(self):
        """测试 _rag_search 返回正确的格式"""
        with patch('src.agents.dimension_hierarchy.inference._get_config') as mock_config:
            mock_config.return_value = {}
            
            inference = DimensionHierarchyInference(
                enable_rag=False,
                enable_cache=False,
                enable_self_learning=False,
            )
            
            fields = [
                Field(name="test", caption="测试字段", data_type="string", role="dimension"),
            ]
            
            results, misses = await inference._rag_search(fields)
            
            # 验证返回格式
            assert isinstance(results, dict)
            assert isinstance(misses, list)
            # RAG 禁用时，所有字段都应该是 miss
            assert len(misses) == len(fields)
    
    def test_store_to_rag_returns_count(self):
        """测试 _store_to_rag 返回存储数量"""
        with patch('src.agents.dimension_hierarchy.inference._get_config') as mock_config:
            mock_config.return_value = {}
            
            inference = DimensionHierarchyInference(
                enable_rag=False,
                enable_cache=False,
                enable_self_learning=False,
            )
            
            results = {
                "测试字段": DimensionAttributes(
                    category=DimensionCategory.OTHER,
                    category_detail="other-test",
                    level=3,
                    granularity="medium",
                    level_confidence=0.9,
                    reasoning="测试",
                )
            }
            fields = [Field(name="test", caption="测试字段", data_type="string", role="dimension")]
            
            count = inference._store_to_rag(results, fields, "test-ds")
            
            # 自学习禁用时应返回 0
            assert count == 0
    
    @pytest.mark.asyncio
    async def test_infer_works_without_rag(self):
        """测试禁用 RAG 时推断仍然工作"""
        with patch('src.agents.dimension_hierarchy.inference._get_config') as mock_config:
            mock_config.return_value = {}
            
            inference = DimensionHierarchyInference(
                enable_rag=False,
                enable_cache=False,
                enable_self_learning=False,
            )
            
            fields = [
                Field(name="year", caption="年份", data_type="integer", role="dimension"),
            ]
            
            result = await inference.infer("test-ds", fields)
            
            # 应该有推断结果（通过种子匹配或 LLM）
            assert result is not None
            assert hasattr(result, 'dimension_hierarchy')


class TestIndexDocumentFormat:
    """测试 IndexDocument 格式"""
    
    def test_pattern_to_index_document_format(self):
        """测试 pattern 转换为 IndexDocument 格式"""
        from src.infra.rag import IndexDocument
        
        pattern = {
            "pattern_id": "test-id",
            "field_caption": "年份",
            "data_type": "integer",
            "category": "time",
            "category_detail": "time-year",
            "source": "seed",
            "verified": True,
        }
        
        index_text = f"{pattern['field_caption']} | {pattern.get('category', '')} | {pattern.get('category_detail', '')}"
        doc = IndexDocument(
            id=pattern["pattern_id"],
            content=index_text,
            metadata={
                "field_caption": pattern["field_caption"],
                "data_type": pattern["data_type"],
                "category": pattern.get("category", ""),
                "category_detail": pattern.get("category_detail", ""),
                "source": pattern.get("source", ""),
                "verified": pattern.get("verified", False),
            },
        )
        
        assert doc.id == "test-id"
        assert "年份" in doc.content
        assert doc.metadata["category"] == "time"
        assert doc.metadata["verified"] is True


class TestDimensionPatternsIndex:
    """测试维度模式索引常量"""
    
    def test_index_name_constant(self):
        """测试索引名称常量"""
        assert DIMENSION_PATTERNS_INDEX == "dimension_patterns"
    
    def test_pattern_source_enum(self):
        """测试 PatternSource 枚举"""
        assert PatternSource.SEED.value == "seed"
        assert PatternSource.LLM.value == "llm"
        assert PatternSource.MANUAL.value == "manual"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
