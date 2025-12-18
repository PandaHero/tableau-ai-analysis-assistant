"""
异常类定义

提供统一的异常处理机制。
"""
from typing import Optional, Dict, Any


class VizQLError(Exception):
    """VizQL API 错误基类"""
    
    def __init__(self, status_code: int, message: str, error_code: Optional[str] = None, debug: Optional[Dict[str, Any]] = None):
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        self.debug = debug
        self.is_retryable = self._determine_retryable()
        super().__init__(self.message)
    
    def _determine_retryable(self) -> bool:
        if 500 <= self.status_code < 600:
            return True
        if self.status_code == 429:
            return True
        return False
    
    def __str__(self) -> str:
        return f"VizQLError({self.status_code}): {self.message}"


class VizQLAuthError(VizQLError):
    def __init__(self, message: str, **kwargs):
        super().__init__(status_code=401, message=message, **kwargs)
        self.is_retryable = False


class VizQLValidationError(VizQLError):
    def __init__(self, message: str, **kwargs):
        super().__init__(status_code=400, message=message, **kwargs)
        self.is_retryable = False


class VizQLServerError(VizQLError):
    def __init__(self, message: str, status_code: int = 500, **kwargs):
        super().__init__(status_code=status_code, message=message, **kwargs)
        self.is_retryable = True


class VizQLRateLimitError(VizQLError):
    def __init__(self, message: str, retry_after: Optional[int] = None, **kwargs):
        super().__init__(status_code=429, message=message, **kwargs)
        self.retry_after = retry_after
        self.is_retryable = True


class VizQLTimeoutError(VizQLError):
    def __init__(self, message: str, **kwargs):
        super().__init__(status_code=408, message=message, **kwargs)
        self.is_retryable = True


class VizQLNetworkError(VizQLError):
    def __init__(self, message: str, **kwargs):
        super().__init__(status_code=0, message=message, **kwargs)
        self.is_retryable = True


__all__ = [
    "VizQLError", "VizQLAuthError", "VizQLValidationError", "VizQLServerError",
    "VizQLRateLimitError", "VizQLTimeoutError", "VizQLNetworkError",
]
