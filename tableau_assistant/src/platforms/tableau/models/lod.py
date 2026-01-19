"""Tableau LOD (Level of Detail) Expression models.

LOD expressions compute aggregations at different granularities than the view.
They are used when partition_by differs from view dimensions in specific ways.

Key concept: partition_by → LOD type selection
- partition_by ⊂ view_dimensions → EXCLUDE (exclude some dimensions)
- partition_by ⊃ view_dimensions → INCLUDE (include extra dimensions)
- partition_by ∩ view_dimensions = ∅ → FIXED (completely independent)
"""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from tableau_assistant.src.platforms.tableau.models.vizql_types import VizQLFunction



class LODType(str, Enum):
    """LOD expression types.
    
    FIXED: Compute at specified dimensions only, ignoring view dimensions
    INCLUDE: Add dimensions to the view level
    EXCLUDE: Remove dimensions from the view level
    """
    FIXED = "FIXED"
    INCLUDE = "INCLUDE"
    EXCLUDE = "EXCLUDE"


class LODExpression(BaseModel):
    """LOD (Level of Detail) expression.
    
    LOD expressions are used when the computation granularity differs
    from the view granularity in ways that table calculations cannot handle.
    
    Mapping from SemanticQuery.Computation:
    - LODFixed/LODInclude/LODExclude → LOD expression
    - partition_by determines LOD type:
      - partition_by ⊂ view_dims → EXCLUDE
      - partition_by ⊃ view_dims → INCLUDE  
      - partition_by independent → FIXED
    
    Example:
    - View: [省份, 月份], partition_by: [省份]
    - Result: EXCLUDE [月份] (compute at province level, ignoring month)
    
    - View: [省份], partition_by: [省份, 月份]
    - Result: INCLUDE [月份] (compute at province+month level)
    
    - View: [省份, 月份], partition_by: []
    - Result: FIXED [] (compute at total level)
    """
    model_config = ConfigDict(extra="forbid")
    
    lod_type: LODType = Field(
        description="Type of LOD expression"
    )
    
    dimensions: list[str] = Field(
        default_factory=list,
        description="Dimensions for the LOD expression"
    )
    
    measure: str = Field(
        description="Measure field to aggregate"
    )
    
    aggregation: VizQLFunction = Field(
        default=VizQLFunction.SUM,
        description="Aggregation function"
    )
    
    alias: str | None = Field(
        default=None,
        description="Alias for the LOD expression result"
    )
    
    def to_calculation(self) -> str:
        """Convert to Tableau calculation string.
        
        Returns:
            Tableau calculation formula, e.g.:
            - {FIXED [省份]: SUM([销售额])}
            - {EXCLUDE [月份]: SUM([销售额])}
            - {INCLUDE [城市]: SUM([销售额])}
        """
        dims_str = ", ".join(f"[{d}]" for d in self.dimensions)
        
        if self.lod_type == LODType.FIXED:
            if dims_str:
                return f"{{FIXED {dims_str}: {self.aggregation.value}([{self.measure}])}}"
            else:
                # FIXED with no dimensions = total
                return f"{{FIXED : {self.aggregation.value}([{self.measure}])}}"
        
        elif self.lod_type == LODType.EXCLUDE:
            return f"{{EXCLUDE {dims_str}: {self.aggregation.value}([{self.measure}])}}"
        
        elif self.lod_type == LODType.INCLUDE:
            return f"{{INCLUDE {dims_str}: {self.aggregation.value}([{self.measure}])}}"
        
        raise ValueError(f"Unknown LOD type: {self.lod_type}")


def determine_lod_type(
    partition_by: list[str],
    view_dimensions: list[str],
) -> tuple[LODType, list[str]]:
    """Determine LOD type and dimensions from partition_by and view dimensions.
    
    Args:
        partition_by: Dimensions to partition by (from Computation)
        view_dimensions: Dimensions in the view (from SemanticQuery)
        
    Returns:
        Tuple of (LODType, dimensions for LOD expression)
        
    Logic:
    - partition_by is empty → FIXED [] (total level)
    - partition_by ⊂ view_dims → EXCLUDE (view_dims - partition_by)
    - partition_by ⊃ view_dims → INCLUDE (partition_by - view_dims)
    - partition_by == view_dims → No LOD needed (use table calc)
    """
    partition_set = set(partition_by)
    view_set = set(view_dimensions)
    
    # Empty partition_by = total level
    if not partition_by:
        return LODType.FIXED, []
    
    # partition_by is subset of view → EXCLUDE extra view dimensions
    if partition_set < view_set:
        exclude_dims = list(view_set - partition_set)
        return LODType.EXCLUDE, exclude_dims
    
    # partition_by is superset of view → INCLUDE extra partition dimensions
    if partition_set > view_set:
        include_dims = list(partition_set - view_set)
        return LODType.INCLUDE, include_dims
    
    # partition_by equals view → No LOD needed
    if partition_set == view_set:
        return LODType.FIXED, list(partition_by)  # Use FIXED as fallback
    
    # Disjoint or partial overlap → FIXED at partition_by level
    return LODType.FIXED, list(partition_by)
