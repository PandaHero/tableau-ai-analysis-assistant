"""
VizQL Type Definitions v2.0 (Redesigned)

Based on:
1. tableau_sdk TypeScript type definitions (sdks/tableau/apis/vizqlDataServiceApi.ts)
2. Pydantic 2.x best practices
3. LangChain 1.0 compatibility

Improvements:
- Use Pydantic v2 Field and ConfigDict
- Use Annotated types for better validation
- Use discriminated unions for better performance
- Add examples and docstrings
"""
from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import Literal, Union, Optional, List, Annotated
from enum import Enum


# ============= Enums =============

class FunctionEnum(str, Enum):
    """
    VizQL Function Enum
    
    Corresponds to tableau_sdk Function type
    Reference: sdks/tableau/apis/vizqlDataServiceApi.ts
    """
    # Aggregation functions
    SUM = "SUM"
    AVG = "AVG"
    MEDIAN = "MEDIAN"
    COUNT = "COUNT"
    COUNTD = "COUNTD"
    MIN = "MIN"
    MAX = "MAX"
    STDEV = "STDEV"
    VAR = "VAR"
    COLLECT = "COLLECT"
    
    # Date functions
    YEAR = "YEAR"
    QUARTER = "QUARTER"
    MONTH = "MONTH"
    WEEK = "WEEK"
    DAY = "DAY"
    
    # Date truncation functions
    TRUNC_YEAR = "TRUNC_YEAR"
    TRUNC_QUARTER = "TRUNC_QUARTER"
    TRUNC_MONTH = "TRUNC_MONTH"
    TRUNC_WEEK = "TRUNC_WEEK"
    TRUNC_DAY = "TRUNC_DAY"
    
    # Other
    AGG = "AGG"
    NONE = "NONE"
    UNSPECIFIED = "UNSPECIFIED"


class SortDirection(str, Enum):
    """Sort direction"""
    ASC = "ASC"
    DESC = "DESC"


class ReturnFormat(str, Enum):
    """Return format"""
    OBJECTS = "OBJECTS"
    ARRAYS = "ARRAYS"


class DataType(str, Enum):
    """Data type"""
    INTEGER = "INTEGER"
    REAL = "REAL"
    STRING = "STRING"
    DATETIME = "DATETIME"
    BOOLEAN = "BOOLEAN"
    DATE = "DATE"
    SPATIAL = "SPATIAL"
    UNKNOWN = "UNKNOWN"


# ============= Field Types =============

class FieldBase(BaseModel):
    """
    Base field type
    
    Corresponds to tableau_sdk FieldBase
    """
    model_config = ConfigDict(
        frozen=False,  # Allow modification (for query building)
        extra="forbid",  # Forbid extra fields
        str_strip_whitespace=True,  # Auto strip whitespace
    )
    
    fieldCaption: Annotated[str, Field(
        min_length=1,
        description="Field caption (must match field name in metadata exactly)",
        examples=["Sales", "Order Date", "Category"]
    )]
    
    fieldAlias: Optional[Annotated[str, Field(
        min_length=1,
        description="Field alias (optional)"
    )]] = None
    
    maxDecimalPlaces: Optional[Annotated[int, Field(
        ge=0,
        le=10,
        description="Maximum decimal places (0-10)"
    )]] = None
    
    sortDirection: Optional[SortDirection] = None
    sortPriority: Optional[Annotated[int, Field(ge=0)]] = None


class BasicField(FieldBase):
    """
    Basic field (no function, no calculation)
    
    Used for:
    - Direct reference to dimension fields: Category, Region, Product Name
    - Fields that don't need aggregation or transformation
    
    Examples:
        BasicField(fieldCaption="Category")
        BasicField(fieldCaption="Region", sortDirection=SortDirection.ASC)
    """
    pass


class FunctionField(FieldBase):
    """
    Function field (with aggregation or date function)
    
    Key understanding: Any field can have a function applied, not just measure fields!
    
    Used for:
    - Measure field aggregation: SUM(Sales), AVG(Profit)
    - Dimension field aggregation: COUNTD(Product Name) - count distinct products
    - Date field transformation: YEAR(Order Date), MONTH(Ship Date)
    
    Examples:
        FunctionField(fieldCaption="Sales", function=FunctionEnum.SUM)
        FunctionField(fieldCaption="Product Name", function=FunctionEnum.COUNTD)
        FunctionField(fieldCaption="Order Date", function=FunctionEnum.YEAR)
    """
    function: Annotated[FunctionEnum, Field(
        description="Aggregation or date function (can be applied to any field)"
    )]


