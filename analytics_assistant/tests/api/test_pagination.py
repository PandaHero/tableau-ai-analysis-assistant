# -*- coding: utf-8 -*-
"""会话分页测试。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from hypothesis import given, settings, strategies as st

from analytics_assistant.src.api import dependencies
from analytics_assistant.src.api.main import app
from analytics_assistant.src.infra.business_storage import SessionRepository
from analytics_assistant.tests.helpers.business_storage import create_test_business_database

HEADERS = {"X-Tableau-Username": "pagination-user"}
_CURRENT_DB_PATH: Path | None = None


def _reset_storage() -> Path:
    """为当前用例重建独立业务库。"""
    global _CURRENT_DB_PATH

    if _CURRENT_DB_PATH is not None and _CURRENT_DB_PATH.exists():
        _CURRENT_DB_PATH.unlink()
    database, _CURRENT_DB_PATH = create_test_business_database("pagination")
    dependencies._repositories["sessions"] = SessionRepository(database=database)
    return _CURRENT_DB_PATH


@pytest.fixture(autouse=True)
def isolated_storage() -> Any:
    """每个测试用独立会话仓库，避免属性测试样本互相污染。"""
    original_repos = dependencies._repositories.copy()
    db_path = _reset_storage()
    yield
    dependencies._repositories.clear()
    dependencies._repositories.update(original_repos)
    if db_path.exists():
        db_path.unlink()


def _create_sessions(client: TestClient, count: int) -> list[str]:
    ids: list[str] = []
    for index in range(count):
        response = client.post(
            "/api/sessions",
            json={"title": f"会话-{index}"},
            headers=HEADERS,
        )
        ids.append(response.json()["session_id"])
    return ids


class TestPagination:
    @given(
        num_sessions=st.integers(min_value=0, max_value=15),
        offset=st.integers(min_value=0, max_value=20),
        limit=st.integers(min_value=1, max_value=100),
    )
    @settings(max_examples=30, deadline=None)
    def test_pagination_result_count_within_limit(
        self,
        num_sessions: int,
        offset: int,
        limit: int,
    ) -> None:
        _reset_storage()
        client = TestClient(app)
        _create_sessions(client, num_sessions)

        response = client.get(
            "/api/sessions",
            params={"offset": offset, "limit": limit},
            headers=HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["sessions"]) <= limit
        assert data["total"] == num_sessions

    @given(
        num_sessions=st.integers(min_value=1, max_value=10),
        offset=st.integers(min_value=0, max_value=12),
        limit=st.integers(min_value=1, max_value=100),
    )
    @settings(max_examples=30, deadline=None)
    def test_pagination_is_subsequence_of_full_list(
        self,
        num_sessions: int,
        offset: int,
        limit: int,
    ) -> None:
        _reset_storage()
        client = TestClient(app)
        _create_sessions(client, num_sessions)

        full_response = client.get(
            "/api/sessions",
            params={"offset": 0, "limit": 100},
            headers=HEADERS,
        )
        full_ids = [item["id"] for item in full_response.json()["sessions"]]

        page_response = client.get(
            "/api/sessions",
            params={"offset": offset, "limit": limit},
            headers=HEADERS,
        )
        page_ids = [item["id"] for item in page_response.json()["sessions"]]
        assert page_ids == full_ids[offset:offset + limit]

    def test_offset_beyond_total_returns_empty(self) -> None:
        client = TestClient(app)
        _create_sessions(client, 3)

        response = client.get(
            "/api/sessions",
            params={"offset": 100, "limit": 10},
            headers=HEADERS,
        )
        data = response.json()
        assert data["sessions"] == []
        assert data["total"] == 3

    def test_invalid_pagination_params_return_422(self) -> None:
        client = TestClient(app)

        response = client.get(
            "/api/sessions",
            params={"offset": -1},
            headers=HEADERS,
        )
        assert response.status_code == 422

        response = client.get(
            "/api/sessions",
            params={"limit": 0},
            headers=HEADERS,
        )
        assert response.status_code == 422

        response = client.get(
            "/api/sessions",
            params={"limit": 101},
            headers=HEADERS,
        )
        assert response.status_code == 422
