"""QueryPipeline - Core query execution pipeline.

This component executes the post-semantic-understanding pipeline:
    MapFields → BuildQuery → ExecuteQuery

Note: Step1 and Step2 are handled by separate LangGraph nodes in subgraph.py.
This separation enables ReAct error handling to retry from specific steps.

Pipeline Flow:
    1. MapFields: Map semantic fields to physical fields (RAG+LLM hybrid)
    2. BuildQuery: Build VizQL query from mapped fields
    3. ExecuteQuery: Execute query against Tableau

Middleware Integration Points:
- MapFields: call_tool_with_middleware
  - ToolRetryMiddleware: Tool call retry (network/API errors only)
- ExecuteQuery: call_tool_with_middleware
  - ToolRetryMiddleware: Tool call retry
  - FilesystemMiddleware: Large result handling
  - HumanInTheLoopMiddleware: Human confirmation (optional)

Error Handling:
- Errors are returned as structured QueryError
- ReAct error handler in subgraph.py handles retry decisions

Architecture:
- QueryPipeline: MapFields → BuildQuery → ExecuteQuery only
- step1_node/step2_node: Separate LangGraph nodes in subgraph.py
- react_error_handler_node: Handles errors and decides retry target
"""

import logging
import time
from typing import Any, Dict, List, Optional

from langgraph.types import RunnableConfig

from ..models.pipeline import QueryResult, QueryError, QueryErrorType
from ..models import Step1Output, Step2Output
from ....core.models import SemanticQuery
from ....core.models.data_model import DataModel
from ....agents.base import (
    MiddlewareRunner,
    Runtime,
)

logger = logging.getLogger(__name__)


