"""
build_query Tool 数据模型

定义 Tool 的输入、输出和错误模型。
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


class QueryBuildErrorType(str, Enum):
    """查询构建错误类型"""
    INVALID_COMPUTATION = "invalid_computation"
    UNSUPPORTED_OPERATION = "unsupported_operation"
    MISSING_INPUT = "missing_input"
    VALIDATION_FAILED = "validation_failed"
    BUILD_FAILED = "build_failed"


class QueryBuildError(BaseModel):
    """查询构建错误
    
    当查询构建失败时返回此结构化错误。
    """
    type: QueryBuildErrorType = Field(description="错误类型")
    message: str = Field(description="用户友好的错误信息")
    field_path: Optional[str] = Field(default=None, description="出错的字段路径")
    suggestion: Optional[str] = Field(default=None, description="修复建议")
    
    def to_user_message(self) -> str:
        """生成用户友好的错误消息"""
        msg = self.message
        if self.suggestion:
            msg += f" 建议: {self.suggestion}"
        return msg


class BuildQueryInput(BaseModel):
    """build_query Tool 输入
    
    接收 MappedQuery 并构建 VizQL 查询请求。
    """
    mapped_query: Dict[str, Any] = Field(
        description="MappedQuery 的字典表示（包含 semantic_query 和 field_mappings）"
    )
    datasource_luid: str = Field(
        default="default",
        description="数据源标识符"
    )
    field_metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="字段元数据（用于日期类型检测）"
    )


class BuildQueryOutput(BaseModel):
    """build_query Tool 输出
    
    成功时返回 VizQLQueryRequest，失败时返回 QueryBuildError。
    """
    success: bool = Field(description="是否成功")
    vizql_query: Optional[Dict[str, Any]] = Field(
        default=None,
        description="VizQLQueryRequest 的字典表示（成功时）"
    )
    field_count: int = Field(
        default=0,
        description="查询包含的字段数量"
    )
    has_filters: bool = Field(
        default=False,
        description="是否包含过滤器"
    )
    has_sorts: bool = Field(
        default=False,
        description="是否包含排序"
    )
    has_computations: bool = Field(
        default=False,
        description="是否包含计算（表计算或 LOD）"
    )
    error: Optional[QueryBuildError] = Field(
        default=None,
        description="错误信息（失败时）"
    )
    latency_ms: int = Field(
        default=0,
        description="构建耗时（毫秒）"
    )
    
    @classmethod
    def ok(
        cls,
        vizql_query: Dict[str, Any],
        field_count: int = 0,
        has_filters: bool = False,
        has_sorts: bool = False,
        has_computations: bool = False,
        latency_ms: int = 0
    ) -> "BuildQueryOutput":
        """创建成功响应"""
        return cls(
            success=True,
            vizql_query=vizql_query,
            field_count=field_count,
            has_filters=has_filters,
            has_sorts=has_sorts,
            has_computations=has_computations,
            latency_ms=latency_ms
        )
    
    @classmethod
    def fail(cls, error: QueryBuildError, latency_ms: int = 0) -> "BuildQueryOutput":
        """创建失败响应"""
        return cls(
            success=False,
            error=error,
            latency_ms=latency_ms
        )


__all__ = [
    "BuildQueryInput",
    "BuildQueryOutput",
    "QueryBuildError",
    "QueryBuildErrorType",
]
