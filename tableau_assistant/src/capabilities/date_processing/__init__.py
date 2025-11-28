"""
Date processing capability.

Unified date functionality management including:
- Date calculation (relative dates, periods)
- Date parsing (TimeRange to date range)
- Date format detection (STRING field date formats)
- Date management (unified interface)

This is an independent capability module focused solely on date-related operations.
"""

from tableau_assistant.src.capabilities.date_processing.manager import DateManager
from tableau_assistant.src.capabilities.date_processing.calculator import DateCalculator
from tableau_assistant.src.capabilities.date_processing.parser import DateParser
from tableau_assistant.src.capabilities.date_processing.format_detector import (
    DateFormatDetector,
    DateFormatType
)

__all__ = [
    "DateManager",
    "DateCalculator",
    "DateParser",
    "DateFormatDetector",
    "DateFormatType",
]
