"""
工具层属性测试

属性 1: 工具封装业务逻辑保持
- 验证工具封装前后输出一致
- 使用 Hypothesis 生成随机输入
"""
import json
import pytest
from hypothesis import given, strategies as st, settings, assume
from datetime import datetime, timedelta


# ============= 策略定义 =============

@st.composite
def valid_dimension_intent(draw):
    """生成有效的维度意图"""
    field_name = draw(st.sampled_from(["Region", "Category", "Segment", "State", "City"]))
    return {
        "business_term": field_name,
        "technical_field": field_name,
        "field_data_type": "STRING"
    }


@st.composite
def valid_measure_intent(draw):
    """生成有效的度量意图"""
    field_name = draw(st.sampled_from(["Sales", "Profit", "Quantity", "Discount"]))
    aggregation = draw(st.sampled_from(["SUM", "AVG", "COUNT", "MIN", "MAX"]))
    data_type = "INTEGER" if field_name == "Quantity" else "REAL"
    return {
        "business_term": field_name,
        "technical_field": field_name,
        "field_data_type": data_type,
        "aggregation": aggregation
    }


@st.composite
def valid_subtask(draw):
    """生成有效的 QuerySubTask"""
    question_id = draw(st.integers(min_value=1, max_value=99))
    question_text = draw(st.text(min_size=5, max_size=100))
    
    # 至少有一个维度或度量
    dimensions = draw(st.lists(valid_dimension_intent(), min_size=0, max_size=3))
    measures = draw(st.lists(valid_measure_intent(), min_size=1, max_size=3))
    
    return {
        "question_id": f"q{question_id}",
        "question_text": question_text,
        "task_type": "query",
        "stage": 1,
        "rationale": "Test query",
        "depends_on": [],
        "dimension_intents": dimensions,
        "measure_intents": measures,
        "date_field_intents": [],
        "filter_intents": [],
        "date_filter_intent": None,
        "topn_intent": None,
        "table_calc_intents": []
    }


def valid_metadata():
    """生成有效的 Metadata（固定值策略）"""
    fields = [
        {"name": "Region", "fieldCaption": "Region", "dataType": "STRING", "role": "dimension"},
        {"name": "Category", "fieldCaption": "Category", "dataType": "STRING", "role": "dimension"},
        {"name": "Segment", "fieldCaption": "Segment", "dataType": "STRING", "role": "dimension"},
        {"name": "State", "fieldCaption": "State", "dataType": "STRING", "role": "dimension"},
        {"name": "City", "fieldCaption": "City", "dataType": "STRING", "role": "dimension"},
        {"name": "Sales", "fieldCaption": "Sales", "dataType": "REAL", "role": "measure"},
        {"name": "Profit", "fieldCaption": "Profit", "dataType": "REAL", "role": "measure"},
        {"name": "Quantity", "fieldCaption": "Quantity", "dataType": "INTEGER", "role": "measure"},
        {"name": "Discount", "fieldCaption": "Discount", "dataType": "REAL", "role": "measure"},
    ]
    return st.just({
        "datasource_name": "TestDatasource",
        "datasource_luid": "test-luid-123",
        "field_count": len(fields),
        "fields": fields
    })


@st.composite
def valid_time_range_absolute(draw):
    """生成有效的绝对时间范围"""
    year = draw(st.integers(min_value=2020, max_value=2024))
    value_type = draw(st.sampled_from(["year", "quarter", "month"]))
    
    if value_type == "year":
        value = str(year)
    elif value_type == "quarter":
        quarter = draw(st.integers(min_value=1, max_value=4))
        value = f"{year}-Q{quarter}"
    else:
        month = draw(st.integers(min_value=1, max_value=12))
        value = f"{year}-{month:02d}"
    
    return {
        "type": "absolute",
        "value": value
    }


