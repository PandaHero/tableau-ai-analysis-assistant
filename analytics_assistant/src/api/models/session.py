# -*- coding: utf-8 -*-
"""
会话相关 Pydantic 模型

定义会话 CRUD 的请求和响应数据结构。
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from .chat import Message

class CreateSessionRequest(BaseModel):
    """创建会话请求。"""

    title: Optional[str] = Field(None, description="会话标题")

class CreateSessionResponse(BaseModel):
    """创建会话响应。"""

    session_id: str = Field(..., description="会话 ID")
    created_at: datetime = Field(..., description="创建时间")

class SessionResponse(BaseModel):
    """会话详情模型。"""

    id: str
    tableau_username: str
    title: str
    messages: list[Message]
    created_at: datetime
    updated_at: datetime

class GetSessionsResponse(BaseModel):
    """获取会话列表响应。"""

    sessions: list[SessionResponse]
    total: int

class UpdateSessionRequest(BaseModel):
    """更新会话请求。"""

    title: Optional[str] = None
    messages: Optional[list[Message]] = None
