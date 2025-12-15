"""
Conversation utilities for managing dialogue history.

Provides functions for:
- Trimming answered questions list to avoid prompt overflow
- Managing conversation context

Requirements:
- R14.6: answered_questions 列表超过 20 个时只保留最近 20 个
"""

from typing import List

# Maximum number of answered questions to keep
MAX_ANSWERED_QUESTIONS = 20


def trim_answered_questions(
    questions: List[str],
    max_length: int = MAX_ANSWERED_QUESTIONS,
) -> List[str]:
    """
    Trim answered questions list to avoid prompt overflow.
    
    Keeps only the most recent N questions to prevent the Replanner
    prompt from exceeding token limits.
    
    Args:
        questions: List of answered questions
        max_length: Maximum number of questions to keep (default: 20)
    
    Returns:
        Trimmed list of questions (most recent ones)
    
    Example:
        >>> questions = ["Q1", "Q2", ..., "Q25"]
        >>> trimmed = trim_answered_questions(questions)
        >>> len(trimmed)
        20
        >>> trimmed[0]
        "Q6"  # Oldest kept question
    """
    if len(questions) <= max_length:
        return questions
    
    # Keep only the most recent questions
    return questions[-max_length:]