@st.composite
def valid_time_range_relative(draw):
    """生成有效的相对时间范围"""
    # 使用有效的相对类型: LASTN, LAST, CURRENT, NEXT, NEXTN
    relative_type = draw(st.sampled_from(["LASTN", "NEXTN", "LAST", "CURRENT"]))
    period_type = draw(st.sampled_from(["DAYS", "WEEKS", "MONTHS", "QUARTERS", "YEARS"]))
    range_n = draw(st.integers(min_value=1, max_value=12))
    
    return {
        "type": "relative",
        "relative_type": relative_type,
        "period_type": period_type,
        "range_n": range_n
    }


@st.composite
def valid_numeric_data(draw):
    """生成有效的数值数据，确保数值有足够变化"""
    n_rows = draw(st.integers(min_value=10, max_value=50))
    
    # 生成基础值和变化范围，确保数据有变化
    base_value = draw(st.floats(min_value=-500, max_value=500, allow_nan=False, allow_infinity=False))
    variation = draw(st.floats(min_value=10, max_value=200, allow_nan=False, allow_infinity=False))
    
    data = []
    for i in range(n_rows):
        # 使用基础值加上随机变化，确保数据不会全部相同
        offset = draw(st.floats(min_value=-variation, max_value=variation, allow_nan=False, allow_infinity=False))
        row = {
            "id": i,
            "value": base_value + offset + i * 0.1,  # 添加 i*0.1 确保每行都不同
            "category": draw(st.sampled_from(["A", "B", "C", "D"]))
        }
        data.append(row)
    
    return data


# ============= 属性测试 =============

class TestBuildVizqlQueryProperties:
    """build_vizql_query 工具属性测试"""
    
    @given(subtask=valid_subtask(), metadata=valid_metadata())
    @settings(max_examples=100, deadline=None)
    def test_output_structure_consistent(self, subtask, metadata):
        """属性: 输出结构始终一致"""
        from tableau_assistant.src.capabilities.query.builder.tool import build_vizql_query
        
        result = build_vizql_query.invoke({
            "subtask_json": json.dumps(subtask),
            "metadata_json": json.dumps(metadata)
        })
        
        # 验证输出结构
        assert "query" in result
        assert "field_count" in result
        assert "filter_count" in result
        assert "has_date_filter" in result
        assert "has_topn" in result
        
        # 验证类型
        assert isinstance(result["field_count"], int)
        assert isinstance(result["filter_count"], int)
        assert isinstance(result["has_date_filter"], bool)
        assert isinstance(result["has_topn"], bool)
    
    @given(subtask=valid_subtask(), metadata=valid_metadata())
    @settings(max_examples=100, deadline=None)
    def test_field_count_matches_intents(self, subtask, metadata):
        """属性: 字段数量与意图数量匹配"""
        from tableau_assistant.src.capabilities.query.builder.tool import build_vizql_query
        
        result = build_vizql_query.invoke({
            "subtask_json": json.dumps(subtask),
            "metadata_json": json.dumps(metadata)
        })
        
        expected_count = (
            len(subtask["dimension_intents"]) +
            len(subtask["measure_intents"]) +
            len(subtask.get("date_field_intents", []))
        )
        
        assert result["field_count"] == expected_count
    
    @given(subtask=valid_subtask(), metadata=valid_metadata())
    @settings(max_examples=100, deadline=None)
    def test_no_filters_when_no_filter_intents(self, subtask, metadata):
        """属性: 无筛选意图时筛选器数量为0"""
        from tableau_assistant.src.capabilities.query.builder.tool import build_vizql_query
        
        # 确保没有筛选意图
        subtask["filter_intents"] = []
        subtask["date_filter_intent"] = None
        subtask["topn_intent"] = None
        
        result = build_vizql_query.invoke({
            "subtask_json": json.dumps(subtask),
            "metadata_json": json.dumps(metadata)
        })
        
        assert result["filter_count"] == 0
        assert result["has_date_filter"] is False
        assert result["has_topn"] is False


