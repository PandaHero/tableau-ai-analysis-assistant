# -*- coding: utf-8 -*-
"""
分页参数正确性属性测试（Property 16）

验证会话列表分页：
- 返回结果数量不超过 limit
- 结果是完整列表从 offset 开始的子序列
"""

import pytest
from fastapi.testclient import TestClient
from hypothesis import given, settings, strategies as st
from langgraph.store.memory import InMemoryStore

from analytics_assistant.src.api.main import app
from analytics_assistant.src.api import dependencies
from analytics_assistant.src.infra.storage import BaseRepository

HEADERS = {"X-Tableau-Username": "pagination-user"}


def _reset_storage() -> None:
    """重置存储为全新的 InMemoryStore。"""
    store = InMemoryStore()
    dependencies._repositories["sessions"] = BaseRepository("sessions", store=store)


@pytest.fixture(autouse=True)
def isolated_storage():
    """每个测试使用独立的 InMemoryStore。"""
    original_repos = dependencies._repositories.copy()
    _reset_storage()
    yield
    dependencies._repositories.clear()
    dependencies._repositories.update(original_repos)


def _create_sessions(client: TestClient, count: int) -> list[str]:
    """批量创建会话，返回 session_id 列表。"""
    ids = []
    for i in range(count):
        resp = client.post(
            "/api/sessions",
            json={"title": f"会话-{i}"},
            headers=HEADERS,
        )
        ids.append(resp.json()["session_id"])
    return ids


class TestPagination:
    """分页参数正确性属性测试。"""

    @given(
        num_sessions=st.integers(min_value=0, max_value=15),
        offset=st.integers(min_value=0, max_value=20),
        limit=st.integers(min_value=1, max_value=100),
    )
    @settings(max_examples=30)
    def test_pagination_result_count_within_limit(
        self, num_sessions: int, offset: int, limit: int
    ):
        """返回结果数量不超过 limit。"""
        _reset_storage()
        client = TestClient(app)
        _create_sessions(client, num_sessions)

        resp = client.get(
            "/api/sessions",
            params={"offset": offset, "limit": limit},
            headers=HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()

        assert len(data["sessions"]) <= limit
        assert data["total"] == num_sessions

    @given(
        num_sessions=st.integers(min_value=1, max_value=10),
        offset=st.integers(min_value=0, max_value=12),
        limit=st.integers(min_value=1, max_value=100),
    )
    @settings(max_examples=30)
    def test_pagination_is_subsequence_of_full_list(
        self, num_sessions: int, offset: int, limit: int
    ):
        """分页结果是完整列表从 offset 开始的子序列。"""
        _reset_storage()
        client = TestClient(app)
        _create_sessions(client, num_sessions)

        # 获取完整列表
        full_resp = client.get(
            "/api/sessions",
            params={"offset": 0, "limit": 100},
            headers=HEADERS,
        )
        full_ids = [s["id"] for s in full_resp.json()["sessions"]]

        # 获取分页结果
        page_resp = client.get(
            "/api/sessions",
            params={"offset": offset, "limit": limit},
            headers=HEADERS,
        )
        page_ids = [s["id"] for s in page_resp.json()["sessions"]]

        # 分页结果应等于完整列表的 [offset:offset+limit] 切片
        expected = full_ids[offset:offset + limit]
        assert page_ids == expected

    def test_offset_beyond_total_returns_empty(self):
        """offset 超过总数时返回空列表。"""
        client = TestClient(app)
        _create_sessions(client, 3)

        resp = client.get(
            "/api/sessions",
            params={"offset": 100, "limit": 10},
            headers=HEADERS,
        )
        data = resp.json()
        assert data["sessions"] == []
        assert data["total"] == 3

    def test_invalid_pagination_params_return_422(self):
        """无效分页参数返回 422。"""
        client = TestClient(app)

        # offset 为负数
        resp = client.get(
            "/api/sessions",
            params={"offset": -1},
            headers=HEADERS,
        )
        assert resp.status_code == 422

        # limit 为 0
        resp = client.get(
            "/api/sessions",
            params={"limit": 0},
            headers=HEADERS,
        )
        assert resp.status_code == 422

        # limit 超过 100
        resp = client.get(
            "/api/sessions",
            params={"limit": 101},
            headers=HEADERS,
        )
        assert resp.status_code == 422
