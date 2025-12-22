"""Tableau Query Builder - Converts SemanticQuery to VizQL API request.

This is the core translation layer from platform-agnostic SemanticQuery
to Tableau-specific VizQL API format.

Key translations:
- Computation.partition_by → Table Calculation dimensions (partitioning)
- OperationType → TableCalcType
- Filter types → VizQL filter types
"""

import logging
from typing import Any

from ...core.interfaces import BaseQueryBuilder
from ...core.models import (
    AggregationType,
    Computation,
    DateRangeFilter,
    DateRangeType,
    DimensionField,
    FilterType,
    MeasureField,
    NumericRangeFilter,
    OperationType,
    SemanticQuery,
    SetFilter,
    Sort,
    TextMatchFilter,
    TopNFilter,
    ValidationError,
    ValidationErrorType,
    ValidationResult,
)
from .models import (
    DifferenceTableCalcSpecification,
    LODExpression,
    LODType,
    MovingTableCalcSpecification,
    PercentDifferenceTableCalcSpecification,
    PercentOfTotalTableCalcSpecification,
    RankTableCalcSpecification,
    RankType,
    RelativeTo,
    RunningTotalTableCalcSpecification,
    TableCalcAggregation,
    TableCalcField,
    TableCalcFieldReference,
    VizQLFunction,
    VizQLSortDirection,
    determine_lod_type,
)

logger = logging.getLogger(__name__)


# Mapping from core AggregationType to VizQL Function
AGGREGATION_TO_VIZQL: dict[AggregationType, VizQLFunction] = {
    AggregationType.SUM: VizQLFunction.SUM,
    AggregationType.AVG: VizQLFunction.AVG,
    AggregationType.COUNT: VizQLFunction.COUNT,
    AggregationType.COUNT_DISTINCT: VizQLFunction.COUNTD,
    AggregationType.MIN: VizQLFunction.MIN,
    AggregationType.MAX: VizQLFunction.MAX,
    AggregationType.MEDIAN: VizQLFunction.MEDIAN,
    AggregationType.STDEV: VizQLFunction.STDEV,
    AggregationType.VAR: VizQLFunction.VAR,
}


