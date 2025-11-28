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


# ============= Table Calculation Types =============

class TableCalcComputedAggregation(str, Enum):
    """
    Aggregation functions for table calculations
    
    Used in RUNNING_TOTAL and MOVING_CALCULATION table calculations.
    """
    SUM = "SUM"
    AVG = "AVG"
    MIN = "MIN"
    MAX = "MAX"


class TableCalcFieldReference(BaseModel):
    """
    Field reference used in table calculations
    
    References a field that participates in table calculation partitioning/addressing.
    Can optionally apply a function to the field (e.g., YEAR(Order Date)).
    
    Examples:
        TableCalcFieldReference(fieldCaption="Category")
        TableCalcFieldReference(fieldCaption="Order Date", function=FunctionEnum.YEAR)
    """
    model_config = ConfigDict(
        frozen=False,
        extra="forbid",
        str_strip_whitespace=True,
    )
    
    fieldCaption: Annotated[str, Field(
        min_length=1,
        description="""Field caption to reference.

Usage:
- Specify the field name for partitioning/addressing
- Must match a field name in the query

Values: Field name string (e.g., 'Category', 'Order Date')"""
    )]
    
    function: Optional[FunctionEnum] = Field(
        default=None,
        description="""Optional function to apply to the field.

Usage:
- Apply date functions like YEAR, MONTH to date fields
- Apply aggregations if needed

Values: Any FunctionEnum value or None
- Example: FunctionEnum.YEAR for YEAR(Order Date)
- None for direct field reference"""
    )


class TableCalcCustomSort(BaseModel):
    """
    Custom sort specification for table calculations
    
    Defines how to sort data within table calculation partitions.
    """
    model_config = ConfigDict(
        frozen=False,
        extra="forbid",
        str_strip_whitespace=True,
    )
    
    fieldCaption: Annotated[str, Field(
        min_length=1,
        description="""Field to sort by.

Usage:
- Specify the field name for sorting

Values: Field name string"""
    )]
    
    function: Annotated[FunctionEnum, Field(
        description="""Function to apply to the sort field.

Usage:
- Apply aggregation or date function for sorting

Values: Any FunctionEnum value"""
    )]
    
    direction: Annotated[SortDirection, Field(
        description="""Sort direction.

Usage:
- ASC for ascending order
- DESC for descending order

Values: SortDirection.ASC or SortDirection.DESC"""
    )]


class TableCalcSpecification(BaseModel):
    """
    Base class for table calculation specifications
    
    Table calculations perform computations on the query result set,
    enabling advanced analytics like running totals, moving averages, and rankings.
    
    In Tableau, table calculations use:
    - Partitioning: Defines independent groups (scope of calculation)
    - Addressing: Defines direction/order within each partition
    
    The 'dimensions' field specifies both partitioning and addressing fields.
    
    All table calculations share:
    - tableCalcType: The type of calculation
    - dimensions: Field references that define partitioning and addressing
    
    Note: This is a base class. Use specific subclasses like:
    - RunningTotalTableCalcSpecification
    - MovingTableCalcSpecification
    - RankTableCalcSpecification
    - etc.
    """
    model_config = ConfigDict(
        frozen=False,
        extra="forbid",
        str_strip_whitespace=True,
    )
    
    tableCalcType: Annotated[
        Literal[
            "RUNNING_TOTAL",
            "MOVING_CALCULATION",
            "RANK",
            "PERCENTILE",
            "PERCENT_OF_TOTAL",
            "PERCENT_FROM",
            "PERCENT_DIFFERENCE_FROM",
            "DIFFERENCE_FROM",
            "CUSTOM",
            "NESTED"
        ],
        Field(
            description="""Type of table calculation.

Usage:
- Specify the calculation type to apply

Values: One of 10 supported types
- RUNNING_TOTAL: Cumulative sum or average
- MOVING_CALCULATION: Moving average or sum
- RANK: Ranking (competition, dense, or unique)
- PERCENTILE: Percentile calculation
- PERCENT_OF_TOTAL: Percentage of total
- PERCENT_FROM: Percentage from a reference point
- PERCENT_DIFFERENCE_FROM: Percentage difference from reference
- DIFFERENCE_FROM: Absolute difference from reference
- CUSTOM: Custom table calculation formula
- NESTED: Nested table calculations"""
        )
    ]
    
    dimensions: Annotated[
        List[TableCalcFieldReference],
        Field(
            min_length=1,
            description="""Field references for partitioning and addressing.

Usage:
- Define how the calculation is scoped and ordered
- At least one field reference is required
- Order matters: first field is primary addressing dimension

Values: List of TableCalcFieldReference objects
- Example: [TableCalcFieldReference(fieldCaption="Category")]
- Example with function: [TableCalcFieldReference(fieldCaption="Order Date", function=FunctionEnum.YEAR)]

Tableau Concepts:
- Partitioning: Defines independent calculation groups
- Addressing: Defines direction/order within partitions
- These dimensions control both aspects"""
        )
    ]


