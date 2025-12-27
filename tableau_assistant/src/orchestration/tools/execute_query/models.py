"""
execute_query Tool 数据模型

定义 Tool 的输入、输出和错误模型。
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


class ExecutionErrorType(str, Enum):
    """查询执行错误类型"""
    EXECUTION_FAILED = "execution_failed"
    TIMEOUT = "timeout"
    AUTH_ERROR = "auth_error"
    INVALID_QUERY = "invalid_query"
    MISSING_INPUT = "missing_input"
    API_ERROR = "api_error"


class ExecutionError(BaseModel):
    """查询执行错误
    
    当查询执行失败时返回此结构化错误。
    """
    type: ExecutionErrorType = Field(description="错误类型")
    message: str = Field(description="用户友好的错误信息")
    details: Optional[str] = Field(default=None, description="详细错误信息")
    suggestion: Optional[str] = Field(default=None, description="修复建议")
    
    def to_user_message(self) -> str:
        """生成用户友好的错误消息"""
        msg = self.message
        if self.suggestion:
            msg += f" 建议: {self.suggestion}"
        return msg


class ExecuteQueryInput(BaseModel):
    """execute_query Tool 输入
    
    接收 VizQL 查询并执行。
    """
    vizql_query: Dict[str, Any] = Field(
        description="VizQLQueryRequest 的字典表示"
    )
    datasource_luid: str = Field(
        default="default",
        description="数据源标识符"
    )


class ExecuteQueryOutput(BaseModel):
    """execute_query Tool 输出
    
    成功时返回 ExecuteResult，失败时返回 ExecutionError。
    """
    success: bool = Field(description="是否成功")
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
    query_id: Optional[str] = Field(
        default=None,
        description="查询 ID（用于追踪）"
    )
    file_path: Optional[str] = Field(
        default=None,
        description="大结果集保存的文件路径"
    )
    is_large_result: bool = Field(
        default=False,
        description="是否为大结果集（已保存到文件）"
    )
    error: Optional[ExecutionError] = Field(
        default=None,
        description="错误信息（失败时）"
    )
    execution_time_ms: int = Field(
        default=0,
        description="执行耗时（毫秒）"
    )
    
    @classmethod
    def ok(
        cls,
        data: List[Dict[str, Any]],
        columns: Optional[List[Dict[str, Any]]] = None,
        row_count: int = 0,
        query_id: Optional[str] = None,
        file_path: Optional[str] = None,
        is_large_result: bool = False,
        execution_time_ms: int = 0
    ) -> "ExecuteQueryOutput":
        """创建成功响应"""
        return cls(
            success=True,
            data=data,
            columns=columns,
            row_count=row_count,
            query_id=query_id,
            file_path=file_path,
            is_large_result=is_large_result,
            execution_time_ms=execution_time_ms
        )
    
    @classmethod
    def fail(cls, error: ExecutionError, execution_time_ms: int = 0) -> "ExecuteQueryOutput":
        """创建失败响应"""
        return cls(
            success=False,
            error=error,
            execution_time_ms=execution_time_ms
        )


__all__ = [
    "ExecuteQueryInput",
    "ExecuteQueryOutput",
    "ExecutionError",
    "ExecutionErrorType",
]
