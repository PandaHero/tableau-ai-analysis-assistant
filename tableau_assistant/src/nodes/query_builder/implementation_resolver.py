"""
Implementation Resolver

Determines whether to use table calculations or LOD expressions
based on the semantic analysis specification.

Architecture:
- Code rules for simple scenarios
- LLM fallback for complex scenarios (future)

Requirements:
- R7.2.8: LOD judgment logic
- R7.2.9: requires_external_dimension detection
- R7.2.10: target_granularity handling
- R7.2.11: addressing derivation
"""

import logging
from typing import Dict, Optional, List, TYPE_CHECKING
from dataclasses import dataclass
from enum import Enum

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

from tableau_assistant.src.models.semantic.query import (
    SemanticQuery,
    AnalysisSpec,
    DimensionSpec,
)
from tableau_assistant.src.models.field_mapper.models import MappedQuery
from tableau_assistant.src.models.semantic.enums import (
    AnalysisType,
    ComputationScope,
)

logger = logging.getLogger(__name__)


class ImplementationType(str, Enum):
    """Implementation type for analysis"""
    TABLE_CALC = "table_calc"
    LOD_FIXED = "lod_fixed"
    LOD_INCLUDE = "lod_include"
    LOD_EXCLUDE = "lod_exclude"
    SIMPLE_AGG = "simple_agg"


@dataclass
class DimensionInfo:
    """Dimension information for table calculation addressing"""
    field_name: str
    function: Optional[str] = None  # e.g., "YEAR", "MONTH"


@dataclass
class ImplementationDecision:
    """
    Implementation decision result
    
    Contains:
    - impl_type: Type of implementation (table_calc, lod_fixed, etc.)
    - addressing: List of DimensionInfo for table calc addressing
    - partitioning: List of DimensionInfo for table calc partitioning
    - lod_dimensions: List of dimensions for LOD expression
    - reasoning: Explanation of the decision
    """
    impl_type: ImplementationType
    addressing: List[DimensionInfo] = None
    partitioning: List[DimensionInfo] = None
    lod_dimensions: List[str] = None
    reasoning: str = ""
    
    def __post_init__(self):
        if self.addressing is None:
            self.addressing = []
        if self.partitioning is None:
            self.partitioning = []
        if self.lod_dimensions is None:
            self.lod_dimensions = []


