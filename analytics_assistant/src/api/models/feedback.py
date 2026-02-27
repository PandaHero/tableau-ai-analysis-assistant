# -*- coding: utf-8 -*-
"""
用户反馈相关 Pydantic 模型

定义反馈提交的请求数据结构。
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field

class FeedbackRequest(BaseModel):
    """反馈请求模型。"""

    message_id: str = Field(..., description="消息 ID")
    type: Literal["positive", "negative"] = Field(..., description="反馈类型")
    reason: Optional[str] = Field(None, description="反馈原因")
    comment: Optional[str] = Field(None, description="反馈评论")
