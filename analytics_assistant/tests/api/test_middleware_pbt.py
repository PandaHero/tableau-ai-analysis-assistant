# -*- coding: utf-8 -*-
"""
错误消息安全性属性测试

Property 19: Error Message Safety
"""

from hypothesis import given, settings, strategies as st

from analytics_assistant.src.api.middleware import _sanitize_error_message


# 敏感内容策略
_SENSITIVE_PATTERNS = [
    "api_key=sk-1234567890abcdef",
    "password=mysecretpass",
    "token=eyJhbGciOiJIUzI1NiJ9",
    "connection_string=postgresql://user:pass@host/db",
    "sqlite:///analytics_assistant/data/storage.db",
    "postgresql://admin:secret@localhost:5432/mydb",
    'Traceback (most recent call last):\n  File "main.py"',
    'File "/analytics_assistant/src/api/routers/chat.py", line 42',
    "secret=abc123",
    "api_secret=xyz789",
    "deepseek_api_key=sk-abc",
    "zhipu_api_key=abc.def",
    "conn_string=sqlite:///test.db",
    "db_path=/var/data/storage.db",
    "sk-abcdef1234567890",
]

sensitive_message_strategy = st.sampled_from(_SENSITIVE_PATTERNS)


class TestErrorMessageSafetyPBT:
    """Property 19: Error Message Safety

    **Validates: Requirements 10.2**

    *For any* exception handled by the API, the returned error message should not
    contain sensitive internal details such as stack traces, database connection
    strings, API keys, or file paths.
    """

    @given(sensitive_msg=sensitive_message_strategy)
    @settings(max_examples=30, deadline=5000)
    def test_sensitive_content_sanitized(self, sensitive_msg):
        """包含敏感信息的错误消息被清理。"""
        result = _sanitize_error_message(sensitive_msg)
        assert result == "服务内部错误，请稍后重试"

    @given(
        safe_msg=st.sampled_from([
            "会话不存在",
            "无权访问此会话",
            "缺少 X-Tableau-Username 请求头",
            "请求参数验证失败",
            "数据源不存在",
        ]),
    )
    @settings(max_examples=10, deadline=5000)
    def test_safe_messages_preserved(self, safe_msg):
        """安全的错误消息保持不变。"""
        result = _sanitize_error_message(safe_msg)
        assert result == safe_msg

    @given(
        prefix=st.text(min_size=0, max_size=20),
        sensitive=st.sampled_from([
            "api_key", "password", "token", "secret",
            "connection_string", "sqlite", "postgresql",
            "Traceback", 'File "',
        ]),
        suffix=st.text(min_size=0, max_size=20),
    )
    @settings(max_examples=30, deadline=5000)
    def test_embedded_sensitive_keywords_caught(self, prefix, sensitive, suffix):
        """嵌入在任意文本中的敏感关键词也能被检测。"""
        msg = f"{prefix}{sensitive}{suffix}"
        result = _sanitize_error_message(msg)
        assert result == "服务内部错误，请稍后重试"
