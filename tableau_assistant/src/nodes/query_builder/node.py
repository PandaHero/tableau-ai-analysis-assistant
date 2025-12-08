"""
QueryBuilder Node

Pure code node that converts MappedQuery to VizQLQuery.

Architecture:
- Receives MappedQuery (semantic with technical field mappings)
- Uses ImplementationResolver to determine table calc vs LOD
- Uses ExpressionGenerator to generate VizQL expressions
- Outputs VizQLQuery ready for execution

Requirements:
- R2.8: QueryBuilder Node entry point
- R7.1: Table calculation and LOD support
- R7.2: Expression generation
"""

import logging
from typing import Dict, Any, Optional, List, TYPE_CHECKING

from langgraph.types import RunnableConfig

from tableau_assistant.src.models.semantic.query import (
    SemanticQuery,
    MappedQuery,
    MeasureSpec,
    DimensionSpec,
    FilterSpec,
    AnalysisSpec,
)
from tableau_assistant.src.models.semantic.enums import (
    AnalysisType,
    AggregationType,
    TimeGranularity,
    FilterOperator,
)
from tableau_assistant.src.models.vizql.types import (
    BasicField,
    FunctionField,
    CalculationField,
    TableCalcField,
    FunctionEnum,
    SortDirection,
    TableCalcFieldReference,
)
from .implementation_resolver import (
    ImplementationResolver,
    ImplementationDecision,
    ImplementationType,
)
from .expression_generator import ExpressionGenerator, GeneratedExpression

logger = logging.getLogger(__name__)


# Time granularity to VizQL function mapping
TIME_GRANULARITY_TO_FUNCTION: Dict[TimeGranularity, FunctionEnum] = {
    TimeGranularity.YEAR: FunctionEnum.YEAR,
    TimeGranularity.QUARTER: FunctionEnum.QUARTER,
    TimeGranularity.MONTH: FunctionEnum.MONTH,
    TimeGranularity.WEEK: FunctionEnum.WEEK,
    TimeGranularity.DAY: FunctionEnum.DAY,
}

# Aggregation to VizQL function mapping
AGG_TO_FUNCTION: Dict[AggregationType, FunctionEnum] = {
    AggregationType.SUM: FunctionEnum.SUM,
    AggregationType.AVG: FunctionEnum.AVG,
    AggregationType.COUNT: FunctionEnum.COUNT,
    AggregationType.COUNTD: FunctionEnum.COUNTD,
    AggregationType.MIN: FunctionEnum.MIN,
    AggregationType.MAX: FunctionEnum.MAX,
}


