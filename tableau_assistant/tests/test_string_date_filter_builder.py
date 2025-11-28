"""
测试 StringDateFilterBuilder 模块
"""
import pytest
from tableau_assistant.src.capabilities.query.builder.string_date_filter_builder import StringDateFilterBuilder
from tableau_assistant.src.models.time_granularity import TimeGranularity
from tableau_assistant.src.capabilities.date_processing.format_detector import DateFormatType
from tableau_assistant.src.models.vizql_types import SetFilter, MatchFilter, QuantitativeDateFilter


class TestStringDateFilterBuilder:
    """测试 StringDateFilterBuilder"""
    
    def setup_method(self):
        """每个测试方法前执行"""
        self.builder = StringDateFilterBuilder()
    
    # ========== 场景1：YYYY-MM 格式 ==========
    
    def test_year_month_format_year_question(self):
        """
        场景：字段="2024-01"（YYYY-MM），问题="2024年的销售额"
        预期：使用 MatchFilter，startsWith="2024-"
        """
        filter_obj = self.builder.build_filter(
            field_name="YearMonth",
            field_format=DateFormatType.YEAR_MONTH,
            field_granularity=TimeGranularity.MONTH,
            question_granularity=TimeGranularity.YEAR,
            start_date="2024-01-01",
            end_date="2024-12-31"
        )
        
        assert isinstance(filter_obj, MatchFilter)
        assert filter_obj.startsWith == "2024-"
        assert filter_obj.field.fieldCaption == "YearMonth"
    
    def test_year_month_format_quarter_question(self):
        """
        场景：字段="2024-01"（YYYY-MM），问题="2024年Q1的销售额"
        预期：使用 SetFilter，枚举3个月
        """
        filter_obj = self.builder.build_filter(
            field_name="YearMonth",
            field_format=DateFormatType.YEAR_MONTH,
            field_granularity=TimeGranularity.MONTH,
            question_granularity=TimeGranularity.QUARTER,
            start_date="2024-01-01",
            end_date="2024-03-31"
        )
        
        assert isinstance(filter_obj, SetFilter)
        assert len(filter_obj.values) == 3
        assert filter_obj.values == ["2024-01", "2024-02", "2024-03"]
    
    def test_year_month_format_month_question(self):
        """
        场景：字段="2024-01"（YYYY-MM），问题="2024年1月的销售额"
        预期：使用 SetFilter，精确匹配
        """
        filter_obj = self.builder.build_filter(
            field_name="YearMonth",
            field_format=DateFormatType.YEAR_MONTH,
            field_granularity=TimeGranularity.MONTH,
            question_granularity=TimeGranularity.MONTH,
            start_date="2024-01-01",
            end_date="2024-01-31"
        )
        
        assert isinstance(filter_obj, SetFilter)
        assert len(filter_obj.values) == 1
        assert filter_obj.values == ["2024-01"]
    
    # ========== 场景2：YYYY-QN 格式 ==========
    
    def test_quarter_format_year_question(self):
        """
        场景：字段="2024-Q1"（YYYY-QN），问题="2024年的销售额"
        预期：使用 MatchFilter，startsWith="2024-"
        """
        filter_obj = self.builder.build_filter(
            field_name="Quarter",
            field_format=DateFormatType.QUARTER,
            field_granularity=TimeGranularity.QUARTER,
            question_granularity=TimeGranularity.YEAR,
            start_date="2024-01-01",
            end_date="2024-12-31"
        )
        
        assert isinstance(filter_obj, MatchFilter)
        assert filter_obj.startsWith == "2024-"
    
    def test_quarter_format_quarter_question(self):
        """
        场景：字段="2024-Q1"（YYYY-QN），问题="2024年Q1的销售额"
        预期：使用 SetFilter，精确匹配
        """
        filter_obj = self.builder.build_filter(
            field_name="Quarter",
            field_format=DateFormatType.QUARTER,
            field_granularity=TimeGranularity.QUARTER,
            question_granularity=TimeGranularity.QUARTER,
            start_date="2024-01-01",
            end_date="2024-03-31"
        )
        
        assert isinstance(filter_obj, SetFilter)
        assert len(filter_obj.values) == 1
        assert filter_obj.values == ["2024-Q1"]
    
    # ========== 场景3：YYYY-MM-DD 格式 ==========
    
    def test_iso_date_format_year_question(self):
        """
        场景：字段="2024-01-15"（YYYY-MM-DD），问题="2024年的销售额"
        预期：使用 QuantitativeDateFilter（365天太多）
        """
        filter_obj = self.builder.build_filter(
            field_name="Date",
            field_format=DateFormatType.ISO_DATE,
            field_granularity=TimeGranularity.DAY,
            question_granularity=TimeGranularity.YEAR,
            start_date="2024-01-01",
            end_date="2024-12-31"
        )
        
        assert isinstance(filter_obj, QuantitativeDateFilter)
        assert filter_obj.minDate == "2024-01-01"
        assert filter_obj.maxDate == "2024-12-31"
        assert "DATEPARSE" in filter_obj.field.calculation
    
    def test_iso_date_format_month_question(self):
        """
        场景：字段="2024-01-15"（YYYY-MM-DD），问题="2024年1月的销售额"
        预期：使用 MatchFilter，startsWith="2024-01-"
        """
        filter_obj = self.builder.build_filter(
            field_name="Date",
            field_format=DateFormatType.ISO_DATE,
            field_granularity=TimeGranularity.DAY,
            question_granularity=TimeGranularity.MONTH,
            start_date="2024-01-01",
            end_date="2024-01-31"
        )
        
        assert isinstance(filter_obj, MatchFilter)
        assert filter_obj.startsWith == "2024-01-"
    
    def test_iso_date_format_week_question(self):
        """
        场景：字段="2024-01-15"（YYYY-MM-DD），问题="第1周的销售额"
        预期：使用 SetFilter，枚举7天
        """
        filter_obj = self.builder.build_filter(
            field_name="Date",
            field_format=DateFormatType.ISO_DATE,
            field_granularity=TimeGranularity.DAY,
            question_granularity=TimeGranularity.WEEK,
            start_date="2024-01-01",
            end_date="2024-01-07"
        )
        
        assert isinstance(filter_obj, SetFilter)
        assert len(filter_obj.values) == 7
        assert filter_obj.values[0] == "2024-01-01"
        assert filter_obj.values[-1] == "2024-01-07"
    
    def test_iso_date_format_day_question(self):
        """
        场景：字段="2024-01-15"（YYYY-MM-DD），问题="1月15日的销售额"
        预期：使用 SetFilter，精确匹配
        """
        filter_obj = self.builder.build_filter(
            field_name="Date",
            field_format=DateFormatType.ISO_DATE,
            field_granularity=TimeGranularity.DAY,
            question_granularity=TimeGranularity.DAY,
            start_date="2024-01-15",
            end_date="2024-01-15"
        )
        
        assert isinstance(filter_obj, SetFilter)
        assert len(filter_obj.values) == 1
        assert filter_obj.values == ["2024-01-15"]
    
    # ========== 场景4：MM/DD/YYYY 格式（不支持前缀匹配）==========
    
    def test_us_date_format_year_question(self):
        """
        场景：字段="01/15/2024"（MM/DD/YYYY），问题="2024年的销售额"
        预期：使用 QuantitativeDateFilter（365天太多 + 不支持前缀）
        """
        filter_obj = self.builder.build_filter(
            field_name="Date",
            field_format=DateFormatType.US_DATE,
            field_granularity=TimeGranularity.DAY,
            question_granularity=TimeGranularity.YEAR,
            start_date="2024-01-01",
            end_date="2024-12-31"
        )
        
        assert isinstance(filter_obj, QuantitativeDateFilter)
        assert filter_obj.minDate == "2024-01-01"
        assert filter_obj.maxDate == "2024-12-31"
    
    def test_us_date_format_month_question(self):
        """
        场景：字段="01/15/2024"（MM/DD/YYYY），问题="2024年1月的销售额"
        预期：使用 SetFilter，枚举31天（不支持前缀匹配）
        """
        filter_obj = self.builder.build_filter(
            field_name="Date",
            field_format=DateFormatType.US_DATE,
            field_granularity=TimeGranularity.DAY,
            question_granularity=TimeGranularity.MONTH,
            start_date="2024-01-01",
            end_date="2024-01-31"
        )
        
        assert isinstance(filter_obj, SetFilter)
        assert len(filter_obj.values) == 31
        assert filter_obj.values[0] == "01/01/2024"
        assert filter_obj.values[-1] == "01/31/2024"
    
    # ========== 场景5：字段粒度 < 问题粒度（无法实现）==========
    
    def test_field_coarser_than_question(self):
        """
        场景：字段="2024"（YYYY），问题="2024年1月的销售额"
        预期：返回 None（字段粒度 < 问题粒度，无法实现）
        """
        filter_obj = self.builder.build_filter(
            field_name="Year",
            field_format=DateFormatType.YEAR_ONLY,
            field_granularity=TimeGranularity.YEAR,
            question_granularity=TimeGranularity.MONTH,
            start_date="2024-01-01",
            end_date="2024-01-31"
        )
        
        assert filter_obj is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