class CalculationField(FieldBase):
    """
    Calculation field (custom formula)
    
    Used for:
    - Calculations based on other fields: [Profit] / [Sales]
    - Complex business logic: [Sales] * [Discount]
    
    Note: Calculation fields cannot have a function at the same time (they are mutually exclusive)
    
    Examples:
        CalculationField(
            fieldCaption="Profit Ratio",
            calculation="[Profit] / [Sales]"
        )
        CalculationField(
            fieldCaption="Profit",
            calculation="[Revenue] - [Cost]"
        )
    """
    calculation: Annotated[str, Field(
        min_length=1,
        description="Calculation formula (use [field_name] to reference other fields)"
    )]


# Discriminated Union - three types are mutually exclusive
# According to Tableau SDK definition: either no function/calculation, or has function, or has calculation
VizQLField = Annotated[
    Union[BasicField, FunctionField, CalculationField],
    Field(discriminator=None)
]


# ============= Filter Types =============

class FilterField(BaseModel):
    """
    Field reference in Filter
    
    Supports three forms (according to SDK definition):
    1. Only fieldCaption: FilterField(fieldCaption="Sales")
    2. fieldCaption + function: FilterField(fieldCaption="Sales", function="SUM")
    3. Only calculation: FilterField(calculation="DATEPARSE('yyyy-MM-dd', [Date])")
    
    Note: Automatically excludes None values during serialization, complying with SDK strict mode requirements
    """
    model_config = ConfigDict(
        extra="forbid",
        # Exclude None values during serialization
        exclude_none=True
    )
    
    fieldCaption: Optional[Annotated[str, Field(
        min_length=1,
        description="Field caption"
    )]] = None
    function: Optional[FunctionEnum] = None
    calculation: Optional[Annotated[str, Field(
        min_length=1,
        description="Calculation formula"
    )]] = None
    
    @field_validator("fieldCaption", "calculation")
    @classmethod
    def at_least_one_identifier(cls, v, info):
        """At least one of fieldCaption or calculation is required"""
        if v is None:
            values = info.data
            if not values.get("fieldCaption") and not values.get("calculation"):
                raise ValueError("At least one of fieldCaption or calculation must be specified")
        return v


class SetFilter(BaseModel):
    """
    Set filter
    
    Example:
        SetFilter(
            field=FilterField(fieldCaption="Category"),
            filterType="SET",
            values=["Furniture", "Technology"]
        )
    """
    model_config = ConfigDict(extra="forbid")
    
    field: FilterField
    filterType: Literal["SET"]
    values: Annotated[
        Union[List[str], List[int], List[bool]],
        Field(min_length=1, description="List of filter values")
    ]
    exclude: bool = False
    context: Optional[bool] = None


class TopNFilter(BaseModel):
    """
    TopN filter
    
    Example:
        TopNFilter(
            field=FilterField(fieldCaption="Category"),
            filterType="TOP",
            howMany=10,
            fieldToMeasure=FilterField(fieldCaption="Sales"),
            direction="TOP"
        )
    """
    model_config = ConfigDict(extra="forbid")
    
    field: FilterField
    filterType: Literal["TOP"]
    howMany: Annotated[int, Field(ge=1, le=1000, description="Number of top N items (1-1000)")]
    fieldToMeasure: FilterField
    direction: Literal["TOP", "BOTTOM"] = "TOP"
    context: Optional[bool] = None


class MatchFilter(BaseModel):
    """
    Text match filter
    
    Example:
        MatchFilter(
            field=FilterField(fieldCaption="Product Name"),
            filterType="MATCH",
            contains="Chair"
        )
    """
    model_config = ConfigDict(extra="forbid")
    
    field: FilterField
    filterType: Literal["MATCH"]
    startsWith: Optional[str] = None
    endsWith: Optional[str] = None
    contains: Optional[str] = None
    exclude: bool = False
    context: Optional[bool] = None
    
    @field_validator("startsWith", "endsWith", "contains")
    @classmethod
    def at_least_one_match_type(cls, v, info):
        """At least one match type is required"""
        if v is None:
            values = info.data
            if not any([values.get("startsWith"), values.get("endsWith"), values.get("contains")]):
                raise ValueError("At least one of startsWith, endsWith, or contains must be specified")
        return v


class QuantitativeNumericalFilter(BaseModel):
    """
    Numerical range filter
    
    Example:
        QuantitativeNumericalFilter(
            field=FilterField(fieldCaption="Sales"),
            filterType="QUANTITATIVE_NUMERICAL",
            quantitativeFilterType="RANGE",
            min=1000,
            max=5000
        )
    """
    model_config = ConfigDict(extra="forbid")
    
    field: FilterField
    filterType: Literal["QUANTITATIVE_NUMERICAL"]
    quantitativeFilterType: Literal["RANGE", "MIN", "MAX", "ONLY_NULL", "ONLY_NON_NULL"]
    min: Optional[float] = None
    max: Optional[float] = None
    includeNulls: Optional[bool] = None
    context: Optional[bool] = None


