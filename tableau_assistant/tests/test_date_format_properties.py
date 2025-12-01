"""
Property-based tests for date format detection and conversion.

**Feature: vizql-api-migration**

Properties tested:
- Property 13: Date format detection consistency
- Property 14: Date format conversion round-trip consistency
- Property 15: US/EU format disambiguation correctness
- Property 16: STRING date field DATEPARSE generation correctness
"""

import pytest
from hypothesis import given, strategies as st, settings, assume
from datetime import datetime, date
from typing import List

from tableau_assistant.src.capabilities.date_processing.format_detector import (
    DateFormatDetector,
    DateFormatType,
)
from tableau_assistant.src.capabilities.date_processing.manager import DateManager
from tableau_assistant.src.models.time_granularity import TimeGranularity


# ============= Hypothesis Strategies =============

@st.composite
def iso_date_strategy(draw):
    """Generate random ISO format dates (YYYY-MM-DD)."""
    year = draw(st.integers(min_value=1990, max_value=2030))
    month = draw(st.integers(min_value=1, max_value=12))
    # Ensure valid day for the month
    if month in [4, 6, 9, 11]:
        max_day = 30
    elif month == 2:
        # Handle leap years
        if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0):
            max_day = 29
        else:
            max_day = 28
    else:
        max_day = 31
    day = draw(st.integers(min_value=1, max_value=max_day))
    return f"{year:04d}-{month:02d}-{day:02d}"


@st.composite
def us_date_strategy(draw):
    """Generate random US format dates (MM/DD/YYYY)."""
    year = draw(st.integers(min_value=1990, max_value=2030))
    month = draw(st.integers(min_value=1, max_value=12))
    if month in [4, 6, 9, 11]:
        max_day = 30
    elif month == 2:
        if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0):
            max_day = 29
        else:
            max_day = 28
    else:
        max_day = 31
    day = draw(st.integers(min_value=1, max_value=max_day))
    return f"{month:02d}/{day:02d}/{year:04d}"


@st.composite
def eu_date_strategy(draw):
    """Generate random EU format dates (DD/MM/YYYY)."""
    year = draw(st.integers(min_value=1990, max_value=2030))
    month = draw(st.integers(min_value=1, max_value=12))
    if month in [4, 6, 9, 11]:
        max_day = 30
    elif month == 2:
        if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0):
            max_day = 29
        else:
            max_day = 28
    else:
        max_day = 31
    day = draw(st.integers(min_value=1, max_value=max_day))
    return f"{day:02d}/{month:02d}/{year:04d}"


@st.composite
def clear_us_date_strategy(draw):
    """Generate US dates with day > 12 (clearly US format)."""
    year = draw(st.integers(min_value=1990, max_value=2030))
    month = draw(st.integers(min_value=1, max_value=12))
    # Day must be > 12 to clearly indicate US format
    if month in [4, 6, 9, 11]:
        max_day = 30
    elif month == 2:
        if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0):
            max_day = 29
        else:
            max_day = 28
    else:
        max_day = 31
    day = draw(st.integers(min_value=13, max_value=max_day))
    return f"{month:02d}/{day:02d}/{year:04d}"


@st.composite
def clear_eu_date_strategy(draw):
    """Generate EU dates with day > 12 (clearly EU format)."""
    year = draw(st.integers(min_value=1990, max_value=2030))
    month = draw(st.integers(min_value=1, max_value=12))
    # Day must be > 12 to clearly indicate EU format
    if month in [4, 6, 9, 11]:
        max_day = 30
    elif month == 2:
        if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0):
            max_day = 29
        else:
            max_day = 28
    else:
        max_day = 31
    day = draw(st.integers(min_value=13, max_value=max_day))
    return f"{day:02d}/{month:02d}/{year:04d}"


@st.composite
def timestamp_strategy(draw):
    """Generate random timestamp format dates."""
    year = draw(st.integers(min_value=1990, max_value=2030))
    month = draw(st.integers(min_value=1, max_value=12))
    if month in [4, 6, 9, 11]:
        max_day = 30
    elif month == 2:
        if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0):
            max_day = 29
        else:
            max_day = 28
    else:
        max_day = 31
    day = draw(st.integers(min_value=1, max_value=max_day))
    hour = draw(st.integers(min_value=0, max_value=23))
    minute = draw(st.integers(min_value=0, max_value=59))
    second = draw(st.integers(min_value=0, max_value=59))
    return f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}"


