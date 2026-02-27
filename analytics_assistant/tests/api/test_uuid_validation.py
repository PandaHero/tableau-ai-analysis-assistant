# -*- coding: utf-8 -*-
"""
UUID 格式验证属性测试（Property 15）

验证 session_id 路径参数的 UUID 格式校验：
- 非 UUID 字符串返回 HTTP 422
- 有效 UUID 正常处理（不因格式被拒绝）
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from hypothesis import given, settings, strategies as st
from langgraph.store.memory import InMemoryStore

from analytics_assistant.src.api.main import app
from analytics_assistant.src.api import dependencies
from analytics_assistant.src.infra.storage import BaseRepository

HEADERS = {"X-Tableau-Username": "test-user"}

# 生成 URL 安全的非 UUID 格式字符串策略
# 限制为可打印 ASCII，排除控制字符、URL 特殊字符 #?/% 以及路径遍历字符 .
_URL_SAFE_ALPHABET = st.sampled_from(
    [c for c in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_~"]
)
non_uuid_strings = st.text(
    alphabet=_URL_SAFE_ALPHABET, min_size=1, max_size=80
).filter(lambda s: not _is_valid_uuid(s))


def _is_valid_uuid(s: str) -> bool:
    """检查字符串是否为有效 UUID。"""
    try:
        uuid.UUID(s)
        return True
    except (ValueError, AttributeError):
        return False


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


class TestUUIDValidation:
    """UUID 格式验证属性测试。"""

    @given(invalid_id=non_uuid_strings)
    @settings(max_examples=50)
    def test_non_uuid_returns_422(self, invalid_id: str):
        """非 UUID 格式的 session_id 应返回 422。"""
        client = TestClient(app, raise_server_exceptions=False)

        # GET、PUT、DELETE 三个端点都应拒绝非 UUID
        get_resp = client.get(
            f"/api/sessions/{invalid_id}",
            headers=HEADERS,
        )
        assert get_resp.status_code == 422, (
            f"GET 应返回 422，实际 {get_resp.status_code}，输入: {invalid_id!r}"
        )

        put_resp = client.put(
            f"/api/sessions/{invalid_id}",
            json={"title": "x"},
            headers=HEADERS,
        )
        assert put_resp.status_code == 422, (
            f"PUT 应返回 422，实际 {put_resp.status_code}，输入: {invalid_id!r}"
        )

        delete_resp = client.delete(
            f"/api/sessions/{invalid_id}",
            headers=HEADERS,
        )
        assert delete_resp.status_code == 422, (
            f"DELETE 应返回 422，实际 {delete_resp.status_code}，输入: {invalid_id!r}"
        )

    @given(data=st.data())
    @settings(max_examples=20)
    def test_valid_uuid_not_rejected_by_format(self, data: st.DataObject):
        """有效 UUID 不会因格式校验被拒绝（返回 404 而非 422）。"""
        valid_uuid = str(data.draw(st.uuids()))
        client = TestClient(app, raise_server_exceptions=False)

        get_resp = client.get(
            f"/api/sessions/{valid_uuid}",
            headers=HEADERS,
        )
        # 有效 UUID 应该通过格式校验，返回 404（不存在）而非 422
        assert get_resp.status_code == 404, (
            f"GET 有效 UUID 应返回 404，实际 {get_resp.status_code}，输入: {valid_uuid}"
        )

        put_resp = client.put(
            f"/api/sessions/{valid_uuid}",
            json={"title": "x"},
            headers=HEADERS,
        )
        assert put_resp.status_code == 404, (
            f"PUT 有效 UUID 应返回 404，实际 {put_resp.status_code}，输入: {valid_uuid}"
        )

        delete_resp = client.delete(
            f"/api/sessions/{valid_uuid}",
            headers=HEADERS,
        )
        assert delete_resp.status_code == 404, (
            f"DELETE 有效 UUID 应返回 404，实际 {delete_resp.status_code}，输入: {valid_uuid}"
        )
