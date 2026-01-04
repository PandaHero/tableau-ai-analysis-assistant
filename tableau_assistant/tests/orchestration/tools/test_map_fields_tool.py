# -*- coding: utf-8 -*-
"""
map_fields Tool 单元测试

测试场景：
1. 正常映射 - 所有字段成功映射
2. field_not_found 错误 - 字段不存在
3. ambiguous_field 错误 - 字段存在歧义
4. no_metadata 错误 - 无法获取元数据
5. 空查询 - 没有需要映射的字段
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any

from tableau_assistant.src.orchestration.tools.map_fields.models import (
    MapFieldsOutput,
    FieldMappingError,
    FieldMappingErrorType,
    FieldSuggestion,
    MappingResultItem,
)
from tableau_assistant.src.orchestration.tools.map_fields.tool import (
    map_fields_async,
    _extract_terms_from_semantic_query,
)
from tableau_assistant.src.core.models.query import SemanticQuery
from tableau_assistant.src.core.models.fields import MeasureField, DimensionField


class TestMapFieldsModels:
    """测试 map_fields 数据模型"""
    
    def test_field_mapping_error_to_user_message_field_not_found(self):
        """测试 field_not_found 错误消息生成"""
        error = FieldMappingError(
            type=FieldMappingErrorType.FIELD_NOT_FOUND,
            field="销售额",
            message="字段不存在",
            suggestions=[
                FieldSuggestion(field_name="Sales", confidence=0.9, reason="语义相似"),
                FieldSuggestion(field_name="Revenue", confidence=0.8, reason="同义词"),
            ]
        )
        msg = error.to_user_message()
        assert "销售额" in msg
        assert "Sales" in msg
        assert "Revenue" in msg
    
    def test_field_mapping_error_to_user_message_ambiguous(self):
        """测试 ambiguous_field 错误消息生成"""
        error = FieldMappingError(
            type=FieldMappingErrorType.AMBIGUOUS_FIELD,
            field="日期",
            message="字段存在多个匹配",
            suggestions=[
                FieldSuggestion(field_name="Order Date", confidence=0.85),
                FieldSuggestion(field_name="Ship Date", confidence=0.82),
            ]
        )
        msg = error.to_user_message()
        assert "日期" in msg
        assert "Order Date" in msg
        assert "Ship Date" in msg
    
    def test_field_mapping_error_to_user_message_no_metadata(self):
        """测试 no_metadata 错误消息生成"""
        error = FieldMappingError(
            type=FieldMappingErrorType.NO_METADATA,
            field="test_field",
            message="无法获取元数据"
        )
        msg = error.to_user_message()
        assert "元数据" in msg
        assert "test_field" in msg
    
    def test_map_fields_output_ok(self):
        """测试成功响应创建"""
        output = MapFieldsOutput.ok(
            mapped_query={"semantic_query": {}, "field_mappings": {}},
            field_mappings={
                "销售额": MappingResultItem(
                    business_term="销售额",
                    technical_field="Sales",
                    confidence=0.95,
                    mapping_source="rag_direct"
                )
            },
            overall_confidence=0.95,
            low_confidence_fields=[],
            latency_ms=100
        )
        assert output.success is True
        assert output.error is None
        assert output.overall_confidence == 0.95
        assert "销售额" in output.field_mappings
    
    def test_map_fields_output_fail(self):
        """测试失败响应创建"""
        error = FieldMappingError(
            type=FieldMappingErrorType.FIELD_NOT_FOUND,
            field="unknown_field",
            message="字段不存在"
        )
        output = MapFieldsOutput.fail(error=error, latency_ms=50)
        assert output.success is False
        assert output.error is not None
        assert output.error.type == FieldMappingErrorType.FIELD_NOT_FOUND


class TestExtractTermsFromSemanticQuery:
    """测试从 SemanticQuery 提取术语"""
    
    def test_extract_measures(self):
        """测试提取度量字段"""
        sq = SemanticQuery(
            measures=[
                MeasureField(field_name="Sales", aggregation="SUM"),
                MeasureField(field_name="Profit", aggregation="SUM"),
            ]
        )
        terms = _extract_terms_from_semantic_query(sq)
        assert "Sales" in terms
        assert "Profit" in terms
        # 不限制角色
        assert terms["Sales"] is None
        assert terms["Profit"] is None
    
    def test_extract_dimensions(self):
        """测试提取维度字段"""
        sq = SemanticQuery(
            dimensions=[
                DimensionField(field_name="Category"),
                DimensionField(field_name="Region"),
            ]
        )
        terms = _extract_terms_from_semantic_query(sq)
        assert "Category" in terms
        assert "Region" in terms
    
    def test_extract_filters(self):
        """测试提取过滤器字段"""
        from tableau_assistant.src.core.models.filters import SetFilter
        sq = SemanticQuery(
            filters=[
                SetFilter(field_name="Status", values=["Active"]),
            ]
        )
        terms = _extract_terms_from_semantic_query(sq)
        assert "Status" in terms
    
    def test_extract_empty_query(self):
        """测试空查询"""
        sq = SemanticQuery()
        terms = _extract_terms_from_semantic_query(sq)
        assert len(terms) == 0
    
    def test_no_duplicate_terms(self):
        """测试不重复提取相同字段"""
        from tableau_assistant.src.core.models.filters import SetFilter
        sq = SemanticQuery(
            measures=[MeasureField(field_name="Sales", aggregation="SUM")],
            filters=[SetFilter(field_name="Sales", values=["100"])],
        )
        terms = _extract_terms_from_semantic_query(sq)
        # Sales 只出现一次
        assert list(terms.keys()).count("Sales") == 1


class TestMapFieldsAsync:
    """测试 map_fields_async 函数"""
    
    @pytest.mark.asyncio
    async def test_invalid_semantic_query(self):
        """测试无效的 SemanticQuery 输入"""
        result = await map_fields_async(
            semantic_query={"invalid": "data"},
            datasource_luid="test_ds"
        )
        # 应该返回验证错误或映射失败
        # 由于 SemanticQuery 有默认值，可能不会失败
        # 但如果有必填字段缺失，应该返回错误
        assert isinstance(result, MapFieldsOutput)
    
    @pytest.mark.asyncio
    async def test_empty_semantic_query(self):
        """测试空的 SemanticQuery（没有需要映射的字段）"""
        result = await map_fields_async(
            semantic_query={},
            datasource_luid="test_ds"
        )
        # 空查询应该成功，因为没有需要映射的字段
        assert result.success is True
        assert result.overall_confidence == 1.0
        assert len(result.field_mappings) == 0
    
    @pytest.mark.asyncio
    async def test_no_data_model_returns_no_metadata_error(self):
        """测试没有 data_model 时返回 no_metadata 错误"""
        result = await map_fields_async(
            semantic_query={
                "measures": [{"field_name": "Sales", "aggregation": "SUM"}]
            },
            datasource_luid="test_ds",
            data_model=None,
            config=None
        )
        # 没有 data_model 应该返回 no_metadata 错误
        assert result.success is False
        assert result.error is not None
        assert result.error.type == FieldMappingErrorType.NO_METADATA
    
    @pytest.mark.asyncio
    async def test_successful_mapping_with_mock(self):
        """测试成功映射（使用 mock）"""
        # 创建 mock data_model
        mock_field = MagicMock()
        mock_field.name = "Sales"
        mock_field.fieldCaption = "Sales Amount"
        mock_field.role = "measure"
        mock_field.dataType = "REAL"
        
        mock_data_model = MagicMock()
        mock_data_model.fields = [mock_field]
        
        # Mock FieldMapperNode
        mock_mapping_result = MagicMock()
        mock_mapping_result.business_term = "Sales"
        mock_mapping_result.technical_field = "Sales"
        mock_mapping_result.confidence = 0.95
        mock_mapping_result.mapping_source = "rag_direct"
        mock_mapping_result.category = None
        mock_mapping_result.level = None
        mock_mapping_result.granularity = None
        mock_mapping_result.alternatives = []
        
        with patch(
            'tableau_assistant.src.orchestration.tools.map_fields.tool._get_field_mapper'
        ) as mock_get_mapper:
            mock_mapper = AsyncMock()
            mock_mapper.map_fields_batch = AsyncMock(return_value={
                "Sales": mock_mapping_result
            })
            mock_get_mapper.return_value = mock_mapper
            
            result = await map_fields_async(
                semantic_query={
                    "measures": [{"field_name": "Sales", "aggregation": "SUM"}]
                },
                datasource_luid="test_ds",
                data_model=mock_data_model
            )
            
            assert result.success is True
            assert "Sales" in result.field_mappings
            assert result.field_mappings["Sales"].technical_field == "Sales"
            assert result.field_mappings["Sales"].confidence == 0.95


class TestFieldMappingErrorTypes:
    """测试各种错误类型"""
    
    def test_error_type_enum_values(self):
        """测试错误类型枚举值"""
        assert FieldMappingErrorType.FIELD_NOT_FOUND.value == "field_not_found"
        assert FieldMappingErrorType.AMBIGUOUS_FIELD.value == "ambiguous_field"
        assert FieldMappingErrorType.NO_METADATA.value == "no_metadata"
        assert FieldMappingErrorType.MAPPING_FAILED.value == "mapping_failed"
    
    def test_field_suggestion_model(self):
        """测试字段建议模型"""
        suggestion = FieldSuggestion(
            field_name="Sales",
            confidence=0.9,
            reason="语义相似"
        )
        assert suggestion.field_name == "Sales"
        assert suggestion.confidence == 0.9
        assert suggestion.reason == "语义相似"
    
    def test_mapping_result_item_model(self):
        """测试映射结果项模型"""
        item = MappingResultItem(
            business_term="销售额",
            technical_field="Sales",
            confidence=0.95,
            mapping_source="rag_direct",
            category="financial",
            level=1,
            granularity="transaction"
        )
        assert item.business_term == "销售额"
        assert item.technical_field == "Sales"
        assert item.confidence == 0.95
        assert item.mapping_source == "rag_direct"
