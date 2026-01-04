# -*- coding: utf-8 -*-
"""
build_query Tool 单元测试

测试场景：
1. 正常构建 - 简单查询
2. 正常构建 - 带过滤器
3. 正常构建 - 带排序
4. invalid_computation 错误 - 无效计算
5. unsupported_operation 错误 - 不支持的操作
6. validation_failed 错误 - 验证失败
7. missing_input 错误 - 缺少输入
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from typing import Dict, Any

from tableau_assistant.src.orchestration.tools.build_query.models import (
    BuildQueryOutput,
    QueryBuildError,
    QueryBuildErrorType,
    BuildQueryInput,
)
from tableau_assistant.src.orchestration.tools.build_query.tool import (
    build_query_async,
)


class TestBuildQueryModels:
    """测试 build_query 数据模型"""
    
    def test_query_build_error_to_user_message(self):
        """测试错误消息生成"""
        error = QueryBuildError(
            type=QueryBuildErrorType.INVALID_COMPUTATION,
            message="无效的计算表达式",
            suggestion="请检查计算语法"
        )
        msg = error.to_user_message()
        assert "无效的计算表达式" in msg
        assert "请检查计算语法" in msg
    
    def test_query_build_error_without_suggestion(self):
        """测试没有建议的错误消息"""
        error = QueryBuildError(
            type=QueryBuildErrorType.BUILD_FAILED,
            message="构建失败"
        )
        msg = error.to_user_message()
        assert msg == "构建失败"
    
    def test_build_query_output_ok(self):
        """测试成功响应创建"""
        output = BuildQueryOutput.ok(
            vizql_query={"fields": [{"fieldCaption": "Sales"}]},
            field_count=1,
            has_filters=False,
            has_sorts=False,
            has_computations=False,
            latency_ms=50
        )
        assert output.success is True
        assert output.error is None
        assert output.field_count == 1
        assert output.vizql_query is not None
    
    def test_build_query_output_fail(self):
        """测试失败响应创建"""
        error = QueryBuildError(
            type=QueryBuildErrorType.VALIDATION_FAILED,
            message="验证失败"
        )
        output = BuildQueryOutput.fail(error=error, latency_ms=10)
        assert output.success is False
        assert output.error is not None
        assert output.error.type == QueryBuildErrorType.VALIDATION_FAILED
    
    def test_build_query_input_model(self):
        """测试输入模型"""
        input_data = BuildQueryInput(
            mapped_query={"semantic_query": {}, "field_mappings": {}},
            datasource_luid="test_ds",
            field_metadata={"Sales": {"dataType": "REAL"}}
        )
        assert input_data.datasource_luid == "test_ds"
        assert input_data.field_metadata is not None


class TestQueryBuildErrorTypes:
    """测试错误类型枚举"""
    
    def test_error_type_enum_values(self):
        """测试错误类型枚举值"""
        assert QueryBuildErrorType.INVALID_COMPUTATION.value == "invalid_computation"
        assert QueryBuildErrorType.UNSUPPORTED_OPERATION.value == "unsupported_operation"
        assert QueryBuildErrorType.MISSING_INPUT.value == "missing_input"
        assert QueryBuildErrorType.VALIDATION_FAILED.value == "validation_failed"
        assert QueryBuildErrorType.BUILD_FAILED.value == "build_failed"


class TestBuildQueryAsync:
    """测试 build_query_async 函数"""
    
    @pytest.mark.asyncio
    async def test_missing_input(self):
        """测试缺少输入"""
        result = await build_query_async(
            mapped_query=None,
            datasource_luid="test_ds"
        )
        assert result.success is False
        assert result.error is not None
        assert result.error.type == QueryBuildErrorType.MISSING_INPUT
    
    @pytest.mark.asyncio
    async def test_invalid_mapped_query(self):
        """测试无效的 MappedQuery"""
        result = await build_query_async(
            mapped_query={"invalid": "data"},
            datasource_luid="test_ds"
        )
        # 应该返回验证失败错误
        assert result.success is False
        assert result.error is not None
    
    @pytest.mark.asyncio
    async def test_missing_semantic_query(self):
        """测试 MappedQuery 中缺少 semantic_query"""
        result = await build_query_async(
            mapped_query={"field_mappings": {}},
            datasource_luid="test_ds"
        )
        assert result.success is False
        assert result.error is not None
    
    @pytest.mark.asyncio
    async def test_successful_build_simple_query(self):
        """测试成功构建简单查询"""
        from tableau_assistant.src.core.models.query import SemanticQuery
        from tableau_assistant.src.core.models.fields import MeasureField, DimensionField
        from tableau_assistant.src.agents.field_mapper.models import MappedQuery
        
        # 创建有效的 MappedQuery
        sq = SemanticQuery(
            measures=[MeasureField(field_name="Sales", aggregation="SUM")],
            dimensions=[DimensionField(field_name="Category")]
        )
        mq = MappedQuery(
            semantic_query=sq,
            field_mappings={}
        )
        
        result = await build_query_async(
            mapped_query=mq,
            datasource_luid="test_ds"
        )
        
        assert result.success is True
        assert result.vizql_query is not None
        assert result.field_count > 0
    
    @pytest.mark.asyncio
    async def test_successful_build_with_filters(self):
        """测试成功构建带过滤器的查询"""
        from tableau_assistant.src.core.models.query import SemanticQuery
        from tableau_assistant.src.core.models.fields import MeasureField, DimensionField
        from tableau_assistant.src.core.models.filters import SetFilter
        from tableau_assistant.src.agents.field_mapper.models import MappedQuery
        
        sq = SemanticQuery(
            measures=[MeasureField(field_name="Sales", aggregation="SUM")],
            dimensions=[DimensionField(field_name="Category")],
            filters=[SetFilter(field_name="Region", values=["East", "West"])]
        )
        mq = MappedQuery(
            semantic_query=sq,
            field_mappings={}
        )
        
        result = await build_query_async(
            mapped_query=mq,
            datasource_luid="test_ds"
        )
        
        assert result.success is True
        assert result.has_filters is True
    
    @pytest.mark.asyncio
    async def test_successful_build_with_sorts(self):
        """测试成功构建带排序的查询"""
        from tableau_assistant.src.core.models.query import SemanticQuery
        from tableau_assistant.src.core.models.fields import MeasureField, DimensionField, SortSpec
        from tableau_assistant.src.agents.field_mapper.models import MappedQuery
        
        sq = SemanticQuery(
            measures=[MeasureField(
                field_name="Sales",
                aggregation="SUM",
                sort=SortSpec(direction="DESC", priority=1)
            )],
            dimensions=[DimensionField(field_name="Category")]
        )
        mq = MappedQuery(
            semantic_query=sq,
            field_mappings={}
        )
        
        result = await build_query_async(
            mapped_query=mq,
            datasource_luid="test_ds"
        )
        
        assert result.success is True
        assert result.has_sorts is True
    
    @pytest.mark.asyncio
    async def test_build_with_mapped_query_object(self):
        """测试直接传递 MappedQuery 对象"""
        from tableau_assistant.src.core.models.query import SemanticQuery
        from tableau_assistant.src.core.models.fields import MeasureField
        from tableau_assistant.src.agents.field_mapper.models import MappedQuery
        
        sq = SemanticQuery(
            measures=[MeasureField(field_name="Profit", aggregation="SUM")]
        )
        mq = MappedQuery(
            semantic_query=sq,
            field_mappings={}
        )
        
        # 直接传递对象而非字典
        result = await build_query_async(
            mapped_query=mq,
            datasource_luid="test_ds"
        )
        
        assert result.success is True


class TestBuildQueryOutputFlags:
    """测试输出标志"""
    
    def test_output_flags_default(self):
        """测试默认标志值"""
        output = BuildQueryOutput(success=True)
        assert output.has_filters is False
        assert output.has_sorts is False
        assert output.has_computations is False
        assert output.field_count == 0
    
    def test_output_with_all_flags(self):
        """测试所有标志为 True"""
        output = BuildQueryOutput.ok(
            vizql_query={"fields": []},
            field_count=5,
            has_filters=True,
            has_sorts=True,
            has_computations=True,
            latency_ms=100
        )
        assert output.has_filters is True
        assert output.has_sorts is True
        assert output.has_computations is True
        assert output.field_count == 5
        assert output.latency_ms == 100
