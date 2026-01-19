"""Prompt templates for Semantic Parser Agent.

Prompt templates follow the design principles from appendix-e-prompt-model-guide.md:
- Prompt teaches LLM how to think (4-section structure: ROLE, TASK, DOMAIN KNOWLEDGE, CONSTRAINTS)
- Schema tells LLM what to output (XML tags in Field descriptions)
- Uses VizQLPrompt base class for automatic JSON Schema injection

Note: Observer prompts have been removed. ReAct error handling replaces Observer.
"""

from tableau_assistant.src.agents.semantic_parser.prompts.step1 import Step1Prompt, STEP1_PROMPT
from tableau_assistant.src.agents.semantic_parser.prompts.step2 import Step2Prompt, STEP2_PROMPT
from tableau_assistant.src.agents.semantic_parser.prompts.react_error import ReActErrorHandlerPrompt, REACT_ERROR_PROMPT


__all__ = [
    # Prompt classes
    "Step1Prompt",
    "Step2Prompt",
    "ReActErrorHandlerPrompt",
    # Prompt instances
    "STEP1_PROMPT",
    "STEP2_PROMPT",
    "REACT_ERROR_PROMPT",
]
