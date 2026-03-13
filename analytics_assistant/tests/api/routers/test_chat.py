# -*- coding: utf-8 -*-
"""
Router tests for the chat streaming API.

These tests cover request validation and SSE event mapping for
`POST /api/chat/stream`, while mocking the workflow executor and
history manager to avoid real LLM calls.
"""

import json
from typing import AsyncIterator, Dict, Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from analytics_assistant.src.api.dependencies import get_settings_repository
from analytics_assistant.src.api.main import app
from analytics_assistant.src.infra.storage import StoreFactory
from analytics_assistant.src.orchestration.workflow.runtime import (
    get_interrupt_record,
    save_pending_interrupt,
)


@pytest.fixture(autouse=True)
def reset_storage():
    """Reset the in-memory store before and after each test."""
    StoreFactory.reset()
    yield
    StoreFactory.reset()


def _make_chat_body(
    messages=None,
    datasource_name="测试数据源",
    language="zh",
    thinking_mode=None,
    feature_flags=None,
):
    """Build a chat request body."""
    if messages is None:
        messages = [{"role": "user", "content": "各区域销售额"}]
    body = {
        "messages": messages,
        "datasource_name": datasource_name,
        "language": language,
    }
    if thinking_mode is not None:
        body["thinking_mode"] = thinking_mode
    if feature_flags is not None:
        body["feature_flags"] = feature_flags
    return body


