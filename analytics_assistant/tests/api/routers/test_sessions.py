# -*- coding: utf-8 -*-
"""
会话管理路由单元测试

测试 CRUD 端点、认证、数据隔离。
使用 InMemoryStore 确保测试隔离。
"""

import pytest
from fastapi.testclient import TestClient
from langgraph.store.memory import InMemoryStore

from analytics_assistant.src.api.main import app
from analytics_assistant.src.api import dependencies
from analytics_assistant.src.infra.storage import BaseRepository


@pytest.fixture(autouse=True)
def isolated_storage():
    """每个测试使用独立的 InMemoryStore，确保完全隔离。"""
    store = InMemoryStore()

    # 替换 repository 工厂，使用内存存储
    original_repos = dependencies._repositories.copy()
    dependencies._repositories.clear()
    dependencies._repositories["sessions"] = BaseRepository("sessions", store=store)

    yield

    dependencies._repositories.clear()
    dependencies._repositories.update(original_repos)


HEADERS_ALICE = {"X-Tableau-Username": "alice"}
HEADERS_BOB = {"X-Tableau-Username": "bob"}


class TestCreateSession:
    """POST /api/sessions 测试。"""

    def test_create_session_returns_200(self):
        """创建会话返回 session_id 和 created_at。"""
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
        """不传 title 时使用默认标题。"""
        client = TestClient(app)
        response = client.post(
            "/api/sessions",
            json={},
            headers=HEADERS_ALICE,
        )
        assert response.status_code == 200

    def test_create_session_requires_auth(self):
        """缺少认证头返回 401。"""
        client = TestClient(app)
        response = client.post("/api/sessions", json={})
        assert response.status_code == 401


class TestGetSessions:
    """GET /api/sessions 测试。"""

    def test_empty_list(self):
        """无会话时返回空列表。"""
        client = TestClient(app)
        response = client.get("/api/sessions", headers=HEADERS_ALICE)
        assert response.status_code == 200
        data = response.json()
        assert data["sessions"] == []
        assert data["total"] == 0

    def test_returns_user_sessions_only(self):
        """只返回当前用户的会话。"""
        client = TestClient(app)

        # Alice 创建 2 个会话
        client.post("/api/sessions", json={"title": "A1"}, headers=HEADERS_ALICE)
        client.post("/api/sessions", json={"title": "A2"}, headers=HEADERS_ALICE)

        # Bob 创建 1 个会话
        client.post("/api/sessions", json={"title": "B1"}, headers=HEADERS_BOB)

        # Alice 只能看到自己的
        response = client.get("/api/sessions", headers=HEADERS_ALICE)
        data = response.json()
        assert data["total"] == 2
        titles = {s["title"] for s in data["sessions"]}
        assert titles == {"A1", "A2"}

        # Bob 只能看到自己的
        response = client.get("/api/sessions", headers=HEADERS_BOB)
        data = response.json()
        assert data["total"] == 1
        assert data["sessions"][0]["title"] == "B1"


class TestGetSessionDetail:
    """GET /api/sessions/{id} 测试。"""

    def test_get_session_detail(self):
        """获取会话详情。"""
        client = TestClient(app)
        create_resp = client.post(
            "/api/sessions",
            json={"title": "详情测试"},
            headers=HEADERS_ALICE,
        )
        session_id = create_resp.json()["session_id"]

        response = client.get(
            f"/api/sessions/{session_id}",
            headers=HEADERS_ALICE,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == session_id
        assert data["title"] == "详情测试"
        assert data["tableau_username"] == "alice"

    def test_session_not_found(self):
        """不存在的会话返回 404。"""
        client = TestClient(app)
        response = client.get(
            "/api/sessions/00000000-0000-0000-0000-000000000000",
            headers=HEADERS_ALICE,
        )
        assert response.status_code == 404

    def test_cross_user_access_returns_403(self):
        """跨用户访问返回 403。"""
        client = TestClient(app)

        # Alice 创建会话
        create_resp = client.post(
            "/api/sessions",
            json={"title": "Alice 的会话"},
            headers=HEADERS_ALICE,
        )
        session_id = create_resp.json()["session_id"]

        # Bob 尝试访问 → 403
        response = client.get(
            f"/api/sessions/{session_id}",
            headers=HEADERS_BOB,
        )
        assert response.status_code == 403


class TestUpdateSession:
    """PUT /api/sessions/{id} 测试。"""

    def test_update_title(self):
        """更新会话标题。"""
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
        """更新会话消息列表。"""
        client = TestClient(app)
        create_resp = client.post(
            "/api/sessions",
            json={"title": "消息测试"},
            headers=HEADERS_ALICE,
        )
        session_id = create_resp.json()["session_id"]

        messages = [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好！"},
        ]
        response = client.put(
            f"/api/sessions/{session_id}",
            json={"messages": messages},
            headers=HEADERS_ALICE,
        )
        assert response.status_code == 200
        assert len(response.json()["messages"]) == 2

    def test_update_nonexistent_returns_404(self):
        """更新不存在的会话返回 404。"""
        client = TestClient(app)
        response = client.put(
            "/api/sessions/00000000-0000-0000-0000-000000000000",
            json={"title": "x"},
            headers=HEADERS_ALICE,
        )
        assert response.status_code == 404

    def test_update_cross_user_returns_403(self):
        """跨用户更新返回 403。"""
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
        """删除会话后无法再获取。"""
        client = TestClient(app)
        create_resp = client.post(
            "/api/sessions",
            json={"title": "待删除"},
            headers=HEADERS_ALICE,
        )
        session_id = create_resp.json()["session_id"]

        # 删除
        response = client.delete(
            f"/api/sessions/{session_id}",
            headers=HEADERS_ALICE,
        )
        assert response.status_code == 200

        # 再获取 → 404
        response = client.get(
            f"/api/sessions/{session_id}",
            headers=HEADERS_ALICE,
        )
        assert response.status_code == 404

    def test_delete_nonexistent_returns_404(self):
        """删除不存在的会话返回 404。"""
        client = TestClient(app)
        response = client.delete(
            "/api/sessions/00000000-0000-0000-0000-000000000000",
            headers=HEADERS_ALICE,
        )
        assert response.status_code == 404

    def test_delete_cross_user_returns_403(self):
        """跨用户删除返回 403。"""
        client = TestClient(app)
        create_resp = client.post(
            "/api/sessions",
            json={"title": "Alice"},
            headers=HEADERS_ALICE,
        )
        session_id = create_resp.json()["session_id"]

        response = client.delete(
            f"/api/sessions/{session_id}",
            headers=HEADERS_BOB,
        )
        assert response.status_code == 403