class VizQLQuery:
    """
    VizQL Query representation
    
    Contains all fields needed for VizQL Data Service API call.
    """
    
    def __init__(self):
        self.fields: List[Any] = []
        self.filters: List[Dict[str, Any]] = []
        self.limit: Optional[int] = None
        self.sort_fields: List[Dict[str, Any]] = []
    
    def add_field(self, field: Any):
        """Add a field to the query."""
        self.fields.append(field)
    
    def add_filter(self, filter_spec: Dict[str, Any]):
        """Add a filter to the query."""
        self.filters.append(filter_spec)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API call."""
        result = {
            "fields": [self._field_to_dict(f) for f in self.fields]
        }
        
        if self.filters:
            result["filters"] = self.filters
        
        if self.limit:
            result["limit"] = self.limit
        
        return result
    
    def _field_to_dict(self, field: Any) -> Dict[str, Any]:
        """Convert a field to dictionary."""
        if hasattr(field, "model_dump"):
            return field.model_dump(exclude_none=True)
        elif isinstance(field, dict):
            return field
        else:
            return {"fieldCaption": str(field)}


class QueryBuilderNode:
    """
    QueryBuilder Node implementation.
    
    Converts MappedQuery (semantic with technical fields) to VizQLQuery.
    
    Flow:
    1. Process dimensions → BasicField or FunctionField
    2. Process measures → FunctionField
    3. Process analyses → TableCalcField or CalculationField
    4. Process filters → Filter specifications
    5. Assemble VizQLQuery
    """
    
    def __init__(self, llm: Optional[Any] = None):
        """
        Initialize QueryBuilder.
        
        Args:
            llm: Optional LLM for complex scenarios (future use)
        """
        self.resolver = ImplementationResolver(llm)
        self.generator = ExpressionGenerator()
    
    async def build(self, mapped_query: MappedQuery) -> VizQLQuery:
        """
        Build VizQLQuery from MappedQuery.
        
        Args:
            mapped_query: MappedQuery with field mappings
            
        Returns:
            VizQLQuery ready for execution
        """
        semantic_query = mapped_query.semantic_query
        field_mappings = {
            k: v.technical_field
            for k, v in mapped_query.field_mappings.items()
        }
        
        query = VizQLQuery()
        
        # 1. Process dimensions
        for dim in semantic_query.dimensions:
            field = self._build_dimension_field(dim, field_mappings)
            query.add_field(field)
        
        # 2. Process measures
        for measure in semantic_query.measures:
            field = self._build_measure_field(measure, field_mappings)
            query.add_field(field)
        
        # 3. Process analyses (table calcs / LOD)
        for analysis in semantic_query.analyses:
            field = self._build_analysis_field(
                analysis,
                semantic_query.dimensions,
                field_mappings,
            )
            if field:
                query.add_field(field)
        
        # 4. Process filters
        for filter_spec in semantic_query.filters:
            vizql_filter = self._build_filter(filter_spec, field_mappings)
            if vizql_filter:
                query.add_filter(vizql_filter)
        
        # 5. Process output control
        if semantic_query.output_control:
            if semantic_query.output_control.limit:
                query.limit = semantic_query.output_control.limit
        
        logger.info(f"Built VizQLQuery with {len(query.fields)} fields")
        return query
    
    def _build_dimension_field(
        self,
        dim: DimensionSpec,
        field_mappings: Dict[str, str],
    ) -> Any:
        """
        Build dimension field.
        
        - Time dimensions with granularity → FunctionField
        - Regular dimensions → BasicField
        """
        tech_field = field_mappings.get(dim.name, dim.name)
        
        if dim.time_granularity:
            # Time dimension with granularity
            func = TIME_GRANULARITY_TO_FUNCTION.get(
                dim.time_granularity,
                FunctionEnum.MONTH
            )
            return FunctionField(
                fieldCaption=tech_field,
                function=func,
                fieldAlias=dim.alias,
            )
        else:
            # Regular dimension
            return BasicField(
                fieldCaption=tech_field,
                fieldAlias=dim.alias,
            )
    
    def _build_measure_field(
        self,
        measure: MeasureSpec,
        field_mappings: Dict[str, str],
    ) -> Any:
        """
        Build measure field.
        
        - COUNTD → CalculationField (special case)
        - Other aggregations → FunctionField
        """
        tech_field = field_mappings.get(measure.name, measure.name)
        agg = measure.aggregation or AggregationType.SUM
        
        if agg == AggregationType.COUNTD:
            # COUNTD requires calculation field
            return CalculationField(
                fieldCaption=f"countd_{tech_field}",
                calculation=f"COUNTD([{tech_field}])",
                fieldAlias=measure.alias,
            )
        else:
            func = AGG_TO_FUNCTION.get(agg, FunctionEnum.SUM)
            return FunctionField(
                fieldCaption=tech_field,
                function=func,
                fieldAlias=measure.alias,
            )
    
    def _build_analysis_field(
        self,
        analysis: AnalysisSpec,
        dimensions: List[DimensionSpec],
        field_mappings: Dict[str, str],
    ) -> Optional[Any]:
        """
        Build analysis field (table calc or LOD).
        
        Flow:
        1. Resolve implementation (table calc vs LOD)
        2. Generate expression
        3. Build appropriate field type
        """
        # Get target measure technical field
        target_field = field_mappings.get(
            analysis.target_measure,
            analysis.target_measure
        )
        
        # Resolve implementation
        decision = self.resolver.resolve(
            analysis,
            dimensions,
            field_mappings,
        )
        
        logger.debug(f"Implementation decision: {decision}")
        
        # Generate expression
        kwargs = {}
        if analysis.window_size:
            kwargs["window_size"] = analysis.window_size
        if analysis.order:
            kwargs["order"] = analysis.order
        if analysis.compare_type:
            kwargs["compare_period"] = analysis.compare_type
        
        expression = self.generator.generate(
            analysis.type,
            decision,
            target_field,
            aggregation=AggregationType.SUM,  # Default, could be from analysis
            **kwargs,
        )
        
        # Build field based on expression type
        if expression.calculation:
            # LOD or custom calculation
            return CalculationField(
                fieldCaption=expression.field_alias or f"calc_{target_field}",
                calculation=expression.calculation,
            )
        elif expression.table_calc_spec:
            # Table calculation
            return TableCalcField(
                fieldCaption=target_field,
                function=expression.function,
                fieldAlias=expression.field_alias,
                tableCalculation=expression.table_calc_spec,
            )
        elif expression.function:
            # Simple aggregation
            return FunctionField(
                fieldCaption=target_field,
                function=expression.function,
                fieldAlias=expression.field_alias,
            )
        
        return None
    
    def _build_filter(
        self,
        filter_spec: FilterSpec,
        field_mappings: Dict[str, str],
    ) -> Optional[Dict[str, Any]]:
        """
        Build VizQL filter specification.
        
        Converts semantic filter to VizQL filter format.
        """
        tech_field = field_mappings.get(filter_spec.field, filter_spec.field)
        
        # Build filter based on operator
        if filter_spec.operator == FilterOperator.IN:
            return {
                "field": {"fieldCaption": tech_field},
                "filterType": "SET",
                "values": filter_spec.value if isinstance(filter_spec.value, list) else [filter_spec.value],
                "exclude": False,
            }
        elif filter_spec.operator == FilterOperator.NOT_IN:
            return {
                "field": {"fieldCaption": tech_field},
                "filterType": "SET",
                "values": filter_spec.value if isinstance(filter_spec.value, list) else [filter_spec.value],
                "exclude": True,
            }
        elif filter_spec.operator == FilterOperator.EQUALS:
            return {
                "field": {"fieldCaption": tech_field},
                "filterType": "SET",
                "values": [filter_spec.value],
                "exclude": False,
            }
        elif filter_spec.operator == FilterOperator.BETWEEN:
            # Date range filter
            return {
                "field": {"fieldCaption": tech_field},
                "filterType": "QUANTITATIVE_RANGE",
                "minValue": filter_spec.start_date,
                "maxValue": filter_spec.end_date,
            }
        elif filter_spec.operator in (
            FilterOperator.GREATER_THAN,
            FilterOperator.GREATER_THAN_OR_EQUALS,
            FilterOperator.LESS_THAN,
            FilterOperator.LESS_THAN_OR_EQUALS,
        ):
            # Quantitative filter
            filter_dict = {
                "field": {"fieldCaption": tech_field},
                "filterType": "QUANTITATIVE_RANGE",
            }
            if filter_spec.operator in (FilterOperator.GREATER_THAN, FilterOperator.GREATER_THAN_OR_EQUALS):
                filter_dict["minValue"] = filter_spec.value
            else:
                filter_dict["maxValue"] = filter_spec.value
            return filter_dict
        
        # Default: SET filter
        return {
            "field": {"fieldCaption": tech_field},
            "filterType": "SET",
            "values": [filter_spec.value] if not isinstance(filter_spec.value, list) else filter_spec.value,
            "exclude": False,
        }


async def query_builder_node(state: Dict[str, Any], config: RunnableConfig | None = None) -> Dict[str, Any]:
    """
    QueryBuilder node entry point for LangGraph.
    
    Args:
        state: VizQLState containing mapped_query
        config: Optional configuration
        
    Returns:
        Updated state with vizql_query
    """
    logger.info("QueryBuilder node started")
    
    mapped_query = state.get("mapped_query")
    if not mapped_query:
        logger.error("No mapped_query in state")
        return {
            "errors": state.get("errors", []) + [{
                "node": "query_builder",
                "error": "No mapped_query provided",
                "type": "missing_input",
            }],
            "query_builder_complete": True,
        }
    
    try:
        # Build VizQL query
        builder = QueryBuilderNode()
        vizql_query = await builder.build(mapped_query)
        
        logger.info("QueryBuilder node completed successfully")
        return {
            "vizql_query": vizql_query,
            "query_builder_complete": True,
        }
    
    except Exception as e:
        logger.exception(f"QueryBuilder node failed: {e}")
        return {
            "errors": state.get("errors", []) + [{
                "node": "query_builder",
                "error": str(e),
                "type": "build_error",
            }],
            "query_builder_complete": True,
        }
