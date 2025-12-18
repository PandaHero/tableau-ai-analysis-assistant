"""Validation and result models.

Models for validation errors, results, and query execution results.
Used by platform adapters for validation and error reporting.
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ValidationErrorType(str, Enum):
    """Type of validation error."""
    MISSING_REQUIRED = "MISSING_REQUIRED"
    INVALID_VALUE = "INVALID_VALUE"
    INVALID_TYPE = "INVALID_TYPE"
    CONSTRAINT_VIOLATION = "CONSTRAINT_VIOLATION"
    FIELD_NOT_FOUND = "FIELD_NOT_FOUND"
    INCOMPATIBLE = "INCOMPATIBLE"


class ValidationError(BaseModel):
    """Validation error details."""
    model_config = ConfigDict(extra="forbid")
    
    error_type: ValidationErrorType = Field(
        description="Type of validation error"
    )
    
    field_path: str = Field(
        description="Path to the field with error, e.g., 'computations[0].partition_by'"
    )
    
    message: str = Field(
        description="Human-readable error message"
    )
    
    suggestion: str | None = Field(
        default=None,
        description="Suggested fix for the error"
    )


class ValidationResult(BaseModel):
    """Result of validation.
    
    Used by platform adapters to report validation results.
    """
    model_config = ConfigDict(extra="forbid")
    
    is_valid: bool = Field(
        description="Whether validation passed"
    )
    
    errors: list[ValidationError] = Field(
        default_factory=list,
        description="List of validation errors"
    )
    
    warnings: list[ValidationError] = Field(
        default_factory=list,
        description="List of validation warnings (non-blocking)"
    )
    
    auto_fixed: list[str] = Field(
        default_factory=list,
        description="List of fields that were auto-fixed"
    )


class ColumnInfo(BaseModel):
    """Column information in query result."""
    model_config = ConfigDict(extra="forbid")
    
    name: str = Field(
        description="Column name"
    )
    
    data_type: str = Field(
        description="Data type of the column"
    )
    
    is_dimension: bool = Field(
        default=False,
        description="Whether this is a dimension column"
    )
    
    is_measure: bool = Field(
        default=False,
        description="Whether this is a measure column"
    )
    
    is_computation: bool = Field(
        default=False,
        description="Whether this is a computed column"
    )


class QueryResult(BaseModel):
    """Query execution result.
    
    Returned by platform adapters after executing a query.
    """
    model_config = ConfigDict(extra="forbid")
    
    columns: list[ColumnInfo] = Field(
        description="Column information"
    )
    
    rows: list[dict[str, Any]] = Field(
        description="Query result rows"
    )
    
    row_count: int = Field(
        description="Total number of rows returned"
    )
    
    execution_time_ms: int | None = Field(
        default=None,
        description="Query execution time in milliseconds"
    )
