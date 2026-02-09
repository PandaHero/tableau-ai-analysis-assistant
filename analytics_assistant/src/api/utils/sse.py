# -*- coding: utf-8 -*-
"""
SSE 事件格式化工具

将事件字典转换为 Server-Sent Events 格式字符串。

SSE 格式规范:
    data: {"type":"token","content":"你好"}\n\n

心跳格式:
    : heartbeat\n\n
"""

import json
from typing import Any, Dict


def format_sse_event(event: Dict[str, Any]) -> str:
    """将事件字典转换为 SSE 格式字符串。

    Args:
        event: 事件字典，如 {"type": "token", "content": "你好"}

    Returns:
        SSE 格式字符串，如 'data: {"type":"token","content":"你好"}\\n\\n'
    """
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def format_sse_heartbeat() -> str:
    """生成 SSE 心跳注释。

    心跳用于保持连接活跃，防止代理或浏览器超时断开。

    Returns:
        SSE 心跳字符串 ': heartbeat\\n\\n'
    """
    return ": heartbeat\n\n"