class TestParseDateProperties:
    """parse_date 工具属性测试"""
    
    @given(time_range=valid_time_range_absolute())
    @settings(max_examples=100, deadline=None)
    def test_absolute_date_output_format(self, time_range):
        """属性: 绝对日期输出格式正确"""
        from tableau_assistant.src.capabilities.date_processing.tool import parse_date
        
        result = parse_date.invoke({
            "time_range_json": json.dumps(time_range)
        })
        
        # 验证输出结构
        assert "start_date" in result
        assert "end_date" in result
        assert "adjusted" in result
        
        # 验证日期格式 (YYYY-MM-DD)
        start = datetime.strptime(result["start_date"], "%Y-%m-%d")
        end = datetime.strptime(result["end_date"], "%Y-%m-%d")
        
        # 验证 start <= end
        assert start <= end
    
    @given(time_range=valid_time_range_relative())
    @settings(max_examples=100, deadline=None)
    def test_relative_date_output_format(self, time_range):
        """属性: 相对日期输出格式正确"""
        from tableau_assistant.src.capabilities.date_processing.tool import parse_date
        
        result = parse_date.invoke({
            "time_range_json": json.dumps(time_range),
            "reference_date": "2024-06-15"
        })
        
        # 验证输出结构
        assert "start_date" in result
        assert "end_date" in result
        
        # 验证日期格式
        start = datetime.strptime(result["start_date"], "%Y-%m-%d")
        end = datetime.strptime(result["end_date"], "%Y-%m-%d")
        
        # 验证 start <= end
        assert start <= end
    
    @given(time_range=valid_time_range_absolute())
    @settings(max_examples=50, deadline=None)
    def test_max_date_adjustment_property(self, time_range):
        """属性: max_date 调整正确"""
        from tableau_assistant.src.capabilities.date_processing.tool import parse_date
        
        # 使用一个较早的 max_date
        max_date = "2023-06-30"
        
        result = parse_date.invoke({
            "time_range_json": json.dumps(time_range),
            "max_date": max_date
        })
        
        end = datetime.strptime(result["end_date"], "%Y-%m-%d")
        max_dt = datetime.strptime(max_date, "%Y-%m-%d")
        
        # 验证 end_date 不超过 max_date
        assert end <= max_dt


class TestDetectStatisticsProperties:
    """detect_statistics 工具属性测试"""
    
    @given(data=valid_numeric_data())
    @settings(max_examples=100, deadline=None)
    def test_summary_row_count_matches(self, data):
        """属性: 摘要行数与输入数据匹配"""
        from tableau_assistant.src.capabilities.data_processing.tool import detect_statistics
        
        result = detect_statistics.invoke({
            "data_json": json.dumps(data)
        })
        
        assert result["summary"]["row_count"] == len(data)
    
    @given(data=valid_numeric_data())
    @settings(max_examples=100, deadline=None)
    def test_output_structure_consistent(self, data):
        """属性: 输出结构始终一致"""
        from tableau_assistant.src.capabilities.data_processing.tool import detect_statistics
        
        result = detect_statistics.invoke({
            "data_json": json.dumps(data),
            "include_basic_stats": True,
            "include_anomalies": True,
            "include_trends": True,
            "include_correlations": True,
            "include_distributions": True,
            "include_data_quality": True
        })
        
        # 验证所有请求的分析都存在
        assert "basic_stats" in result
        assert "anomalies" in result
        assert "trends" in result
        assert "correlations" in result
        assert "distributions" in result
        assert "data_quality" in result
        assert "summary" in result


