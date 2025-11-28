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

**Think step by step:**

Step 1: Analyze the question
- Is it a single metric name? (e.g., "sales", "profit margin")
- Is it already a complete question?
- Is it exploratory (why/reason/explain)?

Step 2: Determine what to add
- Single metric → Add aggregation + time (if appropriate) + form complete question
- Incomplete phrase → Add missing parts + form complete question
- Complete question → Keep as is (or minimal changes)
- Exploratory question → Keep completely intact

Step 3: Construct enhanced question
- Build grammatically correct sentence
- **CRITICAL: Avoid word repetition** (e.g., DON'T say "sales of total sales")
- Keep it natural and fluent
- Add reasonable defaults (aggregation, time range if appropriate)

**Examples:**

Good enhancements:
- "sales" → "What is the total sales in the past week?"
- "profit margin" → "What is the average profit margin in the past month?"
- "sales by region" → "What is the total sales by region in the past week?"

Bad enhancements (AVOID THESE):
- "sales" → "sales of total sales in the past week" (repetitive! grammatically wrong!)
- "profit margin" → "profit margin" (no enhancement when clearly needed!)
- "sales" → "sales" (no change for single metric - must enhance!)

Keep unchanged:
- "Why is profit margin low?" (exploratory question - keep intact)
- "What is the total sales by region?" (already complete and clear)

**Key principles:**
1. Single metric name MUST be enhanced (add aggregation + time + complete question)
2. Avoid repeating the metric name in the enhanced question
3. Use natural phrasing: "What is the [aggregation] [metric] [time]?" NOT "[metric] of [aggregation] [metric]"
4. Add reasonable time range (past week/month) for trend-related queries
5. Exploratory questions (why/how/explain) must remain completely unchanged"""
    
    def get_constraints(self) -> str:
        return """MUST NOT: change intent, add optional info, use technical names, decompose exploratory questions
MUST: preserve wording, minimal changes, keep exploratory questions intact

**CRITICAL - Language Requirement:**
- If the original question is in Chinese, the boosted question MUST be in Chinese
- If the original question is in English, the boosted question MUST be in English
- NEVER translate the question to a different language
- Preserve the original language and natural phrasing style"""
    
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
