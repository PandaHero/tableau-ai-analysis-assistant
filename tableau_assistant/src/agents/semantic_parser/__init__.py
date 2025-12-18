"""Semantic Parser Agent - LLM combination architecture.

This agent implements the LLM combination pattern:
- Step 1: Semantic understanding and question restatement (Intuition)
- Step 2: Computation reasoning and self-validation (Reasoning)
- Observer: Consistency checking (Metacognition, on-demand)

The agent outputs SemanticParseResult containing:
- restated_question: Complete standalone question
- intent: Intent classification (DATA_QUERY, CLARIFICATION, GENERAL, IRRELEVANT)
- semantic_query: Platform-agnostic query (for DATA_QUERY intent)
- clarification: Clarification question (for CLARIFICATION intent)
- general_response: General response (for GENERAL intent)
"""

from .agent import SemanticParserAgent
from .node import SemanticParserNode, semantic_parser_node

__all__ = [
    "SemanticParserAgent",
    "SemanticParserNode",
    "semantic_parser_node",
]
