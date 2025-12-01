"""
VizQL 异常类定义

提供统一的异常处理机制，支持：
- 错误分类
- 重试判断
- 详细错误信息
"""
from typing import Optional, Dict, Any


class VizQLError(Exception):
    """
    VizQL API 错误基类
    
    Attributes:
        status_code: HTTP 状态码
        error_code: Tableau 错误代码
        message: 错误消息
        debug: 调试信息
        is_retryable: 是否可重试
    """
    
    def __init__(
        self,
        status_code: int,
        message: str,
        error_code: Optional[str] = None,
        debug: Optional[Dict[str, Any]] = None
    ):
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        self.debug = debug
        self.is_retryable = self._determine_retryable()
        super().__init__(self.message)
    
    def _determine_retryable(self) -> bool:
        """判断错误是否可重试"""
        # 5xx 服务器错误可重试
        if 500 <= self.status_code < 600:
            return True
        # 429 速率限制可重试
        if self.status_code == 429:
            return True
        return False
    
    def __str__(self) -> str:
        return f"VizQLError({self.status_code}): {self.message}"


class VizQLAuthError(VizQLError):
    """认证错误 (401/403)"""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(status_code=401, message=message, **kwargs)
        self.is_retryable = False


class VizQLValidationError(VizQLError):
    """验证错误 (400)"""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(status_code=400, message=message, **kwargs)
        self.is_retryable = False


class VizQLServerError(VizQLError):
    """服务器错误 (5xx)"""
    
    def __init__(self, message: str, status_code: int = 500, **kwargs):
        super().__init__(status_code=status_code, message=message, **kwargs)
        self.is_retryable = True


class VizQLRateLimitError(VizQLError):
    """速率限制错误 (429)"""
    
    def __init__(self, message: str, retry_after: Optional[int] = None, **kwargs):
        super().__init__(status_code=429, message=message, **kwargs)
        self.retry_after = retry_after
        self.is_retryable = True


class VizQLTimeoutError(VizQLError):
    """超时错误"""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(status_code=408, message=message, **kwargs)
        self.is_retryable = True


class VizQLNetworkError(VizQLError):
    """网络错误"""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(status_code=0, message=message, **kwargs)
        self.is_retryable = True


# ============= 导出 =============

__all__ = [
    "VizQLError",
    "VizQLAuthError",
    "VizQLValidationError",
    "VizQLServerError",
    "VizQLRateLimitError",
    "VizQLTimeoutError",
    "VizQLNetworkError",
]
