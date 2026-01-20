"""
RAG (Retrieval-Augmented Generation) Infrastructure

This module provides unified retrieval capabilities for the analytics assistant.
"""

from .models import (
    RetrievalSource,
    EmbeddingResult,
    FieldChunk,
    RetrievalResult,
    MappingResult,
)

from .retriever import (
    RetrievalConfig,
    MetadataFilter,
    BaseRetriever,
    EmbeddingRetriever,
    KeywordRetriever,
    HybridRetriever,
    RetrievalPipeline,
    RetrieverFactory,
    Tokenizer,
)

from .vector_index_manager import (
    IndexConfig,
    VectorIndexManager,
)

from .reranker import (
    BaseReranker,
    DefaultReranker,
    RRFReranker,
    LLMReranker,
)

__all__ = [
    # Models
    "RetrievalSource",
    "EmbeddingResult",
    "FieldChunk",
    "RetrievalResult",
    "MappingResult",
    # Retriever
    "RetrievalConfig",
    "MetadataFilter",
    "BaseRetriever",
    "EmbeddingRetriever",
    "KeywordRetriever",
    "HybridRetriever",
    "RetrievalPipeline",
    "RetrieverFactory",
    "Tokenizer",
    # Vector Index Manager
    "IndexConfig",
    "VectorIndexManager",
    # Reranker
    "BaseReranker",
    "DefaultReranker",
    "RRFReranker",
    "LLMReranker",
]
