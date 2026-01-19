"""Pipeline models - QueryPipeline execution result models.

Defines QueryPipeline output models including success results and error types.
PipelineResult extends ExecuteResult with pipeline-specific fields.
"""

from typing import Any, Dict, List, Optional
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field

from tableau_assistant.src.agents.semantic_parser.models.step1 import Step1Output
from tableau_assistant.src.agents.semantic_parser.models.step2 import Step2Output
from tableau_assistant.src.core.models import IntentType
from tableau_assistant.src.core.models.execute_result import ExecuteResult



class QueryErrorType(str, Enum):
    """Query error types."""
    # Step1/Step2 errors
    STEP1_FAILED = "step1_failed"
    STEP1_PARSE_ERROR = "step1_parse_error"  # 新增：Step1 解析失败
    STEP2_FAILED = "step2_failed"
    STEP2_PARSE_ERROR = "step2_parse_error"  # 新增：Step2 解析失败
    
    # Field mapping errors
    FIELD_NOT_FOUND = "field_not_found"
    AMBIGUOUS_FIELD = "ambiguous_field"
    NO_METADATA = "no_metadata"
    MAPPING_FAILED = "mapping_failed"
    
    # Query build errors
    INVALID_COMPUTATION = "invalid_computation"
    UNSUPPORTED_OPERATION = "unsupported_operation"
    BUILD_FAILED = "build_failed"
    
    # Execution errors
    EXECUTION_FAILED = "execution_failed"
    TIMEOUT = "timeout"
    AUTH_ERROR = "auth_error"
    INVALID_QUERY = "invalid_query"
    
    # Generic errors
    UNKNOWN = "unknown"


class QueryError(BaseModel):
    """Query error model.
    
    Returned as structured error when any step in QueryPipeline fails.
    """
    model_config = ConfigDict(extra="forbid")
    
    type: QueryErrorType = Field(
        description="Error type"
    )
    
    message: str = Field(
        description="User-friendly error message"
    )
    
    step: str = Field(
        description="Step where error occurred (step1, step2, map_fields, build_query, execute_query)"
    )
    
    details: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Detailed error info (e.g., field suggestions, original error)"
    )
    
    can_retry: bool = Field(
        default=False,
        description="Whether retry is possible (used for ReAct decision)"
    )
    
    suggestion: Optional[str] = Field(
        default=None,
        description="Fix suggestion"
    )
    
    def to_user_message(self) -> str:
        """Generate user-friendly error message."""
        msg = self.message
        if self.suggestion:
            msg += f" Suggestion: {self.suggestion}"
        return msg


class PipelineResult(ExecuteResult):
    """QueryPipeline execution result.
    
    Extends ExecuteResult with pipeline-specific fields for intermediate results,
    error handling, and clarification support.
    
    Inheritance from ExecuteResult:
    - data: List[RowData] - Query result data
    - columns: List[ColumnInfo] - Column metadata with semantic info
    - row_count: int - Number of rows returned
    - execution_time_ms: int - Execution time in milliseconds
    - error: Optional[str] - Simple error message
    - query_id: Optional[str] - Query ID
    - timestamp: str - Execution timestamp
    
    PipelineResult adds:
    - success: bool - Pipeline success status
    - step1_output, step2_output - Intermediate LLM outputs
    - semantic_query, mapped_query, vizql_query - Query transformation stages
    - pipeline_error: QueryError - Structured error info
    - clarification - User clarification support
    """
    model_config = ConfigDict(extra="allow")  # Allow extra fields for intermediate results
    
    # Pipeline status
    success: bool = Field(
        default=True,
        description="Whether execution succeeded"
    )
    
    # Intermediate results (for debugging and ReAct)
    step1_output: Optional["Step1Output"] = Field(
        default=None,
        description="Step 1 output (semantic understanding)"
    )
    
    step2_output: Optional["Step2Output"] = Field(
        default=None,
        description="Step 2 output (computation reasoning)"
    )
    
    intent_type: Optional["IntentType"] = Field(
        default=None,
        description="Intent type from Step 1"
    )
    
    semantic_query: Optional[Dict[str, Any]] = Field(
        default=None,
        description="SemanticQuery generated from Step1/Step2"
    )
    
    mapped_query: Optional[Dict[str, Any]] = Field(
        default=None,
        description="MappedQuery after field mapping"
    )
    
    vizql_query: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Built VizQL query"
    )
    
    # Large result handling
    file_path: Optional[str] = Field(
        default=None,
        description="File path for large result set"
    )
    
    is_large_result: bool = Field(
        default=False,
        description="Whether result is large"
    )
    
    # Structured error info (more detailed than ExecuteResult.error)
    pipeline_error: Optional[QueryError] = Field(
        default=None,
        description="Structured error info (on failure)"
    )
    
    # Clarification (when filter values not found)
    needs_clarification: bool = Field(
        default=False,
        description="Whether clarification is needed (e.g., filter value not found)"
    )
    
    clarification: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Clarification info (type, message, field, user_values, available_values)"
    )
    
    @classmethod
    def ok(
        cls,
        data: List[Dict[str, Any]],
        columns: Optional[List[Dict[str, Any]]] = None,
        row_count: int = 0,
        semantic_query: Optional[Dict[str, Any]] = None,
        mapped_query: Optional[Dict[str, Any]] = None,
        vizql_query: Optional[Dict[str, Any]] = None,
        file_path: Optional[str] = None,
        is_large_result: bool = False,
        execution_time_ms: int = 0
    ) -> "PipelineResult":
        """Create success response."""
        return cls(
            success=True,
            data=data,
            columns=columns or [],
            row_count=row_count,
            semantic_query=semantic_query,
            mapped_query=mapped_query,
            vizql_query=vizql_query,
            file_path=file_path,
            is_large_result=is_large_result,
            execution_time_ms=execution_time_ms
        )
    
    @classmethod
    def fail(
        cls,
        error: QueryError,
        semantic_query: Optional[Dict[str, Any]] = None,
        mapped_query: Optional[Dict[str, Any]] = None,
        vizql_query: Optional[Dict[str, Any]] = None,
        execution_time_ms: int = 0
    ) -> "PipelineResult":
        """Create failure response."""
        return cls(
            success=False,
            error=error.message,  # Simple error message for ExecuteResult.error
            pipeline_error=error,  # Structured error for pipeline
            semantic_query=semantic_query,
            mapped_query=mapped_query,
            vizql_query=vizql_query,
            execution_time_ms=execution_time_ms
        )


__all__ = [
    "PipelineResult",
    "QueryError",
    "QueryErrorType",
]