class TableauQueryBuilder(BaseQueryBuilder):
    """Tableau query builder - converts SemanticQuery to VizQL request."""
    
    def build(self, semantic_query: SemanticQuery, **kwargs: Any) -> dict:
        """Build VizQL API request from SemanticQuery.
        
        Args:
            semantic_query: Platform-agnostic semantic query
            **kwargs: Additional parameters (e.g., datasource_id)
            
        Returns:
            VizQL API request dictionary
        """
        fields = []
        
        # Build dimension fields
        if semantic_query.dimensions:
            for dim in semantic_query.dimensions:
                fields.append(self._build_dimension_field(dim))
        
        # Build measure fields
        if semantic_query.measures:
            for measure in semantic_query.measures:
                fields.append(self._build_measure_field(measure))
        
        # Build computation fields (table calculations or LOD)
        if semantic_query.computations:
            view_dims = [d.field_name for d in (semantic_query.dimensions or [])]
            for comp in semantic_query.computations:
                comp_field = self._build_computation_field(comp, view_dims)
                fields.append(comp_field)
        
        # Build filters
        filters = []
        if semantic_query.filters:
            for f in semantic_query.filters:
                vizql_filter = self._build_filter(f)
                if vizql_filter:
                    filters.append(vizql_filter)
        
        # Build request
        request = {
            "fields": fields,
        }
        
        if filters:
            request["filters"] = filters
        
        if semantic_query.row_limit:
            request["rowLimit"] = semantic_query.row_limit
        
        # Add datasource if provided
        datasource_id = kwargs.get("datasource_id")
        if datasource_id:
            request["datasource"] = {"datasourceId": datasource_id}
        
        return request
    
    def validate(self, semantic_query: SemanticQuery, **kwargs: Any) -> ValidationResult:
        """Validate SemanticQuery for Tableau platform.
        
        Args:
            semantic_query: Query to validate
            **kwargs: Additional parameters
            
        Returns:
            ValidationResult with errors, warnings, and auto-fixes
        """
        errors = []
        warnings = []
        auto_fixed = []
        
        # Check for empty query
        if not semantic_query.dimensions and not semantic_query.measures:
            errors.append(ValidationError(
                error_type=ValidationErrorType.MISSING_REQUIRED,
                field_path="dimensions/measures",
                message="Query must have at least one dimension or measure",
            ))
        
        # Validate computations
        if semantic_query.computations:
            view_dims = set(d.field_name for d in (semantic_query.dimensions or []))
            measures = set(m.field_name for m in (semantic_query.measures or []))
            
            for i, comp in enumerate(semantic_query.computations):
                # Check target is in measures
                if comp.target not in measures:
                    errors.append(ValidationError(
                        error_type=ValidationErrorType.INVALID_REFERENCE,
                        field_path=f"computations[{i}].target",
                        message=f"Target '{comp.target}' not in measures",
                        suggestion=f"Add '{comp.target}' to measures or use existing measure",
                    ))
                
                # Check partition_by is subset of dimensions
                for p in comp.partition_by:
                    if p not in view_dims:
                        errors.append(ValidationError(
                            error_type=ValidationErrorType.INVALID_REFERENCE,
                            field_path=f"computations[{i}].partition_by",
                            message=f"Partition dimension '{p}' not in query dimensions",
                            suggestion=f"Add '{p}' to dimensions or remove from partition_by",
                        ))
        
        # Auto-fix: fill default aggregation for measures without one
        if semantic_query.measures:
            for measure in semantic_query.measures:
                if measure.aggregation is None:
                    measure.aggregation = AggregationType.SUM
                    auto_fixed.append(f"Set default aggregation SUM for {measure.field_name}")
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors if errors else None,
            warnings=warnings if warnings else None,
            auto_fixed=auto_fixed if auto_fixed else None,
        )
    
    def _build_dimension_field(self, dim: DimensionField) -> dict:
        """Build VizQL dimension field."""
        field = {
            "fieldCaption": dim.field_name,
        }
        
        if dim.alias:
            field["fieldAlias"] = dim.alias
        
        # TODO: Handle date granularity (DATEPART)
        
        return field
    
    def _build_measure_field(self, measure: MeasureField) -> dict:
        """Build VizQL measure field."""
        vizql_func = AGGREGATION_TO_VIZQL.get(measure.aggregation, VizQLFunction.SUM)
        
        field = {
            "fieldCaption": measure.field_name,
            "function": vizql_func.value,
        }
        
        if measure.alias:
            field["fieldAlias"] = measure.alias
        
        return field
    
    def _build_computation_field(
        self,
        comp: Computation,
        view_dimensions: list[str],
    ) -> dict:
        """Build VizQL computation field (table calc or LOD).
        
        Args:
            comp: Computation from SemanticQuery
            view_dimensions: Dimensions in the view
            
        Returns:
            VizQL field dictionary
        """
        op_type = comp.operation.type
        
        # Check if this should be LOD or Table Calc
        if op_type == OperationType.FIXED:
            return self._build_lod_field(comp, view_dimensions)
        
        # Build table calculation
        return self._build_table_calc_field(comp, view_dimensions)
    
    def _build_table_calc_field(
        self,
        comp: Computation,
        view_dimensions: list[str],
    ) -> dict:
        """Build VizQL table calculation field.
        
        Note: According to VizQL API schema, TableCalcField requires 'tableCalculation'
        and optionally allows 'function' or 'calculation', but not both.
        The 'function' in TableCalcField is for the base measure aggregation.
        """
        op_type = comp.operation.type
        params = comp.operation.params
        
        # Build partitioning dimensions
        partition_dims = [
            {"fieldCaption": d} for d in comp.partition_by
        ]
        
        # Build table calc specification based on operation type
        table_calc: dict
        
        if op_type in (OperationType.RANK, OperationType.DENSE_RANK):
            rank_type = "DENSE" if op_type == OperationType.DENSE_RANK else "COMPETITION"
            table_calc = {
                "tableCalcType": "RANK",
                "dimensions": partition_dims,
                "rankType": rank_type,
                "direction": params.get("direction", "DESC"),
            }
        
        elif op_type == OperationType.RUNNING_SUM:
            table_calc = {
                "tableCalcType": "RUNNING_TOTAL",
                "dimensions": partition_dims,
                "aggregation": "SUM",
            }
        
        elif op_type == OperationType.RUNNING_AVG:
            table_calc = {
                "tableCalcType": "RUNNING_TOTAL",
                "dimensions": partition_dims,
                "aggregation": "AVG",
            }
        
        elif op_type == OperationType.MOVING_AVG:
            window = params.get("window_size", 3)
            table_calc = {
                "tableCalcType": "MOVING_CALCULATION",
                "dimensions": partition_dims,
                "aggregation": "AVG",
                "previous": window - 1,
                "next": 0,
                "includeCurrent": True,
            }
        
        elif op_type == OperationType.MOVING_SUM:
            window = params.get("window_size", 3)
            table_calc = {
                "tableCalcType": "MOVING_CALCULATION",
                "dimensions": partition_dims,
                "aggregation": "SUM",
                "previous": window - 1,
                "next": 0,
                "includeCurrent": True,
            }
        
        elif op_type == OperationType.PERCENT:
            table_calc = {
                "tableCalcType": "PERCENT_OF_TOTAL",
                "dimensions": partition_dims,
            }
        
        elif op_type == OperationType.DIFFERENCE:
            table_calc = {
                "tableCalcType": "DIFFERENCE_FROM",
                "dimensions": partition_dims,
                "relativeTo": params.get("relative_to", "PREVIOUS"),
            }
        
        elif op_type == OperationType.GROWTH_RATE:
            table_calc = {
                "tableCalcType": "PERCENT_DIFFERENCE_FROM",
                "dimensions": partition_dims,
                "relativeTo": params.get("relative_to", "PREVIOUS"),
            }
        
        elif op_type in (OperationType.YEAR_AGO, OperationType.PERIOD_AGO):
            # Period comparison - use DIFFERENCE_FROM with offset
            n = params.get("n", 1)
            table_calc = {
                "tableCalcType": "DIFFERENCE_FROM",
                "dimensions": partition_dims,
                "relativeTo": "PREVIOUS",
                # Note: VizQL doesn't directly support N periods ago
                # This may need custom calculation
            }
        
        else:
            # Default to custom calculation
            table_calc = {
                "tableCalcType": "CUSTOM",
                "dimensions": partition_dims,
            }
        
        # Build the field - TableCalcField only needs fieldCaption and tableCalculation
        # Do NOT include 'function' here as it conflicts with tableCalculation in VizQL schema
        field = {
            "fieldCaption": comp.target,
            "tableCalculation": table_calc,
        }
        
        if comp.alias:
            field["fieldAlias"] = comp.alias
        
        return field
    
    def _build_lod_field(
        self,
        comp: Computation,
        view_dimensions: list[str],
    ) -> dict:
        """Build VizQL LOD expression field."""
        lod_type, lod_dims = determine_lod_type(comp.partition_by, view_dimensions)
        
        lod = LODExpression(
            lod_type=lod_type,
            dimensions=lod_dims,
            measure=comp.target,
            aggregation=VizQLFunction.SUM,
            alias=comp.alias,
        )
        
        # Build as calculated field
        field = {
            "fieldCaption": comp.alias or f"LOD_{comp.target}",
            "calculation": lod.to_calculation(),
        }
        
        return field
    
    def _build_filter(self, f: Any) -> dict | None:
        """Build VizQL filter from core filter model.
        
        VizQL API Filter schema requires:
        - field: FilterField object with fieldCaption (required)
        - filterType: string enum (required)
        - Additional properties based on filterType
        
        See openapi.json Filter schema for details.
        """
        if isinstance(f, SetFilter):
            return {
                "field": {"fieldCaption": f.field_name},
                "filterType": "SET",
                "values": f.values,
                "exclude": f.exclude,
            }
        
        elif isinstance(f, DateRangeFilter):
            if f.range_type == DateRangeType.CUSTOM:
                # Absolute date range
                filter_dict = {
                    "field": {"fieldCaption": f.field_name},
                    "filterType": "QUANTITATIVE_DATE",
                    "quantitativeFilterType": "RANGE",
                }
                if f.start_date:
                    filter_dict["min"] = f.start_date.isoformat() if hasattr(f.start_date, 'isoformat') else str(f.start_date)
                if f.end_date:
                    filter_dict["max"] = f.end_date.isoformat() if hasattr(f.end_date, 'isoformat') else str(f.end_date)
                return filter_dict
            else:
                # Relative date range
                return {
                    "field": {"fieldCaption": f.field_name},
                    "filterType": "DATE",
                    "anchor": f.range_type.value,
                    "periodType": f.granularity.value if f.granularity else "DAY",
                    "rangeN": f.n,
                }
        
        elif isinstance(f, NumericRangeFilter):
            filter_dict = {
                "field": {"fieldCaption": f.field_name},
                "filterType": "QUANTITATIVE_NUMERICAL",
                "quantitativeFilterType": "RANGE",
            }
            if f.min_value is not None:
                filter_dict["min"] = f.min_value
            if f.max_value is not None:
                filter_dict["max"] = f.max_value
            return filter_dict
        
        elif isinstance(f, TextMatchFilter):
            return {
                "field": {"fieldCaption": f.field_name},
                "filterType": "MATCH",
                "contains": f.pattern if f.match_type.value == "CONTAINS" else None,
                "startsWith": f.pattern if f.match_type.value == "STARTS_WITH" else None,
                "endsWith": f.pattern if f.match_type.value == "ENDS_WITH" else None,
                "exactMatch": f.pattern if f.match_type.value == "EXACT" else None,
            }
        
        elif isinstance(f, TopNFilter):
            return {
                "field": {"fieldCaption": f.field_name},
                "filterType": "TOP",
                "howMany": f.n,
                "fieldToMeasure": {"fieldCaption": f.by_field},
                "direction": f.direction.value,
            }
        
        logger.warning(f"Unknown filter type: {type(f)}")
        return None
