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
from tableau_assistant.src.agents.semantic_parser.models import Step1Output


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
        return """Restate user's follow-up question as complete, standalone question.

Process: Merge history → Extract What/Where/How → Classify intent → Generate restatement"""

    def get_specific_domain_knowledge(self) -> str:
        return """**Three-Element Model**
Query = What × Where × How
- What: Target measures + aggregation
- Where: Dimensions + filters
- How: SIMPLE (no computation) | COMPLEX (needs Step 2)

**Think step by step:**
Step 1: Understand user intent
Step 2: Extract business entities (use exact terms from question)
Step 3: Classify entity roles (dimension vs measure)
Step 4: Detect if complex computation needed (ranking, running total, LOD, etc.)
Step 5: Preserve partition intent (per month/within month etc.)

**Intent Classification**
- DATA_QUERY: Has queryable fields, info complete
- CLARIFICATION: References unspecified values
- GENERAL: Asks about metadata/fields
- IRRELEVANT: Not about data analysis"""

    def get_constraints(self) -> str:
        return """MUST: Preserve partition intent, Use business terms, Provide reasoning
MUST: Output restated_question in the SAME LANGUAGE as the user's question
MUST NOT: Lose partition keywords, Invent fields, Classify as DATA_QUERY if incomplete"""

    def get_user_template(self) -> str:
        return """**Current Question:** {question}

**Conversation History:**
{history}

**Available Fields (for reference):**
{data_model}

**Current Time:** {current_time}

Please analyze this question and output Step1Output JSON."""

    def get_output_model(self) -> Type[BaseModel]:
        return Step1Output


# Create prompt instance
STEP1_PROMPT = Step1Prompt()

__all__ = ["Step1Prompt", "STEP1_PROMPT"]
