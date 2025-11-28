"""
Date format detection and conversion module.

Responsibilities:
1. Detect date formats in data source fields
2. Convert various date formats to standard ISO format
3. Handle STRING type date fields
4. Support multiple regional and format conventions

Design principles:
- Automatic detection of common date formats
- Provide format conversion functions
- Handle edge cases and errors
- Support custom formats
"""
from datetime import datetime
from typing import Optional, List, Dict
import re
import logging
from enum import Enum

logger = logging.getLogger(__name__)


class DateFormatType(Enum):
    """Date format type enumeration.
    
    Supported formats:
    - ISO_DATE: International standard (YYYY-MM-DD)
    - US_DATE: American format (MM/DD/YYYY)
    - EU_DATE: European format (DD/MM/YYYY)
    - US_DATE_DASH: American with dashes (MM-DD-YYYY)
    - EU_DATE_DASH: European with dashes (DD-MM-YYYY)
    - YEAR_MONTH: Year and month (YYYY-MM)
    - MONTH_YEAR: Month and year (MM/YYYY)
    - QUARTER: Quarterly format (YYYY-QN)
    - YEAR_ONLY: Year only (YYYY)
    - LONG_DATE: Long month name (January 15, 2024)
    - SHORT_MONTH: Short month name (Jan 15, 2024)
    - TIMESTAMP: Timestamp with time (YYYY-MM-DD HH:MM:SS)
    - EXCEL_DATE: Excel format without leading zeros (M/D/YYYY)
    - UNKNOWN: Cannot determine format
    """
    ISO_DATE = "YYYY-MM-DD"
    US_DATE = "MM/DD/YYYY"
    EU_DATE = "DD/MM/YYYY"
    US_DATE_DASH = "MM-DD-YYYY"
    EU_DATE_DASH = "DD-MM-YYYY"
    YEAR_MONTH = "YYYY-MM"
    MONTH_YEAR = "MM/YYYY"
    QUARTER = "YYYY-QN"
    YEAR_WEEK = "YYYY-WNN"  # ISO week format: 2024-W01, 2024-W52
    YEAR_ONLY = "YYYY"
    LONG_DATE = "Month DD, YYYY"
    SHORT_MONTH = "MMM DD, YYYY"
    TIMESTAMP = "YYYY-MM-DD HH:MM:SS"
    EXCEL_DATE = "M/D/YYYY"
    UNKNOWN = "UNKNOWN"