def _parse_sse_events(response_text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    lines = response_text.strip().split("\n\n")
    for line in lines:
        if line.startswith("data: "):
            events.append(json.loads(line[len("data: "):]))
    return events


def _seed_interrupt(
    *,
    session_id: str,
    interrupt_id: str,
    interrupt_type: str,
    payload: dict[str, Any],
    workflow_context: dict[str, Any] | None = None,
    tableau_username: str = "admin",
) -> dict[str, Any]:
    base_context = {
        "question": "各区域销售额",
        "history": [{"role": "user", "content": "各区域销售额"}],
        "datasource_name": "测试数据源",
        "datasource_luid": "ds_base",
        "project_name": "Default",
        "language": "zh",
        "analysis_depth": "detailed",
        "replan_mode": "user_select",
    }
    if workflow_context:
        base_context.update(workflow_context)
    return save_pending_interrupt(
        session_id=session_id,
        interrupt_id=interrupt_id,
        tableau_username=tableau_username,
        thread_id=session_id,
        run_id="run_seed_001",
        request_id="req_seed_001",
        interrupt_type=interrupt_type,
        payload=payload,
        workflow_context=base_context,
    )


class TestChatStreamValidation:
    """Validation tests for the chat stream endpoint."""

    def test_missing_username_returns_401(self):
        """Missing `X-Tableau-Username` should return 401."""
        client = TestClient(app)
        response = client.post(
            "/api/chat/stream",
            json=_make_chat_body(),
        )
        assert response.status_code == 401

    def test_missing_messages_returns_422(self):
        """Missing `messages` should return 422."""
        client = TestClient(app)
        response = client.post(
            "/api/chat/stream",
            json={"datasource_name": "test"},
            headers={"X-Tableau-Username": "admin"},
        )
        assert response.status_code == 422

    def test_missing_datasource_name_returns_422(self):
        """Missing `datasource_name` should return 422."""
        client = TestClient(app)
        response = client.post(
            "/api/chat/stream",
            json={"messages": [{"role": "user", "content": "hello"}]},
            headers={"X-Tableau-Username": "admin"},
        )
        assert response.status_code == 422

    def test_invalid_role_returns_422(self):
        """Invalid message role should return 422."""
        client = TestClient(app)
        response = client.post(
            "/api/chat/stream",
            json=_make_chat_body(
                messages=[{"role": "invalid", "content": "hello"}],
            ),
            headers={"X-Tableau-Username": "admin"},
        )
        assert response.status_code == 422


class TestChatStreamSSE:
    """SSE mapping tests for the chat stream endpoint."""

    @patch(
        "analytics_assistant.src.api.routers.chat.RootGraphRunner",
    )
    @patch(
        "analytics_assistant.src.api.routers.chat.get_history_manager",
    )
    def test_returns_sse_content_type(self, mock_get_hm, mock_executor_cls):
        """The response content type should be `text/event-stream`."""
        # Mock HistoryManager
        mock_hm = MagicMock()
        mock_hm.truncate_history.return_value = [
            {"role": "user", "content": "hello"},
        ]
        mock_hm.estimate_history_tokens.return_value = 10
        mock_get_hm.return_value = mock_hm

        # Mock RootGraphRunner
        async def mock_stream(*args, **kwargs) -> AsyncIterator[Dict[str, Any]]:
            yield {"type": "complete"}

        mock_executor = MagicMock()
        mock_executor.execute_stream = mock_stream
        mock_executor_cls.return_value = mock_executor

        client = TestClient(app)
        response = client.post(
            "/api/chat/stream",
            json=_make_chat_body(),
            headers={"X-Tableau-Username": "admin"},
        )

        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")

    @patch(
        "analytics_assistant.src.api.routers.chat.RootGraphRunner",
    )
    @patch(
        "analytics_assistant.src.api.routers.chat.get_history_manager",
    )
    def test_streams_token_events(self, mock_get_hm, mock_executor_cls):
        """Token events should be mapped to SSE v2 `answer_delta` events."""
        mock_hm = MagicMock()
        mock_hm.truncate_history.return_value = [
            {"role": "user", "content": "hello"},
        ]
        mock_hm.estimate_history_tokens.return_value = 10
        mock_get_hm.return_value = mock_hm

        async def mock_stream(*args, **kwargs) -> AsyncIterator[Dict[str, Any]]:
            yield {"type": "token", "content": "你好"}
            yield {"type": "token", "content": "世界"}
            yield {"type": "complete"}

        mock_executor = MagicMock()
        mock_executor.execute_stream = mock_stream
        mock_executor_cls.return_value = mock_executor

        client = TestClient(app)
        response = client.post(
            "/api/chat/stream",
            json=_make_chat_body(),
            headers={"X-Tableau-Username": "admin"},
        )

        assert response.status_code == 200
        events = _parse_sse_events(response.text)
        types = [e["type"] for e in events]
        assert "answer_delta" in types
        assert "complete" in types
        answer_events = [e for e in events if e["type"] == "answer_delta"]
        assert len(answer_events) == 2
        assert answer_events[0]["data"]["delta"] == "你好"
        assert answer_events[0]["data"]["display"]["channel"] == "main_answer"
        assert answer_events[0]["data"]["display"]["mode"] == "answer"

    @patch(
        "analytics_assistant.src.api.routers.chat.RootGraphRunner",
    )
    @patch(
        "analytics_assistant.src.api.routers.chat.get_history_manager",
    )
    def test_streams_thinking_events(self, mock_get_hm, mock_executor_cls):
        """Thinking events should be mapped to SSE v2 `status` events."""
        mock_hm = MagicMock()
        mock_hm.truncate_history.return_value = [
            {"role": "user", "content": "hello"},
        ]
        mock_hm.estimate_history_tokens.return_value = 10
        mock_get_hm.return_value = mock_hm

        async def mock_stream(*args, **kwargs) -> AsyncIterator[Dict[str, Any]]:
            yield {
                "type": "thinking",
                "stage": "understanding",
                "name": "理解问题",
                "status": "running",
            }
            yield {
                "type": "thinking",
                "stage": "understanding",
                "name": "理解问题",
                "status": "completed",
            }
            yield {"type": "complete"}

        mock_executor = MagicMock()
        mock_executor.execute_stream = mock_stream
        mock_executor_cls.return_value = mock_executor

        client = TestClient(app)
        response = client.post(
            "/api/chat/stream",
            json=_make_chat_body(),
            headers={"X-Tableau-Username": "admin"},
        )

        assert response.status_code == 200
        events = _parse_sse_events(response.text)
        status_events = [e for e in events if e["type"] == "status"]
        assert len(status_events) == 2
        assert status_events[0]["data"]["stage"] == "understanding"
        assert status_events[0]["data"]["status"] == "running"
        assert status_events[0]["data"]["reasoning_summary"] == "正在理解问题"
        assert status_events[0]["data"]["display"]["channel"] == "activity_timeline"
        assert status_events[0]["data"]["display"]["mode"] == "thinking_summary"
        assert status_events[1]["data"]["status"] == "completed"
        assert status_events[1]["data"]["reasoning_summary"] == "已完成理解问题"

    @patch(
        "analytics_assistant.src.api.routers.chat.RootGraphRunner",
    )
    @patch(
        "analytics_assistant.src.api.routers.chat.get_history_manager",
    )
    def test_summary_mode_hides_raw_thinking_tokens(self, mock_get_hm, mock_executor_cls):
        """Summary mode should hide raw thinking tokens."""
        mock_hm = MagicMock()
        mock_hm.truncate_history.return_value = [
            {"role": "user", "content": "hello"},
        ]
        mock_hm.estimate_history_tokens.return_value = 10
        mock_get_hm.return_value = mock_hm

        async def mock_stream(*args, **kwargs) -> AsyncIterator[Dict[str, Any]]:
            yield {"type": "thinking_token", "content": "internal reasoning"}
            yield {"type": "complete"}

        mock_executor = MagicMock()
        mock_executor.execute_stream = mock_stream
        mock_executor_cls.return_value = mock_executor

        client = TestClient(app)
        response = client.post(
            "/api/chat/stream",
            json=_make_chat_body(thinking_mode="summary"),
            headers={"X-Tableau-Username": "admin"},
        )

        assert response.status_code == 200
        events = _parse_sse_events(response.text)
        assert [event["type"] for event in events] == ["complete"]

    @patch(
        "analytics_assistant.src.api.routers.chat.RootGraphRunner",
    )
    @patch(
        "analytics_assistant.src.api.routers.chat.get_history_manager",
    )
    def test_debug_mode_streams_reasoning_delta(self, mock_get_hm, mock_executor_cls):
        """Debug mode should keep the raw thinking token stream."""
        mock_hm = MagicMock()
        mock_hm.truncate_history.return_value = [
            {"role": "user", "content": "hello"},
        ]
        mock_hm.estimate_history_tokens.return_value = 10
        mock_get_hm.return_value = mock_hm

        async def mock_stream(*args, **kwargs) -> AsyncIterator[Dict[str, Any]]:
            yield {"type": "thinking_token", "content": "internal reasoning"}
            yield {"type": "complete"}

        mock_executor = MagicMock()
        mock_executor.execute_stream = mock_stream
        mock_executor_cls.return_value = mock_executor

        client = TestClient(app)
        response = client.post(
            "/api/chat/stream",
            json=_make_chat_body(thinking_mode="debug"),
            headers={"X-Tableau-Username": "admin"},
        )

        assert response.status_code == 200
        events = _parse_sse_events(response.text)
        reasoning_event = next(e for e in events if e["type"] == "reasoning_delta")
        assert reasoning_event["data"]["delta"] == "internal reasoning"
        assert reasoning_event["data"]["display"]["channel"] == "activity_timeline"
        assert reasoning_event["data"]["display"]["mode"] == "debug"

    @patch(
        "analytics_assistant.src.api.routers.chat.RootGraphRunner",
    )
    @patch(
        "analytics_assistant.src.api.routers.chat.get_history_manager",
    )
    def test_settings_can_disable_thinking_summary(self, mock_get_hm, mock_executor_cls):
        """用户设置关闭思考过程时，只保留进度，不返回 reasoning_summary。"""
        mock_hm = MagicMock()
        mock_hm.truncate_history.return_value = [
            {"role": "user", "content": "hello"},
        ]
        mock_hm.estimate_history_tokens.return_value = 10
        mock_get_hm.return_value = mock_hm

        async def mock_stream(*args, **kwargs) -> AsyncIterator[Dict[str, Any]]:
            yield {
                "type": "thinking",
                "stage": "understanding",
                "name": "理解问题",
                "status": "running",
            }
            yield {"type": "complete"}

        mock_executor = MagicMock()
        mock_executor.execute_stream = mock_stream
        mock_executor_cls.return_value = mock_executor

        mock_settings_repo = MagicMock()
        mock_settings_repo.find_by_id.return_value = {
            "show_thinking_process": False,
        }
        app.dependency_overrides[get_settings_repository] = lambda: mock_settings_repo

        try:
            client = TestClient(app)
            response = client.post(
                "/api/chat/stream",
                json=_make_chat_body(),
                headers={"X-Tableau-Username": "admin"},
            )
        finally:
            app.dependency_overrides.pop(get_settings_repository, None)

        assert response.status_code == 200
        events = _parse_sse_events(response.text)
        status_event = next(e for e in events if e["type"] == "status")
        assert status_event["data"]["reasoning_summary"] is None
        assert status_event["data"]["display"]["mode"] == "progress"

    @patch(
        "analytics_assistant.src.api.routers.chat.RootGraphRunner",
    )
    @patch(
        "analytics_assistant.src.api.routers.chat.get_history_manager",
    )
    def test_history_truncation_called(self, mock_get_hm, mock_executor_cls):
        """`HistoryManager.truncate_history` should be called."""
        mock_hm = MagicMock()
        mock_hm.truncate_history.return_value = [
            {"role": "user", "content": "latest"},
        ]
        mock_hm.estimate_history_tokens.return_value = 5
        mock_get_hm.return_value = mock_hm

        async def mock_stream(*args, **kwargs) -> AsyncIterator[Dict[str, Any]]:
            yield {"type": "complete"}

        mock_executor = MagicMock()
        mock_executor.execute_stream = mock_stream
        mock_executor_cls.return_value = mock_executor

        messages = [
            {"role": "user", "content": "msg1"},
            {"role": "assistant", "content": "reply1"},
            {"role": "user", "content": "latest"},
        ]

        client = TestClient(app)
        client.post(
            "/api/chat/stream",
            json=_make_chat_body(messages=messages),
            headers={"X-Tableau-Username": "admin"},
        )

        # `truncate_history` should be called exactly once.
        mock_hm.truncate_history.assert_called_once()
        call_args = mock_hm.truncate_history.call_args[0][0]
        assert len(call_args) == 3

    @patch(
        "analytics_assistant.src.api.routers.chat.RootGraphRunner",
    )
    @patch(
        "analytics_assistant.src.api.routers.chat.get_history_manager",
    )
    def test_no_cache_headers(self, mock_get_hm, mock_executor_cls):
        """SSE responses should include `no-cache` headers."""
        mock_hm = MagicMock()
        mock_hm.truncate_history.return_value = [
            {"role": "user", "content": "hello"},
        ]
        mock_hm.estimate_history_tokens.return_value = 10
        mock_get_hm.return_value = mock_hm

        async def mock_stream(*args, **kwargs) -> AsyncIterator[Dict[str, Any]]:
            yield {"type": "complete"}

        mock_executor = MagicMock()
        mock_executor.execute_stream = mock_stream
        mock_executor_cls.return_value = mock_executor

        client = TestClient(app)
        response = client.post(
            "/api/chat/stream",
            json=_make_chat_body(),
            headers={"X-Tableau-Username": "admin"},
        )

        assert response.headers.get("cache-control") == "no-cache"

    @patch(
        "analytics_assistant.src.api.routers.chat.RootGraphRunner",
    )
    @patch(
        "analytics_assistant.src.api.routers.chat.get_history_manager",
    )
    def test_request_id_propagated_to_response_and_events(
        self,
        mock_get_hm,
        mock_executor_cls,
    ):
        """An explicit request id should propagate to headers, SSE, and executor."""
        mock_hm = MagicMock()
        mock_hm.truncate_history.return_value = [
            {"role": "user", "content": "hello"},
        ]
        mock_hm.estimate_history_tokens.return_value = 10
        mock_get_hm.return_value = mock_hm

        async def mock_stream(*args, **kwargs) -> AsyncIterator[Dict[str, Any]]:
            yield {"type": "token", "content": "你好"}
            yield {"type": "complete"}

        mock_executor = MagicMock()
        mock_executor.execute_stream = mock_stream
        mock_executor_cls.return_value = mock_executor

        client = TestClient(app)
        request_id = "req-test-123"
        response = client.post(
            "/api/chat/stream",
            json=_make_chat_body(),
            headers={
                "X-Tableau-Username": "admin",
                "X-Request-ID": request_id,
            },
        )

        assert response.status_code == 200
        assert response.headers.get("x-request-id") == request_id
        mock_executor_cls.assert_called_once_with("admin", request_id=request_id)

        events = _parse_sse_events(response.text)
        assert events
        assert all(event.get("request_id") == request_id for event in events)

    @patch(
        "analytics_assistant.src.api.routers.chat.RootGraphRunner",
    )
    @patch(
        "analytics_assistant.src.api.routers.chat.get_history_manager",
    )
    def test_stream_passes_feature_flags_to_root_graph_runner(
        self,
        mock_get_hm,
        mock_executor_cls,
    ):
        mock_hm = MagicMock()
        mock_hm.truncate_history.return_value = [
            {"role": "user", "content": "hello"},
        ]
        mock_hm.estimate_history_tokens.return_value = 10
        mock_get_hm.return_value = mock_hm

        captured: dict[str, Any] = {}

        async def mock_stream(*args, **kwargs) -> AsyncIterator[Dict[str, Any]]:
            del args
            captured.update(kwargs)
            yield {"type": "complete"}

        mock_executor = MagicMock()
        mock_executor.execute_stream = mock_stream
        mock_executor_cls.return_value = mock_executor

        client = TestClient(app)
        response = client.post(
            "/api/chat/stream",
            json=_make_chat_body(feature_flags={"why_screening_wave": False}),
            headers={"X-Tableau-Username": "admin"},
        )

        assert response.status_code == 200
        assert captured["feature_flags"] == {"why_screening_wave": False}

    @patch(
        "analytics_assistant.src.api.routers.chat.RootGraphRunner",
    )
    @patch(
        "analytics_assistant.src.api.routers.chat.get_history_manager",
    )
    def test_generated_session_id_matches_thread_id(
        self,
        mock_get_hm,
        mock_executor_cls,
    ):
        """When `session_id` is omitted, the router should reuse the generated id as `thread_id`."""
        mock_hm = MagicMock()
        mock_hm.truncate_history.return_value = [
            {"role": "user", "content": "hello"},
        ]
        mock_hm.estimate_history_tokens.return_value = 10
        mock_get_hm.return_value = mock_hm

        async def mock_stream(*args, **kwargs) -> AsyncIterator[Dict[str, Any]]:
            yield {"type": "complete"}

        mock_executor = MagicMock()
        mock_executor.execute_stream = mock_stream
        mock_executor_cls.return_value = mock_executor

        client = TestClient(app)
        response = client.post(
            "/api/chat/stream",
            json=_make_chat_body(),
            headers={"X-Tableau-Username": "admin"},
        )

        assert response.status_code == 200
        events = _parse_sse_events(response.text)
        assert events
        assert events[0]["session_id"]
        assert events[0]["thread_id"] == events[0]["session_id"]

    @patch(
        "analytics_assistant.src.api.routers.chat.RootGraphRunner",
    )
    @patch(
        "analytics_assistant.src.api.routers.chat.get_history_manager",
    )
    def test_project_name_forwarded_to_root_graph_runner(
        self,
        mock_get_hm,
        mock_executor_cls,
    ):
        """`project_name` should be forwarded from the API request to the root graph entry."""
        mock_hm = MagicMock()
        mock_hm.truncate_history.return_value = [
            {"role": "user", "content": "hello"},
        ]
        mock_hm.estimate_history_tokens.return_value = 10
        mock_get_hm.return_value = mock_hm

        captured: dict[str, Any] = {}

        async def mock_stream(*args, **kwargs) -> AsyncIterator[Dict[str, Any]]:
            captured.update(kwargs)
            yield {"type": "complete"}

        mock_executor = MagicMock()
        mock_executor.execute_stream = mock_stream
        mock_executor_cls.return_value = mock_executor

        client = TestClient(app)
        response = client.post(
            "/api/chat/stream",
            json={
                **_make_chat_body(),
                "project_name": "Sales",
                "session_id": "sess_project_001",
            },
            headers={"X-Tableau-Username": "admin"},
        )

        assert response.status_code == 200
        assert captured["project_name"] == "Sales"
        assert captured["session_id"] == "sess_project_001"

    @patch(
        "analytics_assistant.src.api.routers.chat.RootGraphRunner",
    )
    @patch(
        "analytics_assistant.src.api.routers.chat.get_history_manager",
    )
    def test_optimization_metrics_preserved_in_sse_events(
        self,
        mock_get_hm,
        mock_executor_cls,
    ):
        """Optimization metrics from executor events should survive SSE mapping."""
        mock_hm = MagicMock()
        mock_hm.truncate_history.return_value = [
            {"role": "user", "content": "hello"},
        ]
        mock_hm.estimate_history_tokens.return_value = 10
        mock_get_hm.return_value = mock_hm

        async def mock_stream(*args, **kwargs) -> AsyncIterator[Dict[str, Any]]:
            yield {
                "type": "interrupt",
                "interrupt_type": "missing_slot",
                "payload": {
                    "message": "请选择字段",
                    "slot_name": "dimension",
                    "options": ["销售方 (Sold Nm)"],
                    "optimization_metrics": {
                        "auth_ms": 12.3,
                        "semantic_understanding_ms": 45.6,
                    },
                },
            }
            yield {
                "type": "complete",
                "optimization_metrics": {
                    "workflow_executor_ms": 78.9,
                },
            }

        mock_executor = MagicMock()
        mock_executor.execute_stream = mock_stream
        mock_executor_cls.return_value = mock_executor

        client = TestClient(app)
        response = client.post(
            "/api/chat/stream",
            json=_make_chat_body(),
            headers={"X-Tableau-Username": "admin"},
        )

        assert response.status_code == 200
        events = _parse_sse_events(response.text)
        clarification_event = next(e for e in events if e["type"] == "interrupt")
        complete_event = next(e for e in events if e["type"] == "complete")

        assert clarification_event["data"]["payload"]["optimization_metrics"] == {
            "auth_ms": 12.3,
            "semantic_understanding_ms": 45.6,
        }
        assert complete_event["data"]["optimization_metrics"] == {
            "workflow_executor_ms": 78.9,
        }

    @patch(
        "analytics_assistant.src.api.routers.chat.RootGraphRunner",
    )
    @patch(
        "analytics_assistant.src.api.routers.chat.get_history_manager",
    )
    def test_complete_event_preserves_context_observability_fields(
        self,
        mock_get_hm,
        mock_executor_cls,
    ):
        """Complete 事件里的上下文可观测字段必须原样保留到 SSE。"""
        mock_hm = MagicMock()
        mock_hm.truncate_history.return_value = [
            {"role": "user", "content": "hello"},
        ]
        mock_hm.estimate_history_tokens.return_value = 10
        mock_get_hm.return_value = mock_hm

        async def mock_stream(*args, **kwargs) -> AsyncIterator[Dict[str, Any]]:
            yield {
                "type": "complete",
                "status": "ok",
                "artifact_refresh_scheduled": True,
                "degrade_flags": [
                    "semantic_retrieval_degraded",
                ],
                "degrade_details": [
                    {
                        "artifact": "field_semantic_index",
                        "degrade_flag": "semantic_retrieval_degraded",
                        "status": "stale",
                        "reason": "schema_changed",
                        "degrade_mode": "read_stale",
                        "refresh_requested": True,
                        "refresh_scheduled": True,
                        "refresh_trigger": "schema_change",
                        "alert_required": False,
                    }
                ],
                "context_metrics": {
                    "context_degraded": True,
                    "artifact_refresh_requested": True,
                    "artifact_refresh_scheduled": True,
                    "artifact_refresh_schedule_failed": False,
                    "refresh_trigger": "schema_change",
                    "refresh_requested_artifacts": ["field_semantic_index"],
                    "schema_change_invalidated": True,
                    "has_stale_artifacts": True,
                    "has_missing_artifacts": False,
                    "degraded_artifacts": ["field_semantic_index"],
                    "degrade_reason_codes": ["schema_changed"],
                    "requires_attention": False,
                    "invalidation_trigger": "schema_change",
                    "invalidation_total_deleted": 4,
                    "artifact_statuses": {
                        "metadata_snapshot": "ready",
                        "field_semantic_index": "stale",
                    },
                },
            }

        mock_executor = MagicMock()
        mock_executor.execute_stream = mock_stream
        mock_executor_cls.return_value = mock_executor

        client = TestClient(app)
        response = client.post(
            "/api/chat/stream",
            json=_make_chat_body(),
            headers={"X-Tableau-Username": "admin"},
        )

        assert response.status_code == 200
        events = _parse_sse_events(response.text)
        complete_event = next(e for e in events if e["type"] == "complete")

        assert complete_event["data"]["artifact_refresh_scheduled"] is True
        assert complete_event["data"]["degrade_flags"] == [
            "semantic_retrieval_degraded",
        ]
        assert complete_event["data"]["degrade_details"][0]["reason"] == "schema_changed"
        assert complete_event["data"]["context_metrics"]["refresh_trigger"] == "schema_change"
        assert complete_event["data"]["context_metrics"]["artifact_refresh_scheduled"] is True
        assert complete_event["data"]["context_metrics"]["artifact_statuses"] == {
            "metadata_snapshot": "ready",
            "field_semantic_index": "stale",
        }

    @patch(
        "analytics_assistant.src.api.routers.chat.RootGraphRunner",
    )
    @patch(
        "analytics_assistant.src.api.routers.chat.get_history_manager",
    )
    def test_streams_parse_result_with_display_projection(
        self,
        mock_get_hm,
        mock_executor_cls,
    ):
        mock_hm = MagicMock()
        mock_hm.truncate_history.return_value = [
            {"role": "user", "content": "hello"},
        ]
        mock_hm.estimate_history_tokens.return_value = 10
        mock_get_hm.return_value = mock_hm

        async def mock_stream(*args, **kwargs) -> AsyncIterator[Dict[str, Any]]:
            yield {
                "type": "parse_result",
                "summary": {
                    "measures": ["销售额"],
                    "dimensions": ["地区"],
                    "filters": ["最近30天"],
                },
                "confidence": 0.92,
                "semantic_guard": {
                    "verified": True,
                    "validation_mode": "deterministic",
                    "corrected": False,
                    "compiler_ready": True,
                    "allowed_to_execute": True,
                    "query_contract_mode": "compiler_input",
                    "query_contract_source": "semantic_output",
                    "error_count": 0,
                    "filter_confirmation_count": 0,
                    "needs_clarification": False,
                    "needs_value_confirmation": False,
                    "has_unresolvable_filters": False,
                    "errors": [],
                },
            }
            yield {"type": "complete"}

        mock_executor = MagicMock()
        mock_executor.execute_stream = mock_stream
        mock_executor_cls.return_value = mock_executor

        client = TestClient(app)
        response = client.post(
            "/api/chat/stream",
            json=_make_chat_body(),
            headers={"X-Tableau-Username": "admin"},
        )

        assert response.status_code == 200
        events = _parse_sse_events(response.text)
        parse_event = next(e for e in events if e["type"] == "parse_result")
        assert parse_event["data"]["confidence"] == 0.92
        assert parse_event["data"]["semantic_guard"] == {
            "verified": True,
            "validation_mode": "deterministic",
            "corrected": False,
            "compiler_ready": True,
            "allowed_to_execute": True,
            "query_contract_mode": "compiler_input",
            "query_contract_source": "semantic_output",
            "error_count": 0,
            "filter_confirmation_count": 0,
            "needs_clarification": False,
            "needs_value_confirmation": False,
            "has_unresolvable_filters": False,
            "errors": [],
        }
        assert parse_event["data"]["reasoning_summary"] == "指标: 销售额；维度: 地区；筛选: 最近30天"
        assert parse_event["data"]["display"] == {
            "channel": "activity_timeline",
            "tone": "info",
            "title": "解析完成",
            "message": "已完成语义解析",
            "summary": "指标: 销售额；维度: 地区；筛选: 最近30天",
            "mode": "thinking_summary",
        }

    @patch(
        "analytics_assistant.src.api.routers.chat.RootGraphRunner",
    )
    @patch(
        "analytics_assistant.src.api.routers.chat.get_history_manager",
    )
    def test_streams_interrupt_with_display_projection(
        self,
        mock_get_hm,
        mock_executor_cls,
    ):
        mock_hm = MagicMock()
        mock_hm.truncate_history.return_value = [
            {"role": "user", "content": "hello"},
        ]
        mock_hm.estimate_history_tokens.return_value = 10
        mock_get_hm.return_value = mock_hm

        async def mock_stream(*args, **kwargs) -> AsyncIterator[Dict[str, Any]]:
            yield {
                "type": "interrupt",
                "interrupt_type": "high_risk_query_confirm",
                "interrupt_id": "int_risk_stream_001",
                "payload": {
                    "message": "本次查询范围较大，请确认是否继续",
                    "summary": "预计扫描 20 万行",
                    "risk_level": "high",
                    "resume_strategy": "root_graph_native",
                },
            }

        mock_executor = MagicMock()
        mock_executor.execute_stream = mock_stream
        mock_executor_cls.return_value = mock_executor

        client = TestClient(app)
        response = client.post(
            "/api/chat/stream",
            json={
                **_make_chat_body(),
                "session_id": "sess_interrupt_projection_001",
            },
            headers={"X-Tableau-Username": "admin"},
        )

        assert response.status_code == 200
        events = _parse_sse_events(response.text)
        interrupt_event = next(e for e in events if e["type"] == "interrupt")
        assert interrupt_event["data"]["interrupt_id"] == "int_risk_stream_001"
        assert interrupt_event["data"]["interrupt_type"] == "high_risk_query_confirm"
        assert interrupt_event["data"]["payload"]["resume_strategy"] == "root_graph_native"
        assert interrupt_event["data"]["display"] == {
            "channel": "decision_card",
            "tone": "warning",
            "title": "需要你确认",
            "message": "本次查询范围较大，请确认是否继续",
            "summary": "预计扫描 20 万行",
        }

    @patch(
        "analytics_assistant.src.api.routers.chat.RootGraphRunner",
    )
    @patch(
        "analytics_assistant.src.api.routers.chat.get_history_manager",
    )
    def test_streams_table_result_with_display_projection(
        self,
        mock_get_hm,
        mock_executor_cls,
    ):
        mock_hm = MagicMock()
        mock_hm.truncate_history.return_value = [
            {"role": "user", "content": "hello"},
        ]
        mock_hm.estimate_history_tokens.return_value = 10
        mock_get_hm.return_value = mock_hm

        async def mock_stream(*args, **kwargs) -> AsyncIterator[Dict[str, Any]]:
            yield {
                "type": "data",
                "tableData": {
                    "rowCount": 18240,
                    "columns": ["日期", "地区", "销售额"],
                    "rows": [["2026-03-01", "华东", 100]],
                },
                "truncated": True,
                "result_manifest_ref": "artifacts/runs/run_001/result/result_manifest.json",
            }
            yield {"type": "complete"}

        mock_executor = MagicMock()
        mock_executor.execute_stream = mock_stream
        mock_executor_cls.return_value = mock_executor

        client = TestClient(app)
        response = client.post(
            "/api/chat/stream",
            json=_make_chat_body(),
            headers={"X-Tableau-Username": "admin"},
        )

        assert response.status_code == 200
        events = _parse_sse_events(response.text)
        result_event = next(e for e in events if e["type"] == "table_result")
        assert result_event["data"]["row_count"] == 18240
        assert result_event["data"]["truncated"] is True
        assert result_event["data"]["result_manifest_ref"] == (
            "artifacts/runs/run_001/result/result_manifest.json"
        )
        assert result_event["data"]["display"] == {
            "channel": "result_card",
            "tone": "success",
            "title": "查询结果",
            "message": "已完成查询",
            "summary": "结果较大，当前展示的是预览和摘要",
        }

    @patch(
        "analytics_assistant.src.api.routers.chat.RootGraphRunner",
    )
    @patch(
        "analytics_assistant.src.api.routers.chat.get_history_manager",
    )
    def test_streams_insight_with_display_projection(
        self,
        mock_get_hm,
        mock_executor_cls,
    ):
        mock_hm = MagicMock()
        mock_hm.truncate_history.return_value = [
            {"role": "user", "content": "hello"},
        ]
        mock_hm.estimate_history_tokens.return_value = 10
        mock_get_hm.return_value = mock_hm

        async def mock_stream(*args, **kwargs) -> AsyncIterator[Dict[str, Any]]:
            yield {
                "type": "insight",
                "summary": "华东区下降主要集中在直营渠道",
                "findings": [
                    {"title": "直营渠道降幅最大", "detail": "直营环比下降 12%"},
                ],
            }
            yield {"type": "complete"}

        mock_executor = MagicMock()
        mock_executor.execute_stream = mock_stream
        mock_executor_cls.return_value = mock_executor

        client = TestClient(app)
        response = client.post(
            "/api/chat/stream",
            json=_make_chat_body(),
            headers={"X-Tableau-Username": "admin"},
        )

        assert response.status_code == 200
        events = _parse_sse_events(response.text)
        insight_event = next(e for e in events if e["type"] == "insight")
        assert insight_event["data"]["summary"] == "华东区下降主要集中在直营渠道"
        assert insight_event["data"]["display"] == {
            "channel": "result_card",
            "tone": "success",
            "title": "关键发现",
            "message": "已生成洞察结论",
            "summary": "华东区下降主要集中在直营渠道",
        }

    @patch(
        "analytics_assistant.src.api.routers.chat.RootGraphRunner",
    )
    @patch(
        "analytics_assistant.src.api.routers.chat.get_history_manager",
    )
    def test_streams_replan_with_display_projection(
        self,
        mock_get_hm,
        mock_executor_cls,
    ):
        mock_hm = MagicMock()
        mock_hm.truncate_history.return_value = [
            {"role": "user", "content": "hello"},
        ]
        mock_hm.estimate_history_tokens.return_value = 10
        mock_get_hm.return_value = mock_hm

        async def mock_stream(*args, **kwargs) -> AsyncIterator[Dict[str, Any]]:
            yield {
                "type": "replan",
                "reason": "已找到两个值得继续拆解的方向",
                "newQuestion": "按渠道继续比较华东区和华南区差异",
                "shouldReplan": True,
            }
            yield {"type": "complete"}

        mock_executor = MagicMock()
        mock_executor.execute_stream = mock_stream
        mock_executor_cls.return_value = mock_executor

        client = TestClient(app)
        response = client.post(
            "/api/chat/stream",
            json=_make_chat_body(),
            headers={"X-Tableau-Username": "admin"},
        )

        assert response.status_code == 200
        events = _parse_sse_events(response.text)
        replan_event = next(e for e in events if e["type"] == "replan")
        assert replan_event["data"]["source_type"] == "replan"
        assert replan_event["data"]["reasoning_summary"] == "已找到两个值得继续拆解的方向"
        assert replan_event["data"]["display"] == {
            "channel": "activity_timeline",
            "tone": "info",
            "title": "后续分析",
            "message": "已找到两个值得继续拆解的方向",
            "summary": "按渠道继续比较华东区和华南区差异",
            "mode": "thinking_summary",
        }

    @patch(
        "analytics_assistant.src.api.routers.chat.RootGraphRunner",
    )
    @patch(
        "analytics_assistant.src.api.routers.chat.get_history_manager",
    )
    def test_stream_maps_internal_node_error_code_to_public_error_code(
        self,
        mock_get_hm,
        mock_executor_cls,
    ):
        mock_hm = MagicMock()
        mock_hm.truncate_history.return_value = [
            {"role": "user", "content": "hello"},
        ]
        mock_hm.estimate_history_tokens.return_value = 10
        mock_get_hm.return_value = mock_hm

        async def mock_stream(*args, **kwargs) -> AsyncIterator[Dict[str, Any]]:
            yield {
                "type": "error",
                "error_code": "planner_step_limit_exceeded",
                "message": "planner exceeds max_total_steps",
                "retryable": False,
            }

        mock_executor = MagicMock()
        mock_executor.execute_stream = mock_stream
        mock_executor_cls.return_value = mock_executor

        client = TestClient(app)
        response = client.post(
            "/api/chat/stream",
            json=_make_chat_body(),
            headers={"X-Tableau-Username": "admin"},
        )

        assert response.status_code == 200
        events = _parse_sse_events(response.text)
        error_event = next(e for e in events if e["type"] == "error")
        assert error_event["data"]["error_code"] == "QUERY_PLAN_ERROR"
        assert error_event["data"]["node_error_code"] == "planner_step_limit_exceeded"

    @patch(
        "analytics_assistant.src.api.routers.chat.RootGraphRunner",
    )
    @patch(
        "analytics_assistant.src.api.routers.chat.get_history_manager",
    )
    def test_stream_rejects_interrupt_without_explicit_type(
        self,
        mock_get_hm,
        mock_executor_cls,
    ):
        mock_hm = MagicMock()
        mock_hm.truncate_history.return_value = [
            {"role": "user", "content": "hello"},
        ]
        mock_hm.estimate_history_tokens.return_value = 10
        mock_get_hm.return_value = mock_hm

        async def mock_stream(*args, **kwargs) -> AsyncIterator[Dict[str, Any]]:
            yield {
                "type": "interrupt",
                "payload": {
                    "message": "Choose dimension field",
                    "slot_name": "dimension",
                },
            }

        mock_executor = MagicMock()
        mock_executor.execute_stream = mock_stream
        mock_executor_cls.return_value = mock_executor

        client = TestClient(app)
        response = client.post(
            "/api/chat/stream",
            json=_make_chat_body(),
            headers={"X-Tableau-Username": "admin"},
        )

        assert response.status_code == 200
        events = _parse_sse_events(response.text)
        error_event = next(e for e in events if e["type"] == "error")

        assert error_event["data"]["error_code"] == "INTERNAL_ERROR"
        assert error_event["data"]["message"] == "workflow execution failed"

    @patch(
        "analytics_assistant.src.api.routers.chat.RootGraphRunner",
    )
    @patch(
        "analytics_assistant.src.api.routers.chat.get_history_manager",
    )
    def test_stream_rejects_legacy_candidate_questions_event(
        self,
        mock_get_hm,
        mock_executor_cls,
    ):
        mock_hm = MagicMock()
        mock_hm.truncate_history.return_value = [
            {"role": "user", "content": "hello"},
        ]
        mock_hm.estimate_history_tokens.return_value = 10
        mock_get_hm.return_value = mock_hm

        async def mock_stream(*args, **kwargs) -> AsyncIterator[Dict[str, Any]]:
            yield {
                "type": "candidate_questions",
                "questions": [{"id": "q1", "question": "按渠道继续分析"}],
            }

        mock_executor = MagicMock()
        mock_executor.execute_stream = mock_stream
        mock_executor_cls.return_value = mock_executor

        client = TestClient(app)
        response = client.post(
            "/api/chat/stream",
            json=_make_chat_body(),
            headers={"X-Tableau-Username": "admin"},
        )

        assert response.status_code == 200
        events = _parse_sse_events(response.text)
        error_event = next(e for e in events if e["type"] == "error")
        assert error_event["data"]["error_code"] == "INTERNAL_ERROR"
        assert error_event["data"]["message"] == "workflow execution failed"

    @patch(
        "analytics_assistant.src.api.routers.chat.RootGraphRunner",
    )
    @patch(
        "analytics_assistant.src.api.routers.chat.get_history_manager",
    )
    def test_stream_rejects_unknown_workflow_event_type(
        self,
        mock_get_hm,
        mock_executor_cls,
    ):
        mock_hm = MagicMock()
        mock_hm.truncate_history.return_value = [
            {"role": "user", "content": "hello"},
        ]
        mock_hm.estimate_history_tokens.return_value = 10
        mock_get_hm.return_value = mock_hm

        async def mock_stream(*args, **kwargs) -> AsyncIterator[Dict[str, Any]]:
            yield {
                "type": "legacy_custom_event",
                "message": "this should never be mapped silently",
            }

        mock_executor = MagicMock()
        mock_executor.execute_stream = mock_stream
        mock_executor_cls.return_value = mock_executor

        client = TestClient(app)
        response = client.post(
            "/api/chat/stream",
            json=_make_chat_body(),
            headers={"X-Tableau-Username": "admin"},
        )

        assert response.status_code == 200
        events = _parse_sse_events(response.text)
        error_event = next(e for e in events if e["type"] == "error")
        assert error_event["data"]["error_code"] == "INTERNAL_ERROR"
        assert error_event["data"]["message"] == "workflow execution failed"

    @patch(
        "analytics_assistant.src.api.routers.chat.RootGraphRunner",
    )
    @patch(
        "analytics_assistant.src.api.routers.chat.get_history_manager",
    )
    def test_stream_persists_datasource_disambiguation_interrupt(
        self,
        mock_get_hm,
        mock_executor_cls,
    ):
        mock_hm = MagicMock()
        mock_hm.truncate_history.return_value = [
            {"role": "user", "content": "hello"},
        ]
        mock_hm.estimate_history_tokens.return_value = 10
        mock_get_hm.return_value = mock_hm

        async def mock_stream(*args, **kwargs) -> AsyncIterator[Dict[str, Any]]:
            yield {
                "type": "interrupt",
                "interrupt_id": "int_ds_stream_001",
                "interrupt_type": "datasource_disambiguation",
                "payload": {
                    "message": "找到多个同名数据源，请选择",
                    "choices": [
                        {
                            "datasource_luid": "ds_sales",
                            "name": "Revenue",
                            "project": "Sales",
                        },
                        {
                            "datasource_luid": "ds_ops",
                            "name": "Revenue",
                            "project": "Ops",
                        },
                    ],
                },
            }

        mock_executor = MagicMock()
        mock_executor.execute_stream = mock_stream
        mock_executor_cls.return_value = mock_executor

        client = TestClient(app)
        response = client.post(
            "/api/chat/stream",
            json={
                **_make_chat_body(datasource_name="Revenue"),
                "session_id": "sess_stream_ds_001",
            },
            headers={"X-Tableau-Username": "admin"},
        )

        assert response.status_code == 200
        events = _parse_sse_events(response.text)
        interrupt_event = next(e for e in events if e["type"] == "interrupt")
        assert interrupt_event["data"]["interrupt_type"] == "datasource_disambiguation"
        record = get_interrupt_record("sess_stream_ds_001", "int_ds_stream_001")
        assert record is not None
        assert record["interrupt_type"] == "datasource_disambiguation"
        assert record["payload"]["choices"][0]["datasource_luid"] == "ds_sales"


class TestChatResumeSSE:
    """Contract tests for `/api/chat/resume`."""

    def test_resume_returns_sse_error_event(self):
        client = TestClient(app)
        response = client.post(
            "/api/chat/resume",
            json={
                "session_id": "sess_001",
                "interrupt_id": "int_001",
                "resume_payload": {"selection_type": "slot_fill", "value": "last_30_days"},
            },
            headers={"X-Tableau-Username": "admin"},
        )

        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")
        events = _parse_sse_events(response.text)
        assert events
        assert events[0]["type"] == "error"
        assert events[0]["data"]["error_code"] == "INTERRUPT_NOT_FOUND"

    @patch("analytics_assistant.src.api.routers.chat.RootGraphRunner")
    def test_resume_followup_select_uses_root_graph_native_resume(self, mock_executor_cls):
        _seed_interrupt(
            session_id="sess_followup_001",
            interrupt_id="int_followup_001",
            interrupt_type="followup_select",
            payload={
                "message": "请选择后续问题",
                "resume_strategy": "root_graph_native",
                "candidates": [
                    {"id": "q1", "question": "按产品线拆分趋势"},
                    {"id": "q2", "question": "按渠道拆分趋势"},
                ],
            },
        )

        captured: dict[str, Any] = {}

        async def mock_stream(*args, **kwargs) -> AsyncIterator[Dict[str, Any]]:
            captured.update(kwargs)
            yield {"type": "complete"}

        mock_executor = MagicMock()
        mock_executor.resume_stream = mock_stream
        mock_executor_cls.return_value = mock_executor

        client = TestClient(app)
        response = client.post(
            "/api/chat/resume",
            json={
                "session_id": "sess_followup_001",
                "interrupt_id": "int_followup_001",
                "resume_payload": {
                    "selection_type": "followup_question",
                    "selected_question_id": "q1",
                },
            },
            headers={"X-Tableau-Username": "admin"},
        )

        assert response.status_code == 200
        events = _parse_sse_events(response.text)
        assert any(event["type"] == "complete" for event in events)
        assert captured["resume_value"] == captured["question"]
        assert captured["resume_strategy"] == "root_graph_native"
        assert captured["question"]
        record = get_interrupt_record("sess_followup_001", "int_followup_001")
        assert record is not None
        assert record["status"] == "resolved"
        assert record["resolved_at"]

    @patch("analytics_assistant.src.api.routers.chat.RootGraphRunner")
    def test_resume_datasource_disambiguation_uses_selected_datasource(
        self,
        mock_executor_cls,
    ):
        _seed_interrupt(
            session_id="sess_ds_001",
            interrupt_id="int_ds_001",
            interrupt_type="datasource_disambiguation",
            payload={
                "message": "找到多个同名数据源，请选择",
                "resume_strategy": "root_graph_native",
                "choices": [
                    {
                        "datasource_luid": "ds_sales",
                        "project": "Sales",
                        "name": "Revenue",
                    },
                    {
                        "datasource_luid": "ds_ops",
                        "project": "Ops",
                        "name": "Revenue",
                    },
                ],
            },
            workflow_context={
                "question": "各区域销售额",
                "history": [{"role": "user", "content": "各区域销售额"}],
                "datasource_name": "Revenue",
                "datasource_luid": None,
                "project_name": None,
            },
        )

        captured: dict[str, Any] = {}

        async def mock_stream(*args, **kwargs) -> AsyncIterator[Dict[str, Any]]:
            captured.update(kwargs)
            yield {"type": "complete"}

        mock_executor = MagicMock()
        mock_executor.resume_stream = mock_stream
        mock_executor_cls.return_value = mock_executor

        client = TestClient(app)
        response = client.post(
            "/api/chat/resume",
            json={
                "session_id": "sess_ds_001",
                "interrupt_id": "int_ds_001",
                "resume_payload": {
                    "selection_type": "datasource",
                    "datasource_luid": "ds_sales",
                },
            },
            headers={"X-Tableau-Username": "admin"},
        )

        assert response.status_code == 200
        events = _parse_sse_events(response.text)
        assert any(event["type"] == "complete" for event in events)
        assert captured["resume_strategy"] == "root_graph_native"
        assert captured["resume_value"] == {
            "datasource_luid": "ds_sales",
            "datasource_name": "Revenue",
            "project_name": "Sales",
        }
        assert captured["datasource_luid"] == "ds_sales"
        assert captured["datasource_name"] == "Revenue"
        assert captured["project_name"] == "Sales"

    @patch("analytics_assistant.src.api.routers.chat.RootGraphRunner")
    def test_resume_missing_slot_without_root_native_strategy_returns_validation_error(
        self,
        mock_executor_cls,
    ):
        _seed_interrupt(
            session_id="sess_slot_001",
            interrupt_id="int_slot_001",
            interrupt_type="missing_slot",
            payload={
                "message": "缺少时间范围，请选择",
                "slot_name": "timeframe",
                "options": ["last_7_days", "last_30_days"],
                "resume_strategy": "langgraph_native",
            },
        )

        client = TestClient(app)
        response = client.post(
            "/api/chat/resume",
            json={
                "session_id": "sess_slot_001",
                "interrupt_id": "int_slot_001",
                "resume_payload": {
                    "selection_type": "slot_fill",
                    "slot_name": "timeframe",
                    "value": "last_30_days",
                },
            },
            headers={"X-Tableau-Username": "admin"},
        )

        assert response.status_code == 200
        events = _parse_sse_events(response.text)
        assert events[0]["type"] == "error"
        assert events[0]["data"]["error_code"] == "RESUME_VALIDATION_ERROR"
        assert events[0]["data"]["message"] == "missing_slot must use root_graph_native resume"
        mock_executor_cls.assert_not_called()

    @patch("analytics_assistant.src.api.routers.chat.RootGraphRunner")
    def test_resume_native_missing_slot_uses_resume_stream(self, mock_executor_cls):
        _seed_interrupt(
            session_id="sess_slot_native_001",
            interrupt_id="int_slot_native_001",
            interrupt_type="missing_slot",
            payload={
                "message": "未识别到过滤值，请补充正确地区",
                "slot_name": "filter_value",
                "field": "Region",
                "requested_value": "Eest",
                "options": [],
                "resume_strategy": "root_graph_native",
            },
        )

        captured: dict[str, Any] = {}

        async def mock_stream(*args, **kwargs) -> AsyncIterator[Dict[str, Any]]:
            captured.update(kwargs)
            yield {"type": "complete"}

        mock_executor = MagicMock()
        mock_executor.resume_stream = mock_stream
        mock_executor_cls.return_value = mock_executor

        client = TestClient(app)
        response = client.post(
            "/api/chat/resume",
            json={
                "session_id": "sess_slot_native_001",
                "interrupt_id": "int_slot_native_001",
                "resume_payload": {
                    "selection_type": "slot_fill",
                    "slot_name": "filter_value",
                    "value": "East",
                },
            },
            headers={"X-Tableau-Username": "admin"},
        )

        assert response.status_code == 200
        events = _parse_sse_events(response.text)
        assert any(event["type"] == "complete" for event in events)
        assert captured["resume_value"] == "East"
        assert captured["resume_strategy"] == "root_graph_native"
        assert captured["question"] == "各区域销售额"
        assert captured["history"] == [{"role": "user", "content": "各区域销售额"}]

    @patch("analytics_assistant.src.api.routers.chat.RootGraphRunner")
    def test_resume_value_confirm_uses_native_resume_stream(self, mock_executor_cls):
        _seed_interrupt(
            session_id="sess_value_001",
            interrupt_id="int_value_001",
            interrupt_type="value_confirm",
            payload={
                "message": "检测到多个候选值，请确认",
                "field": "region",
                "candidates": ["华东", "华南"],
                "resume_strategy": "root_graph_native",
            },
        )

        captured: dict[str, Any] = {}

        async def mock_stream(*args, **kwargs) -> AsyncIterator[Dict[str, Any]]:
            captured.update(kwargs)
            yield {"type": "complete"}

        mock_executor = MagicMock()
        mock_executor.resume_stream = mock_stream
        mock_executor_cls.return_value = mock_executor

        client = TestClient(app)
        response = client.post(
            "/api/chat/resume",
            json={
                "session_id": "sess_value_001",
                "interrupt_id": "int_value_001",
                "resume_payload": {
                    "selection_type": "value_confirm",
                    "field": "region",
                    "value": "华东",
                },
            },
            headers={"X-Tableau-Username": "admin"},
        )

        assert response.status_code == 200
        events = _parse_sse_events(response.text)
        assert any(event["type"] == "complete" for event in events)
        assert captured["resume_value"] == "华东"
        assert captured["resume_strategy"] == "root_graph_native"
        assert captured["question"] == "各区域销售额"
        assert captured["history"] == [{"role": "user", "content": "各区域销售额"}]

    @patch("analytics_assistant.src.api.routers.chat.RootGraphRunner")
    def test_resume_high_risk_confirm_false_returns_cancelled_complete(
        self,
        mock_executor_cls,
    ):
        _seed_interrupt(
            session_id="sess_risk_001",
            interrupt_id="int_risk_001",
            interrupt_type="high_risk_query_confirm",
            payload={
                "message": "该查询预计扫描量较大，是否继续？",
                "risk_level": "high",
                "estimated_rows": 5000000,
                "resume_strategy": "root_graph_native",
                "risk_signature": "sig-risk-test",
            },
        )

        client = TestClient(app)
        response = client.post(
            "/api/chat/resume",
            json={
                "session_id": "sess_risk_001",
                "interrupt_id": "int_risk_001",
                "resume_payload": {
                    "selection_type": "high_risk_query",
                    "confirm": False,
                },
            },
            headers={"X-Tableau-Username": "admin"},
        )

        assert response.status_code == 200
        events = _parse_sse_events(response.text)
        assert len(events) == 1
        assert events[0]["type"] == "complete"
        assert events[0]["data"] == {
            "status": "cancelled",
            "reason": "user_declined_high_risk_query",
        }
        mock_executor_cls.assert_not_called()

    @patch("analytics_assistant.src.api.routers.chat.RootGraphRunner")
    def test_resume_high_risk_confirm_true_uses_root_graph_native_resume(self, mock_executor_cls):
        _seed_interrupt(
            session_id="sess_risk_002",
            interrupt_id="int_risk_002",
            interrupt_type="high_risk_query_confirm",
            payload={
                "message": "该查询预计扫描量较大，是否继续？",
                "risk_level": "high",
                "estimated_rows": 5000000,
                "resume_strategy": "root_graph_native",
                "risk_signature": "sig-risk-test",
            },
        )

        captured: dict[str, Any] = {}

        async def mock_stream(*args, **kwargs) -> AsyncIterator[Dict[str, Any]]:
            captured.update(kwargs)
            yield {"type": "complete"}

        mock_executor = MagicMock()
        mock_executor.resume_stream = mock_stream
        mock_executor_cls.return_value = mock_executor

        client = TestClient(app)
        response = client.post(
            "/api/chat/resume",
            json={
                "session_id": "sess_risk_002",
                "interrupt_id": "int_risk_002",
                "resume_payload": {
                    "selection_type": "high_risk_query",
                    "confirm": True,
                },
            },
            headers={"X-Tableau-Username": "admin"},
        )

        assert response.status_code == 200
        events = _parse_sse_events(response.text)
        assert any(event["type"] == "complete" for event in events)
        assert captured["resume_value"] is True
        assert captured["resume_strategy"] == "root_graph_native"
        assert captured["question"] == "各区域销售额"
        assert captured["history"] == [{"role": "user", "content": "各区域销售额"}]

    def test_resume_invalid_payload_returns_validation_error(self):
        _seed_interrupt(
            session_id="sess_invalid_001",
            interrupt_id="int_invalid_001",
            interrupt_type="datasource_disambiguation",
            payload={
                "message": "找到多个同名数据源，请选择",
                "choices": [
                    {
                        "datasource_luid": "ds_sales",
                        "project": "Sales",
                        "name": "Revenue",
                    },
                ],
            },
        )

        client = TestClient(app)
        response = client.post(
            "/api/chat/resume",
            json={
                "session_id": "sess_invalid_001",
                "interrupt_id": "int_invalid_001",
                "resume_payload": {"selection_type": "datasource"},
            },
            headers={"X-Tableau-Username": "admin"},
        )

        assert response.status_code == 200
        events = _parse_sse_events(response.text)
        assert events
        assert events[0]["type"] == "error"
        assert events[0]["data"]["error_code"] == "RESUME_VALIDATION_ERROR"


