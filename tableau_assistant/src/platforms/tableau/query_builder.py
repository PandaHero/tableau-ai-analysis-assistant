"""Tableau Query Builder - Converts SemanticQuery to VizQL API request.

This is the core translation layer from platform-agnostic SemanticQuery
to Tableau-specific VizQL API format.

Key translations:
- Computation.partition_by → Table Calculation dimensions (partitioning)
- CalcType → TableCalcType
- CalcParams → VizQL specific parameters
- Filter types → VizQL filter types
"""

import logging
from typing import Any

from ...core.interfaces import BaseQueryBuilder
from ...core.models import (
    AggregationType,
    Computation,
    DateRangeFilter,
    DimensionField,
    FilterType,
    MeasureField,
    NumericRangeFilter,
    RankStyle,
    RelativeTo,
    SemanticQuery,
    SetFilter,
    SortDirection,
    TextMatchFilter,
    TopNFilter,
    ValidationError,
    ValidationErrorType,
    ValidationResult,
    DateGranularity,
    WindowAggregation,
)
from .models import (
    LODExpression,
    LODType,
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
    AggregationType.COUNTD: VizQLFunction.COUNTD,
    AggregationType.MIN: VizQLFunction.MIN,
    AggregationType.MAX: VizQLFunction.MAX,
    AggregationType.MEDIAN: VizQLFunction.MEDIAN,
    AggregationType.STDEV: VizQLFunction.STDEV,
    AggregationType.VAR: VizQLFunction.VAR,
}