class RunningTotalTableCalcSpecification(TableCalcSpecification):
    """
    Running total table calculation specification
    
    Computes cumulative sum or average across the partition.
    
    Examples:
        # Cumulative sum of sales by category
        RunningTotalTableCalcSpecification(
            tableCalcType="RUNNING_TOTAL",
            dimensions=[TableCalcFieldReference(fieldCaption="Category")],
            aggregation=TableCalcComputedAggregation.SUM
        )
        
        # Cumulative average, restart every year
        RunningTotalTableCalcSpecification(
            tableCalcType="RUNNING_TOTAL",
            dimensions=[TableCalcFieldReference(fieldCaption="Order Date")],
            aggregation=TableCalcComputedAggregation.AVG,
            restartEvery=TableCalcFieldReference(
                fieldCaption="Order Date",
                function=FunctionEnum.YEAR
            )
        )
    """
    tableCalcType: Literal["RUNNING_TOTAL"] = "RUNNING_TOTAL"
    
    aggregation: Optional[TableCalcComputedAggregation] = Field(
        default=None,
        description="""Aggregation function to apply.

Usage:
- Specify how to aggregate values in the running total
- Optional, defaults to SUM if not specified

Values: TableCalcComputedAggregation enum
- SUM: Cumulative sum
- AVG: Cumulative average
- MIN: Cumulative minimum
- MAX: Cumulative maximum"""
    )
    
    restartEvery: Optional[TableCalcFieldReference] = Field(
        default=None,
        description="""Field to restart the calculation.

Usage:
- Specify a field to reset the running total
- When this field value changes, calculation restarts from zero
- Optional, if not specified, calculation runs across entire partition

Values: TableCalcFieldReference or None
- Example: Restart every year with YEAR(Order Date)"""
    )
    
    customSort: Optional[TableCalcCustomSort] = Field(
        default=None,
        description="""Custom sort specification.

Usage:
- Define custom sorting within partitions
- Optional, uses default sort if not specified

Values: TableCalcCustomSort or None"""
    )
    
    secondaryTableCalculation: Optional['TableCalcSpecification'] = Field(
        default=None,
        description="""Secondary table calculation to apply.

Usage:
- Apply another table calculation on top of running total
- Optional, for nested calculations

Values: Another TableCalcSpecification or None"""
    )


class MovingTableCalcSpecification(TableCalcSpecification):
    """
    Moving calculation table calculation specification
    
    Computes moving average or sum over a sliding window.
    
    Examples:
        # 3-period moving average (2 previous + current)
        MovingTableCalcSpecification(
            tableCalcType="MOVING_CALCULATION",
            dimensions=[TableCalcFieldReference(fieldCaption="Order Date")],
            aggregation=TableCalcComputedAggregation.AVG,
            previous=2,
            next=0,
            includeCurrent=True
        )
        
        # 5-period centered moving average (2 previous + current + 2 next)
        MovingTableCalcSpecification(
            tableCalcType="MOVING_CALCULATION",
            dimensions=[TableCalcFieldReference(fieldCaption="Order Date")],
            aggregation=TableCalcComputedAggregation.AVG,
            previous=2,
            next=2,
            includeCurrent=True
        )
    """
    tableCalcType: Literal["MOVING_CALCULATION"] = "MOVING_CALCULATION"
    
    aggregation: Optional[TableCalcComputedAggregation] = Field(
        default=None,
        description="""Aggregation function to apply.

Usage:
- Specify how to aggregate values in the moving window
- Optional, defaults to SUM if not specified

Values: TableCalcComputedAggregation enum
- SUM: Moving sum
- AVG: Moving average
- MIN: Moving minimum
- MAX: Moving maximum"""
    )
    
    previous: Optional[int] = Field(
        default=-2,
        ge=0,
        description="""Number of previous values to include.

Usage:
- Specify how many previous values to include in window
- Must be >= 0
- Default is -2 (OpenAPI spec default)

Values: Non-negative integer
- 0: No previous values
- 2: Include 2 previous values"""
    )
    
    next: Optional[int] = Field(
        default=0,
        ge=0,
        description="""Number of next values to include.

Usage:
- Specify how many next values to include in window
- Must be >= 0
- Default is 0

Values: Non-negative integer
- 0: No next values
- 2: Include 2 next values"""
    )
    
    includeCurrent: Optional[bool] = Field(
        default=True,
        description="""Whether to include current value.

Usage:
- Include or exclude the current value in calculation
- Default is True

Values: Boolean
- True: Include current value
- False: Exclude current value"""
    )
    
    fillInNull: Optional[bool] = Field(
        default=None,
        description="""Whether to fill in null values.

Usage:
- Handle null values in the window
- Optional

Values: Boolean or None
- True: Fill in nulls
- False: Keep nulls as is
- None: Use default behavior"""
    )
    
    customSort: Optional[TableCalcCustomSort] = Field(
        default=None,
        description="""Custom sort specification.

Usage:
- Define custom sorting within partitions
- Optional, uses default sort if not specified

Values: TableCalcCustomSort or None"""
    )
    
    secondaryTableCalculation: Optional['TableCalcSpecification'] = Field(
        default=None,
        description="""Secondary table calculation to apply.

Usage:
- Apply another table calculation on top of moving calculation
- Optional, for nested calculations

Values: Another TableCalcSpecification or None"""
    )


