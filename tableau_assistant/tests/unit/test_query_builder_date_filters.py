"""
QueryBuilder 日期筛选单元测试

测试 QueryBuilder 根据字段数据类型生成正确的日期筛选条件。

测试场景：
1. DATE 类型 + ABSOLUTE_RANGE → QUANTITATIVE_DATE
2. DATE 类型 + RELATIVE → DATE (RelativeDateFilter)
3. DATE 类型 + SET → 转换为 QUANTITATIVE_DATE 范围
4. STRING 类型 + ABSOLUTE_RANGE → DATEPARSE + QUANTITATIVE_DATE
5. STRING 类型 + RELATIVE → DATEPARSE + QUANTITATIVE_DATE (计算后)
6. STRING 类型 + SET → DATEPARSE + QUANTITATIVE_DATE 或直接 SET
"""

import pytest
from datetime import datetime
from typing import Dict, Any

from tableau_assistant.src.nodes.query_builder.node import QueryBuilderNode
from tableau_assistant.src.models.semantic.query import (
    SemanticQuery,
    MeasureSpec,
    DimensionSpec,
    FilterSpec,
    TimeFilterSpec,
    MappedQuery,
    FieldMapping,
)
from tableau_assistant.src.models.semantic.enums import (
    FilterType,
    TimeFilterMode,
    PeriodType,
    DateRangeType,
    MappingSource,
)


