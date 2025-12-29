"""
QueryBuilder Node

Pure code node that converts MappedQuery to VizQLQuery.

Architecture (refactored):
- Receives MappedQuery (semantic with technical field mappings)
- Uses TableauQueryBuilder from platforms/tableau to build VizQL
- Outputs VizQLQuery ready for execution

Requirements:
- R2.8: QueryBuilder Node entry point
- R7.1: Table calculation and LOD support
- R7.2: Expression generation
"""

import logging
from typing import Dict, Optional, List, Union, Any

from langgraph.types import RunnableConfig
from langchain_core.language_models import BaseChatModel

from tableau_assistant.src.orchestration.workflow.state import VizQLState

# Use new core/models
from tableau_assistant.src.core.models import (
    SemanticQuery,
    DimensionField,
    MeasureField,
    Computation,
    AggregationType,
    DateGranularity,
    SortSpec,
    SetFilter,
    DateRangeFilter,
    NumericRangeFilter,
    TextMatchFilter,
    TopNFilter,
    # Computation subtypes for field mapping
    LODFixed,
    LODInclude,
    LODExclude,
    RankCalc,
    DenseRankCalc,
    PercentileCalc,
    DifferenceCalc,
    PercentDifferenceCalc,
    RunningTotalCalc,
    MovingCalc,
    PercentOfTotalCalc,
)
from tableau_assistant.src.core.models import MappedQuery
from tableau_assistant.src.platforms.tableau.models import VizQLQueryRequest as VizQLQueryModel

# Use new platform adapter
from tableau_assistant.src.platforms.tableau.query_builder import TableauQueryBuilder

logger = logging.getLogger(__name__)