class RankTableCalcSpecification(TableCalcSpecification):
    """
    Rank table calculation specification
    
    Computes ranking within partitions.
    
    Examples:
        # Competition ranking (1, 2, 2, 4) - default
        RankTableCalcSpecification(
            tableCalcType="RANK",
            dimensions=[TableCalcFieldReference(fieldCaption="Category")],
            rankType="COMPETITION",
            direction=SortDirection.DESC
        )
        
        # Dense ranking (1, 2, 2, 3)
        RankTableCalcSpecification(
            tableCalcType="RANK",
            dimensions=[TableCalcFieldReference(fieldCaption="Category")],
            rankType="DENSE",
            direction=SortDirection.ASC
        )
    """
    tableCalcType: Literal["RANK"] = "RANK"
    
    rankType: Optional[Literal["COMPETITION", "MODIFIED COMPETITION", "DENSE", "UNIQUE"]] = Field(
        default="COMPETITION",
        description="""Type of ranking to apply.

Usage:
- Specify how to handle ties in ranking
- Default is COMPETITION

Values: Ranking type
- COMPETITION: Standard competition ranking (1, 2, 2, 4)
- MODIFIED COMPETITION: Modified competition ranking (1, 3, 3, 4)
- DENSE: Dense ranking (1, 2, 2, 3)
- UNIQUE: Unique ranking, no ties (1, 2, 3, 4)"""
    )
    
    direction: Optional[SortDirection] = Field(
        default=None,
        description="""Sort direction for ranking.

Usage:
- ASC: Rank from smallest to largest
- DESC: Rank from largest to smallest
- Optional, uses default sort if not specified

Values: SortDirection enum or None
- SortDirection.ASC: Ascending
- SortDirection.DESC: Descending"""
    )


class PercentileTableCalcSpecification(TableCalcSpecification):
    """Percentile table calculation specification"""
    tableCalcType: Literal["PERCENTILE"] = "PERCENTILE"
    
    direction: Optional[SortDirection] = Field(
        default=None,
        description="""Sort direction for percentile calculation.

Usage:
- Define sort order for percentile
- Optional

Values: SortDirection enum or None"""
    )


class PercentOfTotalTableCalcSpecification(TableCalcSpecification):
    """Percent of total table calculation specification"""
    tableCalcType: Literal["PERCENT_OF_TOTAL"] = "PERCENT_OF_TOTAL"
    
    levelAddress: Optional[TableCalcFieldReference] = Field(
        default=None,
        description="""Level addressing field.

Usage:
- Specify the level for percentage calculation
- Optional

Values: TableCalcFieldReference or None"""
    )
    
    customSort: Optional[TableCalcCustomSort] = Field(
        default=None,
        description="""Custom sort specification.

Usage:
- Define custom sorting
- Optional

Values: TableCalcCustomSort or None"""
    )


