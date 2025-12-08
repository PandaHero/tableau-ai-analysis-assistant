"""
工具层单元测试

测试各 capability 包中的工具：
- build_vizql_query (query/builder/tool.py)
- execute_vizql_query (query/executor/tool.py)
- parse_date (date_processing/tool.py)
- detect_statistics (data_processing/tool.py)
- process_query_result (data_processing/tool.py)

注意：get_metadata 和 semantic_map_fields 是异步工具，需要单独测试
注意：大结果保存由 FilesystemMiddleware 自动处理，不再需要单独的工具
"""
import json
import pytest
import tempfile
import os
from datetime import datetime


class TestBuildVizqlQueryTool:
    """build_vizql_query 工具测试"""
    
    def test_basic_query_build(self):
        """测试基本查询构建"""
        from tableau_assistant.src.capabilities.query.builder.tool import build_vizql_query
        
        subtask = {
            "question_id": "q1",
            "question_text": "Sales by Region",
            "task_type": "query",
            "stage": 1,
            "rationale": "Query sales grouped by region",
            "depends_on": [],
            "dimension_intents": [
                {"business_term": "Region", "technical_field": "Region", "field_data_type": "STRING"}
            ],
            "measure_intents": [
                {"business_term": "Sales", "technical_field": "Sales", "field_data_type": "REAL", "aggregation": "SUM"}
            ],
            "date_field_intents": [],
            "filter_intents": [],
            "date_filter_intent": None,
            "topn_intent": None,
            "table_calc_intents": []
        }
        
        metadata = {
            "datasource_name": "Superstore",
            "datasource_luid": "test-luid",
            "field_count": 2,
            "fields": [
                {"name": "Region", "fieldCaption": "Region", "dataType": "STRING", "role": "dimension"},
                {"name": "Sales", "fieldCaption": "Sales", "dataType": "REAL", "role": "measure"}
            ]
        }
        
        result = build_vizql_query.invoke({
            "subtask_json": json.dumps(subtask),
            "metadata_json": json.dumps(metadata)
        })
        
        assert "query" in result
        assert "field_count" in result
        assert result["field_count"] == 2
        assert result["filter_count"] == 0
        assert result["has_date_filter"] is False
        assert result["has_topn"] is False
    
    def test_query_with_anchor_date(self):
        """测试带锚点日期的查询构建"""
        from tableau_assistant.src.capabilities.query.builder.tool import build_vizql_query
        
        subtask = {
            "question_id": "q2",
            "question_text": "Sales trend",
            "task_type": "query",
            "stage": 1,
            "rationale": "Query sales trend by month",
            "depends_on": [],
            "dimension_intents": [],
            "measure_intents": [
                {"business_term": "Sales", "technical_field": "Sales", "field_data_type": "REAL", "aggregation": "SUM"}
            ],
            "date_field_intents": [
                {"business_term": "Order Date", "technical_field": "Order Date", "field_data_type": "DATE", "date_function": "MONTH"}
            ],
            "filter_intents": [],
            "date_filter_intent": None,
            "topn_intent": None,
            "table_calc_intents": []
        }
        
        metadata = {
            "datasource_name": "Superstore",
            "datasource_luid": "test-luid",
            "field_count": 2,
            "fields": [
                {"name": "Order Date", "fieldCaption": "Order Date", "dataType": "DATE", "role": "dimension"},
                {"name": "Sales", "fieldCaption": "Sales", "dataType": "REAL", "role": "measure"}
            ]
        }
        
        result = build_vizql_query.invoke({
            "subtask_json": json.dumps(subtask),
            "metadata_json": json.dumps(metadata),
            "anchor_date": "2024-12-01",
            "week_start_day": 0
        })
        
        assert "query" in result
        assert result["field_count"] == 2
    
    def test_invalid_json_raises_error(self):
        """测试无效 JSON 输入"""
        from tableau_assistant.src.capabilities.query.builder.tool import build_vizql_query
        
        with pytest.raises(Exception):
            build_vizql_query.invoke({
                "subtask_json": "invalid json",
                "metadata_json": "{}"
            })


