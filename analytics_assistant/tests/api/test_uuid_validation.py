# -*- coding: utf-8 -*-
"""UUID 格式校验属性测试。"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from hypothesis import given, settings, strategies as st

from analytics_assistant.src.api import dependencies
from analytics_assistant.src.api.main import app
from analytics_assistant.src.infra.business_storage import SessionRepository
from analytics_assistant.tests.helpers.business_storage import create_test_business_database

HEADERS = {"X-Tableau-Username": "test-user"}

_URL_SAFE_ALPHABET = st.sampled_from(
    [char for char in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_~"]
)


def _is_valid_uuid(value: str) -> bool:
    """检查字符串是否是有效 UUID。"""
    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError):
        return False


non_uuid_strings = st.text(
    alphabet=_URL_SAFE_ALPHABET,
    min_size=1,
    max_size=80,
).filter(lambda value: not _is_valid_uuid(value))


@pytest.fixture(autouse=True)
def isolated_storage():
    """每个测试使用独立业务库。"""
    database, db_path = create_test_business_database("uuid_validation")
    original_repos = dependencies._repositories.copy()
    dependencies._repositories.clear()
    dependencies._repositories["sessions"] = SessionRepository(database=database)
    yield
    dependencies._repositories.clear()
    dependencies._repositories.update(original_repos)
    if db_path.exists():
        db_path.unlink()


class TestUUIDValidation:
    @given(invalid_id=non_uuid_strings)
    @settings(max_examples=50)
    def test_non_uuid_returns_422(self, invalid_id: str):
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get(f"/api/sessions/{invalid_id}", headers=HEADERS)
        assert response.status_code == 422

        response = client.put(
            f"/api/sessions/{invalid_id}",
            json={"title": "x"},
            headers=HEADERS,
        )
        assert response.status_code == 422

        response = client.delete(f"/api/sessions/{invalid_id}", headers=HEADERS)
        assert response.status_code == 422

    @given(data=st.data())
    @settings(max_examples=20)
    def test_valid_uuid_not_rejected_by_format(self, data: st.DataObject):
        valid_uuid = str(data.draw(st.uuids()))
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get(f"/api/sessions/{valid_uuid}", headers=HEADERS)
        assert response.status_code == 404

        response = client.put(
            f"/api/sessions/{valid_uuid}",
            json={"title": "x"},
            headers=HEADERS,
        )
        assert response.status_code == 404

        response = client.delete(f"/api/sessions/{valid_uuid}", headers=HEADERS)
        assert response.status_code == 404
