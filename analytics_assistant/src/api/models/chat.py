# -*- coding: utf-8 -*-
"""聊天接口的 Pydantic 契约。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class Message(BaseModel):
    """单条消息。"""

    role: Literal["user", "assistant", "system"]
    content: str
    created_at: Optional[datetime] = None


class ChatRequest(BaseModel):
    """`/api/chat/stream` 请求模型。"""

    messages: list[Message] = Field(
        ...,
        min_length=1,
        description="对话历史，最后一条必须是 user。",
    )
    datasource_luid: Optional[str] = Field(
        None,
        description="数据源 LUID，优先级高于 datasource_name。",
    )
    datasource_name: Optional[str] = Field(None, description="数据源名称。")
    project_name: Optional[str] = Field(None, description="数据源所在项目名称。")
    idempotency_key: Optional[str] = Field(None, description="请求幂等键。")
    language: Literal["zh", "en"] = Field(default="zh", description="请求语言。")
    analysis_depth: Literal["detailed", "comprehensive"] = Field(
        default="detailed",
        description="分析深度。",
    )
    replan_mode: Literal["user_select", "auto_continue", "stop"] = Field(
        default="user_select",
        description="后续分析策略。",
    )
    selected_candidate_question: Optional[str] = Field(
        None,
        description="当使用 user_select 时，调用方显式选中的候选问题。",
    )
    feature_flags: dict[str, bool] = Field(
        default_factory=dict,
        description="会话级功能开关，只允许布尔值。",
    )
    session_id: Optional[str] = Field(None, description="会话 ID。")
    thinking_mode: Optional[Literal["off", "summary", "debug"]] = Field(
        default=None,
        description="思考过程展示模式。",
    )

    @model_validator(mode="after")
    def validate_contract(self) -> "ChatRequest":
        """校验聊天入口契约。"""
        if not self.datasource_luid and not self.datasource_name:
            raise ValueError("datasource_luid 或 datasource_name 至少提供一个")
        if not self.messages or self.messages[-1].role != "user":
            raise ValueError("messages 最后一条必须是 user")
        return self


class ChatResumeRequest(BaseModel):
    """`/api/chat/resume` 请求模型。"""

    session_id: str = Field(..., description="会话 ID。")
    interrupt_id: str = Field(..., description="待恢复的中断 ID。")
    resume_payload: dict[str, Any] = Field(..., description="恢复输入 payload。")
    idempotency_key: Optional[str] = Field(None, description="请求幂等键。")
    thinking_mode: Optional[Literal["off", "summary", "debug"]] = Field(
        default=None,
        description="思考过程展示模式。",
    )
