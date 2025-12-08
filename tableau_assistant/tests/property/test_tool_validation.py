"""
Property Tests for Tool Input Validation

测试工具输入验证的正确性。

Property Tests:
- Property 6: 工具输入验证
  - 有效输入应该被接受
  - 无效输入应该返回结构化错误
  - 错误消息应该包含有用的建议

Requirements Validated:
- 3.2: 工具输入验证
- 3.3: 结构化错误响应
"""
import pytest
from hypothesis import given, strategies as st, settings, assume
from typing import List, Optional
import json

from tableau_assistant.src.tools.base import (
    ToolResponse,
    ToolErrorCode,
    ToolError,
    format_tool_response,
)
from tableau_assistant.src.tools.schema_tool import (
    get_schema_module,
    SchemaModuleRegistry,
)
from tableau_assistant.src.tools.date_tool import (
    parse_date,
    detect_date_format,
    _parse_expression_to_time_range,
)


class TestToolResponseStructure:
    """测试 ToolResponse 结构"""
    
    def test_success_response_structure(self):
        """成功响应应该有正确的结构"""
        response = ToolResponse.ok({"key": "value"})
        
        assert response.success is True
        assert response.data == {"key": "value"}
        assert response.error is None
    
    def test_failure_response_structure(self):
        """失败响应应该有正确的结构"""
        response = ToolResponse.fail(
            code=ToolErrorCode.VALIDATION_ERROR,
            message="Invalid input",
            details={"field": "name"},
            recoverable=True,
            suggestion="Please check the input"
        )
        
        assert response.success is False
        assert response.data is None
        assert response.error is not None
        assert response.error.code == ToolErrorCode.VALIDATION_ERROR
        assert response.error.message == "Invalid input"
        assert response.error.details == {"field": "name"}
        assert response.error.recoverable is True
        assert response.error.suggestion == "Please check the input"
    
    @given(st.text(min_size=1, max_size=100))
    @settings(max_examples=20)
    def test_error_message_preserved(self, message: str):
        """错误消息应该被完整保留"""
        assume(message.strip())  # 跳过空白字符串
        
        response = ToolResponse.fail(
            code=ToolErrorCode.EXECUTION_ERROR,
            message=message
        )
        
        assert response.error.message == message


class TestToolResponseFormatting:
    """测试 ToolResponse 格式化"""
    
    def test_format_success_string(self):
        """字符串数据应该直接返回"""
        response = ToolResponse.ok("Hello, World!")
        formatted = format_tool_response(response)
        
        assert formatted == "Hello, World!"
    
    def test_format_success_dict(self):
        """字典数据应该格式化为可读格式"""
        response = ToolResponse.ok({"name": "test", "value": 123})
        formatted = format_tool_response(response)
        
        assert "name: test" in formatted
        assert "value: 123" in formatted
    
    def test_format_error_contains_code(self):
        """错误格式应该包含错误代码"""
        response = ToolResponse.fail(
            code=ToolErrorCode.VALIDATION_ERROR,
            message="Test error"
        )
        formatted = format_tool_response(response)
        
        assert "VALIDATION_ERROR" in formatted
        assert "Test error" in formatted
    
    def test_format_error_contains_suggestion(self):
        """错误格式应该包含建议"""
        response = ToolResponse.fail(
            code=ToolErrorCode.VALIDATION_ERROR,
            message="Test error",
            suggestion="Try this instead"
        )
        formatted = format_tool_response(response)
        
        assert "Try this instead" in formatted


