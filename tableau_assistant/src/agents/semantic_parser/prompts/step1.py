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
Query = What (measures) × Where (dimensions + filters) × How (complexity)

**Think step by step:**
1. Merge context: Combine current question with conversation history
2. Generate restated_question in English
3. Extract entities from restated_question
4. Classify roles: measure vs dimension vs filter
5. Check measure aggregation: pre-aggregated vs regular
6. Detect computation: Check restated_question for complexity keywords
7. Preserve scope: Keep partition keywords (per X, within Y, by Z)

**Entity Classification**
- Measure: quantitative values, can be summed/averaged
- Dimension: categorical grouping, slicing criteria
- Filter: specific values, date ranges, conditions

**Measure Aggregation Check**
- Check Available Fields for [pre-aggregated] marker
- Pre-aggregated = calculated field with built-in aggregation (e.g., Ratio = SUM(A)/SUM(B))
- Regular measure needs aggregation (SUM, AVG, etc.)
- Pre-aggregated measure: aggregation = null (already aggregated)"""

    def get_constraints(self) -> str:
        return """MUST: Preserve partition intent, Use business terms from question, Provide reasoning
MUST NOT: Lose partition keywords, Invent field names, Assume missing information"""

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
