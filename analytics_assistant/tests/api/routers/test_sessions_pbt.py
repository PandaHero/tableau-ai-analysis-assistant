# -*- coding: utf-8 -*-
"""
会话管理属性测试

Property 9: Session CRUD Round-Trip
Property 10: Session List Ordering
Property 11: User Data Isolation
Property 12: Authentication Requirement
Property 13: Cross-User Access Prevention
Property 14: Non-Existent Resource Returns 404
"""

import uuid

import pytest
from hypothesis import given, settings, strategies as st, assume
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
    dependencies._repositories["sessions"] = BaseRepository("sessions", store=store)
    yield
    dependencies._repositories.clear()
    dependencies._repositories.update(original_repos)


# ========================================
# 策略定义
# ========================================

# 用户名策略（非空 ASCII 字母数字，HTTP header 只支持 ASCII）
username_strategy = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N"),
        max_codepoint=127,
    ),
    min_size=1,
    max_size=30,
)

# 会话标题策略
title_strategy = st.text(min_size=1, max_size=100)

# API 端点列表（除 /health 外）
api_endpoints = st.sampled_from([
    ("POST", "/api/sessions"),
    ("GET", "/api/sessions"),
])


class TestSessionCRUDRoundTripPBT:
    """Property 9: Session CRUD Round-Trip

    **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5**

    *For any* session created via POST, the session should be retrievable via GET
    with all its data intact, updatable via PUT with changes reflected in subsequent
    GETs, and after DELETE it should no longer be retrievable (returning 404).
    """

    @given(
        title=title_strategy,
        new_title=title_strategy,
    )
    @settings(max_examples=20, deadline=10000)
    def test_crud_round_trip(self, title, new_title):
        """创建 → 读取 → 更新 → 读取 → 删除 → 读取(404) 完整往返。"""
        client = TestClient(app)
        headers = {"X-Tableau-Username": "pbt_user"}

        # CREATE
        resp = client.post("/api/sessions", json={"title": title}, headers=headers)
        assert resp.status_code == 200
        session_id = resp.json()["session_id"]

        # READ - 数据完整
        resp = client.get(f"/api/sessions/{session_id}", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == title
        assert data["tableau_username"] == "pbt_user"

        # UPDATE
        resp = client.put(
            f"/api/sessions/{session_id}",
            json={"title": new_title},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == new_title

        # READ after UPDATE
        resp = client.get(f"/api/sessions/{session_id}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["title"] == new_title

        # DELETE
        resp = client.delete(f"/api/sessions/{session_id}", headers=headers)
        assert resp.status_code == 200

        # READ after DELETE → 404
        resp = client.get(f"/api/sessions/{session_id}", headers=headers)
        assert resp.status_code == 404


class TestSessionListOrderingPBT:
    """Property 10: Session List Ordering

    **Validates: Requirements 5.2**

    *For any* user's session list returned by GET `/api/sessions`,
    sessions should be ordered by `updatedAt` in descending order (newest first).
    """

    @given(
        titles=st.lists(title_strategy, min_size=2, max_size=8),
    )
    @settings(max_examples=15, deadline=15000)
    def test_sessions_ordered_by_updated_at_desc(self, titles):
        """会话列表按 updated_at 倒序排列。"""
        client = TestClient(app)
        headers = {"X-Tableau-Username": "order_user"}

        # 创建多个会话
        for t in titles:
            client.post("/api/sessions", json={"title": t}, headers=headers)

        # 获取列表
        resp = client.get("/api/sessions", headers=headers)
        assert resp.status_code == 200
        sessions = resp.json()["sessions"]

        # 验证倒序
        timestamps = [s["updated_at"] for s in sessions]
        assert timestamps == sorted(timestamps, reverse=True)


class TestUserDataIsolationPBT:
    """Property 11: User Data Isolation

    **Validates: Requirements 5.6, 6.4**

    *For any* two distinct users, API requests by user A should never return
    sessions belonging to user B.
    """

    @given(
        user_a=username_strategy,
        user_b=username_strategy,
        title_a=title_strategy,
        title_b=title_strategy,
    )
    @settings(max_examples=15, deadline=10000)
    def test_user_data_isolation(self, user_a, user_b, title_a, title_b):
        """不同用户的数据完全隔离。"""
        assume(user_a != user_b)

        client = TestClient(app)

        # 用户 A 创建会话
        client.post(
            "/api/sessions",
            json={"title": title_a},
            headers={"X-Tableau-Username": user_a},
        )

        # 用户 B 创建会话
        client.post(
            "/api/sessions",
            json={"title": title_b},
            headers={"X-Tableau-Username": user_b},
        )

        # 用户 A 只能看到自己的
        resp_a = client.get("/api/sessions", headers={"X-Tableau-Username": user_a})
        for s in resp_a.json()["sessions"]:
            assert s["tableau_username"] == user_a

        # 用户 B 只能看到自己的
        resp_b = client.get("/api/sessions", headers={"X-Tableau-Username": user_b})
        for s in resp_b.json()["sessions"]:
            assert s["tableau_username"] == user_b


class TestAuthenticationRequirementPBT:
    """Property 12: Authentication Requirement

    **Validates: Requirements 5.7, 6.5, 7.5**

    *For any* API request (except `/health`) missing the `X-Tableau-Username` header,
    the response should be 401 Unauthorized.
    """

    @given(endpoint=api_endpoints)
    @settings(max_examples=10, deadline=10000)
    def test_missing_auth_returns_401(self, endpoint):
        """缺少认证头的请求返回 401。"""
        method, path = endpoint
        client = TestClient(app)

        if method == "POST":
            resp = client.post(path, json={})
        else:
            resp = client.get(path)

        assert resp.status_code == 401


class TestCrossUserAccessPreventionPBT:
    """Property 13: Cross-User Access Prevention

    **Validates: Requirements 5.8**

    *For any* attempt by user A to access (GET, PUT, DELETE) a session belonging
    to user B, the response should be 403 Forbidden.
    """

    @given(
        user_a=username_strategy,
        user_b=username_strategy,
        title=title_strategy,
    )
    @settings(max_examples=15, deadline=10000)
    def test_cross_user_access_blocked(self, user_a, user_b, title):
        """跨用户访问被阻止（403）。"""
        assume(user_a != user_b)

        client = TestClient(app)

        # 用户 A 创建会话
        resp = client.post(
            "/api/sessions",
            json={"title": title},
            headers={"X-Tableau-Username": user_a},
        )
        session_id = resp.json()["session_id"]

        # 用户 B 尝试 GET → 403
        resp = client.get(
            f"/api/sessions/{session_id}",
            headers={"X-Tableau-Username": user_b},
        )
        assert resp.status_code == 403

        # 用户 B 尝试 PUT → 403
        resp = client.put(
            f"/api/sessions/{session_id}",
            json={"title": "hacked"},
            headers={"X-Tableau-Username": user_b},
        )
        assert resp.status_code == 403

        # 用户 B 尝试 DELETE → 403
        resp = client.delete(
            f"/api/sessions/{session_id}",
            headers={"X-Tableau-Username": user_b},
        )
        assert resp.status_code == 403


class TestNonExistentResourcePBT:
    """Property 14: Non-Existent Resource Returns 404

    **Validates: Requirements 5.9, 9.2**

    *For any* non-existent session ID, the API should return 404 Not Found.
    """

    @given(fake_id=st.uuids().map(str))
    @settings(max_examples=15, deadline=10000)
    def test_nonexistent_session_returns_404(self, fake_id):
        """不存在的会话 ID 返回 404。"""
        client = TestClient(app)
        headers = {"X-Tableau-Username": "test_user"}

        # GET
        resp = client.get(f"/api/sessions/{fake_id}", headers=headers)
        assert resp.status_code == 404

        # PUT
        resp = client.put(
            f"/api/sessions/{fake_id}",
            json={"title": "x"},
            headers=headers,
        )
        assert resp.status_code == 404

        # DELETE
        resp = client.delete(f"/api/sessions/{fake_id}", headers=headers)
        assert resp.status_code == 404
