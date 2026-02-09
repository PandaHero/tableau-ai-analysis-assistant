# -*- coding: utf-8 -*-
"""
用户设置路由单元测试

测试 GET/PUT /api/settings 端点。
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
    dependencies._repositories["user_settings"] = BaseRepository(
        "user_settings", store=store,
    )
    yield
    dependencies._repositories.clear()
    dependencies._repositories.update(original_repos)


HEADERS = {"X-Tableau-Username": "alice"}


class TestGetSettings:
    """GET /api/settings 测试。"""

    def test_auto_create_defaults(self):
        """首次访问自动创建默认设置。"""
        client = TestClient(app)
        resp = client.get("/api/settings", headers=HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["tableau_username"] == "alice"
        assert data["language"] == "zh"
        assert data["analysis_depth"] == "detailed"
        assert data["theme"] == "light"
        assert data["show_thinking_process"] is True
        assert data["default_datasource_id"] is None

    def test_returns_existing_settings(self):
        """返回已有设置。"""
        client = TestClient(app)
        # 先创建
        client.get("/api/settings", headers=HEADERS)
        # 再获取
        resp = client.get("/api/settings", headers=HEADERS)
        assert resp.status_code == 200
        assert resp.json()["language"] == "zh"

    def test_requires_auth(self):
        """缺少认证头返回 401。"""
        client = TestClient(app)
        resp = client.get("/api/settings")
        assert resp.status_code == 401


class TestUpdateSettings:
    """PUT /api/settings 测试。"""

    def test_partial_update(self):
        """部分更新只修改指定字段。"""
        client = TestClient(app)
        # 先获取默认值
        client.get("/api/settings", headers=HEADERS)

        # 只更新 language
        resp = client.put(
            "/api/settings",
            json={"language": "en"},
            headers=HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["language"] == "en"
        # 其他字段保持默认
        assert data["theme"] == "light"
        assert data["analysis_depth"] == "detailed"

    def test_update_multiple_fields(self):
        """同时更新多个字段。"""
        client = TestClient(app)
        resp = client.put(
            "/api/settings",
            json={
                "language": "en",
                "theme": "dark",
                "show_thinking_process": False,
            },
            headers=HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["language"] == "en"
        assert data["theme"] == "dark"
        assert data["show_thinking_process"] is False

    def test_update_persists(self):
        """更新后再次获取能看到变更。"""
        client = TestClient(app)
        client.put(
            "/api/settings",
            json={"language": "en"},
            headers=HEADERS,
        )
        resp = client.get("/api/settings", headers=HEADERS)
        assert resp.json()["language"] == "en"

    def test_requires_auth(self):
        """缺少认证头返回 401。"""
        client = TestClient(app)
        resp = client.put("/api/settings", json={"language": "en"})
        assert resp.status_code == 401
