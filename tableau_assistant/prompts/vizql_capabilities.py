"""
VizQL Capabilities Prompt Component

Structured description of VizQL query capabilities based on Tableau SDK.
Provides two versions:
1. Simplified version for Understanding Agent (capability boundaries and decomposition rules)
2. Detailed version for Query Planning Agent (full technical specifications)
"""


class VizQLCapabilitiesComponent:
    """
    VizQL query capabilities description
    
    Based on:
    - Tableau SDK TypeScript definitions (vizqlDataServiceApi.ts)
    - Python VizQL types (src/models/vizql_types.py)
    """
    
    def get_simplified_content(self) -> str:
        """
        Simplified version for Understanding Agent
        
        Focuses on:
        - Capability boundaries (what can/cannot be done)
        - Decomposition trigger conditions
        - Decomposition strategies
        
        Does NOT include:
        - Specific field type definitions
        - Filter syntax details
        - Parameter specifications
        """
        return """## VizQL Query Capability Boundaries

### Core Principle: Minimize Decomposition

**Priority Rule**: If one VizQL query can answer the question, do NOT decompose.

---

### What a Single VizQL Query CAN Handle

1. **Multiple Dimensions and Measures**
   - Example: Sales and Profit by Category and Region
   - Rule: Can include multiple dimensions and measures simultaneously

2. **Multiple Filter Conditions**
   - Example: Filter by specific regions, categories, and time range
   - Rule: Can combine multiple filters with AND/OR logic

3. **Aggregations**
   - Example: Sum, Average, Count, Max, Min
   - Rule: Supports SUM, AVG, COUNT, COUNTD, MIN, MAX, MEDIAN, STDEV, VAR

4. **Sorting and TopN**
   - Example: Top 10 products by sales
   - Rule: Can sort and limit result rows

5. **Time Functions**
   - Example: Group by Year, Quarter, Month, Week, Day
   - Rule: Can extract or truncate date fields

6. **Single Time Range**
   - Example: Last month, Year 2024, Last quarter
   - Rule: Can only query ONE continuous time period

7. **Simple Calculated Fields**
   - Example: Profit Margin = Profit / Sales
   - Rule: Can define simple calculation formulas in query

### What a Single VizQL Query CANNOT Handle

1. **Multiple Independent Time Periods**
   - ❌ Wrong: Query "this month" and "last year same period" together
   - ✅ Correct: Decompose into two queries for each time period
   - **Trigger**: Questions with time comparisons (YoY, MoM, vs XX period)

2. **Calculations Requiring Total and Details**
   - ❌ Wrong: Calculate "each category's percentage of total sales" in one query
   - ✅ Correct: Decompose into total query + detail query
   - **Trigger**: Need to calculate percentages, ratios, contributions

3. **Cross-Query Dependencies**
   - ❌ Wrong: Find highest sales category, then query its details in one query
   - ✅ Correct: Decompose into dependent queries
   - **Trigger**: Subsequent analysis depends on previous results

4. **Different Aggregation Granularities**
   - ❌ Wrong: Query "overall trend" and "regional details" together
   - ✅ Correct: Decompose into different granularity queries
   - **Trigger**: Need progressive analysis from coarse to fine

5. **Window Functions and Advanced Analytics**
   - ❌ Not Supported: RANK, ROW_NUMBER, PREVIOUS, LOOKUP, Moving Average
   - ✅ Alternative: Implement through multiple queries and post-processing
   - **Trigger**: Need ranking, cumulative, or moving calculations

---

### Question Decomposition Rules

#### Rule 1: Time Comparison → MUST Decompose into EXACTLY 2 Sub-Questions

**Trigger Keywords**:
- "vs last year", "YoY", "MoM", "compared to"
- "this month vs last month", "this year vs last year"
- "增长", "下降", "变化", "趋势" (when comparing time periods)

**Decomposition Strategy**:
- Sub-question 1: Current period data (execution_type="query")
- Sub-question 2: Comparison period data (execution_type="query")
- Sub-question 3: Calculate comparison result (execution_type="post_processing")
- Relationship: `comparison` (comparison_dimension: "time")

**Decomposition Pattern**:
```
Time Comparison Question
↓
Correct: 3 sub-questions (2 queries + 1 post-processing)
  - Sub-question 1: Current period data (query)
  - Sub-question 2: Comparison period data (query)
  - Sub-question 3: Calculate growth/change (post_processing, depends_on=[0,1])
  - Relationship: comparison (time)
```

#### Rule 2: Percentage/Ratio Calculation → MUST Decompose

**Trigger Keywords**:
- "percentage", "ratio", "proportion"
- "contribution", "share"

**Decomposition Strategy**:
- Sub-question 1: Total query
- Sub-question 2: Detail query
- Relationship: `breakdown`

**Decomposition Pattern**:
```
Percentage/Ratio Question
↓
Decompose into:
  1. Total/aggregate query
  2. Detail/breakdown query
Relationship: breakdown
```

#### Rule 3: Dependencies → MUST Decompose

**Trigger Patterns**:
- "first...then...", "find...then..."
- "highest...details of..."

**Decomposition Strategy**:
- Sub-questions in dependency order
- Use `depends_on` to mark dependencies
- Relationship: `drill_down` or `independent`

**Decomposition Pattern**:
```
Sequential Dependency Question
↓
Decompose in dependency order:
  1. First query (independent)
  2. Second query (depends_on: 1)
Relationship: drill_down or independent
```

#### Rule 4: Multi-Dimension Comparison → May Need Decomposition

**Decision Criteria**:
- Same dimension, different values → **NO decomposition** (use filters)
- Different dimensions → **NO decomposition** (multi-dimension query)
- Cross-time dimension comparison → **MUST decompose** (time comparison)

**Decision Patterns**:
```
Same dimension, different values → NO decomposition (use filters)
Different dimensions → NO decomposition (multi-dimension query)
Cross-time dimension comparison → MUST decompose (time comparison rule applies)
```

#### Rule 5: Exploratory Questions → NO Decomposition

**Trigger Keywords**:
- "why", "reason", "explain"
- "analyze", "explore", "discover"

**Handling**:
- Set `needs_exploration = true`
- **DO NOT decompose** (keep intact)
- **DO NOT set** `topn_requirement` (need full data visibility)
- Mark complexity as `Complex`

**Handling Pattern**:
```
Exploratory Question
↓
Set flags:
  - needs_exploration: true
  - No decomposition (keep intact)
  - No TopN limit (need full visibility)
  - complexity: Complex
```

---

### Decomposition Constraints

1. **Sub-questions Must Be Data Queries**
   - ✅ Correct: "What is sales of each category"
   - ❌ Wrong: "Analyze reasons for sales decline" (analysis task, not query)

2. **Sub-questions Must Use Business Terms**
   - ✅ Correct: "Sales by province"
   - ❌ Wrong: "Group by pro_name field and SUM Sales field"

3. **Sub-questions Must Have Clear Relationships**
   - If multiple sub-questions exist, must provide `sub_question_relationships`
   - Relationship types: `comparison`, `breakdown`, `drill_down`, `independent`

4. **Avoid Over-Decomposition**
   - If one query can complete, don't split into multiple
   - Decomposition purpose: overcome VizQL limitations, not decompose for sake of decomposing

---

### Quick Decision Flow

```
Question Analysis
    │
    ├─ Contains time comparison? ──YES──> Decompose (time comparison)
    │       │
    │      NO
    │       │
    ├─ Need percentage/ratio? ──YES──> Decompose (total + detail)
    │       │
    │      NO
    │       │
    ├─ Has dependencies? ──YES──> Decompose (by dependency order)
    │       │
    │      NO
    │       │
    ├─ Exploratory question? ──YES──> NO decomposition (needs_exploration=true)
    │       │
    │      NO
    │       │
    └─ Single query can handle ──> NO decomposition (keep single sub-question)
```"""
    
    def get_content(self) -> str:
        """
        Detailed version for Query Planning Agent
        
        Includes full technical specifications
        """
        return """## VizQL Query Capabilities

### Field Types

Three mutually exclusive types:

1. **BasicField**: Direct reference (no function, no calculation)
   - Required: fieldCaption
   - Optional: sortDirection, sortPriority

2. **FunctionField**: With aggregation or date function
   - Required: fieldCaption + function
   - Functions: SUM, AVG, COUNT, COUNTD, MIN, MAX, YEAR, MONTH, etc.
   - Note: ANY field can have function (measures, dimensions, dates)

3. **CalculationField**: With custom formula
   - Required: fieldCaption + calculation
   - Formula syntax: Use [Field Name] for references
   - Note: Cannot have function (mutually exclusive)

**Critical**: function and calculation are mutually exclusive.

### Filter Types

VizQL supports six filter types for different data scenarios:

1. **SetFilter** (Discrete Value Selection)
   - Purpose: Filter specific categorical values
   - Syntax: field IN [value1, value2, ...]
   - Examples:
     * Region IN ["East", "West"]
     * Category IN ["Furniture", "Technology"]
   - Use Case: Filtering specific categories, regions, or products

2. **TopNFilter** (Top/Bottom N Selection)
   - Purpose: Limit to top or bottom N values by a measure
   - Parameters:
     * field: Dimension to filter
     * by: Measure to rank by
     * n: Number of items (1-1000)
     * direction: TOP or BOTTOM
   - Examples:
     * TOP 10 Products BY Sales
     * BOTTOM 5 Regions BY Profit
   - Use Case: Finding best/worst performers

3. **MatchFilter** (Text Pattern Matching)
   - Purpose: Text search and pattern matching
   - Match Types:
     * startsWith: Text begins with pattern
     * endsWith: Text ends with pattern
     * contains: Text contains pattern
   - Examples:
     * Product Name CONTAINS "Chair"
     * Customer Name STARTS_WITH "A"
   - Use Case: Text search, name filtering

4. **QuantitativeNumericalFilter** (Numeric Range)
   - Purpose: Filter numeric values by range or condition
   - Filter Types:
     * RANGE: Between min and max (inclusive)
     * MIN: Greater than or equal to min
     * MAX: Less than or equal to max
     * ONLY_NULL: Only null values
     * ONLY_NON_NULL: Only non-null values
   - Examples:
     * Sales BETWEEN 1000 AND 5000
     * Profit >= 100
   - Options: includeNulls (true/false)

5. **QuantitativeDateFilter** (Date Range)
   - Purpose: Filter dates by specific range
   - Filter Types: Same as QuantitativeNumericalFilter
   - Date Format: ISO 8601 (YYYY-MM-DD)
   - Examples:
     * Order Date BETWEEN "2024-01-01" AND "2024-12-31"
     * Ship Date >= "2024-06-01"
   - Options: includeNulls (true/false)

6. **RelativeDateFilter** (Dynamic Date Range)
   - Purpose: Filter dates relative to current date
   - Date Range Types:
     * CURRENT: Current period (e.g., current month)
     * LAST: Previous N periods
     * NEXT: Next N periods
     * TODATE: From start of period to now
     * LASTN: Last N complete periods
     * NEXTN: Next N complete periods
   - Period Types:
     * MINUTES, HOURS, DAYS, WEEKS
     * MONTHS, QUARTERS, YEARS
   - Examples:
     * LAST 3 MONTHS
     * CURRENT QUARTER
     * LAST 7 DAYS
   - Use Case: Rolling time windows, recent data analysis

### Query Options

1. **Sorting**
   - sortDirection: ASC (ascending) or DESC (descending)
   - sortPriority: Integer (lower = higher priority)
   - Multiple fields: Use sortPriority to control order

2. **Formatting**
   - maxDecimalPlaces: 0-10 decimal places for numeric fields
   - fieldAlias: Custom display name for fields

3. **Return Format**
   - OBJECTS: Array of objects (default)
   - ARRAYS: Array of arrays (more compact)

### Query Limitations

1. **Row Limit**
   - Maximum: 10,000 rows per query
   - Recommendation: Use TopNFilter or filters to limit results
   - Large datasets: Consider aggregation or sampling

2. **Performance Considerations**
   - Complex calculations: May slow query execution
   - High cardinality: Avoid dimensions with >10,000 unique values
   - Multiple filters: Combine when possible for efficiency

3. **Single Query Constraints**
   - One aggregation level: Cannot mix different granularities
   - No post-aggregation: Cannot filter on aggregated results
   - No window functions: No RANK, ROW_NUMBER, etc.

### Best Practices

1. **Field Selection**
   - Use exact fieldCaption from metadata
   - Verify field exists and type matches usage
   - Choose appropriate aggregation function

2. **Filter Strategy**
   - Apply filters early to reduce data volume
   - Use TopNFilter for ranking questions
   - Use RelativeDateFilter for time-based analysis

3. **Performance Optimization**
   - Limit result set size with filters or TopN
   - Avoid unnecessary high-cardinality dimensions
   - Use appropriate aggregation level

4. **Query Decomposition**
   - Split when different time periods needed
   - Split when different aggregation levels required
   - Keep single query when possible for simplicity"""
    



# Create component instance
vizql_capabilities = VizQLCapabilitiesComponent()


# ============= 导出 =============

__all__ = [
    "VizQLCapabilitiesComponent",
    "vizql_capabilities",
]
