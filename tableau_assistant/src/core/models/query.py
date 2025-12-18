"""SemanticQuery - The core output model of the semantic layer.

SemanticQuery is platform-agnostic and represents user intent.
Platform adapters convert it to platform-specific queries.
"""

from pydantic import BaseModel, ConfigDict, Field

from .computations import Computation
from .fields import DimensionField, MeasureField, Sort
from .filters import (
    DateRangeFilter,
    Filter,
    NumericRangeFilter,
    SetFilter,
    TextMatchFilter,
    TopNFilter,
)


class SemanticQuery(BaseModel):
    """Core semantic query (platform-agnostic).
    
    <what>Final output of Semantic Parser Agent for DATA_QUERY intent</what>
    
    This model represents user intent in a platform-independent way.
    Platform adapters (Tableau, Power BI, SQL) convert this to platform-specific queries.
    
    <fill_order>
    1. dimensions (from where.dimensions)
    2. measures (from what.measures)
    3. computations (from Step 2, if how_type != SIMPLE)
    4. filters (from where.filters)
    5. sorts (optional)
    6. row_limit (optional)
    </fill_order>
    
    <examples>
    Simple query: {"dimensions": [{"field_name": "省份"}], "measures": [{"field_name": "销售额"}]}
    With computation: {"dimensions": [...], "measures": [...], "computations": [{"target": "销售额", "partition_by": [], "operation": {"type": "RANK"}}]}
    </examples>
    """
    model_config = ConfigDict(extra="forbid")
    
    dimensions: list[DimensionField] | None = Field(
        default=None,
        description="""<what>Dimension fields in the query</what>
<when>Usually required for grouping</when>
<rule>Built from where.dimensions</rule>"""
    )
    
    measures: list[MeasureField] | None = Field(
        default=None,
        description="""<what>Measure fields in the query</what>
<when>Usually required for aggregation</when>
<rule>Built from what.measures</rule>"""
    )
    
    computations: list[Computation] | None = Field(
        default=None,
        description="""<what>Complex computations</what>
<when>ONLY when how_type != SIMPLE</when>
<rule>Built from Step 2 output</rule>"""
    )
    
    filters: list[
        SetFilter | DateRangeFilter | NumericRangeFilter | TextMatchFilter | TopNFilter
    ] | None = Field(
        default=None,
        description="""<what>Filter conditions</what>
<when>When user specifies filtering</when>
<rule>Built from where.filters</rule>"""
    )
    
    sorts: list[Sort] | None = Field(
        default=None,
        description="""<what>Sort specifications</what>
<when>When user specifies ordering</when>"""
    )
    
    row_limit: int | None = Field(
        default=None,
        description="""<what>Maximum number of rows to return</what>
<when>When user specifies limit</when>"""
    )
