# -*- coding: utf-8 -*-
"""反馈相关 Pydantic 模型。"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class FeedbackRequest(BaseModel):
    """反馈提交请求。"""

    message_id: str = Field(..., description="消息 ID")
    type: Literal["positive", "negative"] = Field(..., description="反馈类型")
    reason: Optional[str] = Field(None, description="反馈原因")
    comment: Optional[str] = Field(None, description="反馈评论")
