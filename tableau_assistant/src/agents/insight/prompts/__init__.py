# -*- coding: utf-8 -*-
"""
Insight Agent Prompts

Prompt classes for Insight Agent.

Directory structure:
- prompts/ - Prompt template classes only
- models/ - All data models (including LLM output models)
- components/ - Business logic components
"""

from tableau_assistant.src.agents.insight.prompts.analyst import (
    AnalystPrompt,
    AnalystPromptWithHistory,
    ANALYST_PROMPT,
    ANALYST_PROMPT_WITH_HISTORY,
)
from tableau_assistant.src.agents.insight.prompts.director import (
    DirectorPrompt,
    DIRECTOR_PROMPT,
)


__all__ = [
    # Analyst
    "AnalystPrompt",
    "AnalystPromptWithHistory",
    "ANALYST_PROMPT",
    "ANALYST_PROMPT_WITH_HISTORY",
    # Director
    "DirectorPrompt",
    "DIRECTOR_PROMPT",
]
