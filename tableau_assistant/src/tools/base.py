"""
Tool Base - 工具基础结构

提供工具定义的基础设施：
- 结构化错误响应
- Pydantic 输入验证
- 工具装饰器增强
- 通用工具响应模型
"""
from typing import Dict, Optional, TypeVar, Generic, Union, List
from pydantic import BaseModel, Field
from enum import Enum
import logging
import traceback
from functools import wraps

logger = logging.getLogger(__name__)


class ToolErrorCode(str, Enum):
    """工具错误代码"""
    VALIDATION_ERROR = "VALIDATION_ERROR"
    EXECUTION_ERROR = "EXECUTION_ERROR"
    DEPENDENCY_ERROR = "DEPENDENCY_ERROR"
    TIMEOUT_ERROR = "TIMEOUT_ERROR"
    NOT_FOUND_ERROR = "NOT_FOUND_ERROR"
    PERMISSION_ERROR = "PERMISSION_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ToolError(BaseModel):
    """工具错误响应"""
    code: ToolErrorCode = Field(description="错误代码")
    message: str = Field(description="错误消息")
    details: Optional[Dict[str, str]] = Field(default=None, description="错误详情")
    recoverable: bool = Field(default=True, description="是否可恢复")
    suggestion: Optional[str] = Field(default=None, description="建议操作")


T = TypeVar("T")


class ToolResponse(BaseModel, Generic[T]):
    """
    通用工具响应模型
    
    所有工具应返回此格式，确保一致的错误处理。
    
    Attributes:
        success: 是否成功
        data: 成功时的数据
        error: 失败时的错误信息
    """
    success: bool = Field(description="是否成功")
    data: Optional[T] = Field(default=None, description="成功时的数据")
    error: Optional[ToolError] = Field(default=None, description="失败时的错误信息")
    
    @classmethod
    def ok(cls, data: T) -> "ToolResponse[T]":
        """创建成功响应"""
        return cls(success=True, data=data)
    
    @classmethod
    def fail(
        cls,
        code: ToolErrorCode,
        message: str,
        details: Optional[Dict[str, str]] = None,
        recoverable: bool = True,
        suggestion: Optional[str] = None
    ) -> "ToolResponse[T]":
        """创建失败响应"""
        return cls(
            success=False,
            error=ToolError(
                code=code,
                message=message,
                details=details,
                recoverable=recoverable,
                suggestion=suggestion
            )
        )


def format_tool_response(response: ToolResponse) -> str:
    """
    格式化工具响应为 LLM 友好的字符串
    
    Args:
        response: 工具响应
    
    Returns:
        格式化的字符串
    """
    if response.success:
        if isinstance(response.data, str):
            return response.data
        elif isinstance(response.data, dict):
            return _format_dict_for_llm(response.data)
        elif isinstance(response.data, list):
            return _format_list_for_llm(response.data)
        else:
            return str(response.data)
    else:
        error = response.error
        parts = [f"<error code=\"{error.code.value}\">"]
        parts.append(f"  <message>{error.message}</message>")
        if error.details:
            parts.append(f"  <details>{error.details}</details>")
        if error.suggestion:
            parts.append(f"  <suggestion>{error.suggestion}</suggestion>")
        parts.append("</error>")
        return "\n".join(parts)


def _format_dict_for_llm(data: Dict[str, object], indent: int = 0) -> str:
    """格式化字典为 LLM 友好格式"""
    lines = []
    prefix = "  " * indent
    for key, value in data.items():
        if isinstance(value, dict):
            lines.append(f"{prefix}{key}:")
            lines.append(_format_dict_for_llm(value, indent + 1))
        elif isinstance(value, list):
            lines.append(f"{prefix}{key}:")
            lines.append(_format_list_for_llm(value, indent + 1))
        else:
            lines.append(f"{prefix}{key}: {value}")
    return "\n".join(lines)


