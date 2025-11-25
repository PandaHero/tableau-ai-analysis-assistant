"""DeepAgents 工具的单元测试"""
import pytest
from unittest.mock import Mock, AsyncMock, patch
from tableau_assistant.src.models.metadata import Metadata, FieldMetadata
from tableau_assistant.src.deepagents.tools import parse_date, build_vizql_query


# ============= Fixtures =============

@pytest.fixture
def mock_metadata():
    """创建模拟的 Metadata 对象"""
    fields = [
        FieldMetadata(
            name="Region",
            fieldCaption="Region",
            role="dimension",
            dataType="STRING",
            category="地理",
            level=1
        ),
        FieldMetadata(
            name="Sales",
            fieldCaption="Sales",
            role="measure",
            dataType="REAL",
            aggregation="SUM"
        ),
    ]
    
    return Metadata(
        datasource_luid="test-luid-123",
        datasource_name="Test Datasource",
        fields=fields,
        field_count=2,
        dimension_hierarchy={
            "Region": {
                "category": "地理",
                "level": 1,
                "granularity": "省份"
            }
        }
    )


@pytest.fixture
def mock_runtime(mock_metadata):
    """创建模拟的 Runtime"""
    runtime = Mock()
    runtime.context = Mock()
    runtime.context.datasource_luid = "test-luid-123"
    runtime.store = Mock()
    return runtime


@pytest.fixture
def mock_metadata_manager(mock_metadata):
    """创建模拟的 MetadataManager"""
    manager = Mock()
    manager.get_metadata_async = AsyncMock(return_value=mock_metadata)
    return manager


# ============= get_metadata 工具测试 =============

class TestGetMetadataTool:
    """get_metadata 工具测试套件"""
    
    @pytest.mark.asyncio
    async def test_get_metadata_success(self, mock_runtime, mock_metadata_manager, mock_metadata):
        """测试成功获取元数据"""
        from tableau_assistant.src.deepagents.tools.get_metadata import get_metadata
        
        with patch('langgraph.runtime.get_runtime', return_value=mock_runtime):
            with patch('tableau_assistant.src.components.metadata_manager.MetadataManager', return_value=mock_metadata_manager):
                # 调用工具
                result = await get_metadata.ainvoke({})
                
                # 验证结果
                assert result is not None
                assert result["datasource_luid"] == "test-luid-123"
                assert result["datasource_name"] == "Test Datasource"
                assert result["field_count"] == 2
                assert len(result["fields"]) == 2
                
                # 验证调用参数
                mock_metadata_manager.get_metadata_async.assert_called_once_with(
                    use_cache=True,
                    enhance=True
                )
    
    @pytest.mark.asyncio
    async def test_get_metadata_force_refresh(self, mock_runtime, mock_metadata_manager):
        """测试强制刷新元数据"""
        from tableau_assistant.src.deepagents.tools.get_metadata import get_metadata
        
        with patch('langgraph.runtime.get_runtime', return_value=mock_runtime):
            with patch('tableau_assistant.src.components.metadata_manager.MetadataManager', return_value=mock_metadata_manager):
                # 调用工具（强制刷新）
                result = await get_metadata.ainvoke({"force_refresh": True})
                
                # 验证调用参数（use_cache 应该为 False）
                mock_metadata_manager.get_metadata_async.assert_called_once_with(
                    use_cache=False,
                    enhance=True
                )
    
    @pytest.mark.asyncio
    async def test_get_metadata_no_enhance(self, mock_runtime, mock_metadata_manager):
        """测试不增强元数据"""
        from tableau_assistant.src.deepagents.tools.get_metadata import get_metadata
        
        with patch('langgraph.runtime.get_runtime', return_value=mock_runtime):
            with patch('tableau_assistant.src.components.metadata_manager.MetadataManager', return_value=mock_metadata_manager):
                # 调用工具（不增强）
                result = await get_metadata.ainvoke({"enhance": False})
                
                # 验证调用参数
                mock_metadata_manager.get_metadata_async.assert_called_once_with(
                    use_cache=True,
                    enhance=False
                )
    
    @pytest.mark.asyncio
    async def test_get_metadata_retry_on_connection_error(self, mock_runtime):
        """测试连接错误时的重试机制"""
        from tableau_assistant.src.deepagents.tools.get_metadata import get_metadata
        
        # 创建一个会失败2次然后成功的 mock
        mock_manager = Mock()
        call_count = 0
        
        async def mock_get_metadata_async(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Network error")
            # 第3次调用成功
            return Metadata(
                datasource_luid="test-luid-123",
                datasource_name="Test",
                fields=[],
                field_count=0
            )
        
        mock_manager.get_metadata_async = mock_get_metadata_async
        
        with patch('langgraph.runtime.get_runtime', return_value=mock_runtime):
            with patch('tableau_assistant.src.components.metadata_manager.MetadataManager', return_value=mock_manager):
                # 调用工具（应该重试并最终成功）
                result = await get_metadata.ainvoke({})
                
                # 验证重试了3次
                assert call_count == 3
                assert result["datasource_luid"] == "test-luid-123"
    
    @pytest.mark.asyncio
    async def test_get_metadata_with_none_runtime(self):
        """测试 runtime 为 None 时的行为"""
        from tableau_assistant.src.deepagents.tools.get_metadata import get_metadata
        
        # Mock get_runtime 返回 None
        with patch('langgraph.runtime.get_runtime', return_value=None):
            # 应该在调用 MetadataManager 时失败
            with pytest.raises(Exception):  # MetadataManager 会抛出异常
                await get_metadata.ainvoke({})
    
    @pytest.mark.asyncio
    async def test_get_metadata_max_retries_exceeded(self, mock_runtime):
        """测试超过最大重试次数"""
        from tableau_assistant.src.deepagents.tools.get_metadata import get_metadata
        
        # 创建一个总是失败的 mock
        mock_manager = Mock()
        mock_manager.get_metadata_async = AsyncMock(side_effect=ConnectionError("Network error"))
        
        with patch('langgraph.runtime.get_runtime', return_value=mock_runtime):
            with patch('tableau_assistant.src.components.metadata_manager.MetadataManager', return_value=mock_manager):
                # 应该在3次重试后抛出异常
                with pytest.raises(RuntimeError, match="无法获取数据源元数据"):
                    await get_metadata.ainvoke({})
                
                # 验证调用了3次
                assert mock_manager.get_metadata_async.call_count == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])



# ============= parse_date 工具测试 =============

