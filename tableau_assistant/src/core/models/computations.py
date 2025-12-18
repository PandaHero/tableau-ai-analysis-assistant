"""Computation models - Core abstraction for complex calculations.

The Computation model is the heart of the platform-agnostic semantic layer.
It represents: Computation = Target × Partition × Operation

partition_by is the key abstraction that unifies:
- Tableau: Partitioning/Addressing in Table Calculations
- Power BI: ALL/ALLEXCEPT in DAX
- SQL: PARTITION BY in window functions
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .enums import OperationType


class Operation(BaseModel):
    """Computation operation.
    
    Defines what calculation to perform.
    """
    model_config = ConfigDict(extra="forbid")
    
    type: OperationType = Field(
        description="""<what>Type of computation operation</what>
<when>ALWAYS required</when>
<rule>Must match how_type via OPERATION_TYPE_MAPPING</rule>
<must_not>Use type not in OPERATION_TYPE_MAPPING[how_type]</must_not>"""
    )
    
    params: dict = Field(
        default_factory=dict,
        description="""<what>Operation parameters</what>
<when>Required for some operations</when>
<rule>
- MOVING_AVG/MOVING_SUM: {"window_size": int}
- PERIOD_AGO: {"n": int, "granularity": str}
</rule>"""
    )


class Computation(BaseModel):
    """Computation = Target × Partition × Operation
    
    <what>Core computation definition (platform-agnostic)</what>
    
    <fill_order>
    1. target (ALWAYS)
    2. partition_by (ALWAYS, can be empty)
    3. operation (ALWAYS)
    4. alias (optional)
    </fill_order>
    
    <examples>
    Global ranking: {"target": "销售额", "partition_by": [], "operation": {"type": "RANK"}}
    Monthly ranking: {"target": "销售额", "partition_by": ["订单日期"], "operation": {"type": "RANK"}}
    </examples>
    
    <anti_patterns>
    ❌ partition_by not subset of where.dimensions
    ❌ operation.type not matching how_type
    </anti_patterns>
    """
    model_config = ConfigDict(extra="forbid")
    
    target: str = Field(
        description="""<what>Measure field to compute on</what>
<when>ALWAYS required</when>
<rule>Must be one of what.measures</rule>
<must_not>Use technical field name (will cause mapping error)</must_not>"""
    )
    
    partition_by: list[str] = Field(
        default_factory=list,
        description="""<what>Dimensions to partition by</what>
<when>ALWAYS fill (can be empty list)</when>
<rule>全局/总→[], 每月/当月→[时间维度], 每省→[省份]</rule>
<dependency>partition_by ⊆ where.dimensions</dependency>
<must_not>Include dimension not in where.dimensions (will cause error)</must_not>"""
    )
    
    operation: Operation = Field(
        description="""<what>Computation operation</what>
<when>ALWAYS required</when>
<rule>Must match how_type via OPERATION_TYPE_MAPPING</rule>"""
    )
    
    alias: str | None = Field(
        default=None,
        description="""<what>Display name for computation result</what>
<when>Optional</when>"""
    )
    
    @field_validator("target")
    @classmethod
    def target_not_empty(cls, v: str) -> str:
        """Validate target is not empty."""
        if not v or not v.strip():
            raise ValueError("target cannot be empty")
        return v.strip()
    
    @field_validator("partition_by")
    @classmethod
    def partition_by_is_list(cls, v: list[str]) -> list[str]:
        """Validate partition_by is a list of strings."""
        if not isinstance(v, list):
            raise ValueError("partition_by must be a list")
        return [s.strip() for s in v if s and s.strip()]
