"""
Property-based tests for Error Classification.

**Feature: agent-refactor-with-rag, Property 20: 错误分类正确性**
**Validates: Requirements 21.1**

Property: For any error occurrence, Error_Handler should correctly classify it as:
- TransientError (retryable): network timeout, rate limit, service unavailable
- PermanentError (non-retryable): invalid config, auth failure, resource not found
- UserError (requires user action): invalid input, missing field
"""
import pytest
from hypothesis import given, strategies as st, settings, assume

from tableau_assistant.src.models.common import (
    TransientError,
    PermanentError,
    UserError,
    ErrorCategory,
    ErrorDetail,
    ErrorHandler,
    classify_error,
    wrap_error,
    is_retryable,
    get_retry_delay,
    format_user_message,
)


# ═══════════════════════════════════════════════════════════════════════════
# Strategies
# ═══════════════════════════════════════════════════════════════════════════

@st.composite
def transient_error_messages(draw):
    """Generate messages that should be classified as transient errors"""
    patterns = [
        "timeout",
        "timed out",
        "rate limit exceeded",
        "too many requests",
        "connection reset",
        "connection refused",
        "temporarily unavailable",
        "service unavailable",
        "503 Service Unavailable",
        "504 Gateway Timeout",
        "429 Too Many Requests",
        "retry later",
    ]
    base = draw(st.sampled_from(patterns))
    # Use simple alphanumeric prefix/suffix
    prefix = draw(st.text(min_size=0, max_size=10, alphabet="abcdefghijklmnopqrstuvwxyz "))
    suffix = draw(st.text(min_size=0, max_size=10, alphabet="abcdefghijklmnopqrstuvwxyz "))
    return f"{prefix}{base}{suffix}".strip()


@st.composite
def user_error_messages(draw):
    """Generate messages that should be classified as user errors"""
    patterns = [
        "invalid input",
        "validation error",
        "field not found",
        "not found in datasource",
        "missing required field",
        "ambiguous query",
        "400 Bad Request",
        "422 Unprocessable Entity",
    ]
    base = draw(st.sampled_from(patterns))
    # Use a safe alphabet that won't accidentally create transient patterns
    # Avoid: timeout, timed, rate, limit, connection, retry, 503, 504, 429
    safe_alphabet = "abcdefghjklmnpqsuvwxyz "  # removed i, o, r, t to avoid transient patterns
    prefix = draw(st.text(min_size=0, max_size=5, alphabet=safe_alphabet))
    return f"{prefix}{base}".strip()


@st.composite
def permanent_error_messages(draw):
    """Generate messages that should be classified as permanent errors"""
    patterns = [
        "invalid configuration",
        "authentication failed",
        "permission denied",
        "unauthorized access",
        "forbidden",
        "invalid API key",
        "license expired",
    ]
    base = draw(st.sampled_from(patterns))
    return base


# ═══════════════════════════════════════════════════════════════════════════
# Property Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestErrorClassificationProperty:
    """
    **Feature: agent-refactor-with-rag, Property 20: 错误分类正确性**
    **Validates: Requirements 21.1**
    
    Property: For any error, classify_error should return the correct category.
    """
    
    @given(message=transient_error_messages())
    @settings(max_examples=50, deadline=None)
    def test_transient_errors_classified_correctly(self, message: str):
        """
        Property: Errors with transient patterns should be classified as TRANSIENT.
        
        **Feature: agent-refactor-with-rag, Property 20: 错误分类正确性**
        **Validates: Requirements 21.1**
        """
        # Arrange
        error = Exception(message)
        
        # Act
        category = classify_error(error)
        
        # Assert
        assert category == ErrorCategory.TRANSIENT, \
            f"Expected TRANSIENT for '{message}', got {category}"
    
    @given(message=user_error_messages())
    @settings(max_examples=50, deadline=None)
    def test_user_errors_classified_correctly(self, message: str):
        """
        Property: Errors with user error patterns should be classified as USER.
        
        **Feature: agent-refactor-with-rag, Property 20: 错误分类正确性**
        **Validates: Requirements 21.1**
        """
        # Arrange
        error = Exception(message)
        
        # Act
        category = classify_error(error)
        
        # Assert
        assert category == ErrorCategory.USER, \
            f"Expected USER for '{message}', got {category}"
    
    def test_typed_errors_preserve_category(self):
        """
        Property: Typed errors (TransientError, PermanentError, UserError) 
        should always return their own category.
        
        **Feature: agent-refactor-with-rag, Property 20: 错误分类正确性**
        **Validates: Requirements 21.1**
        """
        # TransientError
        assert classify_error(TransientError("any message")) == ErrorCategory.TRANSIENT
        
        # PermanentError
        assert classify_error(PermanentError("any message")) == ErrorCategory.PERMANENT
        
        # UserError
        assert classify_error(UserError("any message")) == ErrorCategory.USER


