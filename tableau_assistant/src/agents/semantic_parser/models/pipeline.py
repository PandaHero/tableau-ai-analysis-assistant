"""Pipeline models - QueryPipeline 执行结果模型。

定义 QueryPipeline 的输出模型，包括成功结果和错误类型。
"""

from typing import Any, Dict, List, Optional
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field


class QueryErrorType(str, Enum):
    """查询错误类型"""
    # Step1/Step2 错误
    STEP1_FAILED = "step1_failed"
    STEP2_FAILED = "step2_failed"
    
    # 字段映射错误
    FIELD_NOT_FOUND = "field_not_found"
    AMBIGUOUS_FIELD = "ambiguous_field"
    NO_METADATA = "no_metadata"
    MAPPING_FAILED = "mapping_failed"
    
    # 查询构建错误
    INVALID_COMPUTATION = "invalid_computation"
    UNSUPPORTED_OPERATION = "unsupported_operation"
    BUILD_FAILED = "build_failed"
    
    # 执行错误
    EXECUTION_FAILED = "execution_failed"
    TIMEOUT = "timeout"
    AUTH_ERROR = "auth_error"
    INVALID_QUERY = "invalid_query"
    
    # 通用错误
    UNKNOWN = "unknown"


class QueryError(BaseModel):
    """查询错误模型
    
    当 QueryPipeline 中任意步骤失败时返回此结构化错误。
    """
    model_config = ConfigDict(extra="forbid")
    
    type: QueryErrorType = Field(
        description="错误类型"
    )
    
    message: str = Field(
        description="用户友好的错误信息"
    )
    
    step: str = Field(
        description="发生错误的步骤 (step1, step2, map_fields, build_query, execute_query)"
    )
    
    details: Optional[Dict[str, Any]] = Field(
        default=None,
        description="详细错误信息（如字段建议、原始错误等）"
    )
    
    can_retry: bool = Field(
        default=False,
        description="是否可以重试（用于 ReAct 决策）"
    )
    
    suggestion: Optional[str] = Field(
        default=None,
        description="修复建议"
    )
    
    def to_user_message(self) -> str:
        """生成用户友好的错误消息"""
        msg = self.message
        if self.suggestion:
            msg += f" 建议: {self.suggestion}"
        return msg


class QueryResult(BaseModel):
    """QueryPipeline 执行结果
    
    成功时包含查询结果数据，失败时包含错误信息。
    """
    model_config = ConfigDict(extra="forbid")
    
    success: bool = Field(
        description="是否成功"
    )
    
    # 成功时的数据
    data: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="查询结果数据（成功时）"
    )
    
    columns: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="列元数据"
    )
    
    row_count: int = Field(
        default=0,
        description="返回的行数"
    )
    
    # 中间结果（用于调试和 ReAct）
    semantic_query: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Step1/Step2 生成的 SemanticQuery"
    )
    
    mapped_query: Optional[Dict[str, Any]] = Field(
        default=None,
        description="字段映射后的 MappedQuery"
    )
    
    vizql_query: Optional[Dict[str, Any]] = Field(
        default=None,
        description="构建的 VizQL 查询"
    )
    
    # 大结果集处理
    file_path: Optional[str] = Field(
        default=None,
        description="大结果集保存的文件路径"
    )
    
    is_large_result: bool = Field(
        default=False,
        description="是否为大结果集"
    )
    
    # 错误信息
    error: Optional[QueryError] = Field(
        default=None,
        description="错误信息（失败时）"
    )
    
    # 执行统计
    execution_time_ms: int = Field(
        default=0,
        description="总执行耗时（毫秒）"
    )
    
    @classmethod
    def ok(
        cls,
        data: List[Dict[str, Any]],
        columns: Optional[List[Dict[str, Any]]] = None,
        row_count: int = 0,
        semantic_query: Optional[Dict[str, Any]] = None,
        mapped_query: Optional[Dict[str, Any]] = None,
        vizql_query: Optional[Dict[str, Any]] = None,
        file_path: Optional[str] = None,
        is_large_result: bool = False,
        execution_time_ms: int = 0
    ) -> "QueryResult":
        """创建成功响应"""
        return cls(
            success=True,
            data=data,
            columns=columns,
            row_count=row_count,
            semantic_query=semantic_query,
            mapped_query=mapped_query,
            vizql_query=vizql_query,
            file_path=file_path,
            is_large_result=is_large_result,
            execution_time_ms=execution_time_ms
        )
    
    @classmethod
    def fail(
        cls,
        error: QueryError,
        semantic_query: Optional[Dict[str, Any]] = None,
        mapped_query: Optional[Dict[str, Any]] = None,
        vizql_query: Optional[Dict[str, Any]] = None,
        execution_time_ms: int = 0
    ) -> "QueryResult":
        """创建失败响应"""
        return cls(
            success=False,
            error=error,
            semantic_query=semantic_query,
            mapped_query=mapped_query,
            vizql_query=vizql_query,
            execution_time_ms=execution_time_ms
        )


__all__ = [
    "QueryResult",
    "QueryError",
    "QueryErrorType",
]
