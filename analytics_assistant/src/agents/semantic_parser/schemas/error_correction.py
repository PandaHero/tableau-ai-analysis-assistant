# -*- coding: utf-8 -*-
"""
Error Correction Schemas - 错误修正相关数据模型

包含：
- ErrorCorrectionHistory: 错误修正历史记录
- CorrectionResult: 修正结果
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from .output import SemanticOutput


class ErrorCorrectionHistory(BaseModel):
    """错误修正历史记录
    
    记录每次错误修正尝试的信息，用于：
    1. 重复错误检测（通过 error_hash）
    2. 修正历史追踪
    3. 调试和分析
    """
    model_config = ConfigDict(extra="forbid")
    
    error_type: str = Field(
        description="错误类型，如 field_not_found, syntax_error, invalid_filter_value"
    )
    error_hash: str = Field(
        description="错误信息的 hash，用于重复检测"
    )
    attempt_number: int = Field(
        ge=1,
        description="尝试次数（从 1 开始）"
    )
    correction_applied: str = Field(
        default="",
        description="应用的修正描述"
    )
    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="时间戳"
    )


class CorrectionResult(BaseModel):
    """修正结果
    
    ErrorCorrector.correct() 方法的返回值，包含：
    - 修正后的输出（如果成功）
    - 是否应该继续执行
    - 终止原因（如果终止）
    """
    model_config = ConfigDict(extra="forbid")
    
    corrected_output: Optional[SemanticOutput] = Field(
        default=None,
        description="修正后的输出，如果终止则为 None"
    )
    thinking: str = Field(
        default="",
        description="LLM 的思考过程或修正说明"
    )
    should_continue: bool = Field(
        default=False,
        description="是否应该继续执行（使用修正后的输出重试）"
    )
    abort_reason: Optional[str] = Field(
        default=None,
        description="终止原因，如 duplicate_error_detected, total_error_history_exceeded, non_retryable_error"
    )


__all__ = [
    "ErrorCorrectionHistory",
    "CorrectionResult",
]