def _format_list_for_llm(data: List[object], indent: int = 0) -> str:
    """格式化列表为 LLM 友好格式"""
    lines = []
    prefix = "  " * indent
    for i, item in enumerate(data):
        if isinstance(item, dict):
            lines.append(f"{prefix}- [{i}]:")
            lines.append(_format_dict_for_llm(item, indent + 1))
        elif isinstance(item, list):
            lines.append(f"{prefix}- [{i}]:")
            lines.append(_format_list_for_llm(item, indent + 1))
        else:
            lines.append(f"{prefix}- {item}")
    return "\n".join(lines)


def safe_tool_execution(func):
    """
    工具安全执行装饰器
    
    捕获异常并转换为结构化错误响应。
    
    Usage:
        @safe_tool_execution
        def my_tool(arg: str) -> str:
            ...
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ValueError as e:
            logger.warning(f"Tool validation error in {func.__name__}: {e}")
            response = ToolResponse.fail(
                code=ToolErrorCode.VALIDATION_ERROR,
                message=str(e),
                recoverable=True,
                suggestion="请检查输入参数是否正确"
            )
            return format_tool_response(response)
        except PermissionError as e:
            logger.warning(f"Tool permission error in {func.__name__}: {e}")
            response = ToolResponse.fail(
                code=ToolErrorCode.PERMISSION_ERROR,
                message=str(e),
                recoverable=False,
                suggestion="请检查权限配置"
            )
            return format_tool_response(response)
        except TimeoutError as e:
            logger.warning(f"Tool timeout in {func.__name__}: {e}")
            response = ToolResponse.fail(
                code=ToolErrorCode.TIMEOUT_ERROR,
                message=str(e),
                recoverable=True,
                suggestion="请稍后重试"
            )
            return format_tool_response(response)
        except Exception as e:
            logger.error(f"Tool execution error in {func.__name__}: {e}\n{traceback.format_exc()}")
            response = ToolResponse.fail(
                code=ToolErrorCode.INTERNAL_ERROR,
                message=f"工具执行失败: {str(e)}",
                details={"exception_type": type(e).__name__},
                recoverable=False
            )
            return format_tool_response(response)
    
    return wrapper


def safe_async_tool_execution(func):
    """
    异步工具安全执行装饰器
    
    捕获异常并转换为结构化错误响应。
    
    Usage:
        @safe_async_tool_execution
        async def my_async_tool(arg: str) -> str:
            ...
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except ValueError as e:
            logger.warning(f"Tool validation error in {func.__name__}: {e}")
            response = ToolResponse.fail(
                code=ToolErrorCode.VALIDATION_ERROR,
                message=str(e),
                recoverable=True,
                suggestion="请检查输入参数是否正确"
            )
            return format_tool_response(response)
        except PermissionError as e:
            logger.warning(f"Tool permission error in {func.__name__}: {e}")
            response = ToolResponse.fail(
                code=ToolErrorCode.PERMISSION_ERROR,
                message=str(e),
                recoverable=False,
                suggestion="请检查权限配置"
            )
            return format_tool_response(response)
        except TimeoutError as e:
            logger.warning(f"Tool timeout in {func.__name__}: {e}")
            response = ToolResponse.fail(
                code=ToolErrorCode.TIMEOUT_ERROR,
                message=str(e),
                recoverable=True,
                suggestion="请稍后重试"
            )
            return format_tool_response(response)
        except Exception as e:
            logger.error(f"Tool execution error in {func.__name__}: {e}\n{traceback.format_exc()}")
            response = ToolResponse.fail(
                code=ToolErrorCode.INTERNAL_ERROR,
                message=f"工具执行失败: {str(e)}",
                details={"exception_type": type(e).__name__},
                recoverable=False
            )
            return format_tool_response(response)
    
    return wrapper


# Pydantic 输入模型基类
class ToolInputBase(BaseModel):
    """工具输入基类"""
    
    model_config = {
        "extra": "forbid",  # 禁止额外字段
        "validate_assignment": True,  # 赋值时验证
    }


__all__ = [
    "ToolErrorCode",
    "ToolError",
    "ToolResponse",
    "ToolInputBase",
    "format_tool_response",
    "safe_tool_execution",
    "safe_async_tool_execution",
]
