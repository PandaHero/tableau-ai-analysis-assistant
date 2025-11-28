"""
Unit tests for QueryBuilder STRING date field handling.

Tests the _build_date_filter_for_string_field method with different date granularities.
"""
import pytest
from datetime import datetime
from tableau_assistant.src.capabilities.query.builder.builder import QueryBuilder
from tableau_assistant.src.capabilities.date_processing.manager import DateManager
from tableau_assistant.src.capabilities.date_processing.format_detector import DateFormatType
from tableau_assistant.src.models.metadata import Metadata, FieldMetadata


@pytest.fixture
def date_manager():
    """Create DateManager instance."""
    return DateManager(
        anchor_date=datetime(2024, 12, 31),
        week_start_day=0
    )


@pytest.fixture
def metadata_with_string_dates():
    """Create metadata with STRING date fields of different granularities."""
    return Metadata(
        datasource_name="Test Datasource",
        datasource_luid="test-luid-123",
        field_count=7,
        fields=[
            FieldMetadata(
                name="Full Date String",
                fieldCaption="Full Date String",
                dataType="STRING",
                role="dimension",
                sample_values=["01/15/2024", "02/20/2024", "12/31/2024"]
            ),
            FieldMetadata(
                name="Year Month String",
                fieldCaption="Year Month String",
                dataType="STRING",
                role="dimension",
                sample_values=["2024-01", "2024-02", "2024-12"]
            ),
            FieldMetadata(
                name="Year Only String",
                fieldCaption="Year Only String",
                dataType="STRING",
                role="dimension",
                sample_values=["2024", "2023", "2022"]
            ),
            FieldMetadata(
                name="Month Year String",
                fieldCaption="Month Year String",
                dataType="STRING",
                role="dimension",
                sample_values=["01/2024", "02/2024", "12/2024"]
            ),
            FieldMetadata(
                name="Quarter String",
                fieldCaption="Quarter String",
                dataType="STRING",
                role="dimension",
                sample_values=["2024-Q1", "2024-Q2", "2024-Q3", "2024-Q4"]
            ),
            FieldMetadata(
                name="Week String",
                fieldCaption="Week String",
                dataType="STRING",
                role="dimension",
                sample_values=["2024-W01", "2024-W02", "2024-W52"]
            ),
            FieldMetadata(
                name="Sales",
                fieldCaption="Sales",
                dataType="REAL",
                role="measure"
            ),
        ]
    )


@pytest.fixture
def query_builder_with_date_manager(metadata_with_string_dates, date_manager):
    """Create QueryBuilder with DateManager."""
    return QueryBuilder(
        metadata=metadata_with_string_dates,
        anchor_date=datetime(2024, 12, 31),
        week_start_day=0,
        date_manager=date_manager
    )


# ============= Full Date Format Tests =============

class TestFullDateStringFilter:
    """Test STRING date field filtering with full date format."""
    
    def test_full_date_filter_without_date_manager(self, metadata_with_string_dates):
        """Test that filter returns None without DateManager."""
        query_builder = QueryBuilder(
            metadata=metadata_with_string_dates,
            anchor_date=datetime(2024, 12, 31),
            week_start_day=0,
            date_manager=None  # No DateManager
        )
        
        filter_result = query_builder._build_date_filter_for_string_field(
            field_name="Full Date String",
            start_date="2024-01-01",
            end_date="2024-12-31"
        )
        
        assert filter_result is None
    
    def test_full_date_filter_with_cached_format(
        self,
        query_builder_with_date_manager,
        date_manager
    ):
        """Test full date filter with cached format."""
        # Cache the format
        date_manager.cache_field_format("Full Date String", DateFormatType.US_DATE)
        
        # Use a small date range (< 100 days) to trigger SetFilter
        filter_result = query_builder_with_date_manager._build_date_filter_for_string_field(
            field_name="Full Date String",
            start_date="2024-01-01",
            end_date="2024-01-31"  # 31 days
        )
        
        # Should return a SetFilter with 31 date values
        assert filter_result is not None
        from tableau_assistant.src.models.vizql_types import SetFilter
        assert isinstance(filter_result, SetFilter)
        assert len(filter_result.values) == 31


# ============= Year-Month Format Tests =============

