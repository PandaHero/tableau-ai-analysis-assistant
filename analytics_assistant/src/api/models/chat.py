# -*- coding: utf-8 -*-
"""
聊天相关 Pydantic 模型

定义聊天请求和消息数据结构。
"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

class Message(BaseModel):
    """消息模型。"""

    role: Literal["user", "assistant", "system"]
    content: str
    created_at: Optional[datetime] = None

class ChatRequest(BaseModel):
    """聊天请求模型。"""

    messages: list[Message] = Field(
        ...,
        min_length=1,
        description="对话历史，至少包含一条消息",
    )
    datasource_name: str = Field(..., description="数据源名称")
    language: Literal["zh", "en"] = Field(default="zh", description="语言")
    analysis_depth: Literal["detailed", "comprehensive"] = Field(
        default="detailed",
        description="分析深度",
    )
    replan_mode: Literal["user_select", "auto_continue", "stop"] = Field(
        default="user_select",
        description="重规划继续策略：用户选择、自动继续或停止",
    )
    selected_candidate_question: Optional[str] = Field(
        None,
        description="当使用 user_select 时，前端或调用方选中的候选问题",
    )
    session_id: Optional[str] = Field(None, description="会话 ID")