class TestParseDateTool:
    """parse_date 工具测试"""
    
    def test_absolute_year(self):
        """测试绝对日期 - 年"""
        from tableau_assistant.src.capabilities.date_processing.tool import parse_date
        
        time_range = {
            "type": "absolute",
            "value": "2024"
        }
        
        result = parse_date.invoke({
            "time_range_json": json.dumps(time_range)
        })
        
        assert result["start_date"] == "2024-01-01"
        assert result["end_date"] == "2024-12-31"
        assert result["adjusted"] is False
    
    def test_absolute_quarter(self):
        """测试绝对日期 - 季度"""
        from tableau_assistant.src.capabilities.date_processing.tool import parse_date
        
        time_range = {
            "type": "absolute",
            "value": "2024-Q1"
        }
        
        result = parse_date.invoke({
            "time_range_json": json.dumps(time_range)
        })
        
        assert result["start_date"] == "2024-01-01"
        assert result["end_date"] == "2024-03-31"
    
    def test_relative_lastn_months(self):
        """测试相对日期 - 最近N个月"""
        from tableau_assistant.src.capabilities.date_processing.tool import parse_date
        
        time_range = {
            "type": "relative",
            "relative_type": "LASTN",
            "period_type": "MONTHS",
            "range_n": 3
        }
        
        result = parse_date.invoke({
            "time_range_json": json.dumps(time_range),
            "reference_date": "2024-12-31"
        })
        
        assert "start_date" in result
        assert "end_date" in result
        assert result["end_date"] == "2024-12-31"
    
    def test_max_date_adjustment(self):
        """测试最大日期调整"""
        from tableau_assistant.src.capabilities.date_processing.tool import parse_date
        
        time_range = {
            "type": "absolute",
            "value": "2024"
        }
        
        result = parse_date.invoke({
            "time_range_json": json.dumps(time_range),
            "max_date": "2024-06-30"
        })
        
        assert result["end_date"] == "2024-06-30"
        assert result["adjusted"] is True


class TestDetectStatisticsTool:
    """detect_statistics 工具测试"""
    
    def test_basic_statistics(self):
        """测试基本统计检测"""
        from tableau_assistant.src.capabilities.data_processing.tool import detect_statistics
        
        data = [
            {"region": "East", "sales": 100},
            {"region": "West", "sales": 200},
            {"region": "North", "sales": 150},
            {"region": "South", "sales": 180}
        ]
        
        result = detect_statistics.invoke({
            "data_json": json.dumps(data)
        })
        
        assert "summary" in result
        assert result["summary"]["row_count"] == 4
        assert result["summary"]["column_count"] == 2
    
    def test_with_nested_data(self):
        """测试嵌套数据格式"""
        from tableau_assistant.src.capabilities.data_processing.tool import detect_statistics
        
        data = {
            "data": [
                {"region": "East", "sales": 100},
                {"region": "West", "sales": 200}
            ]
        }
        
        result = detect_statistics.invoke({
            "data_json": json.dumps(data)
        })
        
        assert result["summary"]["row_count"] == 2
    
    def test_selective_analysis(self):
        """测试选择性分析"""
        from tableau_assistant.src.capabilities.data_processing.tool import detect_statistics
        
        data = [{"value": i} for i in range(10)]
        
        result = detect_statistics.invoke({
            "data_json": json.dumps(data),
            "include_basic_stats": True,
            "include_anomalies": False,
            "include_trends": False,
            "include_correlations": False,
            "include_distributions": False,
            "include_data_quality": False
        })
        
        assert "basic_stats" in result
        assert "anomalies" not in result
    
    def test_empty_data_raises_error(self):
        """测试空数据"""
        from tableau_assistant.src.capabilities.data_processing.tool import detect_statistics
        
        with pytest.raises(Exception):
            detect_statistics.invoke({
                "data_json": json.dumps([])
            })


class TestProcessQueryResultTool:
    """process_query_result 工具测试"""
    
    def test_default_processing(self):
        """测试默认处理"""
        from tableau_assistant.src.capabilities.data_processing.tool import process_query_result
        
        subtask = {
            "question_id": "q1",
            "question_text": "Sales by Region"
        }
        
        result_data = {
            "data": [
                {"region": "East", "sales": 100},
                {"region": "West", "sales": 200}
            ],
            "row_count": 2
        }
        
        result = process_query_result.invoke({
            "subtask_json": json.dumps(subtask),
            "result_json": json.dumps(result_data),
            "processing_type": "default"
        })
        
        assert result is not None


# 运行测试
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
