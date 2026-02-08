# -*- coding: utf-8 -*-
"""
字段语义推断 Prompt

包含：
- SYSTEM_PROMPT: 系统提示
- build_user_prompt: 构建用户提示
- get_system_prompt: 获取系统提示
"""
from .prompt import (
    SYSTEM_PROMPT,
    build_user_prompt,
    get_system_prompt,
)

__all__ = [
    "SYSTEM_PROMPT",
    "build_user_prompt",
    "get_system_prompt",
]
