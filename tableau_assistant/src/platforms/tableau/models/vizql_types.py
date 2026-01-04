"""VizQL API types - Aligned with Tableau VizQL Data Service OpenAPI spec.

These types map directly to the VizQL API schema for query construction.
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class VizQLFunction(str, Enum):
    """VizQL aggregation functions (from OpenAPI spec)."""
    SUM = "SUM"
    AVG = "AVG"
    COUNT = "COUNT"
    COUNTD = "COUNTD"
    MIN = "MIN"
    MAX = "MAX"
    MEDIAN = "MEDIAN"
    STDEV = "STDEV"
    STDEVP = "STDEVP"
    VAR = "VAR"
    VARP = "VARP"
    ATTR = "ATTR"


class VizQLSortDirection(str, Enum):
    """VizQL sort direction."""
    ASC = "ASC"
    DESC = "DESC"


class VizQLDataType(str, Enum):
    """VizQL data types."""
    STRING = "STRING"
    INTEGER = "INTEGER"
    REAL = "REAL"
    BOOLEAN = "BOOLEAN"
    DATE = "DATE"
    DATETIME = "DATETIME"


class VizQLFieldRole(str, Enum):
    """VizQL field roles."""
    DIMENSION = "DIMENSION"
    MEASURE = "MEASURE"


class VizQLColumnClass(str, Enum):
    """VizQL column class."""
    COLUMN = "COLUMN"
    BIN = "BIN"
    GROUP = "GROUP"
    CALCULATION = "CALCULATION"
    TABLE_CALCULATION = "TABLE_CALCULATION"


# ═══════════════════════════════════════════════════════════════════════════
# VizQL Field Models (aligned with OpenAPI FieldBase)
# ═══════════════════════════════════════════════════════════════════════════

class VizQLFieldBase(BaseModel):
    """Base field properties (from OpenAPI FieldBase)."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    
    field_caption: str = Field(alias="fieldCaption")
    field_alias: str | None = Field(default=None, alias="fieldAlias")
    max_decimal_places: int | None = Field(default=None, alias="maxDecimalPlaces")
    sort_direction: VizQLSortDirection | None = Field(default=None, alias="sortDirection")
    sort_priority: int | None = Field(default=None, alias="sortPriority")


class VizQLDimensionField(VizQLFieldBase):
    """VizQL dimension field."""
    pass


class VizQLMeasureField(VizQLFieldBase):
    """VizQL measure field with aggregation function."""
    function: VizQLFunction


class VizQLCalculatedField(VizQLFieldBase):
    """VizQL calculated field."""
    calculation: str


# ═══════════════════════════════════════════════════════════════════════════
# VizQL Filter Types
# ═══════════════════════════════════════════════════════════════════════════

class VizQLFilterType(str, Enum):
    """VizQL filter types (from OpenAPI spec)."""
    SET = "SET"
    DATE = "DATE"
    QUANTITATIVE_DATE = "QUANTITATIVE_DATE"
    QUANTITATIVE_NUMERICAL = "QUANTITATIVE_NUMERICAL"
    MATCH = "MATCH"
    TOP = "TOP"


class VizQLFilterBase(BaseModel):
    """Base filter properties."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    
    field_caption: str = Field(alias="fieldCaption")
    filter_type: VizQLFilterType = Field(alias="filterType")


class VizQLSetFilter(VizQLFilterBase):
    """Set filter (categorical values)."""
    filter_type: VizQLFilterType = Field(default=VizQLFilterType.SET, alias="filterType")
    values: list[str]
    exclude: bool = False


class VizQLDateFilter(VizQLFilterBase):
    """Relative date filter."""
    filter_type: VizQLFilterType = Field(default=VizQLFilterType.DATE, alias="filterType")
    anchor: str | None = None  # CURRENT, PREVIOUS, NEXT
    period_type: str | None = Field(default=None, alias="periodType")  # YEAR, QUARTER, MONTH, etc.
    range_n: int | None = Field(default=None, alias="rangeN")


class VizQLQuantitativeDateFilter(VizQLFilterBase):
    """Absolute date range filter."""
    filter_type: VizQLFilterType = Field(default=VizQLFilterType.QUANTITATIVE_DATE, alias="filterType")
    min_value: str | None = Field(default=None, alias="minValue")  # ISO date string
    max_value: str | None = Field(default=None, alias="maxValue")
    include_null: bool = Field(default=False, alias="includeNull")


class VizQLQuantitativeNumericalFilter(VizQLFilterBase):
    """Numeric range filter."""
    filter_type: VizQLFilterType = Field(default=VizQLFilterType.QUANTITATIVE_NUMERICAL, alias="filterType")
    min_value: float | None = Field(default=None, alias="minValue")
    max_value: float | None = Field(default=None, alias="maxValue")
    include_null: bool = Field(default=False, alias="includeNull")


class VizQLMatchFilter(VizQLFilterBase):
    """Text match filter."""
    filter_type: VizQLFilterType = Field(default=VizQLFilterType.MATCH, alias="filterType")
    pattern: str
    match_type: str = Field(default="CONTAINS", alias="matchType")  # CONTAINS, STARTS_WITH, etc.


class VizQLTopFilter(VizQLFilterBase):
    """Top N filter."""
    filter_type: VizQLFilterType = Field(default=VizQLFilterType.TOP, alias="filterType")
    how_many: int = Field(alias="howMany")
    field_to_measure: str = Field(alias="fieldToMeasure")
    function: VizQLFunction = VizQLFunction.SUM
    direction: str = "TOP"  # TOP or BOTTOM


# ═══════════════════════════════════════════════════════════════════════════
# VizQL Query Request/Response
# ═══════════════════════════════════════════════════════════════════════════

class VizQLQueryRequest(BaseModel):
    """VizQL query request (from OpenAPI QueryRequest).
    
    Standalone model for VizQL API query construction.
    """
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    
    datasource: Dict[str, Any] = Field(description="Datasource identifier")
    fields: List[Dict[str, Any]] = Field(description="Fields to query")
    filters: Optional[List[Dict[str, Any]]] = Field(default=None, description="Filter conditions")
    sorts: Optional[List[Dict[str, Any]]] = Field(default=None, description="Sort specifications")
    row_limit: Optional[int] = Field(default=None, alias="rowLimit")
    
    def to_api_dict(self) -> Dict[str, Any]:
        """Convert to VizQL API request dictionary."""
        result = {
            "datasource": self.datasource,
            "fields": self.fields,
        }
        if self.filters:
            result["filters"] = self.filters
        if self.sorts:
            result["sorts"] = self.sorts
        if self.row_limit is not None:
            result["rowLimit"] = self.row_limit
        return result


class VizQLQueryResponse(BaseModel):
    """VizQL query response (from OpenAPI QueryOutput)."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    
    columns: List[Dict[str, Any]]
    data: List[List[Any]]
    row_count: int = Field(alias="rowCount")
