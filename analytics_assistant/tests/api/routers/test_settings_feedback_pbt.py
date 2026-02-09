# -*- coding: utf-8 -*-
"""
用户设置和反馈属性测试

Property 15: Settings Round-Trip with Auto-Creation
Property 16: Feedback Persistence with User Association
"""

import pytest
from hypothesis import given, settings, strategies as st
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
    dependencies._repositories["user_feedback"] = BaseRepository(
        "user_feedback", store=store,
    )
    yield
    dependencies._repositories.clear()
    dependencies._repositories.update(original_repos)


# ========================================
# 策略定义
# ========================================

language_strategy = st.sampled_from(["zh", "en"])
depth_strategy = st.sampled_from(["detailed", "comprehensive"])
theme_strategy = st.sampled_from(["light", "dark", "system"])
bool_strategy = st.booleans()

# ASCII 用户名（HTTP header 限制）
username_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), max_codepoint=127),
    min_size=1,
    max_size=30,
)

feedback_type_strategy = st.sampled_from(["positive", "negative"])
message_id_strategy = st.text(min_size=1, max_size=50).filter(lambda s: s.strip())


class TestSettingsRoundTripPBT:
    """Property 15: Settings Round-Trip with Auto-Creation

    **Validates: Requirements 6.1, 6.2, 6.3**

    *For any* authenticated user, GET `/api/settings` should always return valid
    settings (creating defaults on first access), and any subsequent PUT should
    persist changes that are reflected in the next GET.
    """

    @given(username=username_strategy)
    @settings(max_examples=15, deadline=10000)
    def test_auto_creation_on_first_access(self, username):
        """首次访问自动创建默认设置。"""
        client = TestClient(app)
        resp = client.get(
            "/api/settings",
            headers={"X-Tableau-Username": username},
        )
        assert resp.status_code == 200
        data = resp.json()
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
    def test_put_then_get_round_trip(self, language, depth, theme, show_thinking):
        """PUT 更新后 GET 能看到变更。"""
        client = TestClient(app)
        headers = {"X-Tableau-Username": "roundtrip_user"}

        # PUT 更新
        resp = client.put(
            "/api/settings",
            json={
                "language": language,
                "analysis_depth": depth,
                "theme": theme,
                "show_thinking_process": show_thinking,
            },
            headers=headers,
        )
        assert resp.status_code == 200

        # GET 验证
        resp = client.get("/api/settings", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["language"] == language
        assert data["analysis_depth"] == depth
        assert data["theme"] == theme
        assert data["show_thinking_process"] == show_thinking


class TestFeedbackPersistencePBT:
    """Property 16: Feedback Persistence with User Association

    **Validates: Requirements 7.1, 7.4**

    *For any* valid feedback submission, the feedback should be persisted with
    the correct `tableau_username`, `message_id`, and `type` fields.
    """

    @given(
        username=username_strategy,
        message_id=message_id_strategy,
        feedback_type=feedback_type_strategy,
    )
    @settings(max_examples=20, deadline=10000)
    def test_feedback_persisted_with_user(
        self, username, message_id, feedback_type,
    ):
        """反馈提交后关联正确的用户和消息。"""
        client = TestClient(app)
        resp = client.post(
            "/api/feedback",
            json={
                "message_id": message_id,
                "type": feedback_type,
            },
            headers={"X-Tableau-Username": username},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "反馈已提交"
        assert "feedback_id" in data

        # 验证持久化：通过 repo 直接查询
        repo = dependencies._repositories["user_feedback"]
        feedback_data = repo.find_by_id(data["feedback_id"])
        assert feedback_data is not None
        assert feedback_data["tableau_username"] == username
        assert feedback_data["message_id"] == message_id
        assert feedback_data["type"] == feedback_type
