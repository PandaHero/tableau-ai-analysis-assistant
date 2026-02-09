# -*- coding: utf-8 -*-
"""
中间件

统一异常处理器和请求日志中间件。
"""

import logging
import time
from typing import Callable

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

# 敏感关键词列表，用于过滤错误消息中的内部细节
_SENSITIVE_KEYWORDS = [
    "api_key",
    "api_secret",
    "password",
    "token",
    "secret",
    "connection_string",
    "sqlite",
    "postgresql",
    "postgres",
    "traceback",
    "file \"",
    "\\analytics_assistant\\",
    "/analytics_assistant/",
    "deepseek",
    "zhipu",
    "openai",
    "sk-",
    "conn_string",
    "db_path",
]


def _sanitize_error_message(message: str) -> str:
    """清理错误消息，移除可能泄露内部细节的内容。

    Args:
        message: 原始错误消息

    Returns:
        清理后的安全错误消息
    """
    for keyword in _SENSITIVE_KEYWORDS:
        if keyword.lower() in message.lower():
            return "服务内部错误，请稍后重试"
    return message


def register_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理器。

    Args:
        app: FastAPI 应用实例
    """

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        """处理 HTTP 异常（401、403、404 等）。"""
        safe_detail = _sanitize_error_message(str(exc.detail))
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": safe_detail},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        """处理请求参数验证错误。"""
        logger.warning(
            f"请求验证失败: path={request.url.path}, errors={exc.errors()}"
        )
        return JSONResponse(
            status_code=422,
            content={
                "error": "请求参数验证失败",
                "details": [
                    {
                        "field": ".".join(str(loc) for loc in err.get("loc", [])),
                        "message": err.get("msg", ""),
                    }
                    for err in exc.errors()
                ],
            },
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        """处理未捕获的异常。"""
        logger.exception(
            f"未处理异常: path={request.url.path}, error={exc}"
        )
        safe_message = _sanitize_error_message(str(exc))
        return JSONResponse(
            status_code=500,
            content={"error": safe_message},
        )


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """请求日志中间件，记录每个请求的用户名、端点、耗时。"""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable,
    ) -> Response:
        """处理请求并记录日志。"""
        start_time = time.time()
        username = request.headers.get("X-Tableau-Username", "anonymous")
        method = request.method
        path = request.url.path

        try:
            response = await call_next(request)
            elapsed = time.time() - start_time
            logger.info(
                f"API 请求: user={username}, method={method}, "
                f"path={path}, status={response.status_code}, "
                f"duration={elapsed:.3f}s"
            )
            return response
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(
                f"API 请求异常: user={username}, method={method}, "
                f"path={path}, duration={elapsed:.3f}s, error={e}"
            )
            raise
