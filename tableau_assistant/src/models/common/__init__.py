"""
Common models - Shared data structures

Contains:
- errors.py: Error types and handling (TransientError, PermanentError, UserError)
"""

from .errors import (
    # Error types
    TransientError,
    PermanentError,
    UserError,
    ErrorCategory,
    ErrorDetail,
    ErrorHandler,
    # Functions
    classify_error,
    wrap_error,
    is_retryable,
    get_retry_delay,
    format_user_message,
    log_error,
)

__all__ = [
    # Error types
    "TransientError",
    "PermanentError",
    "UserError",
    "ErrorCategory",
    "ErrorDetail",
    "ErrorHandler",
    # Functions
    "classify_error",
    "wrap_error",
    "is_retryable",
    "get_retry_delay",
    "format_user_message",
    "log_error",
]
