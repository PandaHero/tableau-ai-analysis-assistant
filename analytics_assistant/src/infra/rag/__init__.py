"""
RAG (Retrieval-Augmented Generation) Infrastructure

检索策略：精确匹配 → Embedding 检索 → LLM 重排序
不使用 BM25，避免分词依赖。
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
    ExactRetriever,
    EmbeddingRetriever,
    CascadeRetriever,
    RetrievalPipeline,
    RetrieverFactory,
    create_retriever,
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
    "ExactRetriever",
    "EmbeddingRetriever",
    "CascadeRetriever",
    "RetrievalPipeline",
    "RetrieverFactory",
    "create_retriever",
    # Reranker
    "BaseReranker",
    "DefaultReranker",
    "RRFReranker",
    "LLMReranker",
]