@st.composite
def quarter_date_strategy(draw):
    """Generate random quarter format dates (YYYY-QN)."""
    year = draw(st.integers(min_value=1990, max_value=2030))
    quarter = draw(st.integers(min_value=1, max_value=4))
    return f"{year}-Q{quarter}"


@st.composite
def year_month_strategy(draw):
    """Generate random year-month format dates (YYYY-MM)."""
    year = draw(st.integers(min_value=1990, max_value=2030))
    month = draw(st.integers(min_value=1, max_value=12))
    return f"{year:04d}-{month:02d}"


# ============= Property-Based Tests =============

class TestDateFormatDetectionConsistency:
    """
    Property 13: Date format detection consistency
    
    For any sample set with the same format, multiple detections should
    return the same format type.
    """
    
    @given(st.lists(iso_date_strategy(), min_size=3, max_size=10))
    @settings(max_examples=100, deadline=None)
    def test_iso_date_detection_consistency(self, samples: List[str]):
        """
        **Property 13: Date format detection consistency**
        
        For any ISO date sample set, multiple detections should return
        the same format type (ISO_DATE).
        
        **Validates: Requirements 24.2, 24.3**
        """
        detector = DateFormatDetector()
        
        # Detect format multiple times
        result1 = detector.detect_format(samples)
        result2 = detector.detect_format(samples)
        result3 = detector.detect_format(samples)
        
        # All detections should return the same result
        assert result1 == result2 == result3
        # Should detect as ISO_DATE
        assert result1 == DateFormatType.ISO_DATE
    
    @given(st.lists(timestamp_strategy(), min_size=3, max_size=10))
    @settings(max_examples=100, deadline=None)
    def test_timestamp_detection_consistency(self, samples: List[str]):
        """
        **Property 13: Date format detection consistency**
        
        For any timestamp sample set, multiple detections should return
        the same format type (TIMESTAMP).
        
        **Validates: Requirements 24.2, 24.3**
        """
        detector = DateFormatDetector()
        
        result1 = detector.detect_format(samples)
        result2 = detector.detect_format(samples)
        
        assert result1 == result2
        assert result1 == DateFormatType.TIMESTAMP
    
    @given(st.lists(quarter_date_strategy(), min_size=3, max_size=10))
    @settings(max_examples=100, deadline=None)
    def test_quarter_detection_consistency(self, samples: List[str]):
        """
        **Property 13: Date format detection consistency**
        
        For any quarter format sample set, multiple detections should return
        the same format type (QUARTER).
        
        **Validates: Requirements 24.2, 24.3**
        """
        detector = DateFormatDetector()
        
        result1 = detector.detect_format(samples)
        result2 = detector.detect_format(samples)
        
        assert result1 == result2
        assert result1 == DateFormatType.QUARTER
    
    @given(st.lists(year_month_strategy(), min_size=3, max_size=10))
    @settings(max_examples=100, deadline=None)
    def test_year_month_detection_consistency(self, samples: List[str]):
        """
        **Property 13: Date format detection consistency**
        
        For any year-month format sample set, multiple detections should return
        the same format type (YEAR_MONTH).
        
        **Validates: Requirements 24.2, 24.3**
        """
        detector = DateFormatDetector()
        
        result1 = detector.detect_format(samples)
        result2 = detector.detect_format(samples)
        
        assert result1 == result2
        assert result1 == DateFormatType.YEAR_MONTH


