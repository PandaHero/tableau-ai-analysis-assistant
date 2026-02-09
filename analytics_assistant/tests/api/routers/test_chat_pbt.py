# -*- coding: utf-8 -*-
"""
聊天端点属性测试

Property 1: SSE Response Content-Type
Property 2: History Truncation Token Limit
Property 3: History Truncation Order Preservation
"""

import json
from typing import AsyncIterator, Dict, Any, List
from unittest.mock import MagicMock, patch

from hypothesis import given, settings, strategies as st
from fastapi.testclient import TestClient

from analytics_assistant.src.api.main import app
from analytics_assistant.src.agents.semantic_parser.components.history_manager import (
    HistoryManager,
    estimate_history_tokens,
)


# ========================================
# 策略定义
# ========================================

# 有效的消息角色
valid_roles = st.sampled_from(["user", "assistant"])

# 生成有效的消息
message_strategy = st.fixed_dictionaries({
    "role": valid_roles,
    "content": st.text(min_size=1, max_size=200),
})

# 生成非空消息列表（至少 1 条，最多 20 条）
messages_strategy = st.lists(message_strategy, min_size=1, max_size=20)

# 生成有效的数据源名称
datasource_name_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P")),
    min_size=1,
    max_size=50,
)


class TestSSEResponseContentTypePBT:
    """Property 1: SSE Response Content-Type

    **Validates: Requirements 2.1**

    *For any* valid chat request to `/api/chat/stream`,
    the response Content-Type should be `text/event-stream`.
    """

    @given(
        datasource_name=datasource_name_strategy,
        messages=messages_strategy,
    )
    @settings(max_examples=20, deadline=10000)
    @patch("analytics_assistant.src.api.routers.chat.WorkflowExecutor")
    @patch("analytics_assistant.src.api.routers.chat.get_history_manager")
    def test_sse_content_type_property(
        self,
        mock_get_hm,
        mock_executor_cls,
        datasource_name,
        messages,
    ):
        """对任意有效请求，响应 Content-Type 始终为 text/event-stream。"""
        # Mock HistoryManager
        mock_hm = MagicMock()
        mock_hm.truncate_history.return_value = messages[-3:]
        mock_hm.estimate_history_tokens.return_value = 10
        mock_get_hm.return_value = mock_hm

        # Mock WorkflowExecutor
        async def mock_stream(*args, **kwargs) -> AsyncIterator[Dict[str, Any]]:
            yield {"type": "complete"}

        mock_executor = MagicMock()
        mock_executor.execute_stream = mock_stream
        mock_executor_cls.return_value = mock_executor

        client = TestClient(app)
        response = client.post(
            "/api/chat/stream",
            json={
                "messages": messages,
                "datasource_name": datasource_name,
            },
            headers={"X-Tableau-Username": "test_user"},
        )

        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")


class TestHistoryTruncationTokenLimitPBT:
    """Property 2: History Truncation Token Limit

    **Validates: Requirements 3.2, 3.3**

    *For any* conversation history, after truncation the resulting token count
    should be <= the configured `max_history_tokens` limit, and if the original
    history was already within the limit, all messages should be preserved unchanged.
    """

    @given(
        messages=st.lists(message_strategy, min_size=0, max_size=30),
        max_tokens=st.integers(min_value=10, max_value=5000),
    )
    @settings(max_examples=50, deadline=5000)
    def test_truncation_respects_token_limit(self, messages, max_tokens):
        """截断后的 token 数始终 <= max_tokens。"""
        manager = HistoryManager(max_history_tokens=max_tokens)
        truncated = manager.truncate_history(messages, max_tokens=max_tokens)

        truncated_tokens = estimate_history_tokens(truncated)
        assert truncated_tokens <= max_tokens

    @given(
        messages=st.lists(message_strategy, min_size=0, max_size=20),
    )
    @settings(max_examples=50, deadline=5000)
    def test_within_limit_preserves_all(self, messages):
        """原始历史在限制内时，保留所有消息。"""
        original_tokens = estimate_history_tokens(messages)
        # 设置一个足够大的限制
        max_tokens = original_tokens + 100

        manager = HistoryManager(max_history_tokens=max_tokens)
        truncated = manager.truncate_history(messages, max_tokens=max_tokens)

        assert len(truncated) == len(messages)
        for orig, trunc in zip(messages, truncated):
            assert orig["role"] == trunc["role"]
            assert orig["content"] == trunc["content"]


class TestHistoryTruncationOrderPreservationPBT:
    """Property 3: History Truncation Order Preservation

    **Validates: Requirements 3.4**

    *For any* truncated conversation history, the relative order of retained
    messages should be the same as in the original history (newest message last),
    and the retained messages should be a contiguous suffix of the original.
    """

    @given(
        messages=st.lists(message_strategy, min_size=1, max_size=30),
        max_tokens=st.integers(min_value=10, max_value=2000),
    )
    @settings(max_examples=50, deadline=5000)
    def test_order_preserved_and_suffix(self, messages, max_tokens):
        """截断结果是原始列表的连续后缀，顺序不变。"""
        manager = HistoryManager(max_history_tokens=max_tokens)
        truncated = manager.truncate_history(messages, max_tokens=max_tokens)

        if len(truncated) == 0:
            return

        # 截断结果应该是原始列表的后缀
        offset = len(messages) - len(truncated)
        assert offset >= 0

        for i, msg in enumerate(truncated):
            original_msg = messages[offset + i]
            assert msg["role"] == original_msg["role"]
            assert msg["content"] == original_msg["content"]
