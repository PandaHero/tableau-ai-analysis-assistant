from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from analytics_assistant.src.infra.config import get_config

_DEFAULT_BUSINESS_DB_PATH = "analytics_assistant/data/business.db"

_BUSINESS_DDL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS chat_sessions (
    session_id TEXT PRIMARY KEY,
    tableau_username TEXT NOT NULL,
    title TEXT NOT NULL,
    message_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_updated
ON chat_sessions(tableau_username, updated_at DESC);

CREATE TABLE IF NOT EXISTS chat_messages (
    message_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    tableau_username TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    position INTEGER NOT NULL,
    run_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(session_id, position),
    FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session_position
ON chat_messages(session_id, position ASC);

CREATE TABLE IF NOT EXISTS analysis_runs (
    run_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    request_id TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    tableau_username TEXT NOT NULL,
    question TEXT NOT NULL,
    datasource_luid TEXT,
    datasource_name TEXT,
    project_name TEXT,
    status TEXT NOT NULL,
    interrupt_id TEXT,
    interrupt_type TEXT,
    result_manifest_ref TEXT,
    error_code TEXT,
    metrics_json TEXT NOT NULL DEFAULT '{}',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_analysis_runs_session_created
ON analysis_runs(session_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_analysis_runs_user_created
ON analysis_runs(tableau_username, created_at DESC);

CREATE TABLE IF NOT EXISTS analysis_interrupts (
    interrupt_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    tableau_username TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    request_id TEXT NOT NULL,
    interrupt_type TEXT NOT NULL,
    status TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    workflow_context_json TEXT NOT NULL,
    resolved_payload_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    resolved_at TEXT,
    resolved_request_id TEXT,
    resolved_run_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_analysis_interrupts_session_created
ON analysis_interrupts(session_id, created_at DESC);

CREATE TABLE IF NOT EXISTS user_settings (
    tableau_username TEXT PRIMARY KEY,
    language TEXT NOT NULL,
    analysis_depth TEXT NOT NULL,
    theme TEXT NOT NULL,
    default_datasource_id TEXT,
    show_thinking_process INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS message_feedback (
    feedback_id TEXT PRIMARY KEY,
    tableau_username TEXT NOT NULL,
    message_id TEXT NOT NULL,
    type TEXT NOT NULL,
    reason TEXT,
    comment TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_message_feedback_user_created
ON message_feedback(tableau_username, created_at DESC);

CREATE TABLE IF NOT EXISTS query_audit_logs (
    audit_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    tableau_username TEXT NOT NULL,
    datasource_luid TEXT,
    query_text TEXT,
    status TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_query_audit_logs_run_created
ON query_audit_logs(run_id, created_at DESC);
"""


def _resolve_business_db_path() -> str:
    """读取业务存储路径。

    优先读取 `business_storage.connection_string`；未配置时回退到默认路径。
    """
    try:
        config = get_config()
        business_storage = config.get("business_storage", {})
        configured = str(business_storage.get("connection_string") or "").strip()
        if configured:
            return configured
    except Exception:
        pass
    return _DEFAULT_BUSINESS_DB_PATH


class BusinessDatabase:
    """业务表 SQLite 访问入口。

    使用独立 SQLite 文件承载结构化业务数据，避免继续把业务表塞进
    通用 BaseStore 命名空间里，方便后续切换到 Postgres。
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = str(db_path or _resolve_business_db_path()).strip()
        self._schema_lock = threading.Lock()
        self._schema_ready = False

    def ensure_schema(self) -> None:
        """按需初始化业务表结构。"""
        if self._schema_ready:
            return

        with self._schema_lock:
            if self._schema_ready:
                return

            if self.db_path != ":memory:":
                Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

            with self.connect() as conn:
                conn.executescript(_BUSINESS_DDL)
                conn.commit()

            self._schema_ready = True

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """返回开启外键约束的 SQLite 连接。"""
        uri = self.db_path.startswith("file:")
        connection = sqlite3.connect(
            self.db_path,
            check_same_thread=False,
            uri=uri,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
        finally:
            connection.close()


_default_database: Optional[BusinessDatabase] = None
_default_database_lock = threading.Lock()


def get_business_database() -> BusinessDatabase:
    """获取全局业务数据库单例。"""
    global _default_database

    if _default_database is None:
        with _default_database_lock:
            if _default_database is None:
                _default_database = BusinessDatabase()
    _default_database.ensure_schema()
    return _default_database


def reset_business_database() -> None:
    """重置业务数据库单例。

    主要供测试使用，确保不同测试间不会复用旧的数据库配置。
    """
    global _default_database
    with _default_database_lock:
        _default_database = None