class TestParseDateTool:
    """测试 parse_date 工具"""
    
    def test_parse_absolute_year(self):
        """测试解析绝对年份"""
        result = parse_date.invoke({
            "time_range_json": '{"type": "absolute", "value": "2024"}'
        })
        
        assert result["start_date"] == "2024-01-01"
        assert result["end_date"] == "2024-12-31"
        assert result["adjusted"] is False
    
    def test_parse_absolute_quarter(self):
        """测试解析绝对季度"""
        result = parse_date.invoke({
            "time_range_json": '{"type": "absolute", "value": "2024-Q1"}'
        })
        
        assert result["start_date"] == "2024-01-01"
        assert result["end_date"] == "2024-03-31"
        assert result["adjusted"] is False
    
    def test_parse_absolute_month(self):
        """测试解析绝对月份"""
        result = parse_date.invoke({
            "time_range_json": '{"type": "absolute", "value": "2024-03"}'
        })
        
        assert result["start_date"] == "2024-03-01"
        assert result["end_date"] == "2024-03-31"
        assert result["adjusted"] is False
    
    def test_parse_absolute_date(self):
        """测试解析绝对日期"""
        result = parse_date.invoke({
            "time_range_json": '{"type": "absolute", "value": "2024-03-15"}'
        })
        
        assert result["start_date"] == "2024-03-15"
        assert result["end_date"] == "2024-03-15"
        assert result["adjusted"] is False
    
    def test_parse_absolute_date_range(self):
        """测试解析绝对日期范围"""
        result = parse_date.invoke({
            "time_range_json": '{"type": "absolute", "start_date": "2024-01-01", "end_date": "2024-03-31"}'
        })
        
        assert result["start_date"] == "2024-01-01"
        assert result["end_date"] == "2024-03-31"
        assert result["adjusted"] is False
    
    def test_parse_relative_last_n_months(self):
        """测试解析相对时间 - 最近N个月"""
        result = parse_date.invoke({
            "time_range_json": '{"type": "relative", "relative_type": "LASTN", "period_type": "MONTHS", "range_n": 3}',
            "reference_date": "2024-12-31"
        })
        
        assert result["start_date"] == "2024-10-01"
        assert result["end_date"] == "2024-12-31"
        assert result["adjusted"] is False
    
    def test_parse_relative_last_n_days(self):
        """测试解析相对时间 - 最近N天"""
        result = parse_date.invoke({
            "time_range_json": '{"type": "relative", "relative_type": "LASTN", "period_type": "DAYS", "range_n": 7}',
            "reference_date": "2024-12-31"
        })
        
        assert result["start_date"] == "2024-12-25"
        assert result["end_date"] == "2024-12-31"
        assert result["adjusted"] is False
    
    def test_parse_with_max_date_adjustment(self):
        """测试使用 max_date 调整日期范围"""
        result = parse_date.invoke({
            "time_range_json": '{"type": "absolute", "value": "2024"}',
            "max_date": "2024-06-30"
        })
        
        assert result["start_date"] == "2024-01-01"
        assert result["end_date"] == "2024-06-30"  # 被调整
        assert result["adjusted"] is True
    
    def test_parse_with_max_date_no_adjustment(self):
        """测试使用 max_date 但无需调整"""
        result = parse_date.invoke({
            "time_range_json": '{"type": "absolute", "start_date": "2024-01-01", "end_date": "2024-03-31"}',
            "max_date": "2024-12-31"
        })
        
        assert result["start_date"] == "2024-01-01"
        assert result["end_date"] == "2024-03-31"
        assert result["adjusted"] is False
    
    def test_parse_date_tool_async(self):
        """测试 parse_date 工具的异步调用"""
        import asyncio
        
        async def test_async():
            result = await parse_date.ainvoke({
                "time_range_json": '{"type": "absolute", "value": "2024-Q2"}'
            })
            return result
        
        result = asyncio.run(test_async())
        
        assert result["start_date"] == "2024-04-01"
        assert result["end_date"] == "2024-06-30"
        assert result["adjusted"] is False
    
    # ============= 边界情况测试 =============
    
    def test_parse_leap_year_february(self):
        """测试闰年2月"""
        result = parse_date.invoke({
            "time_range_json": '{"type": "absolute", "value": "2024-02"}'
        })
        
        assert result["start_date"] == "2024-02-01"
        assert result["end_date"] == "2024-02-29"  # 闰年
    
    def test_parse_non_leap_year_february(self):
        """测试非闰年2月"""
        result = parse_date.invoke({
            "time_range_json": '{"type": "absolute", "value": "2023-02"}'
        })
        
        assert result["start_date"] == "2023-02-01"
        assert result["end_date"] == "2023-02-28"  # 非闰年
    
    def test_parse_all_quarters(self):
        """测试所有季度"""
        quarters = [
            ("2024-Q1", "2024-01-01", "2024-03-31"),
            ("2024-Q2", "2024-04-01", "2024-06-30"),
            ("2024-Q3", "2024-07-01", "2024-09-30"),
            ("2024-Q4", "2024-10-01", "2024-12-31"),
        ]
        
        for quarter, expected_start, expected_end in quarters:
            result = parse_date.invoke({
                "time_range_json": f'{{"type": "absolute", "value": "{quarter}"}}'
            })
            assert result["start_date"] == expected_start
            assert result["end_date"] == expected_end
    
    def test_parse_year_boundary(self):
        """测试跨年边界"""
        result = parse_date.invoke({
            "time_range_json": '{"type": "absolute", "start_date": "2023-12-15", "end_date": "2024-01-15"}'
        })
        
        assert result["start_date"] == "2023-12-15"
        assert result["end_date"] == "2024-01-15"
    
    # ============= 相对时间测试 =============
    
    def test_parse_relative_last_year(self):
        """测试相对时间 - 去年"""
        result = parse_date.invoke({
            "time_range_json": '{"type": "relative", "relative_type": "LASTN", "period_type": "YEARS", "range_n": 1}',
            "reference_date": "2024-12-31"
        })
        
        assert result["start_date"] == "2024-01-01"
        assert result["end_date"] == "2024-12-31"
    
    def test_parse_relative_last_quarter(self):
        """测试相对时间 - 上季度"""
        result = parse_date.invoke({
            "time_range_json": '{"type": "relative", "relative_type": "LASTN", "period_type": "QUARTERS", "range_n": 1}',
            "reference_date": "2024-12-31"
        })
        
        assert result["start_date"] == "2024-10-01"
        assert result["end_date"] == "2024-12-31"
    
    def test_parse_relative_last_week(self):
        """测试相对时间 - 上周"""
        result = parse_date.invoke({
            "time_range_json": '{"type": "relative", "relative_type": "LASTN", "period_type": "WEEKS", "range_n": 1}',
            "reference_date": "2024-12-31"
        })
        
        # DateCalculator 计算周是从周一开始的，所以是 12-24 到 12-31
        assert result["start_date"] == "2024-12-24"
        assert result["end_date"] == "2024-12-31"
    
    def test_parse_relative_last_30_days(self):
        """测试相对时间 - 最近30天"""
        result = parse_date.invoke({
            "time_range_json": '{"type": "relative", "relative_type": "LASTN", "period_type": "DAYS", "range_n": 30}',
            "reference_date": "2024-12-31"
        })
        
        assert result["start_date"] == "2024-12-02"
        assert result["end_date"] == "2024-12-31"
    
    def test_parse_relative_last_6_months(self):
        """测试相对时间 - 最近6个月"""
        result = parse_date.invoke({
            "time_range_json": '{"type": "relative", "relative_type": "LASTN", "period_type": "MONTHS", "range_n": 6}',
            "reference_date": "2024-12-31"
        })
        
        assert result["start_date"] == "2024-07-01"
        assert result["end_date"] == "2024-12-31"
    
    # ============= max_date 边界测试 =============
    
    def test_parse_max_date_within_range(self):
        """测试 max_date 在范围内（无需调整）"""
        result = parse_date.invoke({
            "time_range_json": '{"type": "absolute", "start_date": "2024-01-01", "end_date": "2024-06-30"}',
            "max_date": "2024-12-31"
        })
        
        assert result["start_date"] == "2024-01-01"
        assert result["end_date"] == "2024-06-30"
        assert result["adjusted"] is False
    
    def test_parse_max_date_exact_match(self):
        """测试 max_date 正好等于 end_date"""
        result = parse_date.invoke({
            "time_range_json": '{"type": "absolute", "start_date": "2024-01-01", "end_date": "2024-06-30"}',
            "max_date": "2024-06-30"
        })
        
        assert result["start_date"] == "2024-01-01"
        assert result["end_date"] == "2024-06-30"
        assert result["adjusted"] is False
    
    def test_parse_max_date_year_adjustment(self):
        """测试 max_date 调整整年"""
        result = parse_date.invoke({
            "time_range_json": '{"type": "absolute", "value": "2024"}',
            "max_date": "2024-03-31"
        })
        
        assert result["start_date"] == "2024-01-01"
        assert result["end_date"] == "2024-03-31"
        assert result["adjusted"] is True
    
    def test_parse_max_date_quarter_adjustment(self):
        """测试 max_date 调整季度"""
        result = parse_date.invoke({
            "time_range_json": '{"type": "absolute", "value": "2024-Q2"}',
            "max_date": "2024-05-15"
        })
        
        assert result["start_date"] == "2024-04-01"
        assert result["end_date"] == "2024-05-15"
        assert result["adjusted"] is True
    
    def test_parse_max_date_relative_adjustment(self):
        """测试 max_date 调整相对时间"""
        result = parse_date.invoke({
            "time_range_json": '{"type": "relative", "relative_type": "LASTN", "period_type": "MONTHS", "range_n": 6}',
            "reference_date": "2024-12-31",
            "max_date": "2024-10-31"
        })
        
        assert result["start_date"] == "2024-07-01"
        assert result["end_date"] == "2024-10-31"
        assert result["adjusted"] is True
    
    # ============= 错误处理测试 =============
    
    def test_parse_invalid_json(self):
        """测试无效的 JSON"""
        import json
        
        with pytest.raises(json.JSONDecodeError):
            parse_date.invoke({
                "time_range_json": 'invalid json'
            })
    
    def test_parse_invalid_time_range_type(self):
        """测试无效的 TimeRange 类型"""
        with pytest.raises(Exception):  # Pydantic validation error
            parse_date.invoke({
                "time_range_json": '{"type": "invalid_type"}'
            })
    
    def test_parse_missing_required_fields_absolute(self):
        """测试绝对时间缺少必需字段"""
        with pytest.raises(ValueError):
            parse_date.invoke({
                "time_range_json": '{"type": "absolute"}'
            })
    
    def test_parse_missing_required_fields_relative(self):
        """测试相对时间缺少必需字段"""
        with pytest.raises(ValueError):
            parse_date.invoke({
                "time_range_json": '{"type": "relative"}'
            })
    
    def test_parse_invalid_date_format(self):
        """测试无效的日期格式"""
        with pytest.raises(ValueError):
            parse_date.invoke({
                "time_range_json": '{"type": "absolute", "value": "2024/01/01"}'
            })
    
    def test_parse_invalid_quarter(self):
        """测试无效的季度"""
        with pytest.raises(ValueError):
            parse_date.invoke({
                "time_range_json": '{"type": "absolute", "value": "2024-Q5"}'
            })
    
    def test_parse_invalid_month(self):
        """测试无效的月份"""
        with pytest.raises(ValueError):
            parse_date.invoke({
                "time_range_json": '{"type": "absolute", "value": "2024-13"}'
            })
    
    def test_parse_invalid_date(self):
        """测试无效的日期"""
        with pytest.raises(ValueError):
            parse_date.invoke({
                "time_range_json": '{"type": "absolute", "value": "2024-02-30"}'
            })
    
    def test_parse_start_after_end(self):
        """测试开始日期晚于结束日期"""
        with pytest.raises(ValueError):
            parse_date.invoke({
                "time_range_json": '{"type": "absolute", "start_date": "2024-12-31", "end_date": "2024-01-01"}'
            })
    
    # ============= 特殊场景测试 =============
    
    def test_parse_single_day(self):
        """测试单日查询"""
        result = parse_date.invoke({
            "time_range_json": '{"type": "absolute", "value": "2024-06-15"}'
        })
        
        assert result["start_date"] == "2024-06-15"
        assert result["end_date"] == "2024-06-15"
    
    def test_parse_month_with_31_days(self):
        """测试31天的月份"""
        months_31 = ["01", "03", "05", "07", "08", "10", "12"]
        
        for month in months_31:
            result = parse_date.invoke({
                "time_range_json": f'{{"type": "absolute", "value": "2024-{month}"}}'
            })
            assert result["end_date"] == f"2024-{month}-31"
    
    def test_parse_month_with_30_days(self):
        """测试30天的月份"""
        months_30 = ["04", "06", "09", "11"]
        
        for month in months_30:
            result = parse_date.invoke({
                "time_range_json": f'{{"type": "absolute", "value": "2024-{month}"}}'
            })
            assert result["end_date"] == f"2024-{month}-30"
    
    def test_parse_without_reference_date(self):
        """测试不提供 reference_date（应使用默认值）"""
        result = parse_date.invoke({
            "time_range_json": '{"type": "absolute", "value": "2024"}'
        })
        
        assert result["start_date"] == "2024-01-01"
        assert result["end_date"] == "2024-12-31"
    
    def test_parse_cache_behavior(self):
        """测试缓存行为（相同输入应返回相同结果）"""
        time_range_json = '{"type": "absolute", "value": "2024-Q3"}'
        
        result1 = parse_date.invoke({"time_range_json": time_range_json})
        result2 = parse_date.invoke({"time_range_json": time_range_json})
        
        assert result1 == result2
    
    def test_parse_cache_with_different_max_date(self):
        """测试不同 max_date 不应使用相同缓存"""
        time_range_json = '{"type": "absolute", "value": "2024"}'
        
        result1 = parse_date.invoke({
            "time_range_json": time_range_json,
            "max_date": "2024-06-30"
        })
        
        result2 = parse_date.invoke({
            "time_range_json": time_range_json,
            "max_date": "2024-09-30"
        })
        
        assert result1["end_date"] == "2024-06-30"
        assert result2["end_date"] == "2024-09-30"
        assert result1 != result2