class PercentFromTableCalcSpecification(TableCalcSpecification):
    """Percent from table calculation specification"""
    tableCalcType: Literal["PERCENT_FROM"] = "PERCENT_FROM"
    
    levelAddress: Optional[TableCalcFieldReference] = Field(
        default=None,
        description="""Level addressing field.

Usage:
- Specify the level for calculation
- Optional

Values: TableCalcFieldReference or None"""
    )
    
    relativeTo: Optional[Literal["PREVIOUS", "NEXT", "FIRST", "LAST"]] = Field(
        default=None,
        description="""Reference point for percentage calculation.

Usage:
- Define what to compare against
- Optional

Values: Reference point or None
- PREVIOUS: Compare to previous value
- NEXT: Compare to next value
- FIRST: Compare to first value
- LAST: Compare to last value
- None: Use default behavior"""
    )
    
    customSort: Optional[TableCalcCustomSort] = Field(
        default=None,
        description="""Custom sort specification.

Usage:
- Define custom sorting
- Optional

Values: TableCalcCustomSort or None"""
    )


class PercentDifferenceFromTableCalcSpecification(TableCalcSpecification):
    """Percent difference from table calculation specification"""
    tableCalcType: Literal["PERCENT_DIFFERENCE_FROM"] = "PERCENT_DIFFERENCE_FROM"
    
    levelAddress: Optional[TableCalcFieldReference] = Field(
        default=None,
        description="""Level addressing field.

Usage:
- Specify the level for calculation
- Optional

Values: TableCalcFieldReference or None"""
    )
    
    relativeTo: Optional[Literal["PREVIOUS", "NEXT", "FIRST", "LAST"]] = Field(
        default=None,
        description="""Reference point for difference calculation.

Usage:
- Define what to compare against
- Optional

Values: Reference point or None
- PREVIOUS: Compare to previous value
- NEXT: Compare to next value
- FIRST: Compare to first value
- LAST: Compare to last value
- None: Use default behavior"""
    )
    
    customSort: Optional[TableCalcCustomSort] = Field(
        default=None,
        description="""Custom sort specification.

Usage:
- Define custom sorting
- Optional

Values: TableCalcCustomSort or None"""
    )


class DifferenceFromTableCalcSpecification(TableCalcSpecification):
    """Difference from table calculation specification"""
    tableCalcType: Literal["DIFFERENCE_FROM"] = "DIFFERENCE_FROM"
    
    levelAddress: Optional[TableCalcFieldReference] = Field(
        default=None,
        description="""Level addressing field.

Usage:
- Specify the level for calculation
- Optional

Values: TableCalcFieldReference or None"""
    )
    
    relativeTo: Optional[Literal["PREVIOUS", "NEXT", "FIRST", "LAST"]] = Field(
        default=None,
        description="""Reference point for difference calculation.

Usage:
- Define what to compare against
- Optional

Values: Reference point or None
- PREVIOUS: Compare to previous value
- NEXT: Compare to next value
- FIRST: Compare to first value
- LAST: Compare to last value
- None: Use default behavior"""
    )
    
    customSort: Optional[TableCalcCustomSort] = Field(
        default=None,
        description="""Custom sort specification.

Usage:
- Define custom sorting
- Optional

Values: TableCalcCustomSort or None"""
    )


class CustomTableCalcSpecification(TableCalcSpecification):
    """Custom table calculation specification"""
    tableCalcType: Literal["CUSTOM"] = "CUSTOM"
    
    levelAddress: Optional[TableCalcFieldReference] = Field(
        default=None,
        description="""Level addressing field.

Usage:
- Specify the level for calculation
- Optional

Values: TableCalcFieldReference or None"""
    )
    
    restartEvery: Optional[TableCalcFieldReference] = Field(
        default=None,
        description="""Field to restart the calculation.

Usage:
- Specify a field to reset the calculation
- Optional

Values: TableCalcFieldReference or None"""
    )
    
    customSort: Optional[TableCalcCustomSort] = Field(
        default=None,
        description="""Custom sort specification.

Usage:
- Define custom sorting
- Optional

Values: TableCalcCustomSort or None"""
    )


class NestedTableCalcSpecification(TableCalcSpecification):
    """Nested table calculation specification"""
    tableCalcType: Literal["NESTED"] = "NESTED"
    
    fieldCaption: Annotated[str, Field(
        min_length=1,
        description="""Field caption for nested calculation.

Usage:
- Specify the field name
- Required for nested calculations

Values: Field name string"""
    )]
    
    levelAddress: Optional[TableCalcFieldReference] = Field(
        default=None,
        description="""Level addressing field.

Usage:
- Specify the level for calculation
- Optional

Values: TableCalcFieldReference or None"""
    )
    
    restartEvery: Optional[TableCalcFieldReference] = Field(
        default=None,
        description="""Field to restart the calculation.

Usage:
- Specify a field to reset the calculation
- Optional

Values: TableCalcFieldReference or None"""
    )
    
    customSort: Optional[TableCalcCustomSort] = Field(
        default=None,
        description="""Custom sort specification.

Usage:
- Define custom sorting
- Optional

Values: TableCalcCustomSort or None"""
    )


