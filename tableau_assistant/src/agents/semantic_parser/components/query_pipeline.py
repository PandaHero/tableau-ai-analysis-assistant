"""QueryPipeline - Core query execution pipeline.

This component executes the post-semantic-understanding pipeline:
    MapFields → BuildQuery → ExecuteQuery

Note: Step1 and Step2 are handled by separate LangGraph nodes in subgraph.py.
This separation enables ReAct error handling to retry from specific steps.

Pipeline Flow:
    1. MapFields: Map semantic fields to physical fields (RAG+LLM hybrid)
    2. BuildQuery: Build VizQL query from mapped fields
    3. ExecuteQuery: Execute query against Tableau

Middleware Integration Points (Requirements 0.3):
All tool calls go through MiddlewareRunner.run_tool() for:
- ToolRetryMiddleware: Tool call retry (network/API errors)
- FilesystemMiddleware: Large result handling
- HumanInTheLoopMiddleware: Human confirmation (optional)
- Observability: Timing, logging, metrics

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
from typing import Any, Awaitable, Callable, Dict, List, Optional, TypeVar

from langgraph.types import RunnableConfig

from tableau_assistant.src.agents.semantic_parser.models.pipeline import PipelineResult, QueryError, QueryErrorType
from tableau_assistant.src.agents.semantic_parser.models import Step1Output, Step2Output
from tableau_assistant.src.core.models import SemanticQuery
from tableau_assistant.src.infra.storage.data_model import DataModel
from tableau_assistant.src.agents.field_mapper.models import MappedQuery
from tableau_assistant.src.agents.base import (
    MiddlewareRunner,
    Runtime,
    get_middleware_from_config,
)
from tableau_assistant.src.infra.observability import get_metrics_from_config


logger = logging.getLogger(__name__)

# Type variable for generic tool result
T = TypeVar('T')


class QueryPipeline:
    """Query execution pipeline: MapFields → BuildQuery → ExecuteQuery.
    
    This pipeline executes the post-semantic-understanding steps.
    Step1 and Step2 are handled by separate LangGraph nodes.
    
    Field mapping uses existing RAG+LLM hybrid strategy:
    1. Cache check (LangGraph SqliteStore)
    2. RAG retrieval (confidence >= 0.9 → direct return)
    3. LLM Fallback (confidence < 0.9 → select from candidates)
    4. RAG unavailable → LLM Only
    
    Middleware Integration (Requirements 0.3):
    All tool calls go through _run_tool_with_middleware() which:
    - Wraps tool calls with MiddlewareRunner.wrap_tool_call()
    - Enables retry, logging, and observability for all pipeline steps
    - Falls back to direct call if no middleware is configured
    
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
            middleware_runner: MiddlewareRunner for middleware execution.
                              If None, will try to get from config during execute().
            runtime: Runtime context (built from config).
                    If None, will be built from config during execute().
        """
        self.runner = middleware_runner
        self.runtime = runtime
    
    def _ensure_middleware_runner(
        self,
        config: Optional[RunnableConfig],
    ) -> Optional[MiddlewareRunner]:
        """Ensure MiddlewareRunner is available.
        
        Priority:
        1. Use instance runner if set
        2. Try to get from config
        3. Return None (direct calls will be used)
        
        Args:
            config: LangGraph RunnableConfig
            
        Returns:
            MiddlewareRunner or None
        """
        if self.runner is not None:
            return self.runner
        
        # Try to get middleware from config
        if config:
            middleware_list = get_middleware_from_config(config)
            if middleware_list:
                self.runner = MiddlewareRunner(middleware=middleware_list)
                logger.debug(f"Created MiddlewareRunner from config with {len(middleware_list)} middleware")
                return self.runner
        
        return None
    
    def _ensure_runtime(
        self,
        config: Optional[RunnableConfig],
    ) -> Runtime:
        """Ensure Runtime is available.
        
        Args:
            config: LangGraph RunnableConfig
            
        Returns:
            Runtime instance
        """
        if self.runtime is not None:
            return self.runtime
        
        # Build runtime from config
        if self.runner is not None:
            self.runtime = self.runner.build_runtime(config=config or {})
        else:
            self.runtime = Runtime(config=config or {})
        
        return self.runtime
    
    async def _run_tool_with_middleware(
        self,
        tool_name: str,
        tool_fn: Callable[..., Awaitable[T]],
        state: Dict[str, Any],
        config: Optional[RunnableConfig],
        **kwargs,
    ) -> T:
        """Run a tool function through middleware wrap_tool_call chain.
        
        This method wraps tool calls with MiddlewareRunner.wrap_tool_call() for:
        - Retry logic (ToolRetryMiddleware)
        - Large result handling (FilesystemMiddleware)
        - Human-in-the-loop (HumanInTheLoopMiddleware)
        - Observability (timing, logging)
        
        If no middleware is configured, falls back to direct call.
        
        Args:
            tool_name: Name of the tool (for logging/metrics)
            tool_fn: Async tool function to call
            state: Current workflow state (passed to middleware)
            config: LangGraph RunnableConfig
            **kwargs: Arguments to pass to tool_fn (excluding config, which is added automatically)
            
        Returns:
            Tool function result
            
        Requirements: 0.3 - Pipeline 贯通 middleware 能力
        """
        runner = self._ensure_middleware_runner(config)
        runtime = self._ensure_runtime(config)
        
        start_time = time.time()
        
        # Add config to kwargs for tools that need it
        kwargs_with_config = {**kwargs, "config": config}
        
        if runner is None:
            # No middleware configured, direct call
            logger.debug(f"[{tool_name}] No middleware configured, direct call")
            result = await tool_fn(**kwargs_with_config)
            elapsed = time.time() - start_time
            logger.debug(f"[{tool_name}] completed in {elapsed:.3f}s (direct)")
            return result
        
        logger.debug(f"[{tool_name}] Running with middleware (wrap_tool_call)")
        
        # Create a lightweight tool wrapper for the middleware system
        # This allows our async functions to work with wrap_tool_call
        from langchain_core.tools import BaseTool
        
        class AsyncFunctionTool(BaseTool):
            """Lightweight wrapper to adapt async functions to BaseTool interface.
            
            ⚠️ 实现说明（GPT-5.2 审查备注）：
            这种包装方式虽然"偏门"（unconventional），但功能正常且必要：
            
            1. 为什么需要这个包装器？
               - MiddlewareRunner.wrap_tool_call() 期望 BaseTool 接口
               - 我们的 pipeline 工具是普通的 async 函数
               - 需要一个适配器将 async 函数包装为 BaseTool
            
            2. 为什么使用 object.__setattr__？
               - BaseTool 继承自 Pydantic BaseModel
               - Pydantic 会验证所有字段，但 _tool_fn 和 _tool_kwargs 不是声明的字段
               - 使用 object.__setattr__ 绕过 Pydantic 验证，直接设置实例属性
            
            3. 替代方案考虑：
               - 可以将 pipeline 工具重构为 BaseTool 子类，但会增加代码复杂度
               - 可以修改 MiddlewareRunner 接受 Callable，但会破坏现有接口
               - 当前方案是最小侵入性的解决方案
            
            4. 风险评估：
               - 低风险：这是内部实现细节，不影响外部接口
               - 已测试：通过 middleware 链正常工作
            """
            name: str = tool_name
            description: str = f"Pipeline tool: {tool_name}"
            _tool_fn: Callable = None
            _tool_kwargs: Dict[str, Any] = None
            
            def __init__(self, fn: Callable, fn_kwargs: Dict[str, Any]):
                super().__init__()
                # 使用 object.__setattr__ 绕过 Pydantic 验证
                object.__setattr__(self, '_tool_fn', fn)
                object.__setattr__(self, '_tool_kwargs', fn_kwargs)
            
            def _run(self, *args, **run_kwargs) -> Any:
                """Sync run - not used, but required by BaseTool."""
                raise NotImplementedError("Use ainvoke instead")
            
            async def _arun(self, *args, **run_kwargs) -> Any:
                """Async run - executes the wrapped function."""
                return await self._tool_fn(**self._tool_kwargs)
        
        # Create the tool wrapper
        tool_wrapper = AsyncFunctionTool(fn=tool_fn, fn_kwargs=kwargs_with_config)
        
        # Build ToolCallRequest for middleware
        tool_call_info = {
            "name": tool_name,
            "args": kwargs_with_config,
            "id": f"{tool_name}_{int(start_time * 1000)}",
        }
        
        request = runner.build_tool_call_request(
            tool_call=tool_call_info,
            tool=tool_wrapper,
            state=state,
            runtime=runtime,
        )
        
        # Define the base handler that actually executes the tool
        async def base_tool_handler(req) -> Any:
            """Execute the actual tool function."""
            tool_instance = req.tool
            # Use _arun which calls our wrapped function
            return await tool_instance._arun()
        
        try:
            # Execute through middleware wrap_tool_call chain
            # This will invoke all wrap_tool_call/awrap_tool_call hooks
            result = await runner.wrap_tool_call(request, base_tool_handler)
            
            elapsed = time.time() - start_time
            logger.info(f"[{tool_name}] completed in {elapsed:.3f}s (with middleware)")
            
            return result
            
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"[{tool_name}] failed after {elapsed:.3f}s: {e}")
            raise
    
    async def execute(
        self,
        question: str,
        step1_output: Step1Output,
        step2_output: Optional[Step2Output] = None,
        data_model: Optional[DataModel] = None,
        datasource_luid: str = "default",
        state: Optional[Dict[str, Any]] = None,
        config: Optional[RunnableConfig] = None,
    ) -> PipelineResult:
        """Execute the query pipeline: MapFields "BuildQuery "ExecuteQuery.
        
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
            PipelineResult with success/error status and data
        """
        start_time = time.time()
        current_state = dict(state) if state else {}
        
        # Get metrics for observability (Requirements 0.5)
        metrics = get_metrics_from_config(config)
        pipeline_start_time = time.monotonic()
        
        # Extract error feedback if present
        error_feedback_info = current_state.pop("error_feedback", None)
        
        # Track intermediate results - use existing from state if available
        # 内部使用 MappedQuery 对象，state 中可能是 dict 需要转"
        mapped_query: Optional[MappedQuery] = None
        if current_state.get("mapped_query"):
            state_mq = current_state.get("mapped_query")
            if isinstance(state_mq, MappedQuery):
                mapped_query = state_mq
            elif isinstance(state_mq, dict):
                try:
                    mapped_query = MappedQuery.model_validate(state_mq)
                except Exception as e:
                    logger.warning(f"Failed to parse mapped_query from state: {e}")
        
        vizql_query_dict: Optional[Dict[str, Any]] = current_state.get("vizql_query")
        
        # Get error feedback for specific step
        def get_error_feedback(step: str) -> Optional[str]:
            if error_feedback_info and error_feedback_info.get("step") == step:
                return error_feedback_info.get("feedback")
            return None
        
        # Build SemanticQuery from Step1 + Step2
        semantic_query = self._build_semantic_query(step1_output, step2_output)
        
        try:
            # ══════════════════════════════════════════════════════════════"
            # MapFields: Field mapping (RAG+LLM hybrid, skip if done)
            # ══════════════════════════════════════════════════════════════"
            if mapped_query is None:
                logger.info("QueryPipeline: Starting MapFields")
                
                map_result = await self._execute_map_fields(
                    semantic_query=semantic_query,
                    datasource_luid=datasource_luid,
                    context=question,
                    data_model=data_model,
                    config=config,
                    current_state=current_state,
                )
                
                if map_result.error:
                    map_result.semantic_query = semantic_query.model_dump() if semantic_query else None
                    return map_result
                
                # map_result.mapped_query "dict，转换为 MappedQuery 对象
                if map_result.mapped_query:
                    mapped_query = MappedQuery.model_validate(map_result.mapped_query)
            else:
                logger.info("QueryPipeline: Skipping MapFields (using existing output)")
            
            # ══════════════════════════════════════════════════════════════"
            # ResolveFilterValues: Validate and resolve SetFilter values
            # ══════════════════════════════════════════════════════════════"
            filter_resolve_info = None
            if mapped_query:
                resolve_result = await self._resolve_filter_values(
                    mapped_query=mapped_query,
                    datasource_luid=datasource_luid,
                    config=config,
                    data_model=data_model,
                )
                
                if resolve_result:
                    # resolve_result["mapped_query"] 现在"MappedQuery 对象
                    mapped_query = resolve_result.get("mapped_query", mapped_query)
                    filter_resolve_info = resolve_result.get("resolve_info")
                    
                    if filter_resolve_info and filter_resolve_info.get("warning"):
                        logger.warning(f"Filter resolve warning: {filter_resolve_info['warning']}")
            
            # ══════════════════════════════════════════════════════════════"
            # BuildQuery: Build VizQL query (skip if done)
            # ══════════════════════════════════════════════════════════════"
            if vizql_query_dict is None:
                logger.info("QueryPipeline: Starting BuildQuery")
                
                build_feedback = get_error_feedback("build_query")
                build_result = await self._execute_build_query(
                    mapped_query=mapped_query,
                    datasource_luid=datasource_luid,
                    config=config,
                    error_feedback=build_feedback,
                    current_state=current_state,
                )
                
                if build_result.error:
                    build_result.semantic_query = semantic_query.model_dump() if semantic_query else None
                    build_result.mapped_query = mapped_query.model_dump() if mapped_query else None
                    return build_result
                
                vizql_query_dict = build_result.vizql_query
            else:
                logger.info("QueryPipeline: Skipping BuildQuery (using existing output)")
            
            # ══════════════════════════════════════════════════════════════"
            # ExecuteQuery: Execute VizQL query
            # ══════════════════════════════════════════════════════════════"
            logger.info("QueryPipeline: Starting ExecuteQuery")
            
            execute_result = await self._execute_query(
                vizql_query=vizql_query_dict,
                datasource_luid=datasource_luid,
                config=config,
                current_state=current_state,
            )
            
            # Add intermediate results (序列化为 dict 用于返回)
            execute_result.semantic_query = semantic_query.model_dump() if semantic_query else None
            execute_result.mapped_query = mapped_query.model_dump() if mapped_query else None
            execute_result.vizql_query = vizql_query_dict
            execute_result.execution_time_ms = int((time.time() - start_time) * 1000)
            
            # Record pipeline metrics (Requirements 0.5)
            if metrics is not None:
                metrics.record_pipeline_timing(pipeline_start_time)
            
            # ══════════════════════════════════════════════════════════════"
            # Check for clarification: If fallback query returned no results
            # ══════════════════════════════════════════════════════════════"
            if (execute_result.success and 
                execute_result.row_count == 0 and 
                filter_resolve_info and 
                filter_resolve_info.get("is_fallback")):
                
                # TextMatchFilter 也没有结果，触发澄清
                logger.info("QueryPipeline: Fallback query returned 0 rows, triggering clarification")
                
                execute_result.needs_clarification = True
                execute_result.clarification = {
                    "type": "FILTER_VALUE_NOT_FOUND",
                    "message": f"筛选 {filter_resolve_info.get('unmatched_values', [])} 在数据中没有找到匹配的结果",
                    "field": filter_resolve_info.get("field"),
                    "user_values": filter_resolve_info.get("unmatched_values", []),
                    "available_values": filter_resolve_info.get("available_values", []),
                }
            
            return execute_result
            
        except Exception as e:
            logger.error(f"QueryPipeline failed: {e}", exc_info=True)
            execution_time_ms = int((time.time() - start_time) * 1000)
            
            # Record pipeline metrics even on failure (Requirements 0.5)
            if metrics is not None:
                metrics.record_pipeline_timing(pipeline_start_time)
            
            return PipelineResult.fail(
                error=QueryError(
                    type=QueryErrorType.UNKNOWN,
                    message=f"Pipeline execution failed: {e}",
                    step="pipeline",
                    can_retry=False,
                ),
                semantic_query=semantic_query.model_dump() if semantic_query else None,
                mapped_query=mapped_query.model_dump() if mapped_query else None,
                vizql_query=vizql_query_dict,
                execution_time_ms=execution_time_ms,
            )

    
    # ══════════════════════════════════════════════════════════════════════"
    # Step Execution Methods
    # ══════════════════════════════════════════════════════════════════════"
    
    async def _execute_map_fields(
        self,
        semantic_query: SemanticQuery,
        datasource_luid: str,
        context: Optional[str],
        data_model: Optional[DataModel],
        config: Optional[RunnableConfig],
        current_state: Optional[Dict[str, Any]] = None,
    ) -> PipelineResult:
        """Execute MapFields tool through middleware.
        
        Uses _run_tool_with_middleware for:
        - ToolRetryMiddleware (network/API errors only)
        - Observability (timing, logging)
        
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
            PipelineResult with mapped_query or error
            
        Requirements: 0.3 - Pipeline 贯通 middleware 能力
        """
        try:
            from tableau_assistant.src.orchestration.tools.map_fields import map_fields_async

            
            # Run through middleware wrapper with actual workflow state
            result = await self._run_tool_with_middleware(
                tool_name="map_fields",
                tool_fn=map_fields_async,
                state=current_state or {},
                config=config,
                # Tool arguments
                semantic_query=semantic_query.model_dump(),
                datasource_luid=datasource_luid,
                context=context,
                data_model=data_model,
            )
            
            if not result.success:
                error = result.error
                error_type = self._map_field_error_type(error.type if error else None)
                
                return PipelineResult.fail(
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
            
            return PipelineResult(
                success=True,
                mapped_query=result.mapped_query,
            )
            
        except Exception as e:
            logger.error(f"MapFields failed: {e}", exc_info=True)
            return PipelineResult.fail(
                error=QueryError(
                    type=QueryErrorType.MAPPING_FAILED,
                    message=f"Field mapping failed: {e}",
                    step="map_fields",
                    can_retry=False,
                ),
            )
    
    async def _execute_build_query(
        self,
        mapped_query: Optional[MappedQuery],
        datasource_luid: str,
        config: Optional[RunnableConfig],
        error_feedback: Optional[str] = None,
        current_state: Optional[Dict[str, Any]] = None,
    ) -> PipelineResult:
        """Execute BuildQuery tool through middleware.
        
        Uses _run_tool_with_middleware for:
        - Observability (timing, logging)
        
        Note: error_feedback is accepted but not used directly here.
        Build errors typically require going back to step1/step2.
        
        Args:
            mapped_query: MappedQuery Pydantic 对象
            datasource_luid: Data source identifier
            config: LangGraph config
            error_feedback: Feedback from previous error (for logging)
        
        Returns:
            PipelineResult with vizql_query or error
            
        Requirements: 0.3 - Pipeline 贯通 middleware 能力
        """
        try:
            if error_feedback:
                logger.info(f"BuildQuery retry with feedback: {error_feedback[:100]}...")
            
            from tableau_assistant.src.orchestration.tools.build_query import build_query_async

            
            # Run through middleware wrapper with actual workflow state
            result = await self._run_tool_with_middleware(
                tool_name="build_query",
                tool_fn=build_query_async,
                state=current_state or {},
                config=config,
                # Tool arguments
                mapped_query=mapped_query,
                datasource_luid=datasource_luid,
            )
            
            if not result.success:
                error = result.error
                error_type = self._map_build_error_type(error.type if error else None)
                
                return PipelineResult.fail(
                    error=QueryError(
                        type=error_type,
                        message=error.message if error else "Query build failed",
                        step="build_query",
                        can_retry=False,
                    ),
                )
            
            return PipelineResult(
                success=True,
                vizql_query=result.vizql_query,
            )
            
        except Exception as e:
            logger.error(f"BuildQuery failed: {e}", exc_info=True)
            return PipelineResult.fail(
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
        current_state: Optional[Dict[str, Any]] = None,
    ) -> PipelineResult:
        """Execute ExecuteQuery tool through middleware.
        
        Uses _run_tool_with_middleware for:
        - ToolRetryMiddleware (network/API errors)
        - FilesystemMiddleware (large result handling)
        - HumanInTheLoopMiddleware (optional)
        - Observability (timing, logging)
        
        Args:
            vizql_query: VizQL query dict
            datasource_luid: Data source identifier
            config: LangGraph config
        
        Returns:
            PipelineResult with data or error
            
        Requirements: 0.3 - Pipeline 贯通 middleware 能力
        """
        try:
            from tableau_assistant.src.orchestration.tools.execute_query import execute_query_async

            
            # Run through middleware wrapper with actual workflow state
            result = await self._run_tool_with_middleware(
                tool_name="execute_query",
                tool_fn=execute_query_async,
                state=current_state or {},
                config=config,
                # Tool arguments
                vizql_query=vizql_query,
                datasource_luid=datasource_luid,
            )
            
            if not result.success:
                error = result.error
                error_type = self._map_execute_error_type(error.type if error else None)
                
                return PipelineResult.fail(
                    error=QueryError(
                        type=error_type,
                        message=error.message if error else "Query execution failed",
                        step="execute_query",
                        can_retry=error_type == QueryErrorType.TIMEOUT,
                        suggestion=error.suggestion if error else None,
                    ),
                )
            
            return PipelineResult.ok(
                data=result.data or [],
                columns=result.columns,
                row_count=result.row_count,
                file_path=result.file_path,
                is_large_result=result.is_large_result,
            )
            
        except Exception as e:
            logger.error(f"ExecuteQuery failed: {e}", exc_info=True)
            return PipelineResult.fail(
                error=QueryError(
                    type=QueryErrorType.EXECUTION_FAILED,
                    message=f"Query execution failed: {e}",
                    step="execute_query",
                    can_retry=False,
                ),
            )

    
    # ══════════════════════════════════════════════════════════════════════"
    # Helper Methods
    # ══════════════════════════════════════════════════════════════════════"
    
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
    
    async def _resolve_filter_values(
        self,
        mapped_query: "MappedQuery",
        datasource_luid: str,
        config: Optional[RunnableConfig],
        data_model: Optional[DataModel] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        解析并验"SetFilter 的"
        
        "MappedQuery 中的 SetFilter 进行值验证：
        1. "DataModel "sample_values 获取字段唯一"
        2. 精确匹配 "RAG 语义匹配
        3. 匹配成功 "使用真实"
        4. 匹配失败 "降级"TextMatchFilter（单值模糊匹配）
        
        Args:
            mapped_query: MappedQuery Pydantic 对象
            datasource_luid: 数据"LUID
            config: LangGraph 配置
            data_model: DataModel 实例（用于获"sample_values"
        
        Returns:
            {
                "mapped_query": 更新后的 MappedQuery Pydantic 对象,
                "resolve_info": {
                    "is_fallback": bool,
                    "warning": str,
                    "unmatched_values": [...],
                    "available_values": [...],
                    "field": str,
                }
            }
            如果没有 SetFilter，返"None
        """
        try:
            from tableau_assistant.src.orchestration.tools.filter_value_resolver import (
                FilterValueResolver,
                MatchFilterFallback,
            )
            from tableau_assistant.src.core.models.filters import SetFilter, TextMatchFilter
            from tableau_assistant.src.core.models.enums import TextMatchType
            
            # 获取 filters
            filters = mapped_query.semantic_query.filters
            if not filters:
                return None
            
            # 查找 SetFilter
            set_filters = []
            other_filters = []
            
            for f in filters:
                if isinstance(f, SetFilter):
                    set_filters.append(f)
                else:
                    other_filters.append(f)
            
            if not set_filters:
                return None
            
            logger.info(f"QueryPipeline: Resolving {len(set_filters)} SetFilter(s)")
            
            # 创建解析器（传入 data_model"
            resolver = FilterValueResolver(
                datasource_luid=datasource_luid,
                config=config,
                data_model=data_model,
            )
            
            # 解析每个 SetFilter
            resolved_filters = list(other_filters)  # 保留其他筛选器（Pydantic 对象"
            resolve_info = {
                "is_fallback": False,
                "warning": None,
                "unmatched_values": [],
                "available_values": [],
                "field": None,
            }
            
            for sf in set_filters:
                field_name = sf.field_name
                
                # 获取映射后的技术字段名
                mapping = mapped_query.field_mappings.get(field_name)
                technical_field = mapping.technical_field if mapping else field_name
                
                # 解析筛选"
                result = await resolver.resolve_set_filter(
                    filter_spec=sf,
                    technical_field_name=technical_field,
                )
                
                # 处理结果
                if result.is_fallback:
                    resolve_info["is_fallback"] = True
                    resolve_info["warning"] = result.warning
                    resolve_info["unmatched_values"].extend(result.unmatched_values)
                    resolve_info["available_values"] = result.available_values
                    resolve_info["field"] = field_name
                    
                    # MatchFilterFallback 需要转换为 TextMatchFilter（Pydantic 模型"
                    if isinstance(result.resolved_filter, MatchFilterFallback):
                        match_type_map = {
                            "contains": TextMatchType.CONTAINS,
                            "startsWith": TextMatchType.STARTS_WITH,
                            "endsWith": TextMatchType.ENDS_WITH,
                        }
                        text_match_type = match_type_map.get(
                            result.resolved_filter.match_type, 
                            TextMatchType.CONTAINS
                        )
                        # 创建 TextMatchFilter Pydantic 对象
                        text_match_filter = TextMatchFilter(
                            field_name=result.resolved_filter.field_name,
                            pattern=result.resolved_filter.pattern,
                            match_type=text_match_type,
                        )
                        resolved_filters.append(text_match_filter)
                        logger.info(f"MatchFilterFallback -> TextMatchFilter: {text_match_filter}")
                    else:
                        # 直接使用 Pydantic 对象
                        resolved_filters.append(result.resolved_filter)
                else:
                    # 直接使用解析后的 SetFilter Pydantic 对象
                    resolved_filters.append(result.resolved_filter)
            
            # 创建新的 SemanticQuery（使"model_copy 更新 filters"
            new_semantic_query = mapped_query.semantic_query.model_copy(update={"filters": resolved_filters})
            
            # 创建新的 MappedQuery（使"model_copy 更新 semantic_query"
            new_mapped_query = mapped_query.model_copy(update={"semantic_query": new_semantic_query})
            
            # 直接返回 Pydantic 对象，不序列"
            return {
                "mapped_query": new_mapped_query,
                "resolve_info": resolve_info,
            }
            
        except Exception as e:
            logger.error(f"Resolve filter values failed: {e}", exc_info=True)
            return None


__all__ = ["QueryPipeline"]
