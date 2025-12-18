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
    
    async def build(self, mapped_query: MappedQuery) -> VizQLQueryModel:
        """
        Build VizQLQuery Pydantic object from MappedQuery.
        
        Args:
            mapped_query: MappedQuery with field mappings
            
        Returns:
            VizQLQuery Pydantic object ready for execution
        """
        semantic_query = mapped_query.semantic_query
        
        # Apply field mappings to semantic query
        mapped_semantic_query = self._apply_field_mappings(
            semantic_query, mapped_query.field_mappings
        )
        
        # Use TableauQueryBuilder to build VizQL request
        vizql_request = self._query_builder.build(mapped_semantic_query)
        
        # Convert to VizQLQuery Pydantic model
        vizql_query = VizQLQueryModel(
            fields=vizql_request.get("fields", []),
            filters=vizql_request.get("filters"),
        )
        
        logger.info(f"Built VizQLQuery with {len(vizql_query.fields)} fields")
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
                )
                for m in semantic_query.measures
            ]
        
        # Map computations
        mapped_computations = None
        if semantic_query.computations:
            mapped_computations = [
                Computation(
                    target=get_tech_field(c.target),
                    partition_by=[get_tech_field(p) for p in c.partition_by],
                    operation=c.operation,
                    alias=c.alias,
                )
                for c in semantic_query.computations
            ]
        
        # Create new SemanticQuery with mapped fields
        return SemanticQuery(
            dimensions=mapped_dimensions,
            measures=mapped_measures,
            computations=mapped_computations,
            filters=semantic_query.filters,  # TODO: Map filter fields
            sorts=semantic_query.sorts,
            row_limit=semantic_query.row_limit,
        )


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
