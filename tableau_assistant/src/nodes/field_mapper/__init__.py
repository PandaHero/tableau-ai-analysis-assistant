"""
FieldMapper Node - RAG + LLM Hybrid Node

Responsible for mapping business terms to technical field names.

Strategy:
1. RAG retrieval: SemanticMapper.search()
2. Fast path: confidence >= 0.9, return directly (no LLM)
3. LLM fallback: confidence < 0.9, use LLM to select from top-k candidates

Input: SemanticQuery (business terms)
Output: MappedQuery (technical fields)
"""

from tableau_assistant.src.nodes.field_mapper.node import (
    field_mapper_node,
    FieldMapperNode,
)
from tableau_assistant.src.nodes.field_mapper.llm_selector import (
    LLMCandidateSelector,
)
from tableau_assistant.src.nodes.field_mapper.cache import (
    FieldMappingCache,
)
from tableau_assistant.src.nodes.field_mapper.hierarchy_inferrer import (
    HierarchyInferrer,
    HierarchyInferenceResult,
)

__all__ = [
    "field_mapper_node",
    "FieldMapperNode",
    "LLMCandidateSelector",
    "FieldMappingCache",
    "HierarchyInferrer",
    "HierarchyInferenceResult",
]