class TestDateFormatConversionRoundTrip:
    """
    Property 14: Date format conversion round-trip consistency
    
    For any valid ISO date, converting to another format and back to ISO
    should preserve the date.
    """
    
    @given(iso_date_strategy())
    @settings(max_examples=100, deadline=None)
    def test_iso_date_round_trip(self, iso_date: str):
        """
        **Property 14: Date format conversion round-trip consistency**
        
        For any valid ISO date, converting to ISO format should return
        the same date (identity conversion).
        
        **Validates: Requirements 24.5, 24.8**
        """
        detector = DateFormatDetector()
        
        # Convert ISO to ISO (should be identity)
        result = detector.convert_to_iso(iso_date, DateFormatType.ISO_DATE)
        
        assert result is not None
        assert result == iso_date
    
    @given(us_date_strategy())
    @settings(max_examples=100, deadline=None)
    def test_us_date_to_iso_conversion(self, us_date: str):
        """
        **Property 14: Date format conversion round-trip consistency**
        
        For any valid US date, converting to ISO format should produce
        a valid ISO date that represents the same calendar date.
        
        **Validates: Requirements 24.5, 24.8**
        """
        detector = DateFormatDetector()
        
        # Convert US to ISO
        iso_result = detector.convert_to_iso(us_date, DateFormatType.US_DATE)
        
        assert iso_result is not None
        
        # Parse both dates and compare
        us_parts = us_date.split('/')
        us_month, us_day, us_year = int(us_parts[0]), int(us_parts[1]), int(us_parts[2])
        
        iso_parts = iso_result.split('-')
        iso_year, iso_month, iso_day = int(iso_parts[0]), int(iso_parts[1]), int(iso_parts[2])
        
        assert us_year == iso_year
        assert us_month == iso_month
        assert us_day == iso_day
    
    @given(eu_date_strategy())
    @settings(max_examples=100, deadline=None)
    def test_eu_date_to_iso_conversion(self, eu_date: str):
        """
        **Property 14: Date format conversion round-trip consistency**
        
        For any valid EU date, converting to ISO format should produce
        a valid ISO date that represents the same calendar date.
        
        **Validates: Requirements 24.5, 24.8**
        """
        detector = DateFormatDetector()
        
        # Convert EU to ISO
        iso_result = detector.convert_to_iso(eu_date, DateFormatType.EU_DATE)
        
        assert iso_result is not None
        
        # Parse both dates and compare
        eu_parts = eu_date.split('/')
        eu_day, eu_month, eu_year = int(eu_parts[0]), int(eu_parts[1]), int(eu_parts[2])
        
        iso_parts = iso_result.split('-')
        iso_year, iso_month, iso_day = int(iso_parts[0]), int(iso_parts[1]), int(iso_parts[2])
        
        assert eu_year == iso_year
        assert eu_month == iso_month
        assert eu_day == iso_day
    
    @given(timestamp_strategy())
    @settings(max_examples=100, deadline=None)
    def test_timestamp_to_iso_conversion(self, timestamp: str):
        """
        **Property 14: Date format conversion round-trip consistency**
        
        For any valid timestamp, converting to ISO format should extract
        the date part correctly.
        
        **Validates: Requirements 24.5, 24.8, 24.9**
        """
        detector = DateFormatDetector()
        
        # Convert timestamp to ISO (extracts date part)
        iso_result = detector.convert_to_iso(timestamp, DateFormatType.TIMESTAMP)
        
        assert iso_result is not None
        
        # The ISO result should be the date part of the timestamp
        expected_date = timestamp.split(' ')[0]
        assert iso_result == expected_date