class QueryPipeline:
    """Query execution pipeline: MapFields → BuildQuery → ExecuteQuery.
    
    This pipeline executes the post-semantic-understanding steps.
    Step1 and Step2 are handled by separate LangGraph nodes.
    
    Field mapping uses existing RAG+LLM hybrid strategy:
    1. Cache check (LangGraph SqliteStore)
    2. RAG retrieval (confidence >= 0.9 → direct return)
    3. LLM Fallback (confidence < 0.9 → select from candidates)
    4. RAG unavailable → LLM Only
    
    Attributes:
        middleware_runner: MiddlewareRunner instance for hook execution
        runtime: Runtime context for middleware
    """
    
    def __init__(
        self,
        middleware_runner: Optional[MiddlewareRunner] = None,
        runtime: Optional[Runtime] = None,
    ):
        """Initialize QueryPipeline.
        
        Args:
            middleware_runner: MiddlewareRunner for middleware execution
            runtime: Runtime context (built from config)
        """
        self.runner = middleware_runner
        self.runtime = runtime
    
    async def execute(
        self,
        question: str,
        step1_output: Step1Output,
        step2_output: Optional[Step2Output] = None,
        data_model: Optional[DataModel] = None,
        datasource_luid: str = "default",
        state: Optional[Dict[str, Any]] = None,
        config: Optional[RunnableConfig] = None,
    ) -> QueryResult:
        """Execute the query pipeline: MapFields → BuildQuery → ExecuteQuery.
        
        Supports retry from map_fields or build_query by checking state:
        - If mapped_query exists in state, skip MapFields
        - If vizql_query exists in state, skip BuildQuery
        
        Error feedback is passed via state["error_feedback"]:
        - step: Which step the feedback is for
        - feedback: The error feedback message
        
        Args:
            question: User's question (for context in field mapping)
            step1_output: Output from Step 1 (required)
            step2_output: Output from Step 2 (optional, for complex queries)
            data_model: Data source model
            datasource_luid: Data source identifier
            state: Current workflow state (may contain outputs from previous steps)
            config: LangGraph RunnableConfig
        
        Returns:
            QueryResult with success/error status and data
        """
        start_time = time.time()
        current_state = dict(state) if state else {}
        
        # Extract error feedback if present
        error_feedback_info = current_state.pop("error_feedback", None)
        
        # Track intermediate results - use existing from state if available
        mapped_query_dict: Optional[Dict[str, Any]] = current_state.get("mapped_query")
        vizql_query_dict: Optional[Dict[str, Any]] = current_state.get("vizql_query")
        
        # Get error feedback for specific step
        def get_error_feedback(step: str) -> Optional[str]:
            if error_feedback_info and error_feedback_info.get("step") == step:
                return error_feedback_info.get("feedback")
            return None
        
        # Build SemanticQuery from Step1 + Step2
        semantic_query = self._build_semantic_query(step1_output, step2_output)
        
        try:
            # ═══════════════════════════════════════════════════════════════
            # MapFields: Field mapping (RAG+LLM hybrid, skip if done)
            # ═══════════════════════════════════════════════════════════════
            if mapped_query_dict is None:
                logger.info("QueryPipeline: Starting MapFields")
                
                map_result = await self._execute_map_fields(
                    semantic_query=semantic_query,
                    datasource_luid=datasource_luid,
                    context=question,
                    data_model=data_model,
                    config=config,
                )
                
                if map_result.error:
                    map_result.semantic_query = semantic_query.model_dump() if semantic_query else None
                    return map_result
                
                mapped_query_dict = map_result.mapped_query
            else:
                logger.info("QueryPipeline: Skipping MapFields (using existing output)")
            
            # ═══════════════════════════════════════════════════════════════
            # BuildQuery: Build VizQL query (skip if done)
            # ═══════════════════════════════════════════════════════════════
            if vizql_query_dict is None:
                logger.info("QueryPipeline: Starting BuildQuery")
                
                build_feedback = get_error_feedback("build_query")
                build_result = await self._execute_build_query(
                    mapped_query=mapped_query_dict,
                    datasource_luid=datasource_luid,
                    config=config,
                    error_feedback=build_feedback,
                )
                
                if build_result.error:
                    build_result.semantic_query = semantic_query.model_dump() if semantic_query else None
                    build_result.mapped_query = mapped_query_dict
                    return build_result
                
                vizql_query_dict = build_result.vizql_query
            else:
                logger.info("QueryPipeline: Skipping BuildQuery (using existing output)")
            
            # ═══════════════════════════════════════════════════════════════
            # ExecuteQuery: Execute VizQL query
            # ═══════════════════════════════════════════════════════════════
            logger.info("QueryPipeline: Starting ExecuteQuery")
            
            execute_result = await self._execute_query(
                vizql_query=vizql_query_dict,
                datasource_luid=datasource_luid,
                config=config,
            )
            
            # Add intermediate results
            execute_result.semantic_query = semantic_query.model_dump() if semantic_query else None
            execute_result.mapped_query = mapped_query_dict
            execute_result.vizql_query = vizql_query_dict
            execute_result.execution_time_ms = int((time.time() - start_time) * 1000)
            
            return execute_result
            
        except Exception as e:
            logger.error(f"QueryPipeline failed: {e}", exc_info=True)
            execution_time_ms = int((time.time() - start_time) * 1000)
            
            return QueryResult.fail(
                error=QueryError(
                    type=QueryErrorType.UNKNOWN,
                    message=f"Pipeline execution failed: {e}",
                    step="pipeline",
                    can_retry=False,
                ),
                semantic_query=semantic_query.model_dump() if semantic_query else None,
                mapped_query=mapped_query_dict,
                vizql_query=vizql_query_dict,
                execution_time_ms=execution_time_ms,
            )

    
    # ═══════════════════════════════════════════════════════════════════════
    # Step Execution Methods
    # ═══════════════════════════════════════════════════════════════════════
    
    async def _execute_map_fields(
        self,
        semantic_query: SemanticQuery,
        datasource_luid: str,
        context: Optional[str],
        data_model: Optional[DataModel],
        config: Optional[RunnableConfig],
    ) -> QueryResult:
        """Execute MapFields tool.
        
        Uses call_tool_with_middleware for:
        - ToolRetryMiddleware (network/API errors only)
        
        Field mapping uses existing RAG+LLM hybrid strategy:
        1. Cache check
        2. RAG retrieval (confidence >= 0.9 → direct return)
        3. LLM Fallback
        4. RAG unavailable → LLM Only
        
        Args:
            semantic_query: SemanticQuery to map
            datasource_luid: Data source identifier
            context: User question context
            data_model: Data model for field mapping
            config: LangGraph config
        
        Returns:
            QueryResult with mapped_query or error
        """
        try:
            from ....orchestration.tools.map_fields import map_fields_async
            
            result = await map_fields_async(
                semantic_query=semantic_query.model_dump(),
                datasource_luid=datasource_luid,
                context=context,
                data_model=data_model,
                config=config,
            )
            
            if not result.success:
                error = result.error
                error_type = self._map_field_error_type(error.type if error else None)
                
                return QueryResult.fail(
                    error=QueryError(
                        type=error_type,
                        message=error.message if error else "Field mapping failed",
                        step="map_fields",
                        can_retry=error_type in (QueryErrorType.MAPPING_FAILED,),
                        details={
                            "field": error.field if error else None,
                            "suggestions": [s.model_dump() for s in error.suggestions] if error and error.suggestions else None,
                        },
                        suggestion=self._build_field_suggestion(error) if error else None,
                    ),
                )
            
            return QueryResult(
                success=True,
                mapped_query=result.mapped_query,
            )
            
        except Exception as e:
            logger.error(f"MapFields failed: {e}", exc_info=True)
            return QueryResult.fail(
                error=QueryError(
                    type=QueryErrorType.MAPPING_FAILED,
                    message=f"Field mapping failed: {e}",
                    step="map_fields",
                    can_retry=False,
                ),
            )
    
    async def _execute_build_query(
        self,
        mapped_query: Dict[str, Any],
        datasource_luid: str,
        config: Optional[RunnableConfig],
        error_feedback: Optional[str] = None,
    ) -> QueryResult:
        """Execute BuildQuery tool.
        
        Pure logic, no middleware needed.
        Note: error_feedback is accepted but not used directly here.
        Build errors typically require going back to step1/step2.
        
        Args:
            mapped_query: MappedQuery dict
            datasource_luid: Data source identifier
            config: LangGraph config
            error_feedback: Feedback from previous error (for logging)
        
        Returns:
            QueryResult with vizql_query or error
        """
        try:
            if error_feedback:
                logger.info(f"BuildQuery retry with feedback: {error_feedback[:100]}...")
            
            from ....orchestration.tools.build_query import build_query_async
            
            result = await build_query_async(
                mapped_query=mapped_query,
                datasource_luid=datasource_luid,
                config=config,
            )
            
            if not result.success:
                error = result.error
                error_type = self._map_build_error_type(error.type if error else None)
                
                return QueryResult.fail(
                    error=QueryError(
                        type=error_type,
                        message=error.message if error else "Query build failed",
                        step="build_query",
                        can_retry=False,
                    ),
                )
            
            return QueryResult(
                success=True,
                vizql_query=result.vizql_query,
            )
            
        except Exception as e:
            logger.error(f"BuildQuery failed: {e}", exc_info=True)
            return QueryResult.fail(
                error=QueryError(
                    type=QueryErrorType.BUILD_FAILED,
                    message=f"Query build failed: {e}",
                    step="build_query",
                    can_retry=False,
                ),
            )
    
    async def _execute_query(
        self,
        vizql_query: Dict[str, Any],
        datasource_luid: str,
        config: Optional[RunnableConfig],
    ) -> QueryResult:
        """Execute ExecuteQuery tool.
        
        Uses call_tool_with_middleware for:
        - ToolRetryMiddleware
        - FilesystemMiddleware (large result handling)
        - HumanInTheLoopMiddleware (optional)
        
        Args:
            vizql_query: VizQL query dict
            datasource_luid: Data source identifier
            config: LangGraph config
        
        Returns:
            QueryResult with data or error
        """
        try:
            from ....orchestration.tools.execute_query import execute_query_async
            
            result = await execute_query_async(
                vizql_query=vizql_query,
                datasource_luid=datasource_luid,
                config=config,
            )
            
            if not result.success:
                error = result.error
                error_type = self._map_execute_error_type(error.type if error else None)
                
                return QueryResult.fail(
                    error=QueryError(
                        type=error_type,
                        message=error.message if error else "Query execution failed",
                        step="execute_query",
                        can_retry=error_type == QueryErrorType.TIMEOUT,
                        suggestion=error.suggestion if error else None,
                    ),
                )
            
            return QueryResult.ok(
                data=result.data or [],
                columns=result.columns,
                row_count=result.row_count,
                file_path=result.file_path,
                is_large_result=result.is_large_result,
            )
            
        except Exception as e:
            logger.error(f"ExecuteQuery failed: {e}", exc_info=True)
            return QueryResult.fail(
                error=QueryError(
                    type=QueryErrorType.EXECUTION_FAILED,
                    message=f"Query execution failed: {e}",
                    step="execute_query",
                    can_retry=False,
                ),
            )

    
    # ═══════════════════════════════════════════════════════════════════════
    # Helper Methods
    # ═══════════════════════════════════════════════════════════════════════
    
    def _build_semantic_query(
        self,
        step1_output: Step1Output,
        step2_output: Optional[Step2Output],
    ) -> SemanticQuery:
        """Build SemanticQuery from Step1 and Step2 outputs.
        
        Step1Output uses core layer models directly:
        - step1_output.where.dimensions: list[DimensionField]
        - step1_output.what.measures: list[MeasureField]
        - step1_output.where.filters: list[Filter]
        
        Sorts are embedded in DimensionField.sort and MeasureField.sort.
        
        Args:
            step1_output: Step 1 output
            step2_output: Step 2 output (optional, for complex queries)
        
        Returns:
            SemanticQuery
        """
        # Use Step1's dimensions directly (already DimensionField)
        dimensions = step1_output.where.dimensions if step1_output.where.dimensions else None
        
        # Use Step1's measures directly (already MeasureField)
        measures = step1_output.what.measures if step1_output.what.measures else None
        
        # Convert Step1's filters to specific filter types for SemanticQuery
        filters = None
        if step1_output.where.filters:
            filters = self._convert_filters(step1_output.where.filters)
        
        # Get computations from Step2 if available
        computations = step2_output.computations if step2_output else None
        
        return SemanticQuery(
            dimensions=dimensions,
            measures=measures,
            computations=computations,
            filters=filters,
        )
    
    def _convert_filters(self, filters: list) -> list:
        """Pass through filters (already specific types from Step1).
        
        Step1Output.Where.filters now uses FilterUnion type directly,
        so filters are already the correct specific types.
        
        Args:
            filters: List of specific filter type instances from Step1Output
        
        Returns:
            Same list (no conversion needed)
        """
        return filters if filters else None
    
    def _map_field_error_type(self, error_type: Optional[str]) -> QueryErrorType:
        """Map field mapping error type to QueryErrorType."""
        if not error_type:
            return QueryErrorType.MAPPING_FAILED
        
        mapping = {
            "field_not_found": QueryErrorType.FIELD_NOT_FOUND,
            "ambiguous_field": QueryErrorType.AMBIGUOUS_FIELD,
            "no_metadata": QueryErrorType.NO_METADATA,
            "mapping_failed": QueryErrorType.MAPPING_FAILED,
        }
        return mapping.get(error_type, QueryErrorType.MAPPING_FAILED)
    
    def _map_build_error_type(self, error_type: Optional[str]) -> QueryErrorType:
        """Map build query error type to QueryErrorType."""
        if not error_type:
            return QueryErrorType.BUILD_FAILED
        
        mapping = {
            "invalid_computation": QueryErrorType.INVALID_COMPUTATION,
            "unsupported_operation": QueryErrorType.UNSUPPORTED_OPERATION,
            "build_failed": QueryErrorType.BUILD_FAILED,
            "validation_failed": QueryErrorType.BUILD_FAILED,
            "missing_input": QueryErrorType.BUILD_FAILED,
        }
        return mapping.get(error_type, QueryErrorType.BUILD_FAILED)
    
    def _map_execute_error_type(self, error_type: Optional[str]) -> QueryErrorType:
        """Map execute query error type to QueryErrorType."""
        if not error_type:
            return QueryErrorType.EXECUTION_FAILED
        
        mapping = {
            "execution_failed": QueryErrorType.EXECUTION_FAILED,
            "timeout": QueryErrorType.TIMEOUT,
            "auth_error": QueryErrorType.AUTH_ERROR,
            "invalid_query": QueryErrorType.INVALID_QUERY,
            "api_error": QueryErrorType.EXECUTION_FAILED,
            "missing_input": QueryErrorType.EXECUTION_FAILED,
        }
        return mapping.get(error_type, QueryErrorType.EXECUTION_FAILED)
    
    def _build_field_suggestion(self, error: Any) -> Optional[str]:
        """Build suggestion message from field mapping error."""
        if not error or not error.suggestions:
            return None
        
        suggestions = error.suggestions[:3]  # Top 3 suggestions
        if not suggestions:
            return None
        
        suggestion_names = [s.field_name for s in suggestions if s.field_name]
        if suggestion_names:
            return f"Did you mean: {', '.join(suggestion_names)}?"
        
        return None


__all__ = ["QueryPipeline"]
