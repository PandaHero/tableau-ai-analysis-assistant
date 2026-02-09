# -*- coding: utf-8 -*-
"""
用户反馈路由单元测试

测试 POST /api/feedback 端点。
"""

import pytest
from fastapi.testclient import TestClient
from langgraph.store.memory import InMemoryStore

from analytics_assistant.src.api.main import app
from analytics_assistant.src.api import dependencies
from analytics_assistant.src.infra.storage import BaseRepository


@pytest.fixture(autouse=True)
def isolated_storage():
    """每个测试使用独立的 InMemoryStore。"""
    store = InMemoryStore()
    original_repos = dependencies._repositories.copy()
    dependencies._repositories.clear()
    dependencies._repositories["user_feedback"] = BaseRepository(
        "user_feedback", store=store,
    )
    yield
    dependencies._repositories.clear()
    dependencies._repositories.update(original_repos)


HEADERS = {"X-Tableau-Username": "alice"}


class TestSubmitFeedback:
    """POST /api/feedback 测试。"""

    def test_submit_positive_feedback(self):
        """提交正面反馈。"""
        client = TestClient(app)
        resp = client.post(
            "/api/feedback",
            json={
                "message_id": "msg-001",
                "type": "positive",
            },
            headers=HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "反馈已提交"
        assert "feedback_id" in data

    def test_submit_negative_feedback_with_reason(self):
        """提交负面反馈（含原因和评论）。"""
        client = TestClient(app)
        resp = client.post(
            "/api/feedback",
            json={
                "message_id": "msg-002",
                "type": "negative",
                "reason": "回答不准确",
                "comment": "字段映射错误",
            },
            headers=HEADERS,
        )
        assert resp.status_code == 200

    def test_requires_message_id(self):
        """缺少 message_id 返回 422。"""
        client = TestClient(app)
        resp = client.post(
            "/api/feedback",
            json={"type": "positive"},
            headers=HEADERS,
        )
        assert resp.status_code == 422

    def test_requires_type(self):
        """缺少 type 返回 422。"""
        client = TestClient(app)
        resp = client.post(
            "/api/feedback",
            json={"message_id": "msg-001"},
            headers=HEADERS,
        )
        assert resp.status_code == 422

    def test_invalid_type_returns_422(self):
        """无效的 type 值返回 422。"""
        client = TestClient(app)
        resp = client.post(
            "/api/feedback",
            json={"message_id": "msg-001", "type": "invalid"},
            headers=HEADERS,
        )
        assert resp.status_code == 422

    def test_requires_auth(self):
        """缺少认证头返回 401。"""
        client = TestClient(app)
        resp = client.post(
            "/api/feedback",
            json={"message_id": "msg-001", "type": "positive"},
        )
        assert resp.status_code == 401
