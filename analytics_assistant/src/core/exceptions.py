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