class TableCalcField(FieldBase):
    """
    Table calculation field
    
    Applies table calculations to query results for advanced analytics.
    
    Used for:
    - Running totals: RUNNING_TOTAL
    - Moving averages: MOVING_CALCULATION
    - Rankings: RANK
    - Percentages: PERCENT_OF_TOTAL
    - And 6 other calculation types
    
    Examples:
        # Running total of sales
        TableCalcField(
            fieldCaption="Sales",
            function=FunctionEnum.SUM,
            tableCalculation=RunningTotalTableCalcSpecification(
                tableCalcType="RUNNING_TOTAL",
                dimensions=[TableCalcFieldReference(fieldCaption="Category")],
                aggregation=TableCalcComputedAggregation.SUM
            )
        )
        
        # 3-period moving average
        TableCalcField(
            fieldCaption="Sales",
            function=FunctionEnum.AVG,
            tableCalculation=MovingTableCalcSpecification(
                tableCalcType="MOVING_CALCULATION",
                dimensions=[TableCalcFieldReference(fieldCaption="Order Date")],
                aggregation=TableCalcComputedAggregation.AVG,
                previous=2,
                next=0,
                includeCurrent=True
            )
        )
        
        # Ranking by sales
        TableCalcField(
            fieldCaption="Sales",
            tableCalculation=RankTableCalcSpecification(
                tableCalcType="RANK",
                dimensions=[TableCalcFieldReference(fieldCaption="Category")],
                rankType="COMPETITION",
                direction=SortDirection.DESC
            )
        )
    """
    function: Optional[FunctionEnum] = Field(
        default=None,
        description="""Optional function to apply before table calculation.

Usage:
- Apply aggregation or date function to the field first
- Then apply table calculation on top
- Optional, not all table calculations need a function

Values: FunctionEnum or None
- Example: FunctionEnum.SUM for SUM(Sales) before running total"""
    )
    
    calculation: Optional[str] = Field(
        default=None,
        description="""Optional calculation formula.

Usage:
- Define a calculation before applying table calculation
- Optional

Values: Calculation string or None
- Example: '[Profit] / [Sales]' before table calculation"""
    )
    
    tableCalculation: Annotated[
        Union[
            RunningTotalTableCalcSpecification,
            MovingTableCalcSpecification,
            RankTableCalcSpecification,
            PercentileTableCalcSpecification,
            PercentOfTotalTableCalcSpecification,
            PercentFromTableCalcSpecification,
            PercentDifferenceFromTableCalcSpecification,
            DifferenceFromTableCalcSpecification,
            CustomTableCalcSpecification,
            NestedTableCalcSpecification,
        ],
        Field(
            description="""Table calculation specification.

Usage:
- Define the table calculation to apply
- Required field

Values: One of 10 TableCalcSpecification types
- RunningTotalTableCalcSpecification
- MovingTableCalcSpecification
- RankTableCalcSpecification
- PercentileTableCalcSpecification
- PercentOfTotalTableCalcSpecification
- PercentFromTableCalcSpecification
- PercentDifferenceFromTableCalcSpecification
- DifferenceFromTableCalcSpecification
- CustomTableCalcSpecification
- NestedTableCalcSpecification"""
        )
    ]
    
    nestedTableCalculations: Optional[List[Union[
        RunningTotalTableCalcSpecification,
        MovingTableCalcSpecification,
        RankTableCalcSpecification,
        PercentileTableCalcSpecification,
        PercentOfTotalTableCalcSpecification,
        PercentFromTableCalcSpecification,
        PercentDifferenceFromTableCalcSpecification,
        DifferenceFromTableCalcSpecification,
        CustomTableCalcSpecification,
        NestedTableCalcSpecification,
    ]]] = Field(
        default=None,
        description="""Optional nested table calculations.

Usage:
- Apply multiple table calculations in sequence
- Optional, for advanced scenarios

Values: List of TableCalcSpecification or None"""
    )


# Discriminated Union - four types are mutually exclusive
# According to Tableau SDK definition: BasicField, FunctionField, CalculationField, or TableCalcField
VizQLField = Annotated[
    Union[BasicField, FunctionField, CalculationField, TableCalcField],
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