class TableauQueryBuilder(BaseQueryBuilder):
    """Tableau query builder - converts SemanticQuery to VizQL request.
    
    Tableau-specific default values are defined here, not in CalcParams.
    This keeps CalcParams platform-agnostic.
    """
    
    # Tableau-specific default values
    DEFAULT_RANK_STYLE = RankStyle.COMPETITION
    DEFAULT_DIRECTION = SortDirection.DESC
    DEFAULT_RELATIVE_TO = RelativeTo.PREVIOUS
    DEFAULT_AGGREGATION = WindowAggregation.SUM
    DEFAULT_WINDOW_PREVIOUS = 2
    DEFAULT_WINDOW_NEXT = 0
    DEFAULT_INCLUDE_CURRENT = True
    
    def build(self, semantic_query: SemanticQuery, **kwargs: Any) -> dict:
        """Build VizQL API request from SemanticQuery.
        
        Args:
            semantic_query: Platform-agnostic semantic query
            **kwargs: Additional parameters:
                - datasource_id: Datasource LUID
                - field_metadata: dict[str, dict] mapping field names to metadata
                  (used for determining field dataType for date handling)
            
        Returns:
            VizQL API request dictionary
        """
        field_metadata = kwargs.get("field_metadata", {})
        fields = []
        
        # Build dimension fields
        if semantic_query.dimensions:
            for dim in semantic_query.dimensions:
                fields.append(self._build_dimension_field(dim, field_metadata))
        
        # Build measure fields
        if semantic_query.measures:
            for measure in semantic_query.measures:
                fields.append(self._build_measure_field(measure))
        
        # Build computation fields (table calculations or LOD)
        # Important: LOD fields must come before table calc fields
        if semantic_query.computations:
            view_dims = [d.field_name for d in (semantic_query.dimensions or [])]
            comp_fields = self._build_computation_fields(
                semantic_query.computations, 
                view_dims,
                measures=semantic_query.measures,
            )
            fields.extend(comp_fields)
        
        # Build filters
        filters = []
        if semantic_query.filters:
            for f in semantic_query.filters:
                vizql_filter = self._build_filter(f, field_metadata)
                if vizql_filter:
                    filters.append(vizql_filter)
        
        # Build Top N filters from computations with top_n parameter
        if semantic_query.computations:
            for comp in semantic_query.computations:
                # Check for RANK or DENSE_RANK with top_n attribute
                if comp.calc_type in ("RANK", "DENSE_RANK") and getattr(comp, 'top_n', None):
                    top_n_filter = self._build_top_n_filter_from_computation(comp, semantic_query)
                    if top_n_filter:
                        filters.append(top_n_filter)
        
        # Build request
        request = {
            "fields": fields,
        }
        
        if filters:
            request["filters"] = filters
        
        # Build sorts - 排序嵌入在字段的 sort 属性中，使用 get_sorts() 获取
        sorts_list = semantic_query.get_sorts()
        if sorts_list:
            sorts = self._build_sorts_from_tuples(sorts_list)
            if sorts:
                request["sorts"] = sorts
        
        if semantic_query.row_limit:
            request["rowLimit"] = semantic_query.row_limit
        
        # Add datasource if provided
        datasource_id = kwargs.get("datasource_id")
        if datasource_id:
            request["datasource"] = {"datasourceId": datasource_id}
        
        return request
    
    def validate(self, semantic_query: SemanticQuery, **kwargs: Any) -> ValidationResult:
        """Validate SemanticQuery for Tableau platform."""
        errors = []
        warnings = []
        auto_fixed = []
        
        # LOD calc_type values (as strings)
        lod_calc_types = {"LOD_FIXED", "LOD_INCLUDE", "LOD_EXCLUDE"}
        
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
                # Check target is in measures (for non-LOD) or valid field
                if comp.calc_type not in lod_calc_types and comp.target not in measures:
                    errors.append(ValidationError(
                        error_type=ValidationErrorType.FIELD_NOT_FOUND,
                        field_path=f"computations[{i}].target",
                        message=f"Target '{comp.target}' not in measures",
                        suggestion=f"Add '{comp.target}' to measures or use existing measure",
                    ))
                
                # Check partition_by is subset of dimensions
                # partition_by is now list[DimensionField], extract field_name from each
                for p in comp.partition_by:
                    p_field_name = p.field_name if hasattr(p, 'field_name') else p
                    if p_field_name not in view_dims:
                        errors.append(ValidationError(
                            error_type=ValidationErrorType.FIELD_NOT_FOUND,
                            field_path=f"computations[{i}].partition_by",
                            message=f"Partition dimension '{p_field_name}' not in query dimensions",
                            suggestion=f"Add '{p_field_name}' to dimensions or remove from partition_by",
                        ))
        
        # Auto-fix: fill default aggregation for measures without one
        if semantic_query.measures:
            for measure in semantic_query.measures:
                if measure.aggregation is None:
                    measure.aggregation = AggregationType.SUM
                    auto_fixed.append(f"Set default aggregation SUM for {measure.field_name}")
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            auto_fixed=auto_fixed,
        )
    
    def _build_dimension_field(self, dim: DimensionField, field_metadata: dict[str, dict] | None = None) -> dict:
        """Build VizQL dimension field.
        
        For date fields with granularity:
        - DATE/DATETIME type: use function: "TRUNC_MONTH" etc.
        - STRING type: use calculation: "DATETRUNC('month', DATEPARSE('yyyy-MM-dd', [Field]))"
        """
        field_metadata = field_metadata or {}
        field = {
            "fieldCaption": dim.field_name,
        }
        
        if dim.alias:
            field["fieldAlias"] = dim.alias
        
        # Handle date granularity
        if dim.date_granularity:
            meta = field_metadata.get(dim.field_name, {})
            data_type = meta.get("dataType", "").upper()
            
            # Map granularity to TRUNC function name
            trunc_map = {
                DateGranularity.YEAR: "TRUNC_YEAR",
                DateGranularity.QUARTER: "TRUNC_QUARTER",
                DateGranularity.MONTH: "TRUNC_MONTH",
                DateGranularity.WEEK: "TRUNC_WEEK",
                DateGranularity.DAY: "TRUNC_DAY",
            }
            
            # Map granularity to DATETRUNC parameter
            datetrunc_map = {
                DateGranularity.YEAR: "year",
                DateGranularity.QUARTER: "quarter",
                DateGranularity.MONTH: "month",
                DateGranularity.WEEK: "week",
                DateGranularity.DAY: "day",
            }
            
            if data_type == "STRING":
                # STRING type date field - use DATETRUNC + DATEPARSE calculation
                granularity_str = datetrunc_map.get(dim.date_granularity, "month")
                field["calculation"] = f"DATETRUNC('{granularity_str}', DATEPARSE('yyyy-MM-dd', [{dim.field_name}]))"
            else:
                # DATE/DATETIME type - use TRUNC_* function
                trunc_func = trunc_map.get(dim.date_granularity)
                if trunc_func:
                    field["function"] = trunc_func
        
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
    
    def _build_sorts(self, sorts: list[Sort]) -> list[dict]:
        """Build VizQL sort specifications.
        
        Args:
            sorts: List of Sort objects from SemanticQuery
            
        Returns:
            List of VizQL sort dictionaries
        """
        vizql_sorts = []
        
        # Sort by priority (lower = higher priority)
        sorted_sorts = sorted(sorts, key=lambda s: s.priority)
        
        for sort in sorted_sorts:
            vizql_sort = {
                "field": {"fieldCaption": sort.field_name},
                "sortDirection": sort.direction.value,
            }
            vizql_sorts.append(vizql_sort)
        
        return vizql_sorts
    
    def _build_sorts_from_tuples(self, sorts: list[tuple[str, "SortSpec"]]) -> list[dict]:
        """Build VizQL sort specifications from (field_name, SortSpec) tuples.
        
        Args:
            sorts: List of (field_name, SortSpec) tuples, already sorted by priority
            
        Returns:
            List of VizQL sort dictionaries
        """
        vizql_sorts = []
        
        for field_name, sort_spec in sorts:
            vizql_sort = {
                "field": {"fieldCaption": field_name},
                "sortDirection": sort_spec.direction.value,
            }
            vizql_sorts.append(vizql_sort)
        
        return vizql_sorts
    
    def _build_computation_fields(
        self,
        computations: list[Computation],
        view_dimensions: list[str],
        measures: list[MeasureField] | None = None,
    ) -> list[dict]:
        """Build computation fields list (LOD first, then table calcs).
        
        Important: LOD fields must be generated before table calc fields
        because table calcs may reference LOD results.
        
        Args:
            computations: List of computation objects
            view_dimensions: List of dimension field names in the query
            measures: List of measure fields (for table calc aggregation lookup)
        """
        # LOD calc_type values (as strings, not CalcType enum)
        lod_calc_types = {"LOD_FIXED", "LOD_INCLUDE", "LOD_EXCLUDE"}
        
        # Build measure lookup for aggregation
        measure_agg_map: dict[str, AggregationType] = {}
        if measures:
            for m in measures:
                measure_agg_map[m.field_name] = m.aggregation or AggregationType.SUM
        
        lod_fields = []
        table_calc_fields = []
        
        for comp in computations:
            if comp.calc_type in lod_calc_types:
                lod_fields.append(self._build_lod_field(comp))
            else:
                table_calc_fields.append(
                    self._build_table_calc_field(comp, view_dimensions, measure_agg_map)
                )
        
        # LOD first, then table calcs
        return lod_fields + table_calc_fields
    
    def _build_table_calc_field(
        self,
        comp: Computation,
        view_dimensions: list[str],
        measure_agg_map: dict[str, AggregationType] | None = None,
    ) -> dict:
        """Build VizQL table calculation field.
        
        Note: Computation is a Union type with different subtypes.
        Each subtype has its attributes directly on the object (not via params).
        
        VizQL API requires table calculation fields to have both:
        - function: The aggregation function (SUM, AVG, etc.)
        - tableCalculation: The table calculation specification
        
        Args:
            comp: Computation object
            view_dimensions: List of dimension field names in the query
            measure_agg_map: Mapping from measure field names to their aggregation types
        """
        # Build partitioning dimensions
        # partition_by is now list[DimensionField], need to handle date_granularity
        partition_dims = []
        for p in comp.partition_by:
            if hasattr(p, 'field_name'):
                # It's a DimensionField object
                dim_ref = {"fieldCaption": p.field_name}
                # If has date_granularity, add function to match the query field
                if hasattr(p, 'date_granularity') and p.date_granularity:
                    trunc_map = {
                        DateGranularity.YEAR: "TRUNC_YEAR",
                        DateGranularity.QUARTER: "TRUNC_QUARTER",
                        DateGranularity.MONTH: "TRUNC_MONTH",
                        DateGranularity.WEEK: "TRUNC_WEEK",
                        DateGranularity.DAY: "TRUNC_DAY",
                    }
                    trunc_func = trunc_map.get(p.date_granularity)
                    if trunc_func:
                        dim_ref["function"] = trunc_func
                partition_dims.append(dim_ref)
            else:
                # Backward compatibility: if it's a string, just use fieldCaption
                partition_dims.append({"fieldCaption": p})
        
        # Build table calc specification based on calc_type
        table_calc: dict
        calc_type = comp.calc_type  # This is a Literal string like "RANK", "PERCENT_OF_TOTAL", etc.
        
        if calc_type in ("RANK", "DENSE_RANK"):
            table_calc = self._build_rank_spec(comp, partition_dims)
        
        elif calc_type == "PERCENTILE":
            table_calc = self._build_percentile_spec(comp, partition_dims)
        
        elif calc_type == "RUNNING_TOTAL":
            table_calc = self._build_running_total_spec(comp, partition_dims)
        
        elif calc_type == "MOVING_CALC":
            table_calc = self._build_moving_calc_spec(comp, partition_dims)
        
        elif calc_type == "PERCENT_OF_TOTAL":
            table_calc = self._build_percent_of_total_spec(comp, partition_dims)
        
        elif calc_type == "DIFFERENCE":
            table_calc = self._build_difference_spec(comp, partition_dims)
        
        elif calc_type == "PERCENT_DIFFERENCE":
            table_calc = self._build_percent_difference_spec(comp, partition_dims)
        
        else:
            # Fallback to custom
            table_calc = {
                "tableCalcType": "CUSTOM",
                "dimensions": partition_dims,
            }
        
        # Get aggregation function for the target measure
        # Default to SUM if not found in measure_agg_map
        agg_type = AggregationType.SUM
        if measure_agg_map and comp.target in measure_agg_map:
            agg_type = measure_agg_map[comp.target]
        
        vizql_func = AGGREGATION_TO_VIZQL.get(agg_type, VizQLFunction.SUM)
        
        # Build the field - VizQL API requires both function and tableCalculation
        field = {
            "fieldCaption": comp.target,
            "function": vizql_func.value,
            "tableCalculation": table_calc,
        }
        
        # 安全访问 alias 属性（不是所有 Computation 类型都有 alias）
        alias = getattr(comp, 'alias', None)
        if alias:
            field["fieldAlias"] = alias
        
        return field
    
    def _build_rank_spec(self, comp: Computation, partition_dims: list[dict]) -> dict:
        """Build rank table calculation spec.
        
        Supports both RankCalc and DenseRankCalc types.
        """
        # Determine rank type
        if comp.calc_type == "DENSE_RANK":
            rank_type = "DENSE"
        else:
            # RankCalc has rank_style attribute
            rank_style = getattr(comp, 'rank_style', None) or self.DEFAULT_RANK_STYLE
            rank_type = rank_style.value if hasattr(rank_style, 'value') else str(rank_style)
        
        direction = getattr(comp, 'direction', None) or self.DEFAULT_DIRECTION
        
        return {
            "tableCalcType": "RANK",
            "dimensions": partition_dims,
            "rankType": rank_type,
            "direction": direction.value if hasattr(direction, 'value') else str(direction),
        }
    
    def _build_top_n_filter_from_computation(
        self,
        comp: Computation,
        semantic_query: SemanticQuery,
    ) -> dict | None:
        """Build Top N filter from computation with top_n parameter.
        
        Args:
            comp: Computation with top_n parameter (RankCalc or DenseRankCalc)
            semantic_query: Full semantic query for context
            
        Returns:
            VizQL Top N filter dict or None
        """
        top_n = getattr(comp, 'top_n', None)
        if not top_n:
            return None
        
        # Determine the dimension to filter on (first partition dimension or first query dimension)
        # partition_by is now list[DimensionField]
        filter_dimension = None
        if comp.partition_by:
            first_partition = comp.partition_by[0]
            filter_dimension = first_partition.field_name if hasattr(first_partition, 'field_name') else first_partition
        elif semantic_query.dimensions:
            filter_dimension = semantic_query.dimensions[0].field_name
        
        if not filter_dimension:
            logger.warning(f"Cannot build Top N filter: no dimension available for computation {comp.target}")
            return None
        
        # Direction: ASC means bottom N, DESC means top N
        direction = getattr(comp, 'direction', None) or self.DEFAULT_DIRECTION
        
        return {
            "field": {"fieldCaption": filter_dimension},
            "filterType": "TOP",
            "howMany": top_n,
            "fieldToMeasure": {"fieldCaption": comp.target},
            "direction": direction.value if hasattr(direction, 'value') else str(direction),
        }
    
    def _build_percentile_spec(self, comp: Computation, partition_dims: list[dict]) -> dict:
        """Build percentile table calculation spec."""
        direction = getattr(comp, 'direction', None) or self.DEFAULT_DIRECTION
        
        return {
            "tableCalcType": "PERCENTILE",
            "dimensions": partition_dims,
            "direction": direction.value if hasattr(direction, 'value') else str(direction),
        }
    
    def _build_running_total_spec(self, comp: Computation, partition_dims: list[dict]) -> dict:
        """Build running total table calculation spec."""
        aggregation = getattr(comp, 'aggregation', None) or self.DEFAULT_AGGREGATION
        
        spec = {
            "tableCalcType": "RUNNING_TOTAL",
            "dimensions": partition_dims,
            "aggregation": aggregation.value if hasattr(aggregation, 'value') else str(aggregation),
        }
        
        restart_every = getattr(comp, 'restart_every', None)
        if restart_every:
            spec["restartEvery"] = {"fieldCaption": restart_every}
        
        return spec
    
    def _build_moving_calc_spec(self, comp: Computation, partition_dims: list[dict]) -> dict:
        """Build moving calculation spec."""
        aggregation = getattr(comp, 'aggregation', None) or self.DEFAULT_AGGREGATION
        previous = getattr(comp, 'window_previous', None)
        if previous is None:
            previous = self.DEFAULT_WINDOW_PREVIOUS
        next_val = getattr(comp, 'window_next', None)
        if next_val is None:
            next_val = self.DEFAULT_WINDOW_NEXT
        include_current = getattr(comp, 'include_current', None)
        if include_current is None:
            include_current = self.DEFAULT_INCLUDE_CURRENT
        
        return {
            "tableCalcType": "MOVING_CALCULATION",
            "dimensions": partition_dims,
            "aggregation": aggregation.value if hasattr(aggregation, 'value') else str(aggregation),
            "previous": previous,
            "next": next_val,
            "includeCurrent": include_current,
        }
    
    def _build_percent_of_total_spec(self, comp: Computation, partition_dims: list[dict]) -> dict:
        """Build percent of total table calculation spec."""
        spec = {
            "tableCalcType": "PERCENT_OF_TOTAL",
            "dimensions": partition_dims,
        }
        
        level_of = getattr(comp, 'level_of', None)
        if level_of:
            spec["levelAddress"] = {"fieldCaption": level_of}
        
        return spec
    
    def _build_difference_spec(self, comp: Computation, partition_dims: list[dict]) -> dict:
        """Build difference table calculation spec."""
        relative_to = getattr(comp, 'relative_to', None) or self.DEFAULT_RELATIVE_TO
        
        return {
            "tableCalcType": "DIFFERENCE_FROM",
            "dimensions": partition_dims,
            "relativeTo": relative_to.value if hasattr(relative_to, 'value') else str(relative_to),
        }
    
    def _build_percent_difference_spec(self, comp: Computation, partition_dims: list[dict]) -> dict:
        """Build percent difference table calculation spec."""
        relative_to = getattr(comp, 'relative_to', None) or self.DEFAULT_RELATIVE_TO
        
        return {
            "tableCalcType": "PERCENT_DIFFERENCE_FROM",
            "dimensions": partition_dims,
            "relativeTo": relative_to.value if hasattr(relative_to, 'value') else str(relative_to),
        }
    
    def _build_lod_field(self, comp: Computation) -> dict:
        """Build VizQL LOD expression field.
        
        Supports LODFixed, LODInclude, LODExclude types.
        These types have 'dimensions' and 'aggregation' attributes directly.
        """
        # Determine LOD type from calc_type string
        lod_type_map = {
            "LOD_FIXED": "FIXED",
            "LOD_INCLUDE": "INCLUDE",
            "LOD_EXCLUDE": "EXCLUDE",
        }
        lod_type = lod_type_map.get(comp.calc_type, "FIXED")
        
        # Build LOD expression string
        # LOD types have 'dimensions' attribute (not lod_dimensions)
        lod_dims = getattr(comp, 'dimensions', []) or []
        dims_str = ", ".join(f"[{d}]" for d in lod_dims)
        
        # LOD types have 'aggregation' attribute (not lod_aggregation)
        aggregation = getattr(comp, 'aggregation', None) or AggregationType.SUM
        agg = aggregation.value if hasattr(aggregation, 'value') else str(aggregation)
        
        if dims_str:
            calculation = f"{{{lod_type} {dims_str} : {agg}([{comp.target}])}}"
        else:
            calculation = f"{{{agg}([{comp.target}])}}"
        
        return {
            "fieldCaption": comp.alias or f"LOD_{comp.target}",
            "calculation": calculation,
        }
    
    def _build_filter(self, f: Any, field_metadata: dict[str, dict] | None = None) -> dict | None:
        """Build VizQL filter from core filter model.
        
        For date filters (DateRangeFilter):
        - DATE/DATETIME 类型：QuantitativeDateFilter + fieldCaption
        - STRING 类型：QuantitativeDateFilter + DATEPARSE 计算字段
        
        VizQL API 限制：
        - SetFilter、MatchFilter、RelativeDateFilter 不支持 CalculatedFilterField
        - 但 QuantitativeDateFilter 支持 CalculatedFilterField
        """
        field_metadata = field_metadata or {}
        
        if isinstance(f, SetFilter):
            return {
                "field": {"fieldCaption": f.field_name},
                "filterType": "SET",
                "values": f.values,
                "exclude": f.exclude,
            }
        
        elif isinstance(f, DateRangeFilter):
            meta = field_metadata.get(f.field_name, {})
            data_type = meta.get("dataType", "").upper()
            
            # 统一使用 QuantitativeDateFilter
            # STRING 类型需要用 DATEPARSE 转换
            if data_type == "STRING":
                # STRING 类型 - 使用 CalculatedFilterField + DATEPARSE
                field_ref = {
                    "calculation": f"DATEPARSE('yyyy-MM-dd', [{f.field_name}])"
                }
            else:
                # DATE/DATETIME 类型 - 直接使用字段名
                field_ref = {"fieldCaption": f.field_name}
            
            filter_dict = {
                "field": field_ref,
                "filterType": "QUANTITATIVE_DATE",
                "quantitativeFilterType": "RANGE",
            }
            
            if f.start_date:
                filter_dict["minDate"] = f.start_date.isoformat() if hasattr(f.start_date, 'isoformat') else str(f.start_date)
            if f.end_date:
                filter_dict["maxDate"] = f.end_date.isoformat() if hasattr(f.end_date, 'isoformat') else str(f.end_date)
            
            return filter_dict
        
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
            filter_dict = {
                "field": {"fieldCaption": f.field_name},
                "filterType": "MATCH",
            }
            # 只添加匹配类型对应的字段，避免发送 None 值
            match_type_value = f.match_type.value if hasattr(f.match_type, 'value') else str(f.match_type)
            if match_type_value == "CONTAINS":
                filter_dict["contains"] = f.pattern
            elif match_type_value == "STARTS_WITH":
                filter_dict["startsWith"] = f.pattern
            elif match_type_value == "ENDS_WITH":
                filter_dict["endsWith"] = f.pattern
            elif match_type_value == "EXACT":
                filter_dict["exactMatch"] = f.pattern
            else:
                # 默认使用 contains
                filter_dict["contains"] = f.pattern
            return filter_dict
        
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