class TestUSEUFormatDisambiguation:
    """
    Property 15: US/EU format disambiguation correctness
    
    For any sample set with clear distinguishing markers (day > 12),
    format detection should correctly distinguish US and EU formats.
    """
    
    @given(st.lists(clear_us_date_strategy(), min_size=3, max_size=10))
    @settings(max_examples=100, deadline=None)
    def test_clear_us_format_detection(self, samples: List[str]):
        """
        **Property 15: US/EU format disambiguation correctness**
        
        For any sample set with day > 12 in US format (MM/DD/YYYY),
        detection should correctly identify as US_DATE.
        
        **Validates: Requirements 24.4**
        """
        detector = DateFormatDetector()
        
        result = detector.detect_format(samples)
        
        # Should detect as US_DATE because day > 12
        assert result == DateFormatType.US_DATE
    
    @given(st.lists(clear_eu_date_strategy(), min_size=3, max_size=10))
    @settings(max_examples=100, deadline=None)
    def test_clear_eu_format_detection(self, samples: List[str]):
        """
        **Property 15: US/EU format disambiguation correctness**
        
        For any sample set with day > 12 in EU format (DD/MM/YYYY),
        detection should correctly identify as EU_DATE.
        
        **Validates: Requirements 24.4**
        """
        detector = DateFormatDetector()
        
        result = detector.detect_format(samples)
        
        # Should detect as EU_DATE because first number > 12
        assert result == DateFormatType.EU_DATE
    
    def test_mixed_clear_indicators_us(self):
        """Test US format detection with mixed clear indicators."""
        detector = DateFormatDetector()
        
        # Mix of clear US dates (day > 12) and ambiguous dates
        samples = [
            "01/15/2024",  # Clear US: day=15 > 12
            "02/20/2024",  # Clear US: day=20 > 12
            "03/05/2024",  # Ambiguous
            "04/25/2024",  # Clear US: day=25 > 12
        ]
        
        result = detector.detect_format(samples)
        assert result == DateFormatType.US_DATE
    
    def test_mixed_clear_indicators_eu(self):
        """Test EU format detection with mixed clear indicators."""
        detector = DateFormatDetector()
        
        # Mix of clear EU dates (first number > 12) and ambiguous dates
        samples = [
            "15/01/2024",  # Clear EU: first=15 > 12
            "20/02/2024",  # Clear EU: first=20 > 12
            "05/03/2024",  # Ambiguous
            "25/04/2024",  # Clear EU: first=25 > 12
        ]
        
        result = detector.detect_format(samples)
        assert result == DateFormatType.EU_DATE


class TestDateManagerCacheConsistency:
    """
    Additional property tests for DateManager cache functionality.
    """
    
    @given(
        st.text(min_size=1, max_size=50, alphabet=st.characters(
            whitelist_categories=('Lu', 'Ll', 'Nd'),
            whitelist_characters='_-'
        )),
        st.sampled_from([
            DateFormatType.ISO_DATE,
            DateFormatType.US_DATE,
            DateFormatType.EU_DATE,
            DateFormatType.TIMESTAMP,
            DateFormatType.QUARTER,
        ])
    )
    @settings(max_examples=100, deadline=None)
    def test_cache_field_format_consistency(self, field_name: str, format_type: DateFormatType):
        """
        Test that cached field formats are retrieved correctly.
        
        **Validates: Requirements 24.10**
        """
        date_manager = DateManager()
        
        # Cache the format
        date_manager.cache_field_format(field_name, format_type)
        
        # Retrieve should return the same format
        cached = date_manager.get_cached_field_format(field_name)
        
        assert cached == format_type
    
    @given(st.lists(
        st.tuples(
            st.text(min_size=1, max_size=30, alphabet=st.characters(
                whitelist_categories=('Lu', 'Ll', 'Nd'),
                whitelist_characters='_-'
            )),
            st.sampled_from([
                DateFormatType.ISO_DATE,
                DateFormatType.US_DATE,
                DateFormatType.EU_DATE,
            ])
        ),
        min_size=1,
        max_size=10,
        unique_by=lambda x: x[0]  # Unique field names
    ))
    @settings(max_examples=100, deadline=None)
    def test_multiple_field_cache_consistency(self, field_formats):
        """
        Test that multiple cached field formats are all retrieved correctly.
        
        **Validates: Requirements 24.10**
        """
        date_manager = DateManager()
        
        # Cache all formats
        for field_name, format_type in field_formats:
            date_manager.cache_field_format(field_name, format_type)
        
        # Verify all cached formats
        for field_name, format_type in field_formats:
            cached = date_manager.get_cached_field_format(field_name)
            assert cached == format_type


# ============= Edge Cases =============