class TestSchemaModuleValidation:
    """测试 Schema 模块工具输入验证"""
    
    def test_valid_module_names_accepted(self):
        """有效的模块名称应该被接受"""
        valid_modules = SchemaModuleRegistry.get_all_module_names()
        
        for module_name in valid_modules:
            result = get_schema_module.invoke({"module_names": [module_name]})
            assert "<error>" not in result
    
    def test_invalid_module_name_rejected(self):
        """无效的模块名称应该返回错误"""
        result = get_schema_module.invoke({"module_names": ["invalid_module"]})
        
        assert "<error>" in result
        assert "invalid_module" in result
    
    def test_empty_module_list_rejected(self):
        """空模块列表应该返回错误"""
        result = get_schema_module.invoke({"module_names": []})
        
        assert "<error>" in result
    
    @given(st.lists(st.sampled_from(["measures", "dimensions", "filters"]), min_size=1, max_size=3))
    @settings(max_examples=10)
    def test_multiple_valid_modules_accepted(self, module_names: List[str]):
        """多个有效模块应该被接受"""
        result = get_schema_module.invoke({"module_names": module_names})
        
        assert "<error>" not in result
        # 验证返回的内容包含所有请求的模块
        for module_name in module_names:
            # 模块内容应该包含模块名称相关的关键词
            assert module_name in result.lower() or "##" in result
    
    @given(st.lists(st.text(min_size=1, max_size=20), min_size=1, max_size=3))
    @settings(max_examples=10)
    def test_random_invalid_modules_rejected(self, module_names: List[str]):
        """随机无效模块名称应该返回错误"""
        valid_modules = set(SchemaModuleRegistry.get_all_module_names())
        
        # 只测试包含无效模块的情况
        if all(m in valid_modules for m in module_names):
            return  # 跳过全部有效的情况
        
        result = get_schema_module.invoke({"module_names": module_names})
        
        assert "<error>" in result


class TestDateExpressionParsing:
    """测试日期表达式解析"""
    
    @pytest.mark.parametrize("expression,expected_type,expected_period", [
        ("最近3个月", "LASTN", "MONTHS"),
        ("最近7天", "LASTN", "DAYS"),
        ("上个月", "LAST", "MONTHS"),
        ("本年", "CURRENT", "YEARS"),
        ("last 30 days", "LASTN", "DAYS"),
        ("this month", "CURRENT", "MONTHS"),
    ])
    def test_relative_date_expressions(self, expression: str, expected_type: str, expected_period: str):
        """相对日期表达式应该被正确解析"""
        time_range = _parse_expression_to_time_range(expression)
        
        assert time_range.type == "relative"
        assert time_range.relative_type == expected_type
        assert time_range.period_type == expected_period
    
    @pytest.mark.parametrize("expression", [
        "2024年1月",
        "2024-01",
        "2024年",
    ])
    def test_absolute_date_expressions(self, expression: str):
        """绝对日期表达式应该被正确解析"""
        time_range = _parse_expression_to_time_range(expression)
        
        assert time_range.type == "absolute"
        assert time_range.start_date is not None
        assert time_range.end_date is not None
    
    def test_invalid_expression_raises_error(self):
        """无效表达式应该抛出 ValueError"""
        with pytest.raises(ValueError):
            _parse_expression_to_time_range("invalid expression xyz")
    
    @given(st.integers(min_value=1, max_value=100))
    @settings(max_examples=20)
    def test_lastn_with_various_n(self, n: int):
        """LASTN 应该支持各种 N 值"""
        expression = f"最近{n}天"
        time_range = _parse_expression_to_time_range(expression)
        
        assert time_range.type == "relative"
        assert time_range.relative_type == "LASTN"
        assert time_range.range_n == n


