# -*- coding: utf-8 -*-
"""
通用 Pydantic 模型

定义错误响应和健康检查等通用数据结构。
"""

from typing import Optional

from pydantic import BaseModel

class ErrorResponse(BaseModel):
    """错误响应模型。"""

    error: str
    detail: Optional[str] = None
    code: Optional[str] = None

class HealthResponse(BaseModel):
    """健康检查响应。"""

    status: str
    version: str
    storage: str
