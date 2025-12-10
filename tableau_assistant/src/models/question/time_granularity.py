"""
Time granularity enumeration for date filtering.

Defines the different levels of time granularity that can be used in queries.
"""
from enum import Enum


class TimeGranularity(str, Enum):
    """
    Time granularity levels.
    
    Used to specify the level of detail for date-based queries and filters.
    Ordered from coarsest to finest granularity.
    """
    YEAR = "YEAR"
    QUARTER = "QUARTER"
    MONTH = "MONTH"
    WEEK = "WEEK"
    DAY = "DAY"
    
    def __lt__(self, other):
        """Compare granularity levels (coarser < finer)."""
        if not isinstance(other, TimeGranularity):
            return NotImplemented
        
        order = [
            TimeGranularity.YEAR,
            TimeGranularity.QUARTER,
            TimeGranularity.MONTH,
            TimeGranularity.WEEK,
            TimeGranularity.DAY
        ]
        return order.index(self) < order.index(other)
    
    def __le__(self, other):
        """Compare granularity levels (coarser <= finer)."""
        return self == other or self < other
    
    def __gt__(self, other):
        """Compare granularity levels (finer > coarser)."""
        if not isinstance(other, TimeGranularity):
            return NotImplemented
        return not self <= other
    
    def __ge__(self, other):
        """Compare granularity levels (finer >= coarser)."""
        return self == other or self > other


def get_field_granularity_from_format(format_type) -> TimeGranularity:
    """
    Determine the time granularity of a date field based on its format.
    
    Args:
        format_type: DateFormatType enum value
    
    Returns:
        TimeGranularity enum value
    
    Examples:
        >>> get_field_granularity_from_format(DateFormatType.YEAR_ONLY)
        TimeGranularity.YEAR
        
        >>> get_field_granularity_from_format(DateFormatType.YEAR_MONTH)
        TimeGranularity.MONTH
        
        >>> get_field_granularity_from_format(DateFormatType.ISO_DATE)
        TimeGranularity.DAY
    """
    from tableau_assistant.src.capabilities.date_processing.format_detector import DateFormatType
    
    # Map format types to granularity
    format_to_granularity = {
        DateFormatType.YEAR_ONLY: TimeGranularity.YEAR,
        DateFormatType.QUARTER: TimeGranularity.QUARTER,
        DateFormatType.YEAR_MONTH: TimeGranularity.MONTH,
        DateFormatType.MONTH_YEAR: TimeGranularity.MONTH,
        DateFormatType.YEAR_WEEK: TimeGranularity.WEEK,
        # All complete date formats have DAY granularity
        DateFormatType.ISO_DATE: TimeGranularity.DAY,
        DateFormatType.US_DATE: TimeGranularity.DAY,
        DateFormatType.EU_DATE: TimeGranularity.DAY,
        DateFormatType.US_DATE_DASH: TimeGranularity.DAY,
        DateFormatType.EU_DATE_DASH: TimeGranularity.DAY,
        DateFormatType.LONG_DATE: TimeGranularity.DAY,
        DateFormatType.SHORT_MONTH: TimeGranularity.DAY,
        DateFormatType.TIMESTAMP: TimeGranularity.DAY,
        DateFormatType.EXCEL_DATE: TimeGranularity.DAY,
    }
    
    return format_to_granularity.get(format_type, TimeGranularity.DAY)