# ============= build_vizql_query 工具测试 =============

class TestBuildVizQLQueryTool:
    """测试 build_vizql_query 工具"""
    
    @pytest.fixture
    def sample_metadata_json(self):
        """创建完整的示例元数据 JSON"""
        return '''{
            "datasource_name": "Superstore",
            "datasource_luid": "test-luid-123",
            "field_count": 5,
            "fields": [
                {
                    "name": "Region",
                    "fieldCaption": "Region",
                    "role": "dimension",
                    "dataType": "STRING",
                    "category": "地理"
                },
                {
                    "name": "Sales",
                    "fieldCaption": "Sales",
                    "role": "measure",
                    "dataType": "REAL",
                    "aggregation": "SUM"
                },
                {
                    "name": "Order Date",
                    "fieldCaption": "Order Date",
                    "role": "dimension",
                    "dataType": "DATE"
                },
                {
                    "name": "Profit",
                    "fieldCaption": "Profit",
                    "role": "measure",
                    "dataType": "REAL",
                    "aggregation": "SUM"
                },
                {
                    "name": "Category",
                    "fieldCaption": "Category",
                    "role": "dimension",
                    "dataType": "STRING"
                }
            ]
        }'''
    
    @pytest.fixture
    def simple_query_subtask_json(self):
        """创建简单查询的 subtask JSON（维度 + 度量）"""
        return '''{
            "question_id": "q1",
            "question_text": "Sales by Region",
            "stage": 1,
            "depends_on": [],
            "rationale": "Query sales grouped by region",
            "dimension_intents": [
                {
                    "business_term": "Region",
                    "technical_field": "Region",
                    "field_data_type": "STRING"
                }
            ],
            "measure_intents": [
                {
                    "business_term": "Sales",
                    "technical_field": "Sales",
                    "field_data_type": "REAL",
                    "aggregation": "SUM"
                }
            ]
        }'''
    
    @pytest.fixture
    def date_field_query_subtask_json(self):
        """创建包含日期字段的 subtask JSON"""
        return '''{
            "question_id": "q2",
            "question_text": "Sales by Month",
            "stage": 1,
            "depends_on": [],
            "rationale": "Query sales grouped by month",
            "date_field_intents": [
                {
                    "business_term": "Month",
                    "technical_field": "Order Date",
                    "field_data_type": "DATE",
                    "date_function": "MONTH"
                }
            ],
            "measure_intents": [
                {
                    "business_term": "Sales",
                    "technical_field": "Sales",
                    "field_data_type": "REAL",
                    "aggregation": "SUM"
                }
            ]
        }'''
    
    @pytest.fixture
    def date_filter_query_subtask_json(self):
        """创建包含日期筛选的 subtask JSON"""
        return '''{
            "question_id": "q3",
            "question_text": "Sales in 2024",
            "stage": 1,
            "depends_on": [],
            "rationale": "Query sales filtered by year 2024",
            "measure_intents": [
                {
                    "business_term": "Sales",
                    "technical_field": "Sales",
                    "field_data_type": "REAL",
                    "aggregation": "SUM"
                }
            ],
            "date_filter_intent": {
                "business_term": "2024",
                "technical_field": "Order Date",
                "field_data_type": "DATE",
                "time_range": {
                    "type": "absolute",
                    "value": "2024"
                }
            }
        }'''
    
    @pytest.fixture
    def topn_query_subtask_json(self):
        """创建包含 TopN 的 subtask JSON"""
        return '''{
            "question_id": "q4",
            "question_text": "Top 5 Regions by Sales",
            "stage": 1,
            "depends_on": [],
            "rationale": "Query top 5 regions by sales",
            "dimension_intents": [
                {
                    "business_term": "Region",
                    "technical_field": "Region",
                    "field_data_type": "STRING"
                }
            ],
            "measure_intents": [
                {
                    "business_term": "Sales",
                    "technical_field": "Sales",
                    "field_data_type": "REAL",
                    "aggregation": "SUM"
                }
            ],
            "topn_intent": {
                "business_term": "Top 5",
                "technical_field": "Region",
                "n": 5,
                "direction": "TOP"
            }
        }'''
    
    @pytest.fixture
    def filter_query_subtask_json(self):
        """创建包含筛选器的 subtask JSON"""
        return '''{
            "question_id": "q5",
            "question_text": "Sales in East Region",
            "stage": 1,
            "depends_on": [],
            "rationale": "Query sales filtered by East region",
            "dimension_intents": [
                {
                    "business_term": "Region",
                    "technical_field": "Region",
                    "field_data_type": "STRING"
                }
            ],
            "measure_intents": [
                {
                    "business_term": "Sales",
                    "technical_field": "Sales",
                    "field_data_type": "REAL",
                    "aggregation": "SUM"
                }
            ],
            "filter_intents": [
                {
                    "business_term": "East",
                    "technical_field": "Region",
                    "filter_type": "SET",
                    "values": ["East"]
                }
            ]
        }'''
    
    def test_build_simple_query(self, sample_metadata_json, simple_query_subtask_json):
        """测试构建简单查询（维度 + 度量）"""
        result = build_vizql_query.invoke({
            "subtask_json": simple_query_subtask_json,
            "metadata_json": sample_metadata_json
        })
        
        assert result["field_count"] == 2
        assert result["filter_count"] == 0
        assert result["has_date_filter"] is False
        assert result["has_topn"] is False
        assert "query" in result
        assert "fields" in result["query"]
    
    def test_build_query_with_date_field(self, sample_metadata_json, date_field_query_subtask_json):
        """测试构建包含日期字段的查询"""
        result = build_vizql_query.invoke({
            "subtask_json": date_field_query_subtask_json,
            "metadata_json": sample_metadata_json
        })
        
        assert result["field_count"] == 2
        assert result["filter_count"] == 0
    
    def test_build_query_with_date_filter(self, sample_metadata_json, date_filter_query_subtask_json):
        """测试构建包含日期筛选的查询"""
        result = build_vizql_query.invoke({
            "subtask_json": date_filter_query_subtask_json,
            "metadata_json": sample_metadata_json,
            "anchor_date": "2024-12-31"
        })
        
        assert result["field_count"] >= 1  # At least the measure
        assert result["filter_count"] >= 1  # At least the date filter
        assert result["has_date_filter"] is True
    
    def test_build_query_with_topn(self, sample_metadata_json, topn_query_subtask_json):
        """测试构建包含 TopN 的查询"""
        result = build_vizql_query.invoke({
            "subtask_json": topn_query_subtask_json,
            "metadata_json": sample_metadata_json
        })
        
        assert result["field_count"] == 2
        assert result["filter_count"] >= 1
        assert result["has_topn"] is True
    
    def test_build_query_with_filter(self, sample_metadata_json, filter_query_subtask_json):
        """测试构建包含筛选器的查询"""
        result = build_vizql_query.invoke({
            "subtask_json": filter_query_subtask_json,
            "metadata_json": sample_metadata_json
        })
        
        assert result["field_count"] == 2
        assert result["filter_count"] >= 1
    
    def test_build_query_with_anchor_date(self, sample_metadata_json):
        """测试使用 anchor_date"""
        subtask_json = '''{
            "question_id": "q6",
            "question_text": "Sales last month",
            "stage": 1,
            "depends_on": [],
            "rationale": "Query sales for last month",
            "measure_intents": [
                {
                    "business_term": "Sales",
                    "technical_field": "Sales",
                    "field_data_type": "REAL",
                    "aggregation": "SUM"
                }
            ],
            "date_filter_intent": {
                "business_term": "last month",
                "technical_field": "Order Date",
                "field_data_type": "DATE",
                "time_range": {
                    "type": "relative",
                    "relative_type": "LASTN",
                    "period_type": "MONTHS",
                    "range_n": 1
                }
            }
        }'''
        
        result = build_vizql_query.invoke({
            "subtask_json": subtask_json,
            "metadata_json": sample_metadata_json,
            "anchor_date": "2024-12-31"
        })
        
        assert result["has_date_filter"] is True
    
    def test_build_query_invalid_subtask(self, sample_metadata_json):
        """测试无效的 subtask（缺少必需字段）"""
        subtask_json = '''{
            "question_id": "q7"
        }'''
        
        with pytest.raises(Exception):  # Should raise validation error
            build_vizql_query.invoke({
                "subtask_json": subtask_json,
                "metadata_json": sample_metadata_json
            })
    
    def test_build_query_invalid_json(self, sample_metadata_json):
        """测试无效的 JSON"""
        import json
        
        with pytest.raises(json.JSONDecodeError):
            build_vizql_query.invoke({
                "subtask_json": "invalid json",
                "metadata_json": sample_metadata_json
            })
    
    def test_build_query_empty_fields(self, sample_metadata_json):
        """测试没有字段的查询（应该失败）"""
        subtask_json = '''{
            "question_id": "q8",
            "question_text": "Empty query",
            "stage": 1,
            "depends_on": [],
            "rationale": "Empty query for testing"
        }'''
        
        with pytest.raises(ValueError, match="查询必须至少包含一个字段"):
            build_vizql_query.invoke({
                "subtask_json": subtask_json,
                "metadata_json": sample_metadata_json
            })
    
    def test_build_query_async(self, sample_metadata_json, simple_query_subtask_json):
        """测试异步调用"""
        import asyncio
        
        async def test_async():
            result = await build_vizql_query.ainvoke({
                "subtask_json": simple_query_subtask_json,
                "metadata_json": sample_metadata_json
            })
            return result
        
        result = asyncio.run(test_async())
        
        assert result["field_count"] == 2
        assert result["filter_count"] == 0

    
    # ============= 复杂场景测试 =============
    
    def test_build_query_multiple_dimensions(self, sample_metadata_json):
        """测试多个维度字段"""
        subtask_json = '''{
            "question_id": "q10",
            "question_text": "Sales by Region and Category",
            "stage": 1,
            "depends_on": [],
            "rationale": "Query sales grouped by region and category",
            "dimension_intents": [
                {
                    "business_term": "Region",
                    "technical_field": "Region",
                    "field_data_type": "STRING"
                },
                {
                    "business_term": "Category",
                    "technical_field": "Category",
                    "field_data_type": "STRING"
                }
            ],
            "measure_intents": [
                {
                    "business_term": "Sales",
                    "technical_field": "Sales",
                    "field_data_type": "REAL",
                    "aggregation": "SUM"
                }
            ]
        }'''
        
        result = build_vizql_query.invoke({
            "subtask_json": subtask_json,
            "metadata_json": sample_metadata_json
        })
        
        assert result["field_count"] == 3  # 2 dimensions + 1 measure
        assert result["filter_count"] == 0
    
    def test_build_query_multiple_measures(self, sample_metadata_json):
        """测试多个度量字段"""
        subtask_json = '''{
            "question_id": "q11",
            "question_text": "Sales and Profit by Region",
            "stage": 1,
            "depends_on": [],
            "rationale": "Query sales and profit grouped by region",
            "dimension_intents": [
                {
                    "business_term": "Region",
                    "technical_field": "Region",
                    "field_data_type": "STRING"
                }
            ],
            "measure_intents": [
                {
                    "business_term": "Sales",
                    "technical_field": "Sales",
                    "field_data_type": "REAL",
                    "aggregation": "SUM"
                },
                {
                    "business_term": "Profit",
                    "technical_field": "Profit",
                    "field_data_type": "REAL",
                    "aggregation": "SUM"
                }
            ]
        }'''
        
        result = build_vizql_query.invoke({
            "subtask_json": subtask_json,
            "metadata_json": sample_metadata_json
        })
        
        assert result["field_count"] == 3  # 1 dimension + 2 measures
        assert result["filter_count"] == 0
    
    def test_build_query_with_sorting(self, sample_metadata_json):
        """测试带排序的查询"""
        subtask_json = '''{
            "question_id": "q12",
            "question_text": "Sales by Region sorted descending",
            "stage": 1,
            "depends_on": [],
            "rationale": "Query sales grouped by region with sorting",
            "dimension_intents": [
                {
                    "business_term": "Region",
                    "technical_field": "Region",
                    "field_data_type": "STRING"
                }
            ],
            "measure_intents": [
                {
                    "business_term": "Sales",
                    "technical_field": "Sales",
                    "field_data_type": "REAL",
                    "aggregation": "SUM",
                    "sort_direction": "DESC",
                    "sort_priority": 0
                }
            ]
        }'''
        
        result = build_vizql_query.invoke({
            "subtask_json": subtask_json,
            "metadata_json": sample_metadata_json
        })
        
        assert result["field_count"] == 2
        # Check that sorting is preserved in the query
        query = result["query"]
        assert "fields" in query
        # Find the measure field and check it has sortDirection
        measure_fields = [f for f in query["fields"] if "function" in f]
        assert len(measure_fields) == 1
        assert measure_fields[0].get("sortDirection") == "DESC"
    
    def test_build_query_dimension_with_countd(self, sample_metadata_json):
        """测试维度字段使用 COUNTD 聚合"""
        subtask_json = '''{
            "question_id": "q13",
            "question_text": "Count distinct regions",
            "stage": 1,
            "depends_on": [],
            "rationale": "Count unique regions",
            "dimension_intents": [
                {
                    "business_term": "Region",
                    "technical_field": "Region",
                    "field_data_type": "STRING",
                    "aggregation": "COUNTD"
                }
            ]
        }'''
        
        result = build_vizql_query.invoke({
            "subtask_json": subtask_json,
            "metadata_json": sample_metadata_json
        })
        
        assert result["field_count"] == 1
        # Check that COUNTD aggregation is applied
        query = result["query"]
        assert query["fields"][0]["function"] == "COUNTD"
    
    def test_build_query_with_multiple_filters(self, sample_metadata_json):
        """测试多个筛选器"""
        subtask_json = '''{
            "question_id": "q14",
            "question_text": "Sales in East Region for Furniture",
            "stage": 1,
            "depends_on": [],
            "rationale": "Query sales with multiple filters",
            "dimension_intents": [
                {
                    "business_term": "Region",
                    "technical_field": "Region",
                    "field_data_type": "STRING"
                }
            ],
            "measure_intents": [
                {
                    "business_term": "Sales",
                    "technical_field": "Sales",
                    "field_data_type": "REAL",
                    "aggregation": "SUM"
                }
            ],
            "filter_intents": [
                {
                    "business_term": "East",
                    "technical_field": "Region",
                    "filter_type": "SET",
                    "values": ["East"]
                },
                {
                    "business_term": "Furniture",
                    "technical_field": "Category",
                    "filter_type": "SET",
                    "values": ["Furniture"]
                }
            ]
        }'''
        
        result = build_vizql_query.invoke({
            "subtask_json": subtask_json,
            "metadata_json": sample_metadata_json
        })
        
        assert result["field_count"] == 2
        assert result["filter_count"] == 2
    
    def test_build_query_date_and_regular_filters(self, sample_metadata_json):
        """测试日期筛选 + 普通筛选"""
        subtask_json = '''{
            "question_id": "q15",
            "question_text": "Sales in East Region in 2024",
            "stage": 1,
            "depends_on": [],
            "rationale": "Query sales with date and regular filters",
            "dimension_intents": [
                {
                    "business_term": "Region",
                    "technical_field": "Region",
                    "field_data_type": "STRING"
                }
            ],
            "measure_intents": [
                {
                    "business_term": "Sales",
                    "technical_field": "Sales",
                    "field_data_type": "REAL",
                    "aggregation": "SUM"
                }
            ],
            "date_filter_intent": {
                "business_term": "2024",
                "technical_field": "Order Date",
                "field_data_type": "DATE",
                "time_range": {
                    "type": "absolute",
                    "value": "2024"
                }
            },
            "filter_intents": [
                {
                    "business_term": "East",
                    "technical_field": "Region",
                    "filter_type": "SET",
                    "values": ["East"]
                }
            ]
        }'''
        
        result = build_vizql_query.invoke({
            "subtask_json": subtask_json,
            "metadata_json": sample_metadata_json,
            "anchor_date": "2024-12-31"
        })
        
        assert result["field_count"] == 2
        assert result["filter_count"] == 2  # 1 date filter + 1 regular filter
        assert result["has_date_filter"] is True
    
    def test_build_query_date_field_and_date_filter(self, sample_metadata_json):
        """测试日期字段 + 日期筛选"""
        subtask_json = '''{
            "question_id": "q16",
            "question_text": "Monthly sales in 2024",
            "stage": 1,
            "depends_on": [],
            "rationale": "Query monthly sales filtered by year",
            "date_field_intents": [
                {
                    "business_term": "Month",
                    "technical_field": "Order Date",
                    "field_data_type": "DATE",
                    "date_function": "MONTH"
                }
            ],
            "measure_intents": [
                {
                    "business_term": "Sales",
                    "technical_field": "Sales",
                    "field_data_type": "REAL",
                    "aggregation": "SUM"
                }
            ],
            "date_filter_intent": {
                "business_term": "2024",
                "technical_field": "Order Date",
                "field_data_type": "DATE",
                "time_range": {
                    "type": "absolute",
                    "value": "2024"
                }
            }
        }'''
        
        result = build_vizql_query.invoke({
            "subtask_json": subtask_json,
            "metadata_json": sample_metadata_json,
            "anchor_date": "2024-12-31"
        })
        
        assert result["field_count"] == 2  # 1 date field + 1 measure
        assert result["filter_count"] >= 1  # At least date filter
        assert result["has_date_filter"] is True
    
    def test_build_query_all_features_combined(self, sample_metadata_json):
        """测试所有功能组合（维度 + 度量 + 日期字段 + 日期筛选 + 普通筛选 + TopN）"""
        subtask_json = '''{
            "question_id": "q17",
            "question_text": "Top 3 regions by sales in 2024 for Furniture",
            "stage": 1,
            "depends_on": [],
            "rationale": "Complex query with all features",
            "dimension_intents": [
                {
                    "business_term": "Region",
                    "technical_field": "Region",
                    "field_data_type": "STRING"
                }
            ],
            "measure_intents": [
                {
                    "business_term": "Sales",
                    "technical_field": "Sales",
                    "field_data_type": "REAL",
                    "aggregation": "SUM",
                    "sort_direction": "DESC",
                    "sort_priority": 0
                }
            ],
            "date_field_intents": [
                {
                    "business_term": "Month",
                    "technical_field": "Order Date",
                    "field_data_type": "DATE",
                    "date_function": "MONTH"
                }
            ],
            "date_filter_intent": {
                "business_term": "2024",
                "technical_field": "Order Date",
                "field_data_type": "DATE",
                "time_range": {
                    "type": "absolute",
                    "value": "2024"
                }
            },
            "filter_intents": [
                {
                    "business_term": "Furniture",
                    "technical_field": "Category",
                    "filter_type": "SET",
                    "values": ["Furniture"]
                }
            ],
            "topn_intent": {
                "business_term": "Top 3",
                "technical_field": "Region",
                "n": 3,
                "direction": "TOP"
            }
        }'''
        
        result = build_vizql_query.invoke({
            "subtask_json": subtask_json,
            "metadata_json": sample_metadata_json,
            "anchor_date": "2024-12-31"
        })
        
        assert result["field_count"] == 3  # 1 dimension + 1 measure + 1 date field
        assert result["filter_count"] == 3  # date filter + regular filter + topn
        assert result["has_date_filter"] is True
        assert result["has_topn"] is True
    
    def test_build_query_different_aggregations(self, sample_metadata_json):
        """测试不同的聚合函数"""
        aggregations = ["SUM", "AVG", "MIN", "MAX", "COUNT"]
        
        for idx, agg in enumerate(aggregations, start=100):
            subtask_json = f'''{{
                "question_id": "q{idx}",
                "question_text": "{agg} of Sales",
                "stage": 1,
                "depends_on": [],
                "rationale": "Test {agg} aggregation",
                "measure_intents": [
                    {{
                        "business_term": "Sales",
                        "technical_field": "Sales",
                        "field_data_type": "REAL",
                        "aggregation": "{agg}"
                    }}
                ]
            }}'''
            
            result = build_vizql_query.invoke({
                "subtask_json": subtask_json,
                "metadata_json": sample_metadata_json
            })
            
            assert result["field_count"] == 1
            query = result["query"]
            assert query["fields"][0]["function"] == agg
    
    def test_build_query_different_date_functions(self, sample_metadata_json):
        """测试不同的日期函数"""
        date_functions = ["YEAR", "QUARTER", "MONTH", "WEEK", "DAY"]
        
        for idx, func in enumerate(date_functions, start=200):
            subtask_json = f'''{{
                "question_id": "q{idx}",
                "question_text": "Sales by {func}",
                "stage": 1,
                "depends_on": [],
                "rationale": "Test {func} date function",
                "date_field_intents": [
                    {{
                        "business_term": "{func}",
                        "technical_field": "Order Date",
                        "field_data_type": "DATE",
                        "date_function": "{func}"
                    }}
                ],
                "measure_intents": [
                    {{
                        "business_term": "Sales",
                        "technical_field": "Sales",
                        "field_data_type": "REAL",
                        "aggregation": "SUM"
                    }}
                ]
            }}'''
            
            result = build_vizql_query.invoke({
                "subtask_json": subtask_json,
                "metadata_json": sample_metadata_json
            })
            
            assert result["field_count"] == 2
    
    def test_build_query_topn_bottom(self, sample_metadata_json):
        """测试 Bottom N"""
        subtask_json = '''{
            "question_id": "q18",
            "question_text": "Bottom 5 Regions by Sales",
            "stage": 1,
            "depends_on": [],
            "rationale": "Query bottom 5 regions",
            "dimension_intents": [
                {
                    "business_term": "Region",
                    "technical_field": "Region",
                    "field_data_type": "STRING"
                }
            ],
            "measure_intents": [
                {
                    "business_term": "Sales",
                    "technical_field": "Sales",
                    "field_data_type": "REAL",
                    "aggregation": "SUM"
                }
            ],
            "topn_intent": {
                "business_term": "Bottom 5",
                "technical_field": "Region",
                "n": 5,
                "direction": "BOTTOM"
            }
        }'''
        
        result = build_vizql_query.invoke({
            "subtask_json": subtask_json,
            "metadata_json": sample_metadata_json
        })
        
        assert result["has_topn"] is True
        query = result["query"]
        # Find TopN filter
        topn_filters = [f for f in query.get("filters", []) if f.get("filterType") == "TOP"]
        assert len(topn_filters) == 1
        assert topn_filters[0]["direction"] == "BOTTOM"
    
    def test_build_query_relative_date_filter(self, sample_metadata_json):
        """测试相对日期筛选"""
        subtask_json = '''{
            "question_id": "q19",
            "question_text": "Sales in last 3 months",
            "stage": 1,
            "depends_on": [],
            "rationale": "Query sales with relative date filter",
            "measure_intents": [
                {
                    "business_term": "Sales",
                    "technical_field": "Sales",
                    "field_data_type": "REAL",
                    "aggregation": "SUM"
                }
            ],
            "date_filter_intent": {
                "business_term": "last 3 months",
                "technical_field": "Order Date",
                "field_data_type": "DATE",
                "time_range": {
                    "type": "relative",
                    "relative_type": "LASTN",
                    "period_type": "MONTHS",
                    "range_n": 3
                }
            }
        }'''
        
        result = build_vizql_query.invoke({
            "subtask_json": subtask_json,
            "metadata_json": sample_metadata_json,
            "anchor_date": "2024-12-31"
        })
        
        assert result["has_date_filter"] is True
        query = result["query"]
        # Find date filter
        date_filters = [f for f in query.get("filters", []) if f.get("filterType") in ["DATE", "QUANTITATIVE_DATE"]]
        assert len(date_filters) >= 1
    
    # ============= STRING类型日期字段测试 =============
    
    def test_build_query_string_date_filter_absolute(self):
        """测试STRING类型日期字段的绝对日期筛选"""
        # 创建包含STRING类型日期字段的元数据
        metadata_json = '''{
            "datasource_name": "Superstore",
            "datasource_luid": "test-luid-123",
            "field_count": 3,
            "fields": [
                {
                    "name": "Date String",
                    "fieldCaption": "Date String",
                    "role": "dimension",
                    "dataType": "STRING",
                    "sample_values": ["2024-01-15", "2024-02-20", "2024-03-10"]
                },
                {
                    "name": "Sales",
                    "fieldCaption": "Sales",
                    "role": "measure",
                    "dataType": "REAL",
                    "aggregation": "SUM"
                },
                {
                    "name": "Region",
                    "fieldCaption": "Region",
                    "role": "dimension",
                    "dataType": "STRING"
                }
            ]
        }'''
        
        subtask_json = '''{
            "question_id": "q20",
            "question_text": "Sales in 2024",
            "stage": 1,
            "depends_on": [],
            "rationale": "Query sales with STRING date filter",
            "measure_intents": [
                {
                    "business_term": "Sales",
                    "technical_field": "Sales",
                    "field_data_type": "REAL",
                    "aggregation": "SUM"
                }
            ],
            "date_filter_intent": {
                "business_term": "2024",
                "technical_field": "Date String",
                "field_data_type": "STRING",
                "time_range": {
                    "type": "absolute",
                    "value": "2024"
                }
            }
        }'''
        
        result = build_vizql_query.invoke({
            "subtask_json": subtask_json,
            "metadata_json": metadata_json,
            "anchor_date": "2024-12-31"
        })
        
        # 验证生成了日期筛选
        assert result["has_date_filter"] is True
        query = result["query"]
        
        # 验证筛选器类型为QUANTITATIVE_DATE（STRING类型日期字段使用此类型）
        date_filters = [f for f in query.get("filters", []) if f.get("filterType") == "QUANTITATIVE_DATE"]
        assert len(date_filters) == 1
        
        # 验证筛选器使用了DATEPARSE calculation
        filter_field = date_filters[0]["field"]
        assert "calculation" in filter_field
        assert "DATEPARSE" in filter_field["calculation"]
        assert "Date String" in filter_field["calculation"]
        
        # 验证日期范围
        assert date_filters[0]["minDate"] == "2024-01-01"
        assert date_filters[0]["maxDate"] == "2024-12-31"
    
    def test_build_query_string_date_filter_relative(self):
        """测试STRING类型日期字段的相对日期筛选"""
        metadata_json = '''{
            "datasource_name": "Superstore",
            "datasource_luid": "test-luid-123",
            "field_count": 2,
            "fields": [
                {
                    "name": "Date String",
                    "fieldCaption": "Date String",
                    "role": "dimension",
                    "dataType": "STRING",
                    "sample_values": ["2024-01-15", "2024-02-20", "2024-03-10"]
                },
                {
                    "name": "Sales",
                    "fieldCaption": "Sales",
                    "role": "measure",
                    "dataType": "REAL",
                    "aggregation": "SUM"
                }
            ]
        }'''
        
        subtask_json = '''{
            "question_id": "q21",
            "question_text": "Sales in last 3 months",
            "stage": 1,
            "depends_on": [],
            "rationale": "Query sales with STRING date relative filter",
            "measure_intents": [
                {
                    "business_term": "Sales",
                    "technical_field": "Sales",
                    "field_data_type": "REAL",
                    "aggregation": "SUM"
                }
            ],
            "date_filter_intent": {
                "business_term": "last 3 months",
                "technical_field": "Date String",
                "field_data_type": "STRING",
                "time_range": {
                    "type": "relative",
                    "relative_type": "LASTN",
                    "period_type": "MONTHS",
                    "range_n": 3
                }
            }
        }'''
        
        result = build_vizql_query.invoke({
            "subtask_json": subtask_json,
            "metadata_json": metadata_json,
            "anchor_date": "2024-12-31"
        })
        
        # 验证生成了日期筛选
        assert result["has_date_filter"] is True
        query = result["query"]
        
        # STRING类型的相对日期筛选也应该使用QUANTITATIVE_DATE
        date_filters = [f for f in query.get("filters", []) if f.get("filterType") == "QUANTITATIVE_DATE"]
        assert len(date_filters) == 1
        
        # 验证使用了DATEPARSE
        filter_field = date_filters[0]["field"]
        assert "calculation" in filter_field
        assert "DATEPARSE" in filter_field["calculation"]
    
    def test_build_query_date_type_vs_string_type(self):
        """测试DATE类型和STRING类型日期字段生成不同的筛选器"""
        # DATE类型元数据
        date_metadata_json = '''{
            "datasource_name": "Superstore",
            "datasource_luid": "test-luid-123",
            "field_count": 2,
            "fields": [
                {
                    "name": "Order Date",
                    "fieldCaption": "Order Date",
                    "role": "dimension",
                    "dataType": "DATE"
                },
                {
                    "name": "Sales",
                    "fieldCaption": "Sales",
                    "role": "measure",
                    "dataType": "REAL",
                    "aggregation": "SUM"
                }
            ]
        }'''
        
        # STRING类型元数据
        string_metadata_json = '''{
            "datasource_name": "Superstore",
            "datasource_luid": "test-luid-123",
            "field_count": 2,
            "fields": [
                {
                    "name": "Date String",
                    "fieldCaption": "Date String",
                    "role": "dimension",
                    "dataType": "STRING",
                    "sample_values": ["2024-01-15", "2024-02-20"]
                },
                {
                    "name": "Sales",
                    "fieldCaption": "Sales",
                    "role": "measure",
                    "dataType": "REAL",
                    "aggregation": "SUM"
                }
            ]
        }'''
        
        # DATE类型 - 相对日期筛选
        date_subtask_json = '''{
            "question_id": "q22",
            "question_text": "Sales in last month",
            "stage": 1,
            "depends_on": [],
            "rationale": "Test DATE type relative filter",
            "measure_intents": [
                {
                    "business_term": "Sales",
                    "technical_field": "Sales",
                    "field_data_type": "REAL",
                    "aggregation": "SUM"
                }
            ],
            "date_filter_intent": {
                "business_term": "last month",
                "technical_field": "Order Date",
                "field_data_type": "DATE",
                "time_range": {
                    "type": "relative",
                    "relative_type": "LASTN",
                    "period_type": "MONTHS",
                    "range_n": 1
                }
            }
        }'''
        
        # STRING类型 - 相对日期筛选
        string_subtask_json = '''{
            "question_id": "q25",
            "question_text": "Sales in last month",
            "stage": 1,
            "depends_on": [],
            "rationale": "Test STRING type relative filter",
            "measure_intents": [
                {
                    "business_term": "Sales",
                    "technical_field": "Sales",
                    "field_data_type": "REAL",
                    "aggregation": "SUM"
                }
            ],
            "date_filter_intent": {
                "business_term": "last month",
                "technical_field": "Date String",
                "field_data_type": "STRING",
                "time_range": {
                    "type": "relative",
                    "relative_type": "LASTN",
                    "period_type": "MONTHS",
                    "range_n": 1
                }
            }
        }'''
        
        # 测试DATE类型
        date_result = build_vizql_query.invoke({
            "subtask_json": date_subtask_json,
            "metadata_json": date_metadata_json,
            "anchor_date": "2024-12-31"
        })
        
        # 测试STRING类型
        string_result = build_vizql_query.invoke({
            "subtask_json": string_subtask_json,
            "metadata_json": string_metadata_json,
            "anchor_date": "2024-12-31"
        })
        
        # 验证两者都生成了日期筛选
        assert date_result["has_date_filter"] is True
        assert string_result["has_date_filter"] is True
        
        # 验证DATE类型使用RelativeDateFilter (filterType="DATE")
        date_query = date_result["query"]
        date_filters = [f for f in date_query.get("filters", []) if f.get("filterType") == "DATE"]
        assert len(date_filters) == 1
        assert "dateRangeType" in date_filters[0]  # RelativeDateFilter特有字段
        
        # 验证STRING类型使用QuantitativeDateFilter (filterType="QUANTITATIVE_DATE")
        string_query = string_result["query"]
        string_filters = [f for f in string_query.get("filters", []) if f.get("filterType") == "QUANTITATIVE_DATE"]
        assert len(string_filters) == 1
        assert "minDate" in string_filters[0]  # QuantitativeDateFilter特有字段
        assert "maxDate" in string_filters[0]
        
        # 验证STRING类型使用了DATEPARSE
        string_filter_field = string_filters[0]["field"]
        assert "calculation" in string_filter_field
        assert "DATEPARSE" in string_filter_field["calculation"]
    
    def test_build_query_string_date_field_with_function(self):
        """测试STRING类型日期字段使用日期函数"""
        metadata_json = '''{
            "datasource_name": "Superstore",
            "datasource_luid": "test-luid-123",
            "field_count": 2,
            "fields": [
                {
                    "name": "Date String",
                    "fieldCaption": "Date String",
                    "role": "dimension",
                    "dataType": "STRING",
                    "sample_values": ["2024-01-15", "2024-02-20", "2024-03-10"]
                },
                {
                    "name": "Sales",
                    "fieldCaption": "Sales",
                    "role": "measure",
                    "dataType": "REAL",
                    "aggregation": "SUM"
                }
            ]
        }'''
        
        subtask_json = '''{
            "question_id": "q23",
            "question_text": "Sales by Month",
            "stage": 1,
            "depends_on": [],
            "rationale": "Query sales grouped by month from STRING date field",
            "date_field_intents": [
                {
                    "business_term": "Month",
                    "technical_field": "Date String",
                    "field_data_type": "STRING",
                    "date_function": "MONTH"
                }
            ],
            "measure_intents": [
                {
                    "business_term": "Sales",
                    "technical_field": "Sales",
                    "field_data_type": "REAL",
                    "aggregation": "SUM"
                }
            ]
        }'''
        
        result = build_vizql_query.invoke({
            "subtask_json": subtask_json,
            "metadata_json": metadata_json
        })
        
        # 验证生成了字段
        assert result["field_count"] == 2
        query = result["query"]
        
        # 查找包含DATEPARSE和MONTH的计算字段
        calc_fields = [f for f in query["fields"] if "calculation" in f]
        assert len(calc_fields) == 1
        
        # 验证calculation包含DATEPARSE和MONTH
        calculation = calc_fields[0]["calculation"]
        assert "DATEPARSE" in calculation
        assert "MONTH" in calculation
        assert "Date String" in calculation
    
    def test_build_query_string_date_different_formats(self):
        """测试不同格式的STRING日期字段"""
        import json
        
        # 测试不同的日期格式
        date_formats = [
            (["2024-01-15", "2024-02-20"], "yyyy-MM-dd"),
            (["2024/01/15", "2024/02/20"], "yyyy/MM/dd"),
            (["15/01/2024", "20/02/2024"], "dd/MM/yyyy"),
            (["20240115", "20240220"], "yyyyMMdd"),
        ]
        
        for sample_values, expected_format in date_formats:
            metadata_dict = {
                "datasource_name": "Superstore",
                "datasource_luid": "test-luid-123",
                "field_count": 2,
                "fields": [
                    {
                        "name": "Date String",
                        "fieldCaption": "Date String",
                        "role": "dimension",
                        "dataType": "STRING",
                        "sample_values": sample_values
                    },
                    {
                        "name": "Sales",
                        "fieldCaption": "Sales",
                        "role": "measure",
                        "dataType": "REAL",
                        "aggregation": "SUM"
                    }
                ]
            }
            metadata_json = json.dumps(metadata_dict)
            
            subtask_json = '''{
                "question_id": "q24",
                "question_text": "Sales in 2024",
                "stage": 1,
                "depends_on": [],
                "rationale": "Test different date formats",
                "measure_intents": [
                    {
                        "business_term": "Sales",
                        "technical_field": "Sales",
                        "field_data_type": "REAL",
                        "aggregation": "SUM"
                    }
                ],
                "date_filter_intent": {
                    "business_term": "2024",
                    "technical_field": "Date String",
                    "field_data_type": "STRING",
                    "time_range": {
                        "type": "absolute",
                        "value": "2024"
                    }
                }
            }'''
            
            result = build_vizql_query.invoke({
                "subtask_json": subtask_json,
                "metadata_json": metadata_json,
                "anchor_date": "2024-12-31"
            })
            
            # 验证生成了日期筛选
            assert result["has_date_filter"] is True
            query = result["query"]
            
            # 验证DATEPARSE使用了正确的格式
            date_filters = [f for f in query.get("filters", []) if f.get("filterType") == "QUANTITATIVE_DATE"]
            assert len(date_filters) == 1
            
            filter_field = date_filters[0]["field"]
            assert "calculation" in filter_field
            assert f"DATEPARSE('{expected_format}'" in filter_field["calculation"]
    
   


