# -*- coding: utf-8 -*-
"""Tableau Adapter 单元测试。

测试任务 2.2.5：
- 测试适配器接口实现
- 测试查询执行流程

注意：测试使用 SemanticOutput 作为输入，这是语义解析器的输出格式。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from analytics_assistant.src.core.schemas import (
    DimensionField,
    MeasureField,
    ValidationErrorType,
)
from analytics_assistant.src.agents.semantic_parser.schemas.output import (
    SemanticOutput,
    What,
    Where,
    SelfCheck,
)
from analytics_assistant.src.platform.tableau.adapter import TableauAdapter


@pytest.fixture
def mock_vizql_client():
    """创建模拟的 VizQL 客户端。"""
    client = AsyncMock()
    client.query_datasource = AsyncMock(return_value={
        "columns": [
            {"fieldCaption": "省份", "dataType": "STRING", "fieldRole": "DIMENSION"},
            {"fieldCaption": "销售额", "dataType": "REAL", "fieldRole": "MEASURE"},
        ],
        "data": [
            {"省份": "北京", "销售额": 100000},
            {"省份": "上海", "销售额": 150000},
        ],
        "rowCount": 2,
        "executionTimeMs": 150,
    })
    return client


@pytest.fixture
def adapter(mock_vizql_client):
    """创建带模拟客户端的适配器。"""
    return TableauAdapter(vizql_client=mock_vizql_client)


@pytest.fixture
def adapter_no_client():
    """创建无客户端的适配器。"""
    return TableauAdapter()


def make_semantic_output(
    dimensions: list[DimensionField] | None = None,
    measures: list[MeasureField] | None = None,
    filters: list | None = None,
) -> SemanticOutput:
    """创建 SemanticOutput 测试对象的辅助函数。"""
    return SemanticOutput(
        restated_question="测试查询",
        what=What(measures=measures or []),
        where=Where(
            dimensions=dimensions or [],
            filters=filters or [],
        ),
        self_check=SelfCheck(
            field_mapping_confidence=1.0,
            time_range_confidence=1.0,
            computation_confidence=1.0,
            overall_confidence=1.0,
        ),
    )


# ═══════════════════════════════════════════════════════════════════════════
# 基本属性测试
# ═══════════════════════════════════════════════════════════════════════════

class TestAdapterProperties:
    """适配器属性测试。"""
    
    def test_platform_name(self, adapter):
        """测试平台名称。"""
        assert adapter.platform_name == "tableau"


# ═══════════════════════════════════════════════════════════════════════════
# build_query 测试
# ═══════════════════════════════════════════════════════════════════════════

class TestBuildQuery:
    """build_query 方法测试。"""
    
    def test_build_simple_query(self, adapter):
        """测试构建简单查询。"""
        query = make_semantic_output(
            dimensions=[DimensionField(field_name="省份")],
            measures=[MeasureField(field_name="销售额")],
        )
        result = adapter.build_query(query)
        
        assert "fields" in result
        assert len(result["fields"]) == 2
    
    def test_build_query_with_kwargs(self, adapter):
        """测试带额外参数的构建。"""
        query = make_semantic_output(
            dimensions=[DimensionField(field_name="省份")],
        )
        result = adapter.build_query(
            query,
            datasource_id="test-ds-id",
            field_metadata={"省份": {"dataType": "STRING"}},
        )
        
        assert "fields" in result


# ═══════════════════════════════════════════════════════════════════════════
# validate_query 测试
# ═══════════════════════════════════════════════════════════════════════════

class TestValidateQuery:
    """validate_query 方法测试。"""
    
    def test_validate_valid_query(self, adapter):
        """测试验证有效查询。"""
        query = make_semantic_output(
            dimensions=[DimensionField(field_name="省份")],
            measures=[MeasureField(field_name="销售额")],
        )
        result = adapter.validate_query(query)
        
        assert result.is_valid is True
    
    def test_validate_empty_query(self, adapter):
        """测试验证空查询。"""
        query = make_semantic_output()
        result = adapter.validate_query(query)
        
        assert result.is_valid is False
        assert len(result.errors) > 0


# ═══════════════════════════════════════════════════════════════════════════
# execute_query 测试
# ═══════════════════════════════════════════════════════════════════════════

class TestExecuteQuery:
    """execute_query 方法测试。"""
    
    @pytest.mark.asyncio
    async def test_execute_simple_query(self, adapter, mock_vizql_client):
        """测试执行简单查询。"""
        query = make_semantic_output(
            dimensions=[DimensionField(field_name="省份")],
            measures=[MeasureField(field_name="销售额")],
        )
        
        result = await adapter.execute_query(
            query,
            datasource_id="test-ds-id",
        )
        
        # 验证调用了 VizQL 客户端
        mock_vizql_client.query_datasource.assert_called_once()
        
        # 验证结果
        assert result.row_count == 2
        assert len(result.columns) == 2
        assert result.execution_time_ms == 150
    
    @pytest.mark.asyncio
    async def test_execute_query_no_client(self, adapter_no_client):
        """测试无客户端时执行查询抛出异常。"""
        query = make_semantic_output(
            dimensions=[DimensionField(field_name="省份")],
            measures=[MeasureField(field_name="销售额")],
        )
        
        with pytest.raises(RuntimeError, match="VizQL 客户端未配置"):
            await adapter_no_client.execute_query(
                query,
                datasource_id="test-ds-id",
            )
    
    @pytest.mark.asyncio
    async def test_execute_invalid_query(self, adapter):
        """测试执行无效查询抛出异常。"""
        query = make_semantic_output()  # 空查询
        
        with pytest.raises(ValueError, match="查询验证失败"):
            await adapter.execute_query(
                query,
                datasource_id="test-ds-id",
            )
    
    @pytest.mark.asyncio
    async def test_execute_query_client_error(self, adapter, mock_vizql_client):
        """测试客户端错误传播。"""
        mock_vizql_client.query_datasource.side_effect = Exception("API Error")
        
        query = make_semantic_output(
            dimensions=[DimensionField(field_name="省份")],
            measures=[MeasureField(field_name="销售额")],
        )
        
        with pytest.raises(Exception, match="API Error"):
            await adapter.execute_query(
                query,
                datasource_id="test-ds-id",
            )


# ═══════════════════════════════════════════════════════════════════════════
# 响应转换测试
# ═══════════════════════════════════════════════════════════════════════════

class TestResponseConversion:
    """响应转换测试。"""
    
    @pytest.mark.asyncio
    async def test_convert_columns(self, adapter, mock_vizql_client):
        """测试列信息转换。"""
        query = make_semantic_output(
            dimensions=[DimensionField(field_name="省份")],
            measures=[MeasureField(field_name="销售额")],
        )
        
        result = await adapter.execute_query(
            query,
            datasource_id="test-ds-id",
        )
        
        # 检查维度列
        dim_col = result.columns[0]
        assert dim_col.name == "省份"
        assert dim_col.is_dimension is True
        assert dim_col.is_measure is False
        
        # 检查度量列
        measure_col = result.columns[1]
        assert measure_col.name == "销售额"
        assert measure_col.is_dimension is False
        assert measure_col.is_measure is True
    
    @pytest.mark.asyncio
    async def test_convert_table_calculation_column(self, adapter, mock_vizql_client):
        """测试表计算列转换。"""
        mock_vizql_client.query_datasource.return_value = {
            "columns": [
                {"fieldCaption": "排名", "columnClass": "TABLE_CALCULATION"},
            ],
            "data": [],
            "rowCount": 0,
        }
        
        query = make_semantic_output(
            dimensions=[DimensionField(field_name="省份")],
            measures=[MeasureField(field_name="销售额")],
        )
        
        result = await adapter.execute_query(
            query,
            datasource_id="test-ds-id",
        )
        
        assert result.columns[0].is_computation is True
    
    @pytest.mark.asyncio
    async def test_convert_data_rows(self, adapter, mock_vizql_client):
        """测试数据行转换。"""
        query = make_semantic_output(
            dimensions=[DimensionField(field_name="省份")],
            measures=[MeasureField(field_name="销售额")],
        )
        
        result = await adapter.execute_query(
            query,
            datasource_id="test-ds-id",
        )
        
        assert len(result.data) == 2
        assert result.data[0]["省份"] == "北京"
        assert result.data[1]["销售额"] == 150000