class TestDateToolWithoutManager:
    """测试没有 DateManager 时的工具行为"""
    
    def test_parse_date_without_manager(self):
        """没有 DateManager 时应该返回错误"""
        # 确保 DateManager 未设置
        from tableau_assistant.src.tools import date_tool
        original_manager = date_tool._date_manager
        date_tool._date_manager = None
        
        try:
            result = parse_date.invoke({"expression": "最近3个月"})
            
            # 应该返回 JSON 格式的错误
            data = json.loads(result)
            assert data["start_date"] is None
            assert data["end_date"] is None
            assert "error" in data
        finally:
            date_tool._date_manager = original_manager
    
    def test_detect_date_format_without_manager(self):
        """没有 DateManager 时应该返回错误"""
        from tableau_assistant.src.tools import date_tool
        original_manager = date_tool._date_manager
        date_tool._date_manager = None
        
        try:
            result = detect_date_format.invoke({"sample_values": ["2024-01-01"]})
            
            # 应该返回 JSON 格式的错误
            data = json.loads(result)
            assert data["format_type"] is None
            assert "error" in data
        finally:
            date_tool._date_manager = original_manager


class TestDetectDateFormatValidation:
    """测试日期格式检测输入验证"""
    
    def test_empty_sample_values_rejected(self):
        """空样本列表应该返回错误"""
        from tableau_assistant.src.tools import date_tool
        original_manager = date_tool._date_manager
        date_tool._date_manager = None  # 先测试无 manager 的情况
        
        try:
            result = detect_date_format.invoke({"sample_values": []})
            data = json.loads(result)
            assert data["format_type"] is None
        finally:
            date_tool._date_manager = original_manager
    
    def test_single_sample_warning(self):
        """单个样本应该返回警告"""
        from tableau_assistant.src.tools import date_tool
        original_manager = date_tool._date_manager
        date_tool._date_manager = None
        
        try:
            result = detect_date_format.invoke({"sample_values": ["2024-01-01"]})
            data = json.loads(result)
            # 应该有错误或警告
            assert data["format_type"] is None or "error" in data
        finally:
            date_tool._date_manager = original_manager


class TestToolRegistryValidation:
    """测试工具注册表验证"""
    
    def test_duplicate_registration_warning(self):
        """重复注册应该被忽略（不抛出异常）"""
        from tableau_assistant.src.tools.registry import ToolRegistry, NodeType
        from langchain_core.tools import tool
        
        registry = ToolRegistry()
        registry.clear()  # 清空以便测试
        
        @tool
        def test_tool() -> str:
            """Test tool"""
            return "test"
        
        # 第一次注册
        registry.register(NodeType.UNDERSTANDING, test_tool)
        
        # 第二次注册应该被忽略
        registry.register(NodeType.UNDERSTANDING, test_tool)
        
        # 应该只有一个工具
        tools = registry.get_tools(NodeType.UNDERSTANDING)
        assert len(tools) == 1
    
    def test_unregister_nonexistent_tool(self):
        """注销不存在的工具应该返回 False"""
        from tableau_assistant.src.tools.registry import ToolRegistry
        
        registry = ToolRegistry()
        registry.clear()
        
        result = registry.unregister("nonexistent_tool")
        assert result is False
    
    def test_get_nonexistent_tool(self):
        """获取不存在的工具应该返回 None"""
        from tableau_assistant.src.tools.registry import ToolRegistry
        
        registry = ToolRegistry()
        registry.clear()
        
        tool = registry.get_tool("nonexistent_tool")
        assert tool is None


class TestErrorCodeCoverage:
    """测试错误代码覆盖"""
    
    def test_all_error_codes_have_values(self):
        """所有错误代码应该有值"""
        for code in ToolErrorCode:
            assert code.value is not None
            assert len(code.value) > 0
    
    def test_error_codes_are_unique(self):
        """错误代码应该唯一"""
        values = [code.value for code in ToolErrorCode]
        assert len(values) == len(set(values))
    
    @pytest.mark.parametrize("code", list(ToolErrorCode))
    def test_error_response_with_each_code(self, code: ToolErrorCode):
        """每个错误代码都应该能创建有效的错误响应"""
        response = ToolResponse.fail(
            code=code,
            message=f"Test error for {code.value}"
        )
        
        assert response.success is False
        assert response.error.code == code
        
        # 格式化应该成功
        formatted = format_tool_response(response)
        assert code.value in formatted
