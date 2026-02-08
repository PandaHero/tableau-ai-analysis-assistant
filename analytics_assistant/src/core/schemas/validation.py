# -*- coding: utf-8 -*-
"""验证和结果模型。

用于验证错误和结果的模型。
由平台适配器用于验证和错误报告。
"""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ValidationErrorType(str, Enum):
    """验证错误类型。"""
    MISSING_REQUIRED = "MISSING_REQUIRED"      # 缺少必填字段
    INVALID_VALUE = "INVALID_VALUE"            # 无效值
    INVALID_TYPE = "INVALID_TYPE"              # 无效类型
    CONSTRAINT_VIOLATION = "CONSTRAINT_VIOLATION"  # 约束违反
    FIELD_NOT_FOUND = "FIELD_NOT_FOUND"        # 字段未找到
    INCOMPATIBLE = "INCOMPATIBLE"              # 不兼容


class ValidationError(BaseModel):
    """验证错误详情。"""
    model_config = ConfigDict(extra="forbid")
    
    error_type: ValidationErrorType = Field(description="验证错误类型")
    field_path: str = Field(description="出错字段的路径（如 'computations[0].partition_by'）")
    message: str = Field(description="人类可读的错误消息")
    suggestion: Optional[str] = Field(default=None, description="建议的修复方法")


class ValidationResult(BaseModel):
    """验证结果。
    
    由平台适配器用于报告验证结果。
    """
    model_config = ConfigDict(extra="forbid")
    
    is_valid: bool = Field(description="验证是否通过")
    errors: List[ValidationError] = Field(
        default_factory=list,
        description="验证错误列表（当 is_valid=False 时）"
    )
    warnings: List[ValidationError] = Field(
        default_factory=list,
        description="验证警告列表（非阻塞）"
    )
    auto_fixed: List[str] = Field(
        default_factory=list,
        description="已自动修复的字段列表"
    )
