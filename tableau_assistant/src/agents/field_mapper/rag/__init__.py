"""
FieldMapper RAG 专用组件（应用层）。

统一 RAG 基础设施已迁移到 `infra/rag/`，本包仅保留 FieldMapper 专用组件：
- KnowledgeAssembler
- FieldValueIndexer
- SemanticMapper

"""

from tableau_assistant.src.agents.field_mapper.rag.assembler import (
    ChunkStrategy,
    AssemblerConfig,
    KnowledgeAssembler,
)
from tableau_assistant.src.agents.field_mapper.rag.field_value_indexer import (
    FieldValueIndexer,
    ValueMatchResult,
    DistinctValuesResult,
)

from tableau_assistant.src.agents.field_mapper.rag.semantic_mapper import (
    SemanticMapper,
    MappingConfig,
    FieldMappingResult,
    MappingSource,
)


__all__ = [
    "ChunkStrategy",
    "AssemblerConfig",
    "KnowledgeAssembler",
    "FieldValueIndexer",

    "ValueMatchResult",
    "DistinctValuesResult",
    "SemanticMapper",
    "MappingConfig",
    "FieldMappingResult",
    "MappingSource",
]
