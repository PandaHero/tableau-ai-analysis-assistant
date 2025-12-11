"""
Expression Generator

Generates VizQL expressions (table calculations and LOD) from
implementation decisions.

Architecture:
- Template-based generation for 100% syntax correctness
- Supports all table calculation types
- Supports LOD expressions (FIXED, INCLUDE, EXCLUDE)

Requirements:
- R7.2.12: Table calculation templates
- R7.2.13: LOD templates
- R7.2.14: 100% syntax correctness
"""

import logging
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass

from tableau_assistant.src.models.semantic.enums import (
    AnalysisType,
    AggregationType,
)
from tableau_assistant.src.models.vizql.types import (
    FunctionEnum,
    TableCalcFieldReference,
    RunningTotalTableCalcSpecification,
    MovingTableCalcSpecification,
    RankTableCalcSpecification,
    PercentOfTotalTableCalcSpecification,
    DifferenceFromTableCalcSpecification,
    PercentDifferenceFromTableCalcSpecification,
    CustomTableCalcSpecification,
    TableCalcComputedAggregation,
    SortDirection,
)
from .implementation_resolver import ImplementationDecision, ImplementationType, DimensionInfo

logger = logging.getLogger(__name__)


# Mapping from semantic aggregation to VizQL function
AGG_TO_FUNCTION: Dict[AggregationType, FunctionEnum] = {
    AggregationType.SUM: FunctionEnum.SUM,
    AggregationType.AVG: FunctionEnum.AVG,
    AggregationType.COUNT: FunctionEnum.COUNT,
    AggregationType.COUNTD: FunctionEnum.COUNTD,
    AggregationType.MIN: FunctionEnum.MIN,
    AggregationType.MAX: FunctionEnum.MAX,
}

# Mapping from semantic aggregation to table calc aggregation
AGG_TO_TABLE_CALC: Dict[AggregationType, TableCalcComputedAggregation] = {
    AggregationType.SUM: TableCalcComputedAggregation.SUM,
    AggregationType.AVG: TableCalcComputedAggregation.AVG,
    AggregationType.MIN: TableCalcComputedAggregation.MIN,
    AggregationType.MAX: TableCalcComputedAggregation.MAX,
}


@dataclass
class GeneratedExpression:
    """
    Generated VizQL expression result
    
    Contains:
    - calculation: The calculation formula (for LOD or custom)
    - table_calc_spec: Table calculation specification (for table calcs)
    - function: Aggregation function to apply
    - field_alias: Suggested alias for the field
    """
    calculation: Optional[str] = None
    table_calc_spec: Optional[Any] = None
    function: Optional[FunctionEnum] = None
    field_alias: Optional[str] = None