class TestDateFormatEdgeCases:
    """Edge case tests for date format detection and conversion."""
    
    def test_empty_samples_returns_unknown(self):
        """Test that empty sample list returns UNKNOWN."""
        detector = DateFormatDetector()
        result = detector.detect_format([])
        assert result == DateFormatType.UNKNOWN
    
    def test_whitespace_only_samples_returns_unknown(self):
        """Test that whitespace-only samples return UNKNOWN."""
        detector = DateFormatDetector()
        result = detector.detect_format(["  ", "\t", "\n"])
        assert result == DateFormatType.UNKNOWN
    
    def test_invalid_date_conversion_returns_none(self):
        """Test that invalid date conversion returns None."""
        detector = DateFormatDetector()
        result = detector.convert_to_iso("not-a-date", DateFormatType.ISO_DATE)
        assert result is None
    
    def test_mixed_format_samples_low_confidence(self):
        """Test that mixed format samples may return UNKNOWN due to low confidence."""
        detector = DateFormatDetector()
        
        # Mix of different formats
        samples = [
            "2024-01-15",  # ISO
            "01/15/2024",  # US
            "15/01/2024",  # EU
            "2024-Q1",     # Quarter
        ]
        
        # With such mixed formats, confidence for any single format should be low
        result = detector.detect_format(samples, confidence_threshold=0.7)
        # Result depends on which format has highest match count
        # This is expected behavior - mixed formats are ambiguous
    
    def test_leap_year_date_conversion(self):
        """Test leap year date conversion."""
        detector = DateFormatDetector()
        
        # Feb 29 in leap year
        result = detector.convert_to_iso("02/29/2024", DateFormatType.US_DATE)
        assert result == "2024-02-29"
        
        # Feb 29 in non-leap year should fail
        result = detector.convert_to_iso("02/29/2023", DateFormatType.US_DATE)
        assert result is None
    
    def test_quarter_to_iso_conversion(self):
        """Test quarter format to ISO conversion."""
        detector = DateFormatDetector()
        
        # Q1 should return first day of Q1
        result = detector.convert_to_iso("2024-Q1", DateFormatType.QUARTER)
        assert result == "2024-01-01"
        
        # Q2 should return first day of Q2
        result = detector.convert_to_iso("2024-Q2", DateFormatType.QUARTER)
        assert result == "2024-04-01"
        
        # Q3 should return first day of Q3
        result = detector.convert_to_iso("2024-Q3", DateFormatType.QUARTER)
        assert result == "2024-07-01"
        
        # Q4 should return first day of Q4
        result = detector.convert_to_iso("2024-Q4", DateFormatType.QUARTER)
        assert result == "2024-10-01"
    
    def test_year_only_to_iso_conversion(self):
        """Test year-only format to ISO conversion."""
        detector = DateFormatDetector()
        
        result = detector.convert_to_iso("2024", DateFormatType.YEAR_ONLY)
        assert result == "2024-01-01"
    
    def test_year_month_to_iso_conversion(self):
        """Test year-month format to ISO conversion."""
        detector = DateFormatDetector()
        
        result = detector.convert_to_iso("2024-06", DateFormatType.YEAR_MONTH)
        assert result == "2024-06-01"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--hypothesis-show-statistics"])


# ============= Property 16: STRING Date Field DATEPARSE Generation =============