class QueryBuilderNode:
    """
    QueryBuilder Node implementation (refactored).
    
    Converts MappedQuery (semantic with technical fields) to VizQLQuery.
    Uses the new TableauQueryBuilder from platforms/tableau.
    """
    
    def __init__(self, llm: Optional[BaseChatModel] = None):
        """
        Initialize QueryBuilder.
        
        Args:
            llm: Optional LLM for complex scenarios (future use)
        """
        self._query_builder = TableauQueryBuilder()
    
    async def build(self, mapped_query: MappedQuery, datasource_luid: str, field_metadata: Dict[str, Any] = None) -> VizQLQueryModel:
        """
        Build VizQLQuery Pydantic object from MappedQuery.
        
        Args:
            mapped_query: MappedQuery with field mappings
            datasource_luid: Datasource LUID for the query
            field_metadata: Optional dict mapping field names to metadata (for date type detection)
            
        Returns:
            VizQLQuery Pydantic object ready for execution
        """
        semantic_query = mapped_query.semantic_query
        field_metadata = field_metadata or {}
        
        # Apply field mappings to semantic query
        mapped_semantic_query = self._apply_field_mappings(
            semantic_query, mapped_query.field_mappings
        )
        
        # Use TableauQueryBuilder to build VizQL request
        vizql_request = self._query_builder.build(mapped_semantic_query, field_metadata=field_metadata)
        
        # 确保 datasource 字段存在
        datasource_dict = {"datasourceLuid": datasource_luid}
        
        # Convert to VizQLQuery Pydantic model
        vizql_query = VizQLQueryModel(
            datasource=datasource_dict,
            fields=vizql_request.get("fields", []),
            filters=vizql_request.get("filters"),
            sorts=vizql_request.get("sorts"),
            row_limit=vizql_request.get("rowLimit"),
        )
        
        logger.info(f"Built VizQLQuery with {len(vizql_query.fields)} fields for datasource {datasource_luid}")
        return vizql_query
    
    def _apply_field_mappings(
        self,
        semantic_query: SemanticQuery,
        field_mappings: Dict[str, Any],
    ) -> SemanticQuery:
        """Apply field mappings to semantic query.
        
        Replaces business terms with technical field names.
        
        Args:
            semantic_query: Original semantic query with business terms
            field_mappings: Mapping from business terms to technical fields
            
        Returns:
            New SemanticQuery with technical field names
        """
        # Helper to get technical field name
        def get_tech_field(business_term: str) -> str:
            mapping = field_mappings.get(business_term)
            if mapping is None:
                return business_term
            if hasattr(mapping, 'technical_field'):
                return mapping.technical_field
            return business_term
        
        # Map dimensions
        mapped_dimensions = None
        if semantic_query.dimensions:
            mapped_dimensions = [
                DimensionField(
                    field_name=get_tech_field(d.field_name),
                    date_granularity=d.date_granularity,
                    alias=d.alias,
                    sort=d.sort,  # 保留排序信息
                )
                for d in semantic_query.dimensions
            ]
        
        # Map measures
        mapped_measures = None
        if semantic_query.measures:
            mapped_measures = [
                MeasureField(
                    field_name=get_tech_field(m.field_name),
                    aggregation=m.aggregation,
                    alias=m.alias,
                    sort=m.sort,  # 保留排序信息
                )
                for m in semantic_query.measures
            ]
        
        # Map computations
        # Note: Computation is a Union type (discriminated by calc_type), so we need to
        # map field names within each specific computation type, not create new instances
        mapped_computations = None
        if semantic_query.computations:
            mapped_computations = []
            for c in semantic_query.computations:
                mapped_comp = self._map_computation_fields(c, get_tech_field)
                mapped_computations.append(mapped_comp)
        
        # Map filters
        mapped_filters = None
        if semantic_query.filters:
            mapped_filters = []
            for f in semantic_query.filters:
                if isinstance(f, SetFilter):
                    mapped_filters.append(SetFilter(
                        field_name=get_tech_field(f.field_name),
                        values=f.values,
                        include=f.include,
                        exclude=f.exclude,
                    ))
                elif isinstance(f, DateRangeFilter):
                    mapped_filters.append(DateRangeFilter(
                        field_name=get_tech_field(f.field_name),
                        start_date=f.start_date,
                        end_date=f.end_date,
                    ))
                elif isinstance(f, NumericRangeFilter):
                    mapped_filters.append(NumericRangeFilter(
                        field_name=get_tech_field(f.field_name),
                        min_value=f.min_value,
                        max_value=f.max_value,
                    ))
                elif isinstance(f, TextMatchFilter):
                    mapped_filters.append(TextMatchFilter(
                        field_name=get_tech_field(f.field_name),
                        pattern=f.pattern,
                        match_type=f.match_type,
                    ))
                elif isinstance(f, TopNFilter):
                    mapped_filters.append(TopNFilter(
                        field_name=get_tech_field(f.field_name),
                        n=f.n,
                        by_field=get_tech_field(f.by_field),
                        direction=f.direction,
                    ))
                else:
                    # Unknown filter type, keep as is
                    mapped_filters.append(f)
        
        # Create new SemanticQuery with mapped fields
        # 注意：排序信息已嵌入在 DimensionField.sort 和 MeasureField.sort 中
        return SemanticQuery(
            dimensions=mapped_dimensions,
            measures=mapped_measures,
            computations=mapped_computations,
            filters=mapped_filters,
            row_limit=semantic_query.row_limit,
        )
    
    def _map_computation_fields(
        self,
        comp: Computation,
        get_tech_field: callable,
    ) -> Computation:
        """Map field names within a Computation object.
        
        Computation is a Union type with different subtypes (LOD, TableCalc).
        Each subtype has different fields that need mapping.
        
        Args:
            comp: Original computation object
            get_tech_field: Function to map business term to technical field
            
        Returns:
            New computation object with mapped field names
        """
        def map_partition_by(partition_by: list) -> list:
            """Map partition_by which is now list[DimensionField]."""
            result = []
            for p in partition_by:
                if isinstance(p, DimensionField):
                    # Create new DimensionField with mapped field_name
                    result.append(DimensionField(
                        field_name=get_tech_field(p.field_name),
                        date_granularity=p.date_granularity,
                        alias=p.alias,
                        sort=p.sort,
                    ))
                else:
                    # String fallback: convert to DimensionField
                    result.append(DimensionField(field_name=get_tech_field(p)))
            return result
        
        # LOD types - have target, dimensions, aggregation
        if isinstance(comp, LODFixed):
            return LODFixed(
                target=get_tech_field(comp.target),
                dimensions=[get_tech_field(d) for d in comp.dimensions],
                aggregation=comp.aggregation,
                alias=comp.alias,
            )
        elif isinstance(comp, LODInclude):
            return LODInclude(
                target=get_tech_field(comp.target),
                dimensions=[get_tech_field(d) for d in comp.dimensions],
                aggregation=comp.aggregation,
                alias=comp.alias,
            )
        elif isinstance(comp, LODExclude):
            return LODExclude(
                target=get_tech_field(comp.target),
                dimensions=[get_tech_field(d) for d in comp.dimensions],
                aggregation=comp.aggregation,
                alias=comp.alias,
            )
        
        # Ranking types - have target, partition_by, direction
        elif isinstance(comp, RankCalc):
            return RankCalc(
                target=get_tech_field(comp.target),
                partition_by=map_partition_by(comp.partition_by),
                direction=comp.direction,
                rank_style=comp.rank_style,
                top_n=comp.top_n,
            )
        elif isinstance(comp, DenseRankCalc):
            return DenseRankCalc(
                target=get_tech_field(comp.target),
                partition_by=map_partition_by(comp.partition_by),
                direction=comp.direction,
                top_n=comp.top_n,
            )
        elif isinstance(comp, PercentileCalc):
            return PercentileCalc(
                target=get_tech_field(comp.target),
                partition_by=map_partition_by(comp.partition_by),
                direction=comp.direction,
            )
        
        # Difference types - have target, partition_by, relative_to
        elif isinstance(comp, DifferenceCalc):
            return DifferenceCalc(
                target=get_tech_field(comp.target),
                partition_by=map_partition_by(comp.partition_by),
                relative_to=comp.relative_to,
            )
        elif isinstance(comp, PercentDifferenceCalc):
            return PercentDifferenceCalc(
                target=get_tech_field(comp.target),
                partition_by=map_partition_by(comp.partition_by),
                relative_to=comp.relative_to,
            )
        
        # Running/Moving types
        elif isinstance(comp, RunningTotalCalc):
            return RunningTotalCalc(
                target=get_tech_field(comp.target),
                partition_by=map_partition_by(comp.partition_by),
                aggregation=comp.aggregation,
                restart_every=comp.restart_every,
            )
        elif isinstance(comp, MovingCalc):
            return MovingCalc(
                target=get_tech_field(comp.target),
                partition_by=map_partition_by(comp.partition_by),
                aggregation=comp.aggregation,
                window_previous=comp.window_previous,
                window_next=comp.window_next,
                include_current=comp.include_current,
            )
        
        # Percent of total
        elif isinstance(comp, PercentOfTotalCalc):
            return PercentOfTotalCalc(
                target=get_tech_field(comp.target),
                partition_by=map_partition_by(comp.partition_by),
                level_of=comp.level_of,
            )
        
        # Unknown type - return as is (shouldn't happen with proper typing)
        else:
            logger.warning(f"Unknown computation type: {type(comp)}, returning as-is")
            return comp


async def query_builder_node(
    state: VizQLState,
    config: RunnableConfig | None = None
) -> Dict[str, object]:
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
    
    # 从 config 获取 datasource_luid
    datasource_luid = state.get("datasource") or "default"
    if config:
        try:
            from tableau_assistant.src.orchestration.workflow.context import get_context
            ctx = get_context(config)
            if ctx and ctx.datasource_luid:
                datasource_luid = ctx.datasource_luid
        except Exception as e:
            logger.warning(f"从 config 获取 datasource_luid 失败: {e}")
    
    # Get data_model for field metadata (used for date type detection)
    data_model = state.get("data_model")
    field_metadata = {}
    if data_model:
        fields = data_model.get("fields", []) if isinstance(data_model, dict) else getattr(data_model, "fields", [])
        field_metadata = {f.get("name") if isinstance(f, dict) else getattr(f, "name", ""): f for f in fields}
    
    try:
        # Build VizQL query
        builder = QueryBuilderNode()
        vizql_query = await builder.build(mapped_query, datasource_luid, field_metadata=field_metadata)
        
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
