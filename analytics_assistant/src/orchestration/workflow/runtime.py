# -*- coding: utf-8 -*-
"""工作流运行时持久化辅助函数。

当前只承载中断记录读写。底层已经切换到结构化业务仓库，不再通过
通用 BaseRepository 的命名空间 KV 持久化中断状态。
"""

from __future__ import annotations

from typing import Any, Optional

from analytics_assistant.src.api.dependencies import get_interrupt_repository


def get_interrupt_record(session_id: str, interrupt_id: str) -> Optional[dict[str, Any]]:
    """获取指定会话下的中断记录。"""
    return get_interrupt_repository().get_interrupt(
        session_id=session_id,
        interrupt_id=interrupt_id,
    )


def save_pending_interrupt(
    *,
    session_id: str,
    interrupt_id: str,
    tableau_username: str,
    thread_id: str,
    run_id: str,
    request_id: str,
    interrupt_type: str,
    payload: dict[str, Any],
    workflow_context: dict[str, Any],
) -> dict[str, Any]:
    """写入待恢复中断。"""
    return get_interrupt_repository().save_pending_interrupt(
        session_id=session_id,
        interrupt_id=interrupt_id,
        tableau_username=tableau_username,
        thread_id=thread_id,
        run_id=run_id,
        request_id=request_id,
        interrupt_type=interrupt_type,
        payload=payload,
        workflow_context=workflow_context,
    )


def mark_interrupt_resolved(
    *,
    session_id: str,
    interrupt_id: str,
    resume_payload: dict[str, Any],
    request_id: Optional[str] = None,
    run_id: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """标记中断已恢复，并保存恢复载荷审计信息。"""
    return get_interrupt_repository().mark_resolved(
        session_id=session_id,
        interrupt_id=interrupt_id,
        resume_payload=resume_payload,
        request_id=request_id,
        run_id=run_id,
    )