class ExpressionGenerator:
    """
    Generates VizQL expressions from implementation decisions.
    
    Supports:
    - Table calculations: RUNNING_SUM, RANK, WINDOW_AVG, etc.
    - LOD expressions: {FIXED ...}, {INCLUDE ...}, {EXCLUDE ...}
    
    All expressions are generated from templates to ensure
    100% syntax correctness.
    """
    
    def generate(
        self,
        analysis_type: AnalysisType,
        decision: ImplementationDecision,
        target_field: str,
        aggregation: AggregationType = AggregationType.SUM,
        **kwargs,
    ) -> GeneratedExpression:
        """
        Generate VizQL expression for an analysis.
        
        Args:
            analysis_type: Type of analysis
            decision: Implementation decision from resolver
            target_field: Technical field name for the measure
            aggregation: Aggregation type
            **kwargs: Additional parameters (window_size, order, compare_type, etc.)
            
        Returns:
            GeneratedExpression with calculation or table_calc_spec
        """
        logger.debug(f"Generating expression for {analysis_type} with {decision.impl_type}")
        
        if decision.impl_type == ImplementationType.SIMPLE_AGG:
            return self._generate_simple_agg(target_field, aggregation)
        
        if decision.impl_type in (
            ImplementationType.LOD_FIXED,
            ImplementationType.LOD_INCLUDE,
            ImplementationType.LOD_EXCLUDE,
        ):
            return self._generate_lod(
                decision.impl_type,
                target_field,
                aggregation,
                decision.lod_dimensions,
            )
        
        # Table calculation
        if analysis_type == AnalysisType.CUMULATIVE:
            return self._generate_running_total(
                target_field, aggregation, decision.addressing
            )
        elif analysis_type == AnalysisType.RANKING:
            return self._generate_rank(
                target_field, decision.addressing,
                kwargs.get("order", "desc")
            )
        elif analysis_type == AnalysisType.PERCENTAGE:
            return self._generate_percent_of_total(
                target_field, aggregation, decision.addressing
            )
        elif analysis_type == AnalysisType.MOVING:
            return self._generate_moving(
                target_field, aggregation, decision.addressing,
                kwargs.get("window_size", 3)
            )
        elif analysis_type == AnalysisType.PERIOD_COMPARE:
            return self._generate_period_compare(
                target_field, aggregation, decision.addressing,
                kwargs.get("compare_period", "previous")
            )
        else:
            # Default to custom table calc
            return self._generate_custom(
                target_field, aggregation, decision.addressing
            )
    
    def _generate_simple_agg(
        self,
        target_field: str,
        aggregation: AggregationType,
    ) -> GeneratedExpression:
        """Generate simple aggregation (no table calc)."""
        return GeneratedExpression(
            function=AGG_TO_FUNCTION.get(aggregation, FunctionEnum.SUM),
            field_alias=f"{aggregation.value}_{target_field}",
        )
    
    def _generate_lod(
        self,
        lod_type: ImplementationType,
        target_field: str,
        aggregation: AggregationType,
        dimensions: List[str],
    ) -> GeneratedExpression:
        """
        Generate LOD expression.
        
        Templates:
        - FIXED: {FIXED [dim1], [dim2] : AGG([field])}
        - INCLUDE: {INCLUDE [dim1] : AGG([field])}
        - EXCLUDE: {EXCLUDE [dim1] : AGG([field])}
        """
        agg_func = aggregation.value.upper()
        dim_list = ", ".join(f"[{d}]" for d in dimensions) if dimensions else ""
        
        if lod_type == ImplementationType.LOD_FIXED:
            if dim_list:
                calc = f"{{FIXED {dim_list} : {agg_func}([{target_field}])}}"
            else:
                calc = f"{{FIXED : {agg_func}([{target_field}])}}"
        elif lod_type == ImplementationType.LOD_INCLUDE:
            calc = f"{{INCLUDE {dim_list} : {agg_func}([{target_field}])}}"
        else:  # LOD_EXCLUDE
            calc = f"{{EXCLUDE {dim_list} : {agg_func}([{target_field}])}}"
        
        return GeneratedExpression(
            calculation=calc,
            field_alias=f"lod_{target_field}",
        )
    
    def _generate_running_total(
        self,
        target_field: str,
        aggregation: AggregationType,
        addressing: List[DimensionInfo],
    ) -> GeneratedExpression:
        """
        Generate running total table calculation.
        
        VizQL: RUNNING_SUM(SUM([Sales]))
        """
        # Create dimension references for addressing with function info
        dimensions = [
            TableCalcFieldReference(
                fieldCaption=dim.field_name,
                function=FunctionEnum(dim.function) if dim.function else None
            )
            for dim in addressing
        ]
        
        table_calc = RunningTotalTableCalcSpecification(
            tableCalcType="RUNNING_TOTAL",
            dimensions=dimensions,
            aggregation=AGG_TO_TABLE_CALC.get(aggregation, TableCalcComputedAggregation.SUM),
        )
        
        return GeneratedExpression(
            table_calc_spec=table_calc,
            function=AGG_TO_FUNCTION.get(aggregation, FunctionEnum.SUM),
            field_alias=f"cumulative_{target_field}",
        )
    
    def _generate_rank(
        self,
        target_field: str,
        addressing: List[DimensionInfo],
        direction: str = "desc",
    ) -> GeneratedExpression:
        """
        Generate rank table calculation.
        
        VizQL: RANK(SUM([Sales]))
        """
        dimensions = [
            TableCalcFieldReference(
                fieldCaption=dim.field_name,
                function=FunctionEnum(dim.function) if dim.function else None
            )
            for dim in addressing
        ]
        
        sort_dir = SortDirection.DESC if direction == "desc" else SortDirection.ASC
        
        table_calc = RankTableCalcSpecification(
            tableCalcType="RANK",
            dimensions=dimensions,
            rankType="COMPETITION",
            direction=sort_dir,
        )
        
        return GeneratedExpression(
            table_calc_spec=table_calc,
            function=FunctionEnum.SUM,
            field_alias=f"rank_{target_field}",
        )
    
    def _generate_percent_of_total(
        self,
        target_field: str,
        aggregation: AggregationType,
        addressing: List[DimensionInfo],
    ) -> GeneratedExpression:
        """
        Generate percent of total table calculation.
        
        VizQL: SUM([Sales]) / TOTAL(SUM([Sales]))
        """
        dimensions = [
            TableCalcFieldReference(
                fieldCaption=dim.field_name,
                function=FunctionEnum(dim.function) if dim.function else None
            )
            for dim in addressing
        ]
        
        table_calc = PercentOfTotalTableCalcSpecification(
            tableCalcType="PERCENT_OF_TOTAL",
            dimensions=dimensions,
        )
        
        return GeneratedExpression(
            table_calc_spec=table_calc,
            function=AGG_TO_FUNCTION.get(aggregation, FunctionEnum.SUM),
            field_alias=f"pct_{target_field}",
        )
    
    def _generate_moving(
        self,
        target_field: str,
        aggregation: AggregationType,
        addressing: List[DimensionInfo],
        window_size: int = 3,
    ) -> GeneratedExpression:
        """
        Generate moving calculation.
        
        VizQL: WINDOW_AVG(SUM([Sales]), -2, 0)
        """
        dimensions = [
            TableCalcFieldReference(
                fieldCaption=dim.field_name,
                function=FunctionEnum(dim.function) if dim.function else None
            )
            for dim in addressing
        ]
        
        # Window: previous (window_size - 1) + current
        previous = window_size - 1
        
        table_calc = MovingTableCalcSpecification(
            tableCalcType="MOVING_CALCULATION",
            dimensions=dimensions,
            aggregation=AGG_TO_TABLE_CALC.get(aggregation, TableCalcComputedAggregation.AVG),
            previous=previous,
            next=0,
            includeCurrent=True,
        )
        
        return GeneratedExpression(
            table_calc_spec=table_calc,
            function=AGG_TO_FUNCTION.get(aggregation, FunctionEnum.SUM),
            field_alias=f"moving_{window_size}_{target_field}",
        )
    
    def _generate_period_compare(
        self,
        target_field: str,
        aggregation: AggregationType,
        addressing: List[DimensionInfo],
        compare_period: str = "previous",
    ) -> GeneratedExpression:
        """
        Generate period comparison calculation.
        
        VizQL: (SUM([Sales]) - LOOKUP(SUM([Sales]), -1)) / ABS(LOOKUP(SUM([Sales]), -1))
        """
        dimensions = [
            TableCalcFieldReference(
                fieldCaption=dim.field_name,
                function=FunctionEnum(dim.function) if dim.function else None
            )
            for dim in addressing
        ]
        
        # Map compare_period to relativeTo
        relative_to_map = {
            "previous": "PREVIOUS",
            "previous_year": "PREVIOUS",
            "previous_month": "PREVIOUS",
            "first": "FIRST",
            "last": "LAST",
        }
        relative_to = relative_to_map.get(compare_period, "PREVIOUS")
        
        table_calc = PercentDifferenceFromTableCalcSpecification(
            tableCalcType="PERCENT_DIFFERENCE_FROM",
            dimensions=dimensions,
            relativeTo=relative_to,
        )
        
        return GeneratedExpression(
            table_calc_spec=table_calc,
            function=AGG_TO_FUNCTION.get(aggregation, FunctionEnum.SUM),
            field_alias=f"pct_diff_{target_field}",
        )
    
    def _generate_custom(
        self,
        target_field: str,
        aggregation: AggregationType,
        addressing: List[DimensionInfo],
    ) -> GeneratedExpression:
        """Generate custom table calculation."""
        dimensions = [
            TableCalcFieldReference(
                fieldCaption=dim.field_name,
                function=FunctionEnum(dim.function) if dim.function else None
            )
            for dim in addressing
        ]
        
        table_calc = CustomTableCalcSpecification(
            tableCalcType="CUSTOM",
            dimensions=dimensions,
        )
        
        return GeneratedExpression(
            table_calc_spec=table_calc,
            function=AGG_TO_FUNCTION.get(aggregation, FunctionEnum.SUM),
            field_alias=f"calc_{target_field}",
        )
