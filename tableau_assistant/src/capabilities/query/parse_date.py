"""
Parse Date Tool - 日期解析工具

封装 DateParser 组件为 LangChain 工具，用于将 TimeRange 转换为具体的日期范围。
"""
from datetime import datetime
from typing import Optional
from langchain_core.tools import tool

from tableau_assistant.src.capabilities.data_processing.date_parser import DateParser
from tableau_assistant.src.models.question import TimeRange


@tool
def parse_date(
    time_range_json: str,
    reference_date: Optional[str] = None,
    max_date: Optional[str] = None
) -> dict:
    """Parse a TimeRange object and calculate the specific date range.
    
    This tool converts a TimeRange (from LLM output) into concrete start_date and end_date.
    It handles both absolute dates (like "2024" or "2024-Q1") and relative dates 
    (like "last 3 months").
    
    Args:
        time_range_json: JSON string of TimeRange object with fields:
            - type: "absolute" or "relative"
            - For absolute: either (start_date, end_date) or value
            - For relative: relative_type, period_type, range_n
        reference_date: Reference date for relative calculations (YYYY-MM-DD format).
            If not provided, uses yesterday's date.
        max_date: Maximum date in the data source (YYYY-MM-DD format).
            If provided, end_date will be adjusted to not exceed this date.
    
    Returns:
        Dictionary with:
            - start_date: Start date in YYYY-MM-DD format
            - end_date: End date in YYYY-MM-DD format
            - adjusted: Whether the date range was adjusted due to max_date
    
    Examples:
        # Absolute date - year
        >>> parse_date('{"type": "absolute", "value": "2024"}')
        {"start_date": "2024-01-01", "end_date": "2024-12-31", "adjusted": false}
        
        # Absolute date - quarter
        >>> parse_date('{"type": "absolute", "value": "2024-Q1"}')
        {"start_date": "2024-01-01", "end_date": "2024-03-31", "adjusted": false}
        
        # Relative date
        >>> parse_date(
        ...     '{"type": "relative", "relative_type": "LASTN", '
        ...     '"period_type": "MONTHS", "range_n": 3}',
        ...     reference_date="2024-12-31"
        ... )
        {"start_date": "2024-10-01", "end_date": "2024-12-31", "adjusted": false}
    """
    import json
    
    # Parse TimeRange from JSON
    time_range_dict = json.loads(time_range_json)
    time_range = TimeRange(**time_range_dict)
    
    # Parse reference_date if provided
    ref_date = None
    if reference_date:
        ref_date = datetime.strptime(reference_date, "%Y-%m-%d")
    
    # Create DateParser
    parser = DateParser()
    
    # Calculate without max_date first to detect if adjustment will happen
    start_date_orig, end_date_orig = parser.calculate_date_range(
        time_range=time_range,
        reference_date=ref_date,
        max_date=None
    )
    
    # Calculate with max_date if provided
    if max_date:
        start_date, end_date = parser.calculate_date_range(
            time_range=time_range,
            reference_date=ref_date,
            max_date=max_date
        )
        adjusted = (end_date != end_date_orig)
    else:
        start_date = start_date_orig
        end_date = end_date_orig
        adjusted = False
    
    return {
        "start_date": start_date,
        "end_date": end_date,
        "adjusted": adjusted
    }


__all__ = ["parse_date"]
