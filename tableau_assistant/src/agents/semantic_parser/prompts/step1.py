# -*- coding: utf-8 -*-
"""Step 1 Prompt - Semantic understanding and question restatement.

Step 1 is the "Intuition" phase of the LLM combination architecture.
It understands the user question, restates it as a complete standalone question,
extracts structured What/Where/How, and classifies intent.

Design principles (from appendix-e-prompt-model-guide.md):
- Prompt teaches LLM HOW to think (4-section structure)
- Schema tells LLM WHAT to output (XML tags in Field descriptions)
- Uses VizQLPrompt base class for automatic JSON Schema injection
"""

from typing import Type
from pydantic import BaseModel

from tableau_assistant.src.agents.base.prompt import VizQLPrompt
from tableau_assistant.src.core.models import Step1Output


class Step1Prompt(VizQLPrompt):
    """Step 1: Semantic understanding and question restatement.
    
    Uses 4-section structure:
    - ROLE: Define the AI's role
    - TASK: Define the task with implicit CoT
    - DOMAIN KNOWLEDGE: Provide domain-specific rules
    - CONSTRAINTS: Define boundaries
    """
    
    def get_role(self) -> str:
        return """Semantic understanding expert for data analysis queries.

Expertise: Question restatement, Three-element model extraction, Intent classification"""

    def get_task(self) -> str:
        return """Restate user's follow-up question as a complete, standalone question.

Process: Merge history context -> Extract What/Where/How -> Classify intent -> Generate restatement"""

    def get_specific_domain_knowledge(self) -> str:
        return """**Three-Element Model**

Query = What × Where × How
- What: Target measures + aggregation
- Where: Dimensions + filters
- How: SIMPLE | RANKING | CUMULATIVE | COMPARISON | GRANULARITY

**Think step by step:**

Step 1: Understand user intent - What does the user want to know?
Step 2: Extract business entities - Use exact terms from question
Step 3: Classify entity roles - Dimension vs Measure
Step 4: Detect date/time constraints as filters
Step 5: Detect analysis type from keywords (排名/占比/同比/累计)
Step 6: Preserve partition intent (每月/当月/全国)

**Intent Classification**

- DATA_QUERY: Has queryable fields, info complete
- CLARIFICATION: References unspecified values
- GENERAL: Asks about metadata/fields
- IRRELEVANT: Not about data analysis

**Merge Rules (for follow-up questions):**

- Current mentions explicitly → Use current value
- Current doesn't mention → Inherit from history
- Current modifies → Replace corresponding element
- Current adds → Merge with history"""

    def get_constraints(self) -> str:
        return """MUST: Preserve partition intent, Use exact terms from user question, Provide reasoning
MUST NOT: Lose partition keywords, Invent fields, Classify as DATA_QUERY if incomplete
MUST NOT: Select field names from metadata - extract exact terms from user question only (field mapping is done later by FieldMapper)"""

    def get_user_template(self) -> str:
        return """**Current Question:** {question}

**Conversation History:**
{history}

**Available Fields (for reference):**
{metadata}

**Current Time:** {current_time}

Please analyze this question and output Step1Output JSON."""

    def get_output_model(self) -> Type[BaseModel]:
        return Step1Output


# Create prompt instance
STEP1_PROMPT = Step1Prompt()

# Legacy constants for backward compatibility
STEP1_SYSTEM_PROMPT = STEP1_PROMPT.get_system_message()
STEP1_USER_TEMPLATE = STEP1_PROMPT.get_user_template()

__all__ = ["Step1Prompt", "STEP1_PROMPT", "STEP1_SYSTEM_PROMPT", "STEP1_USER_TEMPLATE"]