# ============= execute_vizql_query 工具测试 =============

class TestExecuteVizQLQueryTool:
    """测试 execute_vizql_query 工具"""
    
    def test_execute_simple_query_success(self):
        """测试成功执行简单查询"""
        from tableau_assistant.src.deepagents.tools.execute_vizql_query import execute_vizql_query
        
        query_json = '''{
            "fields": [
                {
                    "fieldCaption": "Sales",
                    "function": "SUM"
                }
            ],
            "filters": null
        }'''
        
        # Mock query_vds function
        mock_result = {
            "data": [{"Sales": 1000}, {"Sales": 2000}],
            "query_time_ms": 100
        }
        
        with patch('tableau_assistant.src.components.query_executor.query_vds', return_value=mock_result):
            result = execute_vizql_query.invoke({
                "query_json": query_json,
                "datasource_luid": "test-luid",
                "tableau_token": "test-token",
                "tableau_domain": "https://tableau.example.com"
            })
            
            # 验证结果
            assert result["row_count"] == 2
            assert len(result["data"]) == 2
            assert result["columns"] == ["Sales"]
            assert "performance" in result
            assert result["performance"]["fields_count"] == 1
            assert result["performance"]["filters_count"] == 0
    
    def test_execute_query_with_filters(self):
        """测试执行带筛选器的查询"""
        from tableau_assistant.src.deepagents.tools.execute_vizql_query import execute_vizql_query
        
        query_json = '''{
            "fields": [
                {
                    "fieldCaption": "Region"
                },
                {
                    "fieldCaption": "Sales",
                    "function": "SUM"
                }
            ],
            "filters": [
                {
                    "field": {"fieldCaption": "Region"},
                    "filterType": "SET",
                    "values": ["East", "West"]
                }
            ]
        }'''
        
        mock_result = {
            "data": [
                {"Region": "East", "Sales": 1000},
                {"Region": "West", "Sales": 2000}
            ],
            "query_time_ms": 150
        }
        
        with patch('tableau_assistant.src.components.query_executor.query_vds', return_value=mock_result):
            result = execute_vizql_query.invoke({
                "query_json": query_json,
                "datasource_luid": "test-luid",
                "tableau_token": "test-token",
                "tableau_domain": "https://tableau.example.com",
                "tableau_site": "my-site"
            })
            
            assert result["row_count"] == 2
            assert result["performance"]["fields_count"] == 2
            assert result["performance"]["filters_count"] == 1
    
    def test_execute_query_with_retry(self):
        """测试查询重试机制"""
        from tableau_assistant.src.deepagents.tools.execute_vizql_query import execute_vizql_query
        
        query_json = '''{
            "fields": [{"fieldCaption": "Sales", "function": "SUM"}],
            "filters": null
        }'''
        
        # Mock: 第一次失败,第二次成功
        call_count = 0
        def mock_query_vds(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("Network error")
            return {"data": [{"Sales": 1000}], "query_time_ms": 100}
        
        with patch('tableau_assistant.src.components.query_executor.query_vds', side_effect=mock_query_vds):
            result = execute_vizql_query.invoke({
                "query_json": query_json,
                "datasource_luid": "test-luid",
                "tableau_token": "test-token",
                "tableau_domain": "https://tableau.example.com",
                "enable_retry": True,
                "max_retries": 3
            })
            
            # 验证重试成功
            assert result["row_count"] == 1
            assert result["retry_count"] == 1
            assert call_count == 2
    
    def test_execute_query_invalid_json(self):
        """测试无效的JSON"""
        from tableau_assistant.src.deepagents.tools.execute_vizql_query import execute_vizql_query
        
        with pytest.raises(ValueError, match="Invalid query JSON"):
            execute_vizql_query.invoke({
                "query_json": "invalid json",
                "datasource_luid": "test-luid",
                "tableau_token": "test-token",
                "tableau_domain": "https://tableau.example.com"
            })
    
    def test_execute_query_validation_error(self):
        """测试查询验证错误"""
        from tableau_assistant.src.deepagents.tools.execute_vizql_query import execute_vizql_query
        
        # 空字段列表
        query_json = '''{
            "fields": [],
            "filters": null
        }'''
        
        with pytest.raises(RuntimeError, match="Unexpected error executing query"):
            execute_vizql_query.invoke({
                "query_json": query_json,
                "datasource_luid": "test-luid",
                "tableau_token": "test-token",
                "tableau_domain": "https://tableau.example.com"
            })
    
    def test_execute_query_network_error(self):
        """测试网络错误"""
        from tableau_assistant.src.deepagents.tools.execute_vizql_query import execute_vizql_query
        
        query_json = '''{
            "fields": [{"fieldCaption": "Sales", "function": "SUM"}],
            "filters": null
        }'''
        
        # Mock: 总是失败
        with patch('tableau_assistant.src.components.query_executor.query_vds', side_effect=ConnectionError("Network error")):
            with pytest.raises(RuntimeError, match="Query execution failed"):
                execute_vizql_query.invoke({
                    "query_json": query_json,
                    "datasource_luid": "test-luid",
                    "tableau_token": "test-token",
                    "tableau_domain": "https://tableau.example.com",
                    "enable_retry": True,
                    "max_retries": 2
                })
    
    def test_execute_query_disable_retry(self):
        """测试禁用重试"""
        from tableau_assistant.src.deepagents.tools.execute_vizql_query import execute_vizql_query
        
        query_json = '''{
            "fields": [{"fieldCaption": "Sales", "function": "SUM"}],
            "filters": null
        }'''
        
        call_count = 0
        def mock_query_vds(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise ConnectionError("Network error")
        
        with patch('tableau_assistant.src.components.query_executor.query_vds', side_effect=mock_query_vds):
            with pytest.raises(RuntimeError):
                execute_vizql_query.invoke({
                    "query_json": query_json,
                    "datasource_luid": "test-luid",
                    "tableau_token": "test-token",
                    "tableau_domain": "https://tableau.example.com",
                    "enable_retry": False
                })
            
            # 验证只调用了一次(没有重试)
            assert call_count == 1
    
    def test_execute_query_async(self):
        """测试异步调用"""
        import asyncio
        from tableau_assistant.src.deepagents.tools.execute_vizql_query import execute_vizql_query
        
        query_json = '''{
            "fields": [{"fieldCaption": "Sales", "function": "SUM"}],
            "filters": null
        }'''
        
        mock_result = {
            "data": [{"Sales": 1000}],
            "query_time_ms": 100
        }
        
        async def test_async():
            with patch('tableau_assistant.src.components.query_executor.query_vds', return_value=mock_result):
                result = await execute_vizql_query.ainvoke({
                    "query_json": query_json,
                    "datasource_luid": "test-luid",
                    "tableau_token": "test-token",
                    "tableau_domain": "https://tableau.example.com"
                })
                return result
        
        result = asyncio.run(test_async())
        assert result["row_count"] == 1
    
    def test_execute_query_performance_metrics(self):
        """测试性能指标"""
        from tableau_assistant.src.deepagents.tools.execute_vizql_query import execute_vizql_query
        
        query_json = '''{
            "fields": [
                {"fieldCaption": "Region"},
                {"fieldCaption": "Sales", "function": "SUM"}
            ],
            "filters": [
                {
                    "field": {"fieldCaption": "Region"},
                    "filterType": "SET",
                    "values": ["East"]
                }
            ]
        }'''
        
        mock_result = {
            "data": [{"Region": "East", "Sales": 1000}],
            "query_time_ms": 200
        }
        
        with patch('tableau_assistant.src.components.query_executor.query_vds', return_value=mock_result):
            result = execute_vizql_query.invoke({
                "query_json": query_json,
                "datasource_luid": "test-luid",
                "tableau_token": "test-token",
                "tableau_domain": "https://tableau.example.com"
            })
            
            # 验证性能指标
            assert "performance" in result
            perf = result["performance"]
            assert "execution_time" in perf
            assert "execution_time_ms" in perf
            assert "row_count" in perf
            assert "fields_count" in perf
            assert "filters_count" in perf
            assert "retry_count" in perf
            
            assert perf["row_count"] == 1
            assert perf["fields_count"] == 2
            assert perf["filters_count"] == 1
            assert perf["retry_count"] == 0
