"""
Understanding Prompt (Structured Template)

Uses the structured template system for better consistency and maintainability.
"""
from typing import Type
from pydantic import BaseModel
from tableau_assistant.prompts.base import VizQLPrompt
from tableau_assistant.src.models.question import QuestionUnderstanding


class UnderstandingPrompt(VizQLPrompt):
    """Optimized prompt for question understanding using 4-section structure"""
    
    def get_role(self) -> str:
        return """Query analyzer who determines SQL roles of entities.

SQL Roles:
- Dimension: Aggregated (COUNT/COUNTD) or Grouped (GROUP BY)
- Measure: Always aggregated (SUM/AVG/MIN/MAX)"""
    
    def get_task(self) -> str:
        return """Extract entities, classify types, decide if split needed.

Process: Extract → Classify → Check aggregation → Decide split"""
    
    def get_specific_domain_knowledge(self) -> str:
        return """**Think step by step:**

Step 1: Identify all entities from question
- Which entities are dimensions? (categorical/grouping fields)
- Which entities are measures? (numeric/aggregated fields)
- Which entities are date fields? (temporal fields)

Step 2: Determine SQL role for EACH dimension
For each dimension, ask: "What is its SQL role in this query?"
- Analyze query pattern: Is dimension being counted/aggregated?
- Determine role: Aggregated (has SQL function) or Grouped (GROUP BY)

Step 3: Determine SQL aggregation for EACH measure
For each measure, ask: "What SQL aggregation is requested?"
- Analyze query requirement: What calculation is needed?
- Determine aggregation type based on query semantics

Step 4: Determine date field usage
For each date field, analyze its role:
- Grouping: Used to partition data by time periods (GROUP BY)
- Filtering: Used to filter data by time range (WHERE clause)
- Determine time granularity for grouping if applicable

Step 5: Handle exploratory questions
- Identify exploratory intent: Questions asking for insights, patterns, or general analysis
- Set needs_exploration flag: Mark as true for exploratory questions
- Do NOT select specific fields: Field selection will be done in task planning stage with metadata

Split decision:
| Scenario | Action |
|----------|--------|
| Comparison | Split: N queries (one per target) + 1 post_processing (to compare) |
| Multiple time periods | Split: separate queries |
| Cross-query calculation | Split: queries + post_processing |
| Exploratory (why/reason) | Single query ONLY, set needs_exploration=true, limit to 1-2 dimensions |
| Single query sufficient | Don't split |

Date expression:
- Identify year from context based on max_date
- Determine if time reference is absolute or relative
- Identify special date requirements (holidays, lunar calendar, week start day)
- Query builder will calculate specific date ranges from identified information"""
    
    def get_constraints(self) -> str:
        return """MUST NOT: invent entities, use technical names, split exploratory questions
MUST: extract ALL entities, use business terms, set needs_exploration=true for why/reason questions, determine SQL role for each entity"""
    
    def get_user_template(self) -> str:
        return """Question: "{question}"

Current date: {max_date}"""
    
    def get_output_model(self) -> Type[BaseModel]:
        return QuestionUnderstanding


# Create prompt instance for easy import
UNDERSTANDING_PROMPT = UnderstandingPrompt()


# ============= 导出 =============

__all__ = [
    "UnderstandingPrompt",
    "UNDERSTANDING_PROMPT",
]
