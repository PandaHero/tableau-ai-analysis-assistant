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
        description="""<what>Type of validation error</what>
<when>ALWAYS required</when>"""
    )
    
    field_path: str = Field(
        description="""<what>Path to the field with error</what>
<when>ALWAYS required</when>
<rule>Use dot notation, e.g., 'computations[0].partition_by'</rule>"""
    )
    
    message: str = Field(
        description="""<what>Human-readable error message</what>
<when>ALWAYS required</when>"""
    )
    
    suggestion: str | None = Field(
        default=None,
        description="""<what>Suggested fix for the error</what>
<when>Optional, when fix is known</when>"""
    )


class ValidationResult(BaseModel):
    """Result of validation.
    
    Used by platform adapters to report validation results.
    """
    model_config = ConfigDict(extra="forbid")
    
    is_valid: bool = Field(
        description="""<what>Whether validation passed</what>
<when>ALWAYS required</when>"""
    )
    
    errors: list[ValidationError] = Field(
        default_factory=list,
        description="""<what>List of validation errors</what>
<when>When is_valid=False</when>"""
    )
    
    warnings: list[ValidationError] = Field(
        default_factory=list,
        description="""<what>List of validation warnings (non-blocking)</what>
<when>Optional, for non-critical issues</when>"""
    )
    
    auto_fixed: list[str] = Field(
        default_factory=list,
        description="""<what>List of fields that were auto-fixed</what>
<when>When auto-correction was applied</when>"""
    )


class ColumnInfo(BaseModel):
    """Column information in query result."""
    model_config = ConfigDict(extra="forbid")
    
    name: str = Field(
        description="""<what>Column name</what>
<when>ALWAYS required</when>"""
    )
    
    data_type: str = Field(
        description="""<what>Data type of the column</what>
<when>ALWAYS required</when>"""
    )
    
    is_dimension: bool = Field(
        default=False,
        description="""<what>Whether this is a dimension column</what>
<when>Default False</when>"""
    )
    
    is_measure: bool = Field(
        default=False,
        description="""<what>Whether this is a measure column</what>
<when>Default False</when>"""
    )
    
    is_computation: bool = Field(
        default=False,
        description="""<what>Whether this is a computed column</what>
<when>Default False</when>"""
    )


class QueryResult(BaseModel):
    """Query execution result.
    
    Returned by platform adapters after executing a query.
    """
    model_config = ConfigDict(extra="forbid")
    
    columns: list[ColumnInfo] = Field(
        description="""<what>Column information</what>
<when>ALWAYS required</when>"""
    )
    
    rows: list[dict[str, Any]] = Field(
        description="""<what>Query result rows</what>
<when>ALWAYS required</when>"""
    )
    
    row_count: int = Field(
        description="""<what>Total number of rows returned</what>
<when>ALWAYS required</when>"""
    )
    
    execution_time_ms: int | None = Field(
        default=None,
        description="""<what>Query execution time in milliseconds</what>
<when>Optional, for performance tracking</when>"""
    )