class ImplementationResolver:
    """
    Resolves semantic analysis specs to VizQL implementation decisions.
    
    Decision Tree:
    1. Check if analysis requires external dimension → LOD
    2. Check if target_granularity differs from query dimensions → LOD
    3. Otherwise → Table Calculation
    
    For Table Calculations:
    - Single dimension: addressing = [that dimension]
    - Multiple dimensions + per_group: addressing = [time dimension]
    - Multiple dimensions + across_all: addressing = [all dimensions]
    """
    
    def __init__(self, llm: Optional["BaseChatModel"] = None):
        """
        Initialize resolver.
        
        Args:
            llm: Optional LLM for complex scenarios (future use)
        """
        self.llm = llm
    
    def resolve(
        self,
        analysis: AnalysisSpec,
        dimensions: List[DimensionSpec],
        field_mappings: Dict[str, str],
    ) -> ImplementationDecision:
        """
        Resolve implementation for an analysis spec.
        
        Args:
            analysis: The analysis specification
            dimensions: List of dimensions in the query
            field_mappings: Business term to technical field mappings
            
        Returns:
            ImplementationDecision with implementation details
        """
        logger.debug(f"Resolving implementation for analysis type: {analysis.type}")
        
        # Map time_granularity to VizQL function name
        granularity_to_function = {
            "year": "YEAR",
            "quarter": "QUARTER",
            "month": "MONTH",
            "week": "WEEK",
            "day": "DAY",
        }
        
        # Get technical field names and function info for dimensions
        tech_dimensions: List[DimensionInfo] = []
        time_dimensions: List[DimensionInfo] = []
        non_time_dimensions: List[DimensionInfo] = []
        
        for dim in dimensions:
            tech_field = field_mappings.get(dim.name, dim.name)
            func = granularity_to_function.get(dim.time_granularity) if dim.time_granularity else None
            dim_info = DimensionInfo(field_name=tech_field, function=func)
            tech_dimensions.append(dim_info)
            if dim.time_granularity is not None:
                time_dimensions.append(dim_info)
            else:
                non_time_dimensions.append(dim_info)
        
        # Decision logic based on analysis type
        if analysis.type == AnalysisType.CUMULATIVE:
            return self._resolve_cumulative(
                analysis, tech_dimensions, time_dimensions, non_time_dimensions
            )
        elif analysis.type == AnalysisType.RANKING:
            return self._resolve_ranking(
                analysis, tech_dimensions, time_dimensions, non_time_dimensions
            )
        elif analysis.type == AnalysisType.PERCENTAGE:
            return self._resolve_percentage(
                analysis, tech_dimensions, time_dimensions, non_time_dimensions
            )
        elif analysis.type == AnalysisType.MOVING:
            return self._resolve_moving(
                analysis, tech_dimensions, time_dimensions, non_time_dimensions
            )
        elif analysis.type == AnalysisType.PERIOD_COMPARE:
            return self._resolve_period_compare(
                analysis, tech_dimensions, time_dimensions, non_time_dimensions
            )
        else:
            # Default to table calculation
            return self._resolve_default(
                analysis, tech_dimensions, time_dimensions, non_time_dimensions
            )
    
    def _resolve_cumulative(
        self,
        analysis: AnalysisSpec,
        tech_dimensions: List[DimensionInfo],
        time_dimensions: List[DimensionInfo],
        non_time_dimensions: List[DimensionInfo],
    ) -> ImplementationDecision:
        """
        Resolve cumulative analysis.
        
        Rules:
        - Single dimension: addressing = [that dimension]
        - Multiple dimensions + per_group: addressing = [time dimension]
          (non-time dimensions become implicit partitioning)
        - Multiple dimensions + across_all: addressing = [all dimensions]
        """
        dim_count = len(tech_dimensions)
        
        if dim_count == 0:
            # No dimensions - simple aggregation
            return ImplementationDecision(
                impl_type=ImplementationType.SIMPLE_AGG,
                reasoning="No dimensions, using simple aggregation"
            )
        
        if dim_count == 1:
            # Single dimension - address by that dimension
            return ImplementationDecision(
                impl_type=ImplementationType.TABLE_CALC,
                addressing=list(tech_dimensions),
                reasoning="Single dimension cumulative: addressing by the dimension"
            )
        
        # Multiple dimensions
        scope = analysis.computation_scope or ComputationScope.PER_GROUP
        
        if scope == ComputationScope.PER_GROUP:
            # Per group: address by time dimension, partition by others
            if time_dimensions:
                return ImplementationDecision(
                    impl_type=ImplementationType.TABLE_CALC,
                    addressing=list(time_dimensions),
                    partitioning=list(non_time_dimensions),
                    reasoning="Multi-dimension per_group: addressing by time, partitioning by others"
                )
            else:
                # No time dimension - use first dimension for addressing
                return ImplementationDecision(
                    impl_type=ImplementationType.TABLE_CALC,
                    addressing=[tech_dimensions[0]],
                    partitioning=list(tech_dimensions[1:]),
                    reasoning="Multi-dimension per_group (no time): addressing by first dimension"
                )
        else:
            # Across all: address by all dimensions
            return ImplementationDecision(
                impl_type=ImplementationType.TABLE_CALC,
                addressing=list(tech_dimensions),
                reasoning="Multi-dimension across_all: addressing by all dimensions"
            )
    
    def _resolve_ranking(
        self,
        analysis: AnalysisSpec,
        tech_dimensions: List[DimensionInfo],
        time_dimensions: List[DimensionInfo],
        non_time_dimensions: List[DimensionInfo],
    ) -> ImplementationDecision:
        """
        Resolve ranking analysis.
        
        Rules:
        - Single dimension: addressing = [that dimension]
        - Multiple dimensions + per_group: partition by non-ranking dimensions
        - Multiple dimensions + across_all: address by all
        """
        dim_count = len(tech_dimensions)
        
        if dim_count == 0:
            return ImplementationDecision(
                impl_type=ImplementationType.SIMPLE_AGG,
                reasoning="No dimensions for ranking"
            )
        
        if dim_count == 1:
            return ImplementationDecision(
                impl_type=ImplementationType.TABLE_CALC,
                addressing=list(tech_dimensions),
                reasoning="Single dimension ranking"
            )
        
        scope = analysis.computation_scope or ComputationScope.PER_GROUP
        
        if scope == ComputationScope.PER_GROUP:
            # Rank within each group
            if time_dimensions:
                # Rank within each time period
                return ImplementationDecision(
                    impl_type=ImplementationType.TABLE_CALC,
                    addressing=list(non_time_dimensions) if non_time_dimensions else [tech_dimensions[0]],
                    partitioning=list(time_dimensions),
                    reasoning="Multi-dimension per_group ranking: rank within time periods"
                )
            else:
                return ImplementationDecision(
                    impl_type=ImplementationType.TABLE_CALC,
                    addressing=[tech_dimensions[-1]],
                    partitioning=list(tech_dimensions[:-1]),
                    reasoning="Multi-dimension per_group ranking: rank within groups"
                )
        else:
            return ImplementationDecision(
                impl_type=ImplementationType.TABLE_CALC,
                addressing=list(tech_dimensions),
                reasoning="Multi-dimension across_all ranking"
            )
    
    def _resolve_percentage(
        self,
        analysis: AnalysisSpec,
        tech_dimensions: List[DimensionInfo],
        time_dimensions: List[DimensionInfo],
        non_time_dimensions: List[DimensionInfo],
    ) -> ImplementationDecision:
        """
        Resolve percentage analysis.
        
        Rules:
        - per_group: percentage within each group (PERCENT_OF_TOTAL with partitioning)
        - across_all: percentage of grand total
        """
        dim_count = len(tech_dimensions)
        
        if dim_count == 0:
            return ImplementationDecision(
                impl_type=ImplementationType.SIMPLE_AGG,
                reasoning="No dimensions for percentage"
            )
        
        if dim_count == 1:
            return ImplementationDecision(
                impl_type=ImplementationType.TABLE_CALC,
                addressing=list(tech_dimensions),
                reasoning="Single dimension percentage"
            )
        
        scope = analysis.computation_scope or ComputationScope.PER_GROUP
        
        if scope == ComputationScope.PER_GROUP:
            # Percentage within each group
            if time_dimensions:
                return ImplementationDecision(
                    impl_type=ImplementationType.TABLE_CALC,
                    addressing=list(non_time_dimensions) if non_time_dimensions else [tech_dimensions[0]],
                    partitioning=list(time_dimensions),
                    reasoning="Multi-dimension per_group percentage: within time periods"
                )
            else:
                return ImplementationDecision(
                    impl_type=ImplementationType.TABLE_CALC,
                    addressing=[tech_dimensions[-1]],
                    partitioning=list(tech_dimensions[:-1]),
                    reasoning="Multi-dimension per_group percentage: within groups"
                )
        else:
            return ImplementationDecision(
                impl_type=ImplementationType.TABLE_CALC,
                addressing=list(tech_dimensions),
                reasoning="Multi-dimension across_all percentage"
            )
    
    def _resolve_moving(
        self,
        analysis: AnalysisSpec,
        tech_dimensions: List[DimensionInfo],
        time_dimensions: List[DimensionInfo],
        non_time_dimensions: List[DimensionInfo],
    ) -> ImplementationDecision:
        """
        Resolve moving calculation analysis.
        
        Rules:
        - Moving calculations typically address by time dimension
        - Partition by non-time dimensions for per_group
        """
        dim_count = len(tech_dimensions)
        
        if dim_count == 0:
            return ImplementationDecision(
                impl_type=ImplementationType.SIMPLE_AGG,
                reasoning="No dimensions for moving calculation"
            )
        
        # Moving calculations prefer time dimensions for addressing
        if time_dimensions:
            addressing = list(time_dimensions)
            partitioning = list(non_time_dimensions)
        else:
            addressing = [tech_dimensions[0]]
            partitioning = list(tech_dimensions[1:]) if len(tech_dimensions) > 1 else []
        
        scope = analysis.computation_scope or ComputationScope.PER_GROUP
        
        if scope == ComputationScope.ACROSS_ALL:
            # No partitioning for across_all
            partitioning = []
        
        return ImplementationDecision(
            impl_type=ImplementationType.TABLE_CALC,
            addressing=addressing,
            partitioning=partitioning,
            reasoning=f"Moving calculation: addressing by {'time' if time_dimensions else 'first'} dimension"
        )
    
    def _resolve_period_compare(
        self,
        analysis: AnalysisSpec,
        tech_dimensions: List[DimensionInfo],
        time_dimensions: List[DimensionInfo],
        non_time_dimensions: List[DimensionInfo],
    ) -> ImplementationDecision:
        """
        Resolve period comparison analysis.
        
        Rules:
        - Period comparisons require time dimension
        - Use DIFFERENCE_FROM or PERCENT_DIFFERENCE_FROM table calc
        """
        if not time_dimensions:
            logger.warning("Period comparison without time dimension")
            return ImplementationDecision(
                impl_type=ImplementationType.SIMPLE_AGG,
                reasoning="Period comparison requires time dimension"
            )
        
        return ImplementationDecision(
            impl_type=ImplementationType.TABLE_CALC,
            addressing=list(time_dimensions),
            partitioning=list(non_time_dimensions),
            reasoning="Period comparison: addressing by time dimension"
        )
    
    def _resolve_default(
        self,
        analysis: AnalysisSpec,
        tech_dimensions: List[DimensionInfo],
        time_dimensions: List[DimensionInfo],
        non_time_dimensions: List[DimensionInfo],
    ) -> ImplementationDecision:
        """Default resolution for unknown analysis types."""
        if not tech_dimensions:
            return ImplementationDecision(
                impl_type=ImplementationType.SIMPLE_AGG,
                reasoning="No dimensions, using simple aggregation"
            )
        
        return ImplementationDecision(
            impl_type=ImplementationType.TABLE_CALC,
            addressing=list(tech_dimensions),
            reasoning=f"Default resolution for {analysis.type}"
        )
