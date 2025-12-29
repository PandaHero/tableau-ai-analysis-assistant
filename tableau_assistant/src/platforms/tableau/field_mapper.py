"""Tableau Field Mapper - Maps business terms to Tableau field names.

Uses existing RAG + LLM two-stage retrieval for field mapping.
This is a thin wrapper that implements the BaseFieldMapper interface.
"""

import logging
from typing import Any

from ...core.interfaces import BaseFieldMapper
from ...core.models import SemanticQuery

logger = logging.getLogger(__name__)


class TableauFieldMapper(BaseFieldMapper):
    """Tableau field mapper using RAG + LLM two-stage retrieval.
    
    Wraps existing field mapping infrastructure to implement
    the platform-agnostic BaseFieldMapper interface.
    """
    
    def __init__(
        self,
        semantic_mapper: Any = None,
        datasource_id: str | None = None,
    ):
        """Initialize Tableau field mapper.
        
        Args:
            semantic_mapper: Existing SemanticMapper instance (lazy loaded if None)
            datasource_id: Default datasource ID for field lookup
        """
        self._semantic_mapper = semantic_mapper
        self._datasource_id = datasource_id
    
    def _get_semantic_mapper(self):
        """Get or create semantic mapper."""
        if self._semantic_mapper is None:
            try:
                from tableau_assistant.src.infra.ai.rag.semantic_mapper import (
                    SemanticMapper,
                )
                self._semantic_mapper = SemanticMapper()
            except ImportError:
                logger.warning("SemanticMapper not available, using mock")
                self._semantic_mapper = MockSemanticMapper()
        return self._semantic_mapper
    
    async def map(
        self,
        semantic_query: SemanticQuery,
        **kwargs: Any,
    ) -> SemanticQuery:
        """Map all business terms in SemanticQuery to Tableau field names.
        
        Args:
            semantic_query: Query with business terms
            **kwargs: Additional parameters (e.g., datasource_id, metadata)
            
        Returns:
            SemanticQuery with mapped field names
        """
        datasource_id = kwargs.get("datasource_id", self._datasource_id)
        metadata = kwargs.get("metadata")
        
        # Collect all business terms to map
        terms_to_map = []
        
        if semantic_query.dimensions:
            for dim in semantic_query.dimensions:
                terms_to_map.append(dim.field_name)
        
        if semantic_query.measures:
            for measure in semantic_query.measures:
                terms_to_map.append(measure.field_name)
        
        if semantic_query.computations:
            for comp in semantic_query.computations:
                terms_to_map.append(comp.target)
                # partition_by is now list[DimensionField], extract field_name from each
                for p in comp.partition_by:
                    field_name = p.field_name if hasattr(p, 'field_name') else p
                    terms_to_map.append(field_name)
        
        # Remove duplicates while preserving order
        unique_terms = list(dict.fromkeys(terms_to_map))
        
        # Map all terms
        mapper = self._get_semantic_mapper()
        mapping = {}
        
        for term in unique_terms:
            mapped = await self.map_single_field(
                term,
                datasource_id=datasource_id,
                metadata=metadata,
            )
            mapping[term] = mapped
        
        # Apply mapping to query
        return self._apply_mapping(semantic_query, mapping)
    
    async def map_single_field(
        self,
        field_name: str,
        **kwargs: Any,
    ) -> str:
        """Map a single business term to Tableau field name.
        
        Args:
            field_name: Business term to map
            **kwargs: Additional parameters
            
        Returns:
            Mapped Tableau field name
        """
        datasource_id = kwargs.get("datasource_id", self._datasource_id)
        metadata = kwargs.get("metadata")
        
        mapper = self._get_semantic_mapper()
        
        try:
            # Use existing semantic mapper
            result = await mapper.map_field(
                business_term=field_name,
                datasource_id=datasource_id,
                metadata=metadata,
            )
            
            if result and result.get("field_caption"):
                return result["field_caption"]
            
            # Fallback: return original term
            logger.warning(f"Could not map field '{field_name}', using original")
            return field_name
            
        except Exception as e:
            logger.error(f"Field mapping failed for '{field_name}': {e}")
            return field_name
    
    def _apply_mapping(
        self,
        query: SemanticQuery,
        mapping: dict[str, str],
    ) -> SemanticQuery:
        """Apply field mapping to SemanticQuery.
        
        Creates a new SemanticQuery with mapped field names.
        """
        # Create copies with mapped names
        new_dimensions = None
        if query.dimensions:
            new_dimensions = []
            for dim in query.dimensions:
                new_dim = dim.model_copy()
                new_dim.field_name = mapping.get(dim.field_name, dim.field_name)
                new_dimensions.append(new_dim)
        
        new_measures = None
        if query.measures:
            new_measures = []
            for measure in query.measures:
                new_measure = measure.model_copy()
                new_measure.field_name = mapping.get(measure.field_name, measure.field_name)
                new_measures.append(new_measure)
        
        new_computations = None
        if query.computations:
            new_computations = []
            for comp in query.computations:
                new_comp = comp.model_copy(deep=True)
                new_comp.target = mapping.get(comp.target, comp.target)
                # partition_by is now list[DimensionField], map field_name within each
                new_partition_by = []
                for p in comp.partition_by:
                    if hasattr(p, 'field_name'):
                        # It's a DimensionField, create a new one with mapped field_name
                        from ...core.models import DimensionField
                        new_p = DimensionField(
                            field_name=mapping.get(p.field_name, p.field_name),
                            date_granularity=p.date_granularity,
                            alias=p.alias,
                            sort=p.sort,
                        )
                        new_partition_by.append(new_p)
                    else:
                        # Backward compatibility: it's a string
                        new_partition_by.append(mapping.get(p, p))
                new_comp.partition_by = new_partition_by
                new_computations.append(new_comp)
        
        # Create new query with mapped fields
        return SemanticQuery(
            dimensions=new_dimensions,
            measures=new_measures,
            computations=new_computations,
            filters=query.filters,  # TODO: Map filter fields
            sorts=query.sorts,
            row_limit=query.row_limit,
        )


class MockSemanticMapper:
    """Mock semantic mapper for testing."""
    
    async def map_field(
        self,
        business_term: str,
        datasource_id: str | None = None,
        metadata: Any = None,
    ) -> dict:
        """Mock field mapping - returns original term."""
        logger.warning(f"Using mock mapper for '{business_term}'")
        return {"field_caption": business_term}
