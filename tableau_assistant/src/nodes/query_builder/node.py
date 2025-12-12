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
from typing import Dict, Optional, List, Union, TYPE_CHECKING

from langgraph.types import RunnableConfig

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel
    from tableau_assistant.src.models.workflow.state import VizQLState

from tableau_assistant.src.models.semantic.query import (
    SemanticQuery,
    MeasureSpec,
    DimensionSpec,
    FilterSpec,
    AnalysisSpec,
)
from tableau_assistant.src.models.field_mapper.models import MappedQuery
from tableau_assistant.src.models.semantic.enums import (
    AnalysisType,
    AggregationType,
    TimeGranularity,
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


# 使用 models/vizql/types.py 中的 Pydantic VizQLQuery
from tableau_assistant.src.models.vizql.types import VizQLQuery as VizQLQueryModel


class VizQLQueryBuilder:
    """
    VizQL Query Builder - 用于构建 VizQLQuery Pydantic 对象
    
    提供便捷方法来逐步构建查询，最终生成 VizQLQuery Pydantic 对象。
    """
    
    def __init__(self):
        self._fields: List[Union[BasicField, FunctionField, CalculationField, TableCalcField]] = []
        self._filters: List[Dict[str, object]] = []
        self._limit: Optional[int] = None
    
    def add_field(self, field: Union[BasicField, FunctionField, CalculationField, TableCalcField]) -> None:
        """Add a field to the query."""
        self._fields.append(field)
    
    def add_filter(self, filter_spec: Dict[str, object]) -> None:
        """Add a filter to the query."""
        self._filters.append(filter_spec)
    
    def set_limit(self, limit: int):
        """Set result limit."""
        self._limit = limit
    
    def build(self) -> VizQLQueryModel:
        """Build and return VizQLQuery Pydantic object."""
        return VizQLQueryModel(
            fields=self._fields,
            filters=self._filters if self._filters else None,
        )
    
    @property
    def limit(self) -> Optional[int]:
        return self._limit
    
    @limit.setter
    def limit(self, value: Optional[int]):
        self._limit = value


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
    
    def __init__(self, llm: Optional["BaseChatModel"] = None):
        """
        Initialize QueryBuilder.
        
        Args:
            llm: Optional LLM for complex scenarios (future use)
        """
        self.resolver = ImplementationResolver(llm)
        self.generator = ExpressionGenerator()
    
    async def build(self, mapped_query: MappedQuery) -> VizQLQueryModel:
        """
        Build VizQLQuery Pydantic object from MappedQuery.
        
        Args:
            mapped_query: MappedQuery with field mappings
            
        Returns:
            VizQLQuery Pydantic object ready for execution
        """
        semantic_query = mapped_query.semantic_query
        
        # Simple field mappings for dimensions/measures/analyses (just need technical_field)
        simple_field_mappings = {
            k: v.technical_field
            for k, v in mapped_query.field_mappings.items()
        }
        
        # Full field mappings for filters (need data_type, date_format for date handling)
        full_field_mappings = mapped_query.field_mappings
        
        # 使用 Builder 构建查询
        builder = VizQLQueryBuilder()
        
        # 1. Process dimensions
        for dim in semantic_query.dimensions:
            field = self._build_dimension_field(dim, simple_field_mappings)
            builder.add_field(field)
        
        # 2. Process measures
        for measure in semantic_query.measures:
            field = self._build_measure_field(measure, simple_field_mappings)
            builder.add_field(field)
        
        # 3. Process analyses (table calcs / LOD)
        for analysis in semantic_query.analyses:
            field = self._build_analysis_field(
                analysis,
                semantic_query.dimensions,
                simple_field_mappings,
            )
            if field:
                builder.add_field(field)
        
        # 4. Process filters (use full field mappings for date type handling)
        for filter_spec in semantic_query.filters:
            vizql_filter = self._build_filter(filter_spec, full_field_mappings)
            if vizql_filter:
                builder.add_filter(vizql_filter)
        
        # 5. Process output control
        if semantic_query.output_control:
            if semantic_query.output_control.limit:
                builder.limit = semantic_query.output_control.limit
        
        # 构建 VizQLQuery Pydantic 对象
        query = builder.build()
        logger.info(f"Built VizQLQuery with {len(query.fields)} fields")
        return query
    
    def _build_dimension_field(
        self,
        dim: DimensionSpec,
        field_mappings: Dict[str, str],
    ) -> Union[BasicField, FunctionField]:
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
    ) -> Union[FunctionField, CalculationField]:
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
    ) -> Optional[Union[CalculationField, TableCalcField, FunctionField]]:
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
        
        # 使用 analysis.aggregation 而不是硬编码的 SUM
        # 修复 COUNTD 等非 SUM 聚合在表计算中的问题
        agg_type = AggregationType(analysis.aggregation) if analysis.aggregation else AggregationType.SUM
        
        expression = self.generator.generate(
            analysis.type,
            decision,
            target_field,
            aggregation=agg_type,
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
        field_mappings: Dict[str, object],
    ) -> Optional[Dict[str, object]]:
        """
        Build VizQL filter specification.
        
        Converts semantic filter to VizQL filter format.
        Uses DateParser for time range calculations.
        Handles different field data types (DATE vs STRING) appropriately.
        
        VizQL valid filter types: DATE, MATCH, QUANTITATIVE_DATE, QUANTITATIVE_NUMERICAL, SET, TOP
        
        Date Filter Strategy by Field Type:
        - DATE/DATETIME: Use QUANTITATIVE_DATE or DATE (RelativeDateFilter)
        - STRING: Use DATEPARSE + QUANTITATIVE_DATE, or SET/MATCH for direct string matching
        
        Test Results Reference:
        - DATE + QUANTITATIVE_DATE: ✓ Success
        - DATE + DATE (RelativeDateFilter): ✓ Success
        - DATE + SET: ✗ Failed (DATE type doesn't support SET filter)
        - STRING + DATEPARSE + QUANTITATIVE_DATE: ✓ Success (use filter.field.calculation)
        - STRING + SET: ✓ Success
        - STRING + MATCH: ✓ Success
        """
        from tableau_assistant.src.models.semantic.enums import FilterType, TimeFilterMode
        from tableau_assistant.src.capabilities.date_processing import DateParser
        
        # Get field mapping info (may be string or FieldMapping object)
        field_mapping = field_mappings.get(filter_spec.field)
        if isinstance(field_mapping, str):
            tech_field = field_mapping
            data_type = None
            date_format = None
        elif hasattr(field_mapping, 'technical_field'):
            tech_field = field_mapping.technical_field
            data_type = getattr(field_mapping, 'data_type', None)
            date_format = getattr(field_mapping, 'date_format', None)
        else:
            tech_field = filter_spec.field
            data_type = None
            date_format = None
        
        # Build filter based on filter_type
        if filter_spec.filter_type == FilterType.TIME_RANGE:
            return self._build_time_range_filter(
                filter_spec, tech_field, data_type, date_format
            )
        
        elif filter_spec.filter_type == FilterType.SET:
            # Set filter (enumeration values)
            values = filter_spec.values or []
            exclude = filter_spec.exclude or False
            return {
                "field": {"fieldCaption": tech_field},
                "filterType": "SET",
                "values": values,
                "exclude": exclude,
            }
        
        elif filter_spec.filter_type == FilterType.QUANTITATIVE:
            # Quantitative range filter
            filter_dict = {
                "field": {"fieldCaption": tech_field},
                "filterType": "QUANTITATIVE_NUMERICAL",
            }
            if filter_spec.min_value is not None:
                filter_dict["minValue"] = filter_spec.min_value
            if filter_spec.max_value is not None:
                filter_dict["maxValue"] = filter_spec.max_value
            return filter_dict
        
        elif filter_spec.filter_type == FilterType.MATCH:
            # Pattern match filter
            pattern = filter_spec.pattern
            if not pattern:
                return None
            return {
                "field": {"fieldCaption": tech_field},
                "filterType": "MATCH",
                "pattern": pattern,
            }
        
        # Unknown filter type
        logger.warning(f"Unknown filter_type: {filter_spec.filter_type}")
        return None
    
    def _build_time_range_filter(
        self,
        filter_spec: FilterSpec,
        tech_field: str,
        data_type: Optional[str],
        date_format: Optional[str],
    ) -> Optional[Dict[str, object]]:
        """
        Build time range filter based on field data type.
        
        Strategy:
        - DATE/DATETIME type: Use QUANTITATIVE_DATE or DATE (RelativeDateFilter)
        - STRING type: Use DATEPARSE + QUANTITATIVE_DATE
        - Unknown type: Default to DATE type behavior
        
        Args:
            filter_spec: FilterSpec with time_filter
            tech_field: Technical field name
            data_type: Field data type (DATE, DATETIME, STRING, etc.)
            date_format: Date format for STRING type fields
        
        Returns:
            VizQL filter specification dict
        """
        from tableau_assistant.src.models.semantic.enums import TimeFilterMode
        from tableau_assistant.src.capabilities.date_processing import DateParser
        
        time_filter_spec = filter_spec.time_filter
        if not time_filter_spec:
            logger.warning(f"time_range filter missing time_filter spec for field {filter_spec.field}")
            return None
        
        # Use DateParser to process time filter
        parser = DateParser()
        try:
            result = parser.process_time_filter(time_filter_spec)
        except Exception as e:
            logger.error(f"DateParser failed: {e}")
            return None
        
        filter_type = result.get("filter_type")
        is_string_type = data_type == "STRING"
        
        # Handle STRING type date fields
        if is_string_type:
            return self._build_string_date_filter(
                result, tech_field, date_format, time_filter_spec
            )
        
        # Handle DATE/DATETIME type fields (or unknown type)
        if filter_type == "QUANTITATIVE_DATE":
            return {
                "field": {"fieldCaption": tech_field},
                "filterType": "QUANTITATIVE_DATE",
                "quantitativeFilterType": result.get("quantitative_filter_type", "RANGE"),
                "minDate": result.get("min_date"),
                "maxDate": result.get("max_date"),
            }
        elif filter_type == "DATE":
            # Relative date filter
            filter_dict = {
                "field": {"fieldCaption": tech_field},
                "filterType": "DATE",
                "periodType": result.get("period_type"),
                "dateRangeType": result.get("date_range_type"),
            }
            if result.get("range_n") is not None:
                filter_dict["rangeN"] = result.get("range_n")
            if result.get("anchor_date") is not None:
                filter_dict["anchorDate"] = result.get("anchor_date")
            return filter_dict
        elif filter_type == "SET":
            # DATE type doesn't support SET filter well
            # Convert to QUANTITATIVE_DATE range if possible
            values = result.get("values", [])
            if values:
                # Try to convert SET to date range
                min_date, max_date = self._set_values_to_date_range(values)
                if min_date and max_date:
                    logger.info(f"Converting SET filter to QUANTITATIVE_DATE range: {min_date} to {max_date}")
                    return {
                        "field": {"fieldCaption": tech_field},
                        "filterType": "QUANTITATIVE_DATE",
                        "quantitativeFilterType": "RANGE",
                        "minDate": min_date,
                        "maxDate": max_date,
                    }
            # Fallback to SET (may fail for DATE type)
            logger.warning(f"Using SET filter for DATE type field {tech_field}, this may fail")
            return {
                "field": {"fieldCaption": tech_field},
                "filterType": "SET",
                "values": values,
                "exclude": result.get("exclude", False),
            }
        else:
            logger.warning(f"Unknown filter type from DateParser: {filter_type}")
            return None
    
    def _build_string_date_filter(
        self,
        parser_result: Dict[str, object],
        tech_field: str,
        date_format: Optional[str],
        time_filter_spec: object,
    ) -> Optional[Dict[str, object]]:
        """
        Build date filter for STRING type date fields.
        
        Uses DATEPARSE to convert STRING to DATE, then applies QUANTITATIVE_DATE filter.
        
        VizQL API requires using filter.field.calculation for DATEPARSE:
        {
            "field": {"calculation": "DATEPARSE('yyyy-MM-dd', [field_name])"},
            "filterType": "QUANTITATIVE_DATE",
            ...
        }
        
        Args:
            parser_result: Result from DateParser.process_time_filter()
            tech_field: Technical field name
            date_format: Date format pattern (e.g., 'yyyy-MM-dd')
            time_filter_spec: Original TimeFilterSpec
        
        Returns:
            VizQL filter specification dict
        """
        filter_type = parser_result.get("filter_type")
        
        # Default date format if not provided
        if not date_format:
            date_format = "yyyy-MM-dd"
        
        # Build DATEPARSE calculation expression
        dateparse_calc = f"DATEPARSE('{date_format}', [{tech_field}])"
        
        if filter_type == "QUANTITATIVE_DATE":
            # Use DATEPARSE + QUANTITATIVE_DATE
            return {
                "field": {"calculation": dateparse_calc},
                "filterType": "QUANTITATIVE_DATE",
                "quantitativeFilterType": parser_result.get("quantitative_filter_type", "RANGE"),
                "minDate": parser_result.get("min_date"),
                "maxDate": parser_result.get("max_date"),
            }
        elif filter_type == "DATE":
            # Relative date filter with DATEPARSE
            # Need to calculate actual dates since DATEPARSE + RelativeDateFilter may not work
            from tableau_assistant.src.capabilities.date_processing import DateParser
            parser = DateParser()
            try:
                start_date, end_date = parser.calculate_relative_dates(time_filter_spec)
                return {
                    "field": {"calculation": dateparse_calc},
                    "filterType": "QUANTITATIVE_DATE",
                    "quantitativeFilterType": "RANGE",
                    "minDate": start_date,
                    "maxDate": end_date,
                }
            except Exception as e:
                logger.error(f"Failed to calculate relative dates for STRING field: {e}")
                return None
        elif filter_type == "SET":
            # For STRING type, SET filter can work directly with string values
            # But if we want date semantics, use DATEPARSE + QUANTITATIVE_DATE
            values = parser_result.get("values", [])
            if values:
                min_date, max_date = self._set_values_to_date_range(values)
                if min_date and max_date:
                    return {
                        "field": {"calculation": dateparse_calc},
                        "filterType": "QUANTITATIVE_DATE",
                        "quantitativeFilterType": "RANGE",
                        "minDate": min_date,
                        "maxDate": max_date,
                    }
            # Fallback to direct SET filter on STRING field
            return {
                "field": {"fieldCaption": tech_field},
                "filterType": "SET",
                "values": values,
                "exclude": parser_result.get("exclude", False),
            }
        else:
            logger.warning(f"Unknown filter type for STRING date field: {filter_type}")
            return None
    
    def _set_values_to_date_range(
        self,
        values: List[str],
    ) -> tuple:
        """
        Convert SET values to date range (min_date, max_date).
        
        Handles various date formats:
        - Year: "2024" → "2024-01-01" to "2024-12-31"
        - Month: "2024-01" → "2024-01-01" to "2024-01-31"
        - Quarter: "2024-Q1" → "2024-01-01" to "2024-03-31"
        - Day: "2024-01-15" → "2024-01-15" to "2024-01-15"
        
        Args:
            values: List of date values
        
        Returns:
            (min_date, max_date) tuple in YYYY-MM-DD format, or (None, None) if conversion fails
        """
        import re
        from calendar import monthrange
        
        if not values:
            return (None, None)
        
        all_dates = []
        
        for value in values:
            # Year format: "2024"
            if re.match(r'^\d{4}$', value):
                year = int(value)
                all_dates.append(f"{year}-01-01")
                all_dates.append(f"{year}-12-31")
            # Quarter format: "2024-Q1"
            elif re.match(r'^\d{4}-Q[1-4]$', value, re.IGNORECASE):
                year = int(value[:4])
                quarter = int(value[-1])
                start_month = (quarter - 1) * 3 + 1
                end_month = quarter * 3
                _, last_day = monthrange(year, end_month)
                all_dates.append(f"{year}-{start_month:02d}-01")
                all_dates.append(f"{year}-{end_month:02d}-{last_day:02d}")
            # Month format: "2024-01"
            elif re.match(r'^\d{4}-\d{2}$', value):
                year = int(value[:4])
                month = int(value[5:7])
                _, last_day = monthrange(year, month)
                all_dates.append(f"{year}-{month:02d}-01")
                all_dates.append(f"{year}-{month:02d}-{last_day:02d}")
            # Day format: "2024-01-15"
            elif re.match(r'^\d{4}-\d{2}-\d{2}$', value):
                all_dates.append(value)
            else:
                logger.warning(f"Unknown date format in SET values: {value}")
        
        if not all_dates:
            return (None, None)
        
        # Sort and get min/max
        all_dates.sort()
        return (all_dates[0], all_dates[-1])
    



async def query_builder_node(state: "VizQLState", config: RunnableConfig | None = None) -> Dict[str, object]:
    """
    QueryBuilder node entry point for LangGraph.
    
    Args:
        state: VizQLState containing mapped_query (MappedQuery object or dict)
        config: Optional configuration
        
    Returns:
        Updated state with vizql_query (VizQLQuery Pydantic object)
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
        # mapped_query 必须是 MappedQuery Pydantic 对象
        # Build VizQL query - 返回 VizQLQuery Pydantic 对象
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
