"""
工具函数

提供通用的工具函数。

主要功能：
- conversation: 对话处理工具

使用示例：
    from tableau_assistant.src.infra.utils import trim_answered_questions
    
    trimmed = trim_answered_questions(questions)
"""

from tableau_assistant.src.infra.utils.conversation import (
    trim_answered_questions,
    MAX_ANSWERED_QUESTIONS,
)

__all__ = [
    "trim_answered_questions",
    "MAX_ANSWERED_QUESTIONS",
]
