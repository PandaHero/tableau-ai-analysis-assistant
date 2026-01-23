# -*- coding: utf-8 -*-
"""语义解析器的自定义异常。

这些异常携带额外的上下文信息，用于基于 Observer 的错误修正。
"""


class ValidationError(Exception):
    """带有原始输出的验证错误，用于 Observer 修正。
    
    同时携带错误消息和原始 LLM 输出，
    允许 Observer 查看出错的内容并尝试修正。
    """
    
    def __init__(
        self,
        message: str,
        original_output: str | None = None,
        step: str = "unknown",
    ):
        """初始化 ValidationError。
        
        Args:
            message: 描述出错内容的错误消息
            original_output: 验证失败的原始 LLM 输出
            step: 失败的步骤（"step1" 或 "step2"）
        """
        super().__init__(message)
        self.message = message
        self.original_output = original_output
        self.step = step
    
    def __str__(self) -> str:
        return f"[{self.step}] {self.message}"


class TableauAuthError(Exception):
    """Tableau 认证错误。
    
    当 Tableau 认证失败时抛出此异常。
    """
    
    def __init__(self, message: str, details: str | None = None, auth_method: str | None = None):
        """初始化 TableauAuthError。
        
        Args:
            message: 错误消息
            details: 详细错误信息
            auth_method: 认证方式
        """
        super().__init__(message)
        self.message = message
        self.details = details
        self.auth_method = auth_method
    
    def __str__(self) -> str:
        if self.details:
            return f"{self.message}: {self.details}"
        return self.message


class VizQLError(Exception):
    """VizQL API 基础错误。"""
    
    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        error_code: str | None = None,
        debug: str | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.debug = debug
    
    @property
    def is_retryable(self) -> bool:
        """是否可重试。"""
        if self.status_code:
            return self.status_code >= 500 or self.status_code == 429
        return False
    
    def __str__(self) -> str:
        parts = [self.message]
        if self.error_code:
            parts.append(f"[{self.error_code}]")
        if self.status_code:
            parts.append(f"(HTTP {self.status_code})")
        return " ".join(parts)


class VizQLAuthError(VizQLError):
    """VizQL 认证错误 (401/403)。"""
    pass


class VizQLValidationError(VizQLError):
    """VizQL 验证错误 (400)。"""
    pass


class VizQLServerError(VizQLError):
    """VizQL 服务器错误 (5xx)。"""
    pass


class VizQLRateLimitError(VizQLError):
    """VizQL 限流错误 (429)。"""
    
    def __init__(
        self,
        message: str,
        retry_after: int | None = None,
        error_code: str | None = None,
        debug: str | None = None,
    ):
        super().__init__(message, status_code=429, error_code=error_code, debug=debug)
        self.retry_after = retry_after


class VizQLTimeoutError(VizQLError):
    """VizQL 超时错误。"""
    
    def __init__(self, message: str):
        super().__init__(message)
    
    @property
    def is_retryable(self) -> bool:
        return True


class VizQLNetworkError(VizQLError):
    """VizQL 网络错误。"""
    
    def __init__(self, message: str):
        super().__init__(message)
    
    @property
    def is_retryable(self) -> bool:
        return True
