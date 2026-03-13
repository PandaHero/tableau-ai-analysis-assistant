# -*- coding: utf-8 -*-
"""会话路由单元测试。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from analytics_assistant.src.api import dependencies
from analytics_assistant.src.api.main import app
from analytics_assistant.src.infra.business_storage import SessionRepository
from analytics_assistant.tests.helpers.business_storage import create_test_business_database


@pytest.fixture(autouse=True)
def isolated_storage():
    """每个测试使用独立业务库，确保数据隔离。"""
    database, db_path = create_test_business_database("sessions")
    original_repos = dependencies._repositories.copy()
    dependencies._repositories.clear()
    dependencies._repositories["sessions"] = SessionRepository(database=database)
    yield
    dependencies._repositories.clear()
    dependencies._repositories.update(original_repos)
    if db_path.exists():
        db_path.unlink()


HEADERS_ALICE = {"X-Tableau-Username": "alice"}
HEADERS_BOB = {"X-Tableau-Username": "bob"}


class TestCreateSession:
    """POST /api/sessions 测试。"""

    def test_create_session_returns_200(self):
        client = TestClient(app)
        response = client.post(
            "/api/sessions",
            json={"title": "测试会话"},
            headers=HEADERS_ALICE,
        )
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert "created_at" in data

    def test_create_session_default_title(self):
        client = TestClient(app)
        response = client.post("/api/sessions", json={}, headers=HEADERS_ALICE)
        assert response.status_code == 200

    def test_create_session_requires_auth(self):
        client = TestClient(app)
        response = client.post("/api/sessions", json={})
        assert response.status_code == 401


class TestGetSessions:
    """GET /api/sessions 测试。"""

    def test_empty_list(self):
        client = TestClient(app)
        response = client.get("/api/sessions", headers=HEADERS_ALICE)
        assert response.status_code == 200
        data = response.json()
        assert data["sessions"] == []
        assert data["total"] == 0

    def test_returns_user_sessions_only(self):
        client = TestClient(app)
        client.post("/api/sessions", json={"title": "A1"}, headers=HEADERS_ALICE)
        client.post("/api/sessions", json={"title": "A2"}, headers=HEADERS_ALICE)
        client.post("/api/sessions", json={"title": "B1"}, headers=HEADERS_BOB)

        response = client.get("/api/sessions", headers=HEADERS_ALICE)
        data = response.json()
        assert data["total"] == 2
        titles = {item["title"] for item in data["sessions"]}
        assert titles == {"A1", "A2"}

        response = client.get("/api/sessions", headers=HEADERS_BOB)
        data = response.json()
        assert data["total"] == 1
        assert data["sessions"][0]["title"] == "B1"


class TestGetSessionDetail:
    """GET /api/sessions/{id} 测试。"""

    def test_get_session_detail(self):
        client = TestClient(app)
        create_resp = client.post(
            "/api/sessions",
            json={"title": "详情测试"},
            headers=HEADERS_ALICE,
        )
        session_id = create_resp.json()["session_id"]

        response = client.get(f"/api/sessions/{session_id}", headers=HEADERS_ALICE)
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == session_id
        assert data["title"] == "详情测试"
        assert data["tableau_username"] == "alice"

    def test_session_not_found(self):
        client = TestClient(app)
        response = client.get(
            "/api/sessions/00000000-0000-0000-0000-000000000000",
            headers=HEADERS_ALICE,
        )
        assert response.status_code == 404

    def test_cross_user_access_returns_403(self):
        client = TestClient(app)
        create_resp = client.post(
            "/api/sessions",
            json={"title": "Alice 的会话"},
            headers=HEADERS_ALICE,
        )
        session_id = create_resp.json()["session_id"]

        response = client.get(f"/api/sessions/{session_id}", headers=HEADERS_BOB)
        assert response.status_code == 403


class TestUpdateSession:
    """PUT /api/sessions/{id} 测试。"""

    def test_update_title(self):
        client = TestClient(app)
        create_resp = client.post(
            "/api/sessions",
            json={"title": "原标题"},
            headers=HEADERS_ALICE,
        )
        session_id = create_resp.json()["session_id"]

        response = client.put(
            f"/api/sessions/{session_id}",
            json={"title": "新标题"},
            headers=HEADERS_ALICE,
        )
        assert response.status_code == 200
        assert response.json()["title"] == "新标题"

    def test_update_messages(self):
        client = TestClient(app)
        create_resp = client.post(
            "/api/sessions",
            json={"title": "消息测试"},
            headers=HEADERS_ALICE,
        )
        session_id = create_resp.json()["session_id"]

        messages = [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好呀"},
        ]
        response = client.put(
            f"/api/sessions/{session_id}",
            json={"messages": messages},
            headers=HEADERS_ALICE,
        )
        assert response.status_code == 200
        assert len(response.json()["messages"]) == 2

    def test_update_nonexistent_returns_404(self):
        client = TestClient(app)
        response = client.put(
            "/api/sessions/00000000-0000-0000-0000-000000000000",
            json={"title": "x"},
            headers=HEADERS_ALICE,
        )
        assert response.status_code == 404

    def test_update_cross_user_returns_403(self):
        client = TestClient(app)
        create_resp = client.post(
            "/api/sessions",
            json={"title": "Alice"},
            headers=HEADERS_ALICE,
        )
        session_id = create_resp.json()["session_id"]

        response = client.put(
            f"/api/sessions/{session_id}",
            json={"title": "被 Bob 修改"},
            headers=HEADERS_BOB,
        )
        assert response.status_code == 403


class TestDeleteSession:
    """DELETE /api/sessions/{id} 测试。"""

    def test_delete_session(self):
        client = TestClient(app)
        create_resp = client.post(
            "/api/sessions",
            json={"title": "待删除"},
            headers=HEADERS_ALICE,
        )
        session_id = create_resp.json()["session_id"]

        response = client.delete(f"/api/sessions/{session_id}", headers=HEADERS_ALICE)
        assert response.status_code == 200

        response = client.get(f"/api/sessions/{session_id}", headers=HEADERS_ALICE)
        assert response.status_code == 404

    def test_delete_nonexistent_returns_404(self):
        client = TestClient(app)
        response = client.delete(
            "/api/sessions/00000000-0000-0000-0000-000000000000",
            headers=HEADERS_ALICE,
        )
        assert response.status_code == 404

    def test_delete_cross_user_returns_403(self):
        client = TestClient(app)
        create_resp = client.post(
            "/api/sessions",
            json={"title": "Alice"},
            headers=HEADERS_ALICE,
        )
        session_id = create_resp.json()["session_id"]

        response = client.delete(f"/api/sessions/{session_id}", headers=HEADERS_BOB)
        assert response.status_code == 403