class QuantitativeDateFilter(BaseModel):
    """
    Date range filter
    
    Example:
        QuantitativeDateFilter(
            field=FilterField(fieldCaption="Order Date"),
            filterType="QUANTITATIVE_DATE",
            quantitativeFilterType="RANGE",
            minDate="2016-01-01",
            maxDate="2016-12-31"
        )
    """
    model_config = ConfigDict(extra="forbid")
    
    field: FilterField
    filterType: Literal["QUANTITATIVE_DATE"]
    quantitativeFilterType: Literal["RANGE", "MIN", "MAX", "ONLY_NULL", "ONLY_NON_NULL"]
    minDate: Optional[str] = None
    maxDate: Optional[str] = None
    includeNulls: Optional[bool] = None
    context: Optional[bool] = None


class RelativeDateFilter(BaseModel):
    """
    Relative date filter
    
    Example:
        RelativeDateFilter(
            field=FilterField(fieldCaption="Order Date"),
            filterType="DATE",
            dateRangeType="LASTN",
            periodType="MONTHS",
            rangeN=3
        )
    """
    model_config = ConfigDict(extra="forbid")
    
    field: FilterField
    filterType: Literal["DATE"]
    dateRangeType: Literal["CURRENT", "LAST", "NEXT", "TODATE", "LASTN", "NEXTN"]
    periodType: Literal["MINUTES", "HOURS", "DAYS", "WEEKS", "MONTHS", "QUARTERS", "YEARS"]
    rangeN: Optional[Annotated[int, Field(gt=0)]] = None
    anchorDate: Optional[str] = None
    includeNulls: Optional[bool] = None
    context: Optional[bool] = None


# Discriminated Union for Filters
VizQLFilter = Annotated[
    Union[
        SetFilter,
        TopNFilter,
        MatchFilter,
        QuantitativeNumericalFilter,
        QuantitativeDateFilter,
        RelativeDateFilter,
    ],
    Field(discriminator="filterType")  # Use filterType as discriminator
]


# ============= Query Structure =============

class VizQLQuery(BaseModel):
    """
    VizQL query structure
    
    Corresponds to tableau_sdk Query type
    
    Example:
        VizQLQuery(
            fields=[
                BasicField(fieldCaption="Category"),
                FunctionField(fieldCaption="Sales", function=FunctionEnum.SUM)
            ],
            filters=[
                SetFilter(
                    field=FilterField(fieldCaption="Region"),
                    filterType="SET",
                    values=["East", "West"]
                )
            ]
        )
    """
    model_config = ConfigDict(extra="forbid")
    
    fields: Annotated[
        List[VizQLField],
        Field(min_length=1, description="List of fields (at least 1)")
    ]
    
    filters: Optional[List[VizQLFilter]] = None


class Connection(BaseModel):
    """Datasource connection"""
    model_config = ConfigDict(extra="forbid")
    
    connectionLuid: Optional[str] = None
    connectionUsername: str
    connectionPassword: str


class Datasource(BaseModel):
    """Datasource"""
    model_config = ConfigDict(extra="forbid")
    
    datasourceLuid: Annotated[str, Field(
        min_length=1,
        description="Datasource LUID"
    )]
    connections: Optional[List[Connection]] = None


class QueryOptions(BaseModel):
    """Query options"""
    model_config = ConfigDict(extra="allow")  # Allow extra fields (backward compatibility)
    
    returnFormat: ReturnFormat = ReturnFormat.OBJECTS
    debug: bool = False
    disaggregate: Optional[bool] = None


class QueryRequest(BaseModel):
    """
    VizQL query request
    
    Corresponds to tableau_sdk QueryRequest type
    """
    model_config = ConfigDict(extra="allow")
    
    datasource: Datasource
    query: VizQLQuery
    options: Optional[QueryOptions] = None


class QueryOutput(BaseModel):
    """Query output"""
    model_config = ConfigDict(extra="allow")
    
    data: List[dict]


# ============= Metadata Types =============

class FieldMetadata(BaseModel):
    """Field metadata"""
    model_config = ConfigDict(extra="allow")
    
    fieldName: str
    fieldCaption: str
    dataType: DataType
    defaultAggregation: FunctionEnum
    logicalTableId: Optional[str] = None
    role: Optional[Literal["dimension", "measure"]] = None
    description: Optional[str] = None


class MetadataOutput(BaseModel):
    """Metadata output"""
    model_config = ConfigDict(extra="allow")
    
    data: List[FieldMetadata]


