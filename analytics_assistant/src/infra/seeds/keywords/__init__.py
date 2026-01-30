# -*- coding: utf-8 -*-
"""
关键词种子数据

包含：
- complexity.py: 复杂度检测关键词
- intent.py: 意图识别关键词

用法：
    from analytics_assistant.src.infra.seeds.keywords import (
        COMPLEXITY_KEYWORDS,
        INTENT_KEYWORDS,
    )
"""

from .complexity import COMPLEXITY_KEYWORDS
from .intent import INTENT_KEYWORDS

__all__ = [
    "COMPLEXITY_KEYWORDS",
    "INTENT_KEYWORDS",
]
