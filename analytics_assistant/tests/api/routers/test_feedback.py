# -*- coding: utf-8 -*-
"""用户反馈路由单元测试。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from analytics_assistant.src.api import dependencies
from analytics_assistant.src.api.main import app
from analytics_assistant.src.infra.business_storage import FeedbackRepository
from analytics_assistant.tests.helpers.business_storage import create_test_business_database


@pytest.fixture(autouse=True)
def isolated_storage():
    """每个测试使用独立业务库。"""
    database, db_path = create_test_business_database("feedback")
    original_repos = dependencies._repositories.copy()
    dependencies._repositories.clear()
    dependencies._repositories["user_feedback"] = FeedbackRepository(database=database)
    yield
    dependencies._repositories.clear()
    dependencies._repositories.update(original_repos)
    if db_path.exists():
        db_path.unlink()


HEADERS = {"X-Tableau-Username": "alice"}


class TestSubmitFeedback:
    """POST /api/feedback 测试。"""

    def test_submit_positive_feedback(self):
        client = TestClient(app)
        response = client.post(
            "/api/feedback",
            json={"message_id": "msg-001", "type": "positive"},
            headers=HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "反馈已提交"
        assert "feedback_id" in data

    def test_submit_negative_feedback_with_reason(self):
        client = TestClient(app)
        response = client.post(
            "/api/feedback",
            json={
                "message_id": "msg-002",
                "type": "negative",
                "reason": "回答不准确",
                "comment": "字段映射错误",
            },
            headers=HEADERS,
        )
        assert response.status_code == 200

    def test_requires_message_id(self):
        client = TestClient(app)
        response = client.post(
            "/api/feedback",
            json={"type": "positive"},
            headers=HEADERS,
        )
        assert response.status_code == 422

    def test_requires_type(self):
        client = TestClient(app)
        response = client.post(
            "/api/feedback",
            json={"message_id": "msg-001"},
            headers=HEADERS,
        )
        assert response.status_code == 422

    def test_invalid_type_returns_422(self):
        client = TestClient(app)
        response = client.post(
            "/api/feedback",
            json={"message_id": "msg-001", "type": "invalid"},
            headers=HEADERS,
        )
        assert response.status_code == 422

    def test_requires_auth(self):
        client = TestClient(app)
        response = client.post(
            "/api/feedback",
            json={"message_id": "msg-001", "type": "positive"},
        )
        assert response.status_code == 401
