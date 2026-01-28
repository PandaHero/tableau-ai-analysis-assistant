# -*- coding: utf-8 -*-
"""
Semantic Parser Enums

枚举类型定义：
- PromptComplexity: Prompt 复杂度类型
"""
from enum import Enum


class PromptComplexity(str, Enum):
    """Prompt 复杂度类型
    
    - SIMPLE: 简单查询（直接聚合、简单过滤）
    - COMPLEX: 复杂查询（派生度量、子查询、表计算）
    """
    SIMPLE = "simple"
    COMPLEX = "complex"


__all__ = [
    "PromptComplexity",
]
