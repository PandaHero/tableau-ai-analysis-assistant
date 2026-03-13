# -*- coding: utf-8 -*-
"""会话路由属性测试。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from hypothesis import assume, given, settings, strategies as st

from analytics_assistant.src.api import dependencies
from analytics_assistant.src.api.main import app
from analytics_assistant.src.infra.business_storage import SessionRepository
from analytics_assistant.tests.helpers.business_storage import create_test_business_database


@pytest.fixture(autouse=True)
def isolated_storage():
    """每个测试使用独立业务库。"""
    database, db_path = create_test_business_database("sessions_pbt")
    original_repos = dependencies._repositories.copy()
    dependencies._repositories.clear()
    dependencies._repositories["sessions"] = SessionRepository(database=database)
    yield
    dependencies._repositories.clear()
    dependencies._repositories.update(original_repos)
    if db_path.exists():
        db_path.unlink()


username_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), max_codepoint=127),
    min_size=1,
    max_size=30,
)
title_strategy = st.text(
    alphabet=st.characters(blacklist_categories=("Cc", "Cs", "Zl", "Zp", "Zs"), max_codepoint=0x7E),
    min_size=1,
    max_size=100,
).filter(lambda value: bool(value.strip()) and value == value.strip())
api_endpoints = st.sampled_from(
    [
        ("POST", "/api/sessions"),
        ("GET", "/api/sessions"),
    ]
)


class TestSessionCRUDRoundTripPBT:
    @given(title=title_strategy, new_title=title_strategy)
    @settings(max_examples=20, deadline=10000)
    def test_crud_round_trip(self, title: str, new_title: str) -> None:
        client = TestClient(app)
        headers = {"X-Tableau-Username": "pbt_user"}

        response = client.post("/api/sessions", json={"title": title}, headers=headers)
        assert response.status_code == 200
        session_id = response.json()["session_id"]

        response = client.get(f"/api/sessions/{session_id}", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == title
        assert data["tableau_username"] == "pbt_user"

        response = client.put(
            f"/api/sessions/{session_id}",
            json={"title": new_title},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["title"] == new_title

        response = client.get(f"/api/sessions/{session_id}", headers=headers)
        assert response.status_code == 200
        assert response.json()["title"] == new_title

        response = client.delete(f"/api/sessions/{session_id}", headers=headers)
        assert response.status_code == 200

        response = client.get(f"/api/sessions/{session_id}", headers=headers)
        assert response.status_code == 404


class TestSessionListOrderingPBT:
    @given(titles=st.lists(title_strategy, min_size=2, max_size=8))
    @settings(max_examples=15, deadline=15000)
    def test_sessions_ordered_by_updated_at_desc(self, titles: list[str]) -> None:
        client = TestClient(app)
        headers = {"X-Tableau-Username": "order_user"}

        for title in titles:
            client.post("/api/sessions", json={"title": title}, headers=headers)

        response = client.get("/api/sessions", headers=headers)
        assert response.status_code == 200
        sessions = response.json()["sessions"]
        timestamps = [item["updated_at"] for item in sessions]
        assert timestamps == sorted(timestamps, reverse=True)


class TestUserDataIsolationPBT:
    @given(
        user_a=username_strategy,
        user_b=username_strategy,
        title_a=title_strategy,
        title_b=title_strategy,
    )
    @settings(max_examples=15, deadline=10000)
    def test_user_data_isolation(
        self,
        user_a: str,
        user_b: str,
        title_a: str,
        title_b: str,
    ) -> None:
        assume(user_a != user_b)
        client = TestClient(app)

        client.post(
            "/api/sessions",
            json={"title": title_a},
            headers={"X-Tableau-Username": user_a},
        )
        client.post(
            "/api/sessions",
            json={"title": title_b},
            headers={"X-Tableau-Username": user_b},
        )

        response_a = client.get("/api/sessions", headers={"X-Tableau-Username": user_a})
        for session in response_a.json()["sessions"]:
            assert session["tableau_username"] == user_a

        response_b = client.get("/api/sessions", headers={"X-Tableau-Username": user_b})
        for session in response_b.json()["sessions"]:
            assert session["tableau_username"] == user_b


class TestAuthenticationRequirementPBT:
    @given(endpoint=api_endpoints)
    @settings(max_examples=10, deadline=10000)
    def test_missing_auth_returns_401(self, endpoint: tuple[str, str]) -> None:
        method, path = endpoint
        client = TestClient(app)
        if method == "POST":
            response = client.post(path, json={})
        else:
            response = client.get(path)
        assert response.status_code == 401


class TestCrossUserAccessPreventionPBT:
    @given(
        user_a=username_strategy,
        user_b=username_strategy,
        title=title_strategy,
    )
    @settings(max_examples=15, deadline=10000)
    def test_cross_user_access_blocked(self, user_a: str, user_b: str, title: str) -> None:
        assume(user_a != user_b)
        client = TestClient(app)

        response = client.post(
            "/api/sessions",
            json={"title": title},
            headers={"X-Tableau-Username": user_a},
        )
        session_id = response.json()["session_id"]

        response = client.get(
            f"/api/sessions/{session_id}",
            headers={"X-Tableau-Username": user_b},
        )
        assert response.status_code == 403

        response = client.put(
            f"/api/sessions/{session_id}",
            json={"title": "hacked"},
            headers={"X-Tableau-Username": user_b},
        )
        assert response.status_code == 403

        response = client.delete(
            f"/api/sessions/{session_id}",
            headers={"X-Tableau-Username": user_b},
        )
        assert response.status_code == 403


class TestNonExistentResourcePBT:
    @given(fake_id=st.uuids().map(str))
    @settings(max_examples=15, deadline=10000)
    def test_nonexistent_session_returns_404(self, fake_id: str) -> None:
        client = TestClient(app)
        headers = {"X-Tableau-Username": "test_user"}

        response = client.get(f"/api/sessions/{fake_id}", headers=headers)
        assert response.status_code == 404

        response = client.put(
            f"/api/sessions/{fake_id}",
            json={"title": "x"},
            headers=headers,
        )
        assert response.status_code == 404

        response = client.delete(f"/api/sessions/{fake_id}", headers=headers)
        assert response.status_code == 404
