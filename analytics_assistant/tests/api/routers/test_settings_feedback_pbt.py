# -*- coding: utf-8 -*-
"""设置与反馈属性测试。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from hypothesis import given, settings, strategies as st

from analytics_assistant.src.api import dependencies
from analytics_assistant.src.api.main import app
from analytics_assistant.src.infra.business_storage import FeedbackRepository, SettingsRepository
from analytics_assistant.tests.helpers.business_storage import create_test_business_database


@pytest.fixture(autouse=True)
def isolated_storage():
    """每个测试使用独立业务库。"""
    database, db_path = create_test_business_database("settings_feedback_pbt")
    original_repos = dependencies._repositories.copy()
    dependencies._repositories.clear()
    dependencies._repositories["user_settings"] = SettingsRepository(database=database)
    dependencies._repositories["user_feedback"] = FeedbackRepository(database=database)
    yield
    dependencies._repositories.clear()
    dependencies._repositories.update(original_repos)
    if db_path.exists():
        db_path.unlink()


language_strategy = st.sampled_from(["zh", "en"])
depth_strategy = st.sampled_from(["detailed", "comprehensive"])
theme_strategy = st.sampled_from(["light", "dark", "system"])
bool_strategy = st.booleans()
username_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), max_codepoint=127),
    min_size=1,
    max_size=30,
)
feedback_type_strategy = st.sampled_from(["positive", "negative"])
message_id_strategy = st.text(
    alphabet=st.characters(blacklist_categories=("Cc", "Cs", "Zl", "Zp", "Zs"), max_codepoint=0x7E),
    min_size=1,
    max_size=50,
).filter(lambda value: bool(value.strip()) and value == value.strip())


class TestSettingsRoundTripPBT:
    @given(username=username_strategy)
    @settings(max_examples=15, deadline=10000)
    def test_auto_creation_on_first_access(self, username: str) -> None:
        client = TestClient(app)
        response = client.get(
            "/api/settings",
            headers={"X-Tableau-Username": username},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["tableau_username"] == username
        assert data["language"] == "zh"
        assert data["analysis_depth"] == "detailed"
        assert data["theme"] == "light"

    @given(
        language=language_strategy,
        depth=depth_strategy,
        theme=theme_strategy,
        show_thinking=bool_strategy,
    )
    @settings(max_examples=20, deadline=10000)
    def test_put_then_get_round_trip(
        self,
        language: str,
        depth: str,
        theme: str,
        show_thinking: bool,
    ) -> None:
        client = TestClient(app)
        headers = {"X-Tableau-Username": "roundtrip_user"}

        response = client.put(
            "/api/settings",
            json={
                "language": language,
                "analysis_depth": depth,
                "theme": theme,
                "show_thinking_process": show_thinking,
            },
            headers=headers,
        )
        assert response.status_code == 200

        response = client.get("/api/settings", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["language"] == language
        assert data["analysis_depth"] == depth
        assert data["theme"] == theme
        assert data["show_thinking_process"] == show_thinking


class TestFeedbackPersistencePBT:
    @given(
        username=username_strategy,
        message_id=message_id_strategy,
        feedback_type=feedback_type_strategy,
    )
    @settings(max_examples=20, deadline=10000)
    def test_feedback_persisted_with_user(
        self,
        username: str,
        message_id: str,
        feedback_type: str,
    ) -> None:
        client = TestClient(app)
        response = client.post(
            "/api/feedback",
            json={"message_id": message_id, "type": feedback_type},
            headers={"X-Tableau-Username": username},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "反馈已提交"
        assert "feedback_id" in data

        repo = dependencies._repositories["user_feedback"]
        feedback_data = repo.find_by_id(data["feedback_id"])
        assert feedback_data is not None
        assert feedback_data["tableau_username"] == username
        assert feedback_data["message_id"] == message_id
        assert feedback_data["type"] == feedback_type
