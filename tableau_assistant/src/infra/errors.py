"""
Error Types and Classification

Defines error categories for proper handling:
- TransientError: Can be retried (network issues, rate limits)
- PermanentError: Cannot be retried (invalid config, auth failure)
- UserError: Requires user action (invalid input, missing data)

Error Handling Strategy:
- TransientError: Retry with exponential backoff (1s, 2s, 4s), max 3 retries
- PermanentError: Terminate immediately, log error, return clear message
- UserError: Return user-friendly message with suggestions
"""
import logging
import traceback
from enum import Enum
from typing import Optional, Dict, Any, List, Union
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


class ErrorCategory(str, Enum):
    """Error category enum"""
    TRANSIENT = "transient"
    PERMANENT = "permanent"
    USER = "user"


@dataclass
class ErrorDetail:
    """
    Structured error detail for logging and state tracking
    
    Used in VizQLState.errors for error history
    """
    category: ErrorCategory
    message: str
    error_type: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    context: Dict[str, Any] = field(default_factory=dict)
    stack_trace: Optional[str] = None
    suggestions: List[str] = field(default_factory=list)
    retry_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "category": self.category.value,
            "message": self.message,
            "error_type": self.error_type,
            "timestamp": self.timestamp,
            "context": self.context,
            "stack_trace": self.stack_trace,
            "suggestions": self.suggestions,
            "retry_count": self.retry_count,
        }
    
    @classmethod
    def from_exception(
        cls,
        error: Exception,
        context: Optional[Dict[str, Any]] = None,
        include_stack_trace: bool = True
    ) -> "ErrorDetail":
        """Create ErrorDetail from an exception"""
        category = classify_error(error)
        
        suggestions = []
        if isinstance(error, UserError):
            suggestions = error.suggestions
        
        return cls(
            category=category,
            message=str(error),
            error_type=type(error).__name__,
            context=context or {},
            stack_trace=traceback.format_exc() if include_stack_trace else None,
            suggestions=suggestions,
        )


class TransientError(Exception):
    """
    Transient error - can be retried
    
    Examples:
    - Network timeout
    - Rate limit exceeded
    - Service temporarily unavailable
    - Connection reset
    
    Handling: Retry with exponential backoff
    """
    
    def __init__(
        self,
        message: str,
        retry_after: Optional[int] = None,
        original_error: Optional[Exception] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message)
        self.message = message
        self.retry_after = retry_after  # Seconds to wait before retry
        self.original_error = original_error
        self.context = context or {}
        self.category = ErrorCategory.TRANSIENT
    
    def __str__(self) -> str:
        if self.retry_after:
            return f"{self.message} (retry after {self.retry_after}s)"
        return self.message


class PermanentError(Exception):
    """
    Permanent error - cannot be retried
    
    Examples:
    - Invalid configuration
    - Authentication failure
    - Resource not found (404)
    - Permission denied
    - Invalid API response format
    
    Handling: Log error, notify user, terminate operation
    """
    
    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        original_error: Optional[Exception] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.original_error = original_error
        self.context = context or {}
        self.category = ErrorCategory.PERMANENT
    
    def __str__(self) -> str:
        if self.error_code:
            return f"[{self.error_code}] {self.message}"
        return self.message


class UserError(Exception):
    """
    User error - requires user action to fix
    
    Examples:
    - Invalid input format
    - Missing required field
    - Field not found in datasource
    - Ambiguous query
    
    Handling: Return friendly message to user with guidance
    """
    
    def __init__(
        self,
        message: str,
        user_message: Optional[str] = None,
        suggestions: Optional[list] = None,
        original_error: Optional[Exception] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message)
        self.message = message
        self.user_message = user_message or message  # User-friendly message
        self.suggestions = suggestions or []  # Suggestions for fixing
        self.original_error = original_error
        self.context = context or {}
        self.category = ErrorCategory.USER
    
    def __str__(self) -> str:
        return self.user_message


def classify_error(error: Exception) -> ErrorCategory:
    """
    Classify an error into a category
    
    Args:
        error: The exception to classify
    
    Returns:
        ErrorCategory enum value
    """
    # Already classified
    if isinstance(error, TransientError):
        return ErrorCategory.TRANSIENT
    if isinstance(error, PermanentError):
        return ErrorCategory.PERMANENT
    if isinstance(error, UserError):
        return ErrorCategory.USER
    
    # Classify by error type/message
    error_str = str(error).lower()
    error_type = type(error).__name__.lower()
    
    # Transient patterns
    transient_patterns = [
        "timeout",
        "timed out",
        "rate limit",
        "too many requests",
        "connection reset",
        "connection refused",
        "temporarily unavailable",
        "service unavailable",
        "503",
        "504",
        "429",
        "retry",
    ]
    
    for pattern in transient_patterns:
        if pattern in error_str or pattern in error_type:
            return ErrorCategory.TRANSIENT
    
    # User error patterns
    user_patterns = [
        "invalid input",
        "validation error",
        "field not found",
        "not found",
        "missing required",
        "ambiguous",
        "400",
        "422",
    ]
    
    for pattern in user_patterns:
        if pattern in error_str:
            return ErrorCategory.USER
    
    # Default to permanent for unknown errors
    return ErrorCategory.PERMANENT