class TestYearMonthStringFilter:
    """Test STRING date field filtering with year-month format."""
    
    def test_year_month_filter(self, query_builder_with_date_manager, date_manager):
        """Test year-month format filter."""
        # Cache the format
        date_manager.cache_field_format("Year Month String", DateFormatType.YEAR_MONTH)
        
        filter_result = query_builder_with_date_manager._build_date_filter_for_string_field(
            field_name="Year Month String",
            start_date="2024-01-01",
            end_date="2024-12-31"
        )
        
        # Should return a SetFilter with 12 month values
        assert filter_result is not None
        from tableau_assistant.src.models.vizql_types import SetFilter
        assert isinstance(filter_result, SetFilter)
        assert len(filter_result.values) == 12
        assert filter_result.values[0] == "2024-01"
        assert filter_result.values[-1] == "2024-12"
    
    def test_year_month_filter_extracts_correct_range(
        self,
        query_builder_with_date_manager,
        date_manager
    ):
        """Test that year-month filter extracts correct date range."""
        date_manager.cache_field_format("Year Month String", DateFormatType.YEAR_MONTH)
        
        # Test with specific date range
        filter_result = query_builder_with_date_manager._build_date_filter_for_string_field(
            field_name="Year Month String",
            start_date="2024-03-15",  # Should extract "2024-03"
            end_date="2024-09-20"     # Should extract "2024-09"
        )
        
        # Should return SetFilter with months from March to September (7 months)
        assert filter_result is not None
        from tableau_assistant.src.models.vizql_types import SetFilter
        assert isinstance(filter_result, SetFilter)
        assert len(filter_result.values) == 7
        assert filter_result.values[0] == "2024-03"
        assert filter_result.values[-1] == "2024-09"


# ============= Year Only Format Tests =============

class TestYearOnlyStringFilter:
    """Test STRING date field filtering with year-only format."""
    
    def test_year_only_filter(self, query_builder_with_date_manager, date_manager):
        """Test year-only format filter."""
        # Cache the format
        date_manager.cache_field_format("Year Only String", DateFormatType.YEAR_ONLY)
        
        filter_result = query_builder_with_date_manager._build_date_filter_for_string_field(
            field_name="Year Only String",
            start_date="2024-01-01",
            end_date="2024-12-31"
        )
        
        # Should return SetFilter with 1 year value
        assert filter_result is not None
        from tableau_assistant.src.models.vizql_types import SetFilter
        assert isinstance(filter_result, SetFilter)
        assert len(filter_result.values) == 1
        assert filter_result.values[0] == "2024"
    
    def test_year_only_filter_extracts_correct_year(
        self,
        query_builder_with_date_manager,
        date_manager
    ):
        """Test that year-only filter extracts correct year."""
        date_manager.cache_field_format("Year Only String", DateFormatType.YEAR_ONLY)
        
        # Test with specific date range spanning 2 years
        filter_result = query_builder_with_date_manager._build_date_filter_for_string_field(
            field_name="Year Only String",
            start_date="2023-01-01",
            end_date="2024-12-31"
        )
        
        # Should return SetFilter with 2 year values
        assert filter_result is not None
        from tableau_assistant.src.models.vizql_types import SetFilter
        assert isinstance(filter_result, SetFilter)
        assert len(filter_result.values) == 2
        assert filter_result.values[0] == "2023"
        assert filter_result.values[1] == "2024"


# ============= Month-Year Format Tests =============

class TestMonthYearStringFilter:
    """Test STRING date field filtering with month-year format."""
    
    def test_month_year_filter(self, query_builder_with_date_manager, date_manager):
        """Test month-year format filter."""
        # Cache the format
        date_manager.cache_field_format("Month Year String", DateFormatType.MONTH_YEAR)
        
        filter_result = query_builder_with_date_manager._build_date_filter_for_string_field(
            field_name="Month Year String",
            start_date="2024-01-01",
            end_date="2024-12-31"
        )
        
        # Should return SetFilter with 12 month values in MM/YYYY format
        assert filter_result is not None
        from tableau_assistant.src.models.vizql_types import SetFilter
        assert isinstance(filter_result, SetFilter)
        assert len(filter_result.values) == 12
        assert filter_result.values[0] == "01/2024"
        assert filter_result.values[-1] == "12/2024"


# ============= Quarter Format Tests =============

