"""
Replanner utilities for managing dialogue history.
"""
from typing import List

MAX_ANSWERED_QUESTIONS = 20


def trim_answered_questions(questions: List[str], max_length: int = MAX_ANSWERED_QUESTIONS) -> List[str]:
    """Trim answered questions list to avoid prompt overflow."""
    if len(questions) <= max_length:
        return questions
    return questions[-max_length:]
