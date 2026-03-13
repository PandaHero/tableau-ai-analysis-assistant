# -*- coding: utf-8 -*-
"""用户设置路由单元测试。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from analytics_assistant.src.api import dependencies
from analytics_assistant.src.api.main import app
from analytics_assistant.src.infra.business_storage import SettingsRepository
from analytics_assistant.tests.helpers.business_storage import create_test_business_database


@pytest.fixture(autouse=True)
def isolated_storage():
    """每个测试使用独立业务库。"""
    database, db_path = create_test_business_database("settings")
    original_repos = dependencies._repositories.copy()
    dependencies._repositories.clear()
    dependencies._repositories["user_settings"] = SettingsRepository(database=database)
    yield
    dependencies._repositories.clear()
    dependencies._repositories.update(original_repos)
    if db_path.exists():
        db_path.unlink()


HEADERS = {"X-Tableau-Username": "alice"}


class TestGetSettings:
    """GET /api/settings 测试。"""

    def test_auto_create_defaults(self):
        client = TestClient(app)
        response = client.get("/api/settings", headers=HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert data["tableau_username"] == "alice"
        assert data["language"] == "zh"
        assert data["analysis_depth"] == "detailed"
        assert data["theme"] == "light"
        assert data["show_thinking_process"] is True
        assert data["default_datasource_id"] is None

    def test_returns_existing_settings(self):
        client = TestClient(app)
        client.get("/api/settings", headers=HEADERS)
        response = client.get("/api/settings", headers=HEADERS)
        assert response.status_code == 200
        assert response.json()["language"] == "zh"

    def test_requires_auth(self):
        client = TestClient(app)
        response = client.get("/api/settings")
        assert response.status_code == 401


class TestUpdateSettings:
    """PUT /api/settings 测试。"""

    def test_partial_update(self):
        client = TestClient(app)
        client.get("/api/settings", headers=HEADERS)

        response = client.put(
            "/api/settings",
            json={"language": "en"},
            headers=HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["language"] == "en"
        assert data["theme"] == "light"
        assert data["analysis_depth"] == "detailed"

    def test_update_multiple_fields(self):
        client = TestClient(app)
        response = client.put(
            "/api/settings",
            json={
                "language": "en",
                "theme": "dark",
                "show_thinking_process": False,
            },
            headers=HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["language"] == "en"
        assert data["theme"] == "dark"
        assert data["show_thinking_process"] is False

    def test_update_persists(self):
        client = TestClient(app)
        client.put("/api/settings", json={"language": "en"}, headers=HEADERS)
        response = client.get("/api/settings", headers=HEADERS)
        assert response.json()["language"] == "en"

    def test_requires_auth(self):
        client = TestClient(app)
        response = client.put("/api/settings", json={"language": "en"})
        assert response.status_code == 401
