"""验证和结果模型。

用于验证错误和结果的模型。
由平台适配器用于验证和错误报告。

注意：QueryResult 和 ColumnInfo 已移至 execute_result.py，
作为 ExecuteResult 和 ColumnInfo 用于统一结果处理。
"""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ValidationErrorType(str, Enum):
    """验证错误类型。"""
    MISSING_REQUIRED = "MISSING_REQUIRED"
    INVALID_VALUE = "INVALID_VALUE"
    INVALID_TYPE = "INVALID_TYPE"
    CONSTRAINT_VIOLATION = "CONSTRAINT_VIOLATION"
    FIELD_NOT_FOUND = "FIELD_NOT_FOUND"
    INCOMPATIBLE = "INCOMPATIBLE"


class ValidationError(BaseModel):
    """验证错误详情。"""
    model_config = ConfigDict(extra="forbid")
    
    error_type: ValidationErrorType = Field(
        description="""<what>验证错误类型</what>
<when>始终必需</when>"""
    )
    
    field_path: str = Field(
        description="""<what>出错字段的路径</what>
<when>始终必需</when>
<rule>使用点号表示法，如 'computations[0].partition_by'</rule>"""
    )
    
    message: str = Field(
        description="""<what>人类可读的错误消息</what>
<when>始终必需</when>"""
    )
    
    suggestion: str | None = Field(
        default=None,
        description="""<what>建议的修复方法</what>
<when>可选，当已知修复方法时</when>"""
    )


class ValidationResult(BaseModel):
    """验证结果。
    
    由平台适配器用于报告验证结果。
    """
    model_config = ConfigDict(extra="forbid")
    
    is_valid: bool = Field(
        description="""<what>验证是否通过</what>
<when>始终必需</when>"""
    )
    
    errors: list[ValidationError] = Field(
        default_factory=list,
        description="""<what>验证错误列表</what>
<when>当 is_valid=False 时</when>"""
    )
    
    warnings: list[ValidationError] = Field(
        default_factory=list,
        description="""<what>验证警告列表（非阻塞）</what>
<when>可选，用于非关键问题</when>"""
    )
    
    auto_fixed: list[str] = Field(
        default_factory=list,
        description="""<what>已自动修复的字段列表</what>
<when>当应用了自动修正时</when>"""
    )