class TestQuarterStringFilter:
    """Test STRING date field filtering with quarter format."""
    
    def test_quarter_filter_full_year(self, query_builder_with_date_manager, date_manager):
        """Test quarter format filter for full year."""
        # Cache the format
        date_manager.cache_field_format("Quarter String", DateFormatType.QUARTER)
        
        filter_result = query_builder_with_date_manager._build_date_filter_for_string_field(
            field_name="Quarter String",
            start_date="2024-01-01",
            end_date="2024-12-31"
        )
        
        # Should return SetFilter with 4 quarter values
        assert filter_result is not None
        from tableau_assistant.src.models.vizql_types import SetFilter
        assert isinstance(filter_result, SetFilter)
        assert len(filter_result.values) == 4
        assert filter_result.values[0] == "2024-Q1"
        assert filter_result.values[1] == "2024-Q2"
        assert filter_result.values[2] == "2024-Q3"
        assert filter_result.values[3] == "2024-Q4"
    
    def test_quarter_filter_partial_year(self, query_builder_with_date_manager, date_manager):
        """Test quarter format filter for partial year."""
        # Cache the format
        date_manager.cache_field_format("Quarter String", DateFormatType.QUARTER)
        
        # Q2 to Q3
        filter_result = query_builder_with_date_manager._build_date_filter_for_string_field(
            field_name="Quarter String",
            start_date="2024-04-01",  # Q2 starts
            end_date="2024-09-30"     # Q3 ends
        )
        
        # Should return SetFilter with 2 quarter values
        assert filter_result is not None
        from tableau_assistant.src.models.vizql_types import SetFilter
        assert isinstance(filter_result, SetFilter)
        assert len(filter_result.values) == 2
        assert filter_result.values[0] == "2024-Q2"
        assert filter_result.values[1] == "2024-Q3"


# ============= Week Format Tests =============

class TestWeekStringFilter:
    """Test STRING date field filtering with week format."""
    
    def test_week_filter(self, query_builder_with_date_manager, date_manager):
        """Test week format filter."""
        # Cache the format
        date_manager.cache_field_format("Week String", DateFormatType.YEAR_WEEK)
        
        # Test a 4-week range
        filter_result = query_builder_with_date_manager._build_date_filter_for_string_field(
            field_name="Week String",
            start_date="2024-01-01",
            end_date="2024-01-28"  # 4 weeks
        )
        
        # Should return SetFilter with week values
        assert filter_result is not None
        from tableau_assistant.src.models.vizql_types import SetFilter
        assert isinstance(filter_result, SetFilter)
        # Should have approximately 4 weeks
        assert len(filter_result.values) >= 4
        # First week should be W01
        assert filter_result.values[0].startswith("2024-W")


# ============= Error Handling Tests =============

class TestStringDateFilterErrorHandling:
    """Test error handling for STRING date field filtering."""
    
    def test_filter_non_string_field(self, query_builder_with_date_manager):
        """Test that filter returns None for non-STRING fields."""
        filter_result = query_builder_with_date_manager._build_date_filter_for_string_field(
            field_name="Sales",  # REAL type, not STRING
            start_date="2024-01-01",
            end_date="2024-12-31"
        )
        
        assert filter_result is None
    
    def test_filter_field_without_cached_format(self, query_builder_with_date_manager):
        """Test that filter returns None when format is not cached."""
        filter_result = query_builder_with_date_manager._build_date_filter_for_string_field(
            field_name="Full Date String",  # Format not cached
            start_date="2024-01-01",
            end_date="2024-12-31"
        )
        
        assert filter_result is None
    
    def test_filter_nonexistent_field(self, query_builder_with_date_manager):
        """Test that filter returns None for nonexistent fields."""
        filter_result = query_builder_with_date_manager._build_date_filter_for_string_field(
            field_name="Nonexistent Field",
            start_date="2024-01-01",
            end_date="2024-12-31"
        )
        
        assert filter_result is None


# ============= Integration Tests =============

class TestStringDateFilterIntegration:
    """Integration tests for STRING date field filtering."""
    
    def test_detect_and_filter_workflow(
        self,
        query_builder_with_date_manager,
        date_manager
    ):
        """Test complete workflow: detect format -> cache -> filter."""
        # 1. Detect format
        samples = ["2024-01", "2024-02", "2024-12"]
        format_type = date_manager.detect_field_date_format(samples)
        
        assert format_type == DateFormatType.YEAR_MONTH
        
        # 2. Cache format
        date_manager.cache_field_format("Year Month String", format_type)
        
        # 3. Build filter
        filter_result = query_builder_with_date_manager._build_date_filter_for_string_field(
            field_name="Year Month String",
            start_date="2024-01-01",
            end_date="2024-12-31"
        )
        
        # Should successfully generate a SetFilter
        assert filter_result is not None
        from tableau_assistant.src.models.vizql_types import SetFilter
        assert isinstance(filter_result, SetFilter)
        assert len(filter_result.values) == 12
    
    def test_large_date_range_returns_none(
        self,
        query_builder_with_date_manager,
        date_manager
    ):
        """Test that large date ranges (>100 days) return None."""
        # Cache format
        date_manager.cache_field_format("Full Date String", DateFormatType.US_DATE)
        
        # Use a large date range (>100 days)
        filter_result = query_builder_with_date_manager._build_date_filter_for_string_field(
            field_name="Full Date String",
            start_date="2024-01-01",
            end_date="2024-12-31"  # 366 days
        )
        
        # Should return None for large date ranges
        assert filter_result is None


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