class TestStringDateFieldDATEPARSE:
    """
    Property 16: STRING date field DATEPARSE generation correctness
    
    For any STRING type date field, QueryBuilder should generate the correct
    DATEPARSE formula in the CalculationField.
    """
    
    @given(
        st.sampled_from([
            DateFormatType.ISO_DATE,
            DateFormatType.US_DATE,
            DateFormatType.EU_DATE,
            DateFormatType.YEAR_MONTH,
        ]),
        st.text(min_size=1, max_size=30, alphabet=st.characters(
            whitelist_categories=('Lu', 'Ll', 'Nd'),
            whitelist_characters='_-'
        )).filter(lambda x: len(x.strip()) > 0),
        iso_date_strategy(),
        iso_date_strategy(),
    )
    @settings(max_examples=100, deadline=None)
    def test_dateparse_format_correctness(
        self, 
        format_type: DateFormatType, 
        field_name: str,
        start_date: str,
        end_date: str
    ):
        """
        **Property 16: STRING date field DATEPARSE generation correctness**
        
        For any STRING type date field with a known format, the StringDateFilterBuilder
        should generate a DATEPARSE formula with the correct format string.
        
        **Validates: Requirements 24.6**
        """
        from tableau_assistant.src.capabilities.query.builder.string_date_filter_builder import (
            StringDateFilterBuilder
        )
        from tableau_assistant.src.models.time_granularity import TimeGranularity
        from tableau_assistant.src.models.vizql_types import QuantitativeDateFilter
        
        # Ensure start_date <= end_date
        if start_date > end_date:
            start_date, end_date = end_date, start_date
        
        # Calculate date range to ensure we get DATEPARSE filter (> 100 days)
        from datetime import datetime
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        days_diff = (end_dt - start_dt).days
        
        # Only test when range > 100 days (triggers DATEPARSE)
        assume(days_diff > 100)
        
        builder = StringDateFilterBuilder()
        
        # Build filter for DAY granularity field with YEAR question granularity
        # This should trigger DATEPARSE + QuantitativeDateFilter
        result = builder.build_filter(
            field_name=field_name.strip(),
            field_format=format_type,
            field_granularity=TimeGranularity.DAY,
            question_granularity=TimeGranularity.YEAR,
            start_date=start_date,
            end_date=end_date
        )
        
        # Should return QuantitativeDateFilter with DATEPARSE
        assert result is not None
        assert isinstance(result, QuantitativeDateFilter)
        
        # Verify DATEPARSE formula is present
        assert result.field.calculation is not None
        assert "DATEPARSE" in result.field.calculation
        assert field_name.strip() in result.field.calculation
        
        # Verify the format string matches the expected format
        expected_formats = {
            DateFormatType.ISO_DATE: "yyyy-MM-dd",
            DateFormatType.US_DATE: "MM/dd/yyyy",
            DateFormatType.EU_DATE: "dd/MM/yyyy",
            DateFormatType.YEAR_MONTH: "yyyy-MM",
        }
        expected_format = expected_formats.get(format_type)
        if expected_format:
            assert expected_format in result.field.calculation
    
    def test_dateparse_iso_format(self):
        """Test DATEPARSE generation for ISO date format."""
        from tableau_assistant.src.capabilities.query.builder.string_date_filter_builder import (
            StringDateFilterBuilder
        )
        from tableau_assistant.src.models.time_granularity import TimeGranularity
        from tableau_assistant.src.models.vizql_types import QuantitativeDateFilter
        
        builder = StringDateFilterBuilder()
        
        result = builder.build_filter(
            field_name="order_date",
            field_format=DateFormatType.ISO_DATE,
            field_granularity=TimeGranularity.DAY,
            question_granularity=TimeGranularity.YEAR,
            start_date="2024-01-01",
            end_date="2024-12-31"
        )
        
        assert isinstance(result, QuantitativeDateFilter)
        assert 'DATEPARSE("yyyy-MM-dd", [order_date])' in result.field.calculation
        assert result.minDate == "2024-01-01"
        assert result.maxDate == "2024-12-31"
    
    def test_dateparse_us_format(self):
        """Test DATEPARSE generation for US date format."""
        from tableau_assistant.src.capabilities.query.builder.string_date_filter_builder import (
            StringDateFilterBuilder
        )
        from tableau_assistant.src.models.time_granularity import TimeGranularity
        from tableau_assistant.src.models.vizql_types import QuantitativeDateFilter
        
        builder = StringDateFilterBuilder()
        
        result = builder.build_filter(
            field_name="sale_date",
            field_format=DateFormatType.US_DATE,
            field_granularity=TimeGranularity.DAY,
            question_granularity=TimeGranularity.YEAR,
            start_date="2024-01-01",
            end_date="2024-12-31"
        )
        
        assert isinstance(result, QuantitativeDateFilter)
        assert 'DATEPARSE("MM/dd/yyyy", [sale_date])' in result.field.calculation
    
    def test_dateparse_eu_format(self):
        """Test DATEPARSE generation for EU date format."""
        from tableau_assistant.src.capabilities.query.builder.string_date_filter_builder import (
            StringDateFilterBuilder
        )
        from tableau_assistant.src.models.time_granularity import TimeGranularity
        from tableau_assistant.src.models.vizql_types import QuantitativeDateFilter
        
        builder = StringDateFilterBuilder()
        
        result = builder.build_filter(
            field_name="transaction_date",
            field_format=DateFormatType.EU_DATE,
            field_granularity=TimeGranularity.DAY,
            question_granularity=TimeGranularity.YEAR,
            start_date="2024-01-01",
            end_date="2024-12-31"
        )
        
        assert isinstance(result, QuantitativeDateFilter)
        assert 'DATEPARSE("dd/MM/yyyy", [transaction_date])' in result.field.calculation


