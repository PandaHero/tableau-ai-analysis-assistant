# -*- coding: utf-8 -*-
"""
维度层级推断 Prompts

Prompt 模板定义。
"""

from .prompt import (
    SYSTEM_PROMPT,
    build_user_prompt,
    build_dimension_inference_prompt,
    get_system_prompt,
)

__all__ = [
    "SYSTEM_PROMPT",
    "build_user_prompt",
    "build_dimension_inference_prompt",
    "get_system_prompt",
]
