# -*- coding: utf-8 -*-
"""
聊天路由

提供 SSE 流式聊天端点 POST /api/chat/stream。
集成 HistoryManager 进行对话历史裁剪，WorkflowExecutor 执行工作流。
"""

import asyncio
import logging
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from analytics_assistant.src.agents.semantic_parser.components.history_manager import (
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
_DEFAULT_SSE_KEEPALIVE = 30


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


@router.post("/stream")
async def chat_stream(
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
    logger.info(
        f"收到聊天请求: user={tableau_username}, "
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

        original_tokens = history_manager.estimate_history_tokens(history)
        truncated_tokens = history_manager.estimate_history_tokens(
            truncated_history,
        )
        logger.info(
            f"对话历史裁剪: {len(history)} → {len(truncated_history)} 条消息, "
            f"{original_tokens} → {truncated_tokens} tokens"
        )

        # 2. 创建工作流执行器
        executor = WorkflowExecutor(tableau_username)

        # 3. 返回 SSE 流式响应
        keepalive_seconds = _get_sse_keepalive()

        async def event_generator() -> AsyncIterator[str]:
            """SSE 事件生成器，带心跳保活。"""
            try:
                async for event in _stream_with_heartbeat(
                    executor.execute_stream(
                        question=request.messages[-1].content,
                        datasource_name=request.datasource_name,
                        history=truncated_history,
                        language=request.language,
                        analysis_depth=request.analysis_depth,
                        session_id=request.session_id,
                    ),
                    keepalive_seconds=keepalive_seconds,
                ):
                    yield event
            except Exception as e:
                logger.exception(f"SSE 流生成失败: {e}")
                yield format_sse_event({
                    "type": "error",
                    "error": "工作流执行失败，请稍后重试",
                })

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
        logger.exception(f"聊天请求处理失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误") from e


async def _stream_with_heartbeat(
    event_stream: AsyncIterator,
    keepalive_seconds: int = _DEFAULT_SSE_KEEPALIVE,
) -> AsyncIterator[str]:
    """为 SSE 事件流添加心跳保活。

    在事件间隔超过 keepalive_seconds 时发送心跳注释，
    防止代理或浏览器超时断开连接。

    Args:
        event_stream: 原始事件流（yield Dict）
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
            yield format_sse_event(event)
        except asyncio.TimeoutError:
            # 超时未收到事件，发送心跳
            yield format_sse_heartbeat()
        except StopAsyncIteration:
            break