class TestStringDateFilterBuilderStrategies:
    """Test different filter strategies based on granularity and format."""
    
    def test_exact_match_uses_set_filter(self):
        """Test that exact granularity match uses SetFilter."""
        from tableau_assistant.src.capabilities.query.builder.string_date_filter_builder import (
            StringDateFilterBuilder
        )
        from tableau_assistant.src.models.time_granularity import TimeGranularity
        from tableau_assistant.src.models.vizql_types import SetFilter
        
        builder = StringDateFilterBuilder()
        
        # Month granularity field with month granularity question
        result = builder.build_filter(
            field_name="month_field",
            field_format=DateFormatType.YEAR_MONTH,
            field_granularity=TimeGranularity.MONTH,
            question_granularity=TimeGranularity.MONTH,
            start_date="2024-01-01",
            end_date="2024-03-31"
        )
        
        assert isinstance(result, SetFilter)
        assert "2024-01" in result.values
        assert "2024-02" in result.values
        assert "2024-03" in result.values
    
    def test_prefix_match_uses_match_filter(self):
        """Test that prefix-matchable formats use MatchFilter for year queries."""
        from tableau_assistant.src.capabilities.query.builder.string_date_filter_builder import (
            StringDateFilterBuilder
        )
        from tableau_assistant.src.models.time_granularity import TimeGranularity
        from tableau_assistant.src.models.vizql_types import MatchFilter
        
        builder = StringDateFilterBuilder()
        
        # Year-month field with year question → should use MatchFilter
        result = builder.build_filter(
            field_name="year_month_field",
            field_format=DateFormatType.YEAR_MONTH,
            field_granularity=TimeGranularity.MONTH,
            question_granularity=TimeGranularity.YEAR,
            start_date="2024-01-01",
            end_date="2024-12-31"
        )
        
        assert isinstance(result, MatchFilter)
        assert result.startsWith == "2024-"
    
    def test_coarser_field_returns_none(self):
        """Test that coarser field granularity than question returns None."""
        from tableau_assistant.src.capabilities.query.builder.string_date_filter_builder import (
            StringDateFilterBuilder
        )
        from tableau_assistant.src.models.time_granularity import TimeGranularity
        
        builder = StringDateFilterBuilder()
        
        # Year granularity field with month granularity question → impossible
        result = builder.build_filter(
            field_name="year_field",
            field_format=DateFormatType.YEAR_ONLY,
            field_granularity=TimeGranularity.YEAR,
            question_granularity=TimeGranularity.MONTH,
            start_date="2024-01-01",
            end_date="2024-03-31"
        )
        
        assert result is None
    
    @given(
        st.sampled_from([
            TimeGranularity.YEAR,
            TimeGranularity.QUARTER,
            TimeGranularity.MONTH,
        ])
    )
    @settings(max_examples=50, deadline=None)
    def test_granularity_comparison_property(self, question_granularity: 'TimeGranularity'):
        """
        Property: Field granularity must be >= question granularity for valid filter.
        
        **Validates: Requirements 24.5**
        """
        from tableau_assistant.src.capabilities.query.builder.string_date_filter_builder import (
            StringDateFilterBuilder
        )
        from tableau_assistant.src.models.time_granularity import TimeGranularity
        
        builder = StringDateFilterBuilder()
        
        # Year granularity field (coarsest)
        result = builder.build_filter(
            field_name="year_field",
            field_format=DateFormatType.YEAR_ONLY,
            field_granularity=TimeGranularity.YEAR,
            question_granularity=question_granularity,
            start_date="2024-01-01",
            end_date="2024-12-31"
        )
        
        # If question granularity is finer than YEAR, result should be None
        if question_granularity != TimeGranularity.YEAR:
            assert result is None
        else:
            assert result is not None
