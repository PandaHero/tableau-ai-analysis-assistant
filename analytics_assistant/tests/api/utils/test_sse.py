# -*- coding: utf-8 -*-
"""
SSE 工具函数单元测试
"""

import json

from analytics_assistant.src.api.utils.sse import (
    format_sse_event,
    format_sse_heartbeat,
)


class TestFormatSSEEvent:
    """format_sse_event 单元测试。"""

    def test_basic_event(self):
        """基本事件格式化。"""
        event = {"type": "token", "content": "hello"}
        result = format_sse_event(event)
        assert result.startswith("data: ")
        assert result.endswith("\n\n")
        # 解析回 JSON 验证
        payload = json.loads(result[len("data: "):-2])
        assert payload == event

    def test_chinese_content(self):
        """中文内容不被转义。"""
        event = {"type": "token", "content": "你好世界"}
        result = format_sse_event(event)
        assert "你好世界" in result
        # ensure_ascii=False
        assert "\\u" not in result

    def test_thinking_event(self):
        """thinking 事件格式化。"""
        event = {
            "type": "thinking",
            "stage": "understanding",
            "name": "理解问题",
            "status": "running",
        }
        result = format_sse_event(event)
        payload = json.loads(result[len("data: "):-2])
        assert payload["stage"] == "understanding"
        assert payload["status"] == "running"

    def test_complete_event(self):
        """complete 事件格式化。"""
        event = {"type": "complete"}
        result = format_sse_event(event)
        payload = json.loads(result[len("data: "):-2])
        assert payload == {"type": "complete"}

    def test_error_event(self):
        """error 事件格式化。"""
        event = {"type": "error", "error": "超时"}
        result = format_sse_event(event)
        payload = json.loads(result[len("data: "):-2])
        assert payload["error"] == "超时"


class TestFormatSSEHeartbeat:
    """format_sse_heartbeat 单元测试。"""

    def test_heartbeat_format(self):
        """心跳格式正确（SSE 注释）。"""
        result = format_sse_heartbeat()
        assert result == ": heartbeat\n\n"

    def test_heartbeat_is_sse_comment(self):
        """心跳以冒号开头（SSE 注释规范）。"""
        result = format_sse_heartbeat()
        assert result.startswith(":")
