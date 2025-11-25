"""
Question Boost Prompt (Structured Template)

Uses the structured template system for better consistency and maintainability.
"""
from typing import Type
from pydantic import BaseModel
from tableau_assistant.prompts.base import DataAnalysisPrompt
from tableau_assistant.src.models.boost import QuestionBoost


class QuestionBoostPrompt(DataAnalysisPrompt):
    """Optimized prompt for question enhancement using 4-section structure
    
    Inherits from DataAnalysisPrompt because it needs data analysis context,
    but overrides get_domain_knowledge() to avoid verbose fundamentals.
    """
    
    def get_role(self) -> str:
        return "Data analyst who completes missing essential information."
    
    def get_task(self) -> str:
        return """Evaluate and add ONLY missing essential info.

Process: Check if exploratory (why/reason) → IF yes THEN return original → ELSE check essentials → IF missing THEN add minimal context → ELSE return original"""
    
    def get_domain_knowledge(self) -> str:
        """Override to provide only specific rules, not generic fundamentals"""
        return """Metadata: {metadata}

Decision rules:
MUST add: time (if trend/comparison), aggregation (if ambiguous)
DON'T add: dimensions, comparisons, TopN, sorting, specific field names (unless explicit)

Exploratory questions (keywords: why, reason, explain):
- Keep completely intact
- Don't add any clarifications or specifications"""
    
    def get_constraints(self) -> str:
        return """MUST NOT: change intent, add optional info, use technical names, decompose exploratory questions
MUST: preserve wording, minimal changes, keep exploratory questions intact"""
    
    def get_user_template(self) -> str:
        return """Original Question: "{question}"

Enhance this question to be more specific and analytically valuable while preserving the original intent."""
    
    def get_output_model(self) -> Type[BaseModel]:
        return QuestionBoost


# Create prompt instance for easy import
QUESTION_BOOST_PROMPT = QuestionBoostPrompt()


# ============= 导出 =============

__all__ = [
    "QuestionBoostPrompt",
    "QUESTION_BOOST_PROMPT",
]