class DateFormatDetector:
    """
    Date format detector.
    
    Automatically detects date formats in data and provides conversion functionality.
    
    Examples:
        >>> detector = DateFormatDetector()
        >>> format_type = detector.detect_format(["01/15/2024", "02/20/2024"])
        >>> print(format_type)
        DateFormatType.US_DATE
        
        >>> converted = detector.convert_to_iso("01/15/2024", DateFormatType.US_DATE)
        >>> print(converted)
        "2024-01-15"
    """
    
    def __init__(self):
        """Initialize date format detector."""
        self._format_patterns = self._build_format_patterns()
        logger.debug("DateFormatDetector initialized")
    
    def _build_format_patterns(self) -> Dict[DateFormatType, List[str]]:
        """Build date format patterns.
        
        Returns:
            Dictionary mapping format types to regex patterns
        """
        return {
            DateFormatType.ISO_DATE: [
                r'^\d{4}-\d{2}-\d{2}$',
                r'^\d{4}-\d{1,2}-\d{1,2}$'
            ],
            DateFormatType.US_DATE: [
                r'^\d{1,2}/\d{1,2}/\d{4}$',
                r'^\d{2}/\d{2}/\d{4}$'
            ],
            DateFormatType.EU_DATE: [
                r'^\d{1,2}/\d{1,2}/\d{4}$',
                r'^\d{2}/\d{2}/\d{4}$'
            ],
            DateFormatType.US_DATE_DASH: [
                r'^\d{1,2}-\d{1,2}-\d{4}$',
                r'^\d{2}-\d{2}-\d{4}$'
            ],
            DateFormatType.EU_DATE_DASH: [
                r'^\d{1,2}-\d{1,2}-\d{4}$',
                r'^\d{2}-\d{2}-\d{4}$'
            ],
            DateFormatType.YEAR_MONTH: [
                r'^\d{4}-\d{1,2}$'
            ],
            DateFormatType.MONTH_YEAR: [
                r'^\d{1,2}/\d{4}$'
            ],
            DateFormatType.QUARTER: [
                r'^\d{4}-Q[1-4]$'
            ],
            DateFormatType.YEAR_ONLY: [
                r'^\d{4}$'
            ],
            DateFormatType.LONG_DATE: [
                r'^[A-Za-z]+ \d{1,2}, \d{4}$'
            ],
            DateFormatType.SHORT_MONTH: [
                r'^[A-Za-z]{3} \d{1,2}, \d{4}$'
            ],
            DateFormatType.TIMESTAMP: [
                r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$',
                r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}'
            ]
        }
    
    def detect_format(
        self, 
        sample_values: List[str], 
        confidence_threshold: float = 0.7
    ) -> DateFormatType:
        """
        Detect date format.
        
        Args:
            sample_values: List of sample date values
            confidence_threshold: Confidence threshold (default 0.7)
        
        Returns:
            Detected date format type
        
        Examples:
            >>> detector.detect_format(["2024-01-15", "2024-02-20"])
            DateFormatType.ISO_DATE
            
            >>> detector.detect_format(["01/15/2024", "02/20/2024"])
            DateFormatType.US_DATE
        """
        if not sample_values:
            return DateFormatType.UNKNOWN
        
        # Clean sample values
        cleaned_samples = [str(val).strip() for val in sample_values if val]
        if not cleaned_samples:
            return DateFormatType.UNKNOWN
        
        logger.info(f"Starting date format detection, sample count: {len(cleaned_samples)}")
        
        # Count matches for each format
        format_scores = {}
        
        for format_type, patterns in self._format_patterns.items():
            matches = 0
            for sample in cleaned_samples:
                if self._matches_any_pattern(sample, patterns):
                    matches += 1
            
            confidence = matches / len(cleaned_samples)
            format_scores[format_type] = confidence
            
            logger.debug(
                f"Format {format_type.value}: {matches}/{len(cleaned_samples)} matches, "
                f"confidence: {confidence:.2f}"
            )
        
        # Find format with highest confidence
        best_format = max(format_scores.keys(), key=lambda k: format_scores[k])
        best_confidence = format_scores[best_format]
        
        # Check if confidence meets threshold
        if best_confidence < confidence_threshold:
            logger.warning(
                f"✗ Cannot determine date format, highest confidence: "
                f"{best_confidence:.2f} < {confidence_threshold}"
            )
            return DateFormatType.UNKNOWN
        
        # Special handling: US and EU formats use same regex patterns
        # Always disambiguate if detected format is US or EU
        if best_format in [DateFormatType.US_DATE, DateFormatType.EU_DATE]:
            return self._disambiguate_us_eu_format(cleaned_samples)
        
        # For other formats, return directly
        logger.info(
            f"✓ Detected date format: {best_format.value}, "
            f"confidence: {best_confidence:.2f}"
        )
        return best_format
    
    def _matches_any_pattern(self, value: str, patterns: List[str]) -> bool:
        """Check if value matches any pattern.
        
        Args:
            value: Value to check
            patterns: List of regex patterns
        
        Returns:
            True if value matches any pattern
        """
        for pattern in patterns:
            if re.match(pattern, value):
                return True
        return False
    
    def _disambiguate_us_eu_format(self, samples: List[str]) -> DateFormatType:
        """
        Disambiguate US and EU date formats.
        
        Strategy:
        1. Look for obvious distinguishing markers (e.g., month > 12)
        2. Analyze date range reasonableness
        3. Default to US format
        
        Args:
            samples: List of sample date values
        
        Returns:
            DateFormatType.US_DATE or DateFormatType.EU_DATE
        """
        logger.info("Attempting to disambiguate US vs EU date format")
        
        us_indicators = 0
        eu_indicators = 0
        
        for sample in samples:
            # Match MM/DD/YYYY or DD/MM/YYYY format
            match = re.match(r'^(\d{1,2})/(\d{1,2})/(\d{4})$', sample)
            if match:
                first_num = int(match.group(1))
                second_num = int(match.group(2))
                
                # If first number > 12, it's EU format (DD/MM/YYYY)
                if first_num > 12:
                    eu_indicators += 1
                # If second number > 12, it's US format (MM/DD/YYYY)
                elif second_num > 12:
                    us_indicators += 1
        
        if eu_indicators > us_indicators:
            logger.info(
                f"✓ Detected as EU format, EU indicators: {eu_indicators}, "
                f"US indicators: {us_indicators}"
            )
            return DateFormatType.EU_DATE
        else:
            logger.info(
                f"✓ Detected as US format, US indicators: {us_indicators}, "
                f"EU indicators: {eu_indicators}"
            )
            return DateFormatType.US_DATE
    
    def convert_to_iso(
        self, 
        date_value: str, 
        source_format: DateFormatType
    ) -> Optional[str]:
        """
        Convert date to ISO format (YYYY-MM-DD).
        
        Args:
            date_value: Original date value
            source_format: Source date format
        
        Returns:
            ISO format date string, or None if conversion fails
        
        Examples:
            >>> detector.convert_to_iso("01/15/2024", DateFormatType.US_DATE)
            "2024-01-15"
            
            >>> detector.convert_to_iso("15/01/2024", DateFormatType.EU_DATE)
            "2024-01-15"
        """
        try:
            if not date_value or not date_value.strip():
                return None
            
            cleaned_value = date_value.strip()
            
            # Convert based on format type
            if source_format == DateFormatType.ISO_DATE:
                # Already ISO format, validate and standardize
                return self._standardize_iso_date(cleaned_value)
            
            elif source_format == DateFormatType.US_DATE:
                return self._convert_us_date(cleaned_value)
            
            elif source_format == DateFormatType.EU_DATE:
                return self._convert_eu_date(cleaned_value)
            
            elif source_format == DateFormatType.US_DATE_DASH:
                return self._convert_us_date_dash(cleaned_value)
            
            elif source_format == DateFormatType.EU_DATE_DASH:
                return self._convert_eu_date_dash(cleaned_value)
            
            elif source_format == DateFormatType.YEAR_MONTH:
                return self._convert_year_month(cleaned_value)
            
            elif source_format == DateFormatType.QUARTER:
                return self._convert_quarter(cleaned_value)
            
            elif source_format == DateFormatType.YEAR_ONLY:
                return self._convert_year_only(cleaned_value)
            
            elif source_format == DateFormatType.TIMESTAMP:
                return self._convert_timestamp(cleaned_value)
            
            else:
                logger.warning(f"Unsupported date format conversion: {source_format}")
                return None
        
        except Exception as e:
            logger.error(f"Date conversion failed: {date_value} ({source_format}) - {e}")
            return None
    
    def _standardize_iso_date(self, value: str) -> Optional[str]:
        """Standardize ISO date format.
        
        Args:
            value: Date value in ISO format
        
        Returns:
            Standardized ISO date string
        """
        try:
            # Parse and reformat to ensure standard format
            dt = datetime.strptime(value, "%Y-%m-%d")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            # Try other ISO variants
            for fmt in ["%Y-%m-%d", "%Y-%m-%d"]:
                try:
                    dt = datetime.strptime(value, fmt)
                    return dt.strftime("%Y-%m-%d")
                except ValueError:
                    continue
            return None
    
    def _convert_us_date(self, value: str) -> Optional[str]:
        """Convert US date format MM/DD/YYYY.
        
        Args:
            value: Date value in US format
        
        Returns:
            ISO format date string
        """
        try:
            dt = datetime.strptime(value, "%m/%d/%Y")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            # Try format without leading zeros
            try:
                dt = datetime.strptime(value, "%m/%d/%Y")
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                return None
    
    def _convert_eu_date(self, value: str) -> Optional[str]:
        """Convert EU date format DD/MM/YYYY.
        
        Args:
            value: Date value in EU format
        
        Returns:
            ISO format date string
        """
        try:
            dt = datetime.strptime(value, "%d/%m/%Y")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            return None
    
    def _convert_us_date_dash(self, value: str) -> Optional[str]:
        """Convert US date format MM-DD-YYYY.
        
        Args:
            value: Date value in US format with dashes
        
        Returns:
            ISO format date string
        """
        try:
            dt = datetime.strptime(value, "%m-%d-%Y")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            return None
    
    def _convert_eu_date_dash(self, value: str) -> Optional[str]:
        """Convert EU date format DD-MM-YYYY.
        
        Args:
            value: Date value in EU format with dashes
        
        Returns:
            ISO format date string
        """
        try:
            dt = datetime.strptime(value, "%d-%m-%Y")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            return None
    
    def _convert_year_month(self, value: str) -> Optional[str]:
        """Convert year-month format YYYY-MM, returns first day of month.
        
        Args:
            value: Date value in year-month format
        
        Returns:
            ISO format date string (first day of month)
        """
        try:
            dt = datetime.strptime(value, "%Y-%m")
            return dt.strftime("%Y-%m-01")
        except ValueError:
            return None
    
    def _convert_quarter(self, value: str) -> Optional[str]:
        """Convert quarter format YYYY-QN, returns first day of quarter.
        
        Args:
            value: Date value in quarter format
        
        Returns:
            ISO format date string (first day of quarter)
        """
        try:
            match = re.match(r'^(\d{4})-Q([1-4])$', value)
            if match:
                year = int(match.group(1))
                quarter = int(match.group(2))
                month = (quarter - 1) * 3 + 1
                return f"{year}-{month:02d}-01"
            return None
        except Exception:
            return None
    
    def _convert_year_only(self, value: str) -> Optional[str]:
        """Convert year format YYYY, returns first day of year.
        
        Args:
            value: Date value in year format
        
        Returns:
            ISO format date string (first day of year)
        """
        try:
            year = int(value)
            return f"{year}-01-01"
        except ValueError:
            return None
    
    def _convert_timestamp(self, value: str) -> Optional[str]:
        """Convert timestamp format, extracts date part.
        
        Args:
            value: Date value in timestamp format
        
        Returns:
            ISO format date string (date part only)
        """
        try:
            # Try multiple timestamp formats
            for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"]:
                try:
                    dt = datetime.strptime(value, fmt)
                    return dt.strftime("%Y-%m-%d")
                except ValueError:
                    continue
            return None
        except Exception:
            return None
    
    def get_format_info(self, format_type: DateFormatType) -> Dict[str, str]:
        """
        Get format information.
        
        Args:
            format_type: Date format type
        
        Returns:
            Dictionary containing format information
        """
        format_info = {
            DateFormatType.ISO_DATE: {
                "name": "ISO Date",
                "pattern": "YYYY-MM-DD",
                "example": "2024-01-15",
                "description": "International standard date format"
            },
            DateFormatType.US_DATE: {
                "name": "US Date",
                "pattern": "MM/DD/YYYY",
                "example": "01/15/2024",
                "description": "American date format"
            },
            DateFormatType.EU_DATE: {
                "name": "European Date",
                "pattern": "DD/MM/YYYY",
                "example": "15/01/2024",
                "description": "European date format"
            },
            DateFormatType.QUARTER: {
                "name": "Quarter",
                "pattern": "YYYY-QN",
                "example": "2024-Q1",
                "description": "Quarterly format"
            },
            DateFormatType.YEAR_ONLY: {
                "name": "Year Only",
                "pattern": "YYYY",
                "example": "2024",
                "description": "Year only"
            }
        }
        
        return format_info.get(format_type, {
            "name": "Unknown",
            "pattern": "Unknown",
            "example": "Unknown",
            "description": "Unknown format"
        })


# ============= Exports =============

__all__ = [
    "DateFormatType",
    "DateFormatDetector",
]