class TestSaveLargeResultProperties:
    """save_large_result 工具属性测试"""
    
    @given(data=valid_numeric_data())
    @settings(max_examples=50, deadline=None)
    def test_file_created_and_metadata_correct(self, data):
        """属性: 文件创建且元数据正确"""
        import tempfile
        import os
        from tableau_assistant.src.capabilities.storage.tool import save_large_result
        
        with tempfile.TemporaryDirectory() as tmpdir:
            result = save_large_result.invoke({
                "data_json": json.dumps(data),
                "task_id": "prop_test",
                "format": "json",
                "compress": False,
                "base_path": tmpdir
            })
            
            # 验证文件存在
            assert os.path.exists(result["file_path"])
            
            # 验证元数据
            assert result["row_count"] == len(data)
            assert result["format"] == "json"
            assert result["compressed"] is False
            assert result["file_size_bytes"] > 0
    
    @given(
        data=valid_numeric_data(),
        format_type=st.sampled_from(["json", "csv"]),
        compress=st.booleans()
    )
    @settings(max_examples=50, deadline=None)
    def test_format_and_compression_options(self, data, format_type, compress):
        """属性: 格式和压缩选项正确应用"""
        import tempfile
        import os
        from tableau_assistant.src.capabilities.storage.tool import save_large_result
        
        with tempfile.TemporaryDirectory() as tmpdir:
            result = save_large_result.invoke({
                "data_json": json.dumps(data),
                "task_id": "prop_test",
                "format": format_type,
                "compress": compress,
                "base_path": tmpdir
            })
            
            # 验证格式
            assert result["format"] == format_type
            assert result["compressed"] == compress
            
            # 验证文件扩展名
            if compress:
                assert result["file_path"].endswith(".gz")
            else:
                if format_type == "json":
                    assert result["file_path"].endswith(".json")
                else:
                    assert result["file_path"].endswith(".csv")


# ============= 工具封装业务逻辑保持属性测试 =============

class TestToolWrappingPreservesLogic:
    """
    属性 1: 工具封装业务逻辑保持
    
    验证工具封装后的输出与直接调用底层组件的输出一致
    """
    
    @given(subtask=valid_subtask(), metadata=valid_metadata())
    @settings(max_examples=100, deadline=None)
    def test_build_vizql_query_preserves_logic(self, subtask, metadata):
        """验证 build_vizql_query 工具保持 QueryBuilder 逻辑"""
        from tableau_assistant.src.capabilities.query.builder.tool import build_vizql_query
        from tableau_assistant.src.capabilities.query.builder.builder import QueryBuilder
        from tableau_assistant.src.models.query_plan import QuerySubTask
        from tableau_assistant.src.models.metadata import Metadata
        
        # 通过工具调用
        tool_result = build_vizql_query.invoke({
            "subtask_json": json.dumps(subtask),
            "metadata_json": json.dumps(metadata)
        })
        
        # 直接调用 QueryBuilder
        subtask_obj = QuerySubTask(**subtask)
        metadata_obj = Metadata(**metadata)
        builder = QueryBuilder(metadata=metadata_obj)
        direct_query = builder.build_query(subtask_obj)
        
        # 验证字段数量一致
        assert tool_result["field_count"] == len(direct_query.fields)
        
        # 验证筛选器数量一致
        direct_filter_count = len(direct_query.filters) if direct_query.filters else 0
        assert tool_result["filter_count"] == direct_filter_count
    
    @given(time_range=valid_time_range_absolute())
    @settings(max_examples=100, deadline=None)
    def test_parse_date_preserves_logic(self, time_range):
        """验证 parse_date 工具保持 DateParser 逻辑"""
        from tableau_assistant.src.capabilities.date_processing.tool import parse_date
        from tableau_assistant.src.capabilities.date_processing.parser import DateParser
        from tableau_assistant.src.models.question import TimeRange
        
        # 通过工具调用
        tool_result = parse_date.invoke({
            "time_range_json": json.dumps(time_range)
        })
        
        # 直接调用 DateParser
        time_range_obj = TimeRange(**time_range)
        parser = DateParser()
        direct_start, direct_end = parser.calculate_date_range(time_range_obj)
        
        # 验证结果一致
        assert tool_result["start_date"] == direct_start
        assert tool_result["end_date"] == direct_end


# 运行测试
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--hypothesis-show-statistics"])
