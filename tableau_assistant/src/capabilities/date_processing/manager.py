"""
Date Manager - Unified date functionality management.

Responsibilities:
1. Provide unified entry point for all date-related functions
2. Manage DateCalculator, DateParser, DateFormatDetector
3. Cache date format detection results
4. Coordinate between different date components

Design principles:
- Single responsibility: each component handles one aspect
- Dependency injection: components are injected and coordinated
- Caching: avoid redundant format detection
- Clean interfaces: simple, intuitive API
"""
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple, List
import logging

from tableau_assistant.src.capabilities.date_processing.calculator import DateCalculator
from tableau_assistant.src.capabilities.date_processing.parser import DateParser
from tableau_assistant.src.capabilities.date_processing.format_detector import DateFormatDetector, DateFormatType
from tableau_assistant.src.models.question import TimeRange

logger = logging.getLogger(__name__)


class DateManager:
    """
    Date Manager - Unified management of all date-related functionality.
    
    Responsibilities:
    1. Provide unified date functionality entry point
    2. Manage DateCalculator, DateParser, DateFormatDetector
    3. Cache date format detection results
    
    Architecture:
        DateManager (unified entry)
        ├── DateCalculator (date calculation)
        │   └── Relative date calculation (LASTN, LAST, CURRENT, NEXT, NEXTN)
        ├── DateParser (date parsing)
        │   └── TimeRange → specific date range
        └── DateFormatDetector (date format detection)
            └── STRING field date format detection and conversion
    
    Usage scenarios:
    - DataModelManager uses DateManager to detect STRING field date formats
    - QueryBuilder uses DateManager to parse date ranges and convert date formats
    - DateFilterConverter uses DateManager to build date filters
    
    Examples:
        >>> # Create DateManager
        >>> date_manager = DateManager(
        ...     anchor_date=datetime(2024, 12, 31),
        ...     week_start_day=0
        ... )
        
        >>> # Date calculation
        >>> result = date_manager.calculate_relative_date("LASTN", "MONTHS", 3)
        >>> print(result)
        {'start_date': '2024-10-01', 'end_date': '2024-12-31'}
        
        >>> # Date format detection
        >>> format_type = date_manager.detect_field_date_format(
        ...     ["01/15/2024", "02/20/2024"]
        ... )
        >>> print(format_type)
        DateFormatType.US_DATE
        
        >>> # Date conversion
        >>> iso_date = date_manager.convert_date_to_iso(
        ...     "01/15/2024", DateFormatType.US_DATE
        ... )
        >>> print(iso_date)
        "2024-01-15"
    """
    
    def __init__(
        self,
        anchor_date: Optional[datetime] = None,
        week_start_day: int = 0
    ):
        """
        Initialize date manager.
        
        Args:
            anchor_date: Anchor date (reference date), defaults to current date
            week_start_day: Week start day (0=Monday, 1=Tuesday, ..., 6=Sunday)
        """
        self.anchor_date = anchor_date or datetime.now()
        self.week_start_day = week_start_day
        
        # Initialize components
        self.calculator = DateCalculator(
            anchor_date=self.anchor_date,
            week_start_day=self.week_start_day
        )
        self.parser = DateParser(date_calculator=self.calculator)
        self.format_detector = DateFormatDetector()
        
        # Cache for field date formats
        self.field_formats_cache: Dict[str, DateFormatType] = {}
        
        logger.debug(
            f"DateManager initialized: "
            f"anchor_date={self.anchor_date.date()}, "
            f"week_start_day={self.week_start_day}"
        )
    
    # ============= Date Calculation Functions =============
    
    def calculate_relative_date(
        self,
        relative_type: str,
        period_type: str,
        range_n: Optional[int] = None
    ) -> Dict[str, str]:
        """
        Calculate relative date range (delegates to DateCalculator).
        
        Args:
            relative_type: Relative type (LASTN, LAST, CURRENT, NEXT, NEXTN)
            period_type: Period type (YEARS, QUARTERS, MONTHS, WEEKS, DAYS)
            range_n: Range quantity (required for LASTN and NEXTN)
        
        Returns:
            Dictionary containing start_date and end_date in "YYYY-MM-DD" format
        
        Examples:
            >>> date_manager.calculate_relative_date("LASTN", "MONTHS", 3)
            {'start_date': '2024-10-01', 'end_date': '2024-12-31'}
            
            >>> date_manager.calculate_relative_date("CURRENT", "YEAR")
            {'start_date': '2024-01-01', 'end_date': '2024-12-31'}
        """
        return self.calculator.calculate_relative_date(
            relative_type=relative_type,
            period_type=period_type,
            range_n=range_n
        )
    
    # ============= Date Parsing Functions =============
    
    def parse_time_range(
        self,
        time_range: TimeRange,
        reference_date: Optional[datetime] = None,
        max_date: Optional[str] = None
    ) -> Tuple[str, str]:
        """
        Parse TimeRange to specific date range (delegates to DateParser).
        
        Args:
            time_range: TimeRange object output by LLM
            reference_date: Reference date (for relative time calculation)
            max_date: Maximum date of data source (optional)
        
        Returns:
            (start_date, end_date) tuple in "YYYY-MM-DD" format
        
        Examples:
            >>> time_range = TimeRange(
            ...     type="relative",
            ...     relative_type="LASTN",
            ...     period_type="MONTHS",
            ...     range_n=3
            ... )
            >>> date_manager.parse_time_range(time_range)
            ("2024-10-01", "2024-12-31")
        """
        return self.parser.calculate_date_range(
            time_range=time_range,
            reference_date=reference_date,
            max_date=max_date
        )
    
    # ============= Date Format Detection Functions =============
    
    def detect_field_date_format(
        self,
        sample_values: List[str],
        confidence_threshold: float = 0.7
    ) -> DateFormatType:
        """
        Detect field date format (delegates to DateFormatDetector).
        
        Args:
            sample_values: List of sample date values
            confidence_threshold: Confidence threshold (default 0.7)
        
        Returns:
            Detected date format type
        
        Examples:
            >>> date_manager.detect_field_date_format(
            ...     ["01/15/2024", "02/20/2024"]
            ... )
            DateFormatType.US_DATE
            
            >>> date_manager.detect_field_date_format(
            ...     ["2024-01-15", "2024-02-20"]
            ... )
            DateFormatType.ISO_DATE
        """
        return self.format_detector.detect_format(
            sample_values=sample_values,
            confidence_threshold=confidence_threshold
        )
    
    def convert_date_to_iso(
        self,
        date_value: str,
        source_format: DateFormatType
    ) -> Optional[str]:
        """
        Convert date to ISO format (delegates to DateFormatDetector).
        
        Args:
            date_value: Original date value
            source_format: Source date format
        
        Returns:
            ISO format date string, or None if conversion fails
        
        Examples:
            >>> date_manager.convert_date_to_iso(
            ...     "01/15/2024", DateFormatType.US_DATE
            ... )
            "2024-01-15"
            
            >>> date_manager.convert_date_to_iso(
            ...     "15/01/2024", DateFormatType.EU_DATE
            ... )
            "2024-01-15"
        """
        return self.format_detector.convert_to_iso(
            date_value=date_value,
            source_format=source_format
        )
    
    def get_format_info(self, format_type: DateFormatType) -> Dict[str, str]:
        """
        Get format information (delegates to DateFormatDetector).
        
        Args:
            format_type: Date format type
        
        Returns:
            Dictionary containing format information (name, pattern, example, description)
        
        Examples:
            >>> info = date_manager.get_format_info(DateFormatType.US_DATE)
            >>> print(info["pattern"])
            "MM/DD/YYYY"
        """
        return self.format_detector.get_format_info(format_type)
    
    # ============= Cache Management =============
    
    def cache_field_format(self, field_name: str, format_type: DateFormatType) -> None:
        """
        Cache field date format.
        
        Args:
            field_name: Field name
            format_type: Date format type
        
        Examples:
            >>> date_manager.cache_field_format("order_date", DateFormatType.US_DATE)
        """
        self.field_formats_cache[field_name] = format_type
        logger.debug(f"Cached date format for field '{field_name}': {format_type.value}")
    
    def get_cached_field_format(self, field_name: str) -> Optional[DateFormatType]:
        """
        Get cached field date format.
        
        Args:
            field_name: Field name
        
        Returns:
            Cached date format type, or None if not cached
        
        Examples:
            >>> format_type = date_manager.get_cached_field_format("order_date")
            >>> if format_type:
            ...     print(f"Cached format: {format_type.value}")
        """
        return self.field_formats_cache.get(field_name)
    
    def clear_format_cache(self) -> None:
        """
        Clear all cached field formats.
        
        Examples:
            >>> date_manager.clear_format_cache()
        """
        cache_size = len(self.field_formats_cache)
        self.field_formats_cache.clear()
        logger.info(f"Cleared date format cache, removed {cache_size} entries")
    
    # ============= Utility Methods =============
    
    def get_anchor_date(self) -> datetime:
        """
        Get anchor date.
        
        Returns:
            Anchor date
        """
        return self.anchor_date
    
    def set_anchor_date(self, anchor_date: datetime) -> None:
        """
        Set anchor date.
        
        Args:
            anchor_date: New anchor date
        """
        self.anchor_date = anchor_date
        self.calculator.anchor_date = anchor_date
        logger.info(f"Updated anchor date to: {anchor_date.date()}")
    
    def get_week_start_day(self) -> int:
        """
        Get week start day.
        
        Returns:
            Week start day (0=Monday, 6=Sunday)
        """
        return self.week_start_day
    
    def get_cache_stats(self) -> Dict[str, any]:
        """
        Get cache statistics.
        
        Returns:
            Dictionary containing cache statistics
        """
        return {
            "format_cache_size": len(self.field_formats_cache),
            "cached_fields": list(self.field_formats_cache.keys()),
            "parser_cache_stats": self.parser.get_performance_stats()
        }


# ============= Exports =============

__all__ = [
    "DateManager",
]
