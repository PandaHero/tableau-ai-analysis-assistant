"""
FieldMapper RAG 专用组件（应用层）。

统一 RAG 基础设施已迁移到 `infra/rag/`，本包仅保留 FieldMapper 专用组件：
- KnowledgeAssembler
- DimensionPattern
- FieldValueIndexer
- SemanticMapper
"""

from .assembler import (
    ChunkStrategy,
    AssemblerConfig,
    KnowledgeAssembler,
)
from .dimension_pattern import (
    DimensionPattern,
    PatternSearchResult,
    DimensionPatternStore,
    DimensionHierarchyRAG,
)
from .field_value_indexer import (
    FieldValueIndexer,
    ValueMatchResult,
    DistinctValuesResult,
)
from .semantic_mapper import (
    SemanticMapper,
    MappingConfig,
    FieldMappingResult,
    MappingSource,
)

__all__ = [
    "ChunkStrategy",
    "AssemblerConfig",
    "KnowledgeAssembler",
    "DimensionPattern",
    "PatternSearchResult",
    "DimensionPatternStore",
    "DimensionHierarchyRAG",
    "FieldValueIndexer",
    "ValueMatchResult",
    "DistinctValuesResult",
    "SemanticMapper",
    "MappingConfig",
    "FieldMappingResult",
    "MappingSource",
]
