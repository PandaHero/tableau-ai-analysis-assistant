# -*- coding: utf-8 -*-
"""
execute_query Tool 单元测试

测试场景：
1. 正常执行 - 小结果集
2. 正常执行 - 大结果集
3. execution_failed 错误 - 执行失败
4. timeout 错误 - 超时
5. auth_error 错误 - 认证失败
6. invalid_query 错误 - 无效查询
7. missing_input 错误 - 缺少输入
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from typing import Dict, Any, List

from tableau_assistant.src.orchestration.tools.execute_query.models import (
    ExecuteQueryOutput,
    ExecutionError,
    ExecutionErrorType,
    ExecuteQueryInput,
)
from tableau_assistant.src.orchestration.tools.execute_query.tool import (
    execute_query_async,
    _classify_error,
    LARGE_RESULT_THRESHOLD,
)


class TestExecuteQueryModels:
    """测试 execute_query 数据模型"""
    
    def test_execution_error_to_user_message(self):
        """测试错误消息生成"""
        error = ExecutionError(
            type=ExecutionErrorType.TIMEOUT,
            message="查询超时",
            suggestion="请简化查询条件"
        )
        msg = error.to_user_message()
        assert "查询超时" in msg
        assert "请简化查询条件" in msg
    
    def test_execution_error_without_suggestion(self):
        """测试没有建议的错误消息"""
        error = ExecutionError(
            type=ExecutionErrorType.EXECUTION_FAILED,
            message="执行失败"
        )
        msg = error.to_user_message()
        assert msg == "执行失败"
    
    def test_execute_query_output_ok(self):
        """测试成功响应创建"""
        output = ExecuteQueryOutput.ok(
            data=[{"Sales": 100}, {"Sales": 200}],
            columns=[{"fieldCaption": "Sales", "dataType": "REAL"}],
            row_count=2,
            query_id="q123",
            execution_time_ms=150
        )
        assert output.success is True
        assert output.error is None
        assert output.row_count == 2
        assert len(output.data) == 2
        assert output.query_id == "q123"
    
    def test_execute_query_output_fail(self):
        """测试失败响应创建"""
        error = ExecutionError(
            type=ExecutionErrorType.AUTH_ERROR,
            message="认证失败"
        )
        output = ExecuteQueryOutput.fail(error=error, execution_time_ms=10)
        assert output.success is False
        assert output.error is not None
        assert output.error.type == ExecutionErrorType.AUTH_ERROR
    
    def test_execute_query_output_large_result(self):
        """测试大结果集标志"""
        output = ExecuteQueryOutput.ok(
            data=[{"x": i} for i in range(1500)],
            row_count=1500,
            is_large_result=True,
            file_path="/tmp/result.json",
            execution_time_ms=500
        )
        assert output.is_large_result is True
        assert output.file_path == "/tmp/result.json"
        assert output.row_count == 1500
    
    def test_execute_query_input_model(self):
        """测试输入模型"""
        input_data = ExecuteQueryInput(
            vizql_query={"fields": [{"fieldCaption": "Sales"}]},
            datasource_luid="test_ds"
        )
        assert input_data.datasource_luid == "test_ds"
        assert input_data.vizql_query is not None


class TestExecutionErrorTypes:
    """测试错误类型枚举"""
    
    def test_error_type_enum_values(self):
        """测试错误类型枚举值"""
        assert ExecutionErrorType.EXECUTION_FAILED.value == "execution_failed"
        assert ExecutionErrorType.TIMEOUT.value == "timeout"
        assert ExecutionErrorType.AUTH_ERROR.value == "auth_error"
        assert ExecutionErrorType.INVALID_QUERY.value == "invalid_query"
        assert ExecutionErrorType.MISSING_INPUT.value == "missing_input"
        assert ExecutionErrorType.API_ERROR.value == "api_error"


class TestClassifyError:
    """测试错误分类函数"""
    
    def test_classify_timeout_error(self):
        """测试超时错误分类"""
        assert _classify_error("Connection timed out") == ExecutionErrorType.TIMEOUT
        assert _classify_error("Request timeout") == ExecutionErrorType.TIMEOUT
    
    def test_classify_auth_error(self):
        """测试认证错误分类"""
        assert _classify_error("Unauthorized access") == ExecutionErrorType.AUTH_ERROR
        assert _classify_error("401 Unauthorized") == ExecutionErrorType.AUTH_ERROR
        assert _classify_error("Auth token expired") == ExecutionErrorType.AUTH_ERROR
    
    def test_classify_invalid_query_error(self):
        """测试无效查询错误分类"""
        assert _classify_error("Invalid query syntax") == ExecutionErrorType.INVALID_QUERY
        assert _classify_error("Malformed request") == ExecutionErrorType.INVALID_QUERY
    
    def test_classify_api_error(self):
        """测试 API 错误分类"""
        assert _classify_error("VizQL API error") == ExecutionErrorType.API_ERROR
        assert _classify_error("API rate limit exceeded") == ExecutionErrorType.API_ERROR
    
    def test_classify_generic_error(self):
        """测试通用错误分类"""
        assert _classify_error("Unknown error") == ExecutionErrorType.EXECUTION_FAILED
        assert _classify_error("") == ExecutionErrorType.EXECUTION_FAILED
        assert _classify_error("Something went wrong") == ExecutionErrorType.EXECUTION_FAILED


class TestExecuteQueryAsync:
    """测试 execute_query_async 函数"""
    
    @pytest.mark.asyncio
    async def test_missing_input(self):
        """测试缺少输入"""
        result = await execute_query_async(
            vizql_query=None,
            datasource_luid="test_ds"
        )
        assert result.success is False
        assert result.error is not None
        assert result.error.type == ExecutionErrorType.MISSING_INPUT
    
    @pytest.mark.asyncio
    async def test_empty_vizql_query(self):
        """测试空的 vizql_query"""
        result = await execute_query_async(
            vizql_query={},
            datasource_luid="test_ds"
        )
        # 空字典也被视为缺少输入
        assert result.success is False
        assert result.error is not None
    
    @pytest.mark.asyncio
    async def test_successful_execution_with_mock(self):
        """测试成功执行（使用 mock）"""
        mock_result = {
            'data': [{'Sales': 100}, {'Sales': 200}],
            'columns': [{'fieldCaption': 'Sales', 'dataType': 'REAL'}],
            'queryId': 'q123'
        }
        
        mock_auth_ctx = MagicMock()
        mock_auth_ctx.api_key = "test_key"
        mock_auth_ctx.site = "test_site"
        mock_auth_ctx.domain = "test.tableau.com"
        mock_auth_ctx.auth_method = "pat"
        mock_auth_ctx.remaining_seconds = 3600
        
        with patch(
            'tableau_assistant.src.platforms.tableau.ensure_valid_auth_async',
            new_callable=AsyncMock,
            return_value=mock_auth_ctx
        ):
            with patch(
                'tableau_assistant.src.platforms.tableau.vizql_client.VizQLClient'
            ) as MockClient:
                mock_client_instance = MagicMock()
                mock_client_instance.query_datasource_async = AsyncMock(return_value=mock_result)
                mock_client_instance.close = MagicMock()
                MockClient.return_value = mock_client_instance
                
                result = await execute_query_async(
                    vizql_query={"fields": [{"fieldCaption": "Sales"}]},
                    datasource_luid="test_ds"
                )
                
                assert result.success is True
                assert result.row_count == 2
                assert result.query_id == "q123"
    
    @pytest.mark.asyncio
    async def test_large_result_detection(self):
        """测试大结果集检测"""
        # 创建超过阈值的数据
        large_data = [{'x': i} for i in range(LARGE_RESULT_THRESHOLD + 100)]
        mock_result = {
            'data': large_data,
            'columns': [{'fieldCaption': 'x', 'dataType': 'INTEGER'}],
            'queryId': 'q456'
        }
        
        mock_auth_ctx = MagicMock()
        mock_auth_ctx.api_key = "test_key"
        mock_auth_ctx.site = "test_site"
        mock_auth_ctx.domain = "test.tableau.com"
        mock_auth_ctx.auth_method = "pat"
        mock_auth_ctx.remaining_seconds = 3600
        
        with patch(
            'tableau_assistant.src.platforms.tableau.ensure_valid_auth_async',
            new_callable=AsyncMock,
            return_value=mock_auth_ctx
        ):
            with patch(
                'tableau_assistant.src.platforms.tableau.vizql_client.VizQLClient'
            ) as MockClient:
                mock_client_instance = MagicMock()
                mock_client_instance.query_datasource_async = AsyncMock(return_value=mock_result)
                mock_client_instance.close = MagicMock()
                MockClient.return_value = mock_client_instance
                
                result = await execute_query_async(
                    vizql_query={"fields": [{"fieldCaption": "x"}]},
                    datasource_luid="test_ds"
                )
                
                assert result.success is True
                assert result.is_large_result is True
                assert result.row_count > LARGE_RESULT_THRESHOLD
    
    @pytest.mark.asyncio
    async def test_auth_error(self):
        """测试认证错误"""
        from tableau_assistant.src.platforms.tableau import TableauAuthError
        
        with patch(
            'tableau_assistant.src.platforms.tableau.ensure_valid_auth_async',
            new_callable=AsyncMock,
            side_effect=TableauAuthError("Invalid credentials")
        ):
            result = await execute_query_async(
                vizql_query={"fields": [{"fieldCaption": "Sales"}]},
                datasource_luid="test_ds"
            )
            
            assert result.success is False
            assert result.error is not None
            assert result.error.type == ExecutionErrorType.AUTH_ERROR
    
    @pytest.mark.asyncio
    async def test_execution_exception(self):
        """测试执行异常"""
        mock_auth_ctx = MagicMock()
        mock_auth_ctx.api_key = "test_key"
        mock_auth_ctx.site = "test_site"
        mock_auth_ctx.domain = "test.tableau.com"
        mock_auth_ctx.auth_method = "pat"
        mock_auth_ctx.remaining_seconds = 3600
        
        with patch(
            'tableau_assistant.src.platforms.tableau.ensure_valid_auth_async',
            new_callable=AsyncMock,
            return_value=mock_auth_ctx
        ):
            with patch(
                'tableau_assistant.src.platforms.tableau.vizql_client.VizQLClient'
            ) as MockClient:
                mock_client_instance = MagicMock()
                mock_client_instance.query_datasource_async = AsyncMock(
                    side_effect=Exception("Connection failed")
                )
                mock_client_instance.close = MagicMock()
                MockClient.return_value = mock_client_instance
                
                result = await execute_query_async(
                    vizql_query={"fields": [{"fieldCaption": "Sales"}]},
                    datasource_luid="test_ds"
                )
                
                assert result.success is False
                assert result.error is not None
                assert result.error.type == ExecutionErrorType.EXECUTION_FAILED


class TestExecuteQueryOutputDefaults:
    """测试输出默认值"""
    
    def test_output_defaults(self):
        """测试默认值"""
        output = ExecuteQueryOutput(success=True)
        assert output.data is None
        assert output.columns is None
        assert output.row_count == 0
        assert output.query_id is None
        assert output.file_path is None
        assert output.is_large_result is False
        assert output.execution_time_ms == 0
    
    def test_large_result_threshold_value(self):
        """测试大结果集阈值"""
        assert LARGE_RESULT_THRESHOLD == 1000
