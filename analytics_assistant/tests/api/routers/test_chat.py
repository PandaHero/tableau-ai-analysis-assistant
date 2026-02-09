# -*- coding: utf-8 -*-
"""
聊天路由单元测试

测试 POST /api/chat/stream 端点的请求验证和 SSE 响应。
使用 Mock 替代 WorkflowExecutor 和 HistoryManager，避免真实 LLM 调用。
"""

import json
from typing import AsyncIterator, Dict, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from analytics_assistant.src.api.main import app
from analytics_assistant.src.infra.storage import StoreFactory


@pytest.fixture(autouse=True)
def reset_storage():
    """每个测试前后重置存储。"""
    StoreFactory.reset()
    yield
    StoreFactory.reset()


def _make_chat_body(
    messages=None,
    datasource_name="测试数据源",
    language="zh",
):
    """构造聊天请求体。"""
    if messages is None:
        messages = [{"role": "user", "content": "各区域销售额"}]
    return {
        "messages": messages,
        "datasource_name": datasource_name,
        "language": language,
    }


class TestChatStreamValidation:
    """聊天端点请求验证测试。"""

    def test_missing_username_returns_401(self):
        """缺少 X-Tableau-Username 返回 401。"""
        client = TestClient(app)
        response = client.post(
            "/api/chat/stream",
            json=_make_chat_body(),
        )
        assert response.status_code == 401

    def test_missing_messages_returns_422(self):
        """缺少 messages 字段返回 422。"""
        client = TestClient(app)
        response = client.post(
            "/api/chat/stream",
            json={"datasource_name": "test"},
            headers={"X-Tableau-Username": "admin"},
        )
        assert response.status_code == 422

    def test_missing_datasource_name_returns_422(self):
        """缺少 datasource_name 返回 422。"""
        client = TestClient(app)
        response = client.post(
            "/api/chat/stream",
            json={"messages": [{"role": "user", "content": "hello"}]},
            headers={"X-Tableau-Username": "admin"},
        )
        assert response.status_code == 422

    def test_invalid_role_returns_422(self):
        """无效的 role 值返回 422。"""
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
    """聊天端点 SSE 响应测试（Mock WorkflowExecutor）。"""

    @patch(
        "analytics_assistant.src.api.routers.chat.WorkflowExecutor",
    )
    @patch(
        "analytics_assistant.src.api.routers.chat.get_history_manager",
    )
    def test_returns_sse_content_type(self, mock_get_hm, mock_executor_cls):
        """响应 Content-Type 为 text/event-stream。"""
        # Mock HistoryManager
        mock_hm = MagicMock()
        mock_hm.truncate_history.return_value = [
            {"role": "user", "content": "hello"},
        ]
        mock_hm.estimate_history_tokens.return_value = 10
        mock_get_hm.return_value = mock_hm

        # Mock WorkflowExecutor
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
        "analytics_assistant.src.api.routers.chat.WorkflowExecutor",
    )
    @patch(
        "analytics_assistant.src.api.routers.chat.get_history_manager",
    )
    def test_streams_token_events(self, mock_get_hm, mock_executor_cls):
        """SSE 流包含 token 事件。"""
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
        lines = response.text.strip().split("\n\n")
        events = []
        for line in lines:
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: "):]))

        # 应该有 token + complete 事件
        types = [e["type"] for e in events]
        assert "token" in types
        assert "complete" in types

    @patch(
        "analytics_assistant.src.api.routers.chat.WorkflowExecutor",
    )
    @patch(
        "analytics_assistant.src.api.routers.chat.get_history_manager",
    )
    def test_streams_thinking_events(self, mock_get_hm, mock_executor_cls):
        """SSE 流包含 thinking 阶段事件。"""
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
        lines = response.text.strip().split("\n\n")
        events = []
        for line in lines:
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: "):]))

        thinking_events = [e for e in events if e["type"] == "thinking"]
        assert len(thinking_events) == 2
        assert thinking_events[0]["status"] == "running"
        assert thinking_events[1]["status"] == "completed"

    @patch(
        "analytics_assistant.src.api.routers.chat.WorkflowExecutor",
    )
    @patch(
        "analytics_assistant.src.api.routers.chat.get_history_manager",
    )
    def test_history_truncation_called(self, mock_get_hm, mock_executor_cls):
        """验证 HistoryManager.truncate_history 被调用。"""
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

        # truncate_history 应该被调用
        mock_hm.truncate_history.assert_called_once()
        call_args = mock_hm.truncate_history.call_args[0][0]
        assert len(call_args) == 3

    @patch(
        "analytics_assistant.src.api.routers.chat.WorkflowExecutor",
    )
    @patch(
        "analytics_assistant.src.api.routers.chat.get_history_manager",
    )
    def test_no_cache_headers(self, mock_get_hm, mock_executor_cls):
        """SSE 响应包含 no-cache 头。"""
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
