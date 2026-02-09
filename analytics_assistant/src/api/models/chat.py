# -*- coding: utf-8 -*-
"""
聊天相关 Pydantic 模型

定义聊天请求和消息数据结构。
"""

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class Message(BaseModel):
    """消息模型。"""

    role: Literal["user", "assistant", "system"]
    content: str
    created_at: Optional[datetime] = None


class ChatRequest(BaseModel):
    """聊天请求模型。"""

    messages: List[Message] = Field(..., description="对话历史")
    datasource_name: str = Field(..., description="数据源名称")
    language: Literal["zh", "en"] = Field(default="zh", description="语言")
    analysis_depth: Literal["detailed", "comprehensive"] = Field(
        default="detailed",
        description="分析深度",
    )
    session_id: Optional[str] = Field(None, description="会话 ID")
