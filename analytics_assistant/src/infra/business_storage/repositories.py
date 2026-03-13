from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from .database import BusinessDatabase, get_business_database


def _utc_now_iso() -> str:
    """统一生成 UTC ISO 时间戳。"""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _dumps_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _loads_json(raw_value: Any, *, default: Any) -> Any:
    if raw_value in (None, ""):
        return default
    try:
        return json.loads(str(raw_value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


class _RepositoryBase:
    """业务仓库公共基类。"""

    namespace = "business"

    def __init__(self, database: Optional[BusinessDatabase] = None) -> None:
        self._database = database or get_business_database()
        self._database.ensure_schema()


class MessageRepository(_RepositoryBase):
    """会话消息仓库。"""

    namespace = "chat_messages"

    def list_messages(self, session_id: str) -> list[dict[str, str]]:
        with self._database.connect() as conn:
            rows = conn.execute(
                """
                SELECT role, content
                FROM chat_messages
                WHERE session_id = ?
                ORDER BY position ASC
                """,
                (session_id,),
            ).fetchall()
        return [
            {
                "role": str(row["role"]),
                "content": str(row["content"]),
            }
            for row in rows
        ]

    def replace_messages(
        self,
        *,
        session_id: str,
        tableau_username: str,
        messages: list[dict[str, str]],
        run_id: Optional[str] = None,
    ) -> None:
        now = _utc_now_iso()
        with self._database.connect() as conn:
            conn.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
            for position, message in enumerate(messages, start=1):
                conn.execute(
                    """
                    INSERT INTO chat_messages (
                        message_id, session_id, tableau_username, role, content,
                        position, run_id, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        session_id,
                        tableau_username,
                        str(message.get("role") or "").strip(),
                        str(message.get("content") or "").strip(),
                        position,
                        run_id,
                        now,
                        now,
                    ),
                )
            conn.execute(
                """
                UPDATE chat_sessions
                SET message_count = ?, updated_at = ?
                WHERE session_id = ?
                """,
                (len(messages), now, session_id),
            )
            conn.commit()

    def append_message(
        self,
        *,
        session_id: str,
        tableau_username: str,
        role: str,
        content: str,
        run_id: Optional[str] = None,
    ) -> dict[str, Any]:
        now = _utc_now_iso()
        normalized_role = str(role or "").strip()
        normalized_content = str(content or "").strip()
        if not normalized_role or not normalized_content:
            raise ValueError("message role and content must not be empty")

        with self._database.connect() as conn:
            row = conn.execute(
                """
                SELECT COALESCE(MAX(position), 0) AS max_position
                FROM chat_messages
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
            position = int(row["max_position"]) + 1
            message_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO chat_messages (
                    message_id, session_id, tableau_username, role, content,
                    position, run_id, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    session_id,
                    tableau_username,
                    normalized_role,
                    normalized_content,
                    position,
                    run_id,
                    now,
                    now,
                ),
            )
            conn.execute(
                """
                UPDATE chat_sessions
                SET message_count = message_count + 1, updated_at = ?
                WHERE session_id = ?
                """,
                (now, session_id),
            )
            conn.commit()
        return {
            "message_id": message_id,
            "session_id": session_id,
            "tableau_username": tableau_username,
            "role": normalized_role,
            "content": normalized_content,
            "position": position,
            "run_id": run_id,
            "created_at": now,
            "updated_at": now,
        }


class SessionRepository(_RepositoryBase):
    """会话仓库。

    该仓库负责会话元数据与消息的聚合查询，满足：
    - 会话 CRUD
    - 数据库分页
    - 消息单独落表
    """

    namespace = "sessions"

    def __init__(
        self,
        database: Optional[BusinessDatabase] = None,
        message_repository: Optional[MessageRepository] = None,
    ) -> None:
        super().__init__(database=database)
        self._messages = message_repository or MessageRepository(self._database)

    def _fetch_messages_map(
        self,
        *,
        conn: Any,
        session_ids: list[str],
    ) -> dict[str, list[dict[str, str]]]:
        if not session_ids:
            return {}

        placeholders = ", ".join("?" for _ in session_ids)
        rows = conn.execute(
            f"""
            SELECT session_id, role, content
            FROM chat_messages
            WHERE session_id IN ({placeholders})
            ORDER BY session_id ASC, position ASC
            """,
            tuple(session_ids),
        ).fetchall()

        messages_map: dict[str, list[dict[str, str]]] = {
            session_id: [] for session_id in session_ids
        }
        for row in rows:
            messages_map[str(row["session_id"])].append({
                "role": str(row["role"]),
                "content": str(row["content"]),
            })
        return messages_map

    def create_session(
        self,
        *,
        session_id: str,
        tableau_username: str,
        title: str,
    ) -> dict[str, Any]:
        now = _utc_now_iso()
        with self._database.connect() as conn:
            conn.execute(
                """
                INSERT INTO chat_sessions (
                    session_id, tableau_username, title, message_count, created_at, updated_at
                )
                VALUES (?, ?, ?, 0, ?, ?)
                """,
                (session_id, tableau_username, title, now, now),
            )
            conn.commit()
        return {
            "id": session_id,
            "tableau_username": tableau_username,
            "title": title,
            "messages": [],
            "created_at": now,
            "updated_at": now,
        }

    def ensure_session(
        self,
        *,
        session_id: str,
        tableau_username: str,
        title: str,
    ) -> dict[str, Any]:
        existing = self.find_by_id(session_id)
        if existing is not None:
            if existing.get("tableau_username") != tableau_username:
                raise ValueError("session belongs to another user")
            return existing
        return self.create_session(
            session_id=session_id,
            tableau_username=tableau_username,
            title=title,
        )

    def find_by_id(self, session_id: str) -> Optional[dict[str, Any]]:
        with self._database.connect() as conn:
            row = conn.execute(
                """
                SELECT session_id, tableau_username, title, message_count, created_at, updated_at
                FROM chat_sessions
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
            if row is None:
                return None
            messages = self._fetch_messages_map(conn=conn, session_ids=[session_id]).get(
                session_id,
                [],
            )
        return {
            "id": str(row["session_id"]),
            "tableau_username": str(row["tableau_username"]),
            "title": str(row["title"]),
            "messages": messages,
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
        }

    def list_for_user(
        self,
        *,
        tableau_username: str,
        offset: int,
        limit: int,
    ) -> tuple[list[dict[str, Any]], int]:
        with self._database.connect() as conn:
            total_row = conn.execute(
                """
                SELECT COUNT(*) AS total
                FROM chat_sessions
                WHERE tableau_username = ?
                """,
                (tableau_username,),
            ).fetchone()
            total = int(total_row["total"]) if total_row is not None else 0

            rows = conn.execute(
                """
                SELECT session_id, tableau_username, title, message_count, created_at, updated_at
                FROM chat_sessions
                WHERE tableau_username = ?
                ORDER BY updated_at DESC, session_id DESC
                LIMIT ? OFFSET ?
                """,
                (tableau_username, int(limit), int(offset)),
            ).fetchall()
            session_ids = [str(row["session_id"]) for row in rows]
            messages_map = self._fetch_messages_map(conn=conn, session_ids=session_ids)

        sessions = [
            {
                "id": str(row["session_id"]),
                "tableau_username": str(row["tableau_username"]),
                "title": str(row["title"]),
                "messages": messages_map.get(str(row["session_id"]), []),
                "created_at": str(row["created_at"]),
                "updated_at": str(row["updated_at"]),
            }
            for row in rows
        ]
        return sessions, total

    def update_session(
        self,
        *,
        session_id: str,
        title: Optional[str] = None,
        messages: Optional[list[dict[str, str]]] = None,
    ) -> Optional[dict[str, Any]]:
        existing = self.find_by_id(session_id)
        if existing is None:
            return None

        next_title = str(title if title is not None else existing["title"])
        next_messages = (
            list(messages)
            if messages is not None
            else list(existing.get("messages") or [])
        )
        now = _utc_now_iso()

        with self._database.connect() as conn:
            conn.execute(
                """
                UPDATE chat_sessions
                SET title = ?, message_count = ?, updated_at = ?
                WHERE session_id = ?
                """,
                (next_title, len(next_messages), now, session_id),
            )
            conn.commit()

        self._messages.replace_messages(
            session_id=session_id,
            tableau_username=str(existing["tableau_username"]),
            messages=next_messages,
        )
        return self.find_by_id(session_id)

    def delete_session(self, session_id: str) -> bool:
        with self._database.connect() as conn:
            row = conn.execute(
                "DELETE FROM chat_sessions WHERE session_id = ?",
                (session_id,),
            )
            conn.commit()
        return int(row.rowcount or 0) > 0

    def append_message(
        self,
        *,
        session_id: str,
        tableau_username: str,
        role: str,
        content: str,
        run_id: Optional[str] = None,
    ) -> dict[str, Any]:
        return self._messages.append_message(
            session_id=session_id,
            tableau_username=tableau_username,
            role=role,
            content=content,
            run_id=run_id,
        )


class SettingsRepository(_RepositoryBase):
    """用户设置仓库。"""

    namespace = "user_settings"

    def find_by_id(self, tableau_username: str) -> Optional[dict[str, Any]]:
        with self._database.connect() as conn:
            row = conn.execute(
                """
                SELECT tableau_username, language, analysis_depth, theme,
                       default_datasource_id, show_thinking_process,
                       created_at, updated_at
                FROM user_settings
                WHERE tableau_username = ?
                """,
                (tableau_username,),
            ).fetchone()
        if row is None:
            return None
        return {
            "tableau_username": str(row["tableau_username"]),
            "language": str(row["language"]),
            "analysis_depth": str(row["analysis_depth"]),
            "theme": str(row["theme"]),
            "default_datasource_id": row["default_datasource_id"],
            "show_thinking_process": bool(row["show_thinking_process"]),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
        }

    def save(self, tableau_username: str, data: dict[str, Any]) -> dict[str, Any]:
        existing = self.find_by_id(tableau_username)
        now = _utc_now_iso()
        created_at = (existing or {}).get("created_at", now)
        payload = {
            "tableau_username": tableau_username,
            "language": str(data.get("language") or "zh"),
            "analysis_depth": str(data.get("analysis_depth") or "detailed"),
            "theme": str(data.get("theme") or "light"),
            "default_datasource_id": data.get("default_datasource_id"),
            "show_thinking_process": 1 if bool(data.get("show_thinking_process", True)) else 0,
            "created_at": created_at,
            "updated_at": now,
        }

        with self._database.connect() as conn:
            conn.execute(
                """
                INSERT INTO user_settings (
                    tableau_username, language, analysis_depth, theme,
                    default_datasource_id, show_thinking_process, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(tableau_username) DO UPDATE SET
                    language = excluded.language,
                    analysis_depth = excluded.analysis_depth,
                    theme = excluded.theme,
                    default_datasource_id = excluded.default_datasource_id,
                    show_thinking_process = excluded.show_thinking_process,
                    updated_at = excluded.updated_at
                """,
                (
                    payload["tableau_username"],
                    payload["language"],
                    payload["analysis_depth"],
                    payload["theme"],
                    payload["default_datasource_id"],
                    payload["show_thinking_process"],
                    payload["created_at"],
                    payload["updated_at"],
                ),
            )
            conn.commit()

        payload["show_thinking_process"] = bool(payload["show_thinking_process"])
        return payload


class FeedbackRepository(_RepositoryBase):
    """反馈仓库。"""

    namespace = "user_feedback"

    def save(self, feedback_id: str, data: dict[str, Any]) -> dict[str, Any]:
        now = _utc_now_iso()
        payload = {
            "feedback_id": feedback_id,
            "tableau_username": str(data.get("tableau_username") or "").strip(),
            "message_id": str(data.get("message_id") or "").strip(),
            "type": str(data.get("type") or "").strip(),
            "reason": data.get("reason"),
            "comment": data.get("comment"),
            "created_at": now,
            "updated_at": now,
        }
        with self._database.connect() as conn:
            conn.execute(
                """
                INSERT INTO message_feedback (
                    feedback_id, tableau_username, message_id, type,
                    reason, comment, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["feedback_id"],
                    payload["tableau_username"],
                    payload["message_id"],
                    payload["type"],
                    payload["reason"],
                    payload["comment"],
                    payload["created_at"],
                    payload["updated_at"],
                ),
            )
            conn.commit()
        return payload

    def find_by_id(self, feedback_id: str) -> Optional[dict[str, Any]]:
        with self._database.connect() as conn:
            row = conn.execute(
                """
                SELECT feedback_id, tableau_username, message_id, type,
                       reason, comment, created_at, updated_at
                FROM message_feedback
                WHERE feedback_id = ?
                """,
                (feedback_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "feedback_id": str(row["feedback_id"]),
            "tableau_username": str(row["tableau_username"]),
            "message_id": str(row["message_id"]),
            "type": str(row["type"]),
            "reason": row["reason"],
            "comment": row["comment"],
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
        }


class AnalysisRunRepository(_RepositoryBase):
    """分析运行仓库。"""

    namespace = "analysis_runs"

    def create_run(
        self,
        *,
        run_id: str,
        session_id: str,
        request_id: str,
        thread_id: str,
        tableau_username: str,
        question: str,
        datasource_luid: Optional[str],
        datasource_name: Optional[str],
        project_name: Optional[str],
        status: str,
        metrics: Optional[dict[str, Any]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        now = _utc_now_iso()
        payload = {
            "run_id": run_id,
            "session_id": session_id,
            "request_id": request_id,
            "thread_id": thread_id,
            "tableau_username": tableau_username,
            "question": question,
            "datasource_luid": datasource_luid,
            "datasource_name": datasource_name,
            "project_name": project_name,
            "status": status,
            "interrupt_id": None,
            "interrupt_type": None,
            "result_manifest_ref": None,
            "error_code": None,
            "metrics_json": _dumps_json(metrics or {}),
            "metadata_json": _dumps_json(metadata or {}),
            "created_at": now,
            "updated_at": now,
        }
        with self._database.connect() as conn:
            conn.execute(
                """
                INSERT INTO analysis_runs (
                    run_id, session_id, request_id, thread_id, tableau_username,
                    question, datasource_luid, datasource_name, project_name, status,
                    interrupt_id, interrupt_type, result_manifest_ref, error_code,
                    metrics_json, metadata_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["run_id"],
                    payload["session_id"],
                    payload["request_id"],
                    payload["thread_id"],
                    payload["tableau_username"],
                    payload["question"],
                    payload["datasource_luid"],
                    payload["datasource_name"],
                    payload["project_name"],
                    payload["status"],
                    payload["interrupt_id"],
                    payload["interrupt_type"],
                    payload["result_manifest_ref"],
                    payload["error_code"],
                    payload["metrics_json"],
                    payload["metadata_json"],
                    payload["created_at"],
                    payload["updated_at"],
                ),
            )
            conn.commit()
        return self.get_run(run_id) or payload

    def get_run(self, run_id: str) -> Optional[dict[str, Any]]:
        with self._database.connect() as conn:
            row = conn.execute(
                """
                SELECT run_id, session_id, request_id, thread_id, tableau_username,
                       question, datasource_luid, datasource_name, project_name, status,
                       interrupt_id, interrupt_type, result_manifest_ref, error_code,
                       metrics_json, metadata_json, created_at, updated_at
                FROM analysis_runs
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "run_id": str(row["run_id"]),
            "session_id": str(row["session_id"]),
            "request_id": str(row["request_id"]),
            "thread_id": str(row["thread_id"]),
            "tableau_username": str(row["tableau_username"]),
            "question": str(row["question"]),
            "datasource_luid": row["datasource_luid"],
            "datasource_name": row["datasource_name"],
            "project_name": row["project_name"],
            "status": str(row["status"]),
            "interrupt_id": row["interrupt_id"],
            "interrupt_type": row["interrupt_type"],
            "result_manifest_ref": row["result_manifest_ref"],
            "error_code": row["error_code"],
            "metrics": _loads_json(row["metrics_json"], default={}),
            "metadata": _loads_json(row["metadata_json"], default={}),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
        }

    def update_run(
        self,
        run_id: str,
        *,
        status: Optional[str] = None,
        interrupt_id: Optional[str] = None,
        interrupt_type: Optional[str] = None,
        result_manifest_ref: Optional[str] = None,
        error_code: Optional[str] = None,
        metrics: Optional[dict[str, Any]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        existing = self.get_run(run_id)
        if existing is None:
            return None

        next_metrics = dict(existing.get("metrics") or {})
        if metrics:
            next_metrics.update(metrics)

        next_metadata = dict(existing.get("metadata") or {})
        if metadata:
            next_metadata.update(metadata)

        now = _utc_now_iso()
        with self._database.connect() as conn:
            conn.execute(
                """
                UPDATE analysis_runs
                SET status = ?,
                    interrupt_id = ?,
                    interrupt_type = ?,
                    result_manifest_ref = ?,
                    error_code = ?,
                    metrics_json = ?,
                    metadata_json = ?,
                    updated_at = ?
                WHERE run_id = ?
                """,
                (
                    status or existing["status"],
                    interrupt_id if interrupt_id is not None else existing.get("interrupt_id"),
                    interrupt_type if interrupt_type is not None else existing.get("interrupt_type"),
                    result_manifest_ref if result_manifest_ref is not None else existing.get("result_manifest_ref"),
                    error_code if error_code is not None else existing.get("error_code"),
                    _dumps_json(next_metrics),
                    _dumps_json(next_metadata),
                    now,
                    run_id,
                ),
            )
            conn.commit()
        return self.get_run(run_id)


class InterruptRepository(_RepositoryBase):
    """中断仓库。"""

    namespace = "analysis_interrupts"

    def get_interrupt(
        self,
        *,
        session_id: str,
        interrupt_id: str,
    ) -> Optional[dict[str, Any]]:
        with self._database.connect() as conn:
            row = conn.execute(
                """
                SELECT interrupt_id, session_id, tableau_username, thread_id, run_id,
                       request_id, interrupt_type, status, payload_json,
                       workflow_context_json, resolved_payload_json,
                       created_at, updated_at, resolved_at,
                       resolved_request_id, resolved_run_id
                FROM analysis_interrupts
                WHERE session_id = ? AND interrupt_id = ?
                """,
                (session_id, interrupt_id),
            ).fetchone()
        if row is None:
            return None
        return {
            "interrupt_id": str(row["interrupt_id"]),
            "session_id": str(row["session_id"]),
            "tableau_username": str(row["tableau_username"]),
            "thread_id": str(row["thread_id"]),
            "run_id": str(row["run_id"]),
            "request_id": str(row["request_id"]),
            "interrupt_type": str(row["interrupt_type"]),
            "status": str(row["status"]),
            "payload": _loads_json(row["payload_json"], default={}),
            "workflow_context": _loads_json(row["workflow_context_json"], default={}),
            "resolved_payload": _loads_json(row["resolved_payload_json"], default=None),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
            "resolved_at": row["resolved_at"],
            "resolved_request_id": row["resolved_request_id"],
            "resolved_run_id": row["resolved_run_id"],
        }

    def save_pending_interrupt(
        self,
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
        existing = self.get_interrupt(session_id=session_id, interrupt_id=interrupt_id)
        now = _utc_now_iso()
        created_at = (existing or {}).get("created_at", now)
        resolved_payload = (existing or {}).get("resolved_payload")

        with self._database.connect() as conn:
            conn.execute(
                """
                INSERT INTO analysis_interrupts (
                    interrupt_id, session_id, tableau_username, thread_id, run_id,
                    request_id, interrupt_type, status, payload_json,
                    workflow_context_json, resolved_payload_json,
                    created_at, updated_at, resolved_at,
                    resolved_request_id, resolved_run_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(interrupt_id) DO UPDATE SET
                    session_id = excluded.session_id,
                    tableau_username = excluded.tableau_username,
                    thread_id = excluded.thread_id,
                    run_id = excluded.run_id,
                    request_id = excluded.request_id,
                    interrupt_type = excluded.interrupt_type,
                    status = excluded.status,
                    payload_json = excluded.payload_json,
                    workflow_context_json = excluded.workflow_context_json,
                    updated_at = excluded.updated_at
                """,
                (
                    interrupt_id,
                    session_id,
                    tableau_username,
                    thread_id,
                    run_id,
                    request_id,
                    interrupt_type,
                    "pending",
                    _dumps_json(payload),
                    _dumps_json(workflow_context),
                    _dumps_json(resolved_payload),
                    created_at,
                    now,
                    (existing or {}).get("resolved_at"),
                    (existing or {}).get("resolved_request_id"),
                    (existing or {}).get("resolved_run_id"),
                ),
            )
            conn.commit()
        return self.get_interrupt(session_id=session_id, interrupt_id=interrupt_id) or {}

    def mark_resolved(
        self,
        *,
        session_id: str,
        interrupt_id: str,
        resume_payload: dict[str, Any],
        request_id: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        existing = self.get_interrupt(session_id=session_id, interrupt_id=interrupt_id)
        if existing is None:
            return None

        now = _utc_now_iso()
        with self._database.connect() as conn:
            conn.execute(
                """
                UPDATE analysis_interrupts
                SET status = 'resolved',
                    resolved_payload_json = ?,
                    resolved_at = ?,
                    resolved_request_id = ?,
                    resolved_run_id = ?,
                    updated_at = ?
                WHERE session_id = ? AND interrupt_id = ?
                """,
                (
                    _dumps_json(resume_payload),
                    now,
                    request_id,
                    run_id,
                    now,
                    session_id,
                    interrupt_id,
                ),
            )
            conn.commit()
        return self.get_interrupt(session_id=session_id, interrupt_id=interrupt_id)


class QueryAuditRepository(_RepositoryBase):
    """查询审计日志仓库。"""

    namespace = "query_audit_logs"

    def create_log(
        self,
        *,
        audit_id: str,
        run_id: str,
        tableau_username: str,
        datasource_luid: Optional[str],
        query_text: Optional[str],
        status: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        now = _utc_now_iso()
        payload = {
            "audit_id": audit_id,
            "run_id": run_id,
            "tableau_username": tableau_username,
            "datasource_luid": datasource_luid,
            "query_text": query_text,
            "status": status,
            "metadata": metadata or {},
            "created_at": now,
        }
        with self._database.connect() as conn:
            conn.execute(
                """
                INSERT INTO query_audit_logs (
                    audit_id, run_id, tableau_username, datasource_luid,
                    query_text, status, metadata_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["audit_id"],
                    payload["run_id"],
                    payload["tableau_username"],
                    payload["datasource_luid"],
                    payload["query_text"],
                    payload["status"],
                    _dumps_json(payload["metadata"]),
                    payload["created_at"],
                ),
            )
            conn.commit()
        return payload
