# -*- coding: utf-8 -*-
"""
中间件

统一异常处理器和请求日志中间件。
"""

import logging
import time
from typing import Callable
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from analytics_assistant.src.infra.error_sanitizer import (
    sanitize_error_message,
    sanitize_error_message as _sanitize_error_message,
)

logger = logging.getLogger(__name__)

def _get_request_id(request: Request) -> str:
    """优先复用请求头中的 request id，否则生成新的。"""
    request_id = request.headers.get("X-Request-ID")
    if request_id:
        return request_id
    return uuid4().hex

def _response_headers(request: Request) -> dict[str, str]:
    """统一附加 request id 响应头，便于前后端和日志串联。"""
    request_id = getattr(request.state, "request_id", "")
    if not request_id:
        return {}
    return {"X-Request-ID": str(request_id)}

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
        safe_detail = sanitize_error_message(str(exc.detail))
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": safe_detail},
            headers=_response_headers(request),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        """处理请求参数验证错误。"""
        request_id = getattr(request.state, "request_id", "")
        logger.warning(
            f"请求验证失败: request_id={request_id}, path={request.url.path}, "
            f"errors={exc.errors()}"
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
            headers=_response_headers(request),
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        """处理未捕获的异常。"""
        request_id = getattr(request.state, "request_id", "")
        logger.exception(
            f"未处理异常: request_id={request_id}, path={request.url.path}, error={exc}"
        )
        safe_message = sanitize_error_message(str(exc))
        return JSONResponse(
            status_code=500,
            content={"error": safe_message},
            headers=_response_headers(request),
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
        request.state.request_id = _get_request_id(request)
        request_id = request.state.request_id
        username = request.headers.get("X-Tableau-Username", "anonymous")
        method = request.method
        path = request.url.path

        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            elapsed = time.time() - start_time
            logger.info(
                f"API 请求: request_id={request_id}, user={username}, "
                f"method={method}, path={path}, status={response.status_code}, "
                f"duration={elapsed:.3f}s"
            )
            return response
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(
                f"API 请求异常: request_id={request_id}, user={username}, "
                f"method={method}, path={path}, duration={elapsed:.3f}s, error={e}"
            )
            raise
