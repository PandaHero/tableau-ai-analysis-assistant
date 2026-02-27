# -*- coding: utf-8 -*-
"""
用户设置相关 Pydantic 模型

定义用户设置的请求和响应数据结构。
"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel

class UserSettingsResponse(BaseModel):
    """用户设置响应模型。"""

    tableau_username: str
    language: Literal["zh", "en"] = "zh"
    analysis_depth: Literal["detailed", "comprehensive"] = "detailed"
    theme: Literal["light", "dark", "system"] = "light"
    default_datasource_id: Optional[str] = None
    show_thinking_process: bool = True
    created_at: datetime
    updated_at: datetime

class UpdateSettingsRequest(BaseModel):
    """更新设置请求（部分更新，只更新非 None 字段）。"""

    language: Optional[Literal["zh", "en"]] = None
    analysis_depth: Optional[Literal["detailed", "comprehensive"]] = None
    theme: Optional[Literal["light", "dark", "system"]] = None
    default_datasource_id: Optional[str] = None
    show_thinking_process: Optional[bool] = None
