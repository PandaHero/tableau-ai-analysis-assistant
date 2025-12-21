# -*- coding: utf-8 -*-
"""
FieldMapper Prompt - 字段映射 Agent 的 Prompt 定义

遵循 VizQLPrompt 规范，使用 4 段式结构。
"""
from typing import Type

from pydantic import BaseModel

from tableau_assistant.src.agents.base.prompt import VizQLPrompt
from tableau_assistant.src.core.models import SingleSelectionResult


class FieldMapperPrompt(VizQLPrompt):
    """
    字段映射 Agent 的 Prompt
    
    将业务术语映射到技术字段名，使用 RAG 候选 + LLM 精选策略。
    """
    
    def get_role(self) -> str:
        return """Field mapping expert who matches business terms to technical field names.

Expertise: semantic matching, field disambiguation, context-aware selection."""
    
    def get_task(self) -> str:
        return """Select the best matching technical field for the business term.

Process: Analyze term semantics -> Compare candidates -> Consider context -> Select best match or null."""
    
    def get_specific_domain_knowledge(self) -> str:
        return """**Think step by step:**

Step 1: Analyze business term semantics
- What does the term mean in business context?
- Is it likely a dimension (categorical) or measure (numeric)?

Step 2: Compare with candidates
- Match field name and caption semantically
- Consider sample values as evidence
- Check data type compatibility

Step 3: Consider context
- Use question context for disambiguation
- Consider field role (dimension vs measure)

Step 4: Make decision
- Evaluate semantic match strength
- Set selected_field to null if no good match exists"""
    
    def get_constraints(self) -> str:
        return """MUST: Only select from provided candidates
MUST: Set selected_field to null if no candidate is a good match
MUST NOT: Invent field names not in candidates
MUST NOT: Select based only on keyword overlap without semantic understanding"""
    
    def get_user_template(self) -> str:
        return """Select the best matching field for this business term:

## Business Term
"{term}"

## Context
{context}

## Candidate Fields
{candidates}

Output JSON with selected_field, confidence, and reasoning."""
    
    def get_output_model(self) -> Type[BaseModel]:
        return SingleSelectionResult


# 单例 Prompt 实例
FIELD_MAPPER_PROMPT = FieldMapperPrompt()


__all__ = [
    "FieldMapperPrompt",
    "SingleSelectionResult",
    "FIELD_MAPPER_PROMPT",
]
