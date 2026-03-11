"""

RAG (Retrieval-Augmented Generation) Infrastructure

检索策略：精确匹配 → Embedding 检索 → LLM 重排序

不使用 BM25，避免分词依赖。

服务层架构：

- RAGService: 统一入口（单例）

- EmbeddingService: Embedding 服务

- IndexManager: 索引管理器

- RetrievalService: 检索服务
"""

from .models import (

    RetrievalSource,

    EmbeddingResult,

    FieldChunk,
    RetrievalResult,

    MappingResult,

)

# 相似度计算模块

from .similarity import (

    cosine_similarity,

    ScoreType,

    SimilarityCalculator,

    l2_similarity,

    inner_product_similarity,

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

# 服务层

from .service import RAGService, get_rag_service

from .embedding_service import EmbeddingService, EmbeddingStats

from .index_manager import IndexManager

from .retrieval_service import RetrievalService

# Schemas

from .schemas import (

    IndexConfig,

    IndexDocument,

    IndexInfo,

    IndexStatus,

    IndexBackend,

    UpdateResult,

    SearchResult,

)

# Exceptions

from .exceptions import (

    RAGError,

    EmbeddingError,
    RAGIndexError,

    IndexExistsError,

    IndexNotFoundError,

    IndexCreationError,

    StorageError,
    RetrievalError,

)

__all__ = [

    # Models

    "cosine_similarity",

    "RetrievalSource",

    "EmbeddingResult",

    "FieldChunk",
    "RetrievalResult",

    "MappingResult",

    # Similarity

    "ScoreType",

    "SimilarityCalculator",

    "l2_similarity",

    "inner_product_similarity",

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

    # Service Layer

    "RAGService",

    "get_rag_service",

    "EmbeddingService",

    "EmbeddingStats",

    "IndexManager",

    "RetrievalService",

    # Schemas

    "IndexConfig",

    "IndexDocument",

    "IndexInfo",

    "IndexStatus",

    "IndexBackend",

    "UpdateResult",

    "SearchResult",

    # Exceptions

    "RAGError",

    "EmbeddingError",

    "RAGIndexError",

    "IndexExistsError",

    "IndexNotFoundError",

    "IndexCreationError",

    "StorageError",
    "RetrievalError",

]

