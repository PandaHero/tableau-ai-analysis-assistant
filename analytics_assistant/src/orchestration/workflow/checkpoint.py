# -*- coding: utf-8 -*-
"""LangGraph checkpointer 管理。

这里统一管理语义图和 root graph 的持久化 checkpoint。
使用 LangGraph 官方 `AsyncSqliteSaver`，避免在异步图执行中混用同步 saver。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from analytics_assistant.src.infra.config import get_config

_DEFAULT_CHECKPOINT_DB_PATH = "analytics_assistant/data/checkpoints.db"

_semantic_parser_checkpointer: Optional[AsyncSqliteSaver] = None
_semantic_parser_conn: Optional[aiosqlite.Connection] = None
_semantic_parser_loop: Optional[asyncio.AbstractEventLoop] = None
_root_graph_checkpointer: Optional[AsyncSqliteSaver] = None
_root_graph_conn: Optional[aiosqlite.Connection] = None
_root_graph_loop: Optional[asyncio.AbstractEventLoop] = None


def _resolve_checkpoint_db_path() -> str:
    """读取 checkpoint 存储路径。"""
    try:
        config = get_config()
        checkpoint_config = config.get("checkpointer", {})
        configured = str(checkpoint_config.get("connection_string") or "").strip()
        if configured:
            return configured
    except Exception:
        pass
    return _DEFAULT_CHECKPOINT_DB_PATH


async def _build_async_sqlite_saver() -> tuple[aiosqlite.Connection, AsyncSqliteSaver]:
    """创建并初始化异步 SQLite saver。"""
    db_path = _resolve_checkpoint_db_path()
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    connection = aiosqlite.connect(db_path)
    saver = AsyncSqliteSaver(connection)
    await saver.setup()
    return connection, saver


def _is_local_checkpoint_path(db_path: str) -> bool:
    """判断当前 checkpoint 路径是否是可安全删除的本地 SQLite 文件。"""
    normalized = str(db_path or "").strip()
    return bool(normalized) and normalized != ":memory:" and "://" not in normalized


def _remove_checkpoint_db_files() -> None:
    """删除本地 SQLite checkpoint 文件及其 sidecar 文件。"""
    db_path = _resolve_checkpoint_db_path()
    if not _is_local_checkpoint_path(db_path):
        return

    sqlite_path = Path(db_path)
    for candidate in (
        sqlite_path,
        Path(f"{db_path}-wal"),
        Path(f"{db_path}-shm"),
    ):
        try:
            candidate.unlink(missing_ok=True)
        except Exception:
            pass


async def _close_async_connection(connection: Optional[aiosqlite.Connection]) -> None:
    """关闭异步 SQLite 连接。"""
    if connection is None:
        return
    try:
        await connection.close()
    except Exception:
        pass


async def _reset_connections(
    connections: list[Optional[aiosqlite.Connection]],
    *,
    clear_persisted_state: bool,
) -> None:
    """关闭旧连接，并按需清理本地 checkpoint 文件。"""
    for connection in connections:
        await _close_async_connection(connection)

    if clear_persisted_state:
        _remove_checkpoint_db_files()


async def get_semantic_parser_checkpointer() -> AsyncSqliteSaver:
    """获取语义子图的持久化 checkpointer。"""
    global _semantic_parser_checkpointer
    global _semantic_parser_conn
    global _semantic_parser_loop

    current_loop = asyncio.get_running_loop()
    if (
        _semantic_parser_checkpointer is not None
        and _semantic_parser_loop is current_loop
    ):
        return _semantic_parser_checkpointer

    if _semantic_parser_conn is not None:
        await _close_async_connection(_semantic_parser_conn)

    _semantic_parser_conn, _semantic_parser_checkpointer = await _build_async_sqlite_saver()
    _semantic_parser_loop = current_loop
    return _semantic_parser_checkpointer


async def get_root_graph_checkpointer() -> AsyncSqliteSaver:
    """获取 root graph 的持久化 checkpointer。"""
    global _root_graph_checkpointer
    global _root_graph_conn
    global _root_graph_loop

    current_loop = asyncio.get_running_loop()
    if _root_graph_checkpointer is not None and _root_graph_loop is current_loop:
        return _root_graph_checkpointer

    if _root_graph_conn is not None:
        await _close_async_connection(_root_graph_conn)

    _root_graph_conn, _root_graph_checkpointer = await _build_async_sqlite_saver()
    _root_graph_loop = current_loop
    return _root_graph_checkpointer


def reset_workflow_checkpointers(*, clear_persisted_state: bool = False) -> None:
    """重置全部工作流 checkpointer。

    主要供测试使用。若当前有运行中的事件循环，则异步关闭旧连接；
    否则直接通过 `asyncio.run` 完成清理。
    `clear_persisted_state=True` 时，会额外删除本地 SQLite checkpoint 文件。
    """
    global _semantic_parser_checkpointer
    global _semantic_parser_conn
    global _semantic_parser_loop
    global _root_graph_checkpointer
    global _root_graph_conn
    global _root_graph_loop

    conns = [_semantic_parser_conn, _root_graph_conn]
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(
            _reset_connections(
                conns,
                clear_persisted_state=clear_persisted_state,
            )
        )
    else:
        loop.create_task(
            _reset_connections(
                conns,
                clear_persisted_state=clear_persisted_state,
            )
        )

    _semantic_parser_checkpointer = None
    _semantic_parser_conn = None
    _semantic_parser_loop = None
    _root_graph_checkpointer = None
    _root_graph_conn = None
    _root_graph_loop = None