class TestQueryBuilderDateFilters:
    """测试 QueryBuilder 日期筛选生成"""
    
    def setup_method(self):
        """设置测试环境"""
        self.builder = QueryBuilderNode()
    
    # ═══════════════════════════════════════════════════════════════════════
    # DATE 类型字段测试
    # ═══════════════════════════════════════════════════════════════════════
    
    def test_date_type_absolute_range(self):
        """DATE 类型 + ABSOLUTE_RANGE → QUANTITATIVE_DATE"""
        filter_spec = FilterSpec(
            field="日期",
            filter_type=FilterType.TIME_RANGE,
            time_filter=TimeFilterSpec(
                mode=TimeFilterMode.ABSOLUTE_RANGE,
                start_date="2024-01-01",
                end_date="2024-12-31",
            )
        )
        
        # DATE 类型字段映射
        field_mappings = {
            "日期": type('FieldMapping', (), {
                'technical_field': 'Order_Date',
                'business_term': '日期',
                'confidence': 0.95,
                'data_type': 'DATE',
                'date_format': None,
            })()
        }
        
        result = self.builder._build_filter(filter_spec, field_mappings)
        
        assert result is not None
        assert result["filterType"] == "QUANTITATIVE_DATE"
        assert result["field"]["fieldCaption"] == "Order_Date"
        assert result["minDate"] == "2024-01-01"
        assert result["maxDate"] == "2024-12-31"
    
    def test_date_type_relative_lastn(self):
        """DATE 类型 + RELATIVE (LASTN) → DATE (RelativeDateFilter)"""
        filter_spec = FilterSpec(
            field="日期",
            filter_type=FilterType.TIME_RANGE,
            time_filter=TimeFilterSpec(
                mode=TimeFilterMode.RELATIVE,
                period_type=PeriodType.MONTHS,
                date_range_type=DateRangeType.LASTN,
                range_n=3,
            )
        )
        
        field_mappings = {
            "日期": type('FieldMapping', (), {
                'technical_field': 'Order_Date',
                'business_term': '日期',
                'confidence': 0.95,
                'data_type': 'DATE',
                'date_format': None,
            })()
        }
        
        result = self.builder._build_filter(filter_spec, field_mappings)
        
        assert result is not None
        assert result["filterType"] == "DATE"
        assert result["field"]["fieldCaption"] == "Order_Date"
        assert result["periodType"] == "MONTHS"
        assert result["dateRangeType"] == "LASTN"
        assert result["rangeN"] == 3
    
    def test_date_type_relative_todate(self):
        """DATE 类型 + RELATIVE (TODATE) → DATE (RelativeDateFilter)"""
        filter_spec = FilterSpec(
            field="日期",
            filter_type=FilterType.TIME_RANGE,
            time_filter=TimeFilterSpec(
                mode=TimeFilterMode.RELATIVE,
                period_type=PeriodType.YEARS,
                date_range_type=DateRangeType.TODATE,
            )
        )
        
        field_mappings = {
            "日期": type('FieldMapping', (), {
                'technical_field': 'Order_Date',
                'business_term': '日期',
                'confidence': 0.95,
                'data_type': 'DATE',
                'date_format': None,
            })()
        }
        
        result = self.builder._build_filter(filter_spec, field_mappings)
        
        assert result is not None
        assert result["filterType"] == "DATE"
        assert result["periodType"] == "YEARS"
        assert result["dateRangeType"] == "TODATE"
    
    def test_date_type_set_converts_to_range(self):
        """DATE 类型 + SET → 转换为 QUANTITATIVE_DATE 范围"""
        filter_spec = FilterSpec(
            field="日期",
            filter_type=FilterType.TIME_RANGE,
            time_filter=TimeFilterSpec(
                mode=TimeFilterMode.SET,
                date_values=["2024-01", "2024-02", "2024-03"],
            )
        )
        
        field_mappings = {
            "日期": type('FieldMapping', (), {
                'technical_field': 'Order_Date',
                'business_term': '日期',
                'confidence': 0.95,
                'data_type': 'DATE',
                'date_format': None,
            })()
        }
        
        result = self.builder._build_filter(filter_spec, field_mappings)
        
        assert result is not None
        # DATE 类型的 SET 应该被转换为 QUANTITATIVE_DATE 范围
        assert result["filterType"] == "QUANTITATIVE_DATE"
        assert result["minDate"] == "2024-01-01"
        assert result["maxDate"] == "2024-03-31"
    
    # ═══════════════════════════════════════════════════════════════════════
    # STRING 类型字段测试
    # ═══════════════════════════════════════════════════════════════════════
    
    def test_string_type_absolute_range_with_dateparse(self):
        """STRING 类型 + ABSOLUTE_RANGE → DATEPARSE + QUANTITATIVE_DATE"""
        filter_spec = FilterSpec(
            field="日期",
            filter_type=FilterType.TIME_RANGE,
            time_filter=TimeFilterSpec(
                mode=TimeFilterMode.ABSOLUTE_RANGE,
                start_date="2024-01-01",
                end_date="2024-12-31",
            )
        )
        
        # STRING 类型字段映射
        field_mappings = {
            "日期": type('FieldMapping', (), {
                'technical_field': 'Order_Date_Str',
                'business_term': '日期',
                'confidence': 0.95,
                'data_type': 'STRING',
                'date_format': 'yyyy-MM-dd',
            })()
        }
        
        result = self.builder._build_filter(filter_spec, field_mappings)
        
        assert result is not None
        assert result["filterType"] == "QUANTITATIVE_DATE"
        # STRING 类型应该使用 calculation 而不是 fieldCaption
        assert "calculation" in result["field"]
        assert "DATEPARSE" in result["field"]["calculation"]
        assert "Order_Date_Str" in result["field"]["calculation"]
        assert result["minDate"] == "2024-01-01"
        assert result["maxDate"] == "2024-12-31"
    
    def test_string_type_relative_with_dateparse(self):
        """STRING 类型 + RELATIVE → DATEPARSE + QUANTITATIVE_DATE (计算后的日期)"""
        filter_spec = FilterSpec(
            field="日期",
            filter_type=FilterType.TIME_RANGE,
            time_filter=TimeFilterSpec(
                mode=TimeFilterMode.RELATIVE,
                period_type=PeriodType.MONTHS,
                date_range_type=DateRangeType.LASTN,
                range_n=3,
            )
        )
        
        field_mappings = {
            "日期": type('FieldMapping', (), {
                'technical_field': 'Order_Date_Str',
                'business_term': '日期',
                'confidence': 0.95,
                'data_type': 'STRING',
                'date_format': 'yyyy-MM-dd',
            })()
        }
        
        result = self.builder._build_filter(filter_spec, field_mappings)
        
        assert result is not None
        # STRING 类型的相对日期应该被计算为具体日期，然后使用 DATEPARSE + QUANTITATIVE_DATE
        assert result["filterType"] == "QUANTITATIVE_DATE"
        assert "calculation" in result["field"]
        assert "DATEPARSE" in result["field"]["calculation"]
        # 应该有计算后的具体日期
        assert result["minDate"] is not None
        assert result["maxDate"] is not None
    
    def test_string_type_set_with_dateparse(self):
        """STRING 类型 + SET → DATEPARSE + QUANTITATIVE_DATE 范围"""
        filter_spec = FilterSpec(
            field="日期",
            filter_type=FilterType.TIME_RANGE,
            time_filter=TimeFilterSpec(
                mode=TimeFilterMode.SET,
                date_values=["2024-01", "2024-02"],
            )
        )
        
        field_mappings = {
            "日期": type('FieldMapping', (), {
                'technical_field': 'Order_Date_Str',
                'business_term': '日期',
                'confidence': 0.95,
                'data_type': 'STRING',
                'date_format': 'yyyy-MM-dd',
            })()
        }
        
        result = self.builder._build_filter(filter_spec, field_mappings)
        
        assert result is not None
        # STRING 类型的 SET 应该被转换为 DATEPARSE + QUANTITATIVE_DATE 范围
        assert result["filterType"] == "QUANTITATIVE_DATE"
        assert "calculation" in result["field"]
        assert "DATEPARSE" in result["field"]["calculation"]
    
    # ═══════════════════════════════════════════════════════════════════════
    # 未知类型字段测试（默认行为）
    # ═══════════════════════════════════════════════════════════════════════
    
    def test_unknown_type_defaults_to_date_behavior(self):
        """未知类型字段默认使用 DATE 类型行为"""
        filter_spec = FilterSpec(
            field="日期",
            filter_type=FilterType.TIME_RANGE,
            time_filter=TimeFilterSpec(
                mode=TimeFilterMode.ABSOLUTE_RANGE,
                start_date="2024-01-01",
                end_date="2024-12-31",
            )
        )
        
        # 没有 data_type 的字段映射
        field_mappings = {
            "日期": type('FieldMapping', (), {
                'technical_field': 'Order_Date',
                'business_term': '日期',
                'confidence': 0.95,
                'data_type': None,  # 未知类型
                'date_format': None,
            })()
        }
        
        result = self.builder._build_filter(filter_spec, field_mappings)
        
        assert result is not None
        assert result["filterType"] == "QUANTITATIVE_DATE"
        assert result["field"]["fieldCaption"] == "Order_Date"
    
    # ═══════════════════════════════════════════════════════════════════════
    # 辅助方法测试
    # ═══════════════════════════════════════════════════════════════════════
    
    def test_set_values_to_date_range_months(self):
        """测试月份格式的 SET 值转换为日期范围"""
        values = ["2024-01", "2024-02", "2024-03"]
        min_date, max_date = self.builder._set_values_to_date_range(values)
        
        assert min_date == "2024-01-01"
        assert max_date == "2024-03-31"
    
    def test_set_values_to_date_range_quarters(self):
        """测试季度格式的 SET 值转换为日期范围"""
        values = ["2024-Q1", "2024-Q2"]
        min_date, max_date = self.builder._set_values_to_date_range(values)
        
        assert min_date == "2024-01-01"
        assert max_date == "2024-06-30"
    
    def test_set_values_to_date_range_years(self):
        """测试年份格式的 SET 值转换为日期范围"""
        values = ["2023", "2024"]
        min_date, max_date = self.builder._set_values_to_date_range(values)
        
        assert min_date == "2023-01-01"
        assert max_date == "2024-12-31"
    
    def test_set_values_to_date_range_days(self):
        """测试日期格式的 SET 值转换为日期范围"""
        values = ["2024-01-15", "2024-02-20", "2024-03-25"]
        min_date, max_date = self.builder._set_values_to_date_range(values)
        
        assert min_date == "2024-01-15"
        assert max_date == "2024-03-25"
    
    def test_set_values_to_date_range_mixed(self):
        """测试混合格式的 SET 值转换为日期范围"""
        values = ["2024-01", "2024-Q2", "2024-07-15"]
        min_date, max_date = self.builder._set_values_to_date_range(values)
        
        assert min_date == "2024-01-01"
        assert max_date == "2024-07-15"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
