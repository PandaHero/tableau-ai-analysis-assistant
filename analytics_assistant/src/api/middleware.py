# -*- coding: utf-8 -*-
"""API middleware and exception handling."""

from __future__ import annotations

import logging
import time
from typing import Callable
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from analytics_assistant.src.infra.error_sanitizer import sanitize_error_message

logger = logging.getLogger(__name__)


def _get_request_id(request: Request) -> str:
    """Reuse caller request id when present, otherwise generate one."""
    request_id = request.headers.get("X-Request-ID")
    if request_id:
        return request_id
    return uuid4().hex


def _response_headers(request: Request) -> dict[str, str]:
    """Attach request id to all API responses."""
    request_id = getattr(request.state, "request_id", "")
    if not request_id:
        return {}
    return {"X-Request-ID": str(request_id)}


def register_exception_handlers(app: FastAPI) -> None:
    """Register global exception handlers."""

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
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
        request_id = getattr(request.state, "request_id", "")
        logger.warning(
            "请求参数校验失败: request_id=%s path=%s errors=%s",
            request_id,
            request.url.path,
            exc.errors(),
        )
        return JSONResponse(
            status_code=422,
            content={
                "error": "请求参数校验失败",
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
        request_id = getattr(request.state, "request_id", "")
        logger.exception(
            "未处理异常: request_id=%s path=%s error=%s",
            request_id,
            request.url.path,
            exc,
        )
        safe_message = sanitize_error_message(str(exc))
        return JSONResponse(
            status_code=500,
            content={"error": safe_message},
            headers=_response_headers(request),
        )


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log request path, caller and latency."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable,
    ) -> Response:
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
                "API 请求: request_id=%s user=%s method=%s path=%s status=%s duration=%.3fs",
                request_id,
                username,
                method,
                path,
                response.status_code,
                elapsed,
            )
            return response
        except Exception as exc:
            elapsed = time.time() - start_time
            logger.error(
                "API 请求异常: request_id=%s user=%s method=%s path=%s duration=%.3fs error=%s",
                request_id,
                username,
                method,
                path,
                elapsed,
                exc,
            )
            raise
