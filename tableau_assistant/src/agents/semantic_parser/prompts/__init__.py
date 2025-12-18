"""Prompt templates for Semantic Parser Agent.

Prompt templates follow the design principles from appendix-e-prompt-model-guide.md:
- Prompt teaches LLM how to think (4-section structure: ROLE, TASK, DOMAIN KNOWLEDGE, CONSTRAINTS)
- Schema tells LLM what to output (XML tags in Field descriptions)
- Uses VizQLPrompt base class for automatic JSON Schema injection
"""

from .step1 import Step1Prompt, STEP1_PROMPT, STEP1_SYSTEM_PROMPT, STEP1_USER_TEMPLATE
from .step2 import Step2Prompt, STEP2_PROMPT, STEP2_SYSTEM_PROMPT, STEP2_USER_TEMPLATE
from .observer import ObserverPrompt, OBSERVER_PROMPT, OBSERVER_SYSTEM_PROMPT, OBSERVER_USER_TEMPLATE

__all__ = [
    # Prompt classes (recommended)
    "Step1Prompt",
    "Step2Prompt",
    "ObserverPrompt",
    # Prompt instances (recommended)
    "STEP1_PROMPT",
    "STEP2_PROMPT",
    "OBSERVER_PROMPT",
    # Legacy constants (for backward compatibility)
    "STEP1_SYSTEM_PROMPT",
    "STEP1_USER_TEMPLATE",
    "STEP2_SYSTEM_PROMPT",
    "STEP2_USER_TEMPLATE",
    "OBSERVER_SYSTEM_PROMPT",
    "OBSERVER_USER_TEMPLATE",
]