class TestRetryLogicProperty:
    """
    Property tests for retry logic.
    
    **Feature: agent-refactor-with-rag, Property 20: 错误分类正确性**
    **Validates: Requirements 21.2**
    """
    
    def test_transient_errors_are_retryable(self):
        """Transient errors should be retryable."""
        error = TransientError("timeout")
        assert is_retryable(error) is True
    
    def test_permanent_errors_not_retryable(self):
        """Permanent errors should not be retryable."""
        error = PermanentError("invalid config")
        assert is_retryable(error) is False
    
    def test_user_errors_not_retryable(self):
        """User errors should not be retryable."""
        error = UserError("bad input")
        assert is_retryable(error) is False
    
    @given(retry_count=st.integers(min_value=0, max_value=10))
    @settings(max_examples=20)
    def test_retry_delay_exponential_backoff(self, retry_count: int):
        """
        Property: Retry delay should follow exponential backoff (2^n).
        
        **Feature: agent-refactor-with-rag, Property 20: 错误分类正确性**
        **Validates: Requirements 21.2**
        """
        # Arrange
        base_delay = 1.0
        
        # Act
        delay = get_retry_delay(retry_count, base_delay)
        
        # Assert
        expected = base_delay * (2 ** retry_count)
        assert delay == expected, f"Expected {expected}, got {delay}"


class TestErrorHandlerProperty:
    """
    Property tests for ErrorHandler.
    
    **Feature: agent-refactor-with-rag, Property 20: 错误分类正确性**
    **Validates: Requirements 21.2, 21.3, 21.4**
    """
    
    @given(retry_count=st.integers(min_value=0, max_value=5))
    @settings(max_examples=20)
    def test_transient_error_retry_within_limit(self, retry_count: int):
        """
        Property: Transient errors should retry if within max_retries limit.
        
        **Feature: agent-refactor-with-rag, Property 20: 错误分类正确性**
        **Validates: Requirements 21.2**
        """
        # Arrange
        max_retries = 3
        handler = ErrorHandler(max_retries=max_retries)
        error = TransientError("timeout")
        
        # Act
        result = handler.handle(error, retry_count=retry_count)
        
        # Assert
        if retry_count < max_retries:
            assert result["should_retry"] is True
            assert result["retry_delay"] > 0
        else:
            assert result["should_retry"] is False
    
    def test_permanent_error_never_retries(self):
        """
        Property: Permanent errors should never trigger retry.
        
        **Feature: agent-refactor-with-rag, Property 20: 错误分类正确性**
        **Validates: Requirements 21.3**
        """
        # Arrange
        handler = ErrorHandler(max_retries=10)
        error = PermanentError("auth failed")
        
        # Act
        result = handler.handle(error, retry_count=0)
        
        # Assert
        assert result["should_retry"] is False
    
    def test_user_error_returns_friendly_message(self):
        """
        Property: User errors should return user-friendly message with suggestions.
        
        **Feature: agent-refactor-with-rag, Property 20: 错误分类正确性**
        **Validates: Requirements 21.4**
        """
        # Arrange
        handler = ErrorHandler()
        suggestions = ["Check field name", "Use exact match"]
        error = UserError("Field not found", suggestions=suggestions)
        
        # Act
        result = handler.handle(error)
        
        # Assert
        assert result["should_retry"] is False
        assert "Field not found" in result["user_message"]
        for suggestion in suggestions:
            assert suggestion in result["user_message"]


class TestErrorDetailProperty:
    """
    Property tests for ErrorDetail.
    
    **Feature: agent-refactor-with-rag, Property 20: 错误分类正确性**
    **Validates: Requirements 21.5**
    """
    
    def test_error_detail_from_exception(self):
        """
        Property: ErrorDetail.from_exception should capture all error info.
        
        **Feature: agent-refactor-with-rag, Property 20: 错误分类正确性**
        **Validates: Requirements 21.5**
        """
        # Arrange
        error = TransientError("Network timeout", retry_after=5)
        context = {"node": "understanding", "attempt": 1}
        
        # Act
        detail = ErrorDetail.from_exception(error, context=context)
        
        # Assert
        assert detail.category == ErrorCategory.TRANSIENT
        assert "Network timeout" in detail.message  # Message may include retry info
        assert detail.error_type == "TransientError"
        assert detail.context == context
        assert detail.timestamp is not None
    
    def test_error_detail_serialization(self):
        """
        Property: ErrorDetail.to_dict should produce valid serializable dict.
        
        **Feature: agent-refactor-with-rag, Property 20: 错误分类正确性**
        **Validates: Requirements 21.5**
        """
        # Arrange
        error = UserError("Invalid input", suggestions=["Try X"])
        detail = ErrorDetail.from_exception(error)
        
        # Act
        data = detail.to_dict()
        
        # Assert
        assert isinstance(data, dict)
        assert data["category"] == "user"
        assert data["message"] == "Invalid input"
        assert "Try X" in data["suggestions"]


class TestWrapErrorProperty:
    """
    Property tests for wrap_error function.
    """
    
    def test_wrap_preserves_typed_errors(self):
        """Wrapping typed errors should preserve their type."""
        errors = [
            TransientError("test"),
            PermanentError("test"),
            UserError("test"),
        ]
        
        for error in errors:
            wrapped = wrap_error(error)
            assert type(wrapped) == type(error)
    
    @given(message=transient_error_messages())
    @settings(max_examples=20)
    def test_wrap_generic_transient(self, message: str):
        """Generic exceptions with transient patterns should wrap to TransientError."""
        error = Exception(message)
        wrapped = wrap_error(error)
        assert isinstance(wrapped, TransientError)
    
    @given(message=user_error_messages())
    @settings(max_examples=20)
    def test_wrap_generic_user(self, message: str):
        """Generic exceptions with user error patterns should wrap to UserError."""
        error = Exception(message)
        wrapped = wrap_error(error)
        assert isinstance(wrapped, UserError)


# ═══════════════════════════════════════════════════════════════════════════
# Run tests
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--hypothesis-show-statistics"])
