"""Prompt templates for Semantic Parser Agent.

Prompt templates follow the design principles from appendix-e-prompt-model-guide.md:
- Prompt teaches LLM how to think (4-section structure: ROLE, TASK, DOMAIN KNOWLEDGE, CONSTRAINTS)
- Schema tells LLM what to output (XML tags in Field descriptions)
- Uses VizQLPrompt base class for automatic JSON Schema injection
"""

from .step1 import Step1Prompt, STEP1_PROMPT
from .step2 import Step2Prompt, STEP2_PROMPT
from .observer import (
    Step1ObserverPrompt,
    Step2ObserverPrompt,
    STEP1_OBSERVER_PROMPT,
    STEP2_OBSERVER_PROMPT,
    OBSERVER_PROMPT,
)

__all__ = [
    # Prompt classes
    "Step1Prompt",
    "Step2Prompt",
    "Step1ObserverPrompt",
    "Step2ObserverPrompt",
    # Prompt instances
    "STEP1_PROMPT",
    "STEP2_PROMPT",
    "STEP1_OBSERVER_PROMPT",
    "STEP2_OBSERVER_PROMPT",
    "OBSERVER_PROMPT",
]