# ============= Helper Functions =============

def create_basic_field(field_caption: str, **kwargs) -> BasicField:
    """Helper function to create basic field"""
    return BasicField(fieldCaption=field_caption, **kwargs)


def create_function_field(
    field_caption: str,
    function: FunctionEnum,
    **kwargs
) -> FunctionField:
    """Helper function to create function field"""
    return FunctionField(
        fieldCaption=field_caption,
        function=function,
        **kwargs
    )


def create_set_filter(
    field_caption: str,
    values: Union[List[str], List[int], List[bool]],
    exclude: bool = False
) -> SetFilter:
    """Helper function to create set filter"""
    return SetFilter(
        field=FilterField(fieldCaption=field_caption),
        filterType="SET",
        values=values,
        exclude=exclude
    )


def create_relative_date_filter(
    field_caption: str,
    date_range_type: Literal["CURRENT", "LAST", "NEXT", "TODATE", "LASTN", "NEXTN"],
    period_type: Literal["MINUTES", "HOURS", "DAYS", "WEEKS", "MONTHS", "QUARTERS", "YEARS"],
    range_n: Optional[int] = None
) -> RelativeDateFilter:
    """Helper function to create relative date filter"""
    return RelativeDateFilter(
        field=FilterField(fieldCaption=field_caption),
        filterType="DATE",
        dateRangeType=date_range_type,
        periodType=period_type,
        rangeN=range_n
    )


def create_dateparse_field(
    field_caption: str,
    date_format: str = "yyyy-MM-dd",
    alias: Optional[str] = None
) -> CalculationField:
    """
    Helper function to create DATEPARSE calculation field
    
    Used to convert STRING type date fields to DATE type
    
    Args:
        field_caption: Original field name (STRING type)
        date_format: Date format (default 'yyyy-MM-dd')
        alias: Calculation field alias (default 'DATEPARSE_{field_caption}')
    
    Returns:
        CalculationField object
    
    Examples:
        >>> # Create DATEPARSE field
        >>> dateparse_field = create_dateparse_field("Date String")
        >>> # Generates: DATEPARSE('yyyy-MM-dd', [Date String])
        
        >>> # Custom date format
        >>> dateparse_field = create_dateparse_field(
        ...     "Date String",
        ...     date_format="yyyy/MM/dd"
        ... )
    
    Note:
        - Common date formats:
          * 'yyyy-MM-dd': 2024-03-15
          * 'yyyy/MM/dd': 2024/03/15
          * 'dd/MM/yyyy': 15/03/2024
          * 'MM/dd/yyyy': 03/15/2024
        - DATEPARSE field needs to be added to query.fields
        - Filters should reference the DATEPARSE field name, not the original field name
    """
    if alias is None:
        alias = f"DATEPARSE_{field_caption}"
    
    return CalculationField(
        fieldCaption=alias,
        calculation=f"DATEPARSE('{date_format}', [{field_caption}])"
    )


# ============= Example Usage =============

if __name__ == "__main__":
    # Example 1: Create simple query
    query = VizQLQuery(
        fields=[
            create_basic_field("Category"),
            create_function_field("Sales", FunctionEnum.SUM)
        ],
        filters=[
            create_set_filter("Region", ["East", "West"])
        ]
    )
    
    print("Example 1 - Simple query:")
    print(query.model_dump_json(indent=2))
    
    # Example 2: Create complex query
    complex_query = VizQLQuery(
        fields=[
            BasicField(
                fieldCaption="Order Date",
                sortDirection=SortDirection.ASC,
                sortPriority=1
            ),
            FunctionField(
                fieldCaption="Sales",
                function=FunctionEnum.SUM,
                maxDecimalPlaces=2
            ),
            FunctionField(
                fieldCaption="Profit",
                function=FunctionEnum.SUM,
                maxDecimalPlaces=2
            )
        ],
        filters=[
            create_relative_date_filter(
                "Order Date",
                "LASTN",
                "MONTHS",
                3
            ),
            TopNFilter(
                field=FilterField(fieldCaption="Category"),
                filterType="TOP",
                howMany=10,
                fieldToMeasure=FilterField(fieldCaption="Sales"),
                direction="TOP"
            )
        ]
    )
    
    print("\nExample 2 - Complex query:")
    print(complex_query.model_dump_json(indent=2))
    
    # Example 3: Create complete request
    request = QueryRequest(
        datasource=Datasource(datasourceLuid="abc123"),
        query=query,
        options=QueryOptions(returnFormat=ReturnFormat.OBJECTS, debug=False)
    )
    
    print("\nExample 3 - Complete request:")
    print(request.model_dump_json(indent=2))