def wrap_error(
    error: Exception,
    context: Optional[Dict[str, Any]] = None
) -> Exception:
    """
    Wrap an exception with proper error type
    
    Args:
        error: Original exception
        context: Additional context information
    
    Returns:
        Wrapped exception (TransientError, PermanentError, or UserError)
    """
    # Already wrapped
    if isinstance(error, (TransientError, PermanentError, UserError)):
        if context:
            error.context.update(context)
        return error
    
    category = classify_error(error)
    
    if category == ErrorCategory.TRANSIENT:
        return TransientError(
            message=str(error),
            original_error=error,
            context=context
        )
    elif category == ErrorCategory.USER:
        return UserError(
            message=str(error),
            original_error=error,
            context=context
        )
    else:
        return PermanentError(
            message=str(error),
            original_error=error,
            context=context
        )


def is_retryable(error: Exception) -> bool:
    """
    Check if an error is retryable
    
    Args:
        error: The exception to check
    
    Returns:
        True if the error can be retried
    """
    return classify_error(error) == ErrorCategory.TRANSIENT


def get_retry_delay(retry_count: int, base_delay: float = 1.0) -> float:
    """
    Calculate retry delay with exponential backoff
    
    Args:
        retry_count: Current retry attempt (0-based)
        base_delay: Base delay in seconds
    
    Returns:
        Delay in seconds (1s, 2s, 4s, ...)
    """
    return base_delay * (2 ** retry_count)


def format_user_message(error: Exception) -> str:
    """
    Format an error message for user display
    
    Args:
        error: The exception
    
    Returns:
        User-friendly error message
    """
    if isinstance(error, UserError):
        msg = error.user_message
        if error.suggestions:
            msg += "\n\n建议:\n" + "\n".join(f"- {s}" for s in error.suggestions)
        return msg
    
    if isinstance(error, TransientError):
        return "服务暂时不可用，请稍后重试。"
    
    if isinstance(error, PermanentError):
        return f"操作失败: {error.message}"
    
    return "发生未知错误，请联系管理员。"


def log_error(
    error: Exception,
    context: Optional[Dict[str, Any]] = None,
    level: str = "error"
) -> ErrorDetail:
    """
    Log an error with proper formatting and return ErrorDetail
    
    Args:
        error: The exception to log
        context: Additional context information
        level: Log level (debug, info, warning, error, critical)
    
    Returns:
        ErrorDetail for state tracking
    """
    detail = ErrorDetail.from_exception(error, context)
    
    log_msg = f"[{detail.category.value.upper()}] {detail.error_type}: {detail.message}"
    if context:
        log_msg += f" | Context: {context}"
    
    log_func = getattr(logger, level, logger.error)
    log_func(log_msg)
    
    if detail.stack_trace and level in ("error", "critical"):
        logger.debug(f"Stack trace:\n{detail.stack_trace}")
    
    return detail


class ErrorHandler:
    """
    Centralized error handler for the workflow
    
    Provides:
    - Error classification
    - Retry logic
    - User message formatting
    - Error logging and tracking
    """
    
    def __init__(self, max_retries: int = 3, base_delay: float = 1.0):
        """
        Initialize error handler
        
        Args:
            max_retries: Maximum retry attempts for transient errors
            base_delay: Base delay for exponential backoff
        """
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.error_history: List[ErrorDetail] = []
    
    def handle(
        self,
        error: Exception,
        context: Optional[Dict[str, Any]] = None,
        retry_count: int = 0
    ) -> Dict[str, Any]:
        """
        Handle an error and return handling instructions
        
        Args:
            error: The exception to handle
            context: Additional context
            retry_count: Current retry count
        
        Returns:
            Dict with keys:
            - should_retry: bool
            - retry_delay: float (if should_retry)
            - user_message: str
            - error_detail: ErrorDetail
        """
        wrapped = wrap_error(error, context)
        detail = log_error(wrapped, context)
        detail.retry_count = retry_count
        self.error_history.append(detail)
        
        result = {
            "should_retry": False,
            "retry_delay": 0.0,
            "user_message": format_user_message(wrapped),
            "error_detail": detail,
        }
        
        if isinstance(wrapped, TransientError):
            if retry_count < self.max_retries:
                result["should_retry"] = True
                result["retry_delay"] = get_retry_delay(retry_count, self.base_delay)
                logger.info(
                    f"Transient error, will retry in {result['retry_delay']}s "
                    f"(attempt {retry_count + 1}/{self.max_retries})"
                )
        
        return result
    
    def get_error_summary(self) -> Dict[str, Any]:
        """Get summary of all errors"""
        if not self.error_history:
            return {"total": 0, "by_category": {}}
        
        by_category = {}
        for detail in self.error_history:
            cat = detail.category.value
            by_category[cat] = by_category.get(cat, 0) + 1
        
        return {
            "total": len(self.error_history),
            "by_category": by_category,
            "last_error": self.error_history[-1].to_dict() if self.error_history else None,
        }
    
    def clear_history(self):
        """Clear error history"""
        self.error_history.clear()


__all__ = [
    "ErrorCategory",
    "TransientError",
    "PermanentError",
    "UserError",
    "ErrorDetail",
    "ErrorHandler",
    "classify_error",
    "wrap_error",
    "is_retryable",
    "get_retry_delay",
    "format_user_message",
    "log_error",
]
