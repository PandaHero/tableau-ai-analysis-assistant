# -*- coding: utf-8 -*-
"""用户设置相关 Pydantic 模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel


class UserSettingsResponse(BaseModel):
    """用户设置响应。"""

    tableau_username: str
    language: Literal["zh", "en"] = "zh"
    analysis_depth: Literal["detailed", "comprehensive"] = "detailed"
    theme: Literal["light", "dark", "system"] = "light"
    default_datasource_id: Optional[str] = None
    show_thinking_process: bool = True
    created_at: datetime
    updated_at: datetime


class UpdateSettingsRequest(BaseModel):
    """用户设置更新请求。"""

    language: Optional[Literal["zh", "en"]] = None
    analysis_depth: Optional[Literal["detailed", "comprehensive"]] = None
    theme: Optional[Literal["light", "dark", "system"]] = None
    default_datasource_id: Optional[str] = None
    show_thinking_process: Optional[bool] = None
