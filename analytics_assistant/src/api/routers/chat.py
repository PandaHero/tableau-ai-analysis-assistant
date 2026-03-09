# -*- coding: utf-8 -*-
"""
聊天路由

提供 SSE 流式聊天端点 POST /api/chat/stream。
集成 HistoryManager 进行对话历史裁剪，WorkflowExecutor 执行工作流。
"""

import asyncio
import logging
from typing import Any, AsyncIterator, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from analytics_assistant.src.orchestration.workflow.history import (
    get_history_manager,
)
from analytics_assistant.src.api.dependencies import get_tableau_username
from analytics_assistant.src.api.models.chat import ChatRequest
from analytics_assistant.src.api.utils.sse import format_sse_event, format_sse_heartbeat
from analytics_assistant.src.infra.config import get_config
from analytics_assistant.src.orchestration.workflow.executor import WorkflowExecutor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])

# 默认心跳间隔（秒）
_DEFAULT_SSE_KEEPALIVE = 120  # 增加到 120 秒,给字段语义推断足够时间

def _get_sse_keepalive() -> int:
    """从 app.yaml 读取 SSE 心跳间隔。

    Returns:
        心跳间隔秒数
    """
    try:
        config = get_config()
        return config.get("api", {}).get(
            "timeout", {},
        ).get("sse_keepalive", _DEFAULT_SSE_KEEPALIVE)
    except Exception:
        return _DEFAULT_SSE_KEEPALIVE

def _estimate_history_tokens(history_manager: object, history: list[dict[str, str]]) -> int:
    """兼容不同 HistoryManager 接口，尽量拿到 token 数。"""
    check_tokens = getattr(history_manager, "check_history_tokens", None)
    if callable(check_tokens):
        try:
            result = check_tokens(history)
            if isinstance(result, tuple) and result:
                return int(result[0])
            if isinstance(result, list) and result:
                return int(result[0])
            if isinstance(result, int):
                return result
        except Exception:
            pass

    estimate_tokens = getattr(history_manager, "estimate_history_tokens", None)
    if callable(estimate_tokens):
        try:
            return int(estimate_tokens(history))
        except Exception:
            pass

    return 0

def _with_request_id(event: dict[str, Any], request_id: Optional[str]) -> dict[str, Any]:
    """为 SSE 事件附加 requestId，方便前后端联调和日志串联。"""
    if not request_id or event.get("requestId"):
        return event
    enriched = dict(event)
    enriched["requestId"] = request_id
    return enriched

@router.post("/stream")
async def chat_stream(
    http_request: Request,
    request: ChatRequest,
    tableau_username: str = Depends(get_tableau_username),
) -> StreamingResponse:
    """SSE 流式聊天端点。

    接收用户消息，执行工作流，返回 SSE 事件流。
    包含心跳保活机制，防止连接超时断开。

    Args:
        request: 聊天请求（messages, datasource_name, language 等）
        tableau_username: Tableau 用户名（从请求头获取）

    Returns:
        SSE StreamingResponse
    """
    request_id = getattr(http_request.state, "request_id", "")
    logger.info(
        f"收到聊天请求: request_id={request_id}, user={tableau_username}, "
        f"datasource={request.datasource_name}, "
        f"messages={len(request.messages)}, "
        f"language={request.language}"
    )

    try:
        # 1. 裁剪对话历史（按 token 数量）
        history_manager = get_history_manager()
        history = [
            {"role": msg.role, "content": msg.content}
            for msg in request.messages
        ]
        truncated_history = history_manager.truncate_history(history)

        original_tokens = _estimate_history_tokens(history_manager, history)
        truncated_tokens = _estimate_history_tokens(history_manager, truncated_history)
        logger.info(
            f"对话历史裁剪: {len(history)} → {len(truncated_history)} 条消息, "
            f"{original_tokens} → {truncated_tokens} tokens, "
            f"request_id={request_id}"
        )

        # 2. 创建工作流执行器
        logger.info("=" * 60)
        logger.info(f"[chat_stream] 创建 WorkflowExecutor: request_id={request_id}")
        executor = WorkflowExecutor(tableau_username, request_id=request_id or None)
        logger.info(f"[chat_stream] WorkflowExecutor 创建完成: request_id={request_id}")

        # 3. 返回 SSE 流式响应
        keepalive_seconds = _get_sse_keepalive()
        logger.info(
            f"[chat_stream] 开始执行工作流, keepalive={keepalive_seconds}s, "
            f"request_id={request_id}"
        )

        async def event_generator() -> AsyncIterator[str]:
            """SSE 事件生成器，带心跳保活。"""
            logger.info(f"[event_generator] 开始生成事件: request_id={request_id}")
            try:
                logger.info(
                    f"[event_generator] 调用 executor.execute_stream(): "
                    f"request_id={request_id}"
                )
                async for event in _stream_with_heartbeat(
                    executor.execute_stream(
                        question=request.messages[-1].content,
                        datasource_name=request.datasource_name,
                        history=truncated_history,
                        language=request.language,
                        analysis_depth=request.analysis_depth,
                        replan_mode=request.replan_mode,
                        selected_candidate_question=request.selected_candidate_question,
                        session_id=request.session_id,
                    ),
                    keepalive_seconds=keepalive_seconds,
                    request_id=request_id or None,
                ):
                    # event 是已格式化的 SSE 字符串，日志仅记录前 80 字符供调试
                    logger.debug(f"[event_generator] 发送 SSE: {repr(event[:80])}")
                    yield event
                logger.info(f"[event_generator] 事件生成完成: request_id={request_id}")
            except Exception as e:
                logger.exception(f"SSE 流生成失败: request_id={request_id}, error={e}")
                yield format_sse_event(_with_request_id({
                    "type": "error",
                    "error": "工作流执行失败，请稍后重试",
                }, request_id or None))

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"聊天请求处理失败: request_id={request_id}, error={e}")
        raise HTTPException(status_code=500, detail="服务器内部错误") from e

async def _stream_with_heartbeat(
    event_stream: AsyncIterator,
    keepalive_seconds: int = _DEFAULT_SSE_KEEPALIVE,
    request_id: Optional[str] = None,
) -> AsyncIterator[str]:
    """为 SSE 事件流添加心跳保活。

    在事件间隔超过 keepalive_seconds 时发送心跳注释，
    防止代理或浏览器超时断开连接。

    Args:
        event_stream: 原始事件流（yield dict）
        keepalive_seconds: 心跳间隔秒数

    Yields:
        SSE 格式字符串（事件或心跳）
    """
    aiter = event_stream.__aiter__()

    while True:
        try:
            event = await asyncio.wait_for(
                aiter.__anext__(),
                timeout=float(keepalive_seconds),
            )
            if isinstance(event, dict):
                event = _with_request_id(event, request_id)
            yield format_sse_event(event)
        except asyncio.TimeoutError:
            # 超时未收到事件，发送心跳
            yield format_sse_heartbeat()
        except StopAsyncIteration:
            break
