# -*- coding: utf-8 -*-
"""语义解析器的自定义异常。

这些异常携带额外的上下文信息，用于基于 Observer 的错误修正。
"""

from typing import Dict, List, Optional


class ValidationError(Exception):
    """带有原始输出的验证错误，用于 Observer 修正。
    
    同时携带错误消息和原始 LLM 输出，
    允许 Observer 查看出错的内容并尝试修正。
    """
    
    def __init__(
        self,
        message: str,
        original_output: Optional[str] = None,
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
    
    def __init__(self, message: str, details: Optional[str] = None, auth_method: Optional[str] = None):
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
        status_code: Optional[int] = None,
        error_code: Optional[str] = None,
        debug: Optional[str] = None,
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
        retry_after: Optional[int] = None,
        error_code: Optional[str] = None,
        debug: Optional[str] = None,
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


# =============================================================================
# 语义解析优化异常定义
# =============================================================================


class SemanticOptimizationError(Exception):
    """语义解析优化异常基类。
    
    所有语义解析优化相关异常的基类，携带上下文信息用于调试。
    """
    
    def __init__(
        self,
        message: str,
        context: Optional[Dict] = None,
    ):
        """初始化 SemanticOptimizationError。
        
        Args:
            message: 错误消息
            context: 异常发生时的上下文信息
        """
        super().__init__(message)
        self.message = message
        self.context = context or {}
    
    def __str__(self) -> str:
        if self.context:
            return f"{self.message} | context: {self.context}"
        return self.message


class RulePrefilterError(SemanticOptimizationError):
    """规则预处理异常。
    
    当 RulePrefilter 执行失败时抛出。
    """
    pass


class FeatureExtractionError(SemanticOptimizationError):
    """特征提取异常。
    
    当 FeatureExtractor 执行失败时抛出。
    """
    pass


class FeatureExtractorTimeoutError(FeatureExtractionError):
    """特征提取超时异常。
    
    当 FeatureExtractor 超时时抛出，调用方应降级使用 PrefilterResult。
    """
    
    def __init__(
        self,
        timeout_ms: int,
        context: Optional[Dict] = None,
    ):
        """初始化 FeatureExtractorTimeoutError。
        
        Args:
            timeout_ms: 超时时间（毫秒）
            context: 异常发生时的上下文信息
        """
        message = f"FeatureExtractor 超时 ({timeout_ms}ms)"
        super().__init__(message, context)
        self.timeout_ms = timeout_ms


class FieldRetrievalError(SemanticOptimizationError):
    """字段检索异常。
    
    当 FieldRetriever 执行失败时抛出。
    """
    pass


class OutputValidationError(SemanticOptimizationError):
    """输出验证异常。
    
    当 OutputValidator 发现不可修正的错误时抛出。
    """
    
    def __init__(
        self,
        message: str,
        validation_errors: Optional[List] = None,
        context: Optional[Dict] = None,
    ):
        """初始化 OutputValidationError。
        
        Args:
            message: 错误消息
            validation_errors: 验证错误列表
            context: 异常发生时的上下文信息
        """
        super().__init__(message, context)
        self.validation_errors = validation_errors or []


class DynamicSchemaError(SemanticOptimizationError):
    """动态 Schema 构建异常。
    
    当 DynamicSchemaBuilder 执行失败时抛出。
    """
    pass


class ModularPromptError(SemanticOptimizationError):
    """模块化 Prompt 构建异常。
    
    当 ModularPromptBuilder 执行失败时抛出。
    """
    pass
